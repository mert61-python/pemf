/**
 * KP-3 C · src/screens/AuthScreen.tsx — giriş / kayıt / şifre sıfırlama AKIŞLARI (her test bir davranış iddiası):
 *  - Giriş: e-posta ve şifrenin kenar boşlukları atılarak gönderilir; Supabase hatası EYLEM iletisine çevrilir; yazmaya başlayınca
 *    hata silinir. Klavyenin "Git" tuşu devre dışı düğmeyi ATLAR → geçersiz e-posta / boş şifre ekranda reddedilir, istek GİTMEZ.
 *  - Çift gönderim kilidi: ilk giriş isteği sürerken düğme + klavye "Git" yeni istek AÇMAZ.
 *  - Şifre sıfırlama: "Şifremi unuttum" → sıfırlama kipi (şifre alanı yok); başarıda girişe dönülür ve yeşil bilgi KALIR; hatada ileti;
 *    "Girişe dön" giriş kipine döner.
 *  - Kayıt: şifre kuralları canlı; klavye "Bitti" (son alan) ile eksik/yanlış girişler sırayla reddedilir (kural · eşleşme · klinik
 *    bilgisi); `.edu` e-postada araştırma ipucu + yalnız ad-soyad zorunlu; geçerli kayıt profil alanlarını KIRPILMIŞ gönderir; kip
 *    değişince profil alanları temizlenir; sunucu hatası iletiye.
 *  - Şifreyi göster düğmesi alanı açık metne çevirir.
 * SAHTE (en alt kat): @supabase/supabase-js istemcisi (ağ YOK); apiClient / acil durdur servisleri ve canlı veri (mandal bandı + ACİL
 * DURDUR — bu dosyanın konusu değil, KarsilamaGiris.D187 ölçer); güvenli alan / klavye kancası.
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
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { AuthScreen } from "@/screens/AuthScreen";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const sb = (jest.requireMock("@supabase/supabase-js") as { __auth: Record<string, jest.Mock> }).__auth;

type U = ReturnType<typeof render>;
const alan = (u: U, k: string) => u.getByPlaceholderText(T(k));
async function yaz(u: U, k: string, v: string) {
  await act(async () => { fireEvent.changeText(alan(u, k), v); });
}
async function bas(u: U, metin: string, sira = 0) {
  await act(async () => { fireEvent.press(u.getAllByText(metin)[sira]); });
}
async function klavyeGit(u: U, k: string) {
  await act(async () => { fireEvent(alan(u, k), "submitEditing"); });
}
/** Gönder düğmesi (giriş kipinde sekme ile aynı metni taşır → SONUNCUSU düğmedir). */
async function gonder(u: U, metin: string) {
  const hepsi = u.getAllByText(metin);
  await act(async () => { fireEvent.press(hepsi[hepsi.length - 1]); });
}

beforeEach(() => {
  for (const f of Object.values(sb)) f.mockClear();
});

