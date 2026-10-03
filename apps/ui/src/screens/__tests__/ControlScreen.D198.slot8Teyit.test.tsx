// Author: mertaygn, cglrgrkn
/**
 * D1.98 · B-6.9 · İG-6.45 — Kontrol ekranı: ESP BİLEREK kapalıyken sahte "Durdurma onaylanamadı" alarmı ve sahte
 * "Bazı bobinler çevrimdışı" uyarısı YOK; gizli slot 8 başlatma seçimine girmez; slot 8 STOP'u KOŞULSUZ gider.
 * ============================================================================================================
 * ÖLÇÜLEN KUSUR (06-2 g5a/g5b; aday İG-6.45, gerçek web + backend ESP=0 + sahte STM):
 *  · her başarılı "⏹ Durdur" → slot 8 yanıtı `mqtt_unavailable` → "bobinler HÂLÂ ÇALIŞIYOR olabilir" (alarm körlüğü);
 *  · her "▶ Başlat" → seçim `{1..8}` → gizli/bağlı olmayan slot 8 için "Bazı bobinler çevrimdışı";
 *  · görünür 7 bobin seçimden çıkarılınca STM çevrimiçiyken "Bağlantı yok" (yanlış tanı).
 * SAHİP KARARLARI: slot 8 STOP kümesinde KOŞULSUZ kalır (orkestratör notu; Ö.4-Y8 gönderim azalmaz) · teyit A-63:
 * ESP kapalıyken STM'e göre · ESP AÇIKKEN başarısız STOP alarmı KALIR (karşıt kol).
 *
 * `/coil/*` yanıtları ELLE YAZILMADI: `__fixtures__/espSlot8Durdurma.json` GERÇEK uçlardan (TestClient) üretilir;
 * bayatlarsa `tests/test_D198_esp_kapali_slot8_STOP_yaniti_DEVRE_DISI.py` KIRMIZI olur.
 */
