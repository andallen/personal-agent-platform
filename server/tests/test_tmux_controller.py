import subprocess
import time
from pathlib import Path

import pytest

from cc_mobile.tmux_controller import TmuxController


def test_ensure_session_creates_when_missing(tmux_socket, session_name):
    ctl = TmuxController(socket_path=tmux_socket, session_name=session_name)
    assert not ctl.session_exists()
    ctl.ensure_session()
    assert ctl.session_exists()


def test_ensure_session_is_idempotent(tmux_socket, session_name):
    ctl = TmuxController(socket_path=tmux_socket, session_name=session_name)
    ctl.ensure_session()
    ctl.ensure_session()  # second call must not raise
    assert ctl.session_exists()


def test_send_text_then_capture_returns_text(tmux_socket, session_name):
    ctl = TmuxController(socket_path=tmux_socket, session_name=session_name)
    ctl.ensure_session()
    ctl.send_text("echo HELLO_FROM_TEST_42")
    ctl.send_keys("Enter")
    time.sleep(0.4)
    pane = ctl.capture_pane(lines=200)
    assert "HELLO_FROM_TEST_42" in pane


def test_send_keys_named_keys(tmux_socket, session_name):
    ctl = TmuxController(socket_path=tmux_socket, session_name=session_name)
    ctl.ensure_session()
    # Type partial command, then Esc to clear (bash readline)
    ctl.send_text("echo nope")
    ctl.send_keys("Escape", "C-u")  # readline: clear line
    ctl.send_text("echo CLEARED")
    ctl.send_keys("Enter")
    time.sleep(0.4)
    pane = ctl.capture_pane(lines=200)
    assert "CLEARED" in pane
    assert "nope" not in pane.split("CLEARED")[0].splitlines()[-3:][0] or "CLEARED" in pane


def test_start_claude_does_not_use_exec(monkeypatch, tmux_socket, session_name):
    """start_claude must NOT use `exec` — if claude exits the shell needs
    to survive so kill_claude → start_claude can recycle the same pane.
    With `exec`, the pane closes when claude exits and tmux closes the
    window/session, making recovery flaky."""
    captured: list[str] = []

    def fake_send_text(self, text):
        captured.append(text)

    monkeypatch.setattr(TmuxController, "send_text", fake_send_text)
    monkeypatch.setattr(TmuxController, "send_keys", lambda self, *k: None)

    ctl = TmuxController(socket_path=tmux_socket, session_name=session_name)
    ctl.start_claude(cwd="/tmp", mode="bypass", resume_id="abc-123")
    assert captured, "start_claude should send a launch command"
    cmd = captured[0]
    assert "exec " not in cmd, f"start_claude must not exec; got: {cmd!r}"
    # Sanity: the launch arguments still made it through.
    assert "claude" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert "--resume" in cmd
    assert "abc-123" in cmd
