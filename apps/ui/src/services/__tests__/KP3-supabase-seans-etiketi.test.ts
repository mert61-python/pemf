/**
 * KP-3 C · services/supabaseAuth + utils/seansDegerEtiketi kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - Şifre sıfırlama: e-posta KIRPILARAK ve sıfırlama sayfası yönlendirmesiyle istenir; hata iletileri eyleme çevrilir (çok deneme / sunucu
 *    yanıt vermiyor), tanınmayan ileti AYNEN, boş ileti "işlem başarısız".
 *  - Giriş / kayıt / profil güncelleme istisna fırlatırsa (ağ) çevrilmiş ileti döner, istisna sızmaz. Oturum okunamazsa null.
 *  - Native oturum deposu: eski DÜZ-METİN oturum SecureStore'a taşınır ve düz kopya silinir; güvenli depo okunamazsa null; web'de silme
 *    AsyncStorage'dan yapılır.
 *  - Seans etiketi: AI Pro organ hedefleri katalogdan çevrilir (her organ), tanınmayan model / tedavi hedefi AYNEN; numaralı hedef çevrilir.
 * SAHTE (en alt kat): @supabase/supabase-js istemcisi (ağ YOK); AsyncStorage / SecureStore jest.setup bellek sahteleri.
 */
jest.mock("@supabase/supabase-js", () => {
  const auth = {
    signInWithPassword: jest.fn(async () => ({ error: null })),
    signUp: jest.fn(async () => ({ data: { session: null }, error: null })),
    resetPasswordForEmail: jest.fn(async () => ({ error: null })),
    updateUser: jest.fn(async () => ({ error: null })),
    getSession: jest.fn(async () => ({ data: { session: null } })),
    resend: jest.fn(async () => ({ error: null })),
  };
  return { createClient: () => ({ auth }), __auth: auth };
});

import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import i18n from "i18next";
import { Platform } from "react-native";

import * as sa from "@/services/supabaseAuth";
import { hedefEtiketi, modEtiketi } from "@/utils/seansDegerEtiketi";

const mockAuth = (jest.requireMock("@supabase/supabase-js") as { __auth: Record<string, jest.Mock> }).__auth;
const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const t = i18n.t.bind(i18n) as unknown as Parameters<typeof modEtiketi>[0];
const ilkPlatform = Platform.OS;

beforeEach(async () => {
  await AsyncStorage.clear();
});
afterEach(() => {
  (Platform as { OS: string }).OS = ilkPlatform;
  jest.restoreAllMocks();
});

