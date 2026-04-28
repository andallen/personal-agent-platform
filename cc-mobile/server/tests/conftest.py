import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import shutil
import subprocess
import uuid

import pytest


@pytest.fixture
def tmux_socket(tmp_path):
    """Provide a private tmux socket so tests don't collide with user sessions."""
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")
    socket_path = tmp_path / "tmux.sock"
    yield str(socket_path)
    # tear down: kill the tmux server on this socket
    subprocess.run(["tmux", "-S", str(socket_path), "kill-server"], capture_output=True)


@pytest.fixture
def session_name():
    return f"test-{uuid.uuid4().hex[:8]}"
