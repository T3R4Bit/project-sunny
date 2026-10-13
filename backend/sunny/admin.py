"""Admin status — one read-only snapshot for the PWA's Admin page."""

from __future__ import annotations

from fastapi import APIRouter

from sunny import config
from sunny.llm import gateway

router = APIRouter(tags=["admin"])


@router.get("/admin/status")
def admin_status() -> dict:
    """Spend, agent, sync and integration health. Never returns secret values."""
    from sunny.agent.loop import get_agent_loop
    from sunny.watcher import get_sync_conflicts

    settings = config.get_settings()
    gateway.check_spend_caps()  # loads persisted spend and rolls the day/month over
    return {
        "spend": {
            "daily": round(gateway._state.daily_spend, 4),
            "daily_cap": settings.llm_spend_daily,
            "monthly": round(gateway._state.monthly_spend, 4),
            "monthly_cap": settings.llm_spend_monthly,
            "auth_latch": gateway._state.auth_latch,
        },
        "models": {"fast": settings.model_fast, "default": settings.model_default, "deep": settings.model_deep},
        "agent": get_agent_loop().get_status(),
        "sync_conflicts": get_sync_conflicts(),
        "integrations": {
            "claude": bool(settings.claude_api_key),
            "nextcloud": bool(settings.nextcloud_caldav_url and settings.nextcloud_user and settings.nextcloud_password),
            "garmin": bool(settings.garmin_username and settings.garmin_password),
            "push": bool(settings.push_vapid_public_key and settings.push_vapid_private_key),
        },
        "vault_path": str(settings.vault_path),
    }
