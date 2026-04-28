import asyncio
import pytest
from cc_mobile.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_and_subscribe_receives_event():
    bus = EventBus()
    sub = bus.subscribe()
    await bus.publish({"kind": "ping"})
    event = await asyncio.wait_for(sub.get(), timeout=0.5)
    assert event == {"kind": "ping"}


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive():
    bus = EventBus()
    s1, s2 = bus.subscribe(), bus.subscribe()
    await bus.publish({"kind": "x"})
    e1 = await asyncio.wait_for(s1.get(), timeout=0.5)
    e2 = await asyncio.wait_for(s2.get(), timeout=0.5)
    assert e1 == e2 == {"kind": "x"}


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    sub = bus.subscribe()
    bus.unsubscribe(sub)
    await bus.publish({"kind": "x"})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sub.get(), timeout=0.1)
