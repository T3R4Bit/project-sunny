"""Tool registry — manages built-in and synthesized agent tools."""

from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from sunny.frontmatter import dump, load
from sunny.vault.io import read_file, atomic_write

log = logging.getLogger(__name__)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema for inputs
    code: str  # Python code to execute
    version: str = "1.0.0"
    created: str = ""
    creator: str = "system"  # system | user | agent
    success: int = 0
    failure: int = 0
    status: str = "active"  # active | broken | disabled


class ToolRegistry:
    """Registry for agent tools (built-in + synthesized)."""

    def __init__(self, vault: Optional[Path] = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._vault = vault or Path("vault")
        self._register_builtins()
        self._load_synthesized_tools()

    def _register_builtins(self) -> None:
        """Register built-in tools."""
        builtins = {
            "fetch_calendar": Tool(
                name="fetch_calendar",
                description="Fetch upcoming calendar events from CalDAV.",
                parameters={"count": {"type": "integer", "default": 7}},
                code="import requests\nresp = requests.get(calenda...",
            ),
            "create_calendar_event": Tool(
                name="create_calendar_event",
                description="Create a new calendar event.",
                parameters={"title": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}},
                code="import requests\nresp = requests.post(event_url, json=...)",
            ),
            "sync_nextcloud_to_google": Tool(
                name="sync_nextcloud_to_google",
                description="Sync calendar events from Nextcloud to Google Calendar.",
                parameters={},
                code="# Sync Nextcloud to Google\ndef sync(...):\n...",
            ),
            "log_to_vault": Tool(
                name="log_to_vault",
                description="Append a log entry to the vault.",
                parameters={"entry": {"type": "string"}, "kind": {"type": "string", "default": "agent"}},
                code="from pathlib import Path\np = vault / 'log' / f'{kind}.md'",
            ),
            "notify": Tool(
                name="notify",
                description="Send a notification at the specified tier.",
                parameters={"message": {"type": "string"}, "tier": {"type": "string", "default": "SILENT"}},
                code="from sunny.tools.notify import notify\ndef notify(message, tier):\n...",
            ),
            "search": Tool(
                name="search",
                description="Search the vault index.",
                parameters={"query": {"type": "string"}, "k": {"type": "integer", "default": 8}},
                code="from sunny.index.service import search\ndef search(query, k=8):\n...",
            ),
            "create_task": Tool(
                name="create_task",
                description="Create a new task in the agent task queue.",
                parameters={"description": {"type": "string"}, "priority": {"type": "integer", "default": 2}},
                code="from sunny.tools.task_queue import TaskQueue\ndef create_task(description, priority=2):\n...",
            ),
            "read_session": Tool(
                name="read_session",
                description="Read a session transcript from the vault.",
                parameters={"id": {"type": "string"}, "project": {"type": "string", "nullable": True}},
                code="from pathlib import Path\ndef read_session(id, project=None):\n...",
            ),
        }
        for tool in builtins.values():
            tool.created = tool.created or ""
            self._tools[tool.name] = tool

    def _load_synthesized_tools(self) -> None:
        """Load synthesized tools from tools/ directory."""
        tools_dir = self._vault / "tools"
        if not tools_dir.exists():
            return
        for f in tools_dir.glob("*.py"):
            name = f.stem
            registry_path = self._vault / "tools" / "registry.yaml"
            meta_content = ""
            if registry_path.exists():
                meta_content = read_file(registry_path) or ""
                post = load(meta_content)
                tools_meta = dict(post.metadata)
                tool_meta = tools_meta.get(name, {})
                self._tools[name] = Tool(
                    name=name,
                    description=tool_meta.get("description", name),
                    parameters=tool_meta.get("parameters", {}),
                    code=f.read_text(),
                    version=tool_meta.get("version", "1.0.0"),
                    created=tool_meta.get("created", ""),
                    creator=tool_meta.get("creator", "agent"),
                    success=int(tool_meta.get("success", 0)),
                    failure=int(tool_meta.get("failure", 0)),
                    status=tool_meta.get("status", "active"),
                )

    def register(self, tool: Tool) -> None:
        """Register a tool (used for synthesized tools)."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def get_active_tools(self) -> list[Tool]:
        """Get all active tools."""
        return [t for t in self._tools.values() if t.status == "active"]

    def mark_failure(self, name: str) -> None:
        """Mark a tool failure. 3 failures → broken."""
        tool = self._tools.get(name)
        if tool:
            tool.failure += 1
            if tool.failure >= 3:
                tool.status = "broken"
                log.warning("Tool %s marked broken after %d failures", name, tool.failure)

    def mark_success(self, name: str) -> None:
        """Mark a tool success."""
        tool = self._tools.get(name)
        if tool:
            tool.success += 1
            if tool.status == "broken":
                tool.status = "active"
                log.info("Tool %s reactivated after %d consecutive successes", name, tool.failure)

    def synthesize(self, name: str, description: str, parameters: dict,
                   code: str, creator: str = "agent") -> Tool:
        """Synthesize a new tool. Writes to tools/<name>.py and registry.yaml."""
        tool = Tool(
            name=name,
            description=description,
            parameters=parameters,
            code=code,
            creator=creator,
        )
        self._tools[name] = tool

        # Write tool file
        tools_dir = self._vault / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        (tools_dir / f"{name}.py").write_text(code)

        # Update registry
        self._save_registry()

        log.info("Synthesized tool: %s", name)
        return tool

    def _save_registry(self) -> None:
        """Save the tool registry to registry.yaml."""
        registry_path = self._vault / "tools" / "registry.yaml"
        meta = {}
        for tool in self._tools.values():
            meta[tool.name] = {
                "version": tool.version,
                "created": tool.created,
                "creator": tool.creator,
                "success": tool.success,
                "failure": tool.failure,
                "status": tool.status,
                "description": tool.description,
                "parameters": tool.parameters,
            }
        post = load("")
        post.metadata.update(meta)
        atomic_write(registry_path, dump(post))


# Built-in tool function registry — maps tool name -> callable
TOOL_HANDLERS: dict[str, Callable[..., Any]] = {}


def register_tool_handler(name: str, handler: Callable[..., Any]) -> None:
    """Register a handler function for a tool."""
    TOOL_HANDLERS[name] = handler


def get_tool_handler(name: str) -> Optional[Callable[..., Any]]:
    """Get a tool handler by name."""
    return TOOL_HANDLERS.get(name)
