let defaultHost = "127.0.0.1";
if (typeof window !== "undefined" && window.location && window.location.hostname) {
  defaultHost = window.location.hostname;
}

export let serviceConfig = {
  // REST API — FastAPI server (port 8000)
  apiBaseUrl: process.env.EXPO_PUBLIC_PEMF_API_BASE_URL ?? `http://${defaultHost}:8000/api`,
  // WebSocket — frontend_bridge (port 5050)
  websocketUrl: process.env.EXPO_PUBLIC_PEMF_WS_URL ?? `ws://${defaultHost}:5050/ws`,
  // HTTP snapshot fallback (same bridge, different port)
  bridgeBaseUrl: process.env.EXPO_PUBLIC_PEMF_BRIDGE_URL ?? `http://${defaultHost}:5050/api`,
};

export const updateServiceConfig = (ipAddress: string) => {
  serviceConfig = {
    apiBaseUrl: `http://${ipAddress}:8000/api`,
    websocketUrl: `ws://${ipAddress}:5050/ws`,
    bridgeBaseUrl: `http://${ipAddress}:5050/api`
  };
};
