from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


class TmuxController:
    def __init__(
        self,
        session_name: str = "claude-mobile",
        socket_path: str | None = None,
    ) -> None:
        self.session_name = session_name
        self.socket_path = socket_path

    def _base(self) -> list[str]:
        cmd = ["tmux"]
        if self.socket_path:
            cmd += ["-S", self.socket_path]
        return cmd

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._base() + list(args),
            capture_output=True,
            text=True,
            check=check,
        )

    def session_exists(self) -> bool:
        result = subprocess.run(
            self._base() + ["has-session", "-t", self.session_name],
            capture_output=True,
        )
        return result.returncode == 0

    def ensure_session(self, cwd: str | None = None) -> None:
        if self.session_exists():
            return
        args = ["new-session", "-d", "-s", self.session_name]
        if cwd:
            args += ["-c", cwd]
        self._run(*args)

    def send_text(self, text: str) -> None:
        # `-l` sends literal text without interpreting key names.
        self._run("send-keys", "-t", self.session_name, "-l", text)

    def send_keys(self, *keys: str) -> None:
        # No -l: tmux interprets named keys (Enter, Escape, C-u, etc.)
        self._run("send-keys", "-t", self.session_name, *keys)

    def capture_pane(self, lines: int = 200) -> str:
        # -p prints to stdout. -S -<lines> starts <lines> rows up.
        # -J joins wrapped lines so detectors see logical lines.
        result = self._run(
            "capture-pane",
            "-t",
            self.session_name,
            "-p",
            "-J",
            "-S",
            f"-{lines}",
        )
        return result.stdout

    def kill_session(self) -> None:
        self._run("kill-session", "-t", self.session_name, check=False)

    def is_claude_alive(self) -> bool:
        """Heuristic: are there processes named 'claude' or 'claude-cli' under this session?"""
        # tmux list-panes shows current_command for each pane.
        result = self._run(
            "list-panes",
            "-t",
            self.session_name,
            "-F",
            "#{pane_current_command}",
            check=False,
        )
        if result.returncode != 0:
            return False
        commands = result.stdout.split()
        return any("claude" in c.lower() for c in commands)

    def start_claude(
        self,
        cwd: str,
        mode: str = "default",
        resume_id: str | None = None,
        bin_path: str = "claude",
    ) -> None:
        """Send the launch keystroke into the existing session's pane."""
        # Build the argv list the user wants to run.
        argv = [bin_path]
        if mode == "bypass":
            argv.append("--dangerously-skip-permissions")
        if resume_id:
            argv += ["--resume", resume_id]
        cmd = " ".join(shlex.quote(a) for a in argv)
        # cd then exec replace shell so it's a clean process tree.
        full = f"cd {shlex.quote(cwd)} && exec {cmd}"
        self.send_text(full)
        self.send_keys("Enter")

    def kill_claude(self) -> None:
        """Send Ctrl+C twice (interrupt then quit) — claim the shell, no exec swap kept."""
        self.send_keys("C-c")
        self.send_keys("C-c")
