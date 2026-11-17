/**
 * KP-3 C · dil (i18n/dil), mobil güncelleme denetimi (services/updates), AI ayrıntı biçimleyicisi (utils/aiDetail) kapsanmayan kolları — her
 * test bir DAVRANIŞ iddiası:
 *  - cihazYereli: Intl → navigator → yerel modül sırası; hepsi okunamazsa null (dil seçimi tr'ye düşer). jest.setup bu işlevi SAHTELER →
 *    burada GERÇEĞİ (`requireActual`) ölçülür.
 *  - kayitliDilEszamanli (web): localStorage'daki geçerli seçim döner; localStorage erişimi patlarsa null. bicimYereli: en → en-GB, tr → tr-TR.
 *  - checkMobileUpdate: Android DIŞINDA hiç sorulmaz; manifest !ok / ağ hatası → güncelleme YOK; daha eski ya da AYNI sürüm → YOK, daha yeni
 *    → VAR (sürüm demeti `v` önekini yok sayar).
 *  - fmtVal: düz dizi öğeleri — null "—", mantıksal değer evet / hayır, metin değer adına çevrilir, kesirli sayı 2 basamak.
 * SAHTE (en alt kat): Intl / navigator / NativeModules / localStorage / fetch / expo-constants sürümü; Platform.OS ayarlanıp geri alınır.
 */
import i18n from "i18next";
import { NativeModules, Platform } from "react-native";

import { degerAdi, fmtVal } from "@/utils/aiDetail";

const gercekDil = jest.requireActual("@/i18n/dil") as typeof import("@/i18n/dil");
const ilkPlatform = Platform.OS;
const ilkFetch = global.fetch;

afterEach(() => {
  (Platform as { OS: string }).OS = ilkPlatform;
  global.fetch = ilkFetch;
  jest.restoreAllMocks();
});

describe("cihazYereli (gerçek)", () => {
  it("Intl → navigator → yerel modül; hiçbiri yoksa null", () => {
    expect(gercekDil.cihazYereli()).toBe(Intl.DateTimeFormat().resolvedOptions().locale);
    const intl = jest.spyOn(Intl, "DateTimeFormat").mockImplementation(() => {
      throw new Error("Intl yok");
    });
    const g = globalThis as { navigator?: { language?: string } };
    const ilkNav = Object.getOwnPropertyDescriptor(globalThis, "navigator");
    Object.defineProperty(globalThis, "navigator", { configurable: true, value: { language: "en-US" } });
    const nm = NativeModules as Record<string, unknown>;
    const ilkI18n = nm.I18nManager;
    try {
      expect(gercekDil.cihazYereli()).toBe("en-US");
      Object.defineProperty(globalThis, "navigator", { configurable: true, get: () => { throw new Error("navigator yok"); } });
      nm.I18nManager = { localeIdentifier: "tr_TR" };
      expect(gercekDil.cihazYereli()).toBe("tr_TR");
      nm.I18nManager = undefined;
      expect(gercekDil.cihazYereli()).toBeNull();
    } finally {
      nm.I18nManager = ilkI18n;
      if (ilkNav) Object.defineProperty(globalThis, "navigator", ilkNav);
      else delete g.navigator;
      intl.mockRestore();
    }
  });

  it("web kayıtlı seçim eşzamanlı; localStorage patlarsa null; biçim yereli", () => {
    (Platform as { OS: string }).OS = "web";
    const ls = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
    try {
      Object.defineProperty(globalThis, "localStorage", { configurable: true, value: { getItem: (k: string) => (k === gercekDil.DIL_DEPO_ANAHTARI ? "en" : null) } });
      expect(gercekDil.kayitliDilEszamanli()).toBe("en");
      // ⚠️ Bu ortamda globalThis üzerindeki erişimci (getter) çağrılmıyor (ölçüldü) → gerçekçi durum: getItem fırlatır (gizli kip).
      Object.defineProperty(globalThis, "localStorage", { configurable: true, value: { getItem: () => { throw new Error("SecurityError"); } } });
      expect(gercekDil.kayitliDilEszamanli()).toBeNull();
    } finally {
      if (ls) Object.defineProperty(globalThis, "localStorage", ls);
      else delete (globalThis as { localStorage?: unknown }).localStorage;
    }
    expect(gercekDil.bicimYereli("en")).toBe("en-GB");
    expect(gercekDil.bicimYereli("tr")).toBe("tr-TR");
  });
});

