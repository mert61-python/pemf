/**
 * KP-4 B1 · src/screens/AuthScreen.tsx — KAYIT formunda klavyenin "ileri" tuşu odağı SIRADAKİ alana taşır (telefon klavyesinde formu
 * dokunmadan doldurmak; KP-3 ad → soyad ve klinik → şehir → ilçe halkalarını ölçtü, kalan halkalar burada):
 *   unvan → cep telefonu → e-posta → şifre → şifre tekrar → klinik adı · adres → acil telefon.
 * Girişte şifre alanındaki "Git" ise ODAK TAŞIMAZ (gönderir — KP-3 ölçtü); burada karşıt olarak yalnız odak taşınmadığı doğrulanır.
 * SAHTE (en alt kat): @supabase/supabase-js istemcisi; RN jest TextInput sahtesinin ortak `focus` yöntemi (hangi alana çağrıldığı
 * `mock.contexts` ile okunur); güvenli alan / klavye kancası; canlı veri.
 */
jest.mock("@supabase/supabase-js", () => {
  const auth = {
    signInWithPassword: jest.fn(async () => ({ error: null })),
    signUp: jest.fn(async () => ({ data: { session: { access_token: "a" } }, error: null })),
    resetPasswordForEmail: jest.fn(async () => ({ error: null })),
    getSession: jest.fn(async () => ({ data: { session: null } })),
    onAuthStateChange: jest.fn(() => ({ data: { subscription: { unsubscribe: jest.fn() } } })),
  };
  return { createClient: () => ({ auth }), __auth: auth };
});
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
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/hooks/useKeyboard", () => ({
  useKeyboard: () => ({ acik: false, yukseklik: 0 }),
  KAV_BEHAVIOR_PENCERE: undefined,
  KAV_BEHAVIOR_MODAL: undefined,
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: { stm: "online", coils: [{ id: 1, running: false, connected: true }], activeTreatment: { isActive: false } },
    connectionQuality: "live",
    unreadCount: 0,
    reconnect: jest.fn(),
  }),
}));

import React from "react";
import { TextInput } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { AuthScreen } from "@/screens/AuthScreen";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
type U = ReturnType<typeof render>;
const odak = (TextInput as unknown as { prototype: { focus: jest.Mock } }).prototype.focus;

/** `k` alanında klavye "ileri" → odak alan alanın yer tutucusu (odak hiç taşınmadıysa null). */
async function ileri(u: U, k: string): Promise<string | null> {
  odak.mockClear();
  await act(async () => { fireEvent(u.getByPlaceholderText(T(k)), "submitEditing"); });
  const c = odak.mock.contexts as Array<{ props?: { placeholder?: string } }>;
  return c.length ? (c[c.length - 1]?.props?.placeholder ?? null) : null;
}

it("KRİTİK: kayıt formunda 'ileri' odağı sıradaki alana taşır (unvan → telefon → e-posta → şifre → şifre tekrar → klinik adı)", async () => {
  const u = render(<AuthScreen />);
  await act(async () => { fireEvent.press(u.getAllByText(T("giris.kayitOl"))[0]); });
  expect(await ileri(u, "giris.alan.unvan")).toBe(T("giris.alan.cepTelefonu"));
  expect(await ileri(u, "giris.alan.cepTelefonu")).toBe(T("giris.alan.eposta"));
  expect(await ileri(u, "giris.alan.eposta")).toBe(T("giris.alan.sifre"));
  expect(await ileri(u, "giris.alan.sifre")).toBe(T("giris.alan.sifreTekrar"));
  expect(await ileri(u, "giris.alan.sifreTekrar")).toBe(T("giris.klinik.ad"));
  expect(await ileri(u, "giris.klinik.adres")).toBe(T("giris.klinik.acilTelefon"));
});

// KP-7 B (işlev ölçüsü): KP-6 kapanış ölçümünde bu beş halka hiçbir testte tetiklenmiyordu — ad → soyad → unvan · klinik adı →
// şehir → ilçe → adres.
it("kayıt formunda kalan halkalar: ad → soyad → unvan · klinik adı → şehir → ilçe → adres", async () => {
  const u = render(<AuthScreen />);
  await act(async () => { fireEvent.press(u.getAllByText(T("giris.kayitOl"))[0]); });
  expect(await ileri(u, "giris.alan.ad")).toBe(T("giris.alan.soyad"));
  expect(await ileri(u, "giris.alan.soyad")).toBe(T("giris.alan.unvan"));
  expect(await ileri(u, "giris.klinik.ad")).toBe(T("giris.klinik.sehir"));
  expect(await ileri(u, "giris.klinik.sehir")).toBe(T("giris.klinik.ilce"));
  expect(await ileri(u, "giris.klinik.ilce")).toBe(T("giris.klinik.adres"));
});

it("KARŞIT: girişte şifre alanındaki 'Git' odak TAŞIMAZ (gönderim yolu); e-posta 'ileri' şifreye taşır", async () => {
  const u = render(<AuthScreen />);
  expect(await ileri(u, "giris.alan.eposta")).toBe(T("giris.alan.sifre"));
  expect(await ileri(u, "giris.alan.sifre")).toBeNull();
});
