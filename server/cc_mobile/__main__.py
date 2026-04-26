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
from .detectors import PermissionPromptDetector, PlanApprovalDetector
from .session_manager import SessionManager
from .state_store import StateStore
from .tmux_controller import TmuxController

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
STATE_PATH = Path.home() / ".config" / "cc-mobile" / "state.json"
STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


def main() -> None:
    bus = EventBus()
    tmux = TmuxController(session_name="claude-mobile")
    state = StateStore(STATE_PATH)
    options = OptionsDiscovery()
    manager = SessionManager(
        tmux=tmux, state=state, bus=bus, projects_root=PROJECTS_ROOT
    )
    detectors = [PermissionPromptDetector(), PlanApprovalDetector()]
    pane_watcher = PaneWatcher(tmux=tmux, bus=bus, detectors=detectors)
    # Tailer points at the projects root and recurses; the most-recently-
    # modified jsonl in the tree is always the active session, so project
    # switches are followed automatically without any re-target wiring.
    tailer = JSONLTailer(directory=PROJECTS_ROOT, bus=bus)

    app = build_app(
        manager=manager, bus=bus, static_dir=STATIC_DIR, options=options
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
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
