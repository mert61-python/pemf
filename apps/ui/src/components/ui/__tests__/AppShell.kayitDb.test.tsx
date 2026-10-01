// Author: mertaygn, cglrgrkn
/**
 * D1.37 — kayıt DB bandı KABUKTA çizilir (1-B inceleme i2: arayüzde `dbReady`/`dbSebep` okuyan 0 satır vardı).
 * Bileşenin kendi testi davranışı ölçer; bu dosya bandın GERÇEKTEN AppShell'e takılı olduğunu ölçer (bileşen
 * var ama hiçbir ekran kullanmıyor tuzağı). Sahteler `AppShell.kabuk.test.tsx` ile aynı; yalnız sağlık ucu
 * `dbReady:false` döner. ACİL DURDUR bant varken de çizilir (Ö.4-Y8: bant hiçbir şeyi kapılamaz).
 */
let mockSaglik: Record<string, unknown> | null = null;
jest.mock("@/services/apiClient", () => ({
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  apiGet: jest.fn(async (yol: string) => (yol === "/health" ? mockSaglik : null)),
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
import { Text } from "react-native";
import { render, waitFor, act } from "@testing-library/react-native";
import { AppShell } from "@/components/ui/AppShell";

const GOC = "Hasta veritabanı göç bekliyor: at-rest şifreleme göçü tamamlanmadı (dosya kilitli olabilir).";

const setup = () =>
  render(
    <AppShell activeRoute="dashboard" title="T" subtitle="ALT" onRouteChange={jest.fn()}>
      <Text>içerik</Text>
    </AppShell>
  );

beforeEach(() => {
  mockGesProps.length = 0;
  mockSaglik = null;
});

it("KRİTİK: sağlık ucu dbReady=false derken kabuk 'göç bekliyor' bandını ÇİZER ve ACİL DURDUR yerinde kalır", async () => {
  mockSaglik = { status: "ok", dbReady: false, dbSebep: GOC };
  const u = setup();
  await waitFor(() => expect(u.getByText(/yeni seans BAŞLATILAMAZ/)).toBeTruthy());
  expect(u.getByText(/göç bekliyor/)).toBeTruthy();
  expect(mockGesProps.length).toBeGreaterThan(0);
});

it("KARŞIT: dbReady=true iken kabukta bant YOK", async () => {
  mockSaglik = { status: "ok", dbReady: true, dbSebep: null };
  const u = setup();
  await act(async () => {});
  expect(u.queryByText(/yeni seans BAŞLATILAMAZ/)).toBeNull();
});
