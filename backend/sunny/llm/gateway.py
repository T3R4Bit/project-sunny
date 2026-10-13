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

import anthropic

from sunny import config

log = logging.getLogger(__name__)

# Fallback model IDs; the live values come from settings (SUNNY_MODEL_*).
MODEL_FAST = "claude-haiku-5-5"
MODEL_DEFAULT = "claude-sonnet-5-5"
MODEL_DEEP = "claude-opus-5-5"

# Sleep sub-budget (fraction of daily cap)
SLEEP_BUDGET_FRACTION = 0.3

# USD per million tokens (input, output), matched by model-ID prefix.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-": (5.0, 25.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-sonnet-": (2.0, 10.0),
    "claude-haiku-5": (0.10, 0.50),
    "claude-haiku-": (1.0, 5.0),
}

# Server-side refusal fallback (routes a refused request to another model by category).
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")


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
_client: anthropic.AsyncAnthropic | None = None
_sync_client: anthropic.Anthropic | None = None
_spend_loaded = False


def init_gateway(api_key: str, api_base: str = "") -> None:
    """Create the Claude client explicitly (otherwise it is built lazily from settings)."""
    global _client
    base_url = api_base.rstrip("/").removesuffix("/v1") or None
    _client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url, timeout=600.0, max_retries=2)


def _get_client() -> anthropic.AsyncAnthropic:
    if _client is None:
        settings = config.get_settings()
        if not settings.claude_api_key:
            raise RuntimeError("CLAUDE_API_KEY is not set")
        init_gateway(settings.claude_api_key, settings.claude_base_url)
    return _client


def _get_sync_client() -> anthropic.Anthropic:
    global _sync_client
    if _sync_client is None:
        settings = config.get_settings()
        if not settings.claude_api_key:
            raise RuntimeError("CLAUDE_API_KEY is not set")
        base_url = settings.claude_base_url.rstrip("/").removesuffix("/v1") or None
        _sync_client = anthropic.Anthropic(api_key=settings.claude_api_key, base_url=base_url,
                                           timeout=600.0, max_retries=2)
    return _sync_client


def _model(model: str | None) -> str:
    return model or config.get_settings().model_default


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
    _load_spend()
    _reset_spend_if_needed()
    settings = config.get_settings()
    daily_cap, monthly_cap = settings.llm_spend_daily, settings.llm_spend_monthly

    if is_sleep:
        sleep_cap = daily_cap * SLEEP_BUDGET_FRACTION
        if _state.sleep_budget_used >= sleep_cap:
            log.warning("Sleep spend cap reached: %.2f / %.2f", _state.sleep_budget_used, sleep_cap)
            return SpendStatus.DAILY_EXCEEDED
    else:
        if _state.daily_spend >= daily_cap:
            log.warning("Daily spend cap reached: %.2f / %.2f", _state.daily_spend, daily_cap)
            return SpendStatus.DAILY_EXCEEDED
        if _state.monthly_spend >= monthly_cap:
            log.warning("Monthly spend cap reached: %.2f / %.2f", _state.monthly_spend, monthly_cap)
            return SpendStatus.MONTHLY_EXCEEDED

    return SpendStatus.OK


def get_auth_status() -> AuthStatus:
    return AuthStatus.LATCH_TRIPPED if _state.auth_latch else AuthStatus.OK


def trip_auth_latch() -> None:
    """Permanently trip the auth latch until restart."""
    _state.auth_latch = True
    log.critical("Auth latch TRIPPED — all future calls will fail until restart")


