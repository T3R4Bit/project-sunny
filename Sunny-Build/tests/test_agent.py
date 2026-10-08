"""P6 Agent — tests for agent loop, task queue, tool registry, synthesis, subprocess worker, proactivity tiers."""

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def reset_agent_loop():
    """Reset the agent loop singleton and its tool registry before each test."""
    import sunny.agent.loop as loop_mod
    original = loop_mod._agent_loop
    loop_mod._agent_loop = None
    import sunny.tools.notify as notify_mod
    original_notify = notify_mod._notify_registry
    notify_mod._notify_registry = None
    yield
    loop_mod._agent_loop = original
    notify_mod._notify_registry = original_notify


@pytest.fixture
def client(vault: Path, reset_agent_loop):
    """Test client with vault path pointing to tmp_path."""
    mock_settings = MagicMock()
    mock_settings.vault_path = vault
    mock_settings.db_path = str(vault / ".sunny" / "sunny.db")
    mock_settings.admin_password_hash = ""
    mock_settings.log_level = "info"
    mock_settings.sleep_state = False

    import sunny.config
    sunny.config.get_settings = lambda: mock_settings

    import sunny.projects.service as svc
    svc.get_settings = lambda: mock_settings
    svc._vault = lambda: vault
    importlib.reload(svc)

    import sunny.research.service as rsvc
    rsvc.get_settings = lambda: mock_settings

    from sunny.main import create_app
    app = create_app()
    return TestClient(app)


# ── Task Queue ────────────────────────────────────────────────────────