describe("giriş", () => {
  it("kenar boşlukları atılarak gönderilir; Supabase hatası eyleme çevrilir; yazınca hata silinir", async () => {
    sb.signInWithPassword.mockResolvedValueOnce({ error: { message: "Invalid login credentials" } });
    const u = render(<AuthScreen />);
    await yaz(u, "giris.alan.eposta", "  dr@klinik.com ");
    await yaz(u, "giris.alan.sifre", " Parola123  ");
    expect(alan(u, "giris.alan.sifre").props.value).toBe("Parola123"); // görünen = gönderilen
    await gonder(u, T("giris.girisYap"));
    expect(sb.signInWithPassword).toHaveBeenCalledWith({ email: "dr@klinik.com", password: "Parola123" });
    expect(u.getByText(T("giris.hata.epostaVeyaSifreHatali"))).toBeTruthy();
    await yaz(u, "giris.alan.sifre", "Parola1234");
    expect(u.queryByText(T("giris.hata.epostaVeyaSifreHatali"))).toBeNull();
  });

  it("klavye 'Git' devre dışı düğmeyi atlar: geçersiz e-posta / boş şifre ekranda reddedilir, istek GİTMEZ", async () => {
    const u = render(<AuthScreen />);
    await yaz(u, "giris.alan.eposta", "dr-klinik");
    await yaz(u, "giris.alan.sifre", "Parola123");
    await klavyeGit(u, "giris.alan.sifre");
    expect(u.getByText(T("giris.hata.gecersizEposta"))).toBeTruthy();
    await yaz(u, "giris.alan.eposta", "dr@klinik.com");
    await yaz(u, "giris.alan.sifre", "   ");
    await klavyeGit(u, "giris.alan.sifre");
    expect(u.getByText(T("giris.hata.sifreGir"))).toBeTruthy();
    expect(sb.signInWithPassword).not.toHaveBeenCalled();
  });

  it("çift gönderim kilidi: ilk istek sürerken düğme ve klavye 'Git' YENİ istek açmaz", async () => {
    let serbest: (v: unknown) => void = () => undefined;
    sb.signInWithPassword.mockImplementationOnce(() => new Promise((coz) => { serbest = coz; }));
    const u = render(<AuthScreen />);
    await yaz(u, "giris.alan.eposta", "dr@klinik.com");
    await yaz(u, "giris.alan.sifre", "Parola123");
    await klavyeGit(u, "giris.alan.sifre");
    await klavyeGit(u, "giris.alan.sifre");
    expect(sb.signInWithPassword).toHaveBeenCalledTimes(1);
    await act(async () => { serbest({ error: null }); });
    await klavyeGit(u, "giris.alan.sifre");
    expect(sb.signInWithPassword).toHaveBeenCalledTimes(2); // kilit istek bitince AÇILIR
  });

  it("şifreyi göster düğmesi alanı açık metne çevirir", async () => {
    const u = render(<AuthScreen />);
    expect(alan(u, "giris.alan.sifre").props.secureTextEntry).toBe(true);
    await act(async () => { fireEvent.press(u.getByLabelText(T("giris.alan.sifreGoster"))); });
    expect(alan(u, "giris.alan.sifre").props.secureTextEntry).toBe(false);
  });
});

describe("şifre sıfırlama", () => {
  it("sıfırlama kipi (şifre alanı yok); başarıda girişe dönülür ve bilgi KALIR; hatada ileti; 'Girişe dön'", async () => {
    const u = render(<AuthScreen />);
    await yaz(u, "giris.alan.eposta", "dr@klinik.com");
    await bas(u, T("giris.sifremiUnuttum"));
    expect(u.getByText(T("giris.sifirlama.baslik"))).toBeTruthy();
    expect(u.queryByPlaceholderText(T("giris.alan.sifre"))).toBeNull();
    sb.resetPasswordForEmail.mockResolvedValueOnce({ error: { message: "Beklenmeyen hata" } });
    await gonder(u, T("giris.sifirlama.gonder"));
    expect(u.getByText("Beklenmeyen hata")).toBeTruthy();
    expect(u.getByText(T("giris.sifirlama.baslik"))).toBeTruthy();
    await gonder(u, T("giris.sifirlama.gonder"));
    expect(sb.resetPasswordForEmail).toHaveBeenLastCalledWith("dr@klinik.com", expect.anything());
    expect(u.queryByText(T("giris.sifirlama.baslik"))).toBeNull(); // giriş kipine dönüldü
    expect(u.getByText(T("giris.sifirlama.gonderildi"))).toBeTruthy();
    await bas(u, T("giris.sifremiUnuttum"));
    await bas(u, T("giris.giriseDon"));
    expect(u.queryByText(T("giris.sifirlama.baslik"))).toBeNull();
    expect(u.getByPlaceholderText(T("giris.alan.sifre"))).toBeTruthy();
  });
});

