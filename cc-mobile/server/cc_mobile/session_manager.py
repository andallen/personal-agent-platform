from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

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

    async def set_model(self, model_id: str) -> None:
        self.tmux.send_text(f"/model {model_id}")
        self.tmux.send_keys("Enter")
        self.state.update(last_model=model_id)
        await self._publish_state()

    async def set_effort(self, effort: str) -> None:
        self.tmux.send_text(f"/effort {effort}")
        self.tmux.send_keys("Enter")
        self.state.update(last_effort=effort)
        await self._publish_state()

    async def set_mode(self, mode: str) -> None:
        """Switch CC's permission mode at runtime.

        Bypass requires the --dangerously-skip-permissions launch flag, so
        transitions to/from bypass respawn claude. The other three modes
        (default, accept_edits, plan) form a UI cycle reachable via BTab
        (Shift+Tab); cycle order is default → accept_edits → plan → default.
        """
        current = self.state.get()["last_mode"]
        if mode == current:
            return

        if mode == "bypass":
            # Non-bypass → bypass: respawn with the bypass flag.
            self.tmux.kill_claude()
            self.tmux.start_claude(cwd=self.state.get()["last_cwd"], mode="bypass")
            await self.bus.publish({"kind": "claude_started"})
        elif current == "bypass":
            # Bypass → non-bypass: respawn without the flag (lands in default),
            # then BTab to target if not default.
            self.tmux.kill_claude()
            self.tmux.start_claude(cwd=self.state.get()["last_cwd"], mode="default")
            await self.bus.publish({"kind": "claude_started"})
            if mode != "default":
                cycle = ["default", "accept_edits", "plan"]
                steps = cycle.index(mode)  # default→accept_edits=1, default→plan=2
                for _ in range(steps):
                    self.tmux.send_keys("BTab")
        else:
            # Non-bypass cycle: BTab the right number of times.
            cycle = ["default", "accept_edits", "plan"]
            cur_idx = cycle.index(current)
            tgt_idx = cycle.index(mode)
            steps = (tgt_idx - cur_idx) % len(cycle)
            for _ in range(steps):
                self.tmux.send_keys("BTab")

        self.state.update(last_mode=mode)
        await self._publish_state()

    async def clear(self) -> None:
        self.tmux.send_text("/clear")
        self.tmux.send_keys("Enter")

    async def compact(self) -> None:
        self.tmux.send_text("/compact")
        self.tmux.send_keys("Enter")

    async def switch_project(self, cwd: str) -> None:
        self.tmux.kill_claude()
        s = self.state.get()
        self.tmux.start_claude(cwd=cwd, mode=s["last_mode"], resume_id=None)
        self.state.update(last_cwd=cwd)
        await self.bus.publish({"kind": "claude_started"})
        await self._publish_state()

    async def resume(self, session_id: str) -> None:
        self.tmux.kill_claude()
        s = self.state.get()
        self.tmux.start_claude(cwd=s["last_cwd"], mode=s["last_mode"], resume_id=session_id)
        await self.bus.publish({"kind": "claude_started"})
        await self._publish_state()

    _DECISION_KEYS: dict[str, tuple[str, ...]] = {
        # Per research (Task 3) — CC presents a numbered list:
        #   1. Yes
        #   2. Yes, allow all <kind> during this session
        #   3. No
        "allow_once": ("1", "Enter"),
        "allow_always": ("2", "Enter"),
        "deny": ("3", "Enter"),
    }

    async def decide_permission(self, prompt_id: str, decision: str) -> None:
        keys = self._DECISION_KEYS[decision]
        self.tmux.send_keys(*keys)

    async def list_recent_projects(self) -> list[dict[str, Any]]:
        if not self.projects_root.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for entry in self.projects_root.iterdir():
            if not entry.is_dir():
                continue
            cwd = self._decode_project_dir(entry.name)
            mtime = entry.stat().st_mtime
            out.append({"cwd": cwd, "name": Path(cwd).name, "mtime": mtime})
        out.sort(key=lambda p: p["mtime"], reverse=True)
        return out

    async def current_state(self) -> dict[str, Any]:
        s = self.state.get()
        return {
            "cwd": s["last_cwd"],
            "mode": s["last_mode"],
            "model": s["last_model"],
            "effort": s["last_effort"],
            "claude_alive": self.tmux.is_claude_alive(),
        }

    async def list_recent_sessions(self, cwd: str) -> list[dict[str, Any]]:
        encoded = self._encode_project_dir(cwd)
        d = self.projects_root / encoded
        if not d.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for f in d.glob("*.jsonl"):
            out.append({"id": f.stem, "mtime": f.stat().st_mtime, "size": f.stat().st_size})
        out.sort(key=lambda s: s["mtime"], reverse=True)
        return out

    @staticmethod
    def _encode_project_dir(cwd: str) -> str:
        # Claude Code uses leading-dash form: /Users/andrewallen → -Users-andrewallen
        return cwd.replace("/", "-")

    @staticmethod
    def _decode_project_dir(name: str) -> str:
        if name.startswith("-"):
            return "/" + name[1:].replace("-", "/")
        return name.replace("-", "/")
