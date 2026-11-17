/**
 * KP-8 · src/screens/ControlScreen.tsx kalan dallar (düzenek KP3-ControlScreen-kollari ile AYNI — apiClient / seans servisi / canlı
 * veri sahte; ağır alt paneller çizilmez):
 *  - Otomatik hedef önerisi (auto_preset) alan getirmezse ya da HİÇ gelmezse operatörün değerleri KORUNUR (seans o değerlerle başlar);
 *    kaynak bilgisi yoksa "literatür" notu çıkmaz.
 *  - Süre alanı sıfır / negatif / geçersizse seans 20 dk ile başlar (süresiz seansa sızmaz).
 *  - Seans servisi başarısız olup hata NEDENİ vermezse genel "seans başlatılamadı" (otomatik) / "manuel başlatılamadı" iletisi.
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

beforeEach(() => {
  mockApiPost.mockReset();
  mockAlert.mockReset();
  mockStart.mockClear();
  mockStart.mockImplementation(async () => true);
  mockSonHata = null;
});

const HASTA = { id: "p-8", name: "Pamuk" };
const ilkHedef = () => T("kontrol.hedef.dokuIyilesmesi");

it("öneri alan getirmezse / hiç gelmezse operatörün değerleri korunur; süre negatifse 20 dk", async () => {
  mockApiPost.mockImplementation(async (yol: string) => (yol === "/hardware/auto_preset" ? { parameters: {} } : null));
  const u = await ekran({ calisan: false, espBagli: false }, HASTA);
  await bas(u, T("kontrol.sekme.otomatik"));
  await yaz(u, T("kontrol.panel.frekansHz"), "33");
  await yaz(u, T("kontrol.ekran.yogunlukKayit"), "1");
  await act(async () => { fireEvent.press(u.getAllByText(ilkHedef())[0]); });
  await act(async () => {});
  expect(yollar()).toContain("/hardware/auto_preset");
  mockApiPost.mockImplementation(async () => null);
  await act(async () => { fireEvent.press(u.getAllByText(ilkHedef())[0]); });
  await act(async () => {});
  await yaz(u, T("kontrol.panel.sureDk"), "-5");
  await bas(u, T("kontrol.ekran.otomatikBaslat"));
  expect(mockStart).toHaveBeenCalledWith(expect.objectContaining({ frequency: 33, durationMinutes: 20 }));
});

it("servis nedensiz başarısız: otomatik → 'seans başlatılamadı', manuel → 'manuel başlatılamadı'", async () => {
  mockSonHata = null;
  mockStart.mockImplementation(async () => false);
  mockApiPost.mockImplementation(async () => null);
  let u = await ekran({ calisan: false, espBagli: false }, HASTA);
  await bas(u, T("kontrol.sekme.otomatik"));
  await yaz(u, T("kontrol.ekran.yogunlukKayit"), "1");
  await bas(u, T("kontrol.ekran.otomatikBaslat"));
  expect(mockAlert).toHaveBeenLastCalledWith(T("ayarlar.sistemDurumu.hata"), T("kontrol.ekran.seansBaslatilamadi"));
  u.unmount();
  mockAlert.mockReset();
  u = await ekran({ calisan: false, espBagli: false }, HASTA);
  await bas(u, T("kontrol.panel.baslat"));
  expect(mockAlert).toHaveBeenLastCalledWith(T("ayarlar.sistemDurumu.hata"), T("kontrol.ekran.manuelBaslatilamadi"));
});
