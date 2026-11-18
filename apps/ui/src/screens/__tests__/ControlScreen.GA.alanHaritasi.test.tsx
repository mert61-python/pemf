// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A3 — Kontrol ekranında "Alan haritası" kartı: kart VAR, varsayılan KAPALI (abonelik yok), ACİL DURDUR düğmesi kartın
 * ÖNÜNDE (kart sekme içeriğinin altında — düğmenin yeri DEĞİŞMEZ) ve kart AÇIKKEN de ACİL DURDUR aynı dört durdurma isteğini gönderir.
 * Aparat: ControlScreen.IG634_635.acilDurdurErisimi.test.tsx (gerçek ekran, sahte fetch).
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", bridgeBaseUrl: "http://127.0.0.1:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
let mockSnap: Record<string, unknown>;
const mockAlan: { harita: unknown; abone: jest.Mock } = { harita: null, abone: jest.fn() };
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live", haveRealData: true,
    telemetryStale: false, sensorHistory: {}, unreadCount: 0, markAllRead: jest.fn(),
    clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
    donanimBelirsiz: false, alanHaritasi: mockAlan.harita, alanAbone: mockAlan.abone,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operator: "Dr. X" }),
  useOperatorOptional: () => null,
}));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({
    navigate: jest.fn(), goTo: jest.fn(), navigateTo: jest.fn(),
    selectedPatient: mockHasta, setSelectedPatient: jest.fn(),
  }),
}));
let mockHasta: { id: string; name: string } | null = null;
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { ControlScreen } from "@/screens/ControlScreen";

const cagrilar: string[] = [];
let seansAktif = false;
let stopAsili = false;
const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });
const ESTOP_DORTLU = ["/hardware/command", "/hardware/emergency_stop", "/hardware/emergency_stop", "/session/stop"];

const bobinler = (calisan: number[]) =>
  [1, 2, 3, 4, 5, 6, 7].map((id) => ({
    id, running: calisan.includes(id), connected: true, stm32Driven: true, frequencyHz: 0, dutyCycle: 0,
    objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [],
  }));

beforeEach(() => {
  cagrilar.length = 0;
  seansAktif = false;
  stopAsili = false;
  mockHasta = null;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  jest.spyOn(console, "error").mockImplementation(() => {});
  (global as { fetch: unknown }).fetch = jest.fn((url: string) => {
    const yol = String(url).replace("http://127.0.0.1:8000/api", "");
    cagrilar.push(yol);
    if (yol === "/session/active")
      return yanit(seansAktif ? { is_active: true, mode: "Manuel", frequency: 50, intensity: 1, duration_minutes: 30, elapsed_sec: 10 } : { is_active: false });
    if (yol === "/session/stop" && stopAsili) return new Promise(() => {});
    if (yol === "/hardware/emergency_stop") return yanit({ confirmed: true, status: "success" });
    return yanit({ status: "success" });
  });
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
    patient: null,
    activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
    notifications: [],
    coils: bobinler([1]),
    system: {}, sessions: [],
  };
});
afterEach(() => jest.restoreAllMocks());

const durdurmalar = () => cagrilar.filter((y) => /\/hardware\/emergency_stop|\/hardware\/command|\/session\/stop/.test(y)).sort();

async function ekran() {
  const u = render(<ControlScreen />);
  await act(async () => {});
  return u;
}

describe("GA — alan haritası kartı kontrol akışını ETKİLEMEZ", () => {
  beforeEach(() => {
    mockAlan.harita = null;
    mockAlan.abone = jest.fn();
  });

  it("KRİTİK: kart var, varsayılan KAPALI; ACİL DURDUR kartın ÖNÜNDE", async () => {
    const u = await ekran();
    expect(u.getByTestId("alan-haritasi-karti")).toBeTruthy();
    expect(mockAlan.abone).not.toHaveBeenCalled();
    const agac = JSON.stringify(u.toJSON());
    const estop = agac.indexOf("Tüm bobinleri acil durdur");
    const kart = agac.indexOf("alan-haritasi-karti");
    expect(estop).toBeGreaterThan(-1);
    expect(kart).toBeGreaterThan(estop);
    u.unmount();
  });

  it("KRİTİK: kart AÇIKKEN ACİL DURDUR aynı dört durdurma isteğini gönderir", async () => {
    mockAlan.harita = { surum: 1, durum: "sifir", zaman: 1, modelTahmini: true };
    const u = await ekran();
    fireEvent(u.getByTestId("alan-haritasi-ac"), "valueChange", true);
    expect(mockAlan.abone.mock.calls).toEqual([[true]]);
    await act(async () => {
      fireEvent.press(u.getAllByLabelText("Tüm bobinleri acil durdur")[0]);
    });
    await act(async () => {});
    expect(durdurmalar()).toEqual(ESTOP_DORTLU);
    u.unmount();
    expect(mockAlan.abone.mock.calls).toEqual([[true], [false]]); // ekrandan çıkınca abonelik biter
  });
});
