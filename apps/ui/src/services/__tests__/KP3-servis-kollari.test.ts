/**
 * KP-3 C · küçük servis / yapılandırma modüllerinin kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - entitlement: bozuk hesap tarihi → deneme ŞİMDİDEN başlar (toISOString çökmez); deneme bitişi yok / bozuk → 0 gün ("NaN gün" yok);
 *    süresi dolmuş hesapta profil kullanılamaz; sert-kilit KAPALIYKEN (ENTITLEMENT_ENFORCED=false) kapılar HER ZAMAN izinli.
 *  - i18n: başlatma hatası yoksa tanı işlevi null döner; kritik metin dil okunamazsa TÜRKÇE yedeğe düşer.
 *  - apiClient: native onay iletişimi (İptal → false, onay → true); güvenli taban: boş / şemasız → false, ortamla eklenen güvenilir
 *    tünel ana makinesi → true; şifresiz public adrese GET / DELETE GİTMEZ (hata balonu + yedek değer); GET iki denemede de ağ hatası →
 *    yedek değer; DELETE sunucu hatası → hata balonu + yedek değer.
 *  - config: cihaz kimliği okunamazsa null; web'de jeton AsyncStorage'a yazılır / boşla silinir; native'de eski düz-metin jeton
 *    SecureStore'a TAŞINIR ve düz kopya silinir; depo erişilemezse oturum-ömürlü istemci kimliği üretilir.
 *  - deviceRegistry: boş kod / kimlik ağa gitmeden "yok".  - duzHttpKapisi: şemasız adres şifresiz izinli SAYILMAZ.
 * SAHTE (en alt kat): fetch, Alert.alert, toast köprüsü, AsyncStorage hata enjeksiyonu; Platform.OS testte ayarlanıp geri alınır.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import i18n from "i18next";
import { Alert, Platform } from "react-native";

import * as ent from "@/config/entitlement";
import { baslatmaHatasi } from "@/i18n";
import { KRITIK_YEDEK, kritikMetin } from "@/i18n/kritik";
import * as api from "@/services/apiClient";
import * as config from "@/services/config";
import { uzakCihaziKimlikleCoz, uzakCihaziKodlaCoz } from "@/services/deviceRegistry";
import { isCleartextAllowed } from "@/services/duzHttpKapisi";
import * as toastBridge from "@/services/toastBridge";

const ilkPlatform = Platform.OS;
const ilkTaban = config.serviceConfig.apiBaseUrl;
const ilkFetch = global.fetch;

beforeEach(async () => {
  await AsyncStorage.clear();
  config.serviceConfig.apiToken = "";
});
afterEach(() => {
  (Platform as { OS: string }).OS = ilkPlatform;
  config.serviceConfig.apiBaseUrl = ilkTaban;
  global.fetch = ilkFetch;
  jest.restoreAllMocks();
  delete process.env.EXPO_PUBLIC_PEMF_TRUSTED_HOSTS;
});

describe("entitlement", () => {
  it("bozuk hesap tarihi → deneme şimdiden; bitişsiz / bozuk bitiş → 0 gün; süresi dolmuşta profil yok; kilit kapalıyken kapı açık", () => {
    const once = Date.now();
    const e = ent.defaultEntitlement("bozuk-tarih");
    const bitis = new Date(e.trialEndsAt as string).getTime();
    expect(bitis - once).toBeGreaterThanOrEqual(14 * 864e5); // deneme ŞİMDİDEN (bozuk tarih yok sayıldı)
    expect(bitis - Date.now()).toBeLessThanOrEqual(14 * 864e5);
    const simdi = new Date(bitis - 14 * 864e5);
    expect(Number.isNaN(new Date(e.trialEndsAt as string).getTime())).toBe(false);
    expect(ent.trialDaysLeft(e, simdi)).toBe(14);
    expect(ent.trialDaysLeft({ ...e, trialEndsAt: null }, simdi)).toBe(0);
    expect(ent.trialDaysLeft({ ...e, trialEndsAt: "bitis-degil" }, simdi)).toBe(0);
    const dolmus = ent.defaultEntitlement("2000-01-01T00:00:00Z");
    expect(ent.canUseProfile(dolmus, "veterinarian", simdi)).toBe(false);
    expect(ent.ENTITLEMENT_ENFORCED).toBe(false);
    expect(ent.gateProfile(dolmus, "researcher", simdi)).toBe(true);
    expect(ent.gateFeature(dolmus, "realtime", simdi)).toBe(true);
    expect(ent.gateFeature(dolmus, "research", simdi)).toBe(true);
  });
});

describe("i18n", () => {
  it("başlatma hatası yoksa tanı null; dil okunamazsa kritik metin Türkçe yedekte", () => {
    expect(baslatmaHatasi()).toBeNull();
    const tanim = Object.getOwnPropertyDescriptor(i18n, "language");
    Object.defineProperty(i18n, "language", { configurable: true, get: () => { throw new Error("dil okunamadı"); } });
    try {
      jest.spyOn(i18n, "exists").mockReturnValue(false);
      expect(kritikMetin("guvenlik.acilDurdur.kartRedBaslik")).toBe(KRITIK_YEDEK.tr["guvenlik.acilDurdur.kartRedBaslik"]);
    } finally {
      if (tanim) Object.defineProperty(i18n, "language", tanim);
      else delete (i18n as { language?: string }).language;
    }
  });
});

describe("apiClient", () => {
  it("native onay: İptal → false, onay → true", async () => {
    (Platform as { OS: string }).OS = "ios";
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
    const iptal = api.platformConfirm("Sil", "Emin misiniz?", "Sil");
    (alert.mock.calls[0][2] as { onPress: () => void }[])[0].onPress();
    await expect(iptal).resolves.toBe(false);
    const onay = api.platformConfirm("Sil", "Emin misiniz?", "Sil");
    (alert.mock.calls[1][2] as { onPress: () => void }[])[1].onPress();
    await expect(onay).resolves.toBe(true);
    expect(alert.mock.calls[1][0]).toBe("Sil");
  });

  it("güvenli taban: boş / şemasız → false; ortamla eklenen güvenilir tünel → true", () => {
    expect(api.isSafeBackendBase("")).toBe(false);
    expect(api.isSafeBackendBase("kendi-tunel.test/api")).toBe(false);
    expect(api.isSafeBackendBase("https://kendi-tunel.test/api")).toBe(false);
    process.env.EXPO_PUBLIC_PEMF_TRUSTED_HOSTS = " Baska.test , kendi-tunel.test ";
    expect(api.isSafeBackendBase("https://kendi-tunel.test/api")).toBe(true);
  });

  it("şifresiz public adrese GET / DELETE gitmez: hata balonu + yedek değer", async () => {
    const toast = jest.spyOn(toastBridge, "emitToast").mockReturnValue(true);
    global.fetch = jest.fn(() => Promise.reject(new Error("fetch çağrılmamalıydı"))) as unknown as typeof fetch;
    config.serviceConfig.apiBaseUrl = "http://8.8.8.8:8000/api";
    await expect(api.apiGet("/patients", "yedek")).resolves.toBe("yedek");
    await expect(api.apiDelete("/patients/1", "yedek-sil")).resolves.toBe("yedek-sil");
    expect(global.fetch).not.toHaveBeenCalled();
    const beklenen = `${i18n.t("ortak.hata.guvensizBaglanti")}: ${i18n.t("ortak.hata.sifresizAdres")}`;
    expect(toast.mock.calls).toEqual([[beklenen, "error"], [beklenen, "error"]]);
    await api.apiGet("/patients", "yedek", { silent: true });
    expect(toast).toHaveBeenCalledTimes(2);
  });

  it("GET iki denemede de ağ hatası → yedek; DELETE sunucu hatası → hata balonu + yedek", async () => {
    const toast = jest.spyOn(toastBridge, "emitToast").mockReturnValue(true);
    jest.spyOn(console, "error").mockImplementation(() => undefined);
    jest.spyOn(console, "warn").mockImplementation(() => undefined);
    config.serviceConfig.apiBaseUrl = "http://192.168.1.40:8000/api";
    const ag = jest.fn(() => Promise.reject(new TypeError("Network request failed")));
    global.fetch = ag as unknown as typeof fetch;
    await expect(api.apiGet("/health", { ok: false }, { silent: true, timeoutMs: 50 })).resolves.toEqual({ ok: false });
    expect(ag).toHaveBeenCalledTimes(2);
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, status: 500, json: async () => ({}) })) as unknown as typeof fetch;
    await expect(api.apiDelete("/patients/1", "yedek")).resolves.toBe("yedek");
    expect(toast).toHaveBeenLastCalledWith(`${i18n.t("ortak.hata.sunucuHatasi")}: ${i18n.t("ortak.hata.silmeHatasi")}`, "error");
  });
});

describe("config", () => {
  it("cihaz kimliği okunamazsa null", async () => {
    jest.spyOn(AsyncStorage, "getItem").mockRejectedValueOnce(new Error("depo kilitli"));
    await expect(config.getStoredDeviceId()).resolves.toBeNull();
  });

  it("web: jeton AsyncStorage'a yazılır, boşla silinir", async () => {
    (Platform as { OS: string }).OS = "web";
    await config.setStoredApiToken("web-jeton");
    expect(await AsyncStorage.getItem("@pemf_api_token")).toBe("web-jeton");
    await config.setStoredApiToken("");
    expect(await AsyncStorage.getItem("@pemf_api_token")).toBeNull();
  });

  it("native: eski düz-metin jeton SecureStore'a taşınır, düz kopya silinir", async () => {
    (Platform as { OS: string }).OS = "android";
    await AsyncStorage.setItem("@pemf_api_token", "eski-jeton");
    await config.loadStoredApiToken();
    expect(config.serviceConfig.apiToken).toBe("eski-jeton");
    expect(await AsyncStorage.getItem("secure:pemf_api_token")).toBe("eski-jeton");
    expect(await AsyncStorage.getItem("@pemf_api_token")).toBeNull();
  });

  it("depo erişilemezse oturum-ömürlü istemci kimliği", async () => {
    await jest.isolateModulesAsync(async () => {
      const taze = require("@/services/config") as typeof config;
      const asMod = require("@react-native-async-storage/async-storage");
      const AS = asMod.default || asMod;
      jest.spyOn(AS, "getItem").mockRejectedValueOnce(new Error("depo yok"));
      const id = await taze.getClientInstanceId();
      expect(id).toMatch(/^c[a-z0-9]{1,8}$/);
      await expect(taze.getClientInstanceId()).resolves.toBe(id);
    });
  });
});

describe("deviceRegistry / duzHttpKapisi", () => {
  it("boş kod / kimlik ağa gitmeden 'yok'; şemasız adres şifresiz izinli değil", async () => {
    const ag = jest.fn(() => Promise.reject(new TypeError("ağ yok — gerçek Supabase'e GİDİLMEZ")));
    global.fetch = ag as unknown as typeof fetch;
    await expect(uzakCihaziKodlaCoz("   ")).resolves.toEqual({ durum: "yok" });
    await expect(uzakCihaziKimlikleCoz("")).resolves.toEqual({ durum: "yok" });
    expect(ag).not.toHaveBeenCalled();
    expect(isCleartextAllowed("192.168.1.40:8000")).toBe(false);
    expect(isCleartextAllowed("")).toBe(false);
  });
});
