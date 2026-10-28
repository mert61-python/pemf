// Author: mertaygn, cglrgrkn
/**
 * L1-7.11 (O-9.1 · DALGA-1 §7) — açılış splash'inde (AuthGate `loading`, tavan `HYDRATE_SPLASH_CEILING_MS` = 6 sn) bobin çalışırken
 * ACİL DURDUR VAR ve basınca STOP isteği GİDER.
 * =====================================================================================================================
 * ÖLÇÜLEN KUSUR (HEAD `ebf1c3fe`, `PemfApp.tsx:84-91`): splash yalnız `ActivityIndicator` çiziyordu; uygulama bobinler çalışırken yeniden
 * açılırsa ≤ 6 sn durdurma kontrolü yoktu (Karşılama / Giriş ekranlarında A-58 / Y23 ile `GlobalEmergencyStop` VAR). Fiziksel / mobil yol
 * bu sürede yazılımın sorumluluğunu kaldırmaz.
 * SÖZLEŞME: splash GERÇEK `GlobalEmergencyStop`'u çizer (görünürlük kuralı kabukla / Karşılama ile AYNI: bobin çalışıyor / seans / STM
 * belirsiz / teyitsiz; oturuma / yüklemeye / kataloğa bağlı DEĞİL — Ö.4-Y8). Basış GERÇEK `performEmergencyStop`'u koşar: STOP yolları
 * (bridge `fetch` + `/hardware/emergency_stop` + `stop_all_coils` + `/session/stop`) gider. Boşta düğme YOK (gürültü yok).
 * GERÇEK: `AuthGate`, `GlobalEmergencyStop`, `performEmergencyStop`; sahte olan bağlamlar, `apiPost` ve `fetch` (ağ yok).
 * ⚠️ MUTASYON: splash'ten GES çıkarılırsa KRİTİK; GES koşulsuz / sabit "çalışıyor" çizilirse KARŞIT KIRMIZI.
 */
let mockAuth: any;
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => mockAuth,
  AuthProvider: ({ children }: any) => children,
}));
let mockSnap: any;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnap }),
  LiveDataProvider: ({ children }: any) => children,
}));
jest.mock("@/context/EntitlementContext", () => ({ EntitlementProvider: ({ children }: any) => children }));
jest.mock("@/components/ui/AppShell", () => ({ AppShell: ({ children }: any) => children }));
jest.mock("@/screens/AuthScreen", () => {
  const R = require("react");
  const { Text: T } = require("react-native");
  return { AuthScreen: () => R.createElement(T, null, "giris-ekrani") };
});
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api", bridgeBaseUrl: "http://127.0.0.1:65530/api", apiToken: "" },
}));
const mockApiPost = jest.fn(async () => null);
jest.mock("@/services/apiClient", () => ({
  apiPost: (...a: unknown[]) => (mockApiPost as any)(...a),
  apiGet: jest.fn(async () => null),
  authHeaders: () => ({}),
  platformAlert: jest.fn(),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { AuthGate } from "@/PemfApp";

void React;

const calisan = { stm: "online", coils: [{ id: 1, running: true, connected: true }], activeTreatment: { isActive: false } };
const bosta = { stm: "online", coils: [{ id: 1, running: false, connected: true }], activeTreatment: { isActive: false } };

beforeEach(() => {
  mockApiPost.mockClear();
  (global as any).fetch = jest.fn(async () => ({ ok: true, status: 200, json: async () => ({ confirmed: true }) }));
  mockAuth = { session: null, loading: true, hesapEkleniyor: false, hesapEklemeVazgec: jest.fn() };
});

it("KRİTİK: splash (loading) sırasında bobin çalışırken ACİL DURDUR düğmesi ekranda", async () => {
  mockSnap = calisan;
  const u = render(<AuthGate />);
  await act(async () => {});
  expect(u.queryByText("giris-ekrani")).toBeNull(); // aparat: gerçekten splash
  expect(u.queryByLabelText("Acil durdur")).not.toBeNull();
});

it("KRİTİK: splash'teki ACİL DURDUR'a basınca STOP istekleri GİDER (bridge + emergency_stop + stop_all_coils + session/stop)", async () => {
  mockSnap = calisan;
  const u = render(<AuthGate />);
  await act(async () => {});
  await act(async () => {
    fireEvent.press(u.getByLabelText("Acil durdur"));
  });
  for (let i = 0; i < 5; i++) await act(async () => {});
  const fetchUrl = ((global as any).fetch as jest.Mock).mock.calls.map((c) => String(c[0]));
  expect(fetchUrl).toContain("http://127.0.0.1:65530/api/hardware/emergency_stop");
  const yollar = mockApiPost.mock.calls.map((c: any[]) => String(c[0]));
  expect(yollar).toEqual(expect.arrayContaining(["/hardware/emergency_stop", "/hardware/command", "/session/stop"]));
  const komut = mockApiPost.mock.calls.find((c: any[]) => c[0] === "/hardware/command") as any[];
  expect(komut[1]).toEqual({ command: "stop_all_coils", params: {} });
});

it("KRİTİK (web — masaüstü arayüzü): splash'teki ACİL DURDUR platforma bağlı DEĞİL", async () => {
  // D67 orkestratör kolu: jest ön ayarı Platform.OS = "ios" → GES'i yalnız web'de gizleyen mutant YAŞIYORDU (masaüstü = web).
  const { Platform } = require("react-native");
  const eski = Platform.OS;
  Object.defineProperty(Platform, "OS", { value: "web", configurable: true, writable: true });
  try {
    mockSnap = calisan;
    const u = render(<AuthGate />);
    await act(async () => {});
    expect(u.queryByText("giris-ekrani")).toBeNull();
    expect(u.queryByLabelText("Acil durdur")).not.toBeNull();
  } finally {
    Object.defineProperty(Platform, "OS", { value: eski, configurable: true, writable: true });
  }
});

it("KARŞIT: splash'te hiçbir şey çalışmıyorken düğme YOK (gürültü yok)", async () => {
  mockSnap = bosta;
  const u = render(<AuthGate />);
  await act(async () => {});
  expect(u.queryByLabelText("Acil durdur")).toBeNull();
});

it("KARŞIT: yükleme bitince (oturum yok) splash yerine Giriş ekranı gelir — GES orada AuthScreen'in kendi işi", async () => {
  mockSnap = calisan;
  mockAuth = { ...mockAuth, loading: false };
  const u = render(<AuthGate />);
  await act(async () => {});
  expect(u.queryByText("giris-ekrani")).not.toBeNull();
});
