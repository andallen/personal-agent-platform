from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any, Protocol

from .event_bus import EventBus
from .types import PermissionPrompt


class _PaneSource(Protocol):
    def capture_pane(self, lines: int = 200) -> str: ...


class _Detector(Protocol):
    def detect(self, pane_text: str) -> PermissionPrompt | None: ...


class PaneWatcher:
    def __init__(
        self,
        tmux: _PaneSource,
        bus: EventBus,
        detectors: list[_Detector],
        interval: float = 0.25,
    ) -> None:
        self.tmux = tmux
        self.bus = bus
        self.detectors = detectors
        self.interval = interval
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._active: dict[str, PermissionPrompt] = {}  # by id

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
            try:
                pane = self.tmux.capture_pane(lines=200)
            except Exception:
                pane = ""
            await self._tick(pane)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue

    async def _tick(self, pane: str) -> None:
        seen: dict[str, PermissionPrompt] = {}
        for det in self.detectors:
            prompt = det.detect(pane)
            if prompt is not None:
                seen[prompt.id] = prompt
        # New prompts
        for pid, prompt in seen.items():
            if pid not in self._active:
                await self.bus.publish(
                    {"kind": "permission_prompt", "prompt": asdict(prompt)}
                )
        # Resolved prompts
        for pid in list(self._active):
            if pid not in seen:
                await self.bus.publish(
                    {"kind": "permission_prompt_resolved", "id": pid}
                )
        self._active = seen
