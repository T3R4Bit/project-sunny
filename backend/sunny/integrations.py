"""External integrations used by the daily brief: weather, Google (Calendar + Gmail), Garmin.

Each integration exposes:
- ``configured()``: are the settings present?
- ``check()``: a live probe returning {"ok": bool, "detail": str} for the Settings page
- data fetchers used by sunny.brief

Tokens (Google refresh token, Garmin session) live in ``settings.secret_dir`` with mode 600, which
is the persistent ``sunny-state`` volume and is never synced or committed.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from sunny import config

log = logging.getLogger(__name__)
router = APIRouter(tags=["integrations"])

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def tz() -> ZoneInfo:
    return ZoneInfo(config.get_settings().timezone)


def _secret_path(name: str) -> Path:
    return Path(config.get_settings().secret_dir) / name


def _write_secret(name: str, data: dict) -> None:
    path = _secret_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    path.chmod(0o600)


def _read_secret(name: str) -> Optional[dict]:
    try:
        return json.loads(_secret_path(name).read_text())
    except (OSError, ValueError):
        return None


# --- Weather (OpenWeatherMap) -------------------------------------------------------------

OWM = "https://api.openweathermap.org/data/2.5"


def weather_locations() -> list[str]:
    raw = config.get_settings().weather_locations
    return [loc.strip() for loc in raw.split(";") if loc.strip()]


def weather_configured() -> bool:
    s = config.get_settings()
    return bool(s.openweathermap_api_key and weather_locations())


def weather_for(location: str) -> dict:
    """Current conditions plus today's high/low and max rain chance (local day)."""
    s = config.get_settings()
    params = {"q": location, "appid": s.openweathermap_api_key, "units": "imperial"}
    with httpx.Client(timeout=TIMEOUT) as c:
        cur = c.get(f"{OWM}/weather", params=params)
        cur.raise_for_status()
        fc = c.get(f"{OWM}/forecast", params=params)
        fc.raise_for_status()
    cur, fc = cur.json(), fc.json()

    today = datetime.now(tz()).date()
    temps, pops, conditions = [cur["main"]["temp"]], [], []
    for item in fc.get("list", []):
        when = datetime.fromtimestamp(item["dt"], tz())
        if when.date() != today:
            continue
        temps += [item["main"]["temp_max"], item["main"]["temp_min"]]
        pops.append(item.get("pop", 0))
        conditions.append(item["weather"][0]["description"])
    return {
        "location": cur.get("name") or location,
        "now_f": round(cur["main"]["temp"]),
        "feels_f": round(cur["main"]["feels_like"]),
        "condition": cur["weather"][0]["description"],
        "high_f": round(max(temps)),
        "low_f": round(min(temps)),
        "rain_chance": round(max(pops) * 100) if pops else 0,
        "later": max(set(conditions), key=conditions.count) if conditions else None,
        "wind_mph": round(cur.get("wind", {}).get("speed", 0)),
    }


def weather_check() -> dict:
    if not weather_configured():
        return {"ok": False, "detail": "OPENWEATHERMAP_API_KEY or WEATHER_LOCATIONS not set"}
    w = weather_for(weather_locations()[0])
    return {"ok": True, "detail": f"{w['location']}: {w['now_f']}°F, {w['condition']}"}


# --- Google (OAuth + Calendar + Gmail) ----------------------------------------------------

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]
GOOGLE_TOKEN_FILE = "google_token.json"
_oauth_states: dict[str, float] = {}  # state -> expiry


def google_configured() -> bool:
    s = config.get_settings()
    return bool(s.google_client_id and s.google_client_secret and s.google_redirect_uri)


def google_connected() -> bool:
    tok = _read_secret(GOOGLE_TOKEN_FILE)
    return bool(tok and tok.get("refresh_token"))


def _google_access_token() -> str:
    """A valid access token, refreshing (and persisting) it when it is about to expire."""
    tok = _read_secret(GOOGLE_TOKEN_FILE)
    if not tok or not tok.get("refresh_token"):
        raise RuntimeError("Google is not connected")
    if tok.get("access_token") and tok.get("expires_at", 0) > time.time() + 60:
        return tok["access_token"]
    s = config.get_settings()
    r = httpx.post("https://oauth2.googleapis.com/token", timeout=TIMEOUT, data={
        "client_id": s.google_client_id,
        "client_secret": s.google_client_secret,
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    })
    if r.status_code == 400 and "invalid_grant" in r.text:
        raise RuntimeError("Google sign-in expired or was revoked; reconnect Google in Settings")
    r.raise_for_status()
    data = r.json()
    tok.update(access_token=data["access_token"], expires_at=time.time() + data.get("expires_in", 3600))
    _write_secret(GOOGLE_TOKEN_FILE, tok)
    return tok["access_token"]


def _google_get(url: str, **params: Any) -> dict:
    r = httpx.get(url, params=params, timeout=TIMEOUT,
                  headers={"Authorization": f"Bearer {_google_access_token()}"})
    r.raise_for_status()
    return r.json()


