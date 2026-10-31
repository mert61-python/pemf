// Author: mertaygn, cglrgrkn
/**
 * BE 2 · Y226 / Y227 / Y228 — ACİL DURDUR EKRANI: boşta kapanışta alarm yok, teyitsiz düğme yalnız bir şey çalışıyorduysa,
 * bağlantı yokken mandal bandı yok, çevrimdışı tek bant.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR (31.10, sahip telefonda): başlatıcı boştayken kapatılınca telefon kırmızı "ACİL DURDURMA MANDALLI — uygulama seans ya da
 * bobin çalışırken kapatıldı" (yanlış neden) + her ekranda "ACİL DURDUR (teyitsiz)" gösteriyordu; bağlantı kopukken son bilinen mandal
 * ve çalışamayan "Sıfırla" kalıyordu; Ana Ekran'da kabuğun "Cihaza bağlanılamıyor … DOKUNUN" bandına ek olarak ikinci bir "Canlı bağlantı
 * yok …" bandı vardı.
 *
 * Gerçek olanlar: `AppShell`, `EstopMandalBandi`, `GlobalEmergencyStop`, `DashboardScreen`. Sahte: canlı veri (`useLiveData` — backend
 * yükü `test_BE2_bosta_kapanis_alarmsiz_teyitsiz_dugme_kosulu.py` ile kilitli), ağ / servisler, kabuk süsleri.
 * DEĞİŞMEZ: çalışırken kapanış bugünkü gibi (bant + doğru neden + teyitsiz düğme); bobin çalışırken bağlantı koparsa ACİL DURDUR kalır;
 * profil ekranı barının boyutu / yeri (Y221) DEĞİŞMEDİ; STOP gönderimi `performEmergencyStop` ile aynı.
 */
jest.mock("@/services/apiClient", () => ({
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb ?? null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
const mockDurdur = jest.fn();
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: (...a: unknown[]) => mockDurdur(...a),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/services/installedProfiles", () => ({ installedModes: () => null }));
jest.mock("@/components/ui/AuroraBackground", () => ({ AuroraBackground: () => null }));
jest.mock("@/components/ui/NotificationCenter", () => ({ NotificationCenter: () => null }));
jest.mock("@/components/ui/UpdateBanner", () => ({ UpdateBanner: () => null }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("expo-blur", () => ({ BlurView: () => null }));
jest.mock("expo-linear-gradient", () => ({ LinearGradient: () => null }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/hooks/useSessionControl", () => ({
  useSessionControl: () => ({
    isActive: false, treatment: null, elapsedSec: 0, remainingSec: 0,
    loading: false, stopping: false, error: null, lastError: () => null,
    startSession: jest.fn(), stopSession: jest.fn(), emergencyStop: jest.fn(),
  }),
}));
let mockCanli: { snap: any; bagli: boolean } = { snap: null, bagli: true };
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockCanli.snap, wsConnected: mockCanli.bagli, connectionQuality: mockCanli.bagli ? "live" : "offline",
    haveRealData: true, telemetryStale: false, sensorHistory: {},
    unreadCount: 0, markAllRead: jest.fn(), clearNotifications: jest.fn(),
    refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", setUserMode: jest.fn() }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" }, logout: jest.fn() }) }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { AppShell } from "@/components/ui/AppShell";
import { DashboardScreen } from "@/screens/DashboardScreen";

const NOTR = "PC'deki PEMF uygulaması kapatıldı — yeniden açılınca otomatik bağlanır";
const BANT = /ACİL DURDURMA MANDALLI/;
const TEYITSIZ = /ACİL DURDUR \(teyitsiz\)/;
const KABUK_CEVRIMDISI = /Cihaza bağlanılamıyor/;
const ANA_CEVRIMDISI = /Canlı bağlantı yok/;

const bobin = (id: number, running: boolean) => ({
  id, running, connected: true, frequencyHz: running ? 100 : 0, dutyCycle: running ? 40 : 0,
  magneticMt: 0, objectTemp: 0, ambientTemp: 0, currentA: 0, measuredFields: [],
});
const snap = (ek: Record<string, unknown> = {}, calisan = false) => ({
  gateway: "online", mqtt: "devre_disi", stm: "online", internet: "offline", patient: null,
  activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
  coils: [1, 2, 3, 4, 5, 6, 7].map((i) => bobin(i, calisan && i === 1)).concat([{ ...bobin(8, false), connected: false }]),
  notifications: [], system: {},
  ...ek,
});
const kapanisMandali = (bosta: boolean) => ({ aktif: true, neden: "uygulama_kapanisi", nesil: 2, oncekiOturum: false, bostaKapanis: bosta });

const kabuk = (rota: "dashboard" | "patients" = "dashboard") => (
  <AppShell activeRoute={rota} title="T" subtitle="" onRouteChange={jest.fn()}>
    {rota === "dashboard" ? <DashboardScreen /> : <></>}
  </AppShell>
);

let hataSus: jest.SpyInstance;
beforeEach(() => {
  hataSus = jest.spyOn(console, "error").mockImplementation(() => undefined);
  mockDurdur.mockReset();
});
afterEach(() => hataSus.mockRestore());

