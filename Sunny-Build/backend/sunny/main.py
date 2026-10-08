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
from fastapi.responses import JSONResponse

from sunny.config import get_settings, Settings
from sunny.db import init_db
from sunny.auth import router as auth_router
from sunny.projects.router import router as projects_router
from sunny.watcher import start_watcher, stop_watcher

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

    return app


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

    # Start the vault file watcher
    settings = get_settings()
    watcher_task = await start_watcher(settings.vault_path)

    yield

    # Shutdown: stop watcher and background loops
    log.info("Sunny V2 shutting down")
    stop_watcher()

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

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    sunny = logging.getLogger("sunny")
    sunny.setLevel(level)

    # Avoid duplicate handlers on re-init
    if not sunny.handlers:
        sunny.addHandler(handler)