def _reset_spend_if_needed() -> None:
    """Reset daily (and on a new month, monthly) spend when the period rolls over."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    this_month = now.strftime("%Y-%m")

    if _state.last_spend_reset_month and _state.last_spend_reset_month != this_month:
        log.info("Monthly spend cap reset")
        reset_spend_tracking()
    elif _state.last_spend_reset_date and _state.last_spend_reset_date != today:
        log.info("Daily spend cap reset")
        _state.daily_spend = 0.0
        _state.sleep_budget_used = 0.0
        _state.last_spend_reset_date = today
    elif not _state.last_spend_reset_date:
        _state.last_spend_reset_date = today
        _state.last_spend_reset_month = this_month


# --- Spend persistence (so restarts don't reset the caps) ---


def _spend_file() -> Path:
    return Path(config.get_settings().db_path).parent / "llm-spend.json"


def _load_spend() -> None:
    global _spend_loaded
    if _spend_loaded:
        return
    _spend_loaded = True
    try:
        data = json.loads(_spend_file().read_text())
    except (OSError, ValueError):
        return
    _state.daily_spend = float(data.get("daily_spend", 0.0))
    _state.monthly_spend = float(data.get("monthly_spend", 0.0))
    _state.sleep_budget_used = float(data.get("sleep_budget_used", 0.0))
    _state.last_spend_reset_date = data.get("date", "")
    _state.last_spend_reset_month = data.get("month", "")


def _save_spend() -> None:
    try:
        path = _spend_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "daily_spend": _state.daily_spend,
            "monthly_spend": _state.monthly_spend,
            "sleep_budget_used": _state.sleep_budget_used,
            "date": _state.last_spend_reset_date,
            "month": _state.last_spend_reset_month,
        }))
    except OSError:
        log.warning("Failed to persist LLM spend")


# --- Request building ---


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Move leading system messages into the top-level system prompt (the API takes it there)."""
    system_parts: list[str] = []
    rest: list[dict] = []
    for m in messages:
        if m.get("role") == "system" and not rest:
            system_parts.append(str(m.get("content", "")))
        else:
            rest.append(m)
    return "\n\n".join(p for p in system_parts if p), rest


def _request_kwargs(messages: list[dict], model: str, max_tokens: int) -> dict[str, Any]:
    system, msgs = _split_system(messages)
    kwargs: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": msgs}
    if system:
        kwargs["system"] = system
    if model in _FALLBACK_MODELS:
        kwargs["extra_headers"] = {"anthropic-beta": _FALLBACK_BETA}
        kwargs["extra_body"] = {"fallbacks": "default"}
    return kwargs


def _semaphore(is_sleep: bool) -> asyncio.Semaphore:
    if _state.semaphore is None:
        _state.semaphore = asyncio.Semaphore(config.get_settings().llm_max_concurrent if is_sleep else 1)
    return _state.semaphore


async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    *,
    max_tokens: int = 16000,
    temperature: float | None = None,  # ignored: current models reject sampling params
    json_schema: dict | None = None,
    purpose: str = "chat",
    is_sleep: bool = False,
) -> dict[str, Any]:
    """Send a chat completion request.

    Args:
        messages: List of {role, content} dicts; leading "system" entries become the system prompt.
        model: Model ID (defaults to SUNNY_MODEL_DEFAULT).
        max_tokens: Maximum completion tokens.
        json_schema: Optional JSON schema for structured output.
        purpose: Log purpose (chat, summary, extraction, etc.).
        is_sleep: Whether this is a sleep-mode call (uses sub-budget).

    Returns:
        dict with 'content' (the reply text or parsed JSON if json_schema provided).
    """
    if _state.auth_latch:
        log.error("Auth latch tripped — refusing call to %s", purpose)
        raise RuntimeError("Auth latch tripped — cannot call LLM")

    status = check_spend_caps(purpose, is_sleep)
    if status != SpendStatus.OK:
        log.warning("Spend cap blocking call to %s: %s", purpose, status.value)
        return {"content": "", "spend_blocked": True}

    model = _model(model)
    kwargs = _request_kwargs(messages, model, max_tokens)
    if json_schema:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}

    start_time = time.monotonic()
    try:
        async with _semaphore(is_sleep):
            response = await _get_client().messages.create(**kwargs)
    except anthropic.AuthenticationError:
        trip_auth_latch()
        _state.auth_error_count += 1
        log.error("AuthenticationError — latch tripped")
        raise
    except anthropic.APIStatusError as e:
        log.error("HTTPError [%s] from LLM API", e.status_code)
        raise
    except Exception as e:
        # Never log connection error messages (may contain keys)
        log.error("LLM call failed for %s: %s", purpose, type(e).__name__)
        raise

    return _finish(response, model, purpose, json_schema, start_time, is_sleep)


