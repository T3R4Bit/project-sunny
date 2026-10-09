"""Sunny router — deterministic intent detection with confidence scoring.

Intents are matched in order. The top match must exceed the confidence
threshold (default 0.7) and be at least 0.15 above the runner-up.
Ambiguous intents trigger a clarifying question; no match falls through
to Claude.

Every decision is logged to log/routing.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.7
CONFIDENCE_MARGIN = 0.15

INTENTS_LOG_FILE = "log/routing.md"


class Intent(str, Enum):
    """Sunny's deterministic intents."""
    LIST_TASKS = "list_tasks"
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    DELETE_TASK = "delete_task"
    SLEEP_STATE = "sleep_state"
    CALENDAR_QUICK_ADD = "calendar_quick_add"
    RECIPE_LOOKUP = "recipe_lookup"
    RUN_AGENT = "run_agent"
    NEW_SESSION = "new_session"
    MOVE_SESSION = "move_session"
    SEARCH = "search"
    CREATE_RESEARCH = "create_research"
    CLOSE_SESSION = "close_session"


@dataclass
class Match:
    """A single intent match result."""
    intent: Intent
    confidence: float  # 0.0 to 1.0
    matched_text: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingResult:
    """The outcome of a routing decision."""
    intent: Intent | None
    confidence: float
    runner_up: Match | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    logged: bool = True

    @property
    def action(self) -> str:
        """What to do next."""
        if self.confidence >= DEFAULT_CONFIDENCE_THRESHOLD and (
            self.runner_up is None
            or self.confidence - self.runner_up.confidence >= CONFIDENCE_MARGIN
        ):
            return "execute"
        if self.intent:
            return "clarify"
        return "claude"


def _get_intent_patterns() -> list[tuple[Intent, list[str]]]:
    """Return list of (intent, trigger_phrases)."""
    return [
        (Intent.LIST_TASKS, ["list task", "show task", "my tasks", "what do i have", "task list", "tasks to do"]),
        (Intent.CREATE_TASK, ["add task", "create task", "new task", "remind me", "i need to", "i should", "todo"]),
        (Intent.UPDATE_TASK, ["update task", "complete task", "finish task", "done with", "mark complete", "done"]),
        (Intent.DELETE_TASK, ["delete task", "remove task", "dismiss task", "cancel task", "drop task"]),
        (Intent.SLEEP_STATE, ["going to bed", "going to sleep", "i'm going to sleep", "i'm sleeping", "can't sleep", "can't sleep", "wake up", "i'm awake", "back awake", "can't sleep", "insomnia"]),
        (Intent.CALENDAR_QUICK_ADD, ["add event", "create event", "schedule", "calendar event", "put on calendar", "block time"]),
        (Intent.RECIPE_LOOKUP, ["recipe", "cook", "what can i make", "ingredients", "dinner idea", "lunch idea"]),
        (Intent.RUN_AGENT, ["run agent", "start agent", "let agent work", "run the agent", "activate agent"]),
        (Intent.NEW_SESSION, ["new chat", "new session", "start a chat", "new project chat"]),
        (Intent.MOVE_SESSION, ["move session", "move to", "transfer session", "move chat"]),
        (Intent.SEARCH, ["search", "find", "look up", "search for", "where did i", "what did i say about"]),
        (Intent.CREATE_RESEARCH, ["start research", "new research", "research on", "research about", "deep dive"]),
        (Intent.CLOSE_SESSION, ["close session", "close chat", "end session", "done with this", "finish this chat"]),
    ]


def route(message: str, context: dict | None = None) -> RoutingResult:
    """Route a user message to the appropriate handler.

    Uses deterministic pattern matching. The top match must exceed the
    confidence threshold and beat the runner-up by the margin.

    Args:
        message: The user's message text.
        context: Optional context dict with project_slug, session info, etc.

    Returns:
        RoutingResult with intent, confidence, and action.
    """
    if not message or not message.strip():
        return RoutingResult(intent=None, confidence=0.0)

    lower_msg = message.lower().strip()
    patterns = _get_intent_patterns()
    matches: list[Match] = []

    for intent, triggers in patterns:
        for trigger in triggers:
            if trigger in lower_msg:
                confidence = _calc_confidence(lower_msg, trigger)
                params = _extract_params(intent, lower_msg, context or {})
                matches.append(Match(
                    intent=intent,
                    confidence=confidence,
                    matched_text=trigger,
                    parameters=params,
                ))
                break  # one trigger match per intent is enough

    if not matches:
        return RoutingResult(intent=None, confidence=0.0)

    matches.sort(key=lambda m: m.confidence, reverse=True)
    top = matches[0]
    runner_up = matches[1] if len(matches) > 1 else None

    result = RoutingResult(
        intent=top.intent,
        confidence=top.confidence,
        runner_up=runner_up,
        parameters=top.parameters,
    )

    # Log the routing decision
    _log_routing(result)

    return result


def _calc_confidence(message: str, trigger: str) -> float:
    """Calculate match confidence based on various signals."""
    base = 0.85  # exact phrase match

    # Boost if trigger is at the start of the message
    if message.startswith(trigger):
        base = min(1.0, base + 0.1)

    # Boost if the message is short and equals the trigger
    if message == trigger:
        base = 1.0

    return base


def _extract_params(intent: Intent, message: str, context: dict) -> dict:
    """Extract structured parameters from the message for the matched intent."""
    params: dict[str, Any] = {}

    # Common params
    params["_raw_message"] = message
    if "project_slug" in context:
        params["project_slug"] = context["project_slug"]
    if "session_id" in context:
        params["session_id"] = context["session_id"]

    if intent == Intent.SLEEP_STATE:
        if "can't sleep" in message or "insomnia" in message:
            params["state"] = "cant_sleep"
        elif "awake" in message or "wake up" in message or "back awake" in message:
            params["state"] = "awake"
        else:
            params["state"] = "sleeping"

    if intent == Intent.CALENDAR_QUICK_ADD:
        # Simple extraction: try to find time pattern
        import re
        time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:am|pm)?)', message, re.IGNORECASE)
        if time_match:
            params["time"] = time_match.group(1)

    return params


def _log_routing(result: RoutingResult) -> None:
    """Log the routing decision to log/routing.md."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    intent_str = result.intent.value if result.intent else "none"
    action = result.action
    confidence = round(result.confidence, 3)

    runner_str = ""
    if result.runner_up:
        runner_str = f"\n  runner_up: {result.runner_up.intent.value} ({round(result.runner_up.confidence, 3)})"

    line = f"[{timestamp}] input=\"{_last_message or ''[:100]}\" intent={intent_str} confidence={confidence} action={action}{runner_str}\n"

    try:
        log_path = Path("vault") / INTENTS_LOG_FILE
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        log.warning("Failed to write routing log: %s", line.strip())


# Keep reference to last message for logging
_last_message: str = ""


def route_with_log(message: str, context: dict | None = None) -> RoutingResult:
    """Route a message and update the logged message text."""
    global _last_message
    _last_message = message
    return route(message, context)
