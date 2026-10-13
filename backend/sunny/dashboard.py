"""Dashboard — one snapshot of the homelab and of Sunny itself for the PWA's Dashboard page.

Host, Tailscale, service, container, Syncthing, Minecraft and backup data come from the JSON file
written by deploy/collector.py on the host (bind-mounted read-only), so this container never needs
the Docker socket, the Tailscale socket or systemd. Sunny's own state is read in-process.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

from sunny import config
from sunny.llm import gateway

router = APIRouter(tags=["dashboard"])

# A snapshot older than this many collector intervals is reported as stale.
STALE_INTERVALS = 4


def _host_snapshot(path: Path) -> dict:
    try:
        snap = json.loads(path.read_text())
    except FileNotFoundError:
        return {"available": False, "reason": "collector not running (no status file)"}
    except (OSError, ValueError) as e:
        return {"available": False, "reason": f"unreadable status file: {type(e).__name__}"}

    age = None
    try:
        collected = datetime.fromisoformat(snap["collected_at"])
        age = (datetime.now(timezone.utc) - collected).total_seconds()
    except (KeyError, ValueError):
        pass
    interval = snap.get("interval_s", 20)
    snap["available"] = True
    snap["age_s"] = round(age) if age is not None else None
    snap["stale"] = age is None or age > interval * STALE_INTERVALS
    return snap


def _vault_commits(vault: Path, n: int = 5) -> list[dict]:
    try:
        out = subprocess.run(
            ["git", "-C", str(vault), "log", f"-{n}", "--format=%h%x1f%cI%x1f%s"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        sha, when, subject = line.split("\x1f", 2)
        rows.append({"sha": sha, "time": when, "subject": subject})
    return rows


def _sunny_state() -> dict:
    from sunny.agent.loop import get_agent_loop
    from sunny.watcher import get_sync_conflicts

    settings = config.get_settings()
    gateway.check_spend_caps()  # loads persisted spend and rolls the day/month over
    agent = get_agent_loop().get_status()
    return {
        "healthy": True,
        "spend": {
            "daily": round(gateway._state.daily_spend, 4),
            "daily_cap": settings.llm_spend_daily,
            "monthly": round(gateway._state.monthly_spend, 4),
            "monthly_cap": settings.llm_spend_monthly,
            "auth_latch": gateway._state.auth_latch,
        },
        "models": {"fast": settings.model_fast, "default": settings.model_default, "deep": settings.model_deep},
        "agent": {"state": agent.get("state"), "running": agent.get("running"), "tasks": agent.get("task_count")},
        "sync_conflicts": len(get_sync_conflicts()),
        "recent_commits": _vault_commits(Path(settings.vault_path)),
    }


def _overall(snap: dict, sunny: dict) -> dict:
    """ok | warn | down plus a one-line reason list, from the signals that matter."""
    issues: list[str] = []
    down = False
    if not snap.get("available"):
        issues.append("Host collector offline")
    else:
        if snap.get("stale"):
            issues.append("Host status is stale")
        for svc in snap.get("services") or []:
            if isinstance(svc, dict) and svc.get("active") not in ("active", "activating"):
                issues.append(f"{svc.get('name')} is {svc.get('active')}")
                if svc.get("name") in ("docker", "tailscaled"):
                    down = True
        for c in snap.get("containers") or []:
            if isinstance(c, dict) and c.get("state") != "running":
                issues.append(f"container {c.get('name')} {c.get('state')}")
        host = snap.get("host") or {}
        if host.get("disk_total") and host["disk_used"] / host["disk_total"] > 0.9:
            issues.append("Disk over 90%")
        if host.get("mem_total") and host["mem_available"] / host["mem_total"] < 0.08:
            issues.append("Memory nearly exhausted")
        mc = snap.get("minecraft") or {}
        if mc and not mc.get("online"):
            issues.append("Minecraft not answering")
        for f in (snap.get("syncthing") or {}).get("folders", []) or []:
            if f.get("errors"):
                issues.append(f"Syncthing folder {f['id']} has errors")
    if sunny["spend"]["auth_latch"]:
        issues.append("Claude API key rejected")
        down = True
    if sunny["sync_conflicts"]:
        issues.append(f"{sunny['sync_conflicts']} sync conflict(s)")
    return {"level": "down" if down else ("warn" if issues else "ok"), "issues": issues}


@router.get("/dashboard")
def dashboard() -> dict:
    snap = _host_snapshot(Path(config.get_settings().host_status_file))
    sunny = _sunny_state()
    return {"overall": _overall(snap, sunny), "sunny": sunny, "host": snap}