def chat_completion_sync(
    messages: list[dict],
    model: str | None = None,
    *,
    max_tokens: int = 16000,
    json_schema: dict | None = None,
    purpose: str = "chat",
    is_sleep: bool = False,
) -> dict[str, Any]:
    """Blocking twin of chat_completion for synchronous callers (e.g. the session close hook)."""
    if _state.auth_latch:
        raise RuntimeError("Auth latch tripped — cannot call LLM")
    if check_spend_caps(purpose, is_sleep) != SpendStatus.OK:
        return {"content": "", "spend_blocked": True}

    model = _model(model)
    kwargs = _request_kwargs(messages, model, max_tokens)
    if json_schema:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}
    start_time = time.monotonic()
    try:
        response = _get_sync_client().messages.create(**kwargs)
    except anthropic.AuthenticationError:
        trip_auth_latch()
        raise
    except Exception as e:
        log.error("LLM call failed for %s: %s", purpose, type(e).__name__)
        raise
    return _finish(response, model, purpose, json_schema, start_time, is_sleep)


def _finish(response: Any, model: str, purpose: str, json_schema: dict | None,
            start_time: float, is_sleep: bool) -> dict[str, Any]:
    """Turn an API response into Sunny's result dict and record its cost."""
    if response.stop_reason == "refusal":
        log.warning("Claude declined the %s request", purpose)
    content_text = "".join(b.text for b in response.content if b.type == "text")
    result: dict[str, Any] = {
        "content": content_text,
        "prompt_tokens": response.usage.input_tokens,
        "completion_tokens": response.usage.output_tokens,
        "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        "stop_reason": response.stop_reason,
    }
    if json_schema and response.stop_reason != "refusal":
        try:
            result["content"] = json.loads(content_text)
        except json.JSONDecodeError:
            log.warning("JSON schema response failed to parse")

    _account(purpose, response.model or model, result, (time.monotonic() - start_time) * 1000, is_sleep)
    return result


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rate = next((v for k, v in PRICES_PER_MTOK.items() if model.startswith(k)), PRICES_PER_MTOK["claude-sonnet-"])
    return (prompt_tokens * rate[0] + completion_tokens * rate[1]) / 1_000_000


def _account(purpose: str, model: str, result: dict, latency_ms: float, is_sleep: bool = False) -> None:
    """Add a call's cost to the spend totals and append it to log/llm-usage.md."""
    cost = _cost(model, result.get("prompt_tokens", 0), result.get("completion_tokens", 0))
    _state.daily_spend += cost
    _state.monthly_spend += cost
    if is_sleep:
        _state.sleep_budget_used += cost
    _save_spend()

    usage = UsageEntry(
        purpose=purpose,
        model=model,
        prompt_tokens=result.get("prompt_tokens", 0),
        completion_tokens=result.get("completion_tokens", 0),
        total_tokens=result.get("total_tokens", 0),
        cost=cost,
        latency_ms=latency_ms,
    )
    try:
        log_path = Path(config.get_settings().vault_path) / "log" / "llm-usage.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{usage.timestamp}] purpose={usage.purpose} model={usage.model} "
                    f"in={usage.prompt_tokens} out={usage.completion_tokens} "
                    f"total={usage.total_tokens} cost=${usage.cost:.4f} "
                    f"latency={usage.latency_ms:.0f}ms\n")
    except OSError:
        log.warning("Failed to write LLM usage log")


async def streaming_chat(
    messages: list[dict],
    model: str | None = None,
    *,
    max_tokens: int = 64000,
    on_chunk: Any = None,  # callback(chunk: str) -> None
    purpose: str = "chat",
) -> AsyncIterator[str]:
    """Stream a chat completion, yielding text chunks as they arrive."""
    if _state.auth_latch:
        raise RuntimeError("Auth latch tripped")

    if check_spend_caps(purpose) != SpendStatus.OK:
        yield "[Sunny's daily or monthly Claude spend cap has been reached]"
        return

    model = _model(model)
    start_time = time.monotonic()
    try:
        async with _semaphore(False):
            async with _get_client().messages.stream(**_request_kwargs(messages, model, max_tokens)) as stream:
                async for text in stream.text_stream:
                    if on_chunk:
                        on_chunk(text)
                    yield text
                final = await stream.get_final_message()
    except anthropic.AuthenticationError:
        trip_auth_latch()
        raise

    if final.stop_reason == "refusal":
        yield "\n\n[Claude declined to answer this.]"
    _account(purpose, final.model or model, {
        "prompt_tokens": final.usage.input_tokens,
        "completion_tokens": final.usage.output_tokens,
        "total_tokens": final.usage.input_tokens + final.usage.output_tokens,
    }, (time.monotonic() - start_time) * 1000)
