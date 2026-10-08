"""P8 — Periodic report generation for Sunny.

Generates summary reports from session data, extraction results,
and agent activity. Reports are stored as markdown in the vault.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


@dataclass
class ReportSection:
    """A single section of a report."""
    title: str
    content: str
    kind: str = "text"  # text | facts | deadlines | topics | decisions


@dataclass
class Report:
    """A generated report."""
    title: str
    sections: list[ReportSection] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    report_type: str = "summary"  # summary | daily | weekly | session

    def add_section(self, title: str, content: str, kind: str = "text") -> None:
        self.sections.append(ReportSection(title=title, content=content, kind=kind))

    def render(self) -> str:
        """Render the report as markdown."""
        lines = [f"# {self.title}", ""]
        for section in self.sections:
            lines.append(f"## {section.title}")
            lines.append("")
            lines.append(section.content)
            lines.append("")
        return "\n".join(lines)

    def save(self, vault: Path, filename: Optional[str] = None) -> Path:
        """Save the report to the vault."""
        reports_dir = vault / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"report-{self.report_type}-{date_str}.md"

        filepath = reports_dir / filename
        filepath.write_text(self.render(), encoding="utf-8")
        log.info("Saved report: %s", filepath)
        return filepath


class ReportGenerator:
    """Generates periodic reports from vault data."""

    def __init__(self, vault: Path) -> None:
        self.vault = vault

    def generate_session_report(
        self,
        session_slug: str,
        summary: str = "",
        facts: list[str] = None,
        deadlines: list[str] = None,
        topics: list[str] = None,
        decisions: list[str] = None,
        open_questions: list[str] = None,
    ) -> Report:
        """Generate a report for a single session."""
        report = Report(
            title=f"Session Report: {session_slug}",
            report_type="session",
        )

        if summary:
            report.add_section("Summary", summary)

        if facts:
            report.add_section(
                "Extracted Facts",
                "\n".join(f"- {f}" for f in facts),
                kind="facts",
            )

        if deadlines:
            report.add_section(
                "Deadlines",
                "\n".join(f"- {d}" for d in deadlines),
                kind="deadlines",
            )

        if topics:
            report.add_section(
                "Topics",
                "\n".join(f"- {t}" for t in topics),
                kind="topics",
            )

        if decisions:
            report.add_section(
                "Decisions",
                "\n".join(f"- {d}" for d in decisions),
                kind="decisions",
            )

        if open_questions:
            report.add_section(
                "Open Questions",
                "\n".join(f"- {q}" for q in open_questions),
            )

        return report

    def generate_daily_report(self, date: Optional[str] = None) -> Report:
        """Generate a daily summary report."""
        if not date:
            date = datetime.now().strftime("%Y%m%d")

        report = Report(
            title=f"Daily Report: {date}",
            report_type="daily",
        )

        # Gather stats from extraction log if available
        extraction_log = self.vault / "log" / "extraction.md"
        if extraction_log.exists():
            content = extraction_log.read_text(encoding="utf-8")
            lines = content.strip().split("\n") if content.strip() else []
            report.add_section(
                "Extraction Activity",
                f"Extraction log has {len(lines)} entries.",
            )

        # Gather facts count
        facts_dir = self.vault / "memory" / "facts"
        if facts_dir.exists():
            fact_files = list(facts_dir.glob("*.md"))
            report.add_section(
                "Personal Facts",
                f"Total facts recorded: {len(fact_files)}.",
            )

        return report

    def generate_weekly_report(self, week_start: Optional[str] = None) -> Report:
        """Generate a weekly summary report."""
        report = Report(
            title=f"Weekly Report: {week_start or 'current'}",
            report_type="weekly",
        )

        # Count all extraction log entries
        extraction_log = self.vault / "log" / "extraction.md"
        if extraction_log.exists():
            content = extraction_log.read_text(encoding="utf-8")
            lines = content.strip().split("\n") if content.strip() else []
            report.add_section(
                "Weekly Summary",
                f"Extraction processed {len(lines)} entries this week.",
            )

        # Count facts
        facts_dir = self.vault / "memory" / "facts"
        if facts_dir.exists():
            fact_files = list(facts_dir.glob("*.md"))
            report.add_section(
                "Knowledge Base",
                f"Knowledge base contains {len(fact_files)} fact entries.",
            )

        # Check for pending decisions
        approve_dir = self.vault / "memory" / "decisions"
        if approve_dir.exists():
            pending = list(approve_dir.glob("pending*.md"))
            report.add_section(
                "Pending Decisions",
                f"{len(pending)} decisions awaiting review.",
                kind="decisions",
            )

        return report


def render_report_table(
    sections: list[dict[str, str]],
    column_widths: Optional[list[int]] = None,
) -> str:
    """Render sections as a markdown table for embedding in reports."""
    if not sections:
        return "No data."

    headers = ["Section", "Content"]
    col_w = column_widths or [20, 80]
    sep = "| " + " | ".join("-" * w for w in col_w) + " |"
    lines = [
        "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_w)) + " |",
        sep,
    ]
    for section in sections:
        lines.append(
            "| " + " | ".join(
                str(section.get(k, "")).ljust(w)
                for k, w in zip(headers, col_w)
            ) + " |"
        )
    return "\n".join(lines)
