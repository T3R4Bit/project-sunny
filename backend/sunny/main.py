"""Sunny V2 — application factory, lifespan, loop registry, health endpoint."""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sunny.config import get_settings, Settings
from sunny.db import init_db
from sunny.admin import router as admin_router
from sunny.dashboard import router as dashboard_router
from sunny import brief
from sunny.integrations import router as integrations_router
from sunny.auth import install_auth_middleware, router as auth_router
from sunny.projects.router import router as projects_router
from sunny.watcher import start_watcher, stop_watcher
from sunny.index.router import router as index_router
from sunny.index.watcher import start_index_watcher, stop_index_watcher
from sunny.llm.router import router as llm_router
from sunny.research.router import router as research_router
from sunny.tools.router import router as agent_router

log = logging.getLogger("sunny")

# --- Loop registry ---
_loop_registry: dict[str, asyncio.AbstractEventLoop] = {}
_loop_started: dict[str, bool] = {}


def register_loop(name: str, loop: asyncio.AbstractEventLoop) -> None:
    """Register a loop by name. Double-start guard: skips if already running."""
    if name in _loop_registry and _loop_started.get(name):
        log.warning("Loop '%s' already started; skipping duplicate registration", name)
        return
    _loop_registry[name] = loop
    _loop_started[name] = False


def get_loop(name: str) -> asyncio.AbstractEventLoop:
    """Get a registered loop by name, or the event loop if none registered."""
    return _loop_registry.get(name, asyncio.get_event_loop())


def mark_loop_started(name: str) -> None:
    """Mark a loop as started (after its background task begins)."""
    _loop_started[name] = True


def get_all_loops() -> dict[str, asyncio.AbstractEventLoop]:
    """Return a copy of the loop registry."""
    return dict(_loop_registry)


# --- App factory ---


def create_app() -> FastAPI:
    """Create the FastAPI application with lifespan and routes."""
    app = FastAPI(
        title="Sunny",
        description="Personal AI assistant",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middleware: log every request
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        method = request.method
        path = request.url.path
        response = await call_next(request)
        log.info("%s %s -> %d", method, path, response.status_code)
        return response

    # Every non-public route needs a session
    install_auth_middleware(app)

    # Health endpoint
    @app.get("/health")
    async def health() -> dict[str, Any]:
        settings = get_settings()
        return {
            "status": "ok",
            "version": "0.1.0",
            "vault_path": str(settings.vault_path),
            "db_path": str(settings.db_path),
        }

    # Catch-all for unexpected errors
    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled exception at %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "internal server error"},
        )

    # Include auth routes
    app.include_router(auth_router)

    # Include project/session routes
    app.include_router(projects_router)

    # Include index/search routes
    app.include_router(index_router)

    # Include chat/LLM routes
    app.include_router(llm_router)

    # Include research routes
    app.include_router(research_router)

    # Include agent tools routes
    app.include_router(agent_router)

    # Include admin status
    app.include_router(admin_router)
    app.include_router(dashboard_router)
    app.include_router(integrations_router)
    app.include_router(brief.router)

    mount_frontend(app, get_settings().frontend_dir)

    return app


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built PWA: index.html at /, hashed bundles under /assets, root files by name."""
    index = dist / "index.html"
    if not index.is_file():
        log.info("No frontend build at %s; serving API only", dist)
        return

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def spa_index() -> FileResponse:
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    for f in dist.iterdir():
        if f.is_file() and f.name != "index.html":
            app.add_api_route(f"/{f.name}", _static_file(f), include_in_schema=False)


def _static_file(path: Path):
    async def serve() -> FileResponse:
        return FileResponse(path, headers={"Cache-Control": "no-cache"} if path.name == "sw.js" else None)
    return serve


# --- Lifespan ---


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: init logging, DB, then start background loops."""
    setup_logging()

    log.info("Sunny V2 starting up")

    # Initialize database
    settings = get_settings()
    init_db(settings.db_path)
    log.info("Database initialized at %s", settings.db_path)

    # Register the main event loop
    main_loop = asyncio.get_event_loop()
    register_loop("main", main_loop)
    mark_loop_started("main")

    log.info("Startup complete")

    # Start the vault file watcher (runs in its own thread)
    start_watcher(settings.vault_path)

    # Start the index watcher
    await start_index_watcher()

    # Start the agent loop
    from sunny.agent.loop import start_agent_loop, stop_agent_loop, AgentState
    await start_agent_loop(AgentState.AWAKE)

    # Daily brief scheduler
    brief.start_scheduler()

    yield

    # Shutdown: stop watchers and background loops
    log.info("Sunny V2 shutting down")
    stop_watcher()
    await stop_index_watcher()
    await stop_agent_loop()
    await brief.stop_scheduler()

    for name, loop in _loop_registry.items():
        if name == "main":
            continue
        if not loop.is_closed():
            # Cancel all tasks in the loop
            tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            try:
                loop.stop()
            except RuntimeError:
                pass

    log.info("Shutdown complete")


# --- Logging ---


def setup_logging() -> None:
    """Configure root and sunny loggers."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # One handler on the root logger; "sunny.*" loggers propagate to it
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(h, "_sunny", False) for h in root.handlers):
        handler._sunny = True
        root.addHandler(handler)

    logging.getLogger("sunny").setLevel(level)
