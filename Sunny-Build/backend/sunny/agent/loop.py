"""Agent loop — background task scheduler for Sunny.

Integrates P8 sleep state machine, batch pipeline, reports, and briefing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from sunny.config import get_settings
from sunny.tools.task_queue import TaskQueue
from sunny.tools.registry import ToolRegistry
from sunny.tools.subprocess_worker import execute_tool_in_subprocess
from sunny.tools.notify import notify, NotifyTier
from sunny.agent.sleep_state import SleepStateMachine, SleepState
from sunny.agent.batch import BatchPipeline, BatchTask

log = logging.getLogger(__name__)


class AgentState(str, Enum):
    AWAKE = "awake"
    CANT_SLEEP = "cant_sleep"
    SLEEPING = "sleeping"
    OFF = "off"


class AgentLoop:
    """Main agent loop that runs background tasks."""

    INTERVAL_AWAKE = 300  # 5 minutes in seconds
    INTERVAL_CANT_SLEEP = 300

    def __init__(self) -> None:
        self.state = AgentState.OFF
        self._task_queue = TaskQueue()
        self._tool_registry = ToolRegistry()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._cycle_start_hash: str = ""
        self._sleep_state = SleepStateMachine(state=SleepState.AWAKE)
        self._batch_pipeline = BatchPipeline()
        self._last_report_time: float = 0
        self._report_interval: int = 86400  # 24 hours default

    async def start(self, state: AgentState = AgentState.AWAKE) -> None:
        """Start the agent loop."""
        if self._running:
            log.warning("Agent loop already running")
            return
        self.state = state
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        log.info("Agent loop started (state=%s)", state.value)

    async def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("Agent loop stopped")

    async def _run_loop(self) -> None:
        """Main loop: pull tasks → execute → log → commit."""
        while self._running:
            try:
                await self._cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception("Agent loop error: %s", e)
            interval = self.INTERVAL_AWAKE if self.state in (AgentState.AWAKE, AgentState.CANT_SLEEP) else 600
            try:
                await asyncio.wait_for(asyncio.sleep(interval), timeout=interval + 5)
            except asyncio.TimeoutError:
                pass

    async def _cycle(self) -> None:
        """Execute one agent cycle."""
        settings = get_settings()
        vault = Path(settings.vault_path)
        log.info("Agent cycle start (state=%s)", self.state.value)

        # Handle sleep state
        tasks = self._task_queue.get_next_tasks(vault, limit=5)
        task_exists = len(tasks) > 0
        self._sleep_state.should_sleep(task_exists)

        # Execute tasks in batches if available
        if tasks:
            await self._execute_batch(vault, tasks)
        else:
            # Run sleep cycle
            await self._sleep_state.run_sleep_cycle(task_exists=False)

        # Periodic report generation
        now = asyncio.get_event_loop().time()
        if now - self._last_report_time > self._report_interval:
            await self._generate_periodic_report(vault)
            self._last_report_time = now

    async def _execute_batch(self, vault: Path, tasks: list[Any]) -> None:
        """Execute tasks as a batch."""
        # Add tasks to batch pipeline for grouping
        batch_tasks = []
        for task in tasks:
            batch_tasks.append(BatchTask(
                id=task.id,
                description=task.description,
                priority=task.priority,
                group_key=task.source,
            ))

        self._batch_pipeline.enqueue_many(batch_tasks)

        # Execute batch
        async def processor(batch: list[BatchTask]) -> list[dict]:
            results = []
            for t in batch:
                task_result = self._execute_single_task(t, vault)
                if asyncio.iscoroutine(task_result):
                    task_result = await task_result
                results.append(task_result)
            return results

        result = await self._batch_pipeline.run_next_batch(processor)
        log.info(
            "Batch execution: %d tasks, %d errors",
            result.task_count, len(result.errors)
        )

    async def _generate_periodic_report(self, vault: Path) -> None:
        """Generate a daily/periodic report."""
        try:
            from sunny.agent.reports import ReportGenerator
            generator = ReportGenerator(vault)
            report = generator.generate_daily_report()
            report.save(vault)
            log.info("Generated periodic report")
        except Exception as e:
            log.error("Failed to generate report: %s", e)

    async def _execute_single_task(self, task: BatchTask, vault: Path) -> dict:
        """Execute a single batch task."""
        if task.group_key == "synthesis":
            result = execute_tool_in_subprocess(
                code=task.description,
                timeout=60,
                memory_limit_mb=256,
            )
            return result

        return {
            "status": "completed",
            "task_id": task.id,
            "description": task.description,
        }

    async def _execute_task(self, task: Any) -> dict:
        """Execute a single task based on its type."""
        settings = get_settings()
        vault = Path(settings.vault_path)

        if task.agent == "default":
            return await self._default_task_handler(task)
        elif task.agent == "synthesis":
            return await self._synthesis_task_handler(task)
        else:
            return {"status": "skipped", "reason": f"Unknown agent: {task.agent}"}

    async def _default_task_handler(self, task: Any) -> dict:
        """Handle default agent tasks."""
        source = task.source

        if source == "agent":
            if task.priority == 1:
                notify(f"Proactive: {task.description}", tier=NotifyTier.ALERT)
            elif task.priority == 2:
                notify(f"Proactive: {task.description}", tier=NotifyTier.SUGGEST)
            else:
                notify(f"Proactive: {task.description}", tier=NotifyTier.QUIET)

        return {
            "status": "completed",
            "task_id": task.id,
            "description": task.description,
        }

    async def _synthesis_task_handler(self, task: Any) -> dict:
        """Handle synthesis tasks (tool creation, deep analysis)."""
        result = execute_tool_in_subprocess(
            code=task.description,
            timeout=60,
            memory_limit_mb=256,
        )
        return result

    async def _revert_on_failure(self, vault: Path, task_id: str) -> None:
        """Git revert to cycle-start on unrecoverable error."""
        if not self._cycle_start_hash:
            log.warning("No cycle-start hash to revert to for task %s", task_id)
            return

        try:
            import subprocess
            result = subprocess.run(
                ["git", "revert", "--no-commit", self._cycle_start_hash],
                cwd=vault,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info("Reverted cycle for task %s", task_id)
            else:
                log.error("Revert failed for task %s: %s", task_id, result.stderr)
        except Exception as e:
            log.error("Revert error for task %s: %s", task_id, e)

    def add_task(self, description: str, priority: int = 2,
                 agent: str = "default", source: str = "user",
                 vault: Optional[Path] = None) -> str:
        """Add a task to the queue. Returns task ID."""
        task_id = self._task_queue.enqueue(
            description=description,
            priority=priority,
            agent=agent,
            source=source,
        )
        if vault:
            self._task_queue._save_task(vault, self._task_queue._find_task(task_id))
        return task_id

    def set_state(self, state: AgentState) -> None:
        """Change agent state."""
        self.state = state
        log.info("Agent state changed to %s", state.value)

    def get_status(self) -> dict:
        """Get agent loop status."""
        return {
            "state": self.state.value,
            "running": self._running,
            "task_count": self._task_queue.count_pending(),
            "sleep_state": self._sleep_state.get_stats(),
            "batch_stats": {
                "pending": self._batch_pipeline.pending_count,
                "total_processed": self._batch_pipeline.total_tasks_processed,
            },
        }


# Global agent loop singleton
_agent_loop: Optional[AgentLoop] = None


def get_agent_loop() -> AgentLoop:
    """Get the global agent loop, creating if needed."""
    global _agent_loop
    if _agent_loop is None:
        _agent_loop = AgentLoop()
    return _agent_loop


async def start_agent_loop(state: AgentState = AgentState.AWAKE) -> None:
    """Start the agent loop (called from lifespan)."""
    loop = get_agent_loop()
    await loop.start(state)


async def stop_agent_loop() -> None:
    """Stop the agent loop (called from lifespan)."""
    global _agent_loop
    if _agent_loop:
        await _agent_loop.stop()
        _agent_loop = None
