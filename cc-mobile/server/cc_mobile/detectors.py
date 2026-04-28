from __future__ import annotations

import hashlib
import re
from typing import Protocol

from .types import PermissionPrompt


class Detector(Protocol):
    def detect(self, pane_text: str) -> PermissionPrompt | None: ...


def _id_from(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]


# CC's permission prompt shape (verified against real edit fixture, CC v2.1.119):
#
#   Do you want to <verb> <target>?
#  ❯ 1. Yes
#    2. Yes, allow all <kind> during this session (shift+tab)
#    3. No
#
#  Esc to cancel · Tab to amend
#
# Anchors:
#   _PROMPT_OPTIONS  — the ❯ 1. Yes / 2. Yes, allow all <keyword> ... (shift+tab) block
#                      Captures the session-allow keyword (e.g. "edits", "bash commands")
#   _PROMPT_QUESTION — the "Do you want to <verb phrase>?" line just above the options
#
# Classification priority: session-allow keyword > question verb (keyword is more stable)

_PROMPT_OPTIONS = re.compile(
    r"^\s*❯\s*1\.\s*Yes\s*$\n"
    r"\s+2\.\s*Yes,\s+allow\s+all\s+([a-z][a-z ]*?)\s+during\s+this\s+session\s+\(shift\+tab\)",
    re.MULTILINE,
)
_PROMPT_QUESTION = re.compile(r"Do you want to\s+([^\n?]+)\?", re.MULTILINE)
_PLAN_APPROVAL_HEADER = re.compile(
    r"^\s*Ready to code\?\s*$",
    re.MULTILINE,
)


def _kind_from_session_keyword(keyword: str) -> str:
    keyword = keyword.lower()
    if "edit" in keyword or "write" in keyword or "create" in keyword:
        return "edit"
    if "bash" in keyword or "command" in keyword:
        return "bash"
    if "read" in keyword:
        return "read"
    return "other"


def _kind_from_question(verb_phrase: str) -> str:
    vp = verb_phrase.lower()
    if "run" in vp or "execute" in vp:
        return "bash"
    if "create" in vp or "write" in vp or "edit" in vp or "modify" in vp:
        return "edit"
    if "read" in vp or "view" in vp:
        return "read"
    return "other"


class PermissionPromptDetector:
    def detect(self, pane_text: str) -> PermissionPrompt | None:
        m_opts = _PROMPT_OPTIONS.search(pane_text)
        if not m_opts:
            return None

        # Look for the "Do you want to ...?" question that precedes the options block
        prefix = pane_text[: m_opts.start()]
        m_q = None
        for m in _PROMPT_QUESTION.finditer(prefix):
            m_q = m  # keep the last (closest) match
        if m_q is None:
            return None

        verb_phrase = m_q.group(1).strip()

        # Classify: session-keyword first (more reliable), fall back to question verb
        kind = _kind_from_session_keyword(m_opts.group(1))
        if kind == "other":
            kind = _kind_from_question(verb_phrase)

        return PermissionPrompt(
            id=_id_from(f"{kind}|{verb_phrase}"),
            kind=kind,
            target=verb_phrase,
            raw=pane_text[-2000:],
        )


class PlanApprovalDetector:
    def detect(self, pane_text: str) -> PermissionPrompt | None:
        m = _PLAN_APPROVAL_HEADER.search(pane_text)
        if not m:
            return None
        return PermissionPrompt(
            id=_id_from(f"plan|{m.start()}"),
            kind="plan_approval",
            target="approve plan",
            raw=pane_text[-2000:],
        )
