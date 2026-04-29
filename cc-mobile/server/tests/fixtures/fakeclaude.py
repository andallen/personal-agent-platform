#!/usr/bin/env python3
"""Stand-in for `claude` used by integration tests.

Sets its own process name to `claude` via prctl(PR_SET_NAME) so that
TmuxController.is_claude_alive() — which keys off pane_current_command —
correctly reports it alive. Without that, the check looks for the
substring "claude" in the pane's current command and finds "python3" or
"bash" instead, breaking the integration test entirely.

Also handles --resume: writes JSONL events to
$FAKECLAUDE_PROJECTS_ROOT/<encoded_cwd>/<session_id>.jsonl, mirroring
real claude's directory layout so the JSONLTailer rotates correctly.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path


def _set_proc_name(name: str) -> None:
    try:
        libc = ctypes.CDLL("libc.so.6")
        # PR_SET_NAME = 15
        libc.prctl(15, name.encode(), 0, 0, 0)
    except OSError:
        pass


def _encode(cwd: str) -> str:
    return cwd.replace("/", "-")


def main() -> int:
    _set_proc_name("claude")

    p = argparse.ArgumentParser()
    p.add_argument("--resume", default=None)
    p.add_argument("--dangerously-skip-permissions", action="store_true")
    args, _ = p.parse_known_args()

    session_id = args.resume or uuid.uuid4().hex
    projects_root = Path(os.environ.get("FAKECLAUDE_PROJECTS_ROOT", "/tmp/fakeclaude"))
    cwd = os.getcwd()
    out_dir = projects_root / _encode(cwd)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / f"{session_id}.jsonl"

    # Touch jsonl on launch so JSONLTailer sees activity / mtime bump.
    with jsonl.open("a") as f:
        f.write(json.dumps({"type": "system", "subtype": "start", "sessionId": session_id}) + "\n")

    print(f"fakeclaude session_id={session_id} resume={'yes' if args.resume else 'no'}")
    sys.stdout.flush()
    time.sleep(0.3)  # render-delay simulation
    print()
    print("❯ ")
    sys.stdout.flush()

    # Two-Ctrl+C exit, like real claude.
    ctrl_c_count = {"n": 0}

    def on_int(sig, frame):
        ctrl_c_count["n"] += 1
        if ctrl_c_count["n"] >= 2:
            sys.exit(0)
        print()
        print("(press Ctrl+C again to exit)")
        print("❯ ")
        sys.stdout.flush()

    signal.signal(signal.SIGINT, on_int)

    while True:
        try:
            line = input()
        except EOFError:
            return 0
        with jsonl.open("a") as f:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": line}}) + "\n")
        print(f"> {line}")
        print("❯ ")
        sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
