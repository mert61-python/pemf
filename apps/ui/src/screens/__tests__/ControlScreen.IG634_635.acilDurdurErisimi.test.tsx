// Author: mertaygn, cglrgrkn
/**
 * İG-6.34 · İG-6.35 — Kontrol ekranındaki ACİL DURDUR'lara erişim: hasta seçilmemişken de çizilir, seans kartınınki hiçbir istek
 * askıdayken kilitlenmez; basış GERÇEKTEN durdurma gönderir.
 * ==========================================================================================================================
 * ÖLÇÜLEN KÖRLÜK (D5 doğrulaması, mutant GERÇEK bileşen ağacında, 129 ilgili jest dosyası 1592/1592 YEŞİL):
 *  (6.34) `<PatientGate soft>` → `<PatientGate>`: hasta seçilmemiş Kontrol ekranında "TÜM BOBİNLERİ ACİL DURDUR" da gizlenir
 *         (bu rotada kayan ACİL DURDUR da yok — ekran kendi düğmesini çizer). Tüm ControlScreen testleri PatientGate'i geçirgen
 *         sahteyle değiştirdiği için kapı yoktu.
 *  (6.35) seans kartının ACİL DURDUR'una `disabled={loading}` eklenince (D1.82 öncesi Durdur hatasının ACİL DURDUR ikizi)
 *         `/session/stop` askıdayken ACİL DURDUR basışı yutulur; kapı yoktu.
 *
 * GERÇEK: `ControlScreen`, `PatientGate`, `SessionProgressCard`, `useSessionControl`, `performEmergencyStop`, `apiClient`.
 * Sahte EN ALT katta: `global.fetch` (kaydedici; `/session/active` aktif seans, `/session/stop` isteğe bağlı ASILI) + bağlamlar
 * (canlı veri, kimlik, gezinme — hasta SEÇİLMEMİŞ) + ilgisiz ağır paneller.
 * ⚠️ Yalnız KAPI: ACİL DURDUR / STOP davranışı değişmez; bu dosya ürün koduna dokunmaz.
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
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live", haveRealData: true,
    telemetryStale: false, sensorHistory: {}, unreadCount: 0, markAllRead: jest.fn(),
    clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
    donanimBelirsiz: false,
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

describe("İG-6.34 — hasta SEÇİLMEMİŞ Kontrol ekranında ACİL DURDUR erişilebilir", () => {
  it("KRİTİK: bobin çalışırken 'Tüm bobinleri acil durdur' ÇİZİLİR ve basış 4 durdurma isteği gönderir", async () => {
    const u = await ekran();
    expect(u.getByLabelText("Hasta seçin")).toBeTruthy(); // aparat: GERÇEK hasta kapısı seçim kartını gösteriyor
    const dugmeler = u.queryAllByLabelText("Tüm bobinleri acil durdur");
    expect(dugmeler).toHaveLength(1);
    await act(async () => {
      fireEvent.press(dugmeler[0]);
    });
    await act(async () => {});
    expect(durdurmalar()).toEqual(ESTOP_DORTLU);
    u.unmount();
  });

  it("KRİTİK: hasta seçilmemişken aktif seansın kartı ve kendi ACİL DURDUR'u da çizilir", async () => {
    seansAktif = true;
    const u = await ekran();
    expect(u.getByLabelText("Hasta seçin")).toBeTruthy();
    expect(u.queryAllByLabelText("Acil durdurma — tüm bobinleri anında durdur")).toHaveLength(1);
    u.unmount();
  });
});

describe("İG-6.35 — seans kartının ACİL DURDUR'u hiçbir istek askıdayken kilitlenmez", () => {
  // Hasta SEÇİLİ: bu blok İG-6.34'ten bağımsız ölçer (hasta kapısı mutantı buraya taşmaz).
  beforeEach(() => {
    mockHasta = { id: "1", name: "Boncuk" };
  });

  it("KRİTİK: /session/stop ASKIDAYKEN kartın ACİL DURDUR'u etkin ve basış durdurma gönderir", async () => {
    seansAktif = true;
    stopAsili = true;
    const u = await ekran();
    await act(async () => {
      fireEvent.press(u.getByLabelText("Seansı durdur"));
    });
    expect(cagrilar.filter((y) => y === "/session/stop")).toHaveLength(1); // aparat: durdurma uçuşta (askıda)
    const acil = u.getByLabelText("Acil durdurma — tüm bobinleri anında durdur");
    expect(acil.props.accessibilityState?.disabled ?? false).toBe(false);
    cagrilar.length = 0;
    await act(async () => {
      fireEvent.press(acil);
    });
    await act(async () => {});
    expect(cagrilar.filter((y) => y === "/hardware/emergency_stop")).toHaveLength(2);
    expect(cagrilar).toContain("/hardware/command");
    u.unmount();
  });

  it("KARŞIT: askıda istek yokken de kartın ACİL DURDUR'u 4 durdurma isteği gönderir (aparat ölçüyor)", async () => {
    seansAktif = true;
    const u = await ekran();
    cagrilar.length = 0;
    await act(async () => {
      fireEvent.press(u.getByLabelText("Acil durdurma — tüm bobinleri anında durdur"));
    });
    await act(async () => {});
    expect(durdurmalar()).toEqual(ESTOP_DORTLU);
    u.unmount();
  });
});
