"""P8 — Sleep State Machine for the agent loop.

Transitions between awake, can't sleep, sleeping, and off states.
Implements backoff delays and heartbeat monitoring to keep
the agent alive and responsive between task cycles.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


class SleepState(str, Enum):
    AWAKE = "awake"
    CAN_T_SLEEP = "cant_sleep"
    SLEEPING = "sleeping"
    OFF = "off"


@dataclass
class SleepCycle:
    """One sleep/awake cycle record."""
    state: SleepState
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    duration: float = field(init=False, default=0.0)
    wake_count: int = 0
    sleep_count: int = 0
    heartbeats: int = 0

    def __post_init__(self):
        if self.ended_at:
            self.duration = self.ended_at - self.started_at

    def mark_ended(self) -> None:
        self.ended_at = time.time()
        self.duration = self.ended_at - self.started_at

    def record_heartbeat(self) -> None:
        self.heartbeats += 1


class SleepStateMachine:
    """Manages agent sleep/awake transitions with backoff."""

    SLEEP_BASE_INTERVAL = 120  # 2 min default sleep
    SLEEP_MAX_INTERVAL = 3600  # 1 hour max
    CAN_T_SLEEP_INTERVAL = 30  # 30 sec when we can't sleep
    HEARTBEAT_TIMEOUT = 60  # 60 sec heartbeat timeout
    BACKOFF_MULTIPLIER = 2.0
    BACKOFF_MAX = 300  # 5 min max backoff

    def __init__(self, state: SleepState = SleepState.AWAKE) -> None:
        self.current_state = state
        self._sleep_interval = self.SLEEP_BASE_INTERVAL
        self._heartbeat_interval = self.HEARTBEAT_TIMEOUT
        self._last_heartbeat = 0.0
        self._cycle = SleepCycle(state=self.current_state)
        self._running = False
        self._state_history: list[SleepCycle] = []
        self._total_sleep_time: float = 0.0
        self._total_awake_time: float = 0.0

    @property
    def cycle(self) -> SleepCycle:
        return self._cycle

    @property
    def sleep_interval(self) -> float:
        return self._sleep_interval

    @property
    def state_history(self) -> list[SleepCycle]:
        return self._state_history

    @property
    def total_sleep_time(self) -> float:
        return self._total_sleep_time

    @property
    def total_awake_time(self) -> float:
        return self._total_awake_time

    def transition_to(self, new_state: SleepState) -> None:
        """Transition to a new state."""
        old_state = self.current_state
        self._cycle.mark_ended()
        self._state_history.append(self._cycle)
        self._cycle = SleepCycle(state=new_state)

        if new_state == SleepState.SLEEPING:
            self._cycle.sleep_count += 1
            self._total_sleep_time += self._cycle.duration if self._cycle.duration > 0 else 0

        elif new_state == SleepState.AWAKE:
            self._cycle.wake_count += 1
            self._total_awake_time += self._cycle.duration if self._cycle.duration > 0 else 0

        self.current_state = new_state

        # Apply state-specific interval logic
        if new_state == SleepState.SLEEPING:
            # Exponential backoff: increase interval with each sleep
            self._sleep_interval = min(
                self._sleep_interval * self.BACKOFF_MULTIPLIER,
                self.BACKOFF_MAX
            )
        elif new_state == SleepState.CAN_T_SLEEP:
            self._sleep_interval = self.CAN_T_SLEEP_INTERVAL
        elif new_state == SleepState.AWAKE:
            # Reset backoff when waking
            self._sleep_interval = self.SLEEP_BASE_INTERVAL

        log.info(
            "Sleep state transition: %s → %s (interval=%.0fs)",
            old_state.value, new_state.value, self._sleep_interval
        )

    async def run_sleep_cycle(self, task_exists: bool = False) -> None:
        """Run one sleep/awake cycle.

        Args:
            task_exists: Whether there are pending tasks waiting.
        """
        if task_exists and self.current_state == SleepState.SLEEPING:
            self.transition_to(SleepState.AWAKE)
            return

        if task_exists:
            self.transition_to(SleepState.CAN_T_SLEEP)
            return

        if self.current_state == SleepState.AWAKE and not task_exists:
            self.transition_to(SleepState.SLEEPING)

        interval = self._sleep_interval
        if self.current_state == SleepState.CAN_T_SLEEP:
            interval = self.CAN_T_SLEEP_INTERVAL

        log.debug("Sleeping for %.0f seconds", interval)
        try:
            await asyncio.wait_for(asyncio.sleep(interval), timeout=interval)
        except asyncio.TimeoutError:
            pass

    def heartbeat(self) -> bool:
        """Record a heartbeat. Returns False if heartbeat timed out."""
        self._cycle.record_heartbeat()
        now = time.time()
        if self._last_heartbeat > 0:
            time_since = now - self._last_heartbeat
            if time_since > self._heartbeat_interval:
                log.warning(
                    "Heartbeat timeout: %.0fs since last heartbeat", time_since
                )
                self.transition_to(SleepState.CAN_T_SLEEP)
                return False
        self._last_heartbeat = now
        return True

    def should_sleep(self, task_exists: bool = False) -> SleepState:
        """Decide whether to sleep or stay awake based on task state."""
        if task_exists:
            if self.current_state == SleepState.SLEEPING:
                self.transition_to(SleepState.AWAKE)
            else:
                self.transition_to(SleepState.CAN_T_SLEEP)
        else:
            if self.current_state not in (SleepState.SLEEPING,):
                self.transition_to(SleepState.SLEEPING)
        return self.current_state

    def get_stats(self) -> dict:
        """Return sleep/awake statistics."""
        return {
            "current_state": self.current_state.value,
            "sleep_interval": self._sleep_interval,
            "total_sleep_time": round(self._total_sleep_time, 1),
            "total_awake_time": round(self._total_awake_time, 1),
            "sleep_count": self._cycle.sleep_count,
            "wake_count": self._cycle.wake_count,
            "heartbeats": self._cycle.heartbeats,
            "history_length": len(self._state_history),
        }

    def reset(self) -> None:
        """Reset state machine to initial state."""
        self._total_sleep_time = 0.0
        self._total_awake_time = 0.0
        self._sleep_interval = self.SLEEP_BASE_INTERVAL
        self._last_heartbeat = 0.0
        self._cycle = SleepCycle(state=SleepState.AWAKE)
        self._state_history.clear()
        self.current_state = SleepState.AWAKE
