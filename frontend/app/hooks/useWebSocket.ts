/** WebSocket hook — connects to AgentX backend for real-time streaming with reconnection. */

import { useEffect, useRef, useCallback, useState } from "react";
import type { WSMessage } from "../lib/types";

const WS_BASE =
  import.meta.env.VITE_WS_URL ??
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`;

const RECONNECT_DELAY = 2000;
const MAX_RECONNECT = 5;

interface UseWebSocketOptions {
  sessionId: string;
  onMessage?: (msg: WSMessage) => void;
}

export type WsStatus = "connecting" | "connected" | "reconnecting" | "offline";

interface UseWebSocketReturn {
  connected: boolean;
  status: WsStatus;
  send: (data: Record<string, unknown>) => void;
  lastMessage: WSMessage | null;
}

export function useWebSocket({
  sessionId,
  onMessage,
}: UseWebSocketOptions): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<number | null>(null);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  // Keep ref current without triggering reconnect
  onMessageRef.current = onMessage;

  useEffect(() => {
    // Don't connect until we have a real session ID — "new" is a placeholder
    // that the backend will reject (404), burning the reconnect budget before
    // the real ID arrives from POST /api/sessions.
    if (!sessionId || sessionId === "new") {
      setStatus("connecting");
      return;
    }
    let cancelled = false;


    function connect() {
      if (cancelled) return;

      const ws = new WebSocket(`${WS_BASE}/${sessionId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setStatus("connected");
        reconnectCountRef.current = 0; // Reset on successful connection
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WSMessage;

          // Handle keepalive ping — respond with pong
          if (msg.type === "ping") {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ action: "pong" }));
            }
            return;
          }

          setLastMessage(msg);
          onMessageRef.current?.(msg);
        } catch {
          console.error("Failed to parse WS message:", event.data);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;

        // Attempt reconnection if not cancelled and under limit
        if (!cancelled && reconnectCountRef.current < MAX_RECONNECT) {
          setStatus("reconnecting");
          reconnectTimerRef.current = window.setTimeout(() => {
            reconnectCountRef.current += 1;
            connect();
          }, RECONNECT_DELAY);
        } else if (!cancelled) {
          setStatus("offline");
        }
      };

      ws.onerror = () => {
        setConnected(false);
        // onclose will fire after onerror and handle reconnection
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
      // Reset reconnect budget so the next real sessionId gets a fresh attempt
      reconnectCountRef.current = 0;
    };
  }, [sessionId]);

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { connected, status, send, lastMessage };
}
