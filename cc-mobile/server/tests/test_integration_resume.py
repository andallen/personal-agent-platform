"""End-to-end integration test for the resume bug.

Spawns a real tmux server on a private socket, runs cc-mobile's
SessionManager + JSONLTailer + TmuxController against a fake `claude`
binary on PATH, and exercises the full resume flow: kill, restart with
--resume, tailer rotation, send_user_message after readiness wait.

This is the test that proves the user's reported failure (tap resume,
nothing changes; type message, message not sent) is fixed at the
integration layer — not just in unit tests.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from cc_mobile.event_bus import EventBus
from cc_mobile.jsonl_tailer import JSONLTailer
from cc_mobile.session_manager import SessionManager
from cc_mobile.state_store import StateStore
from cc_mobile.tmux_controller import TmuxController


FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fakeclaude.py"


@pytest.fixture
def projects_root(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    return root


@pytest.fixture
def state_store(tmp_path):
    return StateStore(tmp_path / "state.json")


@pytest.fixture
def fake_claude_path(tmp_path, projects_root):
    """Put fakeclaude.sh on PATH as `claude`, configure where it writes jsonls."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    target = bindir / "claude"
    shutil.copy(FAKE_CLAUDE, target)
    target.chmod(0o755)
    old_path = os.environ.get("PATH", "")
    old_root = os.environ.get("FAKECLAUDE_PROJECTS_ROOT")
    os.environ["PATH"] = f"{bindir}:{old_path}"
    os.environ["FAKECLAUDE_PROJECTS_ROOT"] = str(projects_root)
    yield target
    os.environ["PATH"] = old_path
    if old_root is None:
        os.environ.pop("FAKECLAUDE_PROJECTS_ROOT", None)
    else:
        os.environ["FAKECLAUDE_PROJECTS_ROOT"] = old_root


