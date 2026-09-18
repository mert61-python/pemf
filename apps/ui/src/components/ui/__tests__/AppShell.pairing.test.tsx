// Author: mertaygn, cglrgrkn
/**
 * ÇEVRİMDIŞI ŞERİDİ — her zaman EYLEMLİ bir kapı açar (2026-08-13).
 *
 * SAHA BİLDİRİMİ: telefon ve cihaz aynı ağda değilken ilk açılışta bağlantı kurulamıyordu (bu
 * beklenen) ama kullanıcı NE YAPACAĞINI öğrenemiyordu. Şerit tek metindi ve dokunmak her zaman
 * `reconnect()` çağırıyordu. Oysa keşif merdiveninin uzaktan adımı KAYITLI bir `device_id`
 * ister (`discovery` adım 3); ilk açılışta o kimlik yoktur → o düğme SONSUZA KADAR başarısız
 * olacak bir işi tekrarlıyordu. Eşleştirme alanı vardı ama Ayarlar'ın içine gömülüydü.
 *
 * ⚠️ İLK TASARIM YANLIŞTI (aynı gün, ikinci saha bildirimi): şerit "daha önce eşleşilmiş mi"
 * diye `getStoredDeviceId()`e bakıyor, yalnız kimlik YOKSA rehberi açıyordu. Ama `checkHealth`
 * HER başarılı bağlantıda kimliği saklar (`discovery.ts:100`) — aynı ağda bir kez bağlanmış
 * HERKESTE kimlik vardır. Sonuç: güncel APK'da bile rehber hiç açılmadı; kullanıcı eski
 * "yeniden bağlan" metnini görmeye devam etti (ekran görüntüsüyle bildirildi).
 *
 * Kilitlenen davranış — TAHMİN YOK:
 *   • Çevrimdışıyken dokunuş HER ZAMAN rehberi açar (kayıtlı kimlik olsun ya da olmasın).
 *   • Rehber iki yolu da sunar: "Yeniden Dene" (aynı ağ) + kod girişi (farklı ağ).
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
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  useResponsive: () => require("@/hooks/__tests__/responsiveMock").sahteMasaustu(),
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
  it("KRITIK: kayıtlı kimlik YOKKEN rehberi açar", async () => {
    mockDeviceId = null;
    const u = setup();
    fireEvent.press(await waitFor(() => u.getByTestId("conn-banner")));
    expect(u.getByText("REHBER-ACIK")).toBeTruthy();
  });

  it("KRITIK: kayıtlı kimlik VARKEN DE rehberi açar (asıl regresyon)", async () => {
    // ⚠️ Eski tasarımda burada `reconnect()` çağrılıyor ve rehber HİÇ açılmıyordu. Aynı ağda
    // bir kez bağlanmış her kullanıcıda kimlik olduğu için sahada rehber görünmedi.
    mockDeviceId = "140936350360443";
    const u = setup();
    fireEvent.press(await waitFor(() => u.getByTestId("conn-banner")));
    expect(u.getByText("REHBER-ACIK")).toBeTruthy();
  });

  it("şerit metni NE YAPILACAĞINI söyler", async () => {
    const u = setup();
    const serit = await waitFor(() => u.getByTestId("conn-banner"));
    expect(String(serit.props.accessibilityLabel)).toContain("bağlanma seçenekleri");
  });

  it("bağlantı canlıyken şerit HİÇ çıkmaz", async () => {
    mockQuality = "live";
    const u = setup();
    await waitFor(() => expect(u.queryByTestId("conn-banner")).toBeNull());
    await waitFor(() => expect(u.queryByTestId("conn-banner")).toBeNull());
  });

  it("çevrimdışıyken şerit ÇIKAR (ters yön)", async () => {
    mockQuality = "offline";
    const u = setup();
    expect(await waitFor(() => u.getByTestId("conn-banner"))).toBeTruthy();
  });
});
