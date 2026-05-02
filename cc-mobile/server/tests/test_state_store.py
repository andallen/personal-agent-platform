import json
from pathlib import Path

from cc_mobile.state_store import StateStore

HOME = str(Path.home())


def test_first_read_returns_defaults(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    state = store.get()
    assert state["last_cwd"] == HOME
    assert state["last_mode"] == "default"
    assert state["last_model"] is None
    assert state["last_effort"] is None


def test_update_writes_atomically_and_persists(tmp_path: Path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.update(last_mode="plan", last_model="claude-sonnet-4-6")

    # New instance reads what was written
    fresh = StateStore(path)
    state = fresh.get()
    assert state["last_mode"] == "plan"
    assert state["last_model"] == "claude-sonnet-4-6"
    # last_cwd default preserved through partial update
    assert state["last_cwd"] == HOME


def test_corrupted_file_falls_back_to_defaults(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text("{ not valid json")
    store = StateStore(path)
    state = store.get()
    assert state["last_mode"] == "default"


def test_atomic_write_uses_tmp_then_rename(tmp_path: Path, monkeypatch):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.update(last_mode="plan")
    # No leftover .tmp files
    assert list(tmp_path.glob("*.tmp")) == []
    # File exists and is valid json
    assert json.loads(path.read_text())["last_mode"] == "plan"