@pytest.fixture
def tmux_socket(tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")
    sock = tmp_path / "tmux.sock"
    yield str(sock)
    subprocess.run(["tmux", "-S", str(sock), "kill-server"], capture_output=True)


@pytest.fixture
def session_name():
    return f"itest-{uuid.uuid4().hex[:8]}"


def _wait_for(predicate, timeout=10.0, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.mark.asyncio
async def test_resume_end_to_end(
    state_store, projects_root, fake_claude_path, tmux_socket, session_name
):
    """The headline regression test: a session was active, the user picks a
    different session, and we expect: (a) the kill→start cycle is verified
    by `pane_current_command` flipping, (b) the tailer publishes a
    ClearMarker on the bus immediately, (c) a subsequent send_user_message
    actually lands in the resumed jsonl as a real user event."""
    # Point TmuxController at fakeclaude by absolute path; that bypasses
    # ~/.bashrc PATH munging which would otherwise resolve to real claude.
    tmux = TmuxController(
        socket_path=tmux_socket,
        session_name=session_name,
        claude_bin=str(fake_claude_path),
    )

    # tmux on Linux derives `pane_current_command` from a different field than
    # /proc/<pid>/comm — even after PR_SET_NAME=claude, tmux still reports
    # "python3" for our fakeclaude. The is_claude_alive heuristic works fine
    # against real claude but not against this stand-in, so widen the match
    # for the test only. (Production code is unchanged.)
    _real_alive = tmux.is_claude_alive

    def alive_for_test() -> bool:
        if _real_alive():
            return True
        result = subprocess.run(
            ["tmux", "-S", tmux_socket, "list-panes", "-t", session_name,
             "-F", "#{pane_current_command}"],
            capture_output=True, text=True,
        )
        return "python" in result.stdout.lower()

    tmux.is_claude_alive = alive_for_test  # type: ignore[method-assign]
    bus = EventBus()
    tailer = JSONLTailer(directory=projects_root, bus=bus, poll_interval=0.05)
    mgr = SessionManager(
        tmux=tmux, state=state_store, bus=bus,
        projects_root=projects_root, tailer=tailer,
    )

    # The cwd must be a path that actually exists on this machine — the
    # start_claude command does `cd <cwd> && claude ...` and the cd has to
    # succeed for fakeclaude to launch.
    cwd_dir = projects_root.parent / "workdir"
    cwd_dir.mkdir()
    cwd = str(cwd_dir)
    state_store.update(last_cwd=cwd, last_mode="bypass")
    await tailer.start()

    # Boot — fakeclaude starts, writes a fresh session jsonl.
    await mgr.boot()
    if not _wait_for(tmux.is_claude_alive, timeout=5.0):
        pane = tmux.capture_pane(lines=200)
        # Probe pane_current_command directly.
        list_panes = subprocess.run(
            ["tmux", "-S", tmux_socket, "list-panes", "-t", session_name,
             "-F", "#{pane_current_command}/#{pane_current_path}"],
            capture_output=True, text=True,
        )
        raise AssertionError(
            f"claude should be alive after boot.\n"
            f"pane_current_command/path: {list_panes.stdout!r}\n"
            f"pane:\n{pane}\n"
        )

    # Find the jsonl fakeclaude wrote (encoded from $PWD inside the pane —
    # the pane's cwd is wherever start_claude cd'd to, which is `cwd`).
    encoded = SessionManager._encode_project_dir(cwd)
    project_dir = projects_root / encoded
    if not _wait_for(lambda: project_dir.exists() and any(project_dir.glob("*.jsonl")), timeout=5.0):
        pane = tmux.capture_pane(lines=200)
        raise AssertionError(
            f"fakeclaude should have created its jsonl on boot.\n"
            f"project_dir={project_dir} exists={project_dir.exists()}\n"
            f"PATH={os.environ.get('PATH')}\n"
            f"FAKECLAUDE_PROJECTS_ROOT={os.environ.get('FAKECLAUDE_PROJECTS_ROOT')}\n"
            f"pane:\n{pane}\n"
        )

    initial_jsonls = list(project_dir.glob("*.jsonl"))
    assert len(initial_jsonls) == 1
    initial_jsonl = initial_jsonls[0]
    initial_session_id = initial_jsonl.stem

    # Now create a SECOND session jsonl manually — this is what we'll resume to.
    # Make its mtime OLDER than the active one so the tailer would NOT auto-pick it.
    target_session_id = uuid.uuid4().hex
    target_jsonl = project_dir / f"{target_session_id}.jsonl"
    import json
    target_jsonl.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "from-target-session"}})
        + "\n"
    )
    old_t = initial_jsonl.stat().st_mtime - 60
    os.utime(target_jsonl, (old_t, old_t))

    # Subscribe to the bus so we can observe what gets published during resume.
    sub = bus.subscribe()
    # Drain anything queued so far.
    while True:
        try:
            sub.get_nowait()
        except asyncio.QueueEmpty:
            break

    # === The resume action ===
    await mgr.resume(target_session_id)

    # T2: Within a short window, we must see a clear_marker followed by the
    # target session's existing event ("from-target-session"). If the OLD
    # bug were still present, we'd see neither (tailer stuck on initial_jsonl).
    saw_clear = False
    saw_target_event = False
    deadline = asyncio.get_event_loop().time() + 5.0
    while asyncio.get_event_loop().time() < deadline and not (saw_clear and saw_target_event):
        try:
            ev = await asyncio.wait_for(sub.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        if ev.get("kind") == "chat_event":
            ev_kind = ev["event"]["kind"]
            if ev_kind == "clear_marker":
                saw_clear = True
            elif ev_kind == "user_message" and "from-target-session" in ev["event"].get("text", ""):
                saw_target_event = True
    assert saw_clear, "tailer must publish ClearMarker on resume"
    assert saw_target_event, "tailer must replay the resumed jsonl's history"

    # T1: claude should be running with --resume <target_session_id>.
    assert _wait_for(tmux.is_claude_alive, timeout=5.0)
    pane = tmux.capture_pane(lines=200)
    assert target_session_id in pane, (
        f"pane should show fakeclaude reporting the resumed session id; got:\n{pane}"
    )
    # AND no fresh session jsonl was created (the old bug created a new one).
    after_jsonls = set(project_dir.glob("*.jsonl"))
    assert after_jsonls == {initial_jsonl, target_jsonl}, (
        f"resume must not spawn a fresh session; jsonls: {after_jsonls}"
    )

    # T3: a send_user_message after the resume must land in target_jsonl.
    await mgr.send_user_message("hello-after-resume")
    assert _wait_for(
        lambda: "hello-after-resume" in target_jsonl.read_text(),
        timeout=5.0,
    ), (
        "the user message should have been written to the resumed jsonl; "
        f"target jsonl content:\n{target_jsonl.read_text()}\n"
        f"pane:\n{tmux.capture_pane(lines=100)}"
    )

    await tailer.stop()
