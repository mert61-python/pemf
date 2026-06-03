import { serviceConfig } from "@/services/config";

export type WsMessageHandler = (payload: unknown) => void;

export function connectPemfWebSocket(onMessage: WsMessageHandler, onState?: (connected: boolean) => void) {
  if (typeof WebSocket === "undefined") {
    onState?.(false);
    return () => undefined;
  }

  let socket: WebSocket | null = null;
  let closedByCaller = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const handleMessage = (event: MessageEvent) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      onMessage(event.data);
    }
  };

  const openSocket = () => {
    socket = new WebSocket(serviceConfig.websocketUrl);
    socket.onopen = () => onState?.(true);
    socket.onerror = () => onState?.(false);
    socket.onmessage = handleMessage;
    socket.onclose = () => {
      onState?.(false);
      if (!closedByCaller) {
        reconnectTimer = setTimeout(openSocket, 3000);
      }
    };
  };

  openSocket();

  return () => {
    closedByCaller = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
    socket = null;
  };
}
