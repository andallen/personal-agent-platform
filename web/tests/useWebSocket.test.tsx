import { act, renderHook } from "@testing-library/react";
import { useWebSocket } from "../src/hooks/useWebSocket";

class MockWS {
  static instances: MockWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;
  constructor(public url: string) {
    MockWS.instances.push(this);
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.();
    }, 0);
  }
  send() {}
  close() {
    this.onclose?.();
  }
}

beforeEach(() => {
  MockWS.instances = [];
  (globalThis as any).WebSocket = MockWS;
});

test("collects events delivered through onmessage", async () => {
  const { result } = renderHook(() => useWebSocket("/ws"));
  await act(async () => {
    await new Promise((r) => setTimeout(r, 1));
    MockWS.instances[0].onmessage?.({
      data: JSON.stringify({ kind: "state", state: { cwd: "/x" } }),
    });
  });
  expect(result.current.events.at(-1)).toEqual({
    kind: "state",
    state: { cwd: "/x" },
  });
});
