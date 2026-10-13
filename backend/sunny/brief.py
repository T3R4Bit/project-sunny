"""Daily brief — weather, calendar, email, Garmin, projects and recent chats, written up by Claude.

Generated once each morning at ``BRIEF_TIME`` (local ``TIMEZONE``) by a background task, and on
demand from the Dashboard. Each run stores the structured sections plus Claude's write-up in
``<state dir>/briefs/<date>.json`` and a readable copy in the vault at ``briefs/<date>.md``.
Every source is optional: one that is unconfigured or failing becomes a note, never an error.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter

from sunny import config, integrations as ig

log = logging.getLogger(__name__)
router = APIRouter(tags=["brief"])

BRIEF_PROMPT = """You are Sunny, Keaton's personal assistant, writing his morning brief.
Using only the data below, write a short, warm brief in plain prose (no headings, no bullet lists,
at most 130 words). Lead with what matters most today: events with times, weather that affects plans
(rain, heat, cold), and anything urgent in email. Mention sleep only if notable. Do not invent
anything that is not in the data, and skip sections that have no data rather than apologising.
Sources listed under "unavailable" were not checked: never say or imply they are empty (do not say
"no events" or "no emails" when calendar or email is unavailable)."""


def _briefs_dir() -> Path:
    return Path(config.get_settings().db_path).parent / "briefs"


def _section(fn: Callable[[], Any], configured: bool, unconfigured_note: str) -> dict:
    if not configured:
        return {"status": "unconfigured", "note": unconfigured_note}
    try:
        return {"status": "ok", "data": fn()}
    except Exception as e:  # noqa: BLE001 — one failing source must not sink the brief
        log.warning("Brief source failed: %s", type(e).__name__)
        return {"status": "error", "note": f"{type(e).__name__}: {str(e)[:160]}"}


def _projects_and_chats() -> dict:
    from sunny.projects import service as svc

    since = datetime.now(ig.tz()) - timedelta(days=1)
    recent = []
    for s in svc.list_sessions(None):
        try:
            started = datetime.fromisoformat(str(s.started))
        except ValueError:
            continue
        if started.tzinfo is None:
            started = started.replace(tzinfo=ig.tz())
        if started >= since:
            recent.append({"title": s.title, "summary": s.summary})
    projects = [p.title for p in svc.list_projects() if p.status == "active"]
    return {"active_projects": projects, "recent_chats": recent[:8]}


def gather() -> dict:
    today = datetime.now(ig.tz()).date()
    weather = _section(
        lambda: [ig.weather_for(loc) for loc in ig.weather_locations()],
        ig.weather_configured(), "Weather not set up (OPENWEATHERMAP_API_KEY)",
    )
    calendar = _section(
        lambda: ig.calendar_events(today),
        ig.google_configured() and ig.google_connected(), "Google not connected",
    )
    email = _section(ig.gmail_summary, ig.google_configured() and ig.google_connected(), "Google not connected")
    health = _section(ig.garmin_summary, ig.garmin_configured(), "Garmin not set up")
    vault = _section(_projects_and_chats, True, "")
    return {"weather": weather, "calendar": calendar, "email": email, "health": health, "vault": vault}


def _write_up(date_label: str, sections: dict) -> str:
    from sunny.llm.gateway import chat_completion_sync

    data = {k: v.get("data") for k, v in sections.items() if v.get("status") == "ok"}
    data["unavailable"] = [k for k, v in sections.items() if v.get("status") != "ok"]
    result = chat_completion_sync(
        [
            {"role": "system", "content": BRIEF_PROMPT},
            {"role": "user", "content": f"Today is {date_label}.\n\nData:\n{json.dumps(data, default=str, indent=1)}"},
        ],
        model=config.get_settings().model_fast,
        max_tokens=1200,
        purpose="daily_brief",
    )
    if result.get("spend_blocked"):
        return "Claude spend cap reached, so today's write-up was skipped. The details are below."
    return str(result.get("content", "")).strip()


def _to_markdown(brief: dict) -> str:
    lines = [f"# Daily brief: {brief['date_label']}", "", brief["summary"], ""]
    s = brief["sections"]
    if s["weather"].get("status") == "ok":
        lines.append("## Weather")
        for w in s["weather"]["data"]:
            lines.append(f"- {w['location']}: {w['now_f']}°F now, high {w['high_f']}° / low {w['low_f']}°, "
                         f"{w['condition']}, {w['rain_chance']}% rain")
        lines.append("")
    if s["calendar"].get("status") == "ok":
        lines.append("## Calendar")
        for e in s["calendar"]["data"] or []:
            when = "all day" if e["all_day"] else datetime.fromisoformat(e["start"]).strftime("%-I:%M %p")
            lines.append(f"- {when}: {e['title']}")
        if not s["calendar"]["data"]:
            lines.append("- Nothing scheduled")
        lines.append("")
    if s["email"].get("status") == "ok":
        lines.append(f"## Email ({s['email']['data']['unread']} unread)")
        for m in s["email"]["data"]["important"]:
            lines.append(f"- {m['from']}: {m['subject']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def generate(save: bool = True) -> dict:
    now = datetime.now(ig.tz())
    sections = gather()
    date_label = now.strftime("%A, %B %-d")
    try:
        summary = _write_up(date_label, sections)
    except Exception as e:  # noqa: BLE001
        log.error("Brief write-up failed: %s", type(e).__name__)
        summary = "Sunny couldn't write today's summary (Claude request failed). The details are below."
    brief = {
        "date": now.date().isoformat(),
        "date_label": date_label,
        "generated_at": now.isoformat(),
        "summary": summary,
        "sections": sections,
    }
    if save:
        _save(brief)
    return brief


def _save(brief: dict) -> None:
    d = _briefs_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{brief['date']}.json").write_text(json.dumps(brief, default=str))
    try:
        from sunny.vault.git_ops import commit as git_commit
        from sunny.vault.io import atomic_write

        vault = config.vault_root()
        path = vault / "briefs" / f"{brief['date']}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, _to_markdown(brief))
        git_commit(vault, f"brief: {brief['date']}", files=[f"briefs/{brief['date']}.md"])
    except Exception as e:  # noqa: BLE001 — the JSON copy is what the UI reads
        log.warning("Could not write brief to vault: %s", type(e).__name__)


def load(day: Optional[str] = None) -> Optional[dict]:
    day = day or datetime.now(ig.tz()).date().isoformat()
    try:
        return json.loads((_briefs_dir() / f"{day}.json").read_text())
    except (OSError, ValueError):
        return None


@router.get("/brief")
def get_brief() -> dict:
    """Today's brief, or the most recent one with `stale: true` if today's isn't generated yet."""
    brief = load()
    if brief:
        return {**brief, "stale": False}
    files = sorted(_briefs_dir().glob("*.json")) if _briefs_dir().exists() else []
    if files:
        return {**json.loads(files[-1].read_text()), "stale": True}
    return {"summary": None, "stale": True}


@router.post("/brief/refresh")
async def refresh_brief() -> dict:
    return {**await asyncio.to_thread(generate), "stale": False}


# --- scheduler ------------------------------------------------------------------------------

_task: Optional[asyncio.Task] = None


def _next_run(now: datetime) -> datetime:
    hh, mm = (int(x) for x in config.get_settings().brief_time.split(":"))
    run = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return run if run > now else run + timedelta(days=1)


async def _loop() -> None:
    # Catch up on start if the morning run was missed (e.g. a restart at 06:59)
    now = datetime.now(ig.tz())
    hh, mm = (int(x) for x in config.get_settings().brief_time.split(":"))
    if load() is None and now >= now.replace(hour=hh, minute=mm, second=0, microsecond=0):
        try:
            await asyncio.to_thread(generate)
        except Exception:
            log.exception("Catch-up brief failed")
    while True:
        now = datetime.now(ig.tz())
        await asyncio.sleep((_next_run(now) - now).total_seconds())
        try:
            await asyncio.to_thread(generate)
            log.info("Daily brief generated")
        except Exception:
            log.exception("Daily brief failed")


def start_scheduler() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop_scheduler() -> None:
    global _task
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
