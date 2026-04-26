import { vi } from "vitest";
import { api } from "../src/api";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    return new Response(JSON.stringify({ url, method: init?.method ?? "GET" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }));
});

afterEach(() => vi.unstubAllGlobals());

test("send posts JSON to /api/send", async () => {
  const r = await api.send("hi");
  expect((r as any).url).toBe("/api/send");
  expect((r as any).method).toBe("POST");
  const body = JSON.parse((fetch as any).mock.calls[0][1].body);
  expect(body).toEqual({ text: "hi" });
});

test("setEffort posts {value}", async () => {
  await api.setEffort("xhigh");
  const body = JSON.parse((fetch as any).mock.calls[0][1].body);
  expect(body).toEqual({ value: "xhigh" });
});

test("getState GETs /api/state", async () => {
  const r = await api.getState();
  expect((r as any).url).toBe("/api/state");
  expect((r as any).method).toBe("GET");
});
