import { render, screen } from "@testing-library/react";
import App from "../src/App";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const map: Record<string, any> = {
      "/api/state": {
        cwd: "/Users/test", mode: "default",
        model: "claude-opus-4-7", effort: "high", claude_alive: true,
      },
      "/api/options": {
        models: [{ id: "claude-opus-4-7", label: "Opus 4.7" }],
        efforts: ["low", "high"], modes: ["default", "plan", "bypass"],
      },
      "/api/slash-commands": [],
      "/api/projects": [],
      "/api/sessions": [],
    };
    const u = new URL(url, "http://t");
    return new Response(JSON.stringify(map[u.pathname] ?? null), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }));
  (globalThis as any).WebSocket = class {
    onopen: any; onmessage: any; onclose: any; onerror: any;
    constructor() {}
    send() {} close() { this.onclose?.(); }
  };
});

test("app renders", async () => {
  render(<App />);
  expect(await screen.findByText(/loading…/)).toBeInTheDocument();
});
