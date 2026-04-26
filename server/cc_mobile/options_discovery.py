from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

USER_COMMANDS_DIR = Path.home() / ".claude" / "commands"

# Hand-maintained fallback. Update when CC adds/removes options. The runtime
# layer can override these by parsing `claude --help` once that lookup is
# verified in research.
FALLBACK_MODELS: list[dict[str, str]] = [
    {"id": "claude-opus-4-7", "label": "Opus 4.7"},
    {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6"},
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5"},
]
FALLBACK_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
# Modes reachable via the runtime UI cycle (Shift+Tab). "auto" is reachable
# only via --permission-mode at launch, so it is not exposed here.
FALLBACK_MODES = ["bypass", "default", "accept_edits", "plan"]

BUILTIN_SLASH_COMMANDS: list[dict[str, str]] = [
    {"name": "/clear", "description": "Reset the conversation"},
    {"name": "/compact", "description": "Summarize older context"},
    {"name": "/model", "description": "Pick a different model"},
    {"name": "/effort", "description": "Set reasoning effort"},
    {"name": "/help", "description": "Show available commands"},
    {"name": "/init", "description": "Initialize CLAUDE.md for this project"},
    {"name": "/memory", "description": "View saved auto-memories"},
    {"name": "/agents", "description": "List available subagents"},
    {"name": "/review", "description": "Review pending changes"},
    {"name": "/security-review", "description": "Scan changes for security issues"},
    {"name": "/loop", "description": "Run a prompt on a recurring interval"},
    {"name": "/schedule", "description": "Schedule a remote agent on cron"},
    {"name": "/fast", "description": "Toggle fast mode"},
    {"name": "/mode", "description": "Change permission mode"},
]


class OptionsDiscovery:
    def __init__(self, claude_bin: str = "claude") -> None:
        self.claude_bin = claude_bin
        self._help_cache: str | None = None

    def _help(self) -> str:
        if self._help_cache is not None:
            return self._help_cache
        try:
            result = subprocess.run(
                [self.claude_bin, "--help"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            self._help_cache = (result.stdout or "") + (result.stderr or "")
        except (FileNotFoundError, subprocess.SubprocessError):
            self._help_cache = ""
        return self._help_cache

    def get_models(self) -> list[dict[str, str]]:
        # `claude --help` does not currently parse-friendly list of model IDs;
        # the fallback list is the authoritative source. If a future CC version
        # adds a parseable section, hook it in here.
        return list(FALLBACK_MODELS)

    def get_efforts(self) -> list[str]:
        return list(FALLBACK_EFFORTS)

    def get_modes(self) -> list[str]:
        return list(FALLBACK_MODES)

    def get_slash_commands(self) -> list[dict[str, str]]:
        cmds = list(BUILTIN_SLASH_COMMANDS)
        cmds.extend(self._user_commands())
        # Dedupe by name, prefer earlier entries (built-ins win over user dupes).
        seen: set[str] = set()
        out: list[dict[str, str]] = []
        for c in cmds:
            if c["name"] in seen:
                continue
            seen.add(c["name"])
            out.append(c)
        return out

    def _user_commands(self) -> list[dict[str, str]]:
        if not USER_COMMANDS_DIR.exists():
            return []
        out: list[dict[str, str]] = []
        for path in sorted(USER_COMMANDS_DIR.glob("*.md")):
            name = "/" + path.stem
            description = self._extract_description(path)
            out.append({"name": name, "description": description})
        return out

    @staticmethod
    def _extract_description(path: Path) -> str:
        try:
            text = path.read_text()
        except OSError:
            return ""
        # Front-matter style: --- ... description: foo ... ---
        m = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL | re.MULTILINE)
        if m:
            for line in m.group(1).splitlines():
                kv = re.match(r"description:\s*(.+)", line.strip())
                if kv:
                    return kv.group(1).strip()
        # Fallback: first non-empty body line
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                return line[:120]
        return ""
