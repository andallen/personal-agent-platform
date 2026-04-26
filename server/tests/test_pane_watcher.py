import asyncio
from dataclasses import dataclass, field

import pytest

from cc_mobile.event_bus import EventBus
from cc_mobile.pane_watcher import PaneWatcher
from cc_mobile.types import PermissionPrompt


@dataclass
class FakeTmux:
    snapshots: list[str] = field(default_factory=list)
    idx: int = 0

    def capture_pane(self, lines: int = 200) -> str:
        if self.idx >= len(self.snapshots):
            return self.snapshots[-1] if self.snapshots else ""
        out = self.snapshots[self.idx]
        self.idx += 1
        return out


@dataclass
class FakeDetector:
    fixed: PermissionPrompt | None
    seen: list[str] = field(default_factory=list)

    def detect(self, pane_text):
        self.seen.append(pane_text)
        return self.fixed


@pytest.mark.asyncio
async def test_watcher_emits_event_when_detector_matches():
    bus = EventBus()
    sub = bus.subscribe()
    prompt = PermissionPrompt(id="x1", kind="bash", target="ls", raw="...")
    tmux = FakeTmux(snapshots=["pane content"])
    watcher = PaneWatcher(tmux=tmux, bus=bus, detectors=[FakeDetector(prompt)], interval=0.05)
    await watcher.start()
    ev = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert ev["kind"] == "permission_prompt"
    assert ev["prompt"]["id"] == "x1"
    await watcher.stop()


@pytest.mark.asyncio
async def test_watcher_emits_resolved_when_match_disappears():
    bus = EventBus()
    sub = bus.subscribe()
    prompt = PermissionPrompt(id="x1", kind="bash", target="ls", raw="...")
    tmux = FakeTmux(snapshots=["with prompt", "no prompt"])
    detector = FakeDetector(prompt)

    async def cycle():
        await watcher.start()
        await asyncio.sleep(0.08)
        # On second tick make detector return None
        detector.fixed = None
        await asyncio.sleep(0.15)
        await watcher.stop()

    watcher = PaneWatcher(tmux=tmux, bus=bus, detectors=[detector], interval=0.05)
    await cycle()

    events: list[dict] = []
    while not sub.empty():
        events.append(sub.get_nowait())
    kinds = [e["kind"] for e in events]
    assert "permission_prompt" in kinds
    assert "permission_prompt_resolved" in kinds


@pytest.mark.asyncio
async def test_watcher_does_not_re_emit_same_prompt_twice():
    bus = EventBus()
    sub = bus.subscribe()
    prompt = PermissionPrompt(id="stable", kind="bash", target="ls", raw="...")
    tmux = FakeTmux(snapshots=["a", "a", "a"])
    watcher = PaneWatcher(tmux=tmux, bus=bus, detectors=[FakeDetector(prompt)], interval=0.05)
    await watcher.start()
    await asyncio.sleep(0.2)
    await watcher.stop()
    seen_ids = []
    while not sub.empty():
        ev = sub.get_nowait()
        if ev["kind"] == "permission_prompt":
            seen_ids.append(ev["prompt"]["id"])
    assert seen_ids == ["stable"]
