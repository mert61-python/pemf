export const serviceConfig = {
  apiBaseUrl: process.env.EXPO_PUBLIC_PEMF_API_BASE_URL ?? "http://127.0.0.1:8000/api",
  websocketUrl: process.env.EXPO_PUBLIC_PEMF_WS_URL ?? "ws://127.0.0.1:5555/"
};
