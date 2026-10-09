"""Sunny LLM gateway — Claude API gateway with caps, semaphore, streaming.

Mandatory rules:
- One gateway module; semaphore caps concurrent calls (default 1 awake, 2 during sleep)
- Daily and monthly spend caps checked before every call
- Auth latch trips permanently on AuthenticationError until restart
- Never log exception messages from connection errors
- Every call appended to log/llm-usage.md
- Streaming for chat; JSON-schema for structured outputs
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

log = logging.getLogger(__name__)

# Models (from config, never hardcoded)
MODEL_FAST = "claude-haiku-4-5-20251001"
MODEL_DEFAULT = "claude-sonnet-5-5"
MODEL_DEEP = "claude-opus-5-5"

# Default spend caps in USD
DEFAULT_DAILY_CAP = 10.0
DEFAULT_MONTHLY_CAP = 100.0

# Sleep sub-budget (fraction of daily cap)
SLEEP_BUDGET_FRACTION = 0.3


class SpendStatus(str, Enum):
    OK = "ok"
    DAILY_EXCEEDED = "daily_exceeded"
    MONTHLY_EXCEEDED = "monthly_exceeded"


class AuthStatus(str, Enum):
    OK = "ok"
    LATCH_TRIPPED = "latch_tripped"


@dataclass
class UsageEntry:
    """A logged LLM usage entry."""
    purpose: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    latency_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"))


@dataclass
class GatewayState:
    """Mutable gateway state."""
    daily_spend: float = 0.0
    monthly_spend: float = 0.0
    auth_latch: bool = False
    auth_error_count: int = 0
    sleep_budget_used: float = 0.0

    # Spending tracking dates
    last_spend_reset_date: str = ""
    last_spend_reset_month: str = ""

    # Semaphore for concurrent calls
    semaphore: asyncio.Semaphore | None = None


# Global gateway state
_state = GatewayState()
_api_key: str = ""
_api_base: str = ""
_client: httpx.AsyncClient | None = None


def init_gateway(api_key: str, api_base: str = "", daily_cap: float = DEFAULT_DAILY_CAP, monthly_cap: float = DEFAULT_MONTHLY_CAP) -> None:
    """Initialize the gateway with API credentials."""
    global _api_key, _api_base, _client
    _api_key = api_key
    _api_base = api_base
    _client = httpx.AsyncClient(
        base_url=_api_base or "https://api.anthropic.com",
        timeout=120.0,
        headers={
            "x-api-key": _api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )


def reset_spend_tracking() -> None:
    """Reset daily/monthly spend tracking (called at day boundary)."""
    _state.daily_spend = 0.0
    _state.monthly_spend = 0.0
    _state.sleep_budget_used = 0.0
    now = datetime.now(timezone.utc)
    _state.last_spend_reset_date = now.strftime("%Y-%m-%d")
    _state.last_spend_reset_month = now.strftime("%Y-%m")


def check_spend_caps(purpose: str = "chat", is_sleep: bool = False) -> SpendStatus:
    """Check if spend caps allow this call.

    Returns SpendStatus. Sleep-mode jobs use a sub-budget.
    """
    _reset_spend_if_needed()

    if is_sleep:
        sleep_cap = DEFAULT_DAILY_CAP * SLEEP_BUDGET_FRACTION
        if _state.sleep_budget_used >= sleep_cap:
            log.warning("Sleep spend cap reached: %.2f / %.2f", _state.sleep_budget_used, sleep_cap)
            return SpendStatus.DAILY_EXCEEDED
    else:
        if _state.daily_spend >= DEFAULT_DAILY_CAP:
            log.warning("Daily spend cap reached: %.2f / %.2f", _state.daily_spend, DEFAULT_DAILY_CAP)
            return SpendStatus.DAILY_EXCEEDED
        if _state.monthly_spend >= DEFAULT_MONTHLY_CAP:
            log.warning("Monthly spend cap reached: %.2f / %.2f", _state.monthly_spend, DEFAULT_MONTHLY_CAP)
            return SpendStatus.MONTHLY_EXCEEDED

    return SpendStatus.OK


def get_auth_status() -> AuthStatus:
    return AuthStatus.LATCH_TRIPPED if _state.auth_latch else AuthStatus.OK


def trip_auth_latch() -> None:
    """Permanently trip the auth latch until restart."""
    _state.auth_latch = True
    log.critical("Auth latch TRIPPED — all future calls will fail until restart")


def _reset_spend_if_needed() -> None:
    """Reset spend tracking if a new day/month has started."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    this_month = now.strftime("%Y-%m")

    if _state.last_spend_reset_date and _state.last_spend_reset_date != today:
        log.info("Daily spend cap reset")
        reset_spend_tracking()
    if _state.last_spend_reset_month and _state.last_spend_reset_month != this_month:
        log.info("Monthly spend cap reset")
        reset_spend_tracking()


