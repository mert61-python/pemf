/**
 * KP-3 C · ControlScreen başlatma kapıları (C12'de kalan kollar) — her test bir DAVRANIŞ iddiası (C12 / D1.98 düzeneğinin aynısı):
 *  - Manuel seans: hasta seçilmeden BAŞLAMAZ (sert kapı) · geçersiz sayı ("abc") → uyarı, seans BAŞLAMAZ.
 *  - Otomatik seans: geçersiz yoğunluk → uyarı, seans BAŞLAMAZ · hiç bobin seçili değilse "bobin seçin" uyarısı, seans BAŞLAMAZ.
 *  - Bobin çipine ikinci basış bobini seçime GERİ ekler (seansa girer).
 * SAHTE: apiClient (ağ sınırı) · useSessionControl (seans servisi) · canlı veri anlık görüntüsü; ağır alt paneller çizilmez.
 * ⚠️ Ürün kodu (bobin sürme) DEĞİŞMEDİ — yalnız test.
 */
const mockApiPost = jest.fn();
const mockAlert = jest.fn();
const mockStart = jest.fn(async (..._a: unknown[]) => true);
let mockSonHata: string | null = null;
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
    loading: false, stopping: false, error: null, lastError: () => mockSonHata,
    startSession: (...a: unknown[]) => mockStart(...a), stopSession: jest.fn(async () => true), emergencyStop: jest.fn(),
    benimse: jest.fn(),
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
let mockHasta: { id: string; name: string } | undefined;
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operator: "Dr. X", operatorEmail: "v@x.com" }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), goTo: jest.fn(), selectedPatient: mockHasta }),
}));
jest.mock("@/components/domain/SessionProgressCard", () => ({ SessionProgressCard: () => null }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import i18n from "i18next";
import { ControlScreen } from "@/screens/ControlScreen";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

const bobin = (id: number, over: Record<string, unknown> = {}) => ({
  id, running: false, connected: false, stm32Driven: id <= 7, frequencyHz: 0, dutyCycle: 0,
  objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [], ...over,
});
const snapshot = (o: { calisan: boolean; espBagli?: boolean; hastaAdi?: string }) => ({
  gateway: "online", mqtt: "online", stm: "online", espEtkin: true,
  patient: { name: o.hastaAdi ?? "", species: "Kedi", breed: "", owner: "S" },
  activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
  notifications: [],
  coils: [
    ...[1, 2, 3, 4, 5, 6, 7].map((i) => bobin(i, { running: o.calisan, connected: true, frequencyHz: 100, dutyCycle: 40 })),
    bobin(8, { running: o.calisan && o.espBagli !== false, connected: o.espBagli !== false, stm32Driven: false }),
  ],
  system: {}, sessions: [],
});

async function ekran(o: Parameters<typeof snapshot>[0], hasta?: { id: string; name: string }) {
  mockSnap = snapshot(o);
  mockHasta = hasta;
  const u = render(<ControlScreen />);
  await act(async () => {});
  return u;
}
async function yaz(u: ReturnType<typeof render>, etiket: string, deger: string) {
  await act(async () => { fireEvent.changeText(u.getByLabelText(etiket), deger); });
}
async function bas(u: ReturnType<typeof render>, metin: string) {
  await act(async () => { fireEvent.press(u.getByText(metin)); });
}
const basliklar = () => mockAlert.mock.calls.map((c) => String(c[0]));
const yollar = () => mockApiPost.mock.calls.map((c) => String(c[0]));
const govde = (yol: string) => mockApiPost.mock.calls.find((c) => c[0] === yol)?.[1];

beforeEach(() => {
  mockApiPost.mockReset();
  mockAlert.mockReset();
  mockStart.mockClear();
  mockStart.mockImplementation(async () => true);
  mockSonHata = null;
});

const HASTA = { id: "p-9", name: "Fındık" };

describe("manuel başlatma kapıları", () => {
  it("hasta seçilmeden başlamaz; geçersiz sayıda uyarı ve başlamaz", async () => {
    let u = await ekran({ calisan: false });
    await bas(u, T("kontrol.sekme.manuel"));
    await bas(u, T("kontrol.panel.baslat"));
    expect(basliklar()).toEqual([T("kontrol.ekran.hastaSecilmedi")]);
    expect(mockStart).not.toHaveBeenCalled();
    u.unmount();
    mockAlert.mockReset();
    u = await ekran({ calisan: false }, HASTA);
    await bas(u, T("kontrol.sekme.manuel"));
    await yaz(u, T("kontrol.panel.frekansHz"), "abc");
    await bas(u, T("kontrol.panel.baslat"));
    expect(basliklar()).toEqual([T("kontrol.ekran.gecersizDeger")]);
    expect(mockStart).not.toHaveBeenCalled();
  });
});

describe("otomatik başlatma kapıları", () => {
  it("geçersiz yoğunluk → uyarı, başlamaz", async () => {
    const u = await ekran({ calisan: false }, HASTA);
    await bas(u, T("kontrol.sekme.otomatik"));
    await yaz(u, T("kontrol.ekran.yogunlukKayit"), "x");
    await bas(u, T("kontrol.ekran.otomatikBaslat"));
    expect(basliklar()).toEqual([T("kontrol.ekran.gecersizDeger")]);
    expect(mockStart).not.toHaveBeenCalled();
  });

  it("hiç bobin seçili değilse 'bobin seçin', başlamaz; ikinci basış bobini geri ekler", async () => {
    const u = await ekran({ calisan: false, espBagli: false }, HASTA);
    await bas(u, T("kontrol.sekme.otomatik"));
    for (const id of [1, 2, 3, 4, 5, 6, 7, 8]) {
      const cip = u.queryAllByText(String(id))[0];
      if (cip) await act(async () => { fireEvent.press(cip); });
    }
    await bas(u, T("kontrol.ekran.otomatikBaslat"));
    expect(mockAlert).toHaveBeenLastCalledWith(T("ayarlar.sistemDurumu.uyari"), T("kontrol.ekran.bobinSecin"));
    expect(mockStart).not.toHaveBeenCalled();
    await act(async () => { fireEvent.press(u.getAllByText("3")[0]); });
    // Ürünün Button'ı aynı etiketin 400 ms içindeki ikinci basışını yutar (çift dokunma koruması) → saat ilerletilir.
    const simdi = Date.now();
    const saat = jest.spyOn(Date, "now").mockReturnValue(simdi + 1000);
    await bas(u, T("kontrol.ekran.otomatikBaslat"));
    saat.mockRestore();
    expect((mockStart.mock.calls[0][0] as { coilIds: number[] }).coilIds).toEqual([3]);
  });
});
