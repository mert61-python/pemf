// Author: mertaygn, cglrgrkn
/**
 * D1.E02 · İG-6.2 · A-51 — kayan ACİL DURDUR YALNIZ ekran GERÇEKTEN kendi durdurma düğmesini çiziyorsa gizlenir.
 * ===========================================================================================================
 * ÖLÇÜLEN KUSUR (aday doğrulaması İG-6.2, gerçek web paketi + backend + sahte STM): `AppShell` GES'i ROTA ADINA göre
 * ("control", "dashboard") gizliyordu. (A) Kontrol ekranı hata kartına düşünce (bozuk paket) ekranda durdurma kontrolü
 * 0. (B) Ana Ekran'da manuel seans sırasında STM koptu → Ana Ekran'ın kendi 🚨 düğmesi kayboldu (`hardwareRunning`
 * false), GES rota kümesinde gizli → 0. Sahip kararı A-51: rota adına göre gizleme KALKAR; hata kartında ya da düğme
 * yoksa kayan düğme GÖRÜNÜR (Ö.4-Y8: durdurma hiçbir koşulda kaybolmaz).
 *
 * Gerçek olanlar: `AppShell`, `GlobalEmergencyStop`, `ErrorBoundary`, `DashboardScreen` (+ `CoilCard` vb.). Sahte olan:
 * canlı veri kaynağı (`useLiveData`), ağ/servisler, kabuk süsleri.
 *
 * KARŞIT (sahip 2026-09-12 "zaten bir sürü var"): Ana Ekran kendi düğmesini çizerken kayan kutu GİZLİ kalır (tek düğme).
 *
 * ⚠️ MUTASYON: gizleme yeniden rota adına bağlanırsa (A)/(B) KIRMIZI; kayıt hiç yapılmazsa (gizleme hiç olmaz) KARŞIT
 * KIRMIZI.
 */
jest.mock("@/services/apiClient", () => ({
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb ?? null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true })),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "UYARI",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "gövde",
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
let mockSnap: any;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live",
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
import { render } from "@testing-library/react-native";
import { AppShell } from "@/components/ui/AppShell";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { ROUTE_ACCESS } from "@/config/access";
import type { RouteKey } from "@/types/domain";

const bobin = (id: number, running: boolean, connected = true) => ({
  id, running, connected, frequencyHz: running ? 100 : 0, dutyCycle: running ? 40 : 0,
  magneticMt: 0, objectTemp: 0, ambientTemp: 0, currentA: 0, measuredFields: [],
});
const snap = (stm: string, running: boolean) => ({
  gateway: "online", mqtt: "devre_disi", stm, internet: "offline",
  patient: null,
  activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
  coils: [1, 2, 3, 4, 5, 6, 7].map((i) => bobin(i, running && i === 1, stm === "online")).concat([bobin(8, false, false)]),
  notifications: [], system: {},
});

function Patlayan(): React.ReactElement {
  throw new Error("Requiring unknown module (bozuk paket benzetimi)");
}

const kabuk = (rota: RouteKey, icerik: React.ReactNode) => (
  <AppShell activeRoute={rota} title="T" subtitle="" onRouteChange={jest.fn()}>
    <ErrorBoundary key={rota}>{icerik}</ErrorBoundary>
  </AppShell>
);
const durdurmaSayisi = (u: ReturnType<typeof render>) => u.queryAllByLabelText(/acil durdur/i).length;

let hataSus: jest.SpyInstance;
beforeEach(() => {
  hataSus = jest.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => hataSus.mockRestore());

describe("D1.E02 / A-51 — kayan ACİL DURDUR gizlemesi görünür durdurma kontrolüne bağlı", () => {
  it("KRİTİK (A): Kontrol ekranı hata kartına düşerse bobin çalışırken ≥1 durdurma kontrolü kalır", () => {
    mockSnap = snap("online", true);
    const u = render(kabuk("control", <Patlayan />));
    expect(durdurmaSayisi(u)).toBeGreaterThanOrEqual(1);
  });

  it("KRİTİK (B): Ana Ekran'da STM kopunca (kendi düğmesi kaybolur) GES '(bağlantı yok)' ile görünür", () => {
    mockSnap = snap("online", true);
    const u = render(kabuk("dashboard", <DashboardScreen />));
    expect(durdurmaSayisi(u)).toBe(1); // aparat: kopuştan önce Ana Ekran'ın kendi düğmesi
    mockSnap = snap("warning", false); // STM koptu: bobinler running:false ("bilinmiyor")
    u.rerender(kabuk("dashboard", <DashboardScreen />));
    expect(durdurmaSayisi(u)).toBeGreaterThanOrEqual(1);
    expect(u.queryByText(/bağlantı yok/)).not.toBeNull();
  });

  it("KARŞIT (sahip 2026-09-12): Ana Ekran kendi düğmesini çizerken kayan kutu GİZLİ — tek düğme", () => {
    mockSnap = snap("online", true);
    const u = render(kabuk("dashboard", <DashboardScreen />));
    expect(durdurmaSayisi(u)).toBe(1);
    expect(u.queryByText(/ACİL DURDUR \(1 bobin\)/)).toBeNull(); // görünen tek düğme Ana Ekran'ınki
  });

  it("KRİTİK: kendi düğmesini ÇİZMEYEN hiçbir rotada GES gizlenmez (tüm rotalar, rota adı yetki vermez)", () => {
    // Eski rota-kümesi pininin (globalAcilDurdurKapsami) DAVRANIŞSAL yerine geçer: gizleme bir rota adına bağlanırsa
    // o rotada içerik düğme çizmediği hâlde kayan kutu kaybolur.
    mockSnap = snap("online", true);
    const rotalar = Array.from(new Set(Object.values(ROUTE_ACCESS).flat()));
    expect(rotalar).toEqual(expect.arrayContaining(["control", "dashboard", "ai", "patients"]));
    for (const rota of rotalar) {
      const u = render(kabuk(rota, <></>));
      expect([rota, u.queryAllByText(/ACİL DURDUR \(1 bobin\)/).length]).toEqual([rota, 1]);
      u.unmount();
    }
  });
});
