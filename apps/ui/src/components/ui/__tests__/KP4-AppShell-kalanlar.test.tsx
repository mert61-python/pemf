/**
 * KP-4 B1 · src/components/ui/AppShell.tsx — KP-3'ten kalan kollar (KP3-AppShell-kollari düzeneğinin aynısı; her test bir davranış):
 *  - Telefonda alt bardaki sekme o rotaya götürür.
 *  - "Daha Fazla" sayfası ve bildirim sayfası: geri tuşu (onRequestClose) ve boşluğa dokunma ikisini de KAPATIR.
 *  - Profil menüsü boşluğa dokununca kapanır.
 *  - Bağlantı yokken şerit eşleştirme rehberini açar; rehber kapatılınca kapanır.
 *  - İçerik genişliği ölçülür ve iki yan iç boşluk düşülerek ekranlara taşınır (ilk ölçümden önce `null`).
 *  - Ev Sahibi tek-kullanıcı operatör penceresindeki "E-posta hesapları" hesap menüsünü açar.
 * SAHTE: canlı veri, servisler, kabuk süsleri (KP-3 ile aynı); operatör bağlamı yalnız son testte (sağlayıcı değeri girdi).
 */
jest.mock("@/services/apiClient", () => ({
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb ?? null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/emergencyStop", () => ({ performEmergencyStop: jest.fn() }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
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
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({ GlobalEmergencyStop: () => null }));
jest.mock("@/hooks/useKeyboard", () => ({
  useKeyboard: () => ({ acik: false, yukseklik: 0 }),
  KAV_BEHAVIOR_PENCERE: undefined,
  KAV_BEHAVIOR_MODAL: undefined,
}));
jest.mock("@/hooks/useResponsive", () => ({
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  useResponsive: () => require("@/hooks/__tests__/responsiveMock").sahteTelefon(),
}));
let mockBaglanti: "live" | "offline" = "live";
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: { coils: [], activeTreatment: { isActive: false } },
    connectionQuality: mockBaglanti,
    unreadCount: 0,
    reconnect: jest.fn(),
  }),
}));
let mockKip = "veterinarian";
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: mockKip, setUserMode: jest.fn() }),
}));
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ logout: jest.fn(), session: { email: "ev@x.com" }, hesaplar: ["ev@x.com"] }),
}));
let mockOperator: Record<string, unknown> | null = null;
jest.mock("@/context/OperatorContext", () => ({
  useOperatorOptional: () => mockOperator,
  useOperator: () => mockOperator ?? { operatorEmail: "" },
}));

import React from "react";
import { Modal, ScrollView, Text } from "react-native";
import { act, fireEvent, render, type RenderResult } from "@testing-library/react-native";
import i18n from "i18next";
import { AppShell } from "@/components/ui/AppShell";
import { useShellLayout } from "@/context/ShellLayoutContext";
import { spacing } from "@/theme/tokens";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

function Olcer() {
  const w = useShellLayout();
  return <Text testID="icerik-genisligi">{String(w)}</Text>;
}

async function kur(git = jest.fn()) {
  const u = render(
    <AppShell activeRoute="dashboard" title="T" subtitle="" onRouteChange={git}>
      <Olcer />
    </AppShell>,
  );
  await act(async () => {});
  return { u, git };
}
type Dugum = ReturnType<RenderResult["UNSAFE_getAllByType"]>[number];
const acikModaller = (u: RenderResult) => u.UNSAFE_getAllByType(Modal).filter((m) => m.props.visible);
/** Modalın perdesi (en dıştaki basılabilir öğe). */
const bosluk = (m: Dugum) => m.findAll((n: Dugum) => typeof n.props?.onPress === "function")[0];
/** `metin`i içeren GÖRÜNÜR modal. */
function modalIcinde(u: RenderResult, metin: string) {
  const m = acikModaller(u).find((x) => x.findAll((n: Dugum) => n.props?.children === metin).length > 0);
  if (!m) throw new Error(`"${metin}" iceren acik modal yok`);
  return m;
}

beforeEach(() => {
  mockBaglanti = "live";
  mockKip = "veterinarian";
  mockOperator = null;
});

it("telefonda alt bar sekmesi o rotaya götürür", async () => {
  const { u, git } = await kur();
  await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.menu.kontrol"))); });
  expect(git).toHaveBeenLastCalledWith("control");
  await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.menu.akilliTeshis"))); });
  expect(git).toHaveBeenLastCalledWith("ai");
});

