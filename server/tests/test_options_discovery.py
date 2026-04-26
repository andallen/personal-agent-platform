from pathlib import Path

from cc_mobile.options_discovery import OptionsDiscovery


def test_models_returns_known_list_when_no_help_available():
    od = OptionsDiscovery(claude_bin="/nonexistent/binary")
    models = od.get_models()
    assert "claude-opus-4-7" in [m["id"] for m in models]
    assert "claude-sonnet-4-6" in [m["id"] for m in models]


def test_efforts_returns_known_levels():
    od = OptionsDiscovery(claude_bin="/nonexistent/binary")
    efforts = od.get_efforts()
    assert efforts == ["low", "medium", "high", "xhigh", "max"]


def test_modes_returns_ui_cycle_modes_only():
    od = OptionsDiscovery(claude_bin="/nonexistent/binary")
    modes = od.get_modes()
    assert "default" in modes
    assert "plan" in modes
    assert "bypass" in modes
    assert "accept_edits" in modes
    # auto is reachable only via --permission-mode flag at launch, not via
    # the Shift+Tab cycle, so it's not exposed in the dropdown.
    assert "auto" not in modes


def test_slash_commands_includes_clear_compact_model(tmp_path: Path, monkeypatch):
    # Empty user-commands dir → only built-ins
    monkeypatch.setattr(
        "cc_mobile.options_discovery.USER_COMMANDS_DIR",
        tmp_path / "commands",
    )
    od = OptionsDiscovery(claude_bin="/nonexistent")
    cmds = od.get_slash_commands()
    names = {c["name"] for c in cmds}
    assert "/clear" in names
    assert "/compact" in names
    assert "/model" in names
    assert "/effort" in names


def test_slash_commands_picks_up_user_commands(tmp_path: Path, monkeypatch):
    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "review-pr.md").write_text(
        "---\ndescription: Review the current PR thoroughly\n---\n\nbody\n"
    )
    monkeypatch.setattr("cc_mobile.options_discovery.USER_COMMANDS_DIR", cmd_dir)
    od = OptionsDiscovery(claude_bin="/nonexistent")
    cmds = od.get_slash_commands()
    matches = [c for c in cmds if c["name"] == "/review-pr"]
    assert len(matches) == 1
    assert "Review" in matches[0]["description"]
