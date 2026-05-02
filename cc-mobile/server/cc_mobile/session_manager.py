from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Protocol

from .event_bus import EventBus
from .jsonl_tailer import _clean
from .state_store import StateStore


def _session_title(path: Path, max_len: int = 60) -> str | None:
    summary: str | None = None
    first_user: str | None = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type")
                if t == "summary" and not summary:
                    s = obj.get("summary")
                    if isinstance(s, str) and s.strip():
                        summary = s.strip()
                elif t == "user" and not first_user:
                    msg = obj.get("message") or {}
                    c = msg.get("content")
                    texts: list[str] = []
                    if isinstance(c, str):
                        texts = [c]
                    elif isinstance(c, list):
                        for b in c:
                            if isinstance(b, dict) and b.get("type") == "text":
                                texts.append(b.get("text") or "")
                    for raw in texts:
                        cleaned = _clean(raw)
                        if cleaned:
                            first_user = cleaned.splitlines()[0]
                            break
                if summary and first_user:
                    break
    except OSError:
        return None
    title = summary or first_user
    if not title:
        return None
    if len(title) > max_len:
        title = title[: max_len - 1].rstrip() + "…"
    return title


class _Tmux(Protocol):
    def session_exists(self) -> bool: ...
    def ensure_session(self, cwd: str | None = None) -> None: ...
    def is_claude_alive(self) -> bool: ...
    def start_claude(self, cwd: str, mode: str = "default", resume_id: str | None = None) -> None: ...
    def kill_claude(self) -> None: ...
    def force_respawn_pane(self, cwd: str | None = None) -> None: ...
    def send_text(self, text: str) -> None: ...
    def send_keys(self, *keys: str) -> None: ...
    def capture_pane(self, lines: int = 200) -> str: ...


class _Tailer(Protocol):
    def rotate_to(self, path: Path | None) -> None: ...


