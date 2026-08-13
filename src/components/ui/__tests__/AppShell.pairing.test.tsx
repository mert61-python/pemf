// Author: mertaygn, cglrgrkn
/**
 * ÇEVRİMDIŞI ŞERİDİ — "hiç eşleşmemiş" ile "bağlantı koptu" AYRI DURUMLARDIR (2026-08-13).
 *
 * SAHA BİLDİRİMİ: telefon ve cihaz aynı ağda değilken ilk açılışta bağlantı kurulamıyordu (bu
 * beklenen) ama kullanıcı NE YAPACAĞINI öğrenemiyordu. Şerit tek metindi ve dokunmak her zaman
 * `reconnect()` çağırıyordu. Oysa keşif merdiveninin uzaktan adımı KAYITLI bir `device_id`
 * ister (`discovery` adım 3); ilk açılışta o kimlik yoktur → o düğme SONSUZA KADAR başarısız
 * olacak bir işi tekrarlıyordu. Eşleştirme alanı vardı ama Ayarlar'ın içine gömülüydü.
 *
 * Kilitlenen davranış:
 *   • Kayıtlı kimlik YOK  → metin "Bağlanmak için DOKUNUN", dokunuş REHBERİ açar (reconnect ÇAĞIRMAZ).
 *   • Kayıtlı kimlik VAR  → eski davranış: dokunuş `reconnect()` (geçici kopma; kod istemek gereksiz).
 *   • Bağlantı canlıyken şerit HİÇ çıkmaz.
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
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({ GlobalEmergencyStop: () => null }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("expo-blur", () => ({ BlurView: () => null }));
jest.mock("expo-linear-gradient", () => ({ LinearGradient: () => null }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/hooks/useResponsive", () => ({
  useResponsive: () => ({ isDesktop: true, isTablet: false, isCompact: false, width: 1280 }),
}));

// Rehber gövdesi bu dosyanın konusu değil; AÇILDIĞINI görebilmek için sade bir işaret bırakır.
jest.mock("@/components/domain/DevicePairingGuide", () => {
  const React = require("react");
  const { Text } = require("react-native");
  return {
    DevicePairingGuide: ({ visible }: { visible: boolean }) =>
      visible ? React.createElement(Text, null, "REHBER-ACIK") : null,
  };
});

let mockDeviceId: string | null = null;
jest.mock("@/services/config", () => ({
  getStoredDeviceId: async () => mockDeviceId,
}));

const mockReconnect = jest.fn();
let mockQuality = "offline";
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: { coils: [], activeTreatment: { isActive: false } },
    connectionQuality: mockQuality,
    unreadCount: 0,
    reconnect: mockReconnect,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", setUserMode: jest.fn() }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ logout: jest.fn() }) }));

import React from "react";
import { Text } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { AppShell } from "@/components/ui/AppShell";

const setup = () =>
  render(
    <AppShell activeRoute="dashboard" title="T" subtitle="S" onRouteChange={jest.fn()}>
      <Text>içerik</Text>
    </AppShell>
  );

beforeEach(() => {
  jest.clearAllMocks();
  mockQuality = "offline";
  mockDeviceId = null;
});

describe("çevrimdışı şeridi", () => {
  it("KRITIK: hiç eşleşmemişken REHBER açar (boşuna yeniden denemez)", async () => {
    mockDeviceId = null;
    const u = setup();
    const serit = await waitFor(() => u.getByLabelText("Cihaza bağlanma rehberini aç"));
    fireEvent.press(serit);
    expect(u.getByText("REHBER-ACIK")).toBeTruthy();
    // ⚠️ ASIL ARIZA: eskiden burada reconnect çağrılıyordu ve HİÇBİR ZAMAN başaramazdı
    // (uzaktan adım kayıtlı device_id ister; ilk açılışta yok).
    expect(mockReconnect).not.toHaveBeenCalled();
  });

  it("hiç eşleşmemişken metin NE YAPILACAĞINI söyler", async () => {
    mockDeviceId = null;
    const u = setup();
    const serit = await waitFor(() => u.getByLabelText("Cihaza bağlanma rehberini aç"));
    expect(String(serit.props.accessibilityLabel)).toContain("rehber");
  });

  it("daha önce eşleşmişse YENİDEN DENER (kod istemez)", async () => {
    mockDeviceId = "140936350360443";
    const u = setup();
    const serit = await waitFor(() => u.getByLabelText("Bağlantıyı yeniden dene"));
    fireEvent.press(serit);
    expect(mockReconnect).toHaveBeenCalled();
    expect(u.queryByText("REHBER-ACIK")).toBeNull();
  });

  it("bağlantı canlıyken şerit HİÇ çıkmaz", async () => {
    // ⚠️ Etiketle sınamak YETMEZ: `eslesmeVar` başlangıçta `null` olduğu için etiket ilk
    // render'da diğerine düşüyor ve mutasyon turunda "şerit her zaman çizilsin" KAÇTI.
    // Şeridin VARLIĞI kararlı bir testID ile sınanır — metin/etiket değişse de geçerli kalır.
    mockQuality = "live";
    const u = setup();
    await waitFor(() => expect(u.queryByTestId("conn-banner")).toBeNull());
    // Durum çözüldükten sonra da çıkmamalı (geç gelen state güncellemesi şeridi doğurmasın).
    await waitFor(() => expect(u.queryByTestId("conn-banner")).toBeNull());
  });

  it("çevrimdışıyken şerit ÇIKAR (ters yön)", async () => {
    mockQuality = "offline";
    const u = setup();
    expect(await waitFor(() => u.getByTestId("conn-banner"))).toBeTruthy();
  });
});
