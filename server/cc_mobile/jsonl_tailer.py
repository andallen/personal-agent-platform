from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .types import (
    AssistantText,
    ChatEvent,
    ClearMarker,
    CompactSummary,
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
    # CC writes a synthetic user-role entry with isCompactSummary=True after
    # /compact finishes — the content is a giant context dump for the next
    # turn, not something a human typed. Surface it as a marker event and
    # drop the body so it doesn't render as a wall-of-text user bubble.
    if obj.get("isCompactSummary"):
        return [CompactSummary()]
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


from .event_bus import EventBus  # noqa: E402 — placed after helpers to avoid circular


class JSONLTailer:
    def __init__(
        self,
        directory: Path,
        bus: EventBus,
        poll_interval: float = 0.25,
    ) -> None:
        self.directory = Path(directory)
        self.bus = bus
        self.poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._cur_path: Path | None = None
        self._cur_offset: int = 0
        # Pin set by rotate_to(): when not None, _loop tracks this path
        # instead of auto-discovering by max mtime. Lets resume() jump the
        # tailer to the resumed jsonl without waiting for it to win the
        # mtime race.
        self._pinned_path: Path | None = None
        # Sentinel meaning "rotate_to(None) was called and we should pick up
        # a fresh auto target on the next iteration." Distinct from "pin was
        # never set" so we can emit a ClearMarker on the unpin transition.
        self._pin_dirty: bool = False

    def rotate_to(self, path: Path | None) -> None:
        """Force the tailer to track `path` (None resumes auto-discovery).

        On the next poll iteration the tailer will switch to `path`, emit a
        ClearMarker, and start reading from offset 0. The pin sticks across
        iterations even if another file has a higher mtime — which is the
        whole point: a freshly-resumed jsonl carries an old mtime until
        Claude actually writes to it.
        """
        self._pinned_path = path
        self._pin_dirty = True

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            if self._pinned_path is not None:
                target = self._pinned_path
            else:
                target = locate_active_jsonl(self.directory)
            if target != self._cur_path:
                # CC never writes a {"type":"clear"} line — /clear, project
                # switch, and resume all just rotate to a fresh jsonl. The
                # rotation itself is the only signal we get, so emit a
                # ClearMarker on every path change *after* the first detection.
                # Also emit when a rotate_to() was just called, even if the
                # path happens to be the same we were already on.
                if self._cur_path is not None and target is not None:
                    await self.bus.publish(
                        {"kind": "chat_event", "event": asdict(ClearMarker())}
                    )
                self._cur_path = target
                self._cur_offset = 0
            elif self._pin_dirty:
                # Unpin (rotate_to(None)) where auto-discovery happens to
                # land on the same path as the prior pin: still surface the
                # transition so the UI knows context changed.
                if self._cur_path is not None:
                    await self.bus.publish(
                        {"kind": "chat_event", "event": asdict(ClearMarker())}
                    )
                self._cur_offset = 0
            self._pin_dirty = False
            if self._cur_path is not None and self._cur_path.exists():
                await self._read_new()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                continue

    async def _read_new(self) -> None:
        assert self._cur_path is not None
        try:
            with self._cur_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._cur_offset)
                while True:
                    line = f.readline()
                    if not line:
                        self._cur_offset = f.tell()
                        return
                    if not line.endswith("\n"):
                        # Partial line — wait for next poll to read it whole.
                        return
                    for event in parse_line(line):
                        payload = {"kind": "chat_event", "event": asdict(event)}
                        await self.bus.publish(payload)
                    self._cur_offset = f.tell()
        except FileNotFoundError:
            self._cur_path = None
            self._cur_offset = 0
