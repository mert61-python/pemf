// Author: mertaygn, cglrgrkn
/**
 * A-47 / Y2 · 1-D inceleme i2-F-2 — canlı veri BAĞLAMI düzeyinde otomatik termal STOP YOK.
 * Ölçülen körlük: LiveDataContext testleri en çok 31 °C besler → bağlamın `sensor_data` dalına geri eklenen
 * "ölçülen > 48 °C → durdurma isteği" bütün suite'lerde yeşil kalıyordu. GERÇEK `LiveDataProvider`, sahte yalnız WS/ağ.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api", websocketUrl: "ws://192.168.1.5:8000/ws", apiToken: "" },
  loadStoredApiToken: jest.fn(async () => undefined),
}));
jest.mock("@/services/discovery", () => ({ discoverBackend: jest.fn(async () => null) }));
jest.mock("@/hooks/useNetworkReachability", () => ({ useNetworkReachability: () => undefined }));
jest.mock("@/hooks/useForegroundReconnect", () => ({ useForegroundReconnect: () => undefined }));
const mockWs: { onMessage?: (m: any) => void; onState?: (c: boolean) => void } = {};
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: any, onState: any) => {
    mockWs.onMessage = onMessage;
    mockWs.onState = onState;
    return () => undefined;
  },
}));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { Text } from "react-native";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";

const { apiPost } = jest.requireMock("@/services/apiClient");

function Probe() {
  const { snapshot } = useLiveData();
  return <Text testID="n">{String((snapshot.coils ?? []).length)}</Text>;
}

it("KRİTİK: ölçülen 49-120 °C telemetrisi bağlamda HİÇBİR istek tetiklemez (A-47)", async () => {
  render(<LiveDataProvider><Probe /></LiveDataProvider>);
  await act(async () => { await Promise.resolve(); });
  await act(async () => { mockWs.onState?.(true); });
  (apiPost as jest.Mock).mockClear();
  for (const t of [49, 63, 120]) {
    for (const id of [6, 7]) {
      const data = { objectTemp: t, magneticMt: 1.8, ambientTemp: 25, currentA: 0, measuredFields: ["objectTemp", "magneticMt"] };
      await act(async () => { mockWs.onMessage?.({ type: "sensor_data", coilId: id, data }); });
      await act(async () => { mockWs.onMessage?.({ type: "coil_status", coilId: id, data: { ...data, id, running: true, connected: true } }); });
    }
  }
  expect(apiPost).not.toHaveBeenCalled();
});
