/**
 * KP-3 C · src/screens/ControlScreen.tsx kapsanmayan kolları — her test bir DAVRANIŞ iddiası (D1.98 düzeneğinin aynısı):
 *  - "Parametreleri Uygula" (seans DIŞINDA çalışan donanım): STM bobinlerine TEK `/coil/batch`, ESP yuvasına kendi `/coil/<id>/control`
 *    isteği gider (süre dakika → saniye, faz alanı dahil); kart kaydı ancak HER bobin SATIRI başarılıysa tazelenir. Üst seviye "success"
 *    ama bir satır başarısızsa "Güncellenemedi" ve kayıt İSTENMEZ; donanım güncellendi ama kayıt tazelenemezse bu SESSİZ geçilmez.
 *  - Geçersiz sayı ("abc") → uyarı, istek YOK; faz 0–360 dışındaysa sınıra çekilir ve operatör UYARILIR (gönderilen = çekilen değer).
 *  - Otomatik seans: hasta seçilmeden BAŞLAMAZ (sert kapı); seçiliyken hedef + parametrelerle başlar; başlatılamazsa seans hatası
 *    gösterilir. Seçimden çıkarılan bobin seansa girmez; bağlı olmayan bobin seçiliyse atlanır ve operatör uyarılır.
 *  - Boş alan varsayılana düşer (boş frekans → 100 Hz).
 * SAHTE: apiClient (ağ sınırı) · useSessionControl (seans servisi) · canlı veri anlık görüntüsü; ağır alt paneller çizilmez.
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

describe("Parametreleri Uygula (seans dışında çalışan donanım)", () => {
  const BASARI = { status: "success", results: [{ status: "success" }, { status: "success" }] };

  it("STM'e TEK batch, ESP'ye kendi isteği (süre sn, faz dahil); her satır başarılıysa kart kaydı tazelenir ve 'Uygulandı'", async () => {
    mockApiPost.mockImplementation(async (yol: string) => (yol === "/coil/batch" ? BASARI : { status: "success" }));
    const u = await ekran({ calisan: true });
    await yaz(u, T("kontrol.panel.frekansHz"), "40");
    await yaz(u, T("kontrol.panel.dutyYuzde"), "30");
    await yaz(u, T("kontrol.panel.fazDerece"), "90");
    await yaz(u, T("kontrol.panel.sureDk"), "15");
    await bas(u, T("kontrol.ekran.parametreleriUygula"));
    expect(govde("/coil/batch")).toEqual({ coil_ids: [1, 2, 3, 4, 5, 6, 7], freq: 40, duty: 30, phase: 90, duration: 900, start: true });
    expect(govde("/coil/8/control")).toEqual({ freq: 40, duty: 30, phase: 90, duration: 900, start: true });
    expect(govde("/session/parametre_guncelle")).toEqual({
      frequency: 40, duty: 30, phase: 90, duration_minutes: 15, coil_ids: [1, 2, 3, 4, 5, 6, 7, 8],
    });
    expect(mockAlert).toHaveBeenLastCalledWith(
      T("kontrol.ekran.uygulandi"),
      T("kontrol.ekran.uygulandiGovde", { count: 8, freq: 40, duty: 30, phase: 90, duration: 15 }),
    );
  });

  it("üst seviye 'success' ama bir bobin SATIRI başarısız → 'Güncellenemedi', kart kaydı İSTENMEZ", async () => {
    mockApiPost.mockImplementation(async (yol: string) =>
      yol === "/coil/batch" ? { status: "success", results: [{ status: "success" }, { status: "error" }] } : { status: "success" });
    const u = await ekran({ calisan: true });
    await bas(u, T("kontrol.ekran.parametreleriUygula"));
    expect(basliklar()).toEqual([T("kontrol.ekran.guncellenemedi")]);
    expect(yollar()).not.toContain("/session/parametre_guncelle");
  });

  it("ESP yanıtı yoksa (null) da 'Güncellenemedi'", async () => {
    mockApiPost.mockImplementation(async (yol: string) => (yol === "/coil/batch" ? BASARI : null));
    const u = await ekran({ calisan: true });
    await bas(u, T("kontrol.ekran.parametreleriUygula"));
    expect(basliklar()).toEqual([T("kontrol.ekran.guncellenemedi")]);
  });

  it("donanım güncellendi ama kart kaydı tazelenemedi → SESSİZ geçilmez (uygulanan frekansla)", async () => {
    mockApiPost.mockImplementation(async (yol: string) =>
      yol === "/coil/batch" ? BASARI : yol === "/session/parametre_guncelle" ? null : { status: "success" });
    const u = await ekran({ calisan: true });
    await bas(u, T("kontrol.ekran.parametreleriUygula"));
    expect(mockAlert).toHaveBeenLastCalledWith(T("kontrol.ekran.kartTazelenemedi"), T("kontrol.ekran.kartTazelenemediGovde", { freq: 100 }));
  });

  it("geçersiz sayı → uyarı, istek YOK; faz sınır dışı → sınıra çekilir ve operatör UYARILIR; boş frekans → 100 Hz", async () => {
    mockApiPost.mockImplementation(async (yol: string) => (yol === "/coil/batch" ? BASARI : { status: "success" }));
    const u = await ekran({ calisan: true });
    await yaz(u, T("kontrol.panel.dutyYuzde"), "abc");
    await bas(u, T("kontrol.ekran.parametreleriUygula"));
    expect(basliklar()).toEqual([T("kontrol.ekran.gecersizDeger")]);
    expect(mockApiPost).not.toHaveBeenCalled();
    mockAlert.mockReset();
    await yaz(u, T("kontrol.panel.dutyYuzde"), "25");
    await yaz(u, T("kontrol.panel.frekansHz"), "");
    await yaz(u, T("kontrol.panel.fazDerece"), "400");
    await bas(u, T("kontrol.ekran.parametreleriUygula"));
    expect(basliklar()[0]).toBe(T("kontrol.ekran.parametreGuvenligi"));
    expect(String(mockAlert.mock.calls[0][1])).toContain(T("kontrol.sinir.faz"));
    expect(govde("/coil/batch")).toMatchObject({ freq: 100, phase: 360 });
  });
});

describe("başlatma kolları", () => {
  it("otomatik seans: hasta seçilmeden BAŞLAMAZ; seçiliyken hedef + parametrelerle başlar; başarısızsa seans hatası gösterilir", async () => {
    let u = await ekran({ calisan: false });
    await bas(u, T("kontrol.sekme.otomatik"));
    await bas(u, T("kontrol.ekran.otomatikBaslat"));
    expect(basliklar()).toEqual([T("kontrol.ekran.hastaSecilmedi")]);
    expect(mockStart).not.toHaveBeenCalled();
    u.unmount();

    mockAlert.mockReset();
    mockSonHata = "Bobin 3 yanıt vermedi";
    mockStart.mockImplementation(async () => false);
    u = await ekran({ calisan: false, espBagli: false }, { id: "p-1", name: "Boncuk" });
    await bas(u, T("kontrol.sekme.otomatik"));
    await yaz(u, T("kontrol.ekran.yogunlukKayit"), "2,5");
    await bas(u, T("kontrol.ekran.otomatikBaslat"));
    expect(mockStart).toHaveBeenCalledWith(expect.objectContaining({
      patientId: "p-1", patientName: "Boncuk", mode: "Otomatik", frequency: 50, duty: 25, intensity: 2.5, durationMinutes: 20,
      coilIds: [1, 2, 3, 4, 5, 6, 7], operatorEmail: "v@x.com",
    }));
    expect(mockAlert).toHaveBeenLastCalledWith(T("ayarlar.sistemDurumu.hata"), "Bobin 3 yanıt vermedi");
  });

  it("seçimden çıkarılan bobin seansa girmez; bağlı olmayan seçili bobin atlanır ve operatör uyarılır", async () => {
    // slot 8 görünür ama BAĞLI DEĞİL (çalışıyor görünüyor → listelenir)
    const u = await ekran({ calisan: false }, { id: "p-2", name: "Pamuk" });
    mockSnap.coils[7] = bobin(8, { running: true, connected: false, stm32Driven: false });
    u.rerender(<ControlScreen />);
    await act(async () => {});
    await act(async () => { fireEvent.press(u.getAllByText("3")[0]); });
    await bas(u, T("kontrol.panel.baslat"));
    expect(basliklar()).toContain(T("kontrol.ekran.bazilariCevrimdisi"));
    expect((mockStart.mock.calls[0][0] as { coilIds: number[] }).coilIds).toEqual([1, 2, 4, 5, 6, 7]);
  });
});