const mockApiPost = jest.fn();
const mockAlert = jest.fn();
const mockStart = jest.fn(async () => true);
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformAlert: (...a: unknown[]) => mockAlert(...a),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/hooks/useSessionControl", () => ({
  useSessionControl: () => ({
    isActive: false, treatment: null, elapsedSec: 0, remainingSec: 0,
    loading: false, stopping: false, error: null, lastError: () => null,
    startSession: (...a: unknown[]) => mockStart(...(a as [])), stopSession: jest.fn(async () => true), emergencyStop: jest.fn(),
  }),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://x/api" } }));
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
jest.mock("@/components/domain/SessionProgressCard", () => ({ SessionProgressCard: () => null }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
// Bobin başı paneller de "⏹ Durdur" çizer; bu kapı ANA Durdur/Başlat akışını ölçer (panel kendi kapısında: D1.82).
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { ControlScreen } from "@/screens/ControlScreen";

const yanit: any = require("./__fixtures__/espSlot8Durdurma.json");

const bobin = (id: number, over: Record<string, unknown> = {}) => ({
  id, running: false, connected: false, stm32Driven: id <= 7, frequencyHz: 0, dutyCycle: 0,
  objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [], ...over,
});
const snapshot = (espAcik: boolean, slot8Calisiyor = true) => ({
  gateway: espAcik ? "online" : "devre_disi", mqtt: espAcik ? "online" : "devre_disi", stm: "online",
  patient: { name: "Boncuk", species: "Kedi", breed: "", owner: "S" },
  activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
  notifications: [],
  coils: [
    ...[1, 2, 3, 4, 5, 6, 7].map((i) => bobin(i, { running: true, connected: true, frequencyHz: 100, dutyCycle: 40 })),
    espAcik ? bobin(8, { running: slot8Calisiyor, connected: true, stm32Driven: false }) : bobin(8, { stm32Driven: false }),
  ],
  system: {}, sessions: [],
});

function yanitlariKur(espAcik: boolean) {
  mockApiPost.mockImplementation(async (yol: string) => {
    if (yol === "/coil/batch") return yanit.espKapali.batch;
    if (/^\/coil\/\d+\/control$/.test(yol)) return espAcik ? yanit.espAcikBrokerOlu.tekil : yanit.espKapali.tekil;
    return { status: "success" };
  });
}
const alarmlar = () => mockAlert.mock.calls.map((c) => String(c[0]));
const durdurmaYollari = () =>
  mockApiPost.mock.calls.filter((c) => (c[1] as any)?.start === false).map((c) => String(c[0])).sort();

async function ekran(espAcik: boolean, slot8Calisiyor = true) {
  mockSnap = snapshot(espAcik, slot8Calisiyor);
  yanitlariKur(espAcik);
  const u = render(<ControlScreen />);
  await act(async () => {});
  return u;
}

beforeEach(() => {
  mockApiPost.mockReset();
  mockAlert.mockReset();
  mockStart.mockClear();
});

describe("D1.98 — ESP bilerek kapalı: slot 8 teyit yorumu, başlatma seçimi, koşulsuz STOP", () => {
  it("KRİTİK: başarılı Durdur sahte 'Durdurma onaylanamadı' ÜRETMEZ ve slot 8 STOP'u YİNE gider", async () => {
    const u = await ekran(false);
    await act(async () => {
      fireEvent.press(u.getByText("⏹ Durdur"));
    });
    expect(durdurmaYollari()).toEqual(["/coil/8/control", "/coil/batch"]);
    expect(alarmlar()).not.toContain("Durdurma onaylanamadı");
  });

  it("KRİTİK: Başlat gizli slot 8 için 'Bazı bobinler çevrimdışı' DEMEZ ve seansa 1-7'yi verir", async () => {
    const u = await ekran(false);
    await act(async () => {
      fireEvent.press(u.getByText("▶ Başlat"));
    });
    expect(alarmlar()).not.toContain("Bazı bobinler çevrimdışı");
    expect(mockStart).toHaveBeenCalledTimes(1);
    expect((mockStart.mock.calls[0] as any[])[0].coilIds).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it("KRİTİK (İG-6.45): görünür 7 bobin seçimden çıkarılınca Başlat 'En az bir bobin seçin' der (yanlış 'Bağlantı yok' değil); Durdur yine slot 8'e gider, alarm yok", async () => {
    const u = await ekran(false);
    for (let i = 1; i <= 7; i++) {
      await act(async () => {
        fireEvent.press(u.getAllByLabelText(new RegExp(`^Bobin ${i}, seçili,`))[0]);
      });
    }
    await act(async () => {
      fireEvent.press(u.getByText("▶ Başlat"));
    });
    expect(alarmlar()).toContain("Uyarı");
    expect(mockAlert.mock.calls.find((c) => c[0] === "Uyarı")?.[1]).toBe("En az bir bobin seçin.");
    expect(alarmlar()).not.toContain("Bağlantı yok");
    expect(mockStart).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.press(u.getByText("⏹ Durdur"));
    });
    expect(durdurmaYollari()).toContain("/coil/8/control");
    expect(alarmlar()).not.toContain("Durdurma onaylanamadı");
  });

  it("KRİTİK (koşulsuz STOP): ESP görünürken slot 8 SEÇİMDEN ÇIKARILSA ve çalışmasa da Durdur ona STOP gönderir", async () => {
    const u = await ekran(true, false);
    await act(async () => {
      fireEvent.press(u.getAllByLabelText(/^Bobin 8, seçili,/)[0]);
    });
    expect(u.getAllByLabelText(/^Bobin 8, seçili değil,/).length).toBeGreaterThan(0); // aparat: seçimden çıktı
    await act(async () => {
      fireEvent.press(u.getByText("⏹ Durdur"));
    });
    expect(durdurmaYollari()).toContain("/coil/8/control");
  });

  it("KARŞIT: ESP AÇIK, slot 8 çalışıyor, STOP yayını başarısız (broker ölü) → alarm KALIR", async () => {
    const u = await ekran(true);
    await act(async () => {
      fireEvent.press(u.getByText("⏹ Durdur"));
    });
    expect(durdurmaYollari()).toContain("/coil/8/control");
    expect(alarmlar()).toContain("Durdurma onaylanamadı");
  });
});
