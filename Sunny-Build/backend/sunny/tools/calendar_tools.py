"""P9 — Calendar tools for Sunny.

High-level tools for scheduling, conflict detection, and calendar management.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class ScheduleSlot:
    """A proposed schedule slot."""
    start: datetime
    end: datetime
    event_name: str
    conflicts: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.conflicts is None:
            self.conflicts = []


class CalendarTools:
    """Calendar management tools for the agent."""

    def __init__(self, vault: Path, caldav_sync) -> None:  # type: ignore
        self.vault = vault
        self.caldav = caldav_sync

    def schedule_meeting(
        self,
        title: str,
        duration_minutes: int = 60,
        participants: Optional[list[str]] = None,
    ) -> Optional[ScheduleSlot]:
        """Find a free slot and propose a meeting."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=7)
        free_slots = self.caldav.find_free_slots(now, end, duration_minutes)

        if not free_slots:
            return None

        # Pick the first available slot
        slot = free_slots[0]
        return ScheduleSlot(
            start=slot[0],
            end=slot[1],
            event_name=title,
        )

    def check_conflicts(
        self,
        title: str,
        start: datetime,
        end: datetime,
    ) -> list[str]:
        """Check if a proposed event conflicts with existing events."""
        existing = self.caldav.fetch_events()
        conflicts = self.caldav.find_conflicts(start, end, existing)
        return [c.summary for c in conflicts]

    def get_upcoming_events(self, days_ahead: int = 7) -> list[dict]:
        """Get upcoming events within the next N days."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days_ahead)
        events = self.caldav.fetch_events(now, end)

        results = []
        for event in events:
            if event.start:
                results.append({
                    "summary": event.summary,
                    "start": event.start.isoformat(),
                    "end": event.end.isoformat() if event.end else None,
                    "location": event.location,
                    "status": event.status,
                })
        return results

    def add_event_to_calendar(
        self,
        title: str,
        start: datetime,
        end: datetime,
        description: str = "",
        location: str = "",
    ) -> dict:
        """Add an event and return result."""
        uid = self.caldav.add_event(
            summary=title,
            start=start,
            end=end,
            description=description,
            location=location,
        )

        return {
            "status": "added" if uid else "failed",
            "uid": uid,
            "title": title,
        }

    def get_smart_schedule(
        self,
        preferred_start: datetime = None,
        work_hours: tuple[int, int] = (9, 17),
    ) -> list[dict]:
        """Generate a smart schedule for the next work day."""
        if preferred_start:
            target = preferred_start
        else:
            today = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
            target = today if today.weekday() < 5 else today + timedelta(days=(5 - today.weekday() + 7) % 7 + 1)

        end = target + timedelta(days=1)
        free_slots = self.caldav.find_free_slots(target, end, 60)

        slots = []
        for slot in free_slots:
            slot_start, slot_end = slot
            if slot_start.replace(tzinfo=timezone.utc).hour >= work_hours[0] and \
               slot_start.replace(tzinfo=timezone.utc).hour <= work_hours[1]:
                slots.append({
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat(),
                    "duration_minutes": int((slot_end - slot_start).total_seconds() / 60),
                })

        return slots