describe("supabaseAuth", () => {
  it("şifre sıfırlama: kırpılmış e-posta + yönlendirme; hata iletileri eyleme çevrilir", async () => {
    await expect(sa.sendPasswordReset("  vet@klinik.test ")).resolves.toEqual({ ok: true });
    expect(mockAuth.resetPasswordForEmail).toHaveBeenLastCalledWith("vet@klinik.test", { redirectTo: sa.AUTH_RESET_URL });
    mockAuth.resetPasswordForEmail.mockResolvedValueOnce({ error: { message: "For security purposes, you can only request this after 29 seconds" } });
    await expect(sa.sendPasswordReset("vet@klinik.test")).resolves.toEqual({ ok: false, error: T("giris.hata.cokFazlaDeneme") });
    mockAuth.resetPasswordForEmail.mockRejectedValueOnce(new Error("502 Bad Gateway"));
    await expect(sa.sendPasswordReset("vet@klinik.test")).resolves.toEqual({ ok: false, error: T("giris.hata.sunucuYanitVermiyor") });
    mockAuth.resetPasswordForEmail.mockResolvedValueOnce({ error: { message: "Beklenmeyen GoTrue iletisi" } });
    await expect(sa.sendPasswordReset("vet@klinik.test")).resolves.toEqual({ ok: false, error: "Beklenmeyen GoTrue iletisi" });
    mockAuth.resetPasswordForEmail.mockResolvedValueOnce({ error: { message: "" } });
    await expect(sa.sendPasswordReset("vet@klinik.test")).resolves.toEqual({ ok: false, error: T("giris.hata.islemBasarisiz") });
  });

  it("giriş / kayıt / profil istisnası çevrilmiş iletiye; oturum okunamazsa null", async () => {
    mockAuth.signInWithPassword.mockRejectedValueOnce(new TypeError("Network request failed"));
    await expect(sa.signInUser("vet@klinik.test", "Parola123")).resolves.toEqual({ ok: false, error: T("giris.hata.sunucuyaUlasilamadi") });
    mockAuth.signUp.mockRejectedValueOnce(new Error("request timed out"));
    const kayit = await sa.signUpUser("vet@klinik.test", "Parola123");
    expect(kayit).toEqual({ ok: false, error: T("giris.hata.sunucuYanitVermiyor") });
    mockAuth.updateUser.mockRejectedValueOnce(new Error("Failed to fetch"));
    await expect(sa.updateProfile({ clinic_phone: "0232" })).resolves.toEqual({ ok: false, error: T("giris.hata.sunucuyaUlasilamadi") });
    const oturum = { access_token: "a", user: { email: "vet@klinik.test" } };
    mockAuth.getSession.mockResolvedValueOnce({ data: { session: oturum } });
    await expect(sa.getCurrentSession()).resolves.toBe(oturum);
    mockAuth.getSession.mockRejectedValueOnce(new Error("depo bozuk"));
    await expect(sa.getCurrentSession()).resolves.toBeNull();
  });

  it("native depo: eski düz-metin oturum taşınır; güvenli depo okunamazsa null; web'de silme AsyncStorage'dan", async () => {
    (Platform as { OS: string }).OS = "android";
    await AsyncStorage.setItem("sb-test-auth-token", "eski-oturum");
    await expect(sa.oturumDeposu.getItem("sb-test-auth-token")).resolves.toBe("eski-oturum");
    expect(await AsyncStorage.getItem("secure:sb-test-auth-token")).toBe("eski-oturum");
    expect(await AsyncStorage.getItem("sb-test-auth-token")).toBeNull();
    jest.spyOn(SecureStore, "getItemAsync").mockRejectedValueOnce(new Error("Keystore kilitli"));
    await expect(sa.oturumDeposu.getItem("sb-test-auth-token")).resolves.toBeNull();
    (Platform as { OS: string }).OS = "web";
    await AsyncStorage.setItem("sb-web", "web-oturum");
    await sa.oturumDeposu.removeItem("sb-web");
    expect(await AsyncStorage.getItem("sb-web")).toBeNull();
  });
});

describe("seansDegerEtiketi", () => {
  it("AI Pro organ hedefleri katalogdan; tanınmayan model / hedef aynen; numaralı hedef çevrilir", () => {
    const organlar: [string, string][] = [
      ["Mide", "ai.organ.ad.mide"],
      ["Böbrek", "ai.organ.ad.bobrek"],
      ["Karaciğer", "ai.organ.ad.karaciger"],
      ["Mesane", "ai.organ.ad.mesane"],
      ["Pankreas", "ai.organ.ad.pankreas"],
      ["Bağırsak", "ai.organ.ad.bagirsak"],
      ["Kalp", "ai.organ.ad.kalp"],
      ["Dalak", "ai.organ.ad.dalak"],
      ["Akciğer (sağ)", "ai.organ.ad.akciger_sag"],
    ];
    for (const [organ, anahtar] of organlar) {
      expect(modEtiketi(t, `AI Pro · Kedi Organ · ${organ}`)).toBe(`AI Pro · ${T("ai.modul.kediOrgan.ad")} · ${T(anahtar)}`);
    }
    expect(modEtiketi(t, "AI Pro · Yeni Model · Mide")).toBe(`AI Pro · Yeni Model · ${T("ai.organ.ad.mide")}`);
    expect(modEtiketi(t, "AI Pro · Fantom Tümör · Tümör 2")).toBe(
      `AI Pro · ${T("ai.modul.fantomTumor.ad")} · ${T("ai.pro.profil.fantom.hedefEtiketi")} 2`,
    );
    expect(modEtiketi(t, "AI Pro · Petri Kuyu · Bilinmeyen 4")).toBe(`AI Pro · ${T("ai.modul.petriKuyu.ad")} · Bilinmeyen 4`);
    expect(hedefEtiketi(t, "Serbest hedef")).toBe("Serbest hedef");
  });
});