def calendar_events(day: date) -> list[dict]:
    """All events on `day` (local time) across the calendars selected in Google Calendar."""
    start = datetime.combine(day, datetime.min.time(), tz())
    end = start + timedelta(days=1)
    cals = _google_get("https://www.googleapis.com/calendar/v3/users/me/calendarList", minAccessRole="reader")
    events = []
    for cal in cals.get("items", []):
        if not cal.get("selected") and not cal.get("primary"):
            continue
        data = _google_get(
            f"https://www.googleapis.com/calendar/v3/calendars/{cal['id']}/events",
            timeMin=start.isoformat(), timeMax=end.isoformat(), singleEvents="true", orderBy="startTime",
        )
        for e in data.get("items", []):
            if e.get("status") == "cancelled":
                continue
            s, en = e.get("start", {}), e.get("end", {})
            all_day = "date" in s
            events.append({
                "title": e.get("summary", "(no title)"),
                "start": s.get("dateTime") or s.get("date"),
                "end": en.get("dateTime") or en.get("date"),
                "all_day": all_day,
                "location": e.get("location", ""),
                "calendar": cal.get("summaryOverride") or cal.get("summary", ""),
            })
    events.sort(key=lambda e: (not e["all_day"], e["start"] or ""))
    return events


def gmail_summary(limit: int = 6) -> dict:
    """Unread inbox count plus the newest important unread messages (sender + subject only)."""
    base = "https://gmail.googleapis.com/gmail/v1/users/me"
    unread = _google_get(f"{base}/labels/INBOX").get("messagesUnread", 0)
    listing = _google_get(f"{base}/messages", q="is:unread is:important in:inbox newer_than:2d", maxResults=limit)
    msgs = []
    for m in listing.get("messages", []):
        meta = _google_get(f"{base}/messages/{m['id']}", format="metadata", metadataHeaders=["From", "Subject"])
        headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
        sender = headers.get("From", "").split("<")[0].strip().strip('"')
        msgs.append({"from": sender, "subject": headers.get("Subject", "(no subject)")})
    return {"unread": unread, "important": msgs}


def google_check() -> dict:
    if not google_configured():
        return {"ok": False, "detail": "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set"}
    if not google_connected():
        return {"ok": False, "detail": "Not connected yet: use Connect Google", "action": "connect"}
    who = _google_get("https://openidconnect.googleapis.com/v1/userinfo").get("email", "")
    n = len(calendar_events(datetime.now(tz()).date()))
    unread = gmail_summary(limit=0)["unread"]
    return {"ok": True, "detail": f"{who}: {n} events today, {unread} unread in inbox"}


@router.post("/integrations/google/start")
def google_start() -> dict:
    """Begin the OAuth flow (session-gated). Returns the Google consent URL."""
    if not google_configured():
        raise HTTPException(400, "Google client id/secret not configured")
    now = time.time()
    for k in [k for k, exp in _oauth_states.items() if exp < now]:
        del _oauth_states[k]
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = now + 600
    s = config.get_settings()
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": s.google_client_id,
        "redirect_uri": s.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    })
    return {"url": url}


