// Author: mertaygn, cglrgrkn
/**
 * AppShell — "Çıkış Yap" navigasyon ögesi (2026-08-06 sahip isteği: Ayarlar'dan SONRA, ÜÇ profilde de).
 *
 * Bu test GERÇEK `useTeardownGuard`'ı kullanır (mock'lanmaz): asıl kilitlenen davranış hasta
 * güvenliğidir — bobinler çalışırken çıkış, durdurma TEYİT EDİLMEDEN yapılmamalı, iptal edilirse
 * oturum kapanmamalı. Çıkışın rota DEĞİL aksiyon olduğu da burada doğrulanır (kaydırarak kazara
 * oturum kapatma riskini kapatan tasarım kararı).
 */
jest.mock("@/services/apiClient", () => ({
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  // AppShell 2026-08-09'da RecoveryCodeBanner'ı da çiziyor (kurtarma kodu uyarısı); o bileşen
  // durumu apiGet ile okur. `null` → bant hiç çizilmez, bu dosyanın konusu (çıkış akışı) etkilenmez.
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

let mockDesktop = true;
jest.mock("@/hooks/useResponsive", () => ({
  useResponsive: () => ({ isDesktop: mockDesktop, isTablet: false, isCompact: !mockDesktop, width: mockDesktop ? 1280 : 390 }),
}));

let mockSnap: any;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnap, connectionQuality: "live", unreadCount: 0, reconnect: jest.fn() }),
}));

let mockMode: string;
const mockLogout = jest.fn();
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockMode, setUserMode: jest.fn() }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ logout: mockLogout }) }));

import React from "react";
import { Text } from "react-native";
import { render, fireEvent, waitFor, act } from "@testing-library/react-native";
import { platformConfirm } from "@/services/apiClient";
import { performEmergencyStop } from "@/services/emergencyStop";
import { AppShell } from "@/components/ui/AppShell";

const mockConfirm = platformConfirm as jest.Mock;
const mockStop = performEmergencyStop as jest.Mock;
const mockRouteChange = jest.fn();

const coils = (runningIds: number[]) =>
  Array.from({ length: 8 }, (_, i) => ({ id: i + 1, running: runningIds.includes(i + 1) }));

const setup = () =>
  render(
    <AppShell activeRoute="dashboard" title="T" subtitle="S" onRouteChange={mockRouteChange}>
      <Text>içerik</Text>
    </AppShell>
  );

beforeEach(() => {
  jest.clearAllMocks();
  mockDesktop = true;
  mockMode = "veterinarian";
  mockSnap = { coils: coils([]), activeTreatment: { isActive: false } };
  mockConfirm.mockResolvedValue(true);
  mockStop.mockResolvedValue({ confirmed: true });
});

/** Kenar çubuğundaki Çıkış düğmesine bas (masaüstü yerleşimi). */
const cikisaBas = async (utils: ReturnType<typeof setup>) => {
  await act(async () => { fireEvent.press(utils.getByLabelText("Çıkış Yap")); });
};

describe("üç profilde de Çıkış Yap ögesi var", () => {
  it("masaüstü kenar çubuğunda Ayarlar'dan SONRA Çıkış Yap gelir (her profil)", () => {
    for (const mode of ["pet_owner", "veterinarian", "researcher"]) {
      mockMode = mode;
      const utils = setup();
      expect(utils.getByLabelText("Çıkış Yap")).toBeTruthy();
      // Sıra: Ayarlar → Çıkış Yap (yalnız bu ikisinin göreli konumu kilitleniyor).
      const etiketler = utils.getAllByRole("button").map((n) => n.props.accessibilityLabel);
      expect(etiketler.indexOf("Çıkış Yap")).toBeGreaterThan(etiketler.indexOf("Ayarlar"));
      utils.unmount();
    }
  });

  it("mobilde 'Daha Fazla' HER profilde açılır ve içinde Çıkış Yap bulunur (4 rotalı pet_owner dahil)", async () => {
    mockDesktop = false;
    for (const mode of ["pet_owner", "veterinarian", "researcher"]) {
      mockMode = mode;
      const utils = setup();
      await act(async () => { fireEvent.press(utils.getByLabelText("Daha Fazla")); });
      expect(utils.getByText("Çıkış Yap")).toBeTruthy();
      utils.unmount();
    }
  });

  it("Çıkış bir ROTA DEĞİL: basınca onRouteChange ÇAĞRILMAZ (kaydırma hedefi de olamaz)", async () => {
    const utils = setup();
    await cikisaBas(utils);
    expect(mockRouteChange).not.toHaveBeenCalled();
  });
});

describe("HASTA GÜVENLİĞİ — teardown guard ile birleşik", () => {
  it("KRİTİK: bobin ÇALIŞIRKEN onay REDDEDİLİRSE çıkış YAPILMAZ", async () => {
    mockSnap = { coils: coils([3, 5]), activeTreatment: { isActive: false } };
    mockConfirm.mockResolvedValue(false); // operatör "İptal"

    const utils = setup();
    await cikisaBas(utils);

    expect(mockLogout).not.toHaveBeenCalled();
    expect(mockStop).not.toHaveBeenCalled(); // donanıma dokunulmadı
    expect(String(mockConfirm.mock.calls[0][1])).toContain("2 bobin");
  });

  it("KRİTİK: durdurma TEYİT EDİLEMEZSE çıkış YAPILMAZ (E-stop ekranda kalır)", async () => {
    mockSnap = { coils: coils([1]), activeTreatment: { isActive: false } };
    mockConfirm.mockResolvedValue(true);
    mockStop.mockResolvedValue({ confirmed: false });

    const utils = setup();
    await cikisaBas(utils);

    expect(mockStop).toHaveBeenCalledTimes(1);
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it("bobin çalışırken onay + TEYİTLİ durdurma → önce durdurulur, sonra çıkılır", async () => {
    mockSnap = { coils: coils([2]), activeTreatment: { isActive: true } };
    const utils = setup();
    await cikisaBas(utils);

    expect(mockStop).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(1));
  });
});

describe("boşta kazara dokunuş koruması", () => {
  it("donanım BOŞTAYKEN de onay istenir; İPTAL edilirse çıkış YAPILMAZ", async () => {
    mockConfirm.mockResolvedValue(false);
    const utils = setup();
    await cikisaBas(utils);

    expect(mockConfirm).toHaveBeenCalledTimes(1);
    expect(String(mockConfirm.mock.calls[0][0])).toMatch(/Çıkış/i);
    expect(mockStop).not.toHaveBeenCalled(); // boşta donanıma dokunulmaz
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it("boşta onay verilirse çıkış yapılır", async () => {
    const utils = setup();
    await cikisaBas(utils);
    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(1));
    expect(mockStop).not.toHaveBeenCalled();
  });
});
