import { useEffect, useRef, useState } from "react";
import type { ServerEvent } from "../types";

export function useWebSocket(path: string) {
  const [events, setEvents] = useState<ServerEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let backoff = 500;

    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}${path}`);
      wsRef.current = ws;
      ws.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        backoff = 500;
      };
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as ServerEvent;
          setEvents((cur) => [...cur, data]);
        } catch {
          // malformed message — ignore
        }
      };
      ws.onclose = () => {
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
      wsRef.current?.close();
    };
  }, [path]);

  return { events, connected };
}
