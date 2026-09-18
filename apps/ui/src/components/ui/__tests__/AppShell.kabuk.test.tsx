// Author: mertaygn, cglrgrkn
/**
 * AppShell — KABUK DAVRANIŞI: ray · klavye · kısa ekran   [S2/S4/S5/S6, 2026-09-04 denetimi]
 * ==========================================================================================
 * ÖLÇÜLEN DURUM (denetim öncesi):
 *  · Kabuk yalnız `isDesktop` okuyordu: 768 px tablette ve 700 px'lik PC penceresinde 240 px'lik
 *    TAM kenar çubuğu çiziliyor, içeriğe 352 px kalıyordu. Ara kabuk (ikon rayı) yoktu.
 *  · Klavye açılınca alt bar klavyenin üstüne biniyor, ACİL DURDUR düğmesi klavyenin ALTINDA
 *    kalıyordu — hasta güvenliği düğmesi form doldururken erişilemez oluyordu.
 *  · Yatay telefonda (428 px yükseklik) başlık + alt başlık + alt bar ekranın yarısını yiyordu.
 *  · Alt bar etiketi 'Akıllı Teşhis' 5 slotta 320-360 px'te kırpılıyordu.
 *
 * BURADA KİLİTLENEN SÖZLEŞME:
 *  1. shellKind === "rail" → alt bar YOK, kenar çubuğu METİNSİZ, ama accessibilityLabel TAM ad.
 *  2. Klavye açık + native → alt bar UNMOUNT, ACİL DURDUR klavyenin ÜSTÜNE taşınır (GİZLENMEZ).
 *  3. Web'de klavye bayrağı alt barı kaldırmaz (RNW klavye olayı yaymaz; `isNative` kapısı).
 *  4. isShort → alt başlık gizlenir, ACİL DURDUR kompakt çizilir.
 *  5. Alt barda KISA etiket görünür; ekran okuyucu etiketi TAM kalır.
 *
 * ⚠️ MUTASYON: `desktop = shellKind !== "bottom"` yerine `isDesktop` konursa 1. vaka; `isNative`
 * kapısı silinirse 3. vaka; `bottomOffset` içindeki `klavye.acik` dalı silinirse 2. vaka KIRILIR.
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

// ACİL DURDUR çizilmek yerine ALDIĞI PROPS kaydedilir: konum/kompaktlık sözleşmesi düğmenin
// kendi testinde değil, KABUĞUN kararında yaşıyor.
const mockGesProps: { bottomOffset?: number; compact?: boolean }[] = [];
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({
  GlobalEmergencyStop: (p: { bottomOffset?: number; compact?: boolean }) => {
    mockGesProps.push(p);
    return null;
  },
}));

let mockKlavye = { acik: false, yukseklik: 0 };
jest.mock("@/hooks/useKeyboard", () => ({
  useKeyboard: () => mockKlavye,
  KAV_BEHAVIOR_PENCERE: undefined,
  KAV_BEHAVIOR_MODAL: undefined,
}));

let mockKabuk: "bottom" | "rail" | "sidebar" = "bottom";
let mockEkstra: Record<string, unknown> = {};
jest.mock("@/hooks/useResponsive", () => ({
  useResponsive: () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const m = require("@/hooks/__tests__/responsiveMock");
    const taban =
      mockKabuk === "sidebar" ? m.sahteMasaustu() : mockKabuk === "rail" ? m.sahteRay() : m.sahteTelefon();
    return { ...taban, ...mockEkstra };
  },
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
  useUserMode: () => ({ userMode: "veterinarian", setUserMode: jest.fn() }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ logout: jest.fn() }) }));

import React from "react";
import { StyleSheet, Text } from "react-native";
import { render } from "@testing-library/react-native";
import { AppShell } from "@/components/ui/AppShell";
import { typography } from "@/theme/tokens";

const setup = () =>
  render(
    <AppShell activeRoute="dashboard" title="T" subtitle="ALT-BASLIK" onRouteChange={jest.fn()}>
      <Text>içerik</Text>
    </AppShell>
  );

/** Kabuğun ACİL DURDUR'a verdiği son props. */
const sonGes = () => mockGesProps[mockGesProps.length - 1];

beforeEach(() => {
  mockGesProps.length = 0;
  mockKlavye = { acik: false, yukseklik: 0 };
  mockKabuk = "bottom";
  mockEkstra = {};
});

