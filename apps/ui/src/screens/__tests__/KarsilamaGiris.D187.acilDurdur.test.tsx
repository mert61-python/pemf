// Author: mertaygn, cglrgrkn
/**
 * D1.87 · A-58 (Karşılama) + Y23 (Giriş) + 1-C §9 #1 — oturum açılmamışken / internet yokken de çalışan bobin DURDURULABİLİR.
 * =====================================================================================================================
 * ÖLÇÜLEN KUSUR (1-C inceleme i3-F-3): Karşılama ve Giriş ekranlarında yalnız mandal bandı ve "Sıfırla" vardı, ACİL DURDUR
 * YOKTU — ekran durduramadan mandalı kaldırabiliyordu (sıra ters). Uygulama bobinler çalışırken yeniden açılırsa (A-58)
 * ya da oturum düşerse ilk ekranda durdurma olmalı. GERÇEK `WelcomeScreen` / `AuthScreen` + GERÇEK `GlobalEmergencyStop`
 * (görünürlük kuralı kabukla AYNI: bobin çalışıyor / seans / STM belirsiz / teyitsiz). Profil kalıcılığı EKLENMEZ (Ö.4).
 * ⚠️ MUTASYON: ekrandan GES çıkarılırsa KRİTİK; GES koşulsuz çizilirse KARŞIT (boşta gürültü) KIRMIZI.
 */
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
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
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
let mockSnap: any = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnap, connectionQuality: "live", unreadCount: 0, reconnect: jest.fn() }),
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
import { act, render } from "@testing-library/react-native";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { AuthScreen } from "@/screens/AuthScreen";

const calisan = { stm: "online", coils: [{ id: 1, running: true, connected: true }], activeTreatment: { isActive: false } };
const bosta = { stm: "online", coils: [{ id: 1, running: false, connected: true }], activeTreatment: { isActive: false } };

describe("D1.87 / A-58 / Y23 — Karşılama ve Giriş ekranlarında ACİL DURDUR", () => {
  it.each([
    ["Karşılama (WelcomeScreen)", () => <WelcomeScreen />],
    ["Giriş (AuthScreen)", () => <AuthScreen />],
  ])("KRİTİK: %s — bobin çalışırken ACİL DURDUR düğmesi ekranda", async (_ad, Ekran) => {
    mockSnap = calisan;
    const u = render(<Ekran />);
    await act(async () => {});
    expect(u.queryByLabelText("Acil durdur")).not.toBeNull();
  });

  it.each([
    ["Karşılama (WelcomeScreen)", () => <WelcomeScreen />],
    ["Giriş (AuthScreen)", () => <AuthScreen />],
  ])("KARŞIT: %s — hiçbir şey çalışmıyorken düğme YOK (gürültü yok)", async (_ad, Ekran) => {
    mockSnap = bosta;
    const u = render(<Ekran />);
    await act(async () => {});
    expect(u.queryByLabelText("Acil durdur")).toBeNull();
  });
});
