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
        # Default capture_pane returns a `❯` so existing tests don't get
        # blocked by the new readiness check; LoadingFakeTmux overrides this.
        self._pane_text = "❯ \n"

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

    def force_respawn_pane(self, cwd=None):
        self.calls.append(("force_respawn_pane", cwd))
        self.alive = False

    def send_text(self, text):
        self.calls.append(("send_text", text))

    def send_keys(self, *keys):
        self.calls.append(("send_keys", keys))

    def capture_pane(self, lines=200):
        self.calls.append(("capture_pane", lines))
        return self._pane_text


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
    # Double-tap Escape to unwind reliably, then a delayed C-u to clear any
    # text CC restored to the input prompt (the canceled /compact, or the
    # last user message that was mid-flight) so it doesn't prefix the
    # next user message.
    assert ("send_keys", ("Escape", "Escape")) in tmux.calls
    assert ("send_keys", ("C-u",)) in tmux.calls
    esc_idx = tmux.calls.index(("send_keys", ("Escape", "Escape")))
    cu_idx = tmux.calls.index(("send_keys", ("C-u",)))
    assert esc_idx < cu_idx, "C-u must follow Escape so the restored text is gone first"
    # NOT Ctrl-C (would kill the CLI process)
    assert all(c[0] != "send_keys" or "C-c" not in c[1] for c in tmux.calls)


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


class FakeTailer:
    def __init__(self):
        self.rotate_calls: list = []

    def rotate_to(self, path):
        self.rotate_calls.append(path)


@pytest.mark.asyncio
async def test_resume_rotates_tailer_to_target_jsonl(state_store, bus, tmp_path):
    """The tailer must be pointed at <projects_root>/<encoded_cwd>/<sid>.jsonl
    BEFORE start_claude runs, so the UI doesn't wait for an mtime race."""
    tmux = FakeTmux(alive=True)
    tailer = FakeTailer()
    mgr = SessionManager(
        tmux=tmux, state=state_store, bus=bus, projects_root=tmp_path, tailer=tailer
    )
    await mgr.boot()
    state_store.update(last_cwd="/Users/andrewallen")
    await mgr.resume("abcd-1234")
    assert len(tailer.rotate_calls) == 1
    target = tailer.rotate_calls[0]
    assert target == tmp_path / "-Users-andrewallen" / "abcd-1234.jsonl"


@pytest.mark.asyncio
async def test_ensure_alive_preserves_resume_id_after_resume(state_store, bus):
    """After a resume, if claude dies (race during startup), _ensure_alive
    must respawn with the SAME --resume id, not as a fresh session."""
    tmux = FakeTmux(alive=True)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=Path("/tmp"))
    await mgr.boot()
    await mgr.resume("abcd-1234")
    # Simulate claude dying during the resume's startup window.
    tmux.alive = False
    tmux.calls.clear()
    await mgr.send_user_message("hi")
    start_calls = [c for c in tmux.calls if c[0] == "start_claude"]
    assert start_calls, "_ensure_alive should restart claude"
    assert start_calls[0][3] == "abcd-1234", (
        "auto-recovered claude must keep the resume target — otherwise the "
        "user lands in a brand-new session and loses their chosen history"
    )


@pytest.mark.asyncio
async def test_switch_project_clears_resume_pin(state_store, bus, tmp_path):
    tmux = FakeTmux(alive=True)
    tailer = FakeTailer()
    mgr = SessionManager(
        tmux=tmux, state=state_store, bus=bus, projects_root=tmp_path, tailer=tailer
    )
    await mgr.boot()
    await mgr.resume("abcd-1234")
    await mgr.switch_project("/home/andrew/projects/foo")
    # Pin should be cleared (None) so the tailer auto-discovers the new fresh jsonl.
    assert tailer.rotate_calls[-1] is None
    # And _current_resume_id should not survive a project switch.
    tmux.alive = False
    tmux.calls.clear()
    await mgr.send_user_message("hi")
    start_calls = [c for c in tmux.calls if c[0] == "start_claude"]
    assert start_calls and start_calls[0][3] is None


