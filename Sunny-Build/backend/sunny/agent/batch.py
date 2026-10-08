"""P8 — Batch Pipeline for grouping related tasks.

Groups small tasks into batches for efficient processing,
with configurable batch sizes and priority-based ordering.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

log = logging.getLogger(__name__)


@dataclass
class BatchTask:
    """A task that can be batched with others."""
    id: str
    description: str
    priority: int = 2
    group_key: str = ""  # Tasks with same group_key are batched together
    payload: dict = field(default_factory=dict)


@dataclass
class BatchResult:
    """Result of executing a batch of tasks."""
    batch_id: str
    task_count: int
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration: float = 0.0


class BatchPipeline:
    """Groups and executes tasks in batches for efficiency."""

    DEFAULT_BATCH_SIZE = 5
    DEFAULT_TIMEOUT = 300  # 5 min max batch duration

    def __init__(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.batch_size = batch_size
        self.timeout = timeout
        self._queue: list[BatchTask] = []
        self._batches_run: list[BatchResult] = []
        self._total_tasks_processed: int = 0

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    @property
    def batches_run(self) -> list[BatchResult]:
        return self._batches_run

    @property
    def total_tasks_processed(self) -> int:
        return self._total_tasks_processed

    def enqueue(self, task: BatchTask) -> None:
        """Add a task to the batch queue."""
        self._queue.append(task)
        log.debug("Enqueued batch task %s (group=%s)", task.id, task.group_key or "none")

    def enqueue_many(self, tasks: list[BatchTask]) -> None:
        """Add multiple tasks at once."""
        for task in tasks:
            self.enqueue(task)

    def get_next_batch(self) -> list[BatchTask]:
        """Get the next batch of tasks to process.

        Groups tasks by group_key first, then takes up to batch_size.
        """
        if not self._queue:
            return []

        # Sort by priority (lower = higher priority)
        self._queue.sort(key=lambda t: t.priority)

        # Group tasks by group_key
        groups: dict[str, list[BatchTask]] = {}
        non_grouped: list[BatchTask] = []

        for task in self._queue:
            if task.group_key:
                groups.setdefault(task.group_key, []).append(task)
            else:
                non_grouped.append(task)

        batch: list[BatchTask] = []

        # Add full groups first (preserves atomicity)
        for key in sorted(groups.keys()):
            if len(batch) + len(groups[key]) <= self.batch_size:
                batch.extend(groups[key])
            elif len(batch) < self.batch_size:
                # Partial group — still take it
                batch.extend(groups[key])

        # Fill remaining slots with non-grouped tasks
        for task in non_grouped:
            if len(batch) >= self.batch_size:
                break
            batch.append(task)

        # Remove processed tasks from queue
        batch_ids = {t.id for t in batch}
        self._queue = [t for t in self._queue if t.id not in batch_ids]

        log.info("Pulled batch of %d tasks from %d pending", len(batch), self.pending_count)
        return batch

    def set_batch_processor(
        self,
        processor: Callable[[list[BatchTask]], Coroutine[Any, Any, list[dict]]],
    ) -> None:
        """Register a function that executes a batch."""
        self._processor = processor

    async def run_next_batch(
        self,
        processor: Optional[Callable[[list[BatchTask]], Coroutine[Any, Any, list[dict]]]] = None,
    ) -> BatchResult:
        """Pull and execute the next batch.

        Args:
            processor: Optional executor function. If None, tasks are tracked
                      without execution.
        """
        batch = self.get_next_batch()
        if not batch:
            return BatchResult(
                batch_id=f"empty-{len(self._batches_run)}",
                task_count=0,
            )

        batch_id = f"batch-{len(self._batches_run)}"
        start_time = asyncio.get_event_loop().time()
        results: list[dict] = []
        errors: list[str] = []

        if processor:
            try:
                results = await asyncio.wait_for(
                    processor(batch),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                errors.append(f"Batch {batch_id} timed out after {self.timeout}s")
                log.warning("Batch %s timed out", batch_id)
            except Exception as e:
                errors.append(f"Batch {batch_id} failed: {e}")
                log.error("Batch %s failed: %s", batch_id, e)
        else:
            # Track without execution
            results = [{"status": "tracked", "task_id": t.id} for t in batch]

        duration = asyncio.get_event_loop().time() - start_time
        batch_result = BatchResult(
            batch_id=batch_id,
            task_count=len(batch),
            results=results,
            errors=errors,
            duration=duration,
        )
        self._batches_run.append(batch_result)
        self._total_tasks_processed += len(batch)

        log.info(
            "Completed batch %s: %d tasks in %.1fs",
            batch_id, len(batch), duration
        )
        return batch_result

    async def run_all_batches(
        self,
        processor: Callable[[list[BatchTask]], Coroutine[Any, Any, list[dict]]],
    ) -> list[BatchResult]:
        """Process all pending batches until queue is empty."""
        all_results: list[BatchResult] = []
        while self._queue:
            result = await self.run_next_batch(processor)
            all_results.append(result)
        return all_results

    def clear(self) -> None:
        """Clear the batch queue and reset stats."""
        self._queue.clear()
        self._total_tasks_processed = 0
        self._batches_run.clear()