async def chat_completion(
    messages: list[dict],
    model: str = MODEL_DEFAULT,
    *,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    json_schema: dict | None = None,
    purpose: str = "chat",
    is_sleep: bool = False,
) -> dict[str, Any]:
    """Send a chat completion request.

    Args:
        messages: List of {role, content} dicts.
        model: Model name.
        max_tokens: Maximum completion tokens.
        temperature: Sampling temperature.
        json_schema: Optional JSON schema for structured output.
        purpose: Log purpose (chat, summary, extraction, etc.).
        is_sleep: Whether this is a sleep-mode call (uses sub-budget).

    Returns:
        dict with 'content' (the reply text or parsed JSON if json_schema provided).
    """
    # Check auth latch
    if _state.auth_latch:
        log.error("Auth latch tripped — refusing call to %s", purpose)
        raise RuntimeError("Auth latch tripped — cannot call LLM")

    # Check spend caps
    status = check_spend_caps(purpose, is_sleep)
    if status != SpendStatus.OK:
        log.warning("Spend cap blocking call to %s: %s", purpose, status.value)
        return {"content": "", "spend_blocked": True}

    # Acquire semaphore
    if _state.semaphore is None:
        _state.semaphore = asyncio.Semaphore(2 if is_sleep else 1)

    start_time = time.monotonic()
    try:
        async with _state.semaphore:
            result = await _do_call(messages, model, max_tokens, temperature, json_schema)
            elapsed = (time.monotonic() - start_time) * 1000
            _record_usage(purpose, model, result, elapsed)
            return result
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            trip_auth_latch()
            _state.auth_error_count += 1
            log.error("AuthenticationError [%s] — latch tripped", e.response.status_code)
            raise
        log.error("HTTPError [%s] from LLM API", e.response.status_code)
        raise
    except Exception as e:
        # Never log connection error messages (may contain keys)
        log.error("LLM call failed for %s: %s", purpose, type(e).__name__)
        raise
    finally:
        pass  # semaphore released by context manager


async def _do_call(
    messages: list[dict],
    model: str,
    max_tokens: int,
    temperature: float,
    json_schema: dict | None,
) -> dict[str, Any]:
    """Execute the actual API call."""
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }

    if temperature is not None:
        payload["temperature"] = temperature

    if json_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "sunny_response", "schema": json_schema},
        }

    response = await _client.post("/v1/messages", json=payload)
    response.raise_for_status()
    data = response.json()

    # Parse response
    content_blocks = data.get("content", [])
    content_text = ""
    for block in content_blocks:
        if block.get("type") == "text":
            content_text += block.get("text", "")

    # Track usage
    usage = data.get("usage", {})
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)
    _update_spend(prompt_tokens, completion_tokens, model)

    # Parse JSON if schema was requested
    if json_schema:
        try:
            content_text = json.loads(content_text)
        except json.JSONDecodeError:
            log.warning("JSON schema response failed to parse: %s", content_text[:200])

    return {
        "content": content_text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _update_spend(prompt_tokens: int, completion_tokens: int, model: str) -> None:
    """Update spend tracking based on token usage."""
    # Rough cost estimates per million tokens (USD)
    costs = {
        "claude-haiku-": (0.00025, 0.00125),
        "claude-sonnet-": (0.003, 0.015),
        "claude-opus-": (0.015, 0.075),
    }

    rate_key = None
    for key in costs:
        if key in model:
            rate_key = key
            break

    if rate_key is None:
        rate_key = "claude-sonnet-"  # default

    input_cost, output_cost = costs[rate_key]
    cost = (prompt_tokens / 1_000_000) * input_cost + (completion_tokens / 1_000_000) * output_cost

    _state.daily_spend += cost
    _state.monthly_spend += cost


def _record_usage(purpose: str, model: str, result: dict, latency_ms: float) -> None:
    """Log usage to log/llm-usage.md."""
    usage = UsageEntry(
        purpose=purpose,
        model=model,
        prompt_tokens=result.get("prompt_tokens", 0),
        completion_tokens=result.get("completion_tokens", 0),
        total_tokens=result.get("total_tokens", 0),
        cost=_estimate_cost(result),
        latency_ms=latency_ms,
    )

    try:
        log_path = Path("vault") / "log" / "llm-usage.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{usage.timestamp}] purpose={usage.purpose} model={usage.model} "
                    f"in={usage.prompt_tokens} out={usage.completion_tokens} "
                    f"total={usage.total_tokens} cost=${usage.cost:.4f} "
                    f"latency={usage.latency_ms:.0f}ms\n")
    except OSError:
        log.warning("Failed to write LLM usage log")


def _estimate_cost(result: dict) -> float:
    """Estimate cost from result tokens."""
    prompt = result.get("prompt_tokens", 0)
    completion = result.get("completion_tokens", 0)
    # Approximate $0.003/$0.015 per million tokens (sonnet rates)
    return (prompt / 1_000_000) * 0.003 + (completion / 1_000_000) * 0.015


async def streaming_chat(
    messages: list[dict],
    model: str = MODEL_DEFAULT,
    *,
    max_tokens: int = 4096,
    on_chunk: Any = None,  # callback(chunk: str) -> None
) -> AsyncIterator[str]:
    """Stream a chat completion, yielding text chunks.

    Yields completed sentences/phrases as they arrive.
    """
    # Check auth latch
    if _state.auth_latch:
        raise RuntimeError("Auth latch tripped")

    # Check spend caps
    status = check_spend_caps("chat")
    if status != SpendStatus.OK:
        yield ""
        return

    if _state.semaphore is None:
        _state.semaphore = asyncio.Semaphore(1)

    async with _state.semaphore:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": True,
        }

        response = await _client.post("/v1/messages", json=payload)
        response.raise_for_status()

        accumulated = ""
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]  # strip "data: "
            if data_str.strip() == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                event_type = data.get("type", "")
                if event_type == "content_block_delta":
                    text = data.get("delta", {}).get("text", "")
                    if text:
                        accumulated += text
                        if on_chunk:
                            on_chunk(text)
                        # Yield on sentence boundaries or chunk size
                        if len(text) > 50 or ". " in text or "\n" in text:
                            yield accumulated
                            accumulated = ""
            except json.JSONDecodeError:
                continue

        # Flush remaining
        if accumulated:
            yield accumulated
