from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any, Awaitable, Callable, Protocol

from .event_bus import EventBus
from .types import PermissionPrompt


class _PaneSource(Protocol):
    def capture_pane(self, lines: int = 200) -> str: ...


class _Detector(Protocol):
    def detect(self, pane_text: str) -> PermissionPrompt | None: ...


class _StatusDetector(Protocol):
    def detect(self, pane_text: str) -> dict[str, Any] | None: ...


class PaneWatcher:
    def __init__(
        self,
        tmux: _PaneSource,
        bus: EventBus,
        detectors: list[_Detector],
        status_detector: _StatusDetector | None = None,
        on_status: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        interval: float = 0.25,
    ) -> None:
        self.tmux = tmux
        self.bus = bus
        self.detectors = detectors
        self.status_detector = status_detector
        self.on_status = on_status
        self.interval = interval
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._active: dict[str, PermissionPrompt] = {}  # by id
        self._last_status: dict[str, Any] | None = None

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

        if self.status_detector and self.on_status:
            status = self.status_detector.detect(pane)
            if status is not None and status != self._last_status:
                await self.on_status(status)
                self._last_status = status
