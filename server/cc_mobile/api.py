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
    async def get_state():
        return await manager.current_state()

    @app.post("/api/send")
    async def post_send(payload: dict):
        await manager.send_user_message(payload["text"])
        return {"ok": True}

    @app.post("/api/interrupt")
    async def post_interrupt():
        await manager.interrupt()
        return {"ok": True}

    @app.post("/api/mode")
    async def post_mode(payload: dict):
        await manager.set_mode(payload["value"])
        return {"ok": True}

    @app.post("/api/model")
    async def post_model(payload: dict):
        await manager.set_model(payload["value"])
        return {"ok": True}

    @app.post("/api/effort")
    async def post_effort(payload: dict):
        await manager.set_effort(payload["value"])
        return {"ok": True}

    @app.post("/api/clear")
    async def post_clear():
        await manager.clear()
        return {"ok": True}

    @app.post("/api/compact")
    async def post_compact():
        await manager.compact()
        return {"ok": True}

    @app.post("/api/resume")
    async def post_resume(payload: dict):
        await manager.resume(payload["session_id"])
        return {"ok": True}

    @app.post("/api/project")
    async def post_project(payload: dict):
        await manager.switch_project(payload["cwd"])
        return {"ok": True}

    @app.post("/api/permission")
    async def post_permission(payload: dict):
        await manager.decide_permission(payload["id"], payload["decision"])
        return {"ok": True}

    @app.get("/api/projects")
    async def get_projects():
        return await manager.list_recent_projects()

    @app.get("/api/sessions")
    async def get_sessions(cwd: str):
        return await manager.list_recent_sessions(cwd)

    @app.get("/api/options")
    async def get_options():
        return {
            "models": options.get_models(),
            "efforts": options.get_efforts(),
            "modes": options.get_modes(),
        }

    @app.get("/api/slash-commands")
    async def get_slash_commands():
        return options.get_slash_commands()

    if static_dir is not None and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
