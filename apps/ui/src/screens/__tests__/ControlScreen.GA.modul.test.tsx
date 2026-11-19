// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — Kontrol ekranında geliştirici modülleri: GİZLİYKEN (varsayılan) seçici YOK ve ekran bugünkü gibi; görünürken seçici
 * ACİL DURDUR düğmesinin ARKASINDA; modül seçilince PEMF sekmeleri yerine modül paneli, ACİL DURDUR aynı yerde ve aynı dört durdurma
 * isteğini gönderir (sunucu modüllere de yayar); "PEMF cihazı" seçilince sekmeler geri gelir.
 * Aparat: ControlScreen.IG634_635.acilDurdurErisimi.test.tsx (gerçek ekran, sahte fetch).
 */
const mockModulApi = { listele: jest.fn(), sec: jest.fn(), birak: jest.fn() };
jest.mock("@/services/moduller", () => {
  const gercek = jest.requireActual("@/services/moduller");
  return {
    modulAdi: gercek.modulAdi,
    modulHataMetni: gercek.modulHataMetni,
    get modulApi() {
      return mockModulApi; // getter: fabrika hoist edilir (KP-8 dersi)
    },
  };
});
jest.mock("@/moduller/kayit", () => {
  const R = jest.requireActual("react");
  const { Text } = jest.requireActual("react-native");
  return { PANELLER: { ornek: () => R.createElement(Text, { testID: "sahte-modul-paneli" }, "panel") } };
});
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

const LISTE = { gorunur: true, etkin: null, canli: false, hata: null, moduller: [{ kimlik: "ornek", ad: { tr: "Örnek modül", en: "Example" } }] };

describe("GA — geliştirici modülleri Kontrol ekranında", () => {
  beforeEach(() => {
    mockAlan.harita = null;
    mockAlan.abone = jest.fn();
    for (const f of Object.values(mockModulApi)) f.mockReset();
  });

  it("KRİTİK: gizliyken seçici YOK, sekmeler bugünkü gibi", async () => {
    mockModulApi.listele.mockResolvedValue({ tamam: true, veri: { ...LISTE, gorunur: false } });
    const u = await ekran();
    expect(u.queryByTestId("modul-secici")).toBeNull();
    expect(u.queryAllByRole("tab").length).toBeGreaterThan(0);
    u.unmount();
  });

  it("KRİTİK: modül seçilince sekmeler yerine panel; ACİL DURDUR ÖNDE ve AYNI dört istek; PEMF'e dönüş", async () => {
    mockModulApi.listele.mockResolvedValue({ tamam: true, veri: LISTE });
    mockModulApi.sec.mockResolvedValue({ tamam: true, veri: {} });
    mockModulApi.birak.mockResolvedValue({ tamam: true, veri: {} });
    const u = await ekran();
    const agac = JSON.stringify(u.toJSON());
    expect(agac.indexOf("modul-secici")).toBeGreaterThan(agac.indexOf("Tüm bobinleri acil durdur"));
    await act(async () => {
      fireEvent.press(u.getByTestId("modul-sec-ornek"));
    });
    expect(u.getByTestId("sahte-modul-paneli")).toBeTruthy();
    expect(u.queryAllByRole("tab")).toHaveLength(0);
    await act(async () => {
      fireEvent.press(u.getAllByLabelText("Tüm bobinleri acil durdur")[0]);
    });
    await act(async () => {});
    expect(durdurmalar()).toEqual(ESTOP_DORTLU);
    await act(async () => {
      fireEvent.press(u.getByTestId("modul-sec-pemf"));
    });
    expect(u.queryByTestId("sahte-modul-paneli")).toBeNull();
    expect(u.queryAllByRole("tab").length).toBeGreaterThan(0);
    u.unmount();
  });
});
