/**
 * KP-3 C · src/PemfApp.tsx — kök kompozisyon + ana yönlendirici (her test bir DAVRANIŞ iddiası):
 *  - Kök: oturum yokken giriş ekranı; oturum açılırken (yükleme) yükleme göstergesi + ACİL DURDUR; profil seçilmeden karşılama ekranı;
 *    "hesap ekle" kipinde giriş ekranı hesap-ekleme kipinde açılır.
 *  - Yönlendirici: her rota kendi (TEMBEL yüklenen) ekranını çizer; profilin ERİŞEMEDİĞİ rota istenirse profilin açılış rotasına düşülür
 *    (ev sahibi Kontrol'e geçemez → Akıllı Teşhis).
 * SAHTE: bağlam sağlayıcıları (girdi), kabuk (AppShell — aldığı props kaydedilir), ekranlar (ad yazan yer tutucular), ACİL DURDUR çizimi,
 *        React.lazy'nin `import()` adımı (platform: jest dinamik içe aktarmayı çalıştıramaz — aşağıda).
 * GERÇEK: PemfApp + AuthGate + MainRouter + erişim kuralları (config/access) + ErrorBoundary + Suspense + tembel fabrikaların modül/ad eşlemesi.
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(() => Promise.resolve(null)) }));
let mockAuth: Record<string, unknown> = {};
let mockKip: string | null = null;
jest.mock("@/context/AuthContext", () => ({ AuthProvider: ({ children }: { children: unknown }) => children, useAuth: () => mockAuth }));
jest.mock("@/context/LiveDataContext", () => ({
  LiveDataProvider: ({ children }: { children: unknown }) => children,
  useLiveData: () => ({ snapshot: { activeTreatment: { isActive: false } } }),
}));
jest.mock("@/context/EntitlementContext", () => ({ EntitlementProvider: ({ children }: { children: unknown }) => children }));
jest.mock("@/context/UserModeContext", () => ({ UserModeProvider: ({ children }: { children: unknown }) => children, useUserMode: () => ({ userMode: mockKip }) }));
jest.mock("@/context/OperatorContext", () => ({ OperatorProvider: ({ children }: { children: unknown }) => children }));
jest.mock("@/context/AppNavContext", () => ({ AppNavProvider: ({ children }: { children: unknown }) => children }));
let mockKabuk: { activeRoute: string; onRouteChange: (r: string) => void } | null = null;
jest.mock("@/components/ui/AppShell", () => ({
  AppShell: (p: { activeRoute: string; onRouteChange: (r: string) => void; children: unknown }) => { mockKabuk = p; return p.children; },
}));
jest.mock("@/components/ui/GlobalEmergencyStop", () => {
  const { Text } = require("react-native");
  return { GlobalEmergencyStop: () => <Text>ACIL-DURDUR</Text> };
});
// ⚠️ PLATFORM: jest (`--experimental-vm-modules` olmadan) `import()` ÇALIŞTIRAMAZ → tembel ekranlar burada hiç yüklenmezdi (ekran
// sınırı hata kartı gösterirdi). En alt erişilebilir katman `React.lazy`: fabrikanın ADLANDIRDIĞI modül + dışa aktarım eşzamanlı yüklenir.
// Böylece "hangi rota HANGİ ekranı çizer" eşlemesi yine üründen okunur (yanlış modül / yanlış ad → yanlış ekran → KIRMIZI).
jest.mock("react", () => {
  const R = jest.requireActual("react");
  const lazy = (f: () => unknown) => {
    const kaynak = String(f);
    const yol = /import\(["']([^"']+)["']\)/.exec(kaynak)?.[1];
    const ad = /default:\s*\w+\.(\w+)/.exec(kaynak)?.[1];
    if (!yol || !ad) throw new Error(`tembel fabrika çözümlenemedi: ${kaynak}`);
    return (p: object) => R.createElement(require(yol)[ad], p);
  };
  return { ...R, lazy, default: { ...R, lazy } };
});
// Yer tutucular fabrikaların İÇİNDE: jest.mock hoist edilir, dış değişken eager import anında henüz yoktur (TDZ).
jest.mock("@/screens/DashboardScreen", () => ({ DashboardScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:dashboard") }));
jest.mock("@/screens/WelcomeScreen", () => ({ WelcomeScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:welcome") }));
jest.mock("@/screens/AuthScreen", () => {
  const { Text } = require("react-native");
  return { AuthScreen: (p: { hesapEkleme?: boolean }) => <Text>{`EKRAN:auth${p.hesapEkleme ? ":ekleme" : ""}`}</Text> };
});
jest.mock("@/screens/ControlScreen", () => ({ ControlScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:control") }));
jest.mock("@/screens/DemaSimulatorScreen", () => ({ DemaSimulatorScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:simulator") }));
jest.mock("@/screens/KpiDashboardScreen", () => ({ KpiDashboardScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:kpi") }));
jest.mock("@/screens/SensorMonitorScreen", () => ({ SensorMonitorScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:sensors") }));
jest.mock("@/screens/TreatmentHistoryScreen", () => ({ TreatmentHistoryScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:history") }));
jest.mock("@/screens/PatientScreen", () => ({ PatientScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:patients") }));
jest.mock("@/screens/AiHubScreen", () => ({ AiHubScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:ai") }));
jest.mock("@/screens/SettingsScreen", () => ({ SettingsScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:settings") }));
jest.mock("@/screens/AiHistoryScreen", () => ({ AiHistoryScreen: () => require("react").createElement(require("react-native").Text, null, "EKRAN:ai_history") }));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { PemfApp } from "@/PemfApp";

const OTURUM = { email: "dr@klinik.com" };
beforeEach(() => {
  mockAuth = { session: OTURUM, loading: false, hesapEkleniyor: false, hesapEklemeVazgec: jest.fn() };
  mockKip = "veterinarian";
  mockKabuk = null;
});

describe("kök kapılar", () => {
  it("oturum yok → giriş; yükleniyor → gösterge + ACİL DURDUR; profil yok → karşılama; hesap ekle → giriş (ekleme kipi)", () => {
    mockAuth = { ...mockAuth, session: null };
    expect(render(<PemfApp />).getByText("EKRAN:auth")).toBeTruthy();
    mockAuth = { ...mockAuth, loading: true };
    const y = render(<PemfApp />);
    expect(y.getByText("ACIL-DURDUR")).toBeTruthy();
    expect(y.queryByText(/^EKRAN:/)).toBeNull();
    mockAuth = { ...mockAuth, loading: false, session: OTURUM };
    mockKip = null;
    expect(render(<PemfApp />).getByText("EKRAN:welcome")).toBeTruthy();
    mockKip = "veterinarian";
    mockAuth = { ...mockAuth, hesapEkleniyor: true };
    expect(render(<PemfApp />).getByText("EKRAN:auth:ekleme")).toBeTruthy();
  });
});

describe("yönlendirici", () => {
  it("her rota kendi tembel ekranını çizer", async () => {
    const u = render(<PemfApp />);
    expect(u.getByText("EKRAN:dashboard")).toBeTruthy(); // veteriner açılış rotası
    for (const r of ["control", "sensors", "history", "patients", "kpi", "simulator", "ai", "ai_history", "settings"]) {
      await act(async () => { mockKabuk!.onRouteChange(r); });
      expect(await u.findByText(`EKRAN:${r}`)).toBeTruthy();
      expect(mockKabuk!.activeRoute).toBe(r);
    }
  });

  it("profilin erişemediği rota → açılış rotası (ev sahibi Kontrol'e geçemez)", async () => {
    mockKip = "pet_owner";
    const u = render(<PemfApp />);
    expect(await u.findByText("EKRAN:ai")).toBeTruthy();
    await act(async () => { mockKabuk!.onRouteChange("control"); });
    expect(u.queryByText("EKRAN:control")).toBeNull();
    expect(mockKabuk!.activeRoute).toBe("ai");
  });
});
