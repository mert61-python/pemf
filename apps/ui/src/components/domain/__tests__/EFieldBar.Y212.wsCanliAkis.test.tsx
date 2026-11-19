// Author: mertaygn, cglrgrkn
/**
 * Y212 · S-D67.13 (sahip, 2026-10-28) — seans sırasında Canlı E-Alanı WS bağlıyken de AKAR; "duraklandı" yanıltmaz.
 * =================================================================================================================================
 * ÖLÇÜLEN KUSUR (D6.25 ürün bulgusu, HEAD 8b002fc0): backend E'yi 2 Hz hesaplayıp yalnız önbelleğe yazıyordu; değer istemciye YALNIZ tam
 * snapshot'la (WS bağlanınca) gidiyordu. WS ayaktayken HTTP yoklaması koşmadığı için seans boyunca bar 5 sn sonra "duraklandı" diyordu
 * (hesap sürerken). Artık her yeni hesap `efield_update` iletisiyle gelir; hesap bitince (seans / bağlam yok) BİR KEZ `null` → bar gizlenir.
 * GERÇEK: LiveDataProvider (WS iletisi → `snapshot.eField`), EFieldBar, katalog. Sahte (en alt kat): WS istemcisi, apiClient, keşif, ağ
 * kancaları; saat jest sahte zamanlayıcısı. İleti dizisinin biçimi backend kapısında (`tests/test_efield_canli_WS_yayini_Y212.py`) ölçülür.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
  platformAlert: jest.fn(),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", websocketUrl: "ws://127.0.0.1:8000/ws", apiToken: "" },
  loadStoredApiToken: jest.fn(async () => undefined),
}));
jest.mock("@/services/discovery", () => ({ discoverBackend: jest.fn(async () => null) }));
jest.mock("@/hooks/useNetworkReachability", () => ({ useNetworkReachability: () => undefined }));
jest.mock("@/hooks/useForegroundReconnect", () => ({ useForegroundReconnect: () => undefined }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
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
import { LiveDataProvider } from "@/context/LiveDataContext";
import { EFieldBar } from "@/components/domain/EFieldBar";

const CANLI = "● canlı";
const DURAKLADI = "duraklandı";

const eField = (ts: number, cancer = 0.05) => ({
  healthy: 0.02, cancer, avg: 0.035, activeCoils: 2, achievedB_T: 0.0025, dutySum: 0.8, ts,
});
const snapshot = (e: unknown) => ({
  type: "snapshot",
  data: {
    stm: "online", gateway: "online", mqtt: "devre_disi",
    activeTreatment: { isActive: true, mode: "Manuel" },
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true, running: id <= 2 })),
    notifications: [],
    eField: e,
  },
});

beforeEach(() => {
  jest.useFakeTimers({ now: new Date("2026-10-28T10:00:00Z") });
});
afterEach(() => {
  jest.useRealTimers();
});

async function kur() {
  const u = render(
    <LiveDataProvider>
      <EFieldBar />
    </LiveDataProvider>,
  );
  await act(async () => {});
  await act(async () => { mockWs.onState?.(true); });
  await act(async () => { mockWs.onMessage?.(snapshot(eField(Date.now() / 1000))); });
  expect(u.queryByText("Tümör")).not.toBeNull(); // ARA: bar ilk tam snapshot'la çizildi
  return u;
}
const ilerlet = async (ms: number) => {
  await act(async () => { jest.advanceTimersByTime(ms); });
};
const efieldUpdate = async (data: unknown) => {
  await act(async () => { mockWs.onMessage?.({ type: "efield_update", data }); });
};

it("KRİTİK: seans sürerken 2 Hz `efield_update` gelir → 30 sn sonra hâlâ 'canlı' ve SON değer çizilir (tam snapshot yok)", async () => {
  const u = await kur();
  let ts = Date.now() / 1000;
  for (let i = 0; i < 60; i++) {
    await ilerlet(500);
    ts += 0.5;
    await efieldUpdate(eField(ts, 0.05 + i / 10_000));
  }
  expect(u.queryByText(CANLI)).not.toBeNull();
  expect(u.queryByText(DURAKLADI)).toBeNull();
  expect(u.queryByText("0,0559")).not.toBeNull(); // son hesap (i = 59) — değer gerçekten iletiden geldi
});

it("KRİTİK: hesap bitince gelen `efield_update null` barı GİZLER (seans bitti — eski değer canlı gibi kalmaz)", async () => {
  const u = await kur();
  await efieldUpdate(null);
  expect(u.queryByText("Tümör")).toBeNull();
  expect(u.queryByText(CANLI)).toBeNull();
});

it("KARŞIT: `efield_update` gelmezse (hesap durdu) 'duraklandı' kuralı aynen işler", async () => {
  const u = await kur();
  await ilerlet(6_000);
  expect(u.queryByText(DURAKLADI)).not.toBeNull();
});
