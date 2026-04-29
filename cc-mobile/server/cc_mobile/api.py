from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from .jsonl_tailer import locate_active_jsonl, parse_line


class _Manager(Protocol):
    async def current_state(self) -> dict[str, Any]: ...


def build_app(
    manager: _Manager,
    bus: Any,
    static_dir: Path | None,
    options: Any,
    projects_root: Path,
) -> FastAPI:
    app = FastAPI(title="cc-mobile", version="0.1.0")
    app.state.manager = manager
    app.state.bus = bus
    app.state.options = options

    def _history_events() -> list[dict[str, Any]]:
        target = locate_active_jsonl(projects_root)
        if target is None:
            return []
        events: list[dict[str, Any]] = []
        with target.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                for ev in parse_line(line):
                    events.append({"kind": "chat_event", "event": asdict(ev)})
        return events

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

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        sub = bus.subscribe()

        async def _ping() -> None:
            while True:
                await asyncio.sleep(15)
                await websocket.send_json({"kind": "ping"})

        ping_task = asyncio.create_task(_ping())
        try:
            await websocket.send_json(
                {"kind": "state", "state": await manager.current_state()}
            )
            for ev in _history_events():
                await websocket.send_json(ev)
            while True:
                event = await sub.get()
                await websocket.send_json(event)
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            ping_task.cancel()
            bus.unsubscribe(sub)

    if static_dir is not None and static_dir.is_dir():
        @app.middleware("http")
        async def _no_cache_html(request: Request, call_next):
            response: Response = await call_next(request)
            path = request.url.path
            if path == "/" or path.endswith(".html"):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            elif path.startswith("/assets/"):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
