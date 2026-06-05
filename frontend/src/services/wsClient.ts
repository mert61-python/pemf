import { serviceConfig } from "@/services/config";

// ─── Message types from the bridge ───────────────────────────────────────────
export type WsMessageType =
  | "snapshot"
  | "sensor_data"
  | "coil_status"
  | "esp_event"
  | "alarm"
  | "notification"
  | "gateway_status"
  | "stm_status"
  | "session_update"
  | "session_control"
  | "ai_vision";

export interface WsMessage {
  type: WsMessageType;
  coilId?: number;
  data?: any;
  eventType?: string;
  timestamp?: number;
}

export type WsMessageHandler = (message: WsMessage) => void;

// ─── Connection ──────────────────────────────────────────────────────────────
export function connectPemfWebSocket(
  onMessage: WsMessageHandler,
  onState?: (connected: boolean) => void
): () => void {
  if (typeof WebSocket === "undefined") {
    onState?.(false);
    return () => undefined;
  }

  let socket: WebSocket | null = null;
  let closedByCaller = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectDelay = 1000;

  const handleMessage = (event: MessageEvent) => {
    try {
      const msg: WsMessage = JSON.parse(event.data);
      onMessage(msg);
    } catch {
      // non-JSON message — ignore
    }
  };

  const openSocket = () => {
    if (closedByCaller) return;
    try {
      socket = new WebSocket(serviceConfig.websocketUrl);
      socket.onopen = () => {
        reconnectDelay = 1000; // reset backoff on success
        onState?.(true);
      };
      socket.onerror = () => onState?.(false);
      socket.onmessage = handleMessage;
      socket.onclose = () => {
        onState?.(false);
        if (!closedByCaller) {
          reconnectTimer = setTimeout(() => {
            reconnectDelay = Math.min(reconnectDelay * 1.5, 15000);
            openSocket();
          }, reconnectDelay);
        }
      };
    } catch {
      onState?.(false);
      if (!closedByCaller) {
        reconnectTimer = setTimeout(openSocket, reconnectDelay);
      }
    }
  };

  openSocket();

  return () => {
    closedByCaller = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
    socket = null;
  };
}
