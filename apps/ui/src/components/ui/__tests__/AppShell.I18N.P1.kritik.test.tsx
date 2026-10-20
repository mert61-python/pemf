// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · KRİTİK — AppShell "cihaza bağlanılamıyor" şeridi (değerler GERÇEK DEĞİL uyarısı): TR + EN metin görünür, dokunuş
 * (rehberi açma) AYNI. Mock düzeni `AppShell.pairing.test.tsx` ile aynı.
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
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { AppShell } from "@/components/ui/AppShell";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };

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
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

describe("KRİTİK: cihaza bağlanılamıyor şeridi — iki dilde metin görünür, eylem AYNI", () => {
  it("Türkçe: göç öncesiyle aynı metin ve erişim adı; dokunuş rehberi açar", async () => {
    const u = setup();
    const serit = await waitFor(() => u.getByTestId("conn-banner"));
    expect(u.getByText("⚠ Cihaza bağlanılamıyor — gösterilen değerler GERÇEK DEĞİL. Bağlanmak için DOKUNUN.")).toBeTruthy();
    expect(serit.props.accessibilityLabel).toBe("Cihaza bağlanma seçeneklerini aç");
    fireEvent.press(serit);
    expect(u.getByText("REHBER-ACIK")).toBeTruthy();
  });

  it("İngilizce (bayrak açık): metin ve erişim adı İngilizce; dokunuş AYNI eylem (rehber açılır), dil dönünce Türkçe", async () => {
    __bayrakTestiAyarla(true);
    const u = setup();
    await waitFor(() => u.getByTestId("conn-banner"));
    await act(async () => {
      await dilSec("en", depo);
    });
    const serit = u.getByTestId("conn-banner");
    expect(u.getByText("⚠ Cannot connect to the device — the values shown are NOT REAL. TAP to connect.")).toBeTruthy();
    expect(serit.props.accessibilityLabel).toBe("Open device connection options");
    fireEvent.press(serit);
    expect(u.getByText("REHBER-ACIK")).toBeTruthy();
    await act(async () => {
      await dilSec("tr", depo);
    });
    expect(u.getByText("⚠ Cihaza bağlanılamıyor — gösterilen değerler GERÇEK DEĞİL. Bağlanmak için DOKUNUN.")).toBeTruthy();
  });
});
