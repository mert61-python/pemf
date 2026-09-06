// Author: mertaygn, cglrgrkn
/**
 * WelcomeScreen + AppShell profil menusu — yalniz KURULU profiller gorunur
 * (profil kaldirma denetimi, 2026-09-06).
 *
 * Baslatici uygulamayi `?profiles=home,research` ile acinca (vet kaldirilmis):
 *  1. Hos geldiniz ekraninda "Veteriner Hekim" karti CIZILMEZ; diger iki kart cizilir.
 *  2. Ust-bar "Profil degistir" menusunde de "Veteriner Hekim" satiri YOKTUR (ayni kaynak:
 *     installedModes()). Ikisi ayni anda kilitlenir — menu filtresi eksikse kullanici modelleri
 *     silinmis profile buradan gecebilirdi.
 *  3. Bayat localStorage ("home,vet,research") parametreyi EZEMEZ — kart geri gelmez.
 *  4. Parametre + depo YOK → uc kart da cizilir (mobil / eski baslatici davranisi korunur).
 *
 * Bu dosya `@/services/installedProfiles`i MOCK'LAMAZ: URL → ekran zinciri ucundan uca olculur.
 * MUTASYON: WelcomeScreen'de `showMode("veterinarian") &&` kosulu silinirse 1 ve 3 KIRMIZI;
 * AppShell'de `PROFILE_LIST.filter(...)` kaldirilirsa 2 KIRMIZI; installedModes parametreyi
 * okumazsa 1-3 KIRMIZI.
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
  EMERGENCY_STOP_UNCONFIRMED_BODY: "govde",
}));
jest.mock("@/components/ui/AuroraBackground", () => ({ AuroraBackground: () => null }));
jest.mock("@/components/ui/NotificationCenter", () => ({ NotificationCenter: () => null }));
jest.mock("@/components/ui/UpdateBanner", () => ({ UpdateBanner: () => null }));
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({ GlobalEmergencyStop: () => null }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
// Kabuk bantlari async state gunceller (act uyarisi); konumuz profil menusu → cizilmez.
jest.mock("@/components/domain/SurumFarkiBanner", () => ({ SurumFarkiBanner: () => null }));
jest.mock("@/components/domain/RecoveryCodeBanner", () => ({ RecoveryCodeBanner: () => null }));
jest.mock("@/components/domain/MobileUpdateBanner", () => ({ MobileUpdateBanner: () => null }));
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
    snapshot: { coils: [], activeTreatment: { isActive: false } },
    connectionQuality: "live",
    unreadCount: 0,
    reconnect: jest.fn(),
  }),
}));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "pet_owner", setUserMode: jest.fn() }),
}));
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ session: { email: "op@klinik.com" }, logout: jest.fn() }),
}));
jest.mock("@/context/EntitlementContext", () => ({
  useEntitlement: () => ({ tier: "pro", trialing: false, trialDaysLeft: 0, realtime: true, research: true }),
}));

import React from "react";
import { Platform, Text } from "react-native";
import { render, fireEvent } from "@testing-library/react-native";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { AppShell } from "@/components/ui/AppShell";

const KEY = "pemf_installed_profiles";
const depo = new Map<string, string>();
function pencereyiKur(search: string) {
  const ls = {
    getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
    setItem: (k: string, v: string) => { depo.set(k, v); },
    removeItem: (k: string) => { depo.delete(k); },
    clear: () => depo.clear(),
  };
  const g = globalThis as Record<string, unknown>;
  if (!g.window) g.window = {};
  const w = g.window as Record<string, unknown>;
  Object.defineProperty(w, "location", { value: { search, hostname: "127.0.0.1" }, configurable: true, writable: true });
  Object.defineProperty(w, "localStorage", { value: ls, configurable: true, writable: true });
}
const setOS = (os: string) => { (Platform as unknown as { OS: string }).OS = os; };

const KART = {
  home: "Evcil Hayvan Sahibi profili",
  vet: "Veteriner Hekim profili",
  research: "Araştırma Modu profili",
};

beforeEach(() => {
  depo.clear();
  setOS("web");
});
afterAll(() => setOS("ios"));

describe("WelcomeScreen — yalniz kurulu profiller", () => {
  it("1. ?profiles=home,research → 'Veteriner Hekim' karti CIZILMEZ, diger ikisi cizilir", () => {
    pencereyiKur("?v=1725580800&profiles=home,research");
    const u = render(<WelcomeScreen />);
    expect(u.queryByLabelText(KART.vet)).toBeNull();
    expect(u.getByLabelText(KART.home)).toBeTruthy();
    expect(u.getByLabelText(KART.research)).toBeTruthy();
  });

  it("3. KRITIK: bayat localStorage ('home,vet,research') parametreyi EZEMEZ — vet karti geri gelmez", () => {
    depo.set(KEY, "home,vet,research");
    pencereyiKur("?profiles=home,research");
    const u = render(<WelcomeScreen />);
    expect(u.queryByLabelText(KART.vet)).toBeNull();
    expect(u.getByLabelText(KART.home)).toBeTruthy();
    expect(u.getByLabelText(KART.research)).toBeTruthy();
    expect(depo.get(KEY)).toBe("home,research");
  });

  it("4. parametre + depo YOK → uc kart da cizilir (mobil / bilgi yok)", () => {
    pencereyiKur("");
    const u = render(<WelcomeScreen />);
    expect(u.getByLabelText(KART.home)).toBeTruthy();
    expect(u.getByLabelText(KART.vet)).toBeTruthy();
    expect(u.getByLabelText(KART.research)).toBeTruthy();
  });

  it("yalniz vet kurulu (?profiles=vet) → yalniz 'Veteriner Hekim' karti", () => {
    pencereyiKur("?profiles=vet");
    const u = render(<WelcomeScreen />);
    expect(u.getByLabelText(KART.vet)).toBeTruthy();
    expect(u.queryByLabelText(KART.home)).toBeNull();
    expect(u.queryByLabelText(KART.research)).toBeNull();
  });
});

describe("AppShell profil menusu — ayni kaynak (installedModes)", () => {
  const kabuk = () =>
    render(
      <AppShell activeRoute="dashboard" title="T" subtitle="A" onRouteChange={jest.fn()}>
        <Text>icerik</Text>
      </AppShell>
    );

  it("2. ?profiles=home,research → menude 'Veteriner Hekim' satiri YOK", () => {
    pencereyiKur("?profiles=home,research");
    const u = kabuk();
    fireEvent.press(u.getByLabelText("Profil değiştir"));
    expect(u.getByText("Profil Değiştir")).toBeTruthy(); // menu acildi
    expect(u.queryByText("Veteriner Hekim")).toBeNull();
    expect(u.getByText("Evcil Hayvan Sahibi")).toBeTruthy();
    expect(u.getByText("Araştırma Modu")).toBeTruthy();
  });

  it("karsit kanit: parametre + depo yok → menude uc profil de var", () => {
    pencereyiKur("");
    const u = kabuk();
    fireEvent.press(u.getByLabelText("Profil değiştir"));
    expect(u.getByText("Veteriner Hekim")).toBeTruthy();
    expect(u.getByText("Evcil Hayvan Sahibi")).toBeTruthy();
    expect(u.getByText("Araştırma Modu")).toBeTruthy();
  });
});
