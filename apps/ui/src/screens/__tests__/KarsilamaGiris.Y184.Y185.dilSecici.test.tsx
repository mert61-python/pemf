// Author: mertaygn, cglrgrkn
/**
 * Y184 (sahip 2026-10-22) — Karşılama (profil seçimi, Çıkış'ın yanında) ve Giriş ekranlarında "Türkçe | English" seçici; Ayarlar'daki
 * "Dil / Language" kartıyla AYNI kayıt (AsyncStorage `pemf.dil`, cihaz düzeyi — Y161); seçim anında ekran yeniden çizilir; bayrak
 * kapalıyken çizilmez.
 * Y185 = D6.26 (B-6.23 · B-6.34 · İG-6.108) — (a) Evcil Hayvan Sahibi kartı profilin GERÇEK yetkilerini anlatır (ROUTE_ACCESS[pet_owner]
 * = teşhis / hastalar / AI geçmişi / ayarlar — seans ve kontrol YOK; eski "tek tuşla güvenli seans başlatın" vaadi); (b) eşleştirme
 * rehberindeki yol menünün ve kart başlığının BUGÜNKÜ adlarından (eski "Daha Fazla → …", kod 6 KARAKTER — harf + rakam, "haneli" değil).
 * GERÇEK `WelcomeScreen` / `AuthScreen` + GERÇEK i18n kataloğu. Mutant: vaadi / eski yolu kataloğa geri yazan → KIRMIZI.
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
import { act, fireEvent, render } from "@testing-library/react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import i18n from "i18next";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { AuthScreen } from "@/screens/AuthScreen";
import { __bayrakTestiAyarla, DIL_DEPO_ANAHTARI } from "@/i18n/dil";
import { ROUTE_ACCESS } from "@/config/access";

mockSnap = { stm: "online", coils: [{ id: 1, running: false, connected: true }], activeTreatment: { isActive: false } };

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
  await AsyncStorage.clear();
});

describe("Y184 — giriş / karşılama ekranında dil seçici", () => {
  it.each([
    ["Karşılama (WelcomeScreen)", () => <WelcomeScreen />],
    ["Giriş (AuthScreen)", () => <AuthScreen />],
  ])("KRİTİK: %s — English seçilince ekran İngilizce ve seçim Ayarlar'la AYNI kayda yazılır", async (_ad, Ekran) => {
    __bayrakTestiAyarla(true);
    const u = render(<Ekran />);
    await act(async () => {});
    expect(u.getByTestId("dil-secici")).toBeTruthy();
    await act(async () => {
      fireEvent.press(u.getByTestId("dil-secici-en"));
    });
    expect(i18n.language).toBe("en");
    expect(await AsyncStorage.getItem(DIL_DEPO_ANAHTARI)).toBe("en");
    expect(u.getByTestId("dil-secici-en").props.accessibilityState).toEqual({ selected: true });
    await act(async () => {
      fireEvent.press(u.getByTestId("dil-secici-tr"));
    });
    expect(i18n.language).toBe("tr");
    expect(await AsyncStorage.getItem(DIL_DEPO_ANAHTARI)).toBe("tr");
  });

  it("KRİTİK: Karşılama'da seçici Çıkış ile AYNI üst satırda; İngilizcede Çıkış 'Sign out' olur (anında yeniden çizim)", async () => {
    __bayrakTestiAyarla(true);
    const u = render(<WelcomeScreen />);
    await act(async () => {});
    expect(u.getByText("Çıkış")).toBeTruthy();
    await act(async () => {
      fireEvent.press(u.getByTestId("dil-secici-en"));
    });
    expect(u.getByText("Sign out")).toBeTruthy();
  });

  it.each([
    ["Karşılama (WelcomeScreen)", () => <WelcomeScreen />],
    ["Giriş (AuthScreen)", () => <AuthScreen />],
  ])("KARŞIT: %s — İngilizce bayrağı kapalıyken seçici YOK", async (_ad, Ekran) => {
    __bayrakTestiAyarla(false);
    const u = render(<Ekran />);
    await act(async () => {});
    expect(u.queryByTestId("dil-secici")).toBeNull();
  });
});

describe("Y185 — profil kartı vaadi ve eşleştirme rehberi yolu GERÇEĞİ söyler", () => {
  it.each(["tr", "en"])("KRİTİK (%s): Evcil Hayvan Sahibi kartı seans / kontrol vaat ETMEZ (profilde yok)", async (dil) => {
    expect(ROUTE_ACCESS.pet_owner).not.toContain("control");
    await act(async () => {
      await i18n.changeLanguage(dil);
    });
    const u = render(<WelcomeScreen />);
    await act(async () => {});
    const aciklama = i18n.t("giris.hosGeldin.sahipAciklama");
    expect(u.getByText(aciklama)).toBeTruthy();
    for (const metin of [aciklama, i18n.t("giris.hosGeldin.sahipIpucu")]) {
      expect(metin).not.toMatch(/seans|session|tek tuş|tek-tuş|one tap|one-touch|kontrol|control/i);
      expect(metin).toMatch(/teşhis|diagnosis/i);
    }
  });

  it.each(["tr", "en"])("KRİTİK (%s): eşleştirme rehberi yolu = bugünkü menü adı → kart başlığı; kod 6 KARAKTER", async (dil) => {
    await act(async () => {
      await i18n.changeLanguage(dil);
    });
    const metin = i18n.t("ayarlar.eslestirmeRehberi.ekranAciklama");
    expect(metin).toContain(`${i18n.t("kabuk.menu.ayarlar")} → ${i18n.t("ayarlar.uzakErisim.baslik")}`);
    expect(metin).not.toMatch(/Daha Fazla|More →|haneli|digit/);
    expect(metin).toMatch(dil === "tr" ? /6 karakterlik/ : /6-character/);
  });
});