@pytest.mark.asyncio
async def test_clear_unpins_tailer(state_store, bus, tmp_path):
    """/clear in claude rotates to a fresh jsonl; drop any resume pin."""
    tmux = FakeTmux(alive=True)
    tailer = FakeTailer()
    mgr = SessionManager(
        tmux=tmux, state=state_store, bus=bus, projects_root=tmp_path, tailer=tailer
    )
    await mgr.boot()
    await mgr.resume("abcd-1234")
    await mgr.clear()
    assert tailer.rotate_calls[-1] is None


class StubbornFakeTmux(FakeTmux):
    """Simulates claude that takes N kill_claude polls before actually exiting,
    mimicking the real-world race where C-c, C-c must be observed."""

    def __init__(self, polls_before_dead: int = 3):
        super().__init__(alive=True)
        self.session_existed = True
        self._polls_before_dead = polls_before_dead
        self._kill_called = False
        self._alive_calls_after_kill = 0

    def is_claude_alive(self) -> bool:
        if self._kill_called:
            self._alive_calls_after_kill += 1
            if self._alive_calls_after_kill > self._polls_before_dead:
                return False
            return True
        return self.alive

    def kill_claude(self):
        self._kill_called = True
        self.calls.append(("kill_claude",))


@pytest.mark.asyncio
async def test_resume_waits_for_claude_to_die_before_starting(state_store, bus, tmp_path):
    """kill_claude returns before claude actually exits; SessionManager must
    wait for is_claude_alive to flip False before calling start_claude.
    Otherwise start_claude's keystrokes leak into the dying claude."""
    tmux = StubbornFakeTmux(polls_before_dead=2)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=tmp_path)
    await mgr.boot()
    await mgr.resume("abcd-1234")
    # The order of calls in tmux.calls must be: kill_claude, then start_claude.
    # And by the time start_claude was called, is_claude_alive() must have
    # been observed False at least once.
    kill_idx = next(i for i, c in enumerate(tmux.calls) if c[0] == "kill_claude")
    start_idx = next(i for i, c in enumerate(tmux.calls) if c[0] == "start_claude")
    assert start_idx > kill_idx
    assert tmux._alive_calls_after_kill > tmux._polls_before_dead


@pytest.mark.asyncio
async def test_switch_project_waits_for_claude_to_die(state_store, bus, tmp_path):
    tmux = StubbornFakeTmux(polls_before_dead=2)
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=tmp_path)
    await mgr.boot()
    await mgr.switch_project("/home/andrew/projects/foo")
    assert tmux._alive_calls_after_kill > tmux._polls_before_dead


class UnkillableFakeTmux(FakeTmux):
    """Simulates claude that ignores C-c, C-c entirely. The polite kill
    must time out and the force-respawn fallback must be invoked."""

    def __init__(self):
        super().__init__(alive=True)
        self.session_existed = True
        self._kill_called = False

    def is_claude_alive(self) -> bool:
        # Stays alive through kill_claude; only flips False after force_respawn_pane.
        return self.alive

    def kill_claude(self):
        self.calls.append(("kill_claude",))
        self._kill_called = True
        # Note: doesn't flip alive — claude won't die from C-c.

    def force_respawn_pane(self, cwd=None):
        self.calls.append(("force_respawn_pane", cwd))
        self.alive = False


@pytest.mark.asyncio
async def test_kill_timeout_triggers_force_respawn(state_store, bus, tmp_path):
    """If C-c, C-c doesn't kill claude within the timeout, SessionManager
    must force-respawn the pane rather than silently letting start_claude
    type into a still-alive claude (the original user-reported bug)."""
    tmux = UnkillableFakeTmux()
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=tmp_path)
    # Tighten the kill timeout so the test runs quickly.
    mgr._KILL_TIMEOUT_SECONDS = 0.2
    await mgr.boot()
    tmux.calls.clear()
    await mgr.resume("abcd-1234")
    actions = [c[0] for c in tmux.calls]
    assert "kill_claude" in actions
    assert "force_respawn_pane" in actions, (
        f"force-respawn must be called when polite kill times out; got actions: {actions}"
    )
    # Order: kill_claude first, then force_respawn_pane.
    assert actions.index("kill_claude") < actions.index("force_respawn_pane")