class SessionManager:
    def __init__(
        self,
        tmux: _Tmux,
        state: StateStore,
        bus: EventBus,
        projects_root: Path,
        tailer: _Tailer | None = None,
    ) -> None:
        self.tmux = tmux
        self.state = state
        self.bus = bus
        self.projects_root = projects_root
        self.tailer = tailer
        # Tracks the session id we most recently asked Claude to resume into,
        # so _ensure_alive's auto-recovery path doesn't silently respawn a
        # fresh session and lose the user's intended target.
        self._current_resume_id: str | None = None

    # Bounds on how long we wait for claude to actually exit after C-c, C-c.
    # Real claude usually goes within ~150ms; we cap at ~2s so a stuck process
    # doesn't deadlock the API request.
    _KILL_POLL_INTERVAL_SECONDS = 0.05
    _KILL_TIMEOUT_SECONDS = 2.0
    # Bounds on how long we wait for claude's `❯` input prompt to render
    # after start_claude. A cold start is fast (<1s); --resume against a
    # large jsonl can take many seconds while history renders.
    _READY_POLL_INTERVAL_SECONDS = 0.1
    _READY_TIMEOUT_SECONDS = 15.0

    def _pane_shows_input_prompt(self) -> bool:
        """Look for claude's `❯ ` input bar in the pane's tail.

        Capturing the whole scrollback would be unreliable: a `❯` from
        before kill_claude could still be in history. We slice the last
        ~30 lines, which is where the active input bar lives in claude's
        bottom-anchored TUI.
        """
        try:
            pane = self.tmux.capture_pane(lines=200)
        except Exception:
            return False
        tail = pane.splitlines()[-30:]
        return any("❯" in line for line in tail)

    async def _kill_claude_and_wait(self) -> None:
        """Send the kill keystrokes and poll until claude is observably dead.

        kill_claude() is synchronous and only sends C-c, C-c — claude takes
        a tick to actually exit. If we kick off start_claude before that,
        the launch keystrokes leak into the dying claude (typed into its
        input bar instead of running in the bash that's about to come back).
        Polling is_claude_alive eliminates the race. If the polite kill
        times out we force-respawn the pane: better to nuke and restart
        than to silently degrade into the user-reported broken state.
        """
        if not self.tmux.is_claude_alive():
            return
        self.tmux.kill_claude()
        deadline = asyncio.get_event_loop().time() + self._KILL_TIMEOUT_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            if not self.tmux.is_claude_alive():
                return
            await asyncio.sleep(self._KILL_POLL_INTERVAL_SECONDS)
        # Polite kill failed. Force-respawn the pane.
        await self.bus.publish({"kind": "claude_kill_timeout"})
        try:
            self.tmux.force_respawn_pane(cwd=self.state.get()["last_cwd"])
        except Exception:
            pass
        # Wait once more for the respawn to settle (very short — respawn-pane is sync).
        deadline = asyncio.get_event_loop().time() + 1.0
        while asyncio.get_event_loop().time() < deadline:
            if not self.tmux.is_claude_alive():
                return
            await asyncio.sleep(self._KILL_POLL_INTERVAL_SECONDS)

    async def _wait_claude_ready(self) -> bool:
        """Poll the pane until claude's `❯` input prompt shows up.

        Used after start_claude to make sure subsequent send_text/Enter
        keystrokes land in the input bar — not in the welcome banner or
        the middle of the resumed-history render. Returns True on ready,
        False on timeout.
        """
        deadline = asyncio.get_event_loop().time() + self._READY_TIMEOUT_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            if self._pane_shows_input_prompt():
                return True
            await asyncio.sleep(self._READY_POLL_INTERVAL_SECONDS)
        await self.bus.publish({"kind": "claude_ready_timeout"})
        return False

    async def boot(self) -> None:
        await self._ensure_alive()

    async def _ensure_alive(self) -> None:
        # Called at startup AND at the top of every user-facing tmux op:
        # if the tmux session or claude process has died between requests
        # we recover transparently instead of bubbling a CalledProcessError
        # up to the API and resetting the phone's websocket.
        if self.tmux.session_exists() and self.tmux.is_claude_alive():
            return
        self.tmux.ensure_session()
        if not self.tmux.is_claude_alive():
            s = self.state.get()
            # If a resume was in flight, preserve the resume target on
            # auto-recovery — otherwise a /api/send arriving during the
            # resume's startup window silently spawns a *fresh* session
            # and stranded the user's chosen history.
            self.tmux.start_claude(
                cwd=s["last_cwd"],
                mode=s["last_mode"],
                resume_id=self._current_resume_id,
            )
            await self.bus.publish({"kind": "claude_started"})
            await self._wait_claude_ready()
        await self._publish_state()

    async def send_user_message(self, text: str) -> None:
        await self._ensure_alive()
        self.tmux.send_text(text)
        self.tmux.send_keys("Enter")

    async def interrupt(self) -> None:
        await self._ensure_alive()
        # Two Escapes back-to-back: a single press cancels regular generation,
        # /compact's streaming summary occasionally needs a second tap.
        self.tmux.send_keys("Escape", "Escape")
        # CC restores the canceled message back into its input buffer a beat
        # after Escape lands (so you can edit and resubmit). If we send C-u
        # in the same burst, it arrives before the restore and clears
        # nothing — then the restored text shows up and silently prefixes
        # the next user message. Wait for the restore, then wipe the line.
        await asyncio.sleep(0.18)
        self.tmux.send_keys("C-u")

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
        await self._ensure_alive()
        self.tmux.send_text(f"/model {model_id}")
        self.tmux.send_keys("Enter")
        self.state.update(last_model=model_id)
        await self._publish_state()

    async def set_effort(self, effort: str) -> None:
        await self._ensure_alive()
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
        await self._ensure_alive()
        current = self.state.get()["last_mode"]
        if mode == current:
            return

        if mode == "bypass":
            # Non-bypass → bypass: respawn with the bypass flag.
            await self._kill_claude_and_wait()
            self.tmux.start_claude(cwd=self.state.get()["last_cwd"], mode="bypass")
            self._current_resume_id = None
            if self.tailer is not None:
                self.tailer.rotate_to(None)
            await self.bus.publish({"kind": "claude_started"})
            await self._wait_claude_ready()
        elif current == "bypass":
            # Bypass → non-bypass: respawn without the flag (lands in default),
            # then BTab to target if not default.
            await self._kill_claude_and_wait()
            self.tmux.start_claude(cwd=self.state.get()["last_cwd"], mode="default")
            self._current_resume_id = None
            if self.tailer is not None:
                self.tailer.rotate_to(None)
            await self.bus.publish({"kind": "claude_started"})
            await self._wait_claude_ready()
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
        await self._ensure_alive()
        self.tmux.send_text("/clear")
        self.tmux.send_keys("Enter")
        # /clear rotates Claude to a fresh jsonl; drop any pin so the tailer
        # picks up the new file via auto-discovery once Claude writes to it.
        self._current_resume_id = None
        if self.tailer is not None:
            self.tailer.rotate_to(None)

    async def compact(self) -> None:
        await self._ensure_alive()
        self.tmux.send_text("/compact")
        self.tmux.send_keys("Enter")

    async def switch_project(self, cwd: str) -> None:
        self.tmux.ensure_session()
        await self._kill_claude_and_wait()
        s = self.state.get()
        self.tmux.start_claude(cwd=cwd, mode=s["last_mode"], resume_id=None)
        self._current_resume_id = None
        if self.tailer is not None:
            self.tailer.rotate_to(None)
        self.state.update(last_cwd=cwd)
        await self.bus.publish({"kind": "claude_started"})
        await self._wait_claude_ready()
        await self._publish_state()

    async def apply_terminal_state(self, status: dict[str, Any]) -> None:
        """Reflect state changes detected in the live tmux pane back into the store.

        Called by PaneWatcher when /model or BTab is used directly in the
        terminal. We only update + re-publish when the value actually changes,
        so this is safe to call on every tick.
        """
        current = self.state.get()
        updates: dict[str, Any] = {}
        model_id = status.get("model_id")
        mode = status.get("mode")
        if model_id and model_id != current["last_model"]:
            updates["last_model"] = model_id
        if mode and mode != current["last_mode"]:
            updates["last_mode"] = mode
        if not updates:
            return
        self.state.update(**updates)
        await self._publish_state()

    async def resume(self, session_id: str) -> None:
        self.tmux.ensure_session()
        await self._kill_claude_and_wait()
        s = self.state.get()
        # Pin the tailer to the target jsonl BEFORE we kick off claude — the
        # UI gets ClearMarker + replay immediately rather than waiting for
        # the resumed session's mtime to overtake whatever was active
        # before. Also remember the resume_id so an _ensure_alive auto-
        # recovery during the startup window doesn't silently respawn
        # a fresh session.
        self._current_resume_id = session_id
        if self.tailer is not None:
            target = self.projects_root / self._encode_project_dir(s["last_cwd"]) / f"{session_id}.jsonl"
            self.tailer.rotate_to(target)
        self.tmux.start_claude(cwd=s["last_cwd"], mode=s["last_mode"], resume_id=session_id)
        await self.bus.publish({"kind": "claude_started"})
        await self._wait_claude_ready()
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
        await self._ensure_alive()
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
            out.append(
                {
                    "id": f.stem,
                    "mtime": f.stat().st_mtime,
                    "size": f.stat().st_size,
                    "title": _session_title(f),
                }
            )
        out.sort(key=lambda s: s["mtime"], reverse=True)
        return out

    @staticmethod
    def _encode_project_dir(cwd: str) -> str:
        # Claude Code uses leading-dash form: /home/user → -home-user
        return cwd.replace("/", "-")

    @staticmethod
    def _decode_project_dir(name: str) -> str:
        if name.startswith("-"):
            return "/" + name[1:].replace("-", "/")
        return name.replace("-", "/")
