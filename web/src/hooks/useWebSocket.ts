import { useCallback, useEffect, useRef, useState } from "react";
import type { ServerEvent } from "../types";

const STALE_MS = 45_000; // 3 missed 15s pings → reconnect

export function useWebSocket(path: string) {
  const [events, setEvents] = useState<ServerEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const pushLocalClear = useCallback(() => {
    setEvents((cur) => [
      ...cur,
      { kind: "chat_event", event: { kind: "clear_marker" } },
    ]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let backoff = 500;
    let staleTimer: ReturnType<typeof setTimeout>;

    function resetStaleTimer(ws: WebSocket) {
      clearTimeout(staleTimer);
      staleTimer = setTimeout(() => {
        ws.close();
      }, STALE_MS);
    }

    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}${path}`);
      wsRef.current = ws;
      ws.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        backoff = 500;
        resetStaleTimer(ws);
      };
      ws.onmessage = (ev) => {
        resetStaleTimer(ws);
        try {
          const data = JSON.parse(ev.data) as ServerEvent;
          if ((data as any).kind === "ping") return;
          setEvents((cur) => [...cur, data]);
        } catch {
          // malformed message — ignore
        }
      };
      ws.onclose = () => {
        clearTimeout(staleTimer);
        if (cancelled) return;
        setConnected(false);
        backoff = Math.min(backoff * 2, 8000);
        setTimeout(connect, backoff);
      };
      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(staleTimer);
      wsRef.current?.close();
    };
  }, [path]);

  return { events, connected, pushLocalClear };
}