class LoadingFakeTmux(FakeTmux):
    """Simulates claude that takes N capture_pane polls to render the
    input prompt after starting. Until then, capture_pane returns the
    welcome screen with no `❯` indicator."""

    def __init__(self, polls_until_ready: int = 3):
        super().__init__(alive=False)
        self.session_existed = True
        self._polls_until_ready = polls_until_ready
        self._capture_calls = 0
        self._started = False

    def start_claude(self, cwd, mode="default", resume_id=None):
        self.calls.append(("start_claude", cwd, mode, resume_id))
        self.alive = True
        self._started = True
        self._capture_calls = 0

    def capture_pane(self, lines=200):
        self.calls.append(("capture_pane", lines))
        if not self._started:
            return ""
        self._capture_calls += 1
        # Welcome screen until ready, then the input prompt appears.
        if self._capture_calls > self._polls_until_ready:
            return (
                "─────────────────\n"
                "❯ \n"
                "─────────────────\n"
                "  Opus 4.7\n"
            )
        return (
            "Welcome back User!\n"
            "loading conversation history...\n"
        )


@pytest.mark.asyncio
async def test_send_user_message_after_fresh_start_waits_for_input_prompt(
    state_store, bus, tmp_path
):
    """If _ensure_alive must start claude (because it died), the eventual
    send_text/Enter must come AFTER `❯` shows up — otherwise the text lands
    in the welcome screen / loading scrollback and Enter fails to submit."""
    tmux = LoadingFakeTmux(polls_until_ready=3)
    # Start claude alive=False so send_user_message has to spawn it.
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=tmp_path)
    await mgr.boot()
    tmux.calls.clear()
    tmux._capture_calls = 0
    tmux._started = False
    tmux.alive = False
    await mgr.send_user_message("hello")
    # Order must be: start_claude, [≥3 capture_pane], send_text, Enter.
    text_idx = next(i for i, c in enumerate(tmux.calls) if c[0] == "send_text")
    start_idx = next(i for i, c in enumerate(tmux.calls) if c[0] == "start_claude")
    assert start_idx < text_idx
    captures_between = sum(
        1 for c in tmux.calls[start_idx:text_idx] if c[0] == "capture_pane"
    )
    assert captures_between > tmux._polls_until_ready, (
        f"send_text must wait for `❯` to appear; saw only {captures_between} "
        f"capture_pane probes between start_claude and send_text "
        f"(needed > {tmux._polls_until_ready})"
    )


@pytest.mark.asyncio
async def test_resume_waits_for_input_prompt_before_returning(
    state_store, bus, tmp_path
):
    """resume() must wait for claude --resume's history render to finish
    (input prompt visible) so that any subsequent /api/send doesn't race."""
    tmux = LoadingFakeTmux(polls_until_ready=4)
    tmux.alive = True  # session has running claude before resume
    tmux._started = True
    tmux._capture_calls = 99  # so kill+restart drives the wait
    mgr = SessionManager(tmux=tmux, state=state_store, bus=bus, projects_root=tmp_path)
    await mgr.boot()
    tmux.calls.clear()
    # Reset the readiness probe counter so the wait starts fresh after restart.
    tmux._capture_calls = 0
    tmux._started = False
    tmux.alive = True  # kill_claude flips this to False
    await mgr.resume("abcd-1234")
    # By the time resume returns, capture_pane must have been polled enough
    # times to see the prompt.
    captures = sum(1 for c in tmux.calls if c[0] == "capture_pane")
    assert captures > tmux._polls_until_ready


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