describe("kabuk türü", () => {
  it("telefon (bottom): alt bar ve 'Daha Fazla' çizilir", () => {
    const u = setup();
    expect(u.getByLabelText("Daha Fazla")).toBeTruthy();
  });

  it("KRİTİK: ray (768 px tablet / dar PC penceresi) alt bar ÇİZMEZ — telefon kabuğu değildir", () => {
    mockKabuk = "rail";
    const u = setup();
    expect(u.queryByLabelText("Daha Fazla")).toBeNull();
  });

  it("KRİTİK: rayda kenar çubuğu METİNSİZ ama ekran okuyucu etiketi TAM kalır", () => {
    mockKabuk = "rail";
    const u = setup();
    expect(u.getByLabelText("Ana Ekran")).toBeTruthy(); // erişilebilirlik korunur
    expect(u.queryByText("Ana Ekran")).toBeNull(); // 72 px raya metin sığmaz
    expect(u.queryByText("Çıkış Yap")).toBeNull();
  });

  it("sidebar (geniş PC): kenar çubuğu METİNLİ, alt bar yok", () => {
    mockKabuk = "sidebar";
    const u = setup();
    expect(u.getByText("Ana Ekran")).toBeTruthy();
    expect(u.queryByLabelText("Daha Fazla")).toBeNull();
  });
});

describe("HASTA GÜVENLİĞİ — klavye açıkken ACİL DURDUR", () => {
  it("KRİTİK: klavye açılınca alt bar kalkar ama ACİL DURDUR klavyenin ÜSTÜNE taşınır", () => {
    mockKlavye = { acik: true, yukseklik: 320 };
    const u = setup();
    expect(u.queryByLabelText("Daha Fazla")).toBeNull(); // alt bar unmount
    expect(sonGes().bottomOffset).toBe(320); // düğme GİZLENMEDİ, klavyenin üstünde
  });

  it("klavye kapalıyken düğme alt barın üstünde durur (ofset > 0)", () => {
    const u = setup();
    expect(u.getByLabelText("Daha Fazla")).toBeTruthy();
    expect(sonGes().bottomOffset).toBeGreaterThan(0);
  });

  it("KRİTİK: WEB'de klavye bayrağı alt barı KALDIRMAZ (RNW klavye olayı yaymaz)", () => {
    mockKlavye = { acik: true, yukseklik: 320 };
    mockEkstra = { isNative: false, isWeb: true };
    const u = setup();
    expect(u.getByLabelText("Daha Fazla")).toBeTruthy();
  });

  it("masaüstünde alt bar yok → ofset 0", () => {
    mockKabuk = "sidebar";
    setup();
    expect(sonGes().bottomOffset).toBe(0);
  });
});

describe("kısa ekran (yatay telefon)", () => {
  it("KRİTİK: isShort → alt başlık gizlenir ve ACİL DURDUR kompakt çizilir", () => {
    mockEkstra = { isShort: true, isLandscape: true, isLandscapePhone: true };
    const u = setup();
    expect(u.queryByText("ALT-BASLIK")).toBeNull();
    expect(sonGes().compact).toBe(true);
    expect(u.getByText("T")).toBeTruthy(); // başlık kalır
  });

  it("normal yükseklikte alt başlık görünür ve düğme kompakt değildir", () => {
    const u = setup();
    expect(u.getByText("ALT-BASLIK")).toBeTruthy();
    expect(sonGes().compact).toBe(false);
  });
});

describe("alt bar etiketleri", () => {
  it("KRİTİK: görünen metin KISALIR, ekran okuyucu etiketi TAM kalır", () => {
    const u = setup();
    expect(u.getByText("Teşhis")).toBeTruthy(); // 5 slotta sığan kısa ad
    expect(u.queryByText("Akıllı Teşhis")).toBeNull();
    expect(u.getByLabelText("Akıllı Teşhis")).toBeTruthy(); // sesli okuma tam ad
  });

  it("kısa karşılığı olmayan rota tam adıyla yazılır", () => {
    const u = setup();
    expect(u.getByText("Ana Ekran")).toBeTruthy();
  });

  // [S6 adım 3] Alt bar etiketi rf(10) idi: 320 px'te (ölçek 0,85) 9 px'e düşüyor, %125 DPI'lı
  // PC ekranında ve yaşlı gözünde okunmuyordu. Taban 11 px (typography.small).
  it("KRİTİK: alt bar etiketi 11 px tabanının altına inmez", () => {
    const u = setup();
    const stil = StyleSheet.flatten(u.getByText("Teşhis").props.style) as { fontSize: number };
    expect(stil.fontSize).toBe(typography.small);
    expect(stil.fontSize).toBeGreaterThanOrEqual(11);
  });
});
