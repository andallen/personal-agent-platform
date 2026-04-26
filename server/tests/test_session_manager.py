import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cc_mobile.event_bus import EventBus
from cc_mobile.session_manager import SessionManager
from cc_mobile.state_store import StateStore


class FakeTmux:
    def __init__(self, alive: bool = False):
        self.session_existed = alive
        self.alive = alive
        self.calls: list[tuple] = []

    def session_exists(self) -> bool:
        return self.session_existed

    def ensure_session(self, cwd=None):
        self.calls.append(("ensure_session", cwd))
        self.session_existed = True

    def is_claude_alive(self) -> bool:
        return self.alive

    def start_claude(self, cwd, mode="default", resume_id=None):
        self.calls.append(("start_claude", cwd, mode, resume_id))
        self.alive = True

    def kill_claude(self):
        self.calls.append(("kill_claude",))
        self.alive = False

    def send_text(self, text):
        self.calls.append(("send_text", text))

    def send_keys(self, *keys):
        self.calls.append(("send_keys", keys))

    def capture_pane(self, lines=200):
        return ""


@pytest.fixture
def state_store(tmp_path):
    return StateStore(tmp_path / "state.json")


@pytest.fixture
def bus():
    return EventBus()


@pytest.mark.asyncio
async def test_boot_cold_starts_claude_in_default_dir(state_store, bus):
    tmux = FakeTmux(alive=False)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    actions = [c[0] for c in tmux.calls]
    assert "ensure_session" in actions
    assert "start_claude" in actions
    start_call = next(c for c in tmux.calls if c[0] == "start_claude")
    assert start_call[1] == "/Users/andrewallen"
    assert start_call[2] == "default"


@pytest.mark.asyncio
async def test_boot_warm_does_not_restart_claude(state_store, bus):
    tmux = FakeTmux(alive=True)
    tmux.session_existed = True
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    actions = [c[0] for c in tmux.calls]
    assert "start_claude" not in actions


@pytest.mark.asyncio
async def test_send_user_message_writes_text_then_enter(state_store, bus):
    tmux = FakeTmux(alive=True)
    tmux.session_existed = True
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.send_user_message("hello world")
    sequence = [c for c in tmux.calls if c[0] in ("send_text", "send_keys")]
    assert sequence[-2] == ("send_text", "hello world")
    assert sequence[-1] == ("send_keys", ("Enter",))


@pytest.mark.asyncio
async def test_interrupt_sends_escape(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.interrupt()
    assert ("send_keys", ("Escape",)) in tmux.calls
    # NOT Ctrl-C
    assert all(c != ("send_keys", ("C-c",)) for c in tmux.calls)
