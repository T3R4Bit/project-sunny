"""P8 — Agent Sleep State Machine, Batch Pipeline, Reports, Briefing."""

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sunny.agent.sleep_state import SleepStateMachine, SleepState, SleepCycle
from sunny.agent.batch import BatchPipeline, BatchTask, BatchResult
from sunny.agent.reports import ReportGenerator, Report, ReportSection
from sunny.agent.briefing import BriefingLoader, BriefingContext


# ── Sleep State Machine tests ─────────────────────────────────────────


class TestSleepStateMachine:
    """Test sleep/awake state transitions."""

    def test_initial_state(self):
        sm = SleepStateMachine()
        assert sm.current_state == SleepState.AWAKE
        assert sm.sleep_interval == 120

    def test_transition_to_sleeping(self):
        sm = SleepStateMachine()
        sm.transition_to(SleepState.SLEEPING)
        assert sm.current_state == SleepState.SLEEPING
        # Backoff should increase interval
        assert sm.sleep_interval == 240

    def test_transition_to_can_t_sleep(self):
        sm = SleepStateMachine()
        sm.transition_to(SleepState.CAN_T_SLEEP)
        assert sm.current_state == SleepState.CAN_T_SLEEP
        assert sm.sleep_interval == 30

    def test_transition_to_awake_resets_backoff(self):
        sm = SleepStateMachine()
        sm.transition_to(SleepState.SLEEPING)
        assert sm.sleep_interval == 240
        sm.transition_to(SleepState.AWAKE)
        assert sm.current_state == SleepState.AWAKE
        assert sm.sleep_interval == 120  # reset

    def test_multiple_sleep_backoff(self):
        sm = SleepStateMachine()
        sm.transition_to(SleepState.SLEEPING)
        first = sm.sleep_interval  # 240
        sm.transition_to(SleepState.AWAKE)  # reset
        sm.transition_to(SleepState.SLEEPING)
        second = sm.sleep_interval  # 240 again since reset
        assert second == first

    def test_backoff_capped_at_max(self):
        sm = SleepStateMachine()
        sm._sleep_interval = 200  # close to cap
        sm.transition_to(SleepState.SLEEPING)
        # 200 * 2 = 400, min(400, 300) = 300
        assert sm.sleep_interval == 300

    def test_sleep_count_increments(self):
        sm = SleepStateMachine()
        sm.transition_to(SleepState.SLEEPING)
        sm.transition_to(SleepState.AWAKE)
        sm.transition_to(SleepState.SLEEPING)
        assert sm.cycle.sleep_count == 1

    def test_wake_count_increments(self):
        sm = SleepStateMachine()
        sm.transition_to(SleepState.SLEEPING)
        sm.transition_to(SleepState.AWAKE)
        sm.transition_to(SleepState.AWAKE)
        assert sm.cycle.wake_count == 1

    def test_heartbeat_records(self):
        sm = SleepStateMachine()
        sm.heartbeat()
        sm.heartbeat()
        assert sm.cycle.heartbeats == 2

    def test_heartbeat_timeout(self):
        sm = SleepStateMachine()
        sm._heartbeat_interval = 0.01
        sm._last_heartbeat = time.time() - 1  # set to 1s ago
        result = sm.heartbeat()
        assert result is False
        assert sm.current_state == SleepState.CAN_T_SLEEP

    def test_should_sleep_with_tasks(self):
        sm = SleepStateMachine()
        result = sm.should_sleep(task_exists=True)
        assert result in (SleepState.AWAKE, SleepState.CAN_T_SLEEP)

    def test_should_sleep_without_tasks(self):
        sm = SleepStateMachine()
        result = sm.should_sleep(task_exists=False)
        assert result == SleepState.SLEEPING

    def test_get_stats(self):
        sm = SleepStateMachine()
        sm.transition_to(SleepState.SLEEPING)
        sm.heartbeat()
        stats = sm.get_stats()
        assert stats["current_state"] == "sleeping"
        assert stats["sleep_count"] == 1
        assert stats["wake_count"] == 0
        assert stats["heartbeats"] == 1

    def test_state_history_accumulates(self):
        sm = SleepStateMachine()
        sm.transition_to(SleepState.SLEEPING)
        sm.transition_to(SleepState.AWAKE)
        sm.transition_to(SleepState.SLEEPING)
        assert len(sm.state_history) == 3  # three transitions recorded

    def test_reset(self):
        sm = SleepStateMachine()
        sm.transition_to(SleepState.SLEEPING)
        sm.transition_to(SleepState.AWAKE)
        sm.reset()
        assert sm.current_state == SleepState.AWAKE
        assert sm.sleep_interval == 120
        assert sm.cycle.sleep_count == 0
        assert len(sm.state_history) == 0

    @pytest.mark.asyncio
    async def test_run_sleep_cycle_no_tasks(self):
        sm = SleepStateMachine()
        sm._sleep_interval = 0.01
        await sm.run_sleep_cycle(task_exists=False)
        assert sm.current_state == SleepState.SLEEPING

    @pytest.mark.asyncio
    async def test_run_sleep_cycle_with_tasks(self):
        sm = SleepStateMachine()
        sm._sleep_interval = 0.01
        sm.transition_to(SleepState.SLEEPING)
        await sm.run_sleep_cycle(task_exists=True)
        assert sm.current_state == SleepState.AWAKE


