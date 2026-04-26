from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .types import (
    AssistantText,
    ChatEvent,
    ClearMarker,
    ToolResult,
    ToolUse,
    UserMessage,
)

NOISE_TAG_RE = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|"
    r"local-command-stdout|local-command-stderr|local-command-caveat|"
    r"user-prompt-submit-hook|user-memory-input)\b[^>]*>.*?</\1>",
    re.DOTALL,
)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean(text: str) -> str:
    text = NOISE_TAG_RE.sub("", text)
    text = ANSI_RE.sub("", text)
    return text.strip()


def parse_line(line: str) -> list[ChatEvent]:
    line = line.strip()
    if not line:
        return []
    try:
        obj: dict[str, Any] = json.loads(line)
    except json.JSONDecodeError:
        return []

    t = obj.get("type")
    if t == "clear":
        return [ClearMarker()]
    if t == "user":
        return _parse_user(obj)
    if t == "assistant":
        return _parse_assistant(obj)
    return []


def _parse_user(obj: dict[str, Any]) -> list[ChatEvent]:
    msg = obj.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        cleaned = _clean(content)
        return [UserMessage(text=cleaned)] if cleaned else []
    if isinstance(content, list):
        events: list[ChatEvent] = []
        text_parts: list[str] = []
        for c in content:
            if not isinstance(c, dict):
                continue
            ct = c.get("type")
            if ct == "text":
                cleaned = _clean(c.get("text") or "")
                if cleaned:
                    text_parts.append(cleaned)
            elif ct == "tool_result":
                tc = c.get("content")
                if isinstance(tc, list):
                    flat = "".join(
                        b.get("text", "") if isinstance(b, dict) else str(b) for b in tc
                    )
                else:
                    flat = str(tc) if tc is not None else ""
                events.append(
                    ToolResult(tool_use_id=str(c.get("tool_use_id", "")), content=flat)
                )
        if text_parts:
            events.insert(0, UserMessage(text="\n\n".join(text_parts)))
        return events
    return []


def _parse_assistant(obj: dict[str, Any]) -> list[ChatEvent]:
    msg = obj.get("message") or {}
    content = msg.get("content", [])
    if not isinstance(content, list):
        return []
    events: list[ChatEvent] = []
    for c in content:
        if not isinstance(c, dict):
            continue
        ct = c.get("type")
        if ct == "text":
            txt = (c.get("text") or "").strip()
            if txt:
                events.append(AssistantText(text=txt))
        elif ct == "tool_use":
            events.append(
                ToolUse(
                    name=str(c.get("name", "")),
                    input=c.get("input") or {},
                    id=str(c.get("id", "")),
                )
            )
        # thinking blocks intentionally dropped
    return events


def locate_active_jsonl(directory: Path) -> Path | None:
    """
    Recursive search so a single JSONLTailer pointed at PROJECTS_ROOT
    automatically follows project switches: when claude starts in a new
    cwd, it writes to a new sub-jsonl, which becomes the most-recent.
    """
    if not directory.is_dir():
        return None
    files = list(directory.rglob("*.jsonl"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)
