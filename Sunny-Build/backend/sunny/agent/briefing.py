"""P8 — Agent briefing: morning context restoration.

Loads the agent's knowledge base, pending tasks, and recent
activity to provide a comprehensive briefing before it starts
processing tasks for a new session.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


@dataclass
class BriefingContext:
    """The complete briefing for an agent session."""
    personal_facts: list[str] = field(default_factory=list)
    pending_tasks: list[str] = field(default_factory=list)
    pending_decisions: list[str] = field(default_factory=list)
    recent_deadlines: list[str] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    knowledge_summary: str = ""
    briefing_version: str = "1.0"

    def to_prompt(self) -> str:
        """Render the briefing as a markdown prompt string."""
        lines = ["# Agent Briefing", ""]

        if self.personal_facts:
            lines.append("## Personal Facts")
            lines.append("")
            for fact in self.personal_facts:
                lines.append(f"- {fact}")
            lines.append("")

        if self.pending_tasks:
            lines.append("## Pending Tasks")
            lines.append("")
            for task in self.pending_tasks:
                lines.append(f"- [ ] {task}")
            lines.append("")

        if self.pending_decisions:
            lines.append("## Pending Decisions")
            lines.append("")
            for dec in self.pending_decisions:
                lines.append(f"- [ ] {dec}")
            lines.append("")

        if self.recent_deadlines:
            lines.append("## Deadlines")
            lines.append("")
            for d in self.recent_deadlines:
                lines.append(f"- ⏰ {d}")
            lines.append("")

        if self.knowledge_summary:
            lines.append("## Knowledge Summary")
            lines.append("")
            lines.append(self.knowledge_summary)
            lines.append("")

        return "\n".join(lines)


class BriefingLoader:
    """Loads agent briefing from vault data."""

    def __init__(self, vault: Path) -> None:
        self.vault = vault

    def load(self) -> BriefingContext:
        """Load the full briefing context."""
        ctx = BriefingContext()

        # Load personal facts
        ctx.personal_facts = self._load_facts()

        # Load pending tasks
        ctx.pending_tasks = self._load_pending_tasks()

        # Load pending decisions
        ctx.pending_decisions = self._load_pending_decisions()

        # Extract deadlines from extraction log
        ctx.recent_deadlines = self._load_deadlines()

        # Load knowledge summary
        ctx.knowledge_summary = self._load_knowledge_summary()

        return ctx

    def _load_facts(self) -> list[str]:
        """Load all personal facts from memory/facts/."""
        facts: list[str] = []
        facts_dir = self.vault / "memory" / "facts"
        if facts_dir.exists():
            for f in sorted(facts_dir.glob("*.md")):
                content = f.read_text(encoding="utf-8")
                # Extract the fact statement (first line that doesn't start with -)
                for line in content.strip().split("\n"):
                    if line.strip() and not line.strip().startswith("#"):
                        facts.append(line.strip().lstrip("- ").strip())
                        break
        return facts

    def _load_pending_tasks(self) -> list[str]:
        """Load pending task descriptions."""
        tasks: list[str] = []
        pending_dir = self.vault / "tasks" / "pending"
        if pending_dir.exists():
            for f in sorted(pending_dir.glob("*.md")):
                content = f.read_text(encoding="utf-8")
                for line in content.strip().split("\n"):
                    if line.strip() and not line.strip().startswith("#"):
                        tasks.append(line.strip())
                        break
        return tasks

    def _load_pending_decisions(self) -> list[str]:
        """Load pending decision descriptions."""
        decisions: list[str] = []
        approve_dir = self.vault / "memory" / "decisions" / "pending"
        if approve_dir.exists():
            for f in sorted(approve_dir.glob("*.md")):
                content = f.read_text(encoding="utf-8")
                for line in content.strip().split("\n"):
                    if line.strip() and not line.strip().startswith("#"):
                        decisions.append(line.strip())
                        break
        return decisions

    def _load_deadlines(self) -> list[str]:
        """Extract recent deadlines from extraction log."""
        deadlines: list[str] = []
        extraction_log = self.vault / "log" / "extraction.md"
        if extraction_log.exists():
            content = extraction_log.read_text(encoding="utf-8")
            for line in content.strip().split("\n"):
                if "deadline_mention" in line.lower():
                    deadlines.append(line.strip())
        return deadlines

    def _load_knowledge_summary(self) -> str:
        """Generate a summary of the knowledge base."""
        facts_dir = self.vault / "memory" / "facts"
        if facts_dir.exists():
            fact_files = list(facts_dir.glob("*.md"))
            if fact_files:
                return f"Knowledge base contains {len(fact_files)} facts."
        return "No knowledge base entries yet."

    async def load_as_summary(self) -> dict:
        """Load briefing and return as structured dict for LLM consumption."""
        ctx = self.load()
        return {
            "personal_facts": ctx.personal_facts,
            "pending_tasks": ctx.pending_tasks,
            "pending_decisions": ctx.pending_decisions,
            "recent_deadlines": ctx.recent_deadlines,
            "recent_topics": ctx.recent_topics,
            "knowledge_summary": ctx.knowledge_summary,
            "briefing_version": ctx.briefing_version,
        }
