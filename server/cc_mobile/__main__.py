from __future__ import annotations

import asyncio
import os
from pathlib import Path

import uvicorn

from .api import build_app
from .event_bus import EventBus
from .jsonl_tailer import JSONLTailer
from .options_discovery import OptionsDiscovery
from .pane_watcher import PaneWatcher
from .detectors import PermissionPromptDetector, PlanApprovalDetector, StatusLineDetector
from .session_manager import SessionManager
from .state_store import StateStore
from .tmux_controller import TmuxController

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
STATE_PATH = Path.home() / ".config" / "cc-mobile" / "state.json"
STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


def main() -> None:
    bus = EventBus()
    tmux = TmuxController(session_name="claude")
    state = StateStore(STATE_PATH)
    options = OptionsDiscovery()
    # Tailer points at the projects root and recurses; the most-recently-
    # modified jsonl in the tree is always the active session, so project
    # switches are followed automatically without any re-target wiring.
    # SessionManager also calls tailer.rotate_to() on resume so the UI
    # updates immediately rather than waiting for an mtime race.
    tailer = JSONLTailer(directory=PROJECTS_ROOT, bus=bus)
    manager = SessionManager(
        tmux=tmux, state=state, bus=bus, projects_root=PROJECTS_ROOT, tailer=tailer
    )
    detectors = [PermissionPromptDetector(), PlanApprovalDetector()]
    status_detector = StatusLineDetector(models=options.get_models())
    pane_watcher = PaneWatcher(
        tmux=tmux,
        bus=bus,
        detectors=detectors,
        status_detector=status_detector,
        on_status=manager.apply_terminal_state,
    )

    app = build_app(
        manager=manager,
        bus=bus,
        static_dir=STATIC_DIR,
        options=options,
        projects_root=PROJECTS_ROOT,
    )

    @app.on_event("startup")
    async def _startup():
        await manager.boot()
        await tailer.start()
        await pane_watcher.start()

    @app.on_event("shutdown")
    async def _shutdown():
        await tailer.stop()
        await pane_watcher.stop()

    port = int(os.environ.get("CC_MOBILE_PORT", "8767"))
    host = os.environ.get("CC_MOBILE_HOST", "0.0.0.0")
    # CC_MOBILE_TLS=off lets a fronting reverse proxy (Caddy) own TLS
    # without us also terminating it on the same port.
    tls_mode = os.environ.get("CC_MOBILE_TLS", "auto").lower()
    certs_dir = Path(__file__).resolve().parent.parent.parent / "certs"
    cert = certs_dir / "server.crt"
    key = certs_dir / "server.key"
    ssl_kwargs = (
        {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
        if tls_mode != "off" and cert.exists() and key.exists()
        else {}
    )
    uvicorn.run(app, host=host, port=port, log_level="info", **ssl_kwargs)


if __name__ == "__main__":
    main()