describe("checkMobileUpdate", () => {
  function guncelleme(surum: string): typeof import("@/services/updates") {
    let m: typeof import("@/services/updates") | undefined;
    jest.isolateModules(() => {
      jest.doMock("expo-constants", () => ({ __esModule: true, default: { expoConfig: { version: surum } } }));
      m = require("@/services/updates");
    });
    return m as typeof import("@/services/updates");
  }
  const manifest = (version: string) =>
    jest.fn(() =>
      Promise.resolve({ ok: true, json: async () => ({ version, apkUrl: "https://objects.githubusercontent.com/pemf/PEMF_Vet_Mobil.apk" }) }),
    ) as unknown as typeof fetch;

  it("Android dışında sorulmaz; !ok / ağ hatası → yok; eski / aynı → yok; yeni (v önekli) → var", async () => {
    const u = guncelleme("2.3.35");
    (Platform as { OS: string }).OS = "ios";
    global.fetch = jest.fn() as unknown as typeof fetch;
    await expect(u.checkMobileUpdate()).resolves.toEqual({ available: false });
    expect(global.fetch).not.toHaveBeenCalled();
    (Platform as { OS: string }).OS = "android";
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, json: async () => ({}) })) as unknown as typeof fetch;
    await expect(u.checkMobileUpdate()).resolves.toEqual({ available: false });
    global.fetch = jest.fn(() => Promise.reject(new TypeError("Network request failed"))) as unknown as typeof fetch;
    await expect(u.checkMobileUpdate()).resolves.toEqual({ available: false });
    global.fetch = manifest("2.2.99");
    expect((await u.checkMobileUpdate()).available).toBe(false);
    global.fetch = manifest("v2.3.35");
    expect((await u.checkMobileUpdate()).available).toBe(false);
    global.fetch = manifest("v2.3.36");
    expect((await u.checkMobileUpdate()).available).toBe(true);
  });

  // KP-7 B (işlev ölçüsü): manifest isteği ASKIDA kalırsa (yanıt yok) 8 sn sonra kesilir → güncelleme YOK (açılış beklemez).
  it("manifest isteği askıda kalırsa 8 sn sonra kesilir → güncelleme yok", async () => {
    const u = guncelleme("2.3.35");
    (Platform as { OS: string }).OS = "android";
    let sinyal: AbortSignal | undefined;
    global.fetch = jest.fn(
      (_u: string, o?: { signal?: AbortSignal }) =>
        new Promise((_coz, reddet) => {
          sinyal = o?.signal;
          o?.signal?.addEventListener("abort", () => reddet(new Error("AbortError")));
        }),
    ) as unknown as typeof fetch;
    jest.useFakeTimers();
    try {
      const p = u.checkMobileUpdate();
      await jest.advanceTimersByTimeAsync(7999);
      expect(sinyal?.aborted).toBe(false);
      await jest.advanceTimersByTimeAsync(1);
      await expect(p).resolves.toEqual({ available: false });
      expect(sinyal?.aborted).toBe(true);
    } finally {
      jest.useRealTimers();
    }
  });
});

describe("fmtVal", () => {
  it("düz dizi öğeleri: null —, mantıksal evet / hayır, metin değer adı, kesir 2 basamak", () => {
    expect(fmtVal([null, true, false, "high", 1.5, 3])).toBe(
      ["—", i18n.t("ai.ckd.secenek.evet"), i18n.t("ai.ckd.secenek.hayir"), degerAdi("high"), "1.50", "3"].join(", "),
    );
  });
});
