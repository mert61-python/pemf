// Author: mertaygn, cglrgrkn
/**
 * Y212 · S-D67.11 (sahip, 2026-10-28) — Kontrol kartı açılıştan SONRA başka istemcide / AI Pro'da başlatılan seansı BENİMSER.
 * ===================================================================================================================
 * ÖLÇÜLEN (L1-7.10 sondası, HEAD `ebf1c3fe`): açılışta `/session/active` boş; ardından WS `activeTreatment.isActive=true` + bobin 1-2
 * çalışıyor → 30 sn sonra kart hâlâ "Seans Bekleniyor" (yoklama YALNIZ yerel seans aktifken). L1-7.10 yalnız bant metnini düzeltti.
 * SÖZLEŞME: WS'te seans YOK → VAR geçişinde kart boştaysa seans WS değerleriyle benimsenir — yeni istek YOK (mutabakat döngüsü `isActive`
 * ile kurulur). Kartın Durdur'u AYNI yol (`/session/stop`); yerel durdurmadan sonra WS'te seans hâlâ görünse de (geç tik) GERİ
 * benimsenmez. Açılıştaki durum `/session/active`ten gelir — L1-7.10 bandı (açılışta WS etkin, yerel boş) AYNEN kalır.
 * GERÇEK: `ControlScreen`, `useSessionControl`, `apiClient`, `SessionProgressCard`; sahte olan `fetch` ve bağlamlar.
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api", bridgeBaseUrl: "http://127.0.0.1:65530/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
let mockSnap: any;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live", haveRealData: true,
    telemetryStale: false, sensorHistory: {}, unreadCount: 0, markAllRead: jest.fn(),
    clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operator: "Dr. X" }) }));
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => ({ navigate: jest.fn(), goTo: jest.fn() }) }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { ControlScreen } from "@/screens/ControlScreen";

const F: any = require("./__fixtures__/kayitGorunumu.D189.json");
const yanit = (o: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

let backendSeans = false;
let cagrilar: string[] = [];

beforeEach(() => {
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  backendSeans = false;
  cagrilar = [];
  (global as any).fetch = jest.fn((url: string, init?: { method?: string }) => {
    const u = String(url);
    cagrilar.push(`${init?.method ?? "GET"} ${u.replace(/^.*\/api/, "")}`);
    if (u.endsWith("/session/active")) return yanit(backendSeans ? { is_active: true, db_session_id: 77, elapsed_sec: 0 } : { is_active: false });
    if (u.endsWith("/session/stop")) {
      backendSeans = false;
      return yanit({ status: "success" });
    }
    return yanit({ status: "success" });
  });
});

const snap = (wsAktif: boolean) => ({
  gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
  patient: { name: "", species: "", breed: "", owner: "" },
  activeTreatment: wsAktif ? F.canliElle : { ...F.canliElle, isActive: false },
  notifications: [],
  coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true, running: wsAktif && id <= 2 })),
});

async function ekranSonraUzakBaslat() {
  mockSnap = snap(false);
  const u = render(<ControlScreen />);
  await act(async () => {});
  await act(async () => {});
  expect(u.queryByText("Seans Bekleniyor")).not.toBeNull(); // ARA: açılışta seans yok
  const acilis = cagrilar.filter((c) => c.endsWith("/session/active")).length;
  backendSeans = true; // başka istemci / AI Pro başlattı
  mockSnap = snap(true);
  u.rerender(<ControlScreen />);
  await act(async () => {});
  return { u, acilis };
}

it("KRİTİK: açılıştan SONRA uzakta başlatılan seans kartta BENİMSENİR — 'Seans Bekleniyor' kalmaz, yeni istek YOK", async () => {
  const { u, acilis } = await ekranSonraUzakBaslat();
  expect(u.queryByText("Seans Bekleniyor")).toBeNull();
  expect(u.queryByText("AKTİF SEANS")).not.toBeNull();
  expect(u.queryByText(/bu kartın dışında başlatıldı/)).toBeNull(); // benimsendi → "kart dışında" bandı yok
  expect(cagrilar.filter((c) => c.endsWith("/session/active")).length).toBe(acilis); // benimseme WS değerinden
});

it("KRİTİK: benimsenen seans kartın Durdur'uyla AYNI yoldan (`/session/stop`) durdurulur", async () => {
  const { u } = await ekranSonraUzakBaslat();
  await act(async () => {
    fireEvent.press(u.getByLabelText("Seansı durdur"));
  });
  await act(async () => {});
  expect(cagrilar).toContain("POST /session/stop");
  expect(u.getByLabelText("Tüm bobinleri acil durdur")).toBeTruthy(); // ACİL DURDUR düğmesi aynı yerde
});

it("KARŞIT: yerel durdurmadan SONRA WS'te seans hâlâ görünse de (geç tik) kart seansı GERİ benimsemez", async () => {
  const { u } = await ekranSonraUzakBaslat();
  await act(async () => {
    fireEvent.press(u.getByLabelText("Seansı durdur"));
  });
  await act(async () => {});
  expect(u.queryByText("Seans Bekleniyor")).not.toBeNull();
  mockSnap = { ...snap(true), activeTreatment: { ...F.canliElle, elapsedSec: 3 } }; // geç tik: hâlâ etkin
  u.rerender(<ControlScreen />);
  await act(async () => {});
  expect(u.queryByText("Seans Bekleniyor")).not.toBeNull();
});
