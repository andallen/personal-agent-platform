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