describe("kayıt", () => {
  async function kayitKipi(u: U) {
    await bas(u, T("giris.kayitOl"));
    expect(u.getByPlaceholderText(T("giris.alan.sifreTekrar"))).toBeTruthy();
  }

  it("son alanda klavye 'Bitti': şifre kuralı → eşleşme → klinik bilgisi sırayla reddedilir; geçerli kayıt KIRPILMIŞ profille gider", async () => {
    const u = render(<AuthScreen />);
    await kayitKipi(u);
    await yaz(u, "giris.alan.ad", " Ayşe ");
    await yaz(u, "giris.alan.soyad", " Kaya ");
    await yaz(u, "giris.alan.eposta", "ayse@klinik.com");
    await yaz(u, "giris.alan.sifre", "zayif");
    await klavyeGit(u, "giris.klinik.acilTelefon");
    expect(u.getByText(T("giris.hata.sifreKurallari"))).toBeTruthy();
    await yaz(u, "giris.alan.sifre", "Parola123");
    await yaz(u, "giris.alan.sifreTekrar", "Parola124");
    await klavyeGit(u, "giris.klinik.acilTelefon");
    expect(u.getByText(T("giris.hata.sifrelerEslesmiyor"))).toBeTruthy();
    await yaz(u, "giris.alan.sifreTekrar", " Parola123 ");
    await klavyeGit(u, "giris.klinik.acilTelefon");
    expect(u.getByText(T("giris.hata.klinikBilgisiEksik"))).toBeTruthy();
    expect(sb.signUp).not.toHaveBeenCalled();
    await yaz(u, "giris.alan.unvan", " Vet. Hekim ");
    await yaz(u, "giris.alan.cepTelefonu", " 0532 ");
    await yaz(u, "giris.klinik.ad", " Pati Klinik ");
    await yaz(u, "giris.klinik.sehir", " İzmir ");
    await yaz(u, "giris.klinik.ilce", " Bornova ");
    await yaz(u, "giris.klinik.adres", " Cad. 1 ");
    await yaz(u, "giris.klinik.acilTelefon", " 0232 ");
    await klavyeGit(u, "giris.klinik.acilTelefon");
    expect(sb.signUp).toHaveBeenCalledWith({
      email: "ayse@klinik.com",
      password: "Parola123",
      options: {
        data: {
          first_name: "Ayşe", last_name: "Kaya", full_name: "Ayşe Kaya", title: "Vet. Hekim", phone: "0532",
          clinic_name: "Pati Klinik", clinic_phone: "0232", city: "İzmir", district: "Bornova", address: "Cad. 1",
        },
      },
    });
    expect(u.queryByText(T("giris.hata.klinikBilgisiEksik"))).toBeNull();
  });

  it(".edu e-posta: araştırma ipucu + klinik isteğe bağlı, yalnız ad-soyad zorunlu; sunucu hatası iletiye", async () => {
    sb.signUp.mockResolvedValueOnce({ data: { session: null }, error: { message: "User already registered" } });
    const u = render(<AuthScreen />);
    await kayitKipi(u);
    await yaz(u, "giris.alan.eposta", "ogr@uni.edu.tr");
    expect(u.getByText(T("giris.arastirmaIpucu"))).toBeTruthy();
    expect(u.getByText(T("giris.klinik.kurumBaslik"))).toBeTruthy();
    await yaz(u, "giris.alan.sifre", "Parola123");
    await yaz(u, "giris.alan.sifreTekrar", "Parola123");
    await klavyeGit(u, "giris.klinik.acilTelefon");
    expect(u.getByText(T("giris.hata.adSoyadEksik"))).toBeTruthy();
    await yaz(u, "giris.alan.ad", "Can");
    expect(u.queryByText(T("giris.hata.adSoyadEksik"))).toBeNull(); // yazınca hata silinir
    await yaz(u, "giris.alan.soyad", "Ak");
    await klavyeGit(u, "giris.klinik.acilTelefon");
    expect(sb.signUp).toHaveBeenCalledTimes(1);
    expect(u.getByText(T("giris.hata.kayitTamamlanamadi"))).toBeTruthy();
  });

  it("kip değişince profil alanları ve hata temizlenir; kural göstergesi canlı", async () => {
    const u = render(<AuthScreen />);
    await kayitKipi(u);
    await yaz(u, "giris.alan.ad", "Ayşe");
    await yaz(u, "giris.klinik.ad", "Pati");
    await yaz(u, "giris.alan.eposta", "ayse@klinik.com");
    await klavyeGit(u, "giris.klinik.acilTelefon");
    expect(u.getByText(T("giris.hata.sifreKurallari"))).toBeTruthy();
    expect(u.getByText(T("giris.kural.enAz8"))).toBeTruthy();
    await bas(u, T("giris.girisYap")); // sekme
    expect(u.queryByText(T("giris.hata.sifreKurallari"))).toBeNull();
    await bas(u, T("giris.gecis.kayitOl")); // alt geçiş bağlantısı
    expect(alan(u, "giris.alan.ad").props.value).toBe("");
    expect(alan(u, "giris.klinik.ad").props.value).toBe("");
    expect(alan(u, "giris.alan.eposta").props.value).toBe("ayse@klinik.com"); // e-posta korunur
    await bas(u, T("giris.gecis.girisYap"));
    expect(u.queryByPlaceholderText(T("giris.alan.sifreTekrar"))).toBeNull();
  });
});
