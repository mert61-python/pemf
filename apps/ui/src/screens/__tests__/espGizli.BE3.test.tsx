// Author: mertaygn, cglrgrkn
/**
 * BE 3 · Y230 — ESP KAPALIYKEN ESP / MQTT yüzeyleri arayüzden GİZLİ (telefon + masaüstü + web aynı kod); `espEtkin: true` ile hepsi geri.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR (31.10 canlı): ESP kapalıyken Ana Ekran "ESP / MQTT" rozeti YEŞİL — backend `network.status` broker erişilebilir olunca
 * ESP kapısız "online" yazıyordu ve arayüz rozeti `mqtt !== "devre_disi"` ile çiziyordu. Sistem Durumu'nda "Sistem Bağlantısı" (MQTT) ve
 * "Cihaz Köprüsü" satırları; Kontrol ekranının "Bağlantı yok" uyarısında "(STM32/WiFi çevrimdışı)" (WiFi = ESP).
 * TEK KAYNAK: backend'in ESP-etkin bilgisi (`snapshot.espEtkin`, `espEtkinMi`) — MQTT durumundan TÜRETİLMEZ (rozet "online" olsa da gizli).
 * Gerçek: `AppShell` + `DashboardScreen`, `GatewayStatusPanel`, `ControlScreen`. Sahte: canlı veri, ağ, ağır paneller. Backend tarafı:
 * `tests/test_BE3_esp_kapaliyken_MQTT_DEVRE_DISI_ve_yuzeysiz.py`.
 */
const mockAlert = jest.fn();
const mockGet = jest.fn(async (_p: string, fb: unknown) => fb ?? null);
jest.mock("@/services/apiClient", () => ({
  platformAlert: (...a: unknown[]) => mockAlert(...a),
  platformConfirm: jest.fn(async () => true),
  apiGet: (...a: [string, unknown]) => mockGet(...a),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/services/emergencyStop", () => ({ performEmergencyStop: jest.fn(async () => ({ confirmed: true })) }));
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
    startSession: jest.fn(async () => true), stopSession: jest.fn(async () => true), emergencyStop: jest.fn(),
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
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operator: "Dr. X" }), useOperatorOptional: () => null }));
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => ({ navigate: jest.fn(), goTo: jest.fn() }) }));
jest.mock("@/components/domain/SessionProgressCard", () => ({ SessionProgressCard: () => null }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { AppShell } from "@/components/ui/AppShell";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { ControlScreen } from "@/screens/ControlScreen";
import { GatewayStatusPanel } from "@/components/domain/GatewayStatusPanel";

const bobin = (id: number, connected: boolean) => ({
  id, running: false, connected, stm32Driven: id <= 7, frequencyHz: 0, dutyCycle: 0,
  magneticMt: 0, objectTemp: 0, ambientTemp: 0, currentA: 0, measuredFields: [],
});
/** `espEtkin` undefined = eski backend (alan yok). `mqtt: "online"` = 31.10'daki yanlış yeşil (rozet MQTT'den türetilmemeli). */
const snap = (espEtkin: boolean | undefined, stm = "online") => ({
  gateway: "online", mqtt: "online", stm, internet: "offline", patient: { name: "Boncuk", species: "Kedi", breed: "", owner: "S" },
  ...(espEtkin === undefined ? {} : { espEtkin }),
  activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
  coils: [1, 2, 3, 4, 5, 6, 7].map((i) => bobin(i, stm === "online")).concat([bobin(8, false)]),
  notifications: [], system: {}, sessions: [],
});

let hataSus: jest.SpyInstance;
beforeEach(() => {
  hataSus = jest.spyOn(console, "error").mockImplementation(() => undefined);
  mockAlert.mockReset();
  mockGet.mockClear();
});
afterEach(() => hataSus.mockRestore());

describe("BE 3 — ESP / MQTT yüzeyleri (Y230)", () => {
  it.each([
    ["ESP kapalı", false, false],
    ["eski backend (alan yok)", undefined, false],
    ["ESP açık (PEMF_ESP_ENABLED=1)", true, true],
  ])("KRİTİK: Ana Ekran 'ESP / MQTT' rozeti — %s (espEtkin=%s) → görünür: %s (mqtt 'online' olsa da)", (_ad, esp, gorunur) => {
    mockSnap = snap(esp);
    const u = render(
      <AppShell activeRoute="dashboard" title="T" subtitle="" onRouteChange={jest.fn()}>
        <DashboardScreen />
      </AppShell>
    );
    expect(u.queryByText("ESP / MQTT") !== null).toBe(gorunur);
  });

  it.each([
    ["ESP kapalı", false, false],
    ["eski backend (alan yok)", undefined, false],
    ["ESP açık", true, true],
  ])("KRİTİK: Sistem Durumu MQTT / köprü satırları — %s (espEtkin=%s) → görünür: %s; diğer satırlar her zaman", async (_ad, esp, gorunur) => {
    mockSnap = snap(esp);
    const u = render(<GatewayStatusPanel />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(u.queryByText("Sistem Bağlantısı") !== null).toBe(gorunur);
    expect(u.queryByText("Cihaz Köprüsü") !== null).toBe(gorunur);
    expect(u.queryByText("Uygulama Bağlantısı")).not.toBeNull();
    expect(u.queryByText("Donanım Sürücüsü")).not.toBeNull();
    expect(u.queryByText("İnternet Bağlantısı")).not.toBeNull();
  });

  it.each([
    ["ESP kapalı", false, "Seçili bobinler için aktif bağlantı yok (STM32 çevrimdışı)."],
    ["ESP açık", true, "Seçili bobinler için aktif bağlantı yok (STM32/WiFi çevrimdışı)."],
  ])("KRİTİK: Kontrol 'Bağlantı yok' uyarısı — %s (espEtkin=%s) → %s", async (_ad, esp, govde) => {
    mockSnap = snap(esp, "warning");
    const u = render(<ControlScreen />);
    await act(async () => {});
    await act(async () => {
      fireEvent.press(u.getByText("▶ Başlat"));
    });
    const uyari = mockAlert.mock.calls.find((c) => c[0] === "Bağlantı yok");
    expect(uyari).toBeDefined();
    expect(uyari![1]).toBe(govde);
  });
});
