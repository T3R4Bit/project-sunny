"""Task queue — YAML-based task management for the agent loop."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sunny.frontmatter import dump, load
from sunny.vault.io import read_file, atomic_write


@dataclass
class Task:
    id: str
    created: str
    status: str  # queued | running | done | failed
    priority: int  # 1 high .. 4 low
    deadline: Optional[str] = None
    agent: str = "default"
    source: str = "user"  # user | extraction | agent
    description: str = ""
    result: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskQueue:
    """YAML-based task queue stored in tasks-queue/."""

    def __init__(self) -> None:
        self._pending: list[Task] = []

    def enqueue(self, description: str, priority: int = 2,
                agent: str = "default", source: str = "user",
                deadline: Optional[str] = None) -> str:
        """Add a task to the queue. Returns task ID."""
        task_id = f"tsk_{uuid.uuid4().hex[:12]}"
        task = Task(
            id=task_id,
            created=_now_iso(),
            status="queued",
            priority=max(1, min(4, priority)),
            deadline=deadline,
            agent=agent,
            source=source,
            description=description,
        )
        self._pending.append(task)
        return task_id

    def get_next_tasks(self, vault: Path, limit: int = 5) -> list[Task]:
        """Get the next N queued tasks sorted by priority then deadline."""
        # Load any tasks on disk that might not be in memory
        self._load_tasks(vault)

        # Filter queued, exclude running/failed/done
        queued = [t for t in self._pending if t.status == "queued"]

        # Sort by priority (1 = high first), then deadline (earliest first)
        queued.sort(key=lambda t: (t.priority, t.deadline or "9999"))

        return queued[:limit]

    def mark_running(self, vault: Path, task_id: str) -> None:
        """Mark a task as running."""
        task = self._find_task(task_id)
        if task:
            task.status = "running"
            self._save_task(vault, task)

    def mark_done(self, vault: Path, task_id: str, result: Any = None) -> None:
        """Mark a task as done with optional result."""
        task = self._find_task(task_id)
        if task:
            task.status = "done"
            task.result = str(result) if result else None
            self._save_task(vault, task)

    def mark_failed(self, vault: Path, task_id: str, error: str) -> None:
        """Mark a task as failed with error context."""
        task = self._find_task(task_id)
        if task:
            task.status = "failed"
            task.result = f"Error: {error}"
            self._save_task(vault, task)

    def _find_task(self, task_id: str) -> Optional[Task]:
        for t in self._pending:
            if t.id == task_id:
                return t
        return None

    def _load_tasks(self, vault: Path) -> None:
        """Load pending tasks from tasks-queue/ directory."""
        queue_dir = vault / "tasks-queue"
        if not queue_dir.exists():
            return
        for f in queue_dir.glob("*.yaml"):
            content = read_file(f) or ""
            if not content:
                continue
            post = load(content)
            meta = dict(post.metadata)
            if meta.get("status") in ("queued", "running"):
                task = Task(
                    id=meta.get("id", f.stem),
                    created=meta.get("created", _now_iso()),
                    status=meta.get("status", "queued"),
                    priority=int(meta.get("priority", 2)),
                    deadline=meta.get("deadline"),
                    agent=meta.get("agent", "default"),
                    source=meta.get("source", "user"),
                    description=meta.get("description", ""),
                    result=meta.get("result"),
                )
                if task not in self._pending:
                    self._pending.append(task)

    def _save_task(self, vault: Path, task: Task) -> None:
        """Save a task to disk."""
        queue_dir = vault / "tasks-queue"
        queue_dir.mkdir(parents=True, exist_ok=True)
        p = queue_dir / f"{task.id}.yaml"
        meta = {
            "id": task.id,
            "created": task.created,
            "status": task.status,
            "priority": task.priority,
            "deadline": task.deadline,
            "agent": task.agent,
            "source": task.source,
            "description": task.description,
            "result": task.result,
        }
        post = load("")
        post.metadata.update(meta)
        atomic_write(p, dump(post))

    def count_pending(self) -> int:
        """Count queued tasks."""
        return sum(1 for t in self._pending if t.status == "queued")
