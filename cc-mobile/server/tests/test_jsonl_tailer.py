import json
from pathlib import Path

import pytest

from cc_mobile.jsonl_tailer import parse_line, locate_active_jsonl
from cc_mobile.types import (
    AssistantText,
    ClearMarker,
    ToolResult,
    ToolUse,
    UserMessage,
)


def line(obj):
    return json.dumps(obj)


def test_parse_user_string_message():
    out = parse_line(line({
        "type": "user",
        "message": {"role": "user", "content": "hello"},
    }))
    assert out == [UserMessage(text="hello")]


def test_parse_user_message_strips_command_and_caveat_tags():
    raw = (
        "<local-command-caveat>x</local-command-caveat>"
        "<command-name>/model</command-name>"
        "actual user text"
    )
    out = parse_line(line({"type": "user", "message": {"role": "user", "content": raw}}))
    assert len(out) == 1
    assert isinstance(out[0], UserMessage)
    assert "actual user text" in out[0].text
    assert "command-name" not in out[0].text


def test_parse_user_with_only_noise_returns_empty():
    raw = "<command-name>/model</command-name>"
    out = parse_line(line({"type": "user", "message": {"role": "user", "content": raw}}))
    assert out == []


def test_parse_user_message_strips_system_reminder():
    raw = "real text <system-reminder>this is noise</system-reminder> more text"
    out = parse_line(line({"type": "user", "message": {"role": "user", "content": raw}}))
    assert len(out) == 1
    assert "this is noise" not in out[0].text
    assert "real text" in out[0].text


def test_parse_user_list_content_with_tool_result():
    obj = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "abc", "content": "ok"},
            ],
        },
    }
    out = parse_line(line(obj))
    assert out == [ToolResult(tool_use_id="abc", content="ok")]


def test_parse_assistant_text_block():
    obj = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    }
    out = parse_line(line(obj))
    assert out == [AssistantText(text="hi")]


def test_parse_assistant_thinking_is_dropped():
    obj = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "internal"},
                {"type": "text", "text": "out"},
            ],
        },
    }
    out = parse_line(line(obj))
    assert out == [AssistantText(text="out")]


def test_parse_assistant_tool_use_emitted():
    obj = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {"command": "ls"}},
            ],
        },
    }
    out = parse_line(line(obj))
    assert out == [ToolUse(name="Bash", input={"command": "ls"}, id="tu_1")]


def test_parse_clear_marker_if_present():
    """If CC writes any of these as a /clear signal, we recognize it."""
    obj = {"type": "summary", "summary": "Compact and continue"}
    out = parse_line(line(obj))
    # Compact/clear markers may be type=summary or type=clear in the jsonl
    # depending on CC version. Either should produce a ClearMarker OR be ignored
    # silently (returns []). Test that we don't crash AND that an explicit
    # type=clear becomes a ClearMarker:
    out2 = parse_line(line({"type": "clear"}))
    assert out2 == [ClearMarker()]


def test_parse_unknown_type_returns_empty():
    obj = {"type": "permission-mode", "permissionMode": "default"}
    out = parse_line(line(obj))
    assert out == []


def test_parse_malformed_json_returns_empty():
    out = parse_line("{ not json")
    assert out == []


def test_locate_active_jsonl_picks_most_recent(tmp_path: Path):
    a = tmp_path / "old.jsonl"
    b = tmp_path / "new.jsonl"
    a.write_text("")
    b.write_text("")
    import os, time
    os.utime(a, (0, 0))
    time.sleep(0.01)
    b.write_text("")  # newer mtime
    found = locate_active_jsonl(tmp_path)
    assert found == b


def test_locate_active_jsonl_returns_none_when_empty(tmp_path: Path):
    assert locate_active_jsonl(tmp_path) is None


import asyncio
import json as _json
import pytest

from cc_mobile.event_bus import EventBus
from cc_mobile.jsonl_tailer import JSONLTailer


@pytest.mark.asyncio
async def test_tailer_emits_existing_lines_on_start(tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text(
        _json.dumps({"type": "user", "message": {"role": "user", "content": "first"}})
        + "\n"
    )
    bus = EventBus()
    sub = bus.subscribe()
    tailer = JSONLTailer(directory=tmp_path, bus=bus, poll_interval=0.05)
    await tailer.start()
    ev = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert ev["kind"] == "chat_event"
    assert ev["event"]["kind"] == "user_message"
    assert ev["event"]["text"] == "first"
    await tailer.stop()


@pytest.mark.asyncio
async def test_tailer_streams_appended_lines(tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text("")
    bus = EventBus()
    sub = bus.subscribe()
    tailer = JSONLTailer(directory=tmp_path, bus=bus, poll_interval=0.05)
    await tailer.start()
    # Append after startup
    with f.open("a") as fp:
        fp.write(
            _json.dumps({"type": "user", "message": {"role": "user", "content": "later"}})
            + "\n"
        )
    ev = await asyncio.wait_for(sub.get(), timeout=2.0)
    assert ev["event"]["text"] == "later"
    await tailer.stop()


@pytest.mark.asyncio
async def test_tailer_switches_to_newer_file(tmp_path):
    a = tmp_path / "a.jsonl"
    a.write_text("")
    bus = EventBus()
    sub = bus.subscribe()
    tailer = JSONLTailer(directory=tmp_path, bus=bus, poll_interval=0.05)
    await tailer.start()
    # New file appears later, mtime newer
    await asyncio.sleep(0.1)
    b = tmp_path / "b.jsonl"
    b.write_text(
        _json.dumps({"type": "user", "message": {"role": "user", "content": "in-b"}})
        + "\n"
    )
    ev = await asyncio.wait_for(sub.get(), timeout=2.0)
    assert ev["event"]["text"] == "in-b"
    await tailer.stop()
