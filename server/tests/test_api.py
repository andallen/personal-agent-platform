import pytest
from httpx import ASGITransport, AsyncClient

from cc_mobile.api import build_app
from cc_mobile.event_bus import EventBus


class FakeMgr:
    async def current_state(self):
        return {
            "cwd": "/Users/andrewallen",
            "mode": "default",
            "model": "claude-opus-4-7",
            "effort": "high",
            "claude_alive": True,
        }


@pytest.mark.asyncio
async def test_get_state_returns_current_state():
    app = build_app(manager=FakeMgr(), bus=EventBus(), static_dir=None, options=None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    assert body["cwd"] == "/Users/andrewallen"
    assert body["model"] == "claude-opus-4-7"