# ── Batch Pipeline tests ─────────────────────────────────────────


class TestBatchPipeline:
    """Test task batching and grouping."""

    def test_initial_state(self):
        bp = BatchPipeline()
        assert bp.pending_count == 0
        assert bp.total_tasks_processed == 0

    def test_enqueue_single(self):
        bp = BatchPipeline()
        bp.enqueue(BatchTask(id="1", description="Task 1"))
        assert bp.pending_count == 1

    def test_enqueue_many(self):
        bp = BatchPipeline()
        tasks = [BatchTask(id=str(i), description=f"Task {i}") for i in range(5)]
        bp.enqueue_many(tasks)
        assert bp.pending_count == 5

    def test_get_batch_orders_by_priority(self):
        bp = BatchPipeline()
        bp.enqueue(BatchTask(id="1", description="Low", priority=3))
        bp.enqueue(BatchTask(id="2", description="High", priority=1))
        bp.enqueue(BatchTask(id="3", description="Medium", priority=2))

        batch = bp.get_next_batch()
        assert len(batch) == 3
        assert batch[0].priority == 1
        assert batch[1].priority == 2
        assert batch[2].priority == 3

    def test_get_batch_respects_batch_size(self):
        bp = BatchPipeline(batch_size=2)
        for i in range(5):
            bp.enqueue(BatchTask(id=str(i), description=f"Task {i}"))

        batch = bp.get_next_batch()
        assert len(batch) == 2
        assert bp.pending_count == 3

    def test_get_batch_groups_by_key(self):
        bp = BatchPipeline(batch_size=10)
        bp.enqueue(BatchTask(id="1", description="A", group_key="grp1"))
        bp.enqueue(BatchTask(id="2", description="B", group_key="grp1"))
        bp.enqueue(BatchTask(id="3", description="C", group_key="grp2"))

        batch = bp.get_next_batch()
        # grp1 tasks should be together
        group_keys = {t.group_key for t in batch}
        assert "grp1" in group_keys

    def test_get_batch_empty(self):
        bp = BatchPipeline()
        batch = bp.get_next_batch()
        assert batch == []

    def test_batch_removes_from_queue(self):
        bp = BatchPipeline()
        bp.enqueue(BatchTask(id="1", description="T1"))
        bp.enqueue(BatchTask(id="2", description="T2"))
        bp.get_next_batch()
        assert bp.pending_count == 0

    @pytest.mark.asyncio
    async def test_run_next_batch(self):
        bp = BatchPipeline()
        bp.enqueue(BatchTask(id="1", description="T1"))

        async def proc(batch):
            return [{"status": "ok"}]

        result = await bp.run_next_batch(proc)
        assert isinstance(result, BatchResult)
        assert result.task_count == 1
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_run_all_batches(self):
        bp = BatchPipeline(batch_size=2)
        for i in range(5):
            bp.enqueue(BatchTask(id=str(i), description=f"T{i}"))

        async def proc(batch):
            return [{"status": "ok"} for _ in batch]

        results = await bp.run_all_batches(proc)
        assert len(results) >= 2
        assert bp.total_tasks_processed == 5

    @pytest.mark.asyncio
    async def test_batch_timeout(self):
        bp = BatchPipeline(timeout=0.01)
        bp.enqueue(BatchTask(id="1", description="Slow task"))

        async def slow_proc(batch):
            await asyncio.sleep(10)
            return []

        result = await bp.run_next_batch(slow_proc)
        assert len(result.errors) > 0

    def test_clear(self):
        bp = BatchPipeline()
        bp.enqueue(BatchTask(id="1", description="T1"))
        bp.clear()
        assert bp.pending_count == 0
        assert bp.total_tasks_processed == 0


# ── Report Generator tests ─────────────────────────────────────────


