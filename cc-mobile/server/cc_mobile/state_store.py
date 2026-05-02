from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "last_cwd": str(Path.home()),
    "last_mode": "default",
    "last_model": None,
    "last_effort": None,
}


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULTS)
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except (json.JSONDecodeError, OSError, ValueError):
            return dict(DEFAULTS)
        return {**DEFAULTS, **data}

    def get(self) -> dict[str, Any]:
        return dict(self._state)

    def update(self, **changes: Any) -> dict[str, Any]:
        self._state.update(changes)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._state, indent=2))
        os.replace(tmp, self.path)
        return self.get()
