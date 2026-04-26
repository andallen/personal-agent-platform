from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .event_bus import EventBus
from .state_store import StateStore


class _Tmux(Protocol):
    def session_exists(self) -> bool: ...
    def ensure_session(self, cwd: str | None = None) -> None: ...
    def is_claude_alive(self) -> bool: ...
    def start_claude(self, cwd: str, mode: str = "default", resume_id: str | None = None) -> None: ...
    def kill_claude(self) -> None: ...
    def send_text(self, text: str) -> None: ...
    def send_keys(self, *keys: str) -> None: ...
    def capture_pane(self, lines: int = 200) -> str: ...


class SessionManager:
    def __init__(
        self,
        tmux: _Tmux,
        state: StateStore,
        bus: EventBus,
        projects_root: Path,
    ) -> None:
        self.tmux = tmux
        self.state = state
        self.bus = bus
        self.projects_root = projects_root

    async def boot(self) -> None:
        self.tmux.ensure_session()
        if not self.tmux.is_claude_alive():
            s = self.state.get()
            self.tmux.start_claude(cwd=s["last_cwd"], mode=s["last_mode"])
            await self.bus.publish({"kind": "claude_started"})
        await self._publish_state()

    async def send_user_message(self, text: str) -> None:
        self.tmux.send_text(text)
        self.tmux.send_keys("Enter")

    async def interrupt(self) -> None:
        self.tmux.send_keys("Escape")

    async def _publish_state(self) -> None:
        s = self.state.get()
        await self.bus.publish(
            {
                "kind": "state",
                "state": {
                    "cwd": s["last_cwd"],
                    "mode": s["last_mode"],
                    "model": s["last_model"],
                    "effort": s["last_effort"],
                    "claude_alive": self.tmux.is_claude_alive(),
                },
            }
        )
