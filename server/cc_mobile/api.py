from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


class _Manager(Protocol):
    async def current_state(self) -> dict[str, Any]: ...


def build_app(
    manager: _Manager,
    bus: Any,
    static_dir: Path | None,
    options: Any,
) -> FastAPI:
    app = FastAPI(title="cc-mobile", version="0.1.0")
    app.state.manager = manager
    app.state.bus = bus
    app.state.options = options

    @app.get("/api/state")
    async def get_state() -> dict[str, Any]:
        return await manager.current_state()

    if static_dir is not None and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