@router.get("/auth/google/callback", include_in_schema=False)
def google_callback(state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    """OAuth redirect target. Public (Google's redirect drops the SameSite=Strict cookie), so it
    only accepts a `state` that a logged-in session obtained from /integrations/google/start."""
    s = config.get_settings()
    back = s.public_url.rstrip("/") + "/?google="
    if _oauth_states.pop(state, 0) < time.time():
        return RedirectResponse(back + "bad_state")
    if error or not code:
        return RedirectResponse(back + (error or "cancelled"))
    r = httpx.post("https://oauth2.googleapis.com/token", timeout=TIMEOUT, data={
        "code": code,
        "client_id": s.google_client_id,
        "client_secret": s.google_client_secret,
        "redirect_uri": s.google_redirect_uri,
        "grant_type": "authorization_code",
    })
    if r.status_code != 200:
        log.error("Google token exchange failed: %s", r.status_code)
        return RedirectResponse(back + "exchange_failed")
    data = r.json()
    old = _read_secret(GOOGLE_TOKEN_FILE) or {}
    _write_secret(GOOGLE_TOKEN_FILE, {
        "refresh_token": data.get("refresh_token") or old.get("refresh_token"),
        "access_token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 3600),
        "scope": data.get("scope", ""),
    })
    log.info("Google connected")
    return RedirectResponse(back + "connected")


@router.post("/integrations/google/disconnect")
def google_disconnect() -> dict:
    tok = _read_secret(GOOGLE_TOKEN_FILE)
    if tok and tok.get("refresh_token"):
        try:
            httpx.post("https://oauth2.googleapis.com/revoke", data={"token": tok["refresh_token"]}, timeout=TIMEOUT)
        except httpx.HTTPError:
            pass
    _secret_path(GOOGLE_TOKEN_FILE).unlink(missing_ok=True)
    return {"status": "disconnected"}


# --- Garmin -------------------------------------------------------------------------------

GARMIN_TOKEN_DIR = "garmin_tokens"


def garmin_configured() -> bool:
    s = config.get_settings()
    return bool(s.garmin_username and s.garmin_password)


def _garmin_client():
    """Logged-in garminconnect client; reuses saved session tokens so we rarely do a full login."""
    from garminconnect import Garmin

    s = config.get_settings()
    token_dir = _secret_path(GARMIN_TOKEN_DIR)
    client = Garmin(s.garmin_username, s.garmin_password)
    try:
        client.login(str(token_dir))
    except Exception:  # noqa: BLE001 — no/expired tokens: fall back to a credential login
        client = Garmin(s.garmin_username, s.garmin_password)
        client.login()
        token_dir.mkdir(parents=True, exist_ok=True)
        token_dir.chmod(0o700)
        client.garth.dump(str(token_dir))
    return client


def garmin_summary(day: Optional[date] = None) -> dict:
    """Last night's sleep plus yesterday's steps and resting heart rate."""
    today = day or datetime.now(tz()).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    g = _garmin_client()
    out: dict[str, Any] = {}
    try:
        sleep = (g.get_sleep_data(today.isoformat()) or {}).get("dailySleepDTO") or {}
        secs = sleep.get("sleepTimeSeconds")
        out["sleep_hours"] = round(secs / 3600, 1) if secs else None
        out["sleep_score"] = ((sleep.get("sleepScores") or {}).get("overall") or {}).get("value")
    except Exception as e:  # noqa: BLE001
        log.warning("Garmin sleep fetch failed: %s", type(e).__name__)
    try:
        stats = g.get_stats(yesterday) or {}
        out["steps_yesterday"] = stats.get("totalSteps")
        out["resting_hr"] = stats.get("restingHeartRate")
        out["body_battery"] = stats.get("bodyBatteryMostRecentValue")
    except Exception as e:  # noqa: BLE001
        log.warning("Garmin stats fetch failed: %s", type(e).__name__)
    return out


def garmin_check() -> dict:
    if not garmin_configured():
        return {"ok": False, "detail": "GARMIN_USERNAME / GARMIN_PASSWORD not set"}
    data = garmin_summary()
    parts = []
    if data.get("sleep_hours") is not None:
        parts.append(f"slept {data['sleep_hours']}h")
    if data.get("steps_yesterday") is not None:
        parts.append(f"{data['steps_yesterday']:,} steps yesterday")
    return {"ok": True, "detail": "Logged in" + (": " + ", ".join(parts) if parts else " (no data for today yet)")}


# --- Claude ---------------------------------------------------------------------------------


def claude_check() -> dict:
    from sunny.llm import gateway

    s = config.get_settings()
    if not s.claude_api_key:
        return {"ok": False, "detail": "CLAUDE_API_KEY not set"}
    if gateway._state.auth_latch:
        return {"ok": False, "detail": "Key was rejected earlier; fix it and restart Sunny"}
    r = httpx.get(f"https://api.anthropic.com/v1/models/{s.model_default}", timeout=TIMEOUT,
                  headers={"x-api-key": s.claude_api_key, "anthropic-version": "2023-06-01"})
    if r.status_code == 401:
        return {"ok": False, "detail": "API key rejected (401)"}
    r.raise_for_status()
    return {"ok": True, "detail": f"Key valid; {r.json().get('display_name', s.model_default)} available"}


# --- registry + routes ----------------------------------------------------------------------

INTEGRATIONS = {
    "claude": {"label": "Claude", "configured": lambda: bool(config.get_settings().claude_api_key), "check": claude_check},
    "weather": {"label": "Weather", "configured": weather_configured, "check": weather_check},
    "google": {"label": "Google Calendar & Gmail", "configured": google_configured, "check": google_check},
    "garmin": {"label": "Garmin", "configured": garmin_configured, "check": garmin_check},
}


@router.get("/integrations")
def list_integrations() -> list[dict]:
    out = []
    for key, i in INTEGRATIONS.items():
        row = {"key": key, "label": i["label"], "configured": i["configured"]()}
        if key == "google":
            row["connected"] = google_connected()
        if key == "weather":
            row["locations"] = weather_locations()
        out.append(row)
    return out


@router.post("/integrations/{key}/check")
def check_integration(key: str) -> dict:
    if key not in INTEGRATIONS:
        raise HTTPException(404, "Unknown integration")
    try:
        return INTEGRATIONS[key]["check"]()
    except httpx.HTTPStatusError as e:
        return {"ok": False, "detail": f"HTTP {e.response.status_code} from {e.request.url.host}"}
    except Exception as e:  # noqa: BLE001 — report, never 500, so the page can show it
        return {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:200]}"}
