// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · KRİTİK — Kontrol ekranındaki "TÜM BOBİNLERİ ACİL DURDUR" düğmesi çeviri sisteminden BAĞIMSIZ (kritikMetin + KRITIK_YEDEK):
 * TR / EN görünür, katalog bozukken yedekten dolu, basış AYNI istekleri gönderir. Mock düzeni `ControlScreen.D182.durdurKilitlenmez.test.tsx` ile aynı.
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", bridgeBaseUrl: "http://127.0.0.1:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
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
// Bobin başı paneller ayrı kapıda (CoilParameterPanel.D182); burada ana Durdur ve seans kartı ölçülür.
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { ControlScreen } from "@/screens/ControlScreen";
import i18n from "i18next";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

type Cagri = { yol: string; govde: any };
const cagrilar: Cagri[] = [];
let startCoz: ((o: unknown) => void) | null = null;
let stopAsili = false;
const stopCozuculer: ((o: unknown) => void)[] = [];
const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

beforeEach(() => {
  cagrilar.length = 0;
  startCoz = null;
  stopAsili = false;
  stopCozuculer.length = 0;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  (global as any).fetch = jest.fn((url: string, init?: any) => {
    const yol = String(url).replace("http://127.0.0.1:8000/api", "");
    cagrilar.push({ yol, govde: init?.body ? JSON.parse(init.body) : undefined });
    if (yol === "/session/start") return new Promise((res) => { startCoz = (o) => res(yanit(o) as any); });
    if (yol === "/session/stop" && stopAsili) return new Promise((res) => { stopCozuculer.push((o) => res(yanit(o) as any)); });
    if (yol === "/session/active") return yanit({ is_active: false });
    return yanit({ status: "success" });
  });
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
    patient: { name: "Boncuk", species: "Kedi", breed: "", owner: "S" },
    activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
    notifications: [],
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({
      id, running: false, connected: true, stm32Driven: true, frequencyHz: 0, dutyCycle: 0,
      objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [],
    })).concat([{ id: 8, running: false, connected: false, stm32Driven: false, frequencyHz: 0, dutyCycle: 0,
      objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [] }]),
    system: {}, sessions: [],
  };
});
const depo = { setItem: async () => undefined };
afterEach(async () => {
  jest.restoreAllMocks();
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

const yollar = () => cagrilar.map((c) => c.yol);
const say = (y: string) => yollar().filter((x) => x === y).length;

async function ekran() {
  const u = render(<ControlScreen />);
  await act(async () => {});
  return u;
}


async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}

describe("KRİTİK: Kontrol ekranı 'TÜM BOBİNLERİ ACİL DURDUR' — iki dilde görünür, eylem AYNI", () => {
  it("Türkçe: göç öncesiyle aynı düğme metni / erişim adı / ipucu", async () => {
    const u = await ekran();
    expect(u.getByText("🚨 TÜM BOBİNLERİ ACİL DURDUR")).toBeTruthy();
    const d = u.getByLabelText("Tüm bobinleri acil durdur");
    expect(d.props.accessibilityHint).toBe("Tüm bobinleri anında durdurur ve aktif seansı sonlandırır");
  });

  it("İngilizce: EMERGENCY STOP ALL COILS; basınca TR ile AYNI istek dizisi gider", async () => {
    const u = await ekran();
    await act(async () => {
      fireEvent.press(u.getByText("🚨 TÜM BOBİNLERİ ACİL DURDUR"));
    });
    const trYollar = yollar();
    expect(trYollar.length).toBeGreaterThan(0);
    u.unmount();
    cagrilar.length = 0;
    await enYap();
    const v = await ekran();
    expect(v.getByText("🚨 EMERGENCY STOP ALL COILS")).toBeTruthy();
    const d = v.getByLabelText("Emergency stop all coils");
    expect(d.props.accessibilityHint).toBe("Stops all coils immediately and ends the active session");
    await act(async () => {
      fireEvent.press(v.getByText("🚨 EMERGENCY STOP ALL COILS"));
    });
    expect(yollar()).toEqual(trYollar);
  });

  it("katalog anahtarları EKSİK: düğme yine İngilizce ve dolu (KRITIK_YEDEK), eylem çalışır", async () => {
    await enYap();
    // ⚠️ Yalnız ACİL DURDUR anahtarları "katalogda yok" sayılır (ekranın öteki metinleri katı jest kipinde eksik anahtarda atar; kritikMetin atmaz).
    const gercek = i18n.exists.bind(i18n);
    jest.spyOn(i18n, "exists").mockImplementation(((k: string, o?: object) => (String(k).startsWith("guvenlik.acilDurdur.") ? false : gercek(k, o as never))) as never);
    try {
      const u = await ekran();
      expect(u.getByText("🚨 EMERGENCY STOP ALL COILS")).toBeTruthy();
      await act(async () => {
        fireEvent.press(u.getByText("🚨 EMERGENCY STOP ALL COILS"));
      });
      expect(yollar().length).toBeGreaterThan(0);
    } finally {
      jest.restoreAllMocks();
    }
  });
});
