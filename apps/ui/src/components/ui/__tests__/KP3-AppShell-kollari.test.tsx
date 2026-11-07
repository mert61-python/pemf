/**
 * KP-3 C · AppShell kapsanmayan kolları — her test bir DAVRANIŞ iddiası (AppShell.kabuk düzeneğinin aynısı):
 *  - Telefonda yatay KAYDIRMA alt bardaki görünür sekmeler arasında gezer: sola çek → sonraki, sağa çek → önceki; ilk/son sekmede
 *    sınır aşılmaz; zayıf / dikey / diyagonal hareket yok sayılır; 500 ms içinde ikinci kaydırma TEK geçiş sayılır; etkin ekran alt
 *    barda değilse ("Daha Fazla" içinden) gezinme yok; masaüstünde kaydırma hiç sahiplenilmez; dokunma (start) sahiplenilmez ve iç
 *    kaydırıcı ortadan çalamaz.
 *  - Oto-eşleştirme işareti (`@pemf_just_paired`) varsa açılışta "otomatik eşleşti" bildirimi gösterilir ve işaret SİLİNİR.
 *  - Profil menüsü: profil seçilince kip değişir ve menü kapanır; boşluğa dokununca kapanır.
 *  - "Daha Fazla": kalan rotaya gidilir ve sayfa kapanır. Telefonda üst bardaki Ayarlar düğmesi Ayarlar'a götürür. Bildirim
 *    düğmesi bildirim sayfasını açar. Masaüstü kenar çubuğunda rota düğmesi o rotaya götürür.
 * SAHTE: PanResponder hareket durumu (platform jest sistemi — ürünün KENDİ işleyicileri doğrudan çağrılır), canlı veri, servisler,
 * kabuk süsleri; AsyncStorage jest.setup bellek sahtesi.
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
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
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
let mockKabuk: "bottom" | "sidebar" = "bottom";
jest.mock("@/hooks/useResponsive", () => ({
  useResponsive: () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const m = require("@/hooks/__tests__/responsiveMock");
    return mockKabuk === "sidebar" ? m.sahteMasaustu() : m.sahteTelefon();
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
const mockKipAyarla = jest.fn();
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", setUserMode: mockKipAyarla }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ logout: jest.fn(), session: { email: "v@x.com" } }) }));

import React from "react";
import { Modal, PanResponder, Text, type PanResponderCallbacks } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import i18n from "i18next";
import { AppShell } from "@/components/ui/AppShell";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
type Rota = Parameters<typeof AppShell>[0]["activeRoute"];

let yapilandirma: PanResponderCallbacks;
async function kur(rota: Rota, git = jest.fn()) {
  // ⚠️ Aynı testte ikinci çizimde `spyOn` AYNI casusu döndürür ve çağrılar birikir → bu bileşenin İLK create'i alınsın.
  const casus = jest.spyOn(PanResponder, "create");
  casus.mockClear();
  const u = render(
    <AppShell activeRoute={rota} title="T" subtitle="" onRouteChange={git}>
      <Text>içerik</Text>
    </AppShell>,
  );
  await act(async () => {});
  yapilandirma = casus.mock.calls[0][0];
  return { u, git };
}
const hareket = (dx: number, dy = 0, vx = 0) => ({ dx, dy, vx }) as never;
const birak = (dx: number, dy = 0, vx = 0) => yapilandirma.onPanResponderRelease!({} as never, hareket(dx, dy, vx));
const sahiplen = (dx: number, dy = 0) => yapilandirma.onMoveShouldSetPanResponder!({} as never, hareket(dx, dy));
const acikModaller = (u: ReturnType<typeof render>) => u.UNSAFE_getAllByType(Modal).filter((m) => m.props.visible).length;

let saat = 10_000;
beforeEach(async () => {
  mockKabuk = "bottom";
  mockToast.mockClear();
  mockKipAyarla.mockClear();
  await AsyncStorage.clear();
  saat = 10_000;
  jest.spyOn(Date, "now").mockImplementation(() => saat);
});
afterEach(() => jest.restoreAllMocks());

describe("kaydırarak sekme geçişi (telefon)", () => {
  it("sola çek → sonraki, sağa çek → önceki; 500 ms içinde ikinci kaydırma tek geçiş; zayıf/dikey yok sayılır", async () => {
    const { git } = await kur("dashboard"); // alt bar: ai · dashboard · control · patients
    expect(yapilandirma.onStartShouldSetPanResponder!({} as never, hareket(0))).toBe(false);
    expect(yapilandirma.onPanResponderTerminationRequest!({} as never, hareket(0))).toBe(false);
    expect(sahiplen(40, 5)).toBe(true);
    expect(sahiplen(20, 0)).toBe(false); // eşik altı
    expect(sahiplen(40, 30)).toBe(false); // diyagonal
    birak(-80);
    expect(git).toHaveBeenLastCalledWith("control");
    saat += 200;
    birak(-80);
    expect(git).toHaveBeenCalledTimes(1); // aynı kaydırma iki kez sayılmaz
    saat += 600;
    birak(40, 0, 0.5); // kısa ama hızlı (flick) → geçerli
    expect(git).toHaveBeenLastCalledWith("ai");
    saat += 600;
    birak(-50, 0, 0.1); // kısa ve yavaş → yok
    birak(-80, -70); // dikey baskın → yok
    expect(git).toHaveBeenCalledTimes(2);
  });

  it("ilk sekmede sağa çekmek sınırı aşmaz; etkin ekran alt barda değilse gezinme yok", async () => {
    let r = await kur("ai");
    birak(90);
    expect(r.git).not.toHaveBeenCalled();
    r.u.unmount();
    r = await kur("sensors"); // "Daha Fazla" içindeki rota
    birak(-90);
    expect(r.git).not.toHaveBeenCalled();
  });

  it("masaüstünde kaydırma sahiplenilmez ve bırakma gezinmez", async () => {
    mockKabuk = "sidebar";
    const { git } = await kur("dashboard");
    expect(sahiplen(80, 0)).toBe(false);
    birak(-90);
    expect(git).not.toHaveBeenCalled();
  });
});

describe("üst bar + menüler", () => {
  it("oto-eşleştirme işareti varsa 'otomatik eşleşti' bildirimi ve işaret SİLİNİR", async () => {
    await AsyncStorage.setItem("@pemf_just_paired", "DEV-1");
    await kur("dashboard");
    await act(async () => {});
    expect(mockToast).toHaveBeenCalledWith(T("kabuk.baglanti.otomatikEslesti"), "success");
    expect(await AsyncStorage.getItem("@pemf_just_paired")).toBeNull();
  });

  it("profil menüsü: seçilen profil kipi değiştirir ve menü kapanır; boşluğa dokununca kapanır", async () => {
    const { u } = await kur("dashboard");
    await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.profil.degistirEtiketi"))); });
    expect(u.getByText(T("kabuk.profil.degistir"))).toBeTruthy();
    await act(async () => { fireEvent.press(u.getByText(T("kabuk.mod.arastirma"))); });
    expect(mockKipAyarla).toHaveBeenCalledWith("researcher");
    expect(u.queryByText(T("kabuk.profil.degistir"))).toBeNull();
    await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.profil.degistirEtiketi"))); });
    const modal = u.UNSAFE_getAllByType(Modal).find((m) => m.props.visible)!;
    await act(async () => { modal.props.onRequestClose(); });
    expect(u.queryByText(T("kabuk.profil.degistir"))).toBeNull();
  });

  it("'Daha Fazla' kalan rotaya götürür ve kapanır; Ayarlar düğmesi; bildirim sayfası açılır", async () => {
    const { u, git } = await kur("dashboard");
    await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.menu.dahaFazlaEtiketi"))); });
    await act(async () => { fireEvent.press(u.getByText(T("kabuk.menu.raporlar"))); });
    expect(git).toHaveBeenLastCalledWith("kpi");
    expect(u.queryByText(T("kabuk.menu.raporlar"))).toBeNull();
    await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.menu.ayarlar"))); });
    expect(git).toHaveBeenLastCalledWith("settings");
    const once = acikModaller(u);
    await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.bildirim.baslik"))); });
    expect(acikModaller(u)).toBe(once + 1);
  });

  it("masaüstü kenar çubuğunda rota düğmesi o rotaya götürür", async () => {
    mockKabuk = "sidebar";
    const { u, git } = await kur("dashboard");
    await act(async () => { fireEvent.press(u.getByLabelText(T("kabuk.menu.hastalar"))); });
    expect(git).toHaveBeenLastCalledWith("patients");
  });
});