it("KRİTİK: 'Daha Fazla' sayfası geri tuşuyla da, boşluğa dokununca da KAPANIR (rota değişmeden)", async () => {
  const { u, git } = await kur();
  await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.menu.dahaFazlaEtiketi"))); });
  let m = modalIcinde(u, T("kabuk.menu.raporlar"));
  await act(async () => { m.props.onRequestClose(); });
  expect(u.queryByText(T("kabuk.menu.raporlar"))).toBeNull();
  await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.menu.dahaFazlaEtiketi"))); });
  m = modalIcinde(u, T("kabuk.menu.raporlar"));
  await act(async () => { fireEvent.press(bosluk(m)); });
  expect(u.queryByText(T("kabuk.menu.raporlar"))).toBeNull();
  expect(git).not.toHaveBeenCalled();
});

it("KRİTİK: bildirim sayfası geri tuşuyla da, boşluğa dokununca da KAPANIR", async () => {
  const { u } = await kur();
  const once = acikModaller(u).length;
  await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.bildirim.baslik"))); });
  expect(acikModaller(u).length).toBe(once + 1);
  const bildirim = () => { const t = u.UNSAFE_getAllByType(Modal); return t[t.length - 1]; }; // ağaçta SON modal
  await act(async () => { bildirim().props.onRequestClose(); });
  expect(acikModaller(u).length).toBe(once);
  await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.bildirim.baslik"))); });
  expect(acikModaller(u).length).toBe(once + 1);
  await act(async () => { fireEvent.press(bosluk(bildirim())); });
  expect(acikModaller(u).length).toBe(once);
});

it("profil menüsü boşluğa dokununca kapanır (profil değişmez)", async () => {
  const { u } = await kur();
  await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.profil.degistirEtiketi"))); });
  const m = modalIcinde(u, T("kabuk.profil.degistir"));
  await act(async () => { fireEvent.press(bosluk(m)); });
  expect(u.queryByText(T("kabuk.profil.degistir"))).toBeNull();
});

it("KRİTİK: bağlantı yokken şerit eşleştirme rehberini açar; rehber kapatılınca kapanır", async () => {
  mockBaglanti = "offline";
  const { u } = await kur();
  const once = acikModaller(u).length;
  await act(async () => { fireEvent.press(u.getByTestId("conn-banner")); });
  expect(acikModaller(u).length).toBe(once + 1);
  const rehber = acikModaller(u)[acikModaller(u).length - 1];
  await act(async () => { fireEvent.press(rehber.findByProps({ accessibilityLabel: T("ortak.kapat") })); });
  expect(acikModaller(u).length).toBe(once);
});

it("KRİTİK: içerik genişliği ölçülür, iki yan iç boşluk düşülerek ekrana taşınır (ölçümden önce null)", async () => {
  const { u } = await kur();
  expect(u.getByTestId("icerik-genisligi").props.children).toBe("null");
  const kaydirici = u.UNSAFE_getAllByType(ScrollView).find((s) => typeof s.props.onLayout === "function")!;
  await act(async () => { fireEvent(kaydirici, "layout", { nativeEvent: { layout: { width: 800, height: 600 } } }); });
  expect(u.getByTestId("icerik-genisligi").props.children).toBe(String(800 - 2 * spacing.xl));
  await act(async () => { fireEvent(kaydirici, "layout", { nativeEvent: { layout: { width: 10, height: 600 } } }); });
  expect(u.getByTestId("icerik-genisligi").props.children).toBe("0"); // negatif genişlik olmaz
});

it("KRİTİK: Ev Sahibi tek-kullanıcı operatör penceresindeki 'E-posta hesapları' hesap menüsünü açar", async () => {
  mockKip = "pet_owner";
  mockOperator = { operators: [], active: null, multiUser: false, lock: jest.fn(), kimlikDbOkunamiyor: false,
    refresh: jest.fn(async () => undefined), operatorEmail: "" };
  const { u } = await kur();
  expect(u.queryByTestId("hesap-menusu-aciklama")).toBeNull();
  await act(async () => { fireEvent.press(u.getByLabelText(T("hesap.operator.operatorSecEtiketi"))); });
  await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.profil.epostaHesaplari"))); });
  expect(u.getByTestId("hesap-menusu-aciklama")).toBeTruthy();
});