describe("BE 2 — ACİL DURDUR ekranı (Y226–Y228)", () => {
  it("KRİTİK Y226: BOŞTA kapanış (bağlıyken) → mandal ALARM bandı YOK, Sıfırla YOK, teyitsiz düğme YOK, tek NÖTR satır VAR", () => {
    mockCanli = {
      bagli: true,
      snap: snap({ estopMandali: kapanisMandali(true), estopTeyit: { teyitli: false, kaynak: "estop", calisiyordu: false } }),
    };
    const u = render(kabuk("patients"));
    expect(u.queryByText(BANT)).toBeNull();
    expect(u.queryByText("Sıfırla")).toBeNull();
    expect(u.queryByText(TEYITSIZ)).toBeNull();
    expect(u.queryAllByText(NOTR)).toHaveLength(1);
  });

  it("KRİTİK Y226 + Y228: BOŞTA kapanıştan sonra bağlantı koptu → yalnız TEK nötr satır (kabuk), kırmızı 'bağlanılamıyor' ve mandal bandı YOK", () => {
    mockCanli = {
      bagli: false,
      snap: snap({ estopMandali: kapanisMandali(true), estopTeyit: { teyitli: false, kaynak: "estop", calisiyordu: false } }),
    };
    const u = render(kabuk());
    expect(u.queryAllByText(NOTR)).toHaveLength(1);
    expect(u.queryByText(KABUK_CEVRIMDISI)).toBeNull();
    expect(u.queryByText(BANT)).toBeNull();
    expect(u.queryByText(ANA_CEVRIMDISI)).toBeNull();
  });

  it("KRİTİK (değişmez): ÇALIŞIRKEN kapanış → bant VAR + doğru neden + teyitsiz düğme VAR, nötr satır YOK", () => {
    mockCanli = {
      bagli: true,
      snap: snap({ estopMandali: kapanisMandali(false), estopTeyit: { teyitli: false, kaynak: "stm_yanitsiz", calisiyordu: true } }),
    };
    const u = render(kabuk("patients"));
    expect(u.queryByText(BANT)).not.toBeNull();
    expect(u.queryByText(/uygulama seans ya da bobin çalışırken kapatıldı/)).not.toBeNull();
    expect(u.queryByText(TEYITSIZ)).not.toBeNull();
    expect(u.queryAllByText(NOTR)).toHaveLength(0);
  });

  it.each([
    ["boştaydı", false, false],
    ["çalışıyordu", true, true],
    ["bilinmiyor (okunamadı)", null, true],
    ["eski backend (alan yok)", undefined, true],
  ])("KRİTİK Y227: teyitsiz durdurma + %s → teyitsiz düğme görünür: %s", (_ad, calisiyordu, gorunur) => {
    const teyit: Record<string, unknown> = { teyitli: false, kaynak: "stm_yanitsiz" };
    if (calisiyordu !== undefined) teyit.calisiyordu = calisiyordu;
    mockCanli = { bagli: true, snap: snap({ estopTeyit: teyit }) };
    const u = render(kabuk("patients"));
    expect(u.queryByText(TEYITSIZ) !== null).toBe(gorunur);
  });

  it.each([
    ["boştaydı", { confirmed: false, kartReddetti: false, calisiyordu: false }, false],
    ["çalışıyordu", { confirmed: false, kartReddetti: false, calisiyordu: true }, true],
    ["eski backend (alan yok)", { confirmed: false, kartReddetti: false }, true],
  ])("KRİTİK Y227: düğmenin KENDİ teyitsiz basışı + %s (yanıt %j) → bobinler durunca düğme kalır: %s", async (_ad, yanit, kalir) => {
    mockCanli = { bagli: true, snap: snap({}, true) };
    mockDurdur.mockResolvedValue(yanit);
    const u = render(kabuk("patients"));
    const dugme = u.getByText(/ACİL DURDUR \(1 bobin\)/);
    await act(async () => {
      fireEvent.press(dugme);
    });
    expect(mockDurdur).toHaveBeenCalledTimes(1);
    mockCanli = { bagli: true, snap: snap({}, false) };
    u.rerender(kabuk("patients"));
    expect(u.queryByText(TEYITSIZ) !== null).toBe(kalir);
  });

  it("KRİTİK Y228: bağlantı YOKKEN mandal bandı (operatör ACİL DURDUR'u) gizli; kabuğun çevrimdışı bandı TEK", () => {
    mockCanli = {
      bagli: false,
      snap: snap({ estopMandali: { aktif: true, neden: "manual", nesil: 3, oncekiOturum: false, bostaKapanis: false } }),
    };
    const u = render(kabuk());
    expect(u.queryByText(BANT)).toBeNull();
    expect(u.queryByText("Sıfırla")).toBeNull();
    expect(u.queryAllByText(KABUK_CEVRIMDISI)).toHaveLength(1);
    expect(u.queryByText(ANA_CEVRIMDISI)).toBeNull();
    expect(u.queryAllByText(NOTR)).toHaveLength(0);
  });

  it("KARŞIT Y228: bağlantı GELİNCE gerçek mandal bandı + Sıfırla görünür", () => {
    mockCanli = {
      bagli: true,
      snap: snap({ estopMandali: { aktif: true, neden: "manual", nesil: 3, oncekiOturum: false, bostaKapanis: false } }),
    };
    const u = render(kabuk());
    expect(u.queryByText(BANT)).not.toBeNull();
    expect(u.queryByText("Sıfırla")).not.toBeNull();
  });

  it("KRİTİK (Ö.4-Y8): bobin çalışırken bağlantı koparsa ACİL DURDUR düğmesi KALIR", () => {
    mockCanli = { bagli: false, snap: snap({}, true) };
    const u = render(kabuk("patients"));
    expect(u.queryAllByLabelText(/acil durdur/i).length).toBeGreaterThanOrEqual(1);
  });
});
