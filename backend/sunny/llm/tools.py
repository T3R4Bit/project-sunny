"""Chat tools — functions the LLM can call during chat.

These tools give the main assistant the ability to query the vault,
search, list sessions, and more on its own judgment.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from sunny.index.service import search as index_search

log = logging.getLogger(__name__)


class ChatToolRegistry:
    """Registry of tools available during chat."""

    def __init__(self) -> None:
        self._tools: dict[str, ChatTool] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register all built-in chat tools."""
        self.register(ChatTool(
            name="search",
            description="Search the vault index. Use when the user asks to find, look up, or search for anything.",
            parameters={
                "query": {"type": "string", "description": "Search query"},
                "project": {"type": "string", "nullable": True, "description": "Filter by project slug"},
                "kinds": {"type": "array", "items": {"type": "string"}, "description": "Filter by kind (session, source, context, file)"},
                "k": {"type": "integer", "default": 8, "description": "Number of results"},
            },
            handler=self._handle_search,
        ))

        self.register(ChatTool(
            name="list_sessions",
            description="List sessions in a project or Home. Use when asked to list, see, or show sessions.",
            parameters={
                "project": {"type": "string", "nullable": True, "description": "Project slug (None for Home)"},
                "since": {"type": "string", "nullable": True, "description": "ISO date filter"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tag filter"},
            },
            handler=self._handle_list_sessions,
        ))

        self.register(ChatTool(
            name="read_session",
            description="Read a full session transcript. Use when asked to read, view, or see a session.",
            parameters={
                "id": {"type": "string", "description": "Session slug/ID"},
                "project": {"type": "string", "nullable": True, "description": "Project slug (None for Home)"},
                "turn_range": {"type": "array", "items": {"type": "integer"}, "nullable": True, "description": "(start, end) turn range"},
            },
            handler=self._handle_read_session,
        ))

        self.register(ChatTool(
            name="read_context",
            description="Read a project's context.md file.",
            parameters={
                "project": {"type": "string", "description": "Project slug"},
            },
            handler=self._handle_read_context,
        ))

        self.register(ChatTool(
            name="list_projects",
            description="List all projects. Use when asked to see projects or project list.",
            parameters={},
            handler=self._handle_list_projects,
        ))

        self.register(ChatTool(
            name="web_search",
            description="Search the web for information. ONLY callable when the user explicitly asked to look something up.",
            parameters={
                "query": {"type": "string", "description": "Search query"},
            },
            handler=self._handle_web_search,
        ))

    def register(self, tool: ChatTool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ChatTool]:
        return self._tools.get(name)

    def get_tool_specs(self) -> list[dict]:
        """Return tool specs for the LLM system prompt."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a tool by name with arguments."""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}
        try:
            return await tool.handler(arguments)
        except Exception as e:
            log.error("Tool %s failed: %s", name, e)
            return {"error": str(e)}

    # ── Tool handlers ───────────────────────────────────────────────────

    async def _handle_search(self, args: dict) -> dict:
        query = args.get("query", "")
        if not query:
            return {"error": "Search requires a query"}

        results = index_search(
            query=query,
            project=args.get("project"),
            kinds=args.get("kinds"),
            k=args.get("k", 8),
        )
        return {
            "query": query,
            "results": [r.model_dump() for r in results],
            "count": len(results),
        }

    async def _handle_list_sessions(self, args: dict) -> dict:
        project = args.get("project")
        # Placeholder: in production, this queries the session store
        sessions = []  # Would come from projects.service.list_sessions()
        return {
            "project": project,
            "sessions": sessions,
            "count": len(sessions),
        }

    async def _handle_read_session(self, args: dict) -> dict:
        session_id = args.get("id", "")
        if not session_id:
            return {"error": "read_session requires an id"}

        # Try to read the session file directly
        project = args.get("project")
        if project:
            path = Path("vault") / "projects" / project / "sessions" / f"{session_id}.md"
        else:
            path = Path("vault") / "chats" / f"{session_id}.md"

        if path.exists():
            content = path.read_text(encoding="utf-8")
            return {"session": session_id, "content": content}
        return {"error": f"Session {session_id} not found"}

    async def _handle_read_context(self, args: dict) -> dict:
        project = args.get("project", "")
        if not project:
            return {"error": "read_context requires a project"}

        path = Path("vault") / "projects" / project / "context.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            return {"project": project, "content": content}
        return {"error": f"Context not found for project {project}"}

    async def _handle_list_projects(self, args: dict) -> dict:
        projects_path = Path("vault") / "projects"
        projects = []
        if projects_path.exists():
            for d in projects_path.iterdir():
                if d.is_dir() and (d / "project.md").exists():
                    projects.append({
                        "slug": d.name,
                        "path": str(d),
                    })
        return {
            "projects": projects,
            "count": len(projects),
        }

    async def _handle_web_search(self, args: dict) -> dict:
        """Web search — should only be called when user explicitly asked."""
        query = args.get("query", "")
        return {
            "web_search": True,
            "query": query,
            "note": "Web search not yet implemented in this stub",
        }


class ChatTool:
    """A single chat tool definition."""
    name: str
    description: str
    parameters: dict
    handler: Any  # Callable[[dict], Awaitable[dict]]

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Any,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
