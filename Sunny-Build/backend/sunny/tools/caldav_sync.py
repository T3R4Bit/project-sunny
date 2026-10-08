"""P9 — CalDAV calendar sync for Sunny.

Reads/writes events via CalDAV (supports Google Calendar, Nextcloud, etc.)
and stores events locally in the vault for offline access.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """A calendar event."""
    uid: str
    summary: str
    description: str = ""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    location: str = ""
    organizer: str = ""
    attendees: list[str] = field(default_factory=list)
    status: str = "confirmed"
    caldav_url: str = ""
    all_day: bool = False

    def to_vault_line(self) -> str:
        """Render as a vault-friendly line for logging."""
        parts = [f"event:{self.uid}", f"summary:{self.summary}"]
        if self.start:
            parts.append(f"start:{self.start.isoformat()}")
        if self.end:
            parts.append(f"end:{self.end.isoformat()}")
        if self.location:
            parts.append(f"location:{self.location}")
        return " | ".join(parts)


class CalDAVSync:
    """Syncs calendar events via CalDAV protocol."""

    def __init__(
        self,
        vault: Path,
        caldav_url: str = "",
        username: str = "",
        password: str = "",
        calendar_name: str = "",
    ) -> None:
        self.vault = vault
        self.caldav_url = caldav_url
        self.username = username
        self.password = password
        self.calendar_name = calendar_name
        self._cache_path = vault / "data" / "caldav_cache.json"

    def is_configured(self) -> bool:
        """Check if CalDAV is configured."""
        return bool(self.caldav_url and self.username and self.password)

    def fetch_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[CalendarEvent]:
        """Fetch events from the CalDAV calendar.

        Returns cached events if direct connection fails (e.g., offline).
        """
        if not self.is_configured():
            log.warning("CalDAV not configured, returning cached events")
            return self._load_cache()

        try:
            return self._fetch_from_caldav(start_date, end_date)
        except Exception as e:
            log.warning("CalDAV fetch failed, using cache: %s", e)
            return self._load_cache()

    def _fetch_from_caldav(self, start_date: Optional[datetime],
                           end_date: Optional[datetime]) -> list[CalendarEvent]:
        """Fetch events from CalDAV server."""
        try:
            import caldav
        except ImportError:
            log.warning("caldav package not installed")
            return self._load_cache()

        client = caldav.DAVClient(self.caldav_url)
        principal = client.principal()
        calendars = principal.calendars()

        events: list[CalendarEvent] = []
        for calendar in calendars:
            if self.calendar_name and self.calendar_name not in calendar.name:
                continue

            if start_date and end_date:
                results = calendar.date_search(start_date, end_date, expand=True)
            else:
                results = calendar.date_search(
                    datetime.now() - __import__("datetime").timedelta(days=7),
                    datetime.now() + __import__("datetime").timedelta(days=30),
                    expand=True,
                )

            for event_obj in results:
                event = event_obj.event
                if not event:
                    continue
                ical = event.data
                cal_event = self._parse_ical(ical, calendar.name)
                if cal_event:
                    events.append(cal_event)

        self._save_cache(events)
        return events

    def _parse_ical(self, data: str, calendar_name: str) -> Optional[CalendarEvent]:
        """Parse an iCalendar string into a CalendarEvent."""
        try:
            from icalendar import Calendar as IcalCalendar
        except ImportError:
            return None

        cal = IcalCalendar.from_ical(data)
        for component in cal.walk():
            if component.name == "VEVENT":
                uid = str(component.get("UID", ""))
                summary = str(component.get("SUMMARY", ""))
                desc = str(component.get("DESCRIPTION", ""))
                location = str(component.get("LOCATION", ""))

                dt_start = component.get("DTSTART")
                dt_end = component.get("DTEND")
                start = dt_start.dt if dt_start else None
                end = dt_end.dt if dt_end else None

                if isinstance(start, datetime):
                    start = start.replace(tzinfo=timezone.utc)
                if isinstance(end, datetime):
                    end = end.replace(tzinfo=timezone.utc)

                organizer = str(component.get("ORGANIZER", ""))
                attendees = []
                for att in component.get("ATTENDEE", []):
                    if isinstance(att, list):
                        attendees.extend([str(a) for a in att])
                    else:
                        attendees.append(str(att))

                return CalendarEvent(
                    uid=uid,
                    summary=summary,
                    description=desc,
                    start=start,
                    end=end,
                    location=location,
                    organizer=organizer,
                    attendees=attendees,
                    caldav_url=f"cal:{calendar_name}/{uid}",
                    all_day=hasattr(dt_start.dt, "hour") if dt_start else False,
                )
        return None

    def add_event(
        self,
        summary: str,
        start: datetime,
        end: Optional[datetime] = None,
        description: str = "",
        location: str = "",
    ) -> Optional[str]:
        """Add an event to the CalDAV calendar. Returns event UID or None."""
        if not self.is_configured():
            log.warning("CalDAV not configured, event not synced")
            return None

        try:
            import caldav
            from icalendar import Event as IcalEvent
        except ImportError:
            return None

        try:
            client = caldav.DAVClient(self.caldav_url)
            principal = client.principal()
            calendar = None
            for cal in principal.calendars():
                if self.calendar_name and self.calendar_name in cal.name:
                    calendar = cal
                    break

            if not calendar:
                calendars = principal.calendars()
                if calendars:
                    calendar = calendars[0]
                else:
                    return None

            ical_event = IcalEvent()
            ical_event.add("summary", summary)
            ical_event.add("description", description)
            ical_event.add("location", location)
            ical_event.add("dtstart", start)
            if end:
                ical_event.add("dtend", end)
            ical_event.add("uid", f"sunny-{summary[:20].replace(' ', '-')}-{datetime.now().isoformat()}")

            event = calendar.add_event(ical_event.to_ical())
            log.info("Added event '%s' to CalDAV calendar", summary)
            return str(event.event.uid)
        except Exception as e:
            log.error("Failed to add event to CalDAV: %s", e)
            return None

    def find_conflicts(
        self,
        start: datetime,
        end: datetime,
        existing_events: Optional[list[CalendarEvent]] = None,
    ) -> list[CalendarEvent]:
        """Find calendar conflicts for a given time range."""
        if existing_events is None:
            existing_events = self.fetch_events()

        conflicts = []
        for event in existing_events:
            if event.start and event.end:
                if not (end <= event.start or start >= event.end):
                    conflicts.append(event)
        return conflicts

    def _load_cache(self) -> list[CalendarEvent]:
        """Load cached events from vault."""
        if not self._cache_path.exists():
            return []
        try:
            import json
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            events = []
            for item in data:
                start = datetime.fromisoformat(item["start"]) if item.get("start") else None
                end = datetime.fromisoformat(item["end"]) if item.get("end") else None
                events.append(CalendarEvent(
                    uid=item["uid"],
                    summary=item["summary"],
                    description=item.get("description", ""),
                    start=start,
                    end=end,
                    location=item.get("location", ""),
                ))
            return events
        except Exception as e:
            log.error("Failed to load CalDAV cache: %s", e)
            return []

    def _save_cache(self, events: list[CalendarEvent]) -> None:
        """Save events to cache."""
        data_dir = self._cache_path.parent
        data_dir.mkdir(parents=True, exist_ok=True)

        import json
        data = []
        for event in events:
            data.append({
                "uid": event.uid,
                "summary": event.summary,
                "description": event.description,
                "start": event.start.isoformat() if event.start else None,
                "end": event.end.isoformat() if event.end else None,
                "location": event.location,
            })
        self._cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def find_free_slots(
        self,
        start: datetime,
        end: datetime,
        slot_duration_minutes: int = 60,
        existing_events: Optional[list[CalendarEvent]] = None,
    ) -> list[tuple[datetime, datetime]]:
        """Find free time slots within a range."""
        if existing_events is None:
            existing_events = self.fetch_events()

        free_slots: list[tuple[datetime, datetime]] = []
        current = start

        # Sort events by start time
        sorted_events = sorted(
            [e for e in existing_events if e.start and e.end],
            key=lambda e: e.start,
        )

        for event in sorted_events:
            event_start = event.start.replace(tzinfo=timezone.utc) if event.start.tzinfo is None else event.start
            event_end = event.end.replace(tzinfo=timezone.utc) if event.end.tzinfo is None else event.end

            if event_start > end or event_end < start:
                continue

            slot = slot_duration_minutes * 60
            if current + __import__("datetime").timedelta(seconds=slot) <= event_start:
                free_slots.append((current, event_start))

            current = max(current, event_end)

        if current < end:
            free_slots.append((current, end))

        return free_slots

    def clear_cache(self) -> None:
        """Clear cached events."""
        if self._cache_path.exists():
            self._cache_path.unlink()