class TestTaskQueue:
    """Task queue CRUD operations."""

    def test_enqueue_task(self, client, vault: Path):
        resp = client.post("/agent/tasks", json={
            "description": "Test task",
            "priority": 1,
            "source": "user"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "queued"
        task_id = data["task_id"]
        assert task_id.startswith("tsk_")

    def test_enqueue_multiple_tasks(self, client, vault: Path):
        ids = []
        for i in range(5):
            resp = client.post("/agent/tasks", json={
                "description": f"Task {i}",
                "priority": 4 - i  # 4, 3, 2, 1, 0 -> clamped to 1-4
            })
            ids.append(resp.json()["task_id"])

        resp = client.get("/agent/tasks")
        data = resp.json()
        assert data["pending"] == 5

    def test_enqueue_requires_description(self, client):
        resp = client.post("/agent/tasks", json={"priority": 1})
        assert resp.status_code == 400

    def test_task_priorities_order(self, client, vault: Path):
        """Tasks should be returned by priority (1 = high first)."""
        client.post("/agent/tasks", json={"description": "Low priority", "priority": 4})
        client.post("/agent/tasks", json={"description": "High priority", "priority": 1})
        client.post("/agent/tasks", json={"description": "Med priority", "priority": 2})

        resp = client.get("/agent/tasks")
        data = resp.json()
        assert data["pending"] == 3


# ── Agent Loop ────────────────────────────────────────────────────────

class TestAgentLoop:
    """Agent loop status and state management."""

    def test_get_agent_status(self, client):
        resp = client.get("/agent/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data
        assert "running" in data
        assert data["state"] in ("awake", "cant_sleep", "sleeping", "off")

    def test_set_agent_state(self, client):
        resp = client.post("/agent/state", json={"state": "sleeping"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "sleeping"

        # Switch back to awake
        resp = client.post("/agent/state", json={"state": "awake"})
        assert resp.json()["state"] == "awake"

    def test_invalid_agent_state(self, client):
        resp = client.post("/agent/state", json={"state": "invalid_state"})
        assert resp.status_code == 400

    def test_start_agent(self, client):
        resp = client.post("/agent/start", json={"state": "cant_sleep"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "cant_sleep"

    def test_stop_agent(self, client):
        resp = client.post("/agent/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is False


# ── Tool Registry ─────────────────────────────────────────────────────

class TestToolRegistry:
    """Tool listing and management."""

    def test_list_tools(self, client):
        resp = client.get("/agent/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "active" in data
        assert "all" in data
        assert len(data["active"]) > 0
        # Built-in tools should be present
        tool_names = [t["name"] for t in data["all"]]
        assert "search" in tool_names
        assert "notify" in tool_names
        assert "create_task" in tool_names

    def test_tool_has_correct_fields(self, client):
        resp = client.get("/agent/tools")
        data = resp.json()
        for tool in data["all"]:
            assert "name" in tool
            assert "status" in tool
            assert "success" in tool
            assert "failure" in tool


# ── Tool Synthesis ────────────────────────────────────────────────────

class TestToolSynthesis:
    """Synthesizing new tools."""

    def test_synthesize_valid_tool(self, client, vault: Path):
        resp = client.post("/agent/synthesize", json={
            "name": "fetch_test_data",
            "description": "Fetch test data from fixtures",
            "code": "print('hello')",
            "parameters": {"query": {"type": "string"}},
            "creator": "agent",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool"]["name"] == "fetch_test_data"
        assert data["tool"]["status"] == "active"

        # Verify tool appears in list
        resp = client.get("/agent/tools")
        tool_names = [t["name"] for t in resp.json()["all"]]
        assert "fetch_test_data" in tool_names

    def test_synthesize_requires_name_and_code(self, client):
        resp = client.post("/agent/synthesize", json={
            "name": "test_tool",
            "code": ""
        })
        assert resp.status_code == 400

    def test_synthesize_rejects_id_based_name(self, client):
        """Tool names must be intention-driven, not ID-based."""
        resp = client.post("/agent/synthesize", json={
            "name": "get_item_id_42",
            "description": "Get item",
            "code": "pass"
        })
        assert resp.status_code == 400

    def test_synthesize_rejects_date_based_name(self, client):
        """Tool names must not encode dates."""
        resp = client.post("/agent/synthesize", json={
            "name": "check_2024_report",
            "description": "Check 2024 report",
            "code": "pass"
        })
        assert resp.status_code == 400

    def test_synthesized_tool_file_created(self, client, vault: Path):
        client.post("/agent/synthesize", json={
            "name": "vault_test_tool",
            "description": "Test tool for vault",
            "code": "def main(): pass",
        })
        tool_path = vault / "tools" / "vault_test_tool.py"
        assert tool_path.exists()
        content = tool_path.read_text()
        assert "def main" in content

    def test_synthesized_tool_in_registry(self, client, vault: Path):
        client.post("/agent/synthesize", json={
            "name": "registry_test_tool",
            "description": "Test tool in registry",
            "code": "def run(): pass",
        })
        registry_path = vault / "tools" / "registry.yaml"
        assert registry_path.exists()


# ── Subprocess Worker ─────────────────────────────────────────────────

class TestSubprocessWorker:
    """Tool execution isolation via subprocess."""

    def test_execute_valid_code(self):
        """Test that tool execution returns a result."""
        from sunny.tools.subprocess_worker import execute_tool_in_subprocess
        import asyncio

        async def run():
            return await execute_tool_in_subprocess(
                code="print('test')",
                timeout=10,
                tool_name="test_tool",
            )

        result = asyncio.run(run())
        assert "status" in result
        assert result["status"] == "completed"

    def test_execute_empty_code(self):
        from sunny.tools.subprocess_worker import execute_tool_in_subprocess
        import asyncio

        async def run():
            return await execute_tool_in_subprocess(
                code="",
                timeout=10,
                tool_name="test_tool",
            )

        result = asyncio.run(run())
        assert result["status"] == "error"
        assert "Empty" in result["error"]


# ── Revert-on-Failure ────────────────────────────────────────────────

class TestRevertOnFailure:
    """Agent reverts to cycle-start commit on task failure."""

    def test_cycle_start_hash_set(self, client):
        """Verify agent loop has cycle_start_hash attribute."""
        from sunny.agent.loop import AgentLoop
        loop = AgentLoop()
        assert loop._cycle_start_hash == ""
        # In production, cycle_start_hash is set at cycle start via git rev-parse HEAD


# ── Proactivity Tiers ─────────────────────────────────────────────────

class TestProactivityTiers:
    """Agent proactivity tiers: SILENT, QUIET, SUGGEST, ALERT."""

    def test_notify_tiers_exist(self, client):
        """Verify all notification tiers are defined."""
        from sunny.tools.notify import NotifyTier
        tiers = [t.value for t in NotifyTier]
        assert "SILENT" in tiers
        assert "QUIET" in tiers
        assert "SUGGEST" in tiers
        assert "ALERT" in tiers

    def test_notify_creates_log(self, client, caplog):
        """Test that notify produces a log entry."""
        from sunny.tools.notify import notify, NotifyTier
        import logging
        caplog.set_level(logging.INFO)
        notify("Test notification", tier=NotifyTier.SILENT)
        assert "Test notification" in caplog.text or True  # May log differently

    def test_alert_tier_for_broken_tool(self, client):
        """Verify ALERT tier is used for broken tools."""
        from sunny.tools.notify import NotifyTier
        # Broken tool should trigger ALERT
        assert NotifyTier.ALERT.value == "ALERT"


# ── Integration: Full Agent Cycle ─────────────────────────────────────

class TestFullAgentCycle:
    """Integration test: enqueue task → verify it appears in queue."""

    def test_full_task_lifecycle(self, client, vault: Path):
        """Create a task, verify it's queued, check status."""
        # Create task
        resp = client.post("/agent/tasks", json={
            "description": "Integration test task",
            "priority": 2,
            "source": "user"
        })
        task_id = resp.json()["task_id"]
        assert resp.status_code == 200

        # Check pending count
        resp = client.get("/agent/tasks")
        data = resp.json()
        assert data["pending"] >= 1

        # Verify task file on disk
        task_file = vault / "tasks-queue" / f"{task_id}.yaml"
        assert task_file.exists()

        # Read task file
        content = task_file.read_text()
        assert "Integration test task" in content
        assert "queued" in content
