// Author: mertaygn, cglrgrkn
/**
 * D1.81 · Y4 — mandal bandı GERÇEKTEN takılı mı: AppShell (her rota), Karşılama (WelcomeScreen) ve Giriş (AuthScreen).
 *
 * Bileşenin kendi testi davranışı ölçer; bu dosya YERLEŞİMİ ölçer ("bileşen var ama hiçbir ekran kullanmıyor"
 * tuzağı — D1.37 dersi). A-58 / Y23 ile tutarlılık: uygulama acil durdurmadan sonra yeniden açılırsa ya da oturum
 * yokken de mandal durumu ve "Sıfırla" görünmeli. Kabukta ACİL DURDUR bant varken de çizilir (Ö.4-Y8: bant hiçbir
 * şeyi kapılamaz). Bant bir işaretleyiciyle değiştirilir (gerçek bileşen kendi testinde).
 */
jest.mock("@/components/ui/EstopMandalBandi", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require("react");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { Text } = require("react-native");
  return { EstopMandalBandi: () => R.createElement(Text, { testID: "mandal-bandi" }, "MANDAL") };
});
jest.mock("@/services/apiClient", () => ({
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
}));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true })),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "UYARI",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "gövde",
}));
const mockGes: unknown[] = [];
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({
  GlobalEmergencyStop: (p: unknown) => {
    mockGes.push(p);
    return null;
  },
}));
jest.mock("@/services/installedProfiles", () => ({ installedModes: () => null }));
jest.mock("@/components/ui/AuroraBackground", () => ({ AuroraBackground: () => null }));
jest.mock("@/components/ui/NotificationCenter", () => ({ NotificationCenter: () => null }));
jest.mock("@/components/ui/UpdateBanner", () => ({ UpdateBanner: () => null }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/components/domain/SurumFarkiBanner", () => ({ SurumFarkiBanner: () => null }));
jest.mock("@/components/domain/RecoveryCodeBanner", () => ({ RecoveryCodeBanner: () => null }));
jest.mock("@/components/domain/MobileUpdateBanner", () => ({ MobileUpdateBanner: () => null }));
jest.mock("@/components/domain/KayitDbBandi", () => ({ KayitDbBandi: () => null }));
jest.mock("expo-blur", () => ({ BlurView: () => null }));
jest.mock("expo-linear-gradient", () => ({ LinearGradient: () => null }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/hooks/useKeyboard", () => ({
  useKeyboard: () => ({ acik: false, yukseklik: 0 }),
  KAV_BEHAVIOR_PENCERE: undefined,
  KAV_BEHAVIOR_MODAL: undefined,
}));
jest.mock("@/hooks/useResponsive", () => ({
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  useResponsive: () => require("@/hooks/__tests__/responsiveMock").sahteMasaustu(),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: { coils: [], activeTreatment: { isActive: false }, estopMandali: { aktif: true, neden: "manual" } },
    connectionQuality: "live",
    unreadCount: 0,
    reconnect: jest.fn(),
  }),
}));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", setUserMode: jest.fn() }),
}));
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ session: { email: "op@klinik.com" }, logout: jest.fn() }),
}));
jest.mock("@/context/EntitlementContext", () => ({
  useEntitlement: () => ({ tier: "pro", trialing: false, trialDaysLeft: 0, realtime: true, research: true }),
}));
jest.mock("@/services/supabaseAuth", () => ({
  signUpUser: jest.fn(async () => ({ ok: true })),
  signInUser: jest.fn(async () => ({ ok: true })),
  sendPasswordReset: jest.fn(async () => ({ ok: true })),
}));

import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";
import { AppShell } from "@/components/ui/AppShell";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { AuthScreen } from "@/screens/AuthScreen";

beforeEach(() => {
  mockGes.length = 0;
});

describe("mandal bandı yerleşimi (Y4 · A-58 · Y23)", () => {
  it("KRITIK: kabuk (AppShell, her rota) bandı çizer ve ACİL DURDUR yerinde kalır", async () => {
    const u = render(
      <AppShell activeRoute="dashboard" title="T" subtitle="ALT" onRouteChange={jest.fn()}>
        <Text>içerik</Text>
      </AppShell>
    );
    await act(async () => {});
    expect(u.getByTestId("mandal-bandi")).toBeTruthy();
    expect(mockGes.length).toBeGreaterThan(0);
  });

  it("KRITIK: Karşılama ekranı (WelcomeScreen) bandı çizer", async () => {
    const u = render(<WelcomeScreen />);
    await act(async () => {});
    expect(u.getByTestId("mandal-bandi")).toBeTruthy();
  });

  it("KRITIK: Giriş ekranı (AuthScreen, oturum yokken) bandı çizer", async () => {
    const u = render(<AuthScreen />);
    await act(async () => {});
    expect(u.getByTestId("mandal-bandi")).toBeTruthy();
  });
});