class TestReportGenerator:
    """Test report generation."""

    def test_generate_session_report(self, vault: Path):
        gen = ReportGenerator(vault)
        report = gen.generate_session_report(
            session_slug="test-session",
            summary="Test summary",
            facts=["F1", "F2"],
            deadlines=["Due Friday"],
            topics=["Python"],
            decisions=["Use Rust"],
            open_questions=["What next?"],
        )
        assert report.title == "Session Report: test-session"
        assert len(report.sections) == 6

    def test_session_report_render(self, vault: Path):
        gen = ReportGenerator(vault)
        report = gen.generate_session_report("test", summary="Hello")
        rendered = report.render()
        assert "## Summary" in rendered
        assert "Hello" in rendered

    def test_session_report_save(self, vault: Path):
        gen = ReportGenerator(vault)
        report = gen.generate_session_report("test", summary="Test")
        path = report.save(vault, "test-report.md")
        assert path.exists()
        content = path.read_text()
        assert "Test" in content

    def test_generate_daily_report(self, vault: Path):
        gen = ReportGenerator(vault)
        report = gen.generate_daily_report()
        assert report.report_type == "daily"
        assert len(report.sections) >= 1

    def test_generate_weekly_report(self, vault: Path):
        gen = ReportGenerator(vault)
        report = gen.generate_weekly_report("week1")
        assert report.report_type == "weekly"
        assert "week1" in report.title

    def test_report_table_empty(self):
        from sunny.agent.reports import render_report_table
        result = render_report_table([])
        assert result == "No data."

    def test_report_table_with_data(self):
        from sunny.agent.reports import render_report_table
        sections = [
            {"Section": "Facts", "Content": "F1, F2"},
            {"Section": "Tasks", "Content": "T1"},
        ]
        result = render_report_table(sections)
        assert "Facts" in result
        assert "Tasks" in result


# ── Briefing Loader tests ─────────────────────────────────────────


class TestBriefingLoader:
    """Test briefing context loading."""

    def test_load_empty_vault(self, vault: Path):
        loader = BriefingLoader(vault)
        ctx = loader.load()
        assert isinstance(ctx, BriefingContext)
        assert ctx.personal_facts == []
        assert ctx.pending_tasks == []
        assert ctx.knowledge_summary == "No knowledge base entries yet."

    def test_load_with_facts(self, vault: Path):
        facts_dir = vault / "memory" / "facts"
        facts_dir.mkdir(parents=True, exist_ok=True)
        fact1 = facts_dir / "fact1.md"
        if not fact1.exists():
            fact1.write_text("Keaton prefers Python.\n")
        fact2 = facts_dir / "fact2.md"
        if not fact2.exists():
            fact2.write_text("Sleep target: 7 hours.\n")

        loader = BriefingLoader(vault)
        ctx = loader.load()
        assert len(ctx.personal_facts) == 2

    def test_load_with_pending_tasks(self, vault: Path):
        pending_dir = vault / "tasks" / "pending"
        pending_dir.mkdir(parents=True)
        pending_dir.joinpath("task1.md").write_text("Build login page.\n")

        loader = BriefingLoader(vault)
        ctx = loader.load()
        assert len(ctx.pending_tasks) >= 1

    def test_load_with_deadlines(self, vault: Path):
        log_dir = vault / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "extraction.md"
        if not log_file.exists():
            log_file.write_text(
                "2024-01-01 deadline_mention: due next Friday\n"
            )

        loader = BriefingLoader(vault)
        ctx = loader.load()
        assert len(ctx.recent_deadlines) >= 1

    def test_briefing_to_prompt(self, vault: Path):
        loader = BriefingLoader(vault)
        ctx = loader.load()
        ctx.personal_facts = ["F1", "F2"]
        ctx.pending_tasks = ["T1"]
        ctx.recent_deadlines = ["Due Friday"]

        prompt = ctx.to_prompt()
        assert "Agent Briefing" in prompt
        assert "Personal Facts" in prompt
        assert "Pending Tasks" in prompt
        assert "Deadlines" in prompt
        assert "F1" in prompt
        assert "T1" in prompt

    def test_briefing_version(self, vault: Path):
        loader = BriefingLoader(vault)
        ctx = loader.load()
        assert ctx.briefing_version == "1.0"

    @pytest.mark.asyncio
    async def test_load_as_summary(self, vault: Path):
        loader = BriefingLoader(vault)
        result = await loader.load_as_summary()
        assert isinstance(result, dict)
        assert "personal_facts" in result
        assert "pending_tasks" in result
        assert "pending_decisions" in result
        assert "knowledge_summary" in result
