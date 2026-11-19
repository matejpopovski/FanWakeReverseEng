"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_core, routes_engine, routes_integration
from app.config import get_settings
from app.db import session_scope
from app.seed import seed_defaults, seed_mock
from app.services import sync

log = logging.getLogger("wakeful")
STATIC = Path(__file__).parent / "static"


def bootstrap() -> None:
    """Migrate, create defaults; in mock mode seed synthetic data and run an initial sync."""
    from app.migrate import upgrade

    upgrade()
    with session_scope() as db:
        seed_defaults(db)
        if get_settings().fanvue_mode == "mock":
            seed_mock(db)
    if get_settings().fanvue_mode == "mock":
        with session_scope() as db:
            sync.sync(db, refresh_all_insights=False)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    if s.app_env != "test":
        bootstrap()
    stop = asyncio.Event()
    task = None
    if s.worker_enabled and s.app_env != "test":
        from app.worker import run_forever

        task = asyncio.create_task(run_forever(stop))
    yield
    stop.set()
    if task:
        await task


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Wakeful", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs" if s.app_env != "prod" else None, openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    for r in (routes_core.public, routes_core.router, routes_engine.router, routes_integration.router,
              routes_integration.public):
        app.include_router(r)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        log.exception("unhandled error")
        return JSONResponse({"detail": "Internal error"}, status_code=500)

    if STATIC.exists():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            f = STATIC / path
            if path and f.is_file() and STATIC in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(STATIC / "index.html")

    return app


app = create_app()
