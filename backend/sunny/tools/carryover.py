"""P13 — Task carry-over tracking.

Handles automatic carry-over of incomplete tasks to new
time periods (days, weeks, months).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Carryover:
    """A carried-over task."""
    original_id: str
    description: str
    original_date: datetime
    carried_to: datetime
    reason: str = ""
    times_carried: int = 0
    is_important: bool = False

    def to_vault_line(self) -> str:
        return f"carryover:{self.original_id} -> {self.carried_to.date()} ({self.reason})"


class CarryoverManager:
    """Manages task carry-overs."""

    def __init__(self, vault: Path) -> None:
        self.vault = vault
        self._carryovers_dir = vault / "data" / "carryovers"
        self._carryovers_dir.mkdir(parents=True, exist_ok=True)
        self._max_carries = 3  # Don't carry same task more than 3 times

    def carry_over_tasks(
        self,
        tasks: list[dict],
        from_period: str = "day",
        to_date: Optional[datetime] = None,
    ) -> list[Carryover]:
        """Carry over incomplete tasks to the next period."""
        if to_date is None:
            to_date = datetime.now(timezone.utc)

        carryovers: list[Carryover] = []

        for task in tasks:
            if not task.get("completed", False):
                description = task.get("description", "Untitled task")
                original_date = task.get("created_at", datetime.now(timezone.utc))

                # Check max carries
                times_carried = self._count_carries(description)
                if times_carried >= self._max_carries:
                    log.info("Task %s hit max carries, dropping", description)
                    continue

                reason = f"Auto-carryover from {from_period}"
                if times_carried > 0:
                    reason += f" (carried {times_carried}x)"

                carryover = Carryover(
                    original_id=task.get("id", ""),
                    description=description,
                    original_date=original_date,
                    carried_to=to_date,
                    reason=reason,
                    times_carried=times_carried,
                )

                # Save
                self._save_carryover(carryover)
                carryovers.append(carryover)
                log.info("Carried over: %s (%dx)", description, times_carried)

        return carryovers

    def get_pending_carries(self, before: Optional[datetime] = None) -> list[Carryover]:
        """Get pending carry-overs."""
        results = []
        if not self._carryovers_dir.exists():
            return results

        for f in self._carryovers_dir.glob("*.md"):
            carryover = self._load_carryover(f)
            if carryover:
                if before is None or carryover.carried_to <= before:
                    results.append(carryover)

        results.sort(key=lambda c: c.carried_to, reverse=True)
        return results

    def clear_carryover(self, original_id: str) -> bool:
        """Mark a carry-over as resolved."""
        for f in self._carryovers_dir.glob("*.md"):
            carryover = self._load_carryover(f)
            if carryover and carryover.original_id == original_id:
                f.unlink()
                log.info("Cleared carryover: %s", original_id)
                return True
        return False

    def get_carryover_summary(self) -> str:
        """Generate a summary of carry-over stats."""
        pending = self.get_pending_carries()
        if not pending:
            return "No pending carry-overs."

        important = [c for c in pending if c.is_important]
        lines = [
            "# Carry-Over Summary",
            "",
            f"Pending: {len(pending)} tasks",
        ]
        if important:
            lines.extend([
                "",
                "## Important",
                "",
            ])
            for c in important:
                lines.append(f"- [ ] {c.description} (carried {c.times_carried}x)")

        return "\n".join(lines)

    def _count_carries(self, description: str) -> int:
        count = 0
        for f in self._carryovers_dir.glob("*.md"):
            carryover = self._load_carryover(f)
            if carryover and carryover.description == description:
                count += 1
        return count

    def _save_carryover(self, carryover: Carryover) -> None:
        filepath = self._carryovers_dir / f"{carryover.original_id}.md"
        filepath.write_text(
            f"# {carryover.description}\n\n"
            f"carried_to: {carryover.carried_to.isoformat()}\n"
            f"original_date: {carryover.original_date.isoformat()}\n"
            f"reason: {carryover.reason}\n"
            f"times_carried: {carryover.times_carried}\n",
            encoding="utf-8",
        )

    def _load_carryover(self, filepath: Path) -> Optional[Carryover]:
        try:
            content = filepath.read_text(encoding="utf-8")
            carried_to = ""
            original_date = ""
            reason = ""
            times_carried = 0
            description = filepath.stem.replace("-", " ").title()

            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("carried_to:"):
                    carried_to = line.split(":", 1)[1].strip()
                elif line.startswith("original_date:"):
                    original_date = line.split(":", 1)[1].strip()
                elif line.startswith("reason:"):
                    reason = line.split(":", 1)[1].strip()
                elif line.startswith("times_carried:"):
                    try:
                        times_carried = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass

            return Carryover(
                original_id=filepath.stem,
                description=description,
                original_date=datetime.fromisoformat(original_date) if original_date else datetime.now(),
                carried_to=datetime.fromisoformat(carried_to) if carried_to else datetime.now(),
                reason=reason,
                times_carried=times_carried,
            )
        except Exception as e:
            log.error("Failed to load carryover %s: %s", filepath, e)
            return None
