// Author: mertaygn, cglrgrkn
/**
 * SGI-1.4 (bağımsız inceleme) — CH1'in YENİ çıkış girişi "Tüm hesaplardan çık" (E-posta hesapları penceresi) kabuğun TEARDOWN KORUMALI
 * çıkışından geçer (A-59 / Y55 / Ö.4-Y8): bobin çalışırken onay + ÖNCE durdurma; onay reddedilirse ya da durdurma teyit edilemezse çıkış YOK.
 * Ölçülen (549ce2b0): `AppShell`'de `onTumundenCik={handleLogout}` bağı herhangi bir kapıyla PİNLİ DEĞİL — korumasız `logout`a çevrilince
 * kabuk / hesap menüsü / operatör / AuthGate 12 süit 75 test YEŞİL kaldı (kayıp test: SG_G7 "MEVCUT çıkış akışını çağırır" yerine gelen
 * test yalnız geri çağrının çağrıldığını ölçer, KORUMAYI değil).
 * GERÇEK `AppShell` + GERÇEK `HesapMenusu` + GERÇEK `useTeardownGuard`; sahte olan yalnız platform onayı, ACİL DURDUR servisi, canlı veri ve
 * kimlik bağlamı (AppShell.logout.test ile aynı aparat).
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
  useResponsive: () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const m = require("@/hooks/__tests__/responsiveMock");
    return m.sahteMasaustu();
  },
}));

let mockSnap: any;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnap, connectionQuality: "live", unreadCount: 0, reconnect: jest.fn() }),
}));
const mockLogout = jest.fn(async () => undefined);
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian", setUserMode: jest.fn() }) }));
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    logout: mockLogout,
    session: { email: "a@klinik.com", token: "x" },
    hesaplar: ["a@klinik.com", "b@klinik.com"],
    hesabaGec: jest.fn(async () => ({ ok: true })),
    hesaptanCik: jest.fn(async () => ({ ok: true })),
    hesapEkle: jest.fn(async () => undefined),
  }),
}));

import React from "react";
import { Text } from "react-native";
import { render, fireEvent, waitFor, act } from "@testing-library/react-native";
import { platformConfirm } from "@/services/apiClient";
import { performEmergencyStop } from "@/services/emergencyStop";
import { AppShell } from "@/components/ui/AppShell";

const mockConfirm = platformConfirm as jest.Mock;
const mockStop = performEmergencyStop as jest.Mock;
const coils = (runningIds: number[]) => Array.from({ length: 8 }, (_, i) => ({ id: i + 1, running: runningIds.includes(i + 1) }));

const tumundenCik = async () => {
  const u = render(
    <AppShell activeRoute="dashboard" title="T" subtitle="S" onRouteChange={jest.fn()}>
      <Text>içerik</Text>
    </AppShell>,
  );
  await act(async () => { fireEvent.press(u.getByLabelText("Profil değiştir")); });
  await act(async () => { fireEvent.press(u.getByTestId("profil-menu-hesaplar")); });
  const dugmeler = u.getAllByLabelText("Tüm hesaplardan çık");
  // Profil menüsündeki satır DEĞİL, E-posta hesapları penceresindeki düğme (son çizilen Modal).
  await act(async () => { fireEvent.press(dugmeler[dugmeler.length - 1]); });
  return u;
};

beforeEach(() => {
  jest.clearAllMocks();
  mockSnap = { coils: coils([]), activeTreatment: { isActive: false } };
  mockConfirm.mockResolvedValue(true);
  mockStop.mockResolvedValue({ confirmed: true });
});

it("KRİTİK: bobin ÇALIŞIRKEN 'Tüm hesaplardan çık' onay ister; REDDEDİLİRSE çıkış YOK, donanıma dokunulmaz", async () => {
  mockSnap = { coils: coils([2, 4]), activeTreatment: { isActive: true } };
  mockConfirm.mockResolvedValue(false);
  await tumundenCik();
  await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
  expect(mockLogout).not.toHaveBeenCalled(); // kabuk (ve ACİL DURDUR) bobinler çalışırken SÖKÜLMEZ
  expect(mockStop).not.toHaveBeenCalled();
  expect(mockConfirm).toHaveBeenCalledTimes(1);
  expect(String(mockConfirm.mock.calls[0][0])).toBe("Seans sürüyor");
});

it("KRİTİK: bobin çalışırken onay + durdurma TEYİT EDİLEMEZSE çıkış YOK (ACİL DURDUR ekranda kalır)", async () => {
  mockSnap = { coils: coils([1]), activeTreatment: { isActive: false } };
  mockStop.mockResolvedValue({ confirmed: false });
  await tumundenCik();
  await waitFor(() => expect(mockStop).toHaveBeenCalledTimes(1));
  await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
  expect(mockLogout).not.toHaveBeenCalled();
});

it("KARŞIT: boşta onayla (>1 hesap: 'Tüm hesaplardan çık' metni) çıkılır; donanıma dokunulmaz", async () => {
  await tumundenCik();
  await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(1));
  expect(mockConfirm).toHaveBeenCalledTimes(1);
  expect(String(mockConfirm.mock.calls[0][0])).toBe("Tüm hesaplardan çık");
  expect(mockStop).not.toHaveBeenCalled();
});
