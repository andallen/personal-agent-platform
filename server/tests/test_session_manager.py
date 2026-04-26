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


@pytest.mark.asyncio
async def test_set_model_sends_slash_command_and_persists(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.set_model("claude-sonnet-4-6")
    assert ("send_text", "/model claude-sonnet-4-6") in tmux.calls
    assert ("send_keys", ("Enter",)) in tmux.calls
    assert state_store.get()["last_model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_set_effort_sends_slash_command(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.set_effort("xhigh")
    assert ("send_text", "/effort xhigh") in tmux.calls
    assert state_store.get()["last_effort"] == "xhigh"


@pytest.mark.asyncio
async def test_set_mode_persists(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.set_mode("plan")
    assert state_store.get()["last_mode"] == "plan"


@pytest.mark.asyncio
async def test_set_mode_bypass_respawns_claude(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    state_store.update(last_mode="default")
    await mgr.set_mode("bypass")
    actions = [c[0] for c in tmux.calls]
    assert "kill_claude" in actions
    start_calls = [c for c in tmux.calls if c[0] == "start_claude"]
    assert start_calls[-1][2] == "bypass"
    assert state_store.get()["last_mode"] == "bypass"


@pytest.mark.asyncio
async def test_set_mode_non_bypass_cycles_btab(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    state_store.update(last_mode="default")
    await mgr.set_mode("plan")
    btab_count = sum(
        1 for c in tmux.calls
        if c[0] == "send_keys" and c[1] == ("BTab",)
    )
    assert btab_count == 2  # default → plan = 2 BTab
    assert state_store.get()["last_mode"] == "plan"


@pytest.mark.asyncio
async def test_clear_sends_slash_clear(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.clear()
    assert ("send_text", "/clear") in tmux.calls


@pytest.mark.asyncio
async def test_compact_sends_slash_compact(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.compact()
    assert ("send_text", "/compact") in tmux.calls


@pytest.mark.asyncio
async def test_switch_project_kills_then_starts_in_new_dir(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.switch_project("/home/andrew/projects/foo")
    actions = [c[0] for c in tmux.calls]
    assert "kill_claude" in actions
    assert any(
        c == ("start_claude", "/home/andrew/projects/foo", "default", None)
        for c in tmux.calls
    )
    assert state_store.get()["last_cwd"] == "/home/andrew/projects/foo"


@pytest.mark.asyncio
async def test_resume_starts_claude_with_resume_id(state_store, bus):
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.resume("abcd-1234")
    assert any(
        c[0] == "start_claude" and c[3] == "abcd-1234"
        for c in tmux.calls
    )


@pytest.mark.asyncio
async def test_decide_permission_allow_once_sends_one_keystroke(state_store, bus):
    """Per research, Allow-once is the FIRST option in CC's list. We send '1' Enter."""
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.decide_permission(prompt_id="p1", decision="allow_once")
    assert ("send_keys", ("1", "Enter")) in tmux.calls


@pytest.mark.asyncio
async def test_list_recent_projects_reads_from_projects_root(state_store, bus, tmp_path):
    proj_root = tmp_path / "projects"
    (proj_root / "-Users-andrewallen").mkdir(parents=True)
    (proj_root / "-home-andrew-projects-foo").mkdir(parents=True)
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=proj_root)
    projects = await mgr.list_recent_projects()
    cwds = {p["cwd"] for p in projects}
    assert "/Users/andrewallen" in cwds
    assert "/home/andrew/projects/foo" in cwds


@pytest.mark.asyncio
async def test_list_recent_sessions_for_cwd(state_store, bus, tmp_path):
    proj_root = tmp_path / "projects"
    enc = proj_root / "-tmp-x"
    enc.mkdir(parents=True)
    (enc / "abc.jsonl").write_text("")
    (enc / "def.jsonl").write_text("")
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=proj_root)
    sessions = await mgr.list_recent_sessions("/tmp/x")
    ids = {s["id"] for s in sessions}
    assert {"abc", "def"}.issubset(ids)
