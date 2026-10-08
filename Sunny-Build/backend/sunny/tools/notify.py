"""Notify registry — proactivity tiers for agent actions."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

log = logging.getLogger(__name__)


class NotifyTier(str, Enum):
    SILENT = "SILENT"      # Execute, log
    QUIET = "QUIET"         # Log + mention in next briefing
    SUGGEST = "SUGGEST"     # Propose, wait for approval
    ALERT = "ALERT"         # Push notification


class NotifyRegistry:
    """Registry of notification handlers by tier."""

    def __init__(self) -> None:
        self._handlers: dict[str, list] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default handlers for each tier."""
        self._handlers[NotifyTier.SILENT.value] = [self._log_handler]
        self._handlers[NotifyTier.QUIET.value] = [self._log_handler, self._briefing_handler]
        self._handlers[NotifyTier.SUGGEST.value] = [self._log_handler, self._suggest_handler]
        self._handlers[NotifyTier.ALERT.value] = [self._log_handler, self._alert_handler]

    def register(self, tier: NotifyTier, handler) -> None:
        """Register a handler for a specific tier."""
        if tier.value not in self._handlers:
            self._handlers[tier.value] = []
        self._handlers[tier.value].append(handler)

    async def notify(self, message: str, tier: NotifyTier = NotifyTier.SILENT,
                     context: Optional[dict] = None) -> None:
        """Send notification through all registered handlers for the tier."""
        handlers = self._handlers.get(tier.value, [])
        for handler in handlers:
            try:
                if callable(handler):
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message, context=context)
                    else:
                        handler(message, context=context)
            except Exception as e:
                log.error("Notify handler error: %s", e)

    def _log_handler(self, message: str, context: Optional[dict] = None) -> None:
        """Default handler: log to file."""
        log.info("[%s] %s", "agent", message)

    def _briefing_handler(self, message: str, context: Optional[dict] = None) -> None:
        """Default handler: queue for next briefing."""
        # In production, this would queue a briefing item
        log.info("[agent] Briefing item: %s", message)

    def _suggest_handler(self, message: str, context: Optional[dict] = None) -> None:
        """Default handler: propose for user approval."""
        log.info("[agent] Suggest: %s — awaiting approval", message)
        # In production, this would create a suggestion in the UI

    def _alert_handler(self, message: str, context: Optional[dict] = None) -> None:
        """Default handler: push notification."""
        log.warning("[agent] ALERT: %s", message)
        # In production, this would send a push notification via Web Push API


# Global notify function
def notify(message: str, tier: NotifyTier = NotifyTier.SILENT,
           context: Optional[dict] = None) -> None:
    """Convenience function to send a notification."""
    registry = get_notify_registry()
    # Synchronous version for non-async contexts
    import logging
    log = logging.getLogger("sunny.tools.notify")
    handlers = registry._handlers.get(tier.value, [])
    for handler in handlers:
        try:
            if callable(handler):
                handler(message, context=context)
        except Exception as e:
            log.error("Notify handler error: %s", e)


# Singleton registry
_notify_registry: Optional[NotifyRegistry] = None


def get_notify_registry() -> NotifyRegistry:
    """Get the global notify registry."""
    global _notify_registry
    if _notify_registry is None:
        _notify_registry = NotifyRegistry()
    return _notify_registry
