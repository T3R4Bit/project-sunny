"""P12 — Ideas management for Sunny.

Capture, tag, retrieve, and review ideas. Ideas are stored
as markdown files in the vault with metadata for easy querying.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Idea:
    """A captured idea."""
    id: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    category: str = "general"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    status: str = "new"  # new | reviewing | implemented | shelved
    score: float = 0.0
    author: str = ""


class IdeasManager:
    """Manages the idea capture and retrieval pipeline."""

    def __init__(self, vault: Path) -> None:
        self.vault = vault
        self._ideas_dir = vault / "data" / "ideas"
        self._ideas_dir.mkdir(parents=True, exist_ok=True)
        self._recent_ideas: list[Idea] = []

    def capture(
        self,
        content: str,
        title: str = "",
        tags: list[str] = None,
        category: str = "general",
        author: str = "",
    ) -> Idea:
        """Capture a new idea."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        slug = title.lower().replace(" ", "-")[:30] or f"idea-{timestamp}"
        idea_id = f"idea-{slug}"

        idea = Idea(
            id=idea_id,
            title=title or content[:50],
            content=content,
            tags=tags or [],
            category=category,
            author=author,
        )

        # Save to vault
        filepath = self._ideas_dir / f"{timestamp}-{idea_id}.md"
        filepath.write_text(self._render_idea(idea), encoding="utf-8")

        self._recent_ideas.insert(0, idea)
        log.info("Captured idea: %s", idea_id)
        return idea

    def retrieve(self, query: str = "", tags: list[str] = None,
                 category: str = "", status: str = "") -> list[Idea]:
        """Retrieve ideas matching criteria."""
        results = []

        if not self._ideas_dir.exists():
            return results

        for f in sorted(self._ideas_dir.glob("*.md"), reverse=True):
            idea = self._load_idea_from_file(f)
            if not idea:
                continue

            # Filter by query
            if query:
                query_lower = query.lower()
                if (query_lower not in idea.title.lower() and
                    query_lower not in idea.content.lower()):
                    continue

            # Filter by tags
            if tags:
                if not any(t in idea.tags for t in tags):
                    continue

            # Filter by category
            if category and idea.category != category:
                continue

            # Filter by status
            if status and idea.status != status:
                continue

            results.append(idea)

        return results

    def review(self, idea_id: str, score: float = 0.0,
               status: str = "") -> Optional[Idea]:
        """Review and score an idea."""
        for f in self._ideas_dir.glob(f"{idea_id}*.md"):
            idea = self._load_idea_from_file(f)
            if idea:
                if score > 0:
                    idea.score = score
                if status:
                    idea.status = status
                idea.updated_at = datetime.now(timezone.utc)

                # Update file
                f.write_text(self._render_idea(idea), encoding="utf-8")
                log.info("Reviewed idea %s: score=%.1f status=%s", idea_id, score, status)
                return idea
        return None

    def get_trending(self, days: int = 7) -> list[Idea]:
        """Get most-scored ideas from recent days."""
        cutoff = datetime.now(timezone.utc)
        from datetime import timedelta
        cutoff = cutoff - timedelta(days=days)

        ideas = []
        for f in self._ideas_dir.glob("*.md"):
            idea = self._load_idea_from_file(f)
            if idea and idea.updated_at and idea.updated_at > cutoff:
                ideas.append(idea)

        ideas.sort(key=lambda i: i.score, reverse=True)
        return ideas[:10]

    def get_by_category(self, category: str) -> list[Idea]:
        return self.retrieve(category=category)

    def _load_idea_from_file(self, filepath: Path) -> Optional[Idea]:
        """Load an idea from its markdown file."""
        try:
            content = filepath.read_text(encoding="utf-8")
            title = ""
            tags = []
            category = "general"
            status = "new"
            score = 0.0

            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("# "):
                    title = line[2:]
                elif line.startswith("tags:"):
                    tag_str = line.split(":", 1)[1].strip()
                    tags = [t.strip() for t in tag_str.split(",") if t.strip()]
                elif line.startswith("category:"):
                    category = line.split(":", 1)[1].strip()
                elif line.startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                elif line.startswith("score:"):
                    try:
                        score = float(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass

            if not title:
                title = filepath.stem.replace("idea-", "").replace("-", " ").title()

            return Idea(
                id=filepath.stem.split("-")[-1] if "-" in filepath.stem else filepath.stem,
                title=title,
                content=content,
                tags=tags,
                category=category,
                status=status,
                score=score,
            )
        except Exception as e:
            log.error("Failed to load idea %s: %s", filepath, e)
            return None

    def _render_idea(self, idea: Idea) -> str:
        """Render idea as markdown."""
        lines = [
            f"# {idea.title}",
            "",
            f"tags: {', '.join(idea.tags)}",
            f"category: {idea.category}",
            f"status: {idea.status}",
            f"score: {idea.score}",
            f"author: {idea.author}",
            "",
            idea.content,
        ]
        return "\n".join(lines)

    def get_stats(self) -> dict:
        if not self._ideas_dir.exists():
            return {"total": 0, "recent": 0}
        total = len(list(self._ideas_dir.glob("*.md")))
        return {
            "total": total,
            "recent": len(self._recent_ideas),
            "by_status": {},
        }
