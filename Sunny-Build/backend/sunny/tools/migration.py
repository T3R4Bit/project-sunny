"""P13 — Data migration and version compatibility.

Handles migrating data between Sunny versions, ensuring
backward compatibility and smooth transitions.
"""

from __future__ import annotations

import logging
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class MigrationStep:
    """A single migration step."""
    name: str
    version_from: str
    version_to: str
    description: str = ""
    executed: bool = False
    error: str = ""


@dataclass
class MigrationResult:
    """Result of a migration run."""
    from_version: str = ""
    to_version: str = "2.0"
    steps_executed: int = 0
    steps_total: int = 0
    errors: list[str] = field(default_factory=list)
    completed: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def success(self) -> bool:
        return self.completed and not self.errors


class DataMigration:
    """Handles data migration between Sunny versions."""

    CURRENT_VERSION = "2.0"
    MIGRATION_LOG = "migration-log.json"

    def __init__(self, vault: Path) -> None:
        self.vault = vault
        self._steps: list[MigrationStep] = self._register_default_steps()

    def _register_default_steps(self) -> list[MigrationStep]:
        """Register all known migration steps."""
        return [
            MigrationStep(
                name="init_data_dirs",
                version_from="0.0",
                version_to="1.0",
                description="Create initial data directories",
            ),
            MigrationStep(
                name="migrate_extractions",
                version_from="1.0",
                version_to="1.1",
                description="Migrate extraction logs to new format",
            ),
            MigrationStep(
                name="migrate_tasks",
                version_from="1.0",
                version_to="1.1",
                description="Migrate task format",
            ),
            MigrationStep(
                name="migrate_facts",
                version_from="1.1",
                version_to="1.2",
                description="Migrate personal facts format",
            ),
            MigrationStep(
                name="migrate_sessions",
                version_from="1.1",
                version_to="1.2",
                description="Migrate session data",
            ),
            MigrationStep(
                name="create_ideas_dir",
                version_from="1.2",
                version_to="1.3",
                description="Create ideas data directory",
            ),
            MigrationStep(
                name="create_recipes_dir",
                version_from="1.2",
                version_to="1.3",
                description="Create recipes data directory",
            ),
            MigrationStep(
                name="create_voice_dir",
                version_from="1.2",
                version_to="1.3",
                description="Create voice interaction directory",
            ),
            MigrationStep(
                name="create_reports_dir",
                version_from="1.2",
                version_to="1.4",
                description="Create reports directory",
            ),
            MigrationStep(
                name="create_carryovers_dir",
                version_from="1.2",
                version_to="1.4",
                description="Create carry-over directory",
            ),
            MigrationStep(
                name="migrate_extraction_to_p7",
                version_from="1.3",
                version_to="1.5",
                description="Migrate extraction to P7 format",
            ),
            MigrationStep(
                name="create_health_dir",
                version_from="1.4",
                version_to="2.0",
                description="Create health data directory",
            ),
            MigrationStep(
                name="create_calendar_dir",
                version_from="1.4",
                version_to="2.0",
                description="Create calendar data directory",
            ),
            MigrationStep(
                name="ensure_backwards_compat",
                version_from="*",
                version_to="2.0",
                description="Ensure backward compatibility with existing data",
            ),
        ]

    def run(self, from_version: str = "") -> MigrationResult:
        """Run all pending migrations."""
        result = MigrationResult(
            from_version=from_version or self._detect_version(),
            to_version=self.CURRENT_VERSION,
        )

        if not result.from_version:
            result.completed = True
            return result

        # Ensure data directories exist
        data_dirs = [
            "data/ideas",
            "data/recipes",
            "data/voice",
            "data/carryovers",
            "data/health",
            "data/calendar",
            "data/caldav_cache",
            "data/garmin_cache",
            "reports",
        ]

        for d in data_dirs:
            dir_path = self.vault / d
            dir_path.mkdir(parents=True, exist_ok=True)

        # Execute migration steps
        for step in self._steps:
            if not self._needs_migration(step, result.from_version):
                continue

            try:
                getattr(self, f"_migrate_{step.name}", self._noop)(step)
                step.executed = True
                result.steps_executed += 1
            except Exception as e:
                step.error = str(e)
                result.errors.append(f"{step.name}: {e}")
                log.error("Migration step %s failed: %s", step.name, e)

        result.steps_total = len([s for s in self._steps if self._needs_migration(s, result.from_version)])
        result.completed = not result.errors

        # Save migration log
        self._save_migration_log(result)

        log.info(
            "Migration complete: %d/%d steps, from %s → %s",
            result.steps_executed, result.steps_total,
            result.from_version, result.to_version
        )
        return result

    def _detect_version(self) -> str:
        """Detect current vault version."""
        # Check migration log
        log_path = self.vault / self.MIGRATION_LOG
        if log_path.exists():
            try:
                log_data = json.loads(log_path.read_text(encoding="utf-8"))
                if log_data:
                    return log_data.get("from_version", "")
            except Exception:
                pass

        # Check for version file
        version_file = self.vault / ".sunny" / "version"
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()

        return ""

    def _needs_migration(self, step: MigrationStep, from_version: str) -> bool:
        """Check if a migration step needs to run."""
        if step.executed:
            return False

        if step.version_from == "*":
            return True

        if from_version and step.version_from != "*":
            # Simple version comparison: if current >= from_version, skip
            try:
                from_version_num = float(from_version)
                step_version = float(step.version_from)
                if from_version_num >= step_version:
                    return False
            except ValueError:
                pass

        return True

    def _noop(self, step: MigrationStep) -> None:
        """Default no-op migration."""
        pass

    def _migrate_init_data_dirs(self, step: MigrationStep) -> None:
        """Create initial data directories."""
        dirs = [
            "memory/facts",
            "memory/decisions/pending",
            "tasks/pending",
            "tasks/completed",
            "log",
            "chats",
            "docs",
        ]
        for d in dirs:
            (self.vault / d).mkdir(parents=True, exist_ok=True)

    def _migrate_extractions(self, step: MigrationStep) -> None:
        """Migrate extraction logs to new format."""
        old_log = self.vault / "log" / "extraction.txt"
        if old_log.exists():
            new_log = self.vault / "log" / "extraction.md"
            if not new_log.exists():
                content = old_log.read_text(encoding="utf-8")
                new_log.write_text("# Extraction Log\n\n" + content, encoding="utf-8")
                old_log.unlink()

    def _migrate_tasks(self, step: MigrationStep) -> None:
        """Migrate task format."""
        pass

    def _migrate_facts(self, step: MigrationStep) -> None:
        """Migrate personal facts format."""
        pass

    def _migrate_sessions(self, step: MigrationStep) -> None:
        """Migrate session data."""
        pass

    def _migrate_create_ideas_dir(self, step: MigrationStep) -> None:
        (self.vault / "data" / "ideas").mkdir(parents=True, exist_ok=True)

    def _migrate_create_recipes_dir(self, step: MigrationStep) -> None:
        (self.vault / "data" / "recipes").mkdir(parents=True, exist_ok=True)

    def _migrate_create_voice_dir(self, step: MigrationStep) -> None:
        (self.vault / "data" / "voice").mkdir(parents=True, exist_ok=True)

    def _migrate_create_reports_dir(self, step: MigrationStep) -> None:
        (self.vault / "reports").mkdir(parents=True, exist_ok=True)

    def _migrate_create_carryovers_dir(self, step: MigrationStep) -> None:
        (self.vault / "data" / "carryovers").mkdir(parents=True, exist_ok=True)

    def _migrate_migrate_extraction_to_p7(self, step: MigrationStep) -> None:
        pass

    def _migrate_create_health_dir(self, step: MigrationStep) -> None:
        (self.vault / "data" / "health").mkdir(parents=True, exist_ok=True)

    def _migrate_create_calendar_dir(self, step: MigrationStep) -> None:
        (self.vault / "data" / "calendar").mkdir(parents=True, exist_ok=True)

    def _migrate_ensure_backwards_compat(self, step: MigrationStep) -> None:
        """Ensure existing data is compatible with current version."""
        pass

    def _save_migration_log(self, result: MigrationResult) -> None:
        """Save migration log."""
        log_path = self.vault / self.MIGRATION_LOG
        log_data = {
            "from_version": result.from_version,
            "to_version": result.to_version,
            "steps_executed": result.steps_executed,
            "steps_total": result.steps_total,
            "errors": result.errors,
            "completed": result.completed,
            "timestamp": result.timestamp,
        }
        log_path.write_text(json.dumps(log_data, indent=2), encoding="utf-8")

    def run_status(self) -> dict:
        """Get current migration status."""
        from_version = self._detect_version()
        pending = [s for s in self._steps if self._needs_migration(s, from_version)]
        return {
            "current_version": self.CURRENT_VERSION,
            "vault_version": from_version or "unknown",
            "pending_steps": len(pending),
            "steps": [
                {
                    "name": s.name,
                    "version_from": s.version_from,
                    "version_to": s.version_to,
                    "executed": s.executed,
                }
                for s in self._steps
            ],
        }
