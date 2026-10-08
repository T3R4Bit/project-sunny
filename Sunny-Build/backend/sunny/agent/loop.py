"""Agent loop — background task scheduler for Sunny."""

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

        # Pull queued tasks by priority/deadline
        tasks = self._task_queue.get_next_tasks(vault, limit=5)

        for task in tasks:
            if not self._running:
                break

            log.info("Executing task %s: %s", task.id, task.description)

            # Mark running
            self._task_queue.mark_running(vault, task.id)

            try:
                # Execute the task
                result = await self._execute_task(task)
                self._task_queue.mark_done(vault, task.id, result)
                notify(f"Task complete: {task.description}", tier=NotifyTier.SILENT)
            except Exception as e:
                log.error("Task %s failed: %s", task.id, e)
                # Revert-on-failure
                await self._revert_on_failure(vault, task.id)
                self._task_queue.mark_failed(vault, task.id, str(e))
                notify(f"Task failed: {task.description} — {e}", tier=NotifyTier.ALERT)

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
        settings = get_settings()
        vault = Path(settings.vault_path)
        source = task.source  # user | extraction | agent

        if source == "agent":
            # Proactive tasks — check tier
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
        # Run in subprocess for isolation
        result = execute_tool_in_subprocess(
            code=task.description,  # task.description contains synthesis code
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
        # Save to disk
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
