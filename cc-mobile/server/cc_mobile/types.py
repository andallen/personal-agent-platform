from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class UserMessage:
    text: str
    kind: Literal["user_message"] = "user_message"


@dataclass(slots=True)
class AssistantText:
    text: str
    kind: Literal["assistant_text"] = "assistant_text"


@dataclass(slots=True)
class ToolUse:
    name: str
    input: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    kind: Literal["tool_use"] = "tool_use"


@dataclass(slots=True)
class ToolResult:
    tool_use_id: str
    content: str
    kind: Literal["tool_result"] = "tool_result"


@dataclass(slots=True)
class ClearMarker:
    kind: Literal["clear_marker"] = "clear_marker"


@dataclass(slots=True)
class CompactSummary:
    kind: Literal["compact_summary"] = "compact_summary"


ChatEvent = (
    UserMessage | AssistantText | ToolUse | ToolResult | ClearMarker | CompactSummary
)


@dataclass(slots=True)
class PermissionPrompt:
    id: str
    kind: Literal["bash", "edit", "read", "plan_approval", "other"]
    target: str
    raw: str


@dataclass(slots=True)
class State:
    cwd: str
    mode: str
    model: str | None
    effort: str | None
    claude_alive: bool
