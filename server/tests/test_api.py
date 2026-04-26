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


class FullFakeMgr:
    def __init__(self):
        self.calls: list[tuple] = []
        self._state = {
            "cwd": "/Users/andrewallen",
            "mode": "default",
            "model": None,
            "effort": None,
            "claude_alive": True,
        }

    async def current_state(self):
        return dict(self._state)

    async def send_user_message(self, text):
        self.calls.append(("send_user_message", text))

    async def interrupt(self):
        self.calls.append(("interrupt",))

    async def set_mode(self, mode):
        self.calls.append(("set_mode", mode))
        self._state["mode"] = mode

    async def set_model(self, model):
        self.calls.append(("set_model", model))
        self._state["model"] = model

    async def set_effort(self, effort):
        self.calls.append(("set_effort", effort))
        self._state["effort"] = effort

    async def clear(self):
        self.calls.append(("clear",))

    async def compact(self):
        self.calls.append(("compact",))

    async def resume(self, session_id):
        self.calls.append(("resume", session_id))

    async def switch_project(self, cwd):
        self.calls.append(("switch_project", cwd))
        self._state["cwd"] = cwd

    async def decide_permission(self, prompt_id, decision):
        self.calls.append(("decide_permission", prompt_id, decision))

    async def list_recent_projects(self):
        return [{"cwd": "/Users/andrewallen", "name": "andrewallen", "mtime": 0.0}]

    async def list_recent_sessions(self, cwd):
        return [{"id": "abc", "mtime": 0.0, "size": 0}]


class FakeOptions:
    def get_models(self): return [{"id": "claude-opus-4-7", "label": "Opus 4.7"}]
    def get_efforts(self): return ["low", "medium", "high"]
    def get_modes(self): return ["default", "plan"]
    def get_slash_commands(self): return [{"name": "/clear", "description": "..."}]


@pytest.mark.asyncio
async def test_post_send_calls_manager():
    mgr = FullFakeMgr()
    app = build_app(manager=mgr, bus=EventBus(), static_dir=None, options=FakeOptions())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/send", json={"text": "hi"})
    assert r.status_code == 200
    assert ("send_user_message", "hi") in mgr.calls


@pytest.mark.asyncio
async def test_post_interrupt():
    mgr = FullFakeMgr()
    app = build_app(manager=mgr, bus=EventBus(), static_dir=None, options=FakeOptions())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/interrupt")
    assert r.status_code == 200
    assert ("interrupt",) in mgr.calls


@pytest.mark.asyncio
async def test_post_mode_model_effort():
    mgr = FullFakeMgr()
    app = build_app(manager=mgr, bus=EventBus(), static_dir=None, options=FakeOptions())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.post("/api/mode", json={"value": "plan"})
        await c.post("/api/model", json={"value": "claude-sonnet-4-6"})
        await c.post("/api/effort", json={"value": "xhigh"})
    assert ("set_mode", "plan") in mgr.calls
    assert ("set_model", "claude-sonnet-4-6") in mgr.calls
    assert ("set_effort", "xhigh") in mgr.calls


@pytest.mark.asyncio
async def test_post_clear_compact_resume_project_permission():
    mgr = FullFakeMgr()
    app = build_app(manager=mgr, bus=EventBus(), static_dir=None, options=FakeOptions())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.post("/api/clear")
        await c.post("/api/compact")
        await c.post("/api/resume", json={"session_id": "abc"})
        await c.post("/api/project", json={"cwd": "/x"})
        await c.post("/api/permission", json={"id": "p1", "decision": "allow_once"})
    assert ("clear",) in mgr.calls
    assert ("compact",) in mgr.calls
    assert ("resume", "abc") in mgr.calls
    assert ("switch_project", "/x") in mgr.calls
    assert ("decide_permission", "p1", "allow_once") in mgr.calls


@pytest.mark.asyncio
async def test_get_lists_and_options():
    mgr = FullFakeMgr()
    app = build_app(manager=mgr, bus=EventBus(), static_dir=None, options=FakeOptions())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        proj = (await c.get("/api/projects")).json()
        sess = (await c.get("/api/sessions", params={"cwd": "/x"})).json()
        opts = (await c.get("/api/options")).json()
        slash = (await c.get("/api/slash-commands")).json()
    assert proj[0]["cwd"] == "/Users/andrewallen"
    assert sess[0]["id"] == "abc"
    assert "models" in opts and "efforts" in opts and "modes" in opts
    assert slash[0]["name"] == "/clear"
