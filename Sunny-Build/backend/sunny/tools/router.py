"""Agent tools router — API for agent loop, task queue, and tool management."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from sunny.agent.loop import AgentState, get_agent_loop, start_agent_loop, stop_agent_loop
from sunny.config import get_settings

router = APIRouter(tags=["agent"])


@router.get("/agent/status")
async def get_agent_status() -> dict:
    """Get agent loop status."""
    loop = get_agent_loop()
    return loop.get_status()


@router.post("/agent/start")
async def start_agent(state: dict = {}) -> dict:
    """Start the agent loop."""
    agent_state = AgentState(state.get("state", "awake"))
    loop = get_agent_loop()
    await loop.start(agent_state)
    return loop.get_status()


@router.post("/agent/stop")
async def stop_agent() -> dict:
    """Stop the agent loop."""
    loop = get_agent_loop()
    await loop.stop()
    return loop.get_status()


@router.post("/agent/state")
async def set_agent_state(body: dict) -> dict:
    """Change agent state."""
    valid_states = ["awake", "cant_sleep", "sleeping", "off"]
    new_state_str = body.get("state", "").lower()
    if new_state_str not in valid_states:
        raise HTTPException(status_code=400, detail=f"Invalid state. Must be one of: {valid_states}")
    new_state = AgentState(new_state_str)
    loop = get_agent_loop()
    loop.set_state(new_state)
    return loop.get_status()


@router.get("/agent/tasks")
async def list_tasks() -> dict:
    """List all tasks from the queue."""
    loop = get_agent_loop()
    return {
        "pending": loop._task_queue.count_pending(),
        "state": loop.state.value,
    }


@router.post("/agent/tasks")
async def create_task(body: dict) -> dict:
    """Add a task to the queue."""
    description = body.get("description", "")
    if not description:
        raise HTTPException(status_code=400, detail="description is required")

    priority = body.get("priority", 2)
    agent = body.get("agent", "default")
    source = body.get("source", "user")

    settings = get_settings()
    vault = Path(settings.vault_path)

    loop = get_agent_loop()
    task_id = loop.add_task(
        description=description,
        priority=priority,
        agent=agent,
        source=source,
        vault=vault,
    )

    return {"task_id": task_id, "status": "queued"}


@router.post("/agent/synthesize")
async def synthesize_tool(body: dict) -> dict:
    """Synthesize a new tool."""
    name = body.get("name", "")
    description = body.get("description", "")
    code = body.get("code", "")
    parameters = body.get("parameters", {})
    creator = body.get("creator", "agent")

    if not name or not code:
        raise HTTPException(status_code=400, detail="name and code are required")

    # Validate name: intention-driven, no IDs or dates
    import re
    if re.search(r"\d{4,}|id_|_id|_[0-9]{4}", name):
        raise HTTPException(
            status_code=400,
            detail="Tool names must be intention-driven (no IDs or dates)",
        )

    # Update tool registry vault path from settings
    settings = get_settings()
    vault = Path(settings.vault_path)
    loop = get_agent_loop()
    loop._tool_registry._vault = vault

    tool = loop._tool_registry.synthesize(
        name=name,
        description=description,
        parameters=parameters,
        code=code,
        creator=creator,
    )

    return {
        "tool": {
            "name": tool.name,
            "description": tool.description,
            "version": tool.version,
            "status": tool.status,
        }
    }


@router.get("/agent/tools")
async def list_tools() -> dict:
    """List all tools (active, broken, disabled)."""
    loop = get_agent_loop()
    active = loop._tool_registry.get_active_tools()
    all_tools = loop._tool_registry._tools

    return {
        "active": [t.name for t in active],
        "all": [
            {
                "name": t.name,
                "status": t.status,
                "success": t.success,
                "failure": t.failure,
            }
            for t in all_tools.values()
        ],
    }
