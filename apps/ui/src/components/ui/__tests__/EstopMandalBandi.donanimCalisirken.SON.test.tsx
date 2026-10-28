// Author: mertaygn, cglrgrkn
/**
 * SON-A1.1 (22-SON A1a · C60 / D5.08 kapı gücü) — ACİL DURDUR mandal bandı DONANIM ÇALIŞIRKEN de çizilir (Ö.4-Y8: güvenlik bandı susmaz).
 * ======================================================================================================================
 * ÖLÇÜLEN KÖRLÜK (uç 8b002fc0): D5.08 kapısı (`tests/test_kabuk_bantlari_TEK_OLCU_D5_08.py`) mandal bandının gizlenmediğini YALNIZ bileşen
 * dosyasında `useDonanimCalisiyor(` DİZESİNİN yokluğuyla ölçüyordu. İki mutant 1 pytest + 12 ilgili jest dosyasında YEŞİL kaldı:
 *   (a) bant ölçüyü TAKMA ADLA alır (`import { useDonanimCalisiyor as donanimOlcusu }` → `if (!mandal?.aktif || donanimOlcusu()) return null`);
 *   (b) kabuk bandı ölçüyle KOŞULLU çizer (`{!donanimCalisiyor && <EstopMandalBandi />}` — kapı yalnız bant dosyalarını tarar).
 * Hiçbir mandal bandı testi donanım ÇALIŞIRKEN (seans aktif ya da seanssız sürülen bobin) bandı çizmiyordu.
 *
 * GERÇEK: `AppShell`, `EstopMandalBandi`, `useDonanimCalisiyor`. Sahte EN ALT katta: canlı veri anlık görüntüsü (bağlam) + ağ / ilgisiz
 * ağır bileşenler. Yalnız KAPI: ürün koduna dokunmaz.
 */
jest.mock("@/services/apiClient", () => ({
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true, kartReddetti: false })),
}));
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({ GlobalEmergencyStop: () => null }));
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
let mockSnap: Record<string, unknown> = {};
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

import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";
import { AppShell } from "@/components/ui/AppShell";
import { EstopMandalBandi } from "@/components/ui/EstopMandalBandi";
import { useDonanimCalisiyor } from "@/hooks/useDonanimCalisiyor";

type Durum = "bosta" | "seans_aktif" | "seanssiz_bobin_calisiyor";
const DURUMLAR: Durum[] = ["bosta", "seans_aktif", "seanssiz_bobin_calisiyor"];
const SIFIRLA = "Acil durdurma mandalını sıfırla";

function kur(durum: Durum) {
  mockSnap = {
    coils: [1, 2, 3].map((id) => ({ id, running: durum === "seanssiz_bobin_calisiyor" && id === 1 })),
    activeTreatment: { isActive: durum === "seans_aktif" },
    estopMandali: { aktif: true, neden: "manual" },
  };
}

function OlcuSondasi() {
  return <Text testID="olcu">{useDonanimCalisiyor() ? "calisiyor" : "bosta"}</Text>;
}

describe("SON-A1.1 — ACİL DURDUR mandal bandı donanım çalışırken GİZLENMEZ (Ö.4-Y8)", () => {
  it.each(DURUMLAR)("vakum: ürünün donanım ölçüsü %s satırında beklenen değeri verir", (durum) => {
    kur(durum);
    const u = render(<OlcuSondasi />);
    expect(u.getByTestId("olcu").props.children).toBe(durum === "bosta" ? "bosta" : "calisiyor");
  });

  it.each(DURUMLAR)("KRİTİK bileşen: mandal kuruluyken (%s) bant NEDEN + 'Sıfırla' ile çizilir", (durum) => {
    kur(durum);
    const u = render(<EstopMandalBandi />);
    expect(u.queryByLabelText(SIFIRLA)).not.toBeNull();
    expect(u.queryByText(/ACİL DURDURMA MANDALLI/)).not.toBeNull();
  });

  it.each(DURUMLAR)("KRİTİK kabuk: AppShell mandal kuruluyken (%s) GERÇEK bandı çizer", async (durum) => {
    kur(durum);
    const u = render(
      <AppShell activeRoute="dashboard" title="T" subtitle="ALT" onRouteChange={jest.fn()}>
        <Text>içerik</Text>
      </AppShell>
    );
    await act(async () => {});
    expect(u.queryByLabelText(SIFIRLA)).not.toBeNull();
    expect(u.queryByText(/ACİL DURDURMA MANDALLI/)).not.toBeNull();
    u.unmount();
  });
});
