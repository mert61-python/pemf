// Author: mertaygn, cglrgrkn
/**
 * D6.25 (B-6.16) — Canlı E-Alanı "canlı / duraklandı" rozeti tazeliği verinin ALINIŞ zamanına göre hesaplanır, backend damgasıyla
 * yerel saat KARŞILAŞTIRILMAZ.
 * =================================================================================================================================
 * ÖLÇÜLEN KUSUR (HEAD ebf1c3fe): `EFieldBar.tsx` `stale = e.ts > 0 && now / 1000 - e.ts > 5` — `e.ts` SUNUCU saatiyle (`efield_live`
 * `time.time()`), `now` İSTEMCİ saatiyle. İstemci ayrı makinede (LAN tableti) ya da saat kaymışken: sunucu GERİDE → yeni gelmiş veri
 * hemen "duraklandı"; sunucu İLERİDE → 30 sn hiç yeni veri gelmese de "canlı" (donmuş sayı canlı sanılır — barın varlık nedeni).
 * SÖZLEŞME: yeni hesap = damga DEĞİŞTİ; aynı damgalı yeniden yayın (ör. başka bir olayla gelen tam snapshot) veriyi TAZELEMEZ.
 * GERÇEK: LiveDataProvider (WS `snapshot` iletisi → `snapshot.eField`), EFieldBar, katalog. Sahte (en alt kat): WS istemcisi, apiClient,
 * keşif, ağ kancaları; saat jest sahte zamanlayıcısı (Date.now dahil).
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

/** `servers/efield_live.compute` dönüş şekli (alan kümesi); `ts` SUNUCU saatiyle (epoch sn). */
const eField = (sunucuTs: number) => ({
  healthy: 0.02, cancer: 0.05, avg: 0.035, activeCoils: 2, achievedB_T: 0.0025, dutySum: 0.8, ts: sunucuTs,
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

const simdiSn = () => Date.now() / 1000;

beforeEach(() => {
  jest.useFakeTimers({ now: new Date("2026-10-28T10:00:00Z") });
});
afterEach(() => {
  jest.useRealTimers();
});

async function kur(e: unknown) {
  const u = render(
    <LiveDataProvider>
      <EFieldBar />
    </LiveDataProvider>,
  );
  await act(async () => {});
  await act(async () => { mockWs.onState?.(true); });
  await act(async () => { mockWs.onMessage?.(snapshot(e)); });
  expect(u.queryByText("Tümör")).not.toBeNull(); // ARA: bar GERÇEK sağlayıcıdan gelen veriyle çizildi
  return u;
}
const ilerlet = async (ms: number) => {
  await act(async () => { jest.advanceTimersByTime(ms); });
};
const gonder = async (e: unknown) => {
  await act(async () => { mockWs.onMessage?.(snapshot(e)); });
};

it("KRİTİK: sunucu saati 60 sn GERİDE — az önce ALINAN veri 'canlı' (eski damga tazeliği belirlemez)", async () => {
  const u = await kur(eField(simdiSn() - 60));
  expect(u.queryByText(CANLI)).not.toBeNull();
  expect(u.queryByText(DURAKLADI)).toBeNull();
});

it("KRİTİK: sunucu saati 60 sn İLERİDE — 30 sn yeni veri ALINMADIYSA 'duraklandı' (donmuş sayı canlı sanılmaz)", async () => {
  const u = await kur(eField(simdiSn() + 60));
  expect(u.queryByText(CANLI)).not.toBeNull(); // ARA: alındığı an canlı
  await ilerlet(30_000);
  expect(u.queryByText(DURAKLADI)).not.toBeNull();
  expect(u.queryByText(CANLI)).toBeNull();
});

it("KARŞIT: damgası DEĞİŞEN yeni hesaplar 2 sn arayla gelirse (sunucu ileride) 30 sn sonra hâlâ 'canlı'", async () => {
  let ts = simdiSn() + 60;
  const u = await kur(eField(ts));
  for (let i = 0; i < 15; i++) {
    await ilerlet(2_000);
    ts += 2;
    await gonder(eField(ts));
  }
  expect(u.queryByText(CANLI)).not.toBeNull();
});

it("KRİTİK: AYNI damgalı yeniden yayın (yeni nesne) veriyi TAZELEMEZ — 6 sn sonra 'duraklandı'", async () => {
  const ts = simdiSn() - 60;
  const u = await kur(eField(ts));
  for (let i = 0; i < 3; i++) {
    await ilerlet(2_000);
    await gonder(eField(ts)); // başka bir olayla gelen tam snapshot: aynı (eski) hesap
  }
  expect(u.queryByText(DURAKLADI)).not.toBeNull();
});

it("SINIR: 5 sn eşiği — 4 sn'de 'canlı', 7 sn'de 'duraklandı'", async () => {
  const u = await kur(eField(simdiSn()));
  await ilerlet(4_000);
  expect(u.queryByText(CANLI)).not.toBeNull();
  await ilerlet(3_000);
  expect(u.queryByText(DURAKLADI)).not.toBeNull();
});
