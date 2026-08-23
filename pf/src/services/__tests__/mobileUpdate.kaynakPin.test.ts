// Author: mertaygn, cglrgrkn
/**
 * INDIRME KAYNAGI PINLENIR — masaustu paritesi (denetim bulgusu M1, 2026-08-23).
 *
 * OLCULEN DURUM: `guncellemeVarMi` manifest'ten gelen `url`i yalnizca VARLIK (truthy) olarak
 * denetliyordu; sema/host/repo-yolu kontrolu YOKTU ve `apkIndir` o adrese korlemesine gidiyordu.
 * Uygulamada `usesCleartextTraffic="true"` acik oldugu icin `http://` adresi GERCEKTEN inerdi.
 *
 * Masaustu ikizi bunu ACIKCA yapiyor — `launcher/core/src/net.rs::validate_download_source`:
 * repo-yolu pinli `github.com` ya da acikca sayilmis nesne-depolari; joker sonek KABUL EDILMEZ;
 * yol-kacisi (nokta-segmenti, %2e/%2f/%5c, ters-egik, bos segment) reddedilir. Ayni depoda API
 * istemcisi de kapili (`apiClient.ts::isCleartextAllowed` — "duz HTTP yalniz yerel aga").
 * Guncelleme yolu tek kapisiz kanaldi.
 *
 * ⚠️ SOZLESME: kapi FAIL-CLOSED'dur — supheli URL "guncelleme YOK" sayilir. Bu, guncellemeyi
 * kaybetmek pahasina yanlis kaynaktan 128 MB indirmemeyi secer. Kapinin BLOKLAMADIGI sey:
 * uygulamanin acilisi, baglanti ve acil durdurma (guncelleme bir kolayliktir, kapi degil).
 */
// ⚠️ Mock kümesi mobileUpdate.test.ts ile AYNI olmalı: `react-native`i olduğu gibi çekmek
// StyleSheet/DevMenu zincirini tetikliyor ve süit hiç başlamıyor; `expo-constants` varsayılan
// dışa aktarım kullandığı için hem `default` hem düz alan verilmeli.
jest.mock("react-native", () => ({ __esModule: true, Platform: { OS: "android" } }));
const mockCfg = { android: { versionCode: 13 } };
jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { get expoConfig() { return mockCfg; } },
  get expoConfig() { return mockCfg; },
}));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  createDownloadResumable: jest.fn(),
  getInfoAsync: jest.fn(),
  deleteAsync: jest.fn(),
  getContentUriAsync: jest.fn(),
}));
jest.mock("expo-sharing", () => ({ __esModule: true, isAvailableAsync: async () => true, shareAsync: jest.fn() }));
jest.mock("../../../modules/apk-installer", () => ({
  apkKur: jest.fn(),
  kurulumIzniVarMi: jest.fn(),
  izinEkraniniAc: jest.fn(),
  apkKuruculVarMi: () => true,
  // ⚠️ Yerel modul YOKMUS gibi bos dize doner (eski APK davranisi): akis SURMELI.
  // Gercek dogrulama vakalari `sha256Hesapla` enjeksiyonuyla ayri testlerde olculuyor.
  dosyaSha256: jest.fn(async () => ""),
}));

import { kaynakGuvenli, guncellemeVarMi } from "@/services/mobileUpdate";

const IYI = "https://github.com/mert61-python/pemf-update/releases/download/launcher-v1.9.32/PEMF_Vet_Mobil.apk";

describe("kaynakGuvenli — masaustu net.rs paritesi", () => {
  it("KRITIK: mesru yayin adresi KABUL edilir", () => {
    expect(kaynakGuvenli(IYI)).toBe(true);
    // GitHub'in nesne depolari (varlik yonlendirmesinin hedefi) de mesrudur:
    expect(kaynakGuvenli("https://objects.githubusercontent.com/x/y.apk")).toBe(true);
    expect(kaynakGuvenli("https://release-assets.githubusercontent.com/x/y.apk")).toBe(true);
  });

  it("KRITIK: http:// REDDEDILIR (uygulamada cleartext acik — gercekten inerdi)", () => {
    expect(kaynakGuvenli(IYI.replace("https://", "http://"))).toBe(false);
  });

  it("KRITIK: yabanci host REDDEDILIR", () => {
    expect(kaynakGuvenli("https://evil.example.com/PEMF_Vet_Mobil.apk")).toBe(false);
    expect(kaynakGuvenli("https://github.com.evil.example/x.apk")).toBe(false);
  });

  it("KRITIK: BASKA BIR REPO reddedilir (host dogru, yol yanlis)", () => {
    expect(kaynakGuvenli("https://github.com/saldirgan/pemf-update/releases/download/v1/x.apk")).toBe(false);
    expect(kaynakGuvenli("https://github.com/mert61-python/baska-depo/releases/download/v1/x.apk")).toBe(false);
  });

  it("KRITIK: yol-kacisi REDDEDILIR (nokta-segmenti / yuzde-kodlu / ters-egik)", () => {
    const kok = "https://github.com/mert61-python/pemf-update/";
    expect(kaynakGuvenli(`${kok}../../saldirgan/repo/x.apk`)).toBe(false);
    expect(kaynakGuvenli(`${kok}%2e%2e/x.apk`)).toBe(false);
    expect(kaynakGuvenli(`${kok}a%2fb/x.apk`)).toBe(false);
    expect(kaynakGuvenli(`${kok}a\\b/x.apk`)).toBe(false);
  });

  it("KARSIT-KANIT: sorgu/parca yol analizine karismaz (mesru URL elenmesin)", () => {
    expect(kaynakGuvenli(`${IYI}?token=abc`)).toBe(true);
  });

  it("bozuk girdi cokmez, false doner", () => {
    // @ts-expect-error kasitli yanlis tip
    expect(kaynakGuvenli(undefined)).toBe(false);
    expect(kaynakGuvenli("")).toBe(false);
    expect(kaynakGuvenli("bu bir url degil")).toBe(false);
  });
});

describe("guncellemeVarMi — pin manifest kapisina BAGLI", () => {
  const manifest = (url: string) =>
    jest.fn(async () => ({
      ok: true,
      json: async () => ({ mobile: { android: { version: "9.9.9", versionCode: 9999, url, sha256: "s", size: 123 } } }),
    })) as unknown as typeof fetch;

  it("KRITIK: pinsiz URL tasiyan manifest guncelleme SUNMAZ (fail-closed)", async () => {
    const r = await guncellemeVarMi(manifest("https://evil.example.com/x.apk"));
    expect(r.varMi).toBe(false);
    expect(r.sebep).toBe("eksik_alan");
  });

  it("KARSIT-KANIT: mesru URL'de guncelleme SUNULUR (kapi asiri genislemesin)", async () => {
    const r = await guncellemeVarMi(manifest(IYI));
    expect(r.varMi).toBe(true);
    expect(r.surum?.versionCode).toBe(9999);
  });
});

/**
 * INDIRMENIN HTTP DURUM KODU DENETLENIR (denetim bulgusu M2, 2026-08-23).
 *
 * OLCULEN DURUM: `apkIndir` yalnizca `sonuc?.uri`ye bakiyordu. Yerel katman durum kodunu ZATEN
 * veriyor (`putInt("status", response.code)`) ve govdeyi durumdan BAGIMSIZ olarak dosyaya yaziyor.
 * Manifest'teki varlik silinmis/yanlis etikete tasinmissa (yayinda YASANMIS bir durum) telefon
 * 404 HTML govdesini APK olarak diske yazip boyut kapisina takiliyor ve kullaniciya
 * "baglantinizi kontrol edip tekrar deneyin" diyordu — tekrar denemek ASLA ise yaramaz.
 *
 * SOZLESME: 2xx disi durum ayri bir sonuc kodudur (`sunucu`) → arayuz DOGRU seyi soyler.
 * Durum BILINMIYORSA (alan yok) eski davranis surer: boyut kapisi zaten arkada durur.
 */
describe("apkIndir — HTTP durum kodu", () => {
  const S = () =>
    ({
      version: "9.9.9", versionCode: 99, size: 1000, sha256: "a".repeat(64),
      url: "https://github.com/mert61-python/pemf-update/releases/download/t/PEMF_Vet_Mobil.apk",
    }) as never;

  // ⚠️ İLK `getInfoAsync` dönüşü {exists:false} OLMALI: `apkIndir` hedefte tam boyutlu bir dosya
  // görürse "hazır paket" hızlı yoluna girip indirmeyi HİÇ yapmaz (mobileUpdate.ts:312) — ilk
  // yazımda mock her çağrıya {exists:true,size:1000} döndüğü için testler indirmeye hiç ulaşmadan
  // yeşil/kırmızı oluyordu. Sonraki çağrı indirme SONRASI doğrulamadır.
  const bilgiSirali = (...yanitlar: unknown[]) => {
    const f = jest.fn();
    yanitlar.forEach((y) => f.mockResolvedValueOnce(y));
    f.mockResolvedValue(yanitlar[yanitlar.length - 1]);
    return f;
  };

  const kur = (status: number | undefined, diskBoyutu = 1000) => ({
    createDownloadResumable: jest.fn().mockReturnValue({
      downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-99.apk", status }),
    }) as never,
    getInfoAsync: bilgiSirali({ exists: false }, { exists: true, size: diskBoyutu }) as never,
    devamOku: jest.fn().mockResolvedValue(null) as never,
    devamYaz: jest.fn() as never,
    devamSil: jest.fn() as never,
    deleteAsync: jest.fn() as never,
  });

  it("KRITIK: 404 govdesi APK sanilmaz — ayri `sunucu` hatasi doner", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    const r = await apkIndir(S(), undefined, kur(404));
    expect(r.ok).toBe(false);
    expect(r.hata).toBe("sunucu");
  });

  it("KRITIK: 416 (devam edilemedi) da `sunucu` — kismi dosyanin SONUNA eklenmesin", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    const r = await apkIndir(S(), undefined, kur(416));
    expect(r.ok).toBe(false);
    expect(r.hata).toBe("sunucu");
  });

  it("KARSIT-KANIT: 200 ve 206 GECERLI (kapi asiri genislemesin)", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    expect((await apkIndir(S(), undefined, kur(200))).ok).toBe(true);
    expect((await apkIndir(S(), undefined, kur(206))).ok).toBe(true);
  });

  it("KARSIT-KANIT: durum BILINMIYORSA eski davranis surer (boyut kapisi arkada)", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    expect((await apkIndir(S(), undefined, kur(undefined))).ok).toBe(true);
    // Boyut tutmuyorsa yine `boyut` hatasi — durum yoklugu boyut kapisini devre disi birakmaz:
    expect((await apkIndir(S(), undefined, kur(undefined, 7))).hata).toBe("boyut");
  });
});

/**
 * ESKI APK'LAR ONBELLEKTEN TEMIZLENIR (denetim bulgusu M7, 2026-08-23).
 *
 * OLCULEN DURUM: basari yolunda yalnizca AsyncStorage izi siliniyor, indirilen ~128 MB'lik APK
 * dosyasi birakiliyordu. Eski surumun dosyasini silen tek yol (`kayit && !ayniIs`) bir sonraki
 * surumde `kayit === null` oldugu icin HIC calismiyor: kurulum basarili oldugunda uygulamanin
 * yeni versionCode'u dosyanınkine esitlenir, `guncellemeVarMi` "guncel" der ve `apkIndir` o surum
 * icin bir daha CAGRILMAZ. Sonuc: her yayinda ~128 MB birikir; depolamasi dolu bir telefonda bu,
 * bir sonraki guncellemenin INEMEMESINE kadar gider — guncelleme mekanizmasi kendini engeller.
 */
describe("apkIndir — eski paket temizligi", () => {
  const S = () =>
    ({
      version: "9.9.9", versionCode: 99, size: 1000, sha256: "a".repeat(64),
      url: "https://github.com/mert61-python/pemf-update/releases/download/t/PEMF_Vet_Mobil.apk",
    }) as never;

  const bilgiSirali = (...y: unknown[]) => {
    const f = jest.fn();
    y.forEach((x) => f.mockResolvedValueOnce(x));
    f.mockResolvedValue(y[y.length - 1]);
    return f;
  };

  const kur = (silinen: string[], dizin: string[]) => ({
    createDownloadResumable: jest.fn().mockReturnValue({
      downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-99.apk", status: 200 }),
    }) as never,
    getInfoAsync: bilgiSirali({ exists: false }, { exists: true, size: 1000 }) as never,
    devamOku: jest.fn().mockResolvedValue(null) as never,
    devamYaz: jest.fn() as never,
    devamSil: jest.fn() as never,
    deleteAsync: jest.fn(async (u: string) => { silinen.push(u); }) as never,
    readDirectoryAsync: jest.fn().mockResolvedValue(dizin) as never,
  });

  it("KRITIK: onceki surumlerin APK'lari silinir (~128 MB/yayin birikmez)", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    const silinen: string[] = [];
    await apkIndir(S(), undefined, kur(silinen, ["pemf-vet-97.apk", "pemf-vet-98.apk", "pemf-vet-99.apk"]));
    expect(silinen).toEqual(expect.arrayContaining(["file:///cache/pemf-vet-97.apk", "file:///cache/pemf-vet-98.apk"]));
  });

  it("KARSIT-KANIT: INDIRILEN dosya ve ilgisiz dosyalar SILINMEZ", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    const silinen: string[] = [];
    const r = await apkIndir(S(), undefined, kur(silinen, ["pemf-vet-99.apk", "baska-uygulama.apk", "veri.db"]));
    expect(r.ok).toBe(true);
    expect(silinen).not.toContain("file:///cache/pemf-vet-99.apk");   // ⚠️ indirilen paketin kendisi
    expect(silinen).not.toContain("file:///cache/baska-uygulama.apk"); // ⚠️ bizim olmayan dosya
    expect(silinen).not.toContain("file:///cache/veri.db");
  });

  it("KARSIT-KANIT: dizin okunamazsa indirme yine de BASARILI (temizlik kritik degil)", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    const d = kur([], []);
    (d as { readDirectoryAsync: unknown }).readDirectoryAsync = jest.fn().mockRejectedValue(new Error("izin yok"));
    expect((await apkIndir(S(), undefined, d)).ok).toBe(true);
  });
});

/**
 * SURUM ALANLARI DOGRULANIR (denetim 2026-08-23, bulgu M8).
 *
 * OLCULEN DURUM: `if (Number(a.versionCode) <= mevcutVersionCode()) return guncel;` — `versionCode`
 * truthy ama SAYISAL DEGILSE (or. "v29", "2.3.21", {}) `Number()` NaN olur ve NaN ile yapilan HER
 * karsilastirma false doner → "guncel" kontrolu ATLANIR ve `varMi: true` donulur (FAIL-OPEN).
 *
 * ⚠️ Manifest'in `mobile` blogu URETILMIYOR, onceki manifestten TASINIP ELLE duzenleniyor
 * (`make_manifest.py::CARRY_ONLY`) — yani tip hatasi gercekci bir yayin kazasidir. Sonuc: sahadaki
 * TUM telefonlar her soguk acilista "Yeni surum hazir" kapisini gorur, 128 MB indirir, Android
 * ayni/eski versionCode'u reddeder ve dongu tekrarlar. Ustelik "Simdilik devam et" ile konan
 * erteleme bayragi da tutmaz (`atlandiMi` icinde `Number(...) || 0` → hep 0) — yani bandi
 * susturmanin YOLU KALMAZ.
 *
 * SOZLESME: surum alanlari sert dogrulanir; gecersizse "guncelleme yok" (fail-closed).
 */
describe("guncellemeVarMi — surum alani dogrulamasi", () => {
  const man = (android: Record<string, unknown>) =>
    jest.fn(async () => ({ ok: true, json: async () => ({ mobile: { android } }) })) as unknown as typeof fetch;

  const TEMEL = {
    version: "9.9.9",
    url: "https://github.com/mert61-python/pemf-update/releases/download/t/PEMF_Vet_Mobil.apk",
    sha256: "a".repeat(64),
    size: 123,
  };

  it.each([["v29"], ["2.3.21"], ["29abc"], [{}], [[]], [true]])(
    "KRITIK: sayisal olmayan versionCode (%p) guncelleme SUNMAZ (NaN fail-open kapandi)",
    async (vc) => {
      const r = await guncellemeVarMi(man({ ...TEMEL, versionCode: vc }));
      expect(r.varMi).toBe(false);
      expect(r.sebep).toBe("eksik_alan");
    },
  );

  it("KRITIK: negatif/ondalikli versionCode reddedilir", async () => {
    expect((await guncellemeVarMi(man({ ...TEMEL, versionCode: -5 }))).varMi).toBe(false);
    expect((await guncellemeVarMi(man({ ...TEMEL, versionCode: 29.5 }))).varMi).toBe(false);
  });

  it("KRITIK: gecersiz size guncelleme SUNMAZ (indirme kapisi boyutla dogruluyor)", async () => {
    expect((await guncellemeVarMi(man({ ...TEMEL, versionCode: 99, size: "cok" }))).varMi).toBe(false);
  });

  it("KRITIK: version METIN degilse reddedilir (basligta bos gorunurdu)", async () => {
    expect((await guncellemeVarMi(man({ ...TEMEL, versionCode: 99, version: 9 }))).varMi).toBe(false);
  });

  it("KARSIT-KANIT: gecerli alanlarda guncelleme SUNULUR ve deger SAYIYA normalize edilir", async () => {
    const r = await guncellemeVarMi(man({ ...TEMEL, versionCode: "99" }));
    expect(r.varMi).toBe(true);
    // ⚠️ Normalize edilmis deger DONMELI: ham metin dosya adina ve erteleme anahtarina giriyor
    // (`pemf-vet-<vc>.apk`, `atlandiMi`), metin kalirsa erteleme hicbir zaman eslesmez.
    expect(r.surum?.versionCode).toBe(99);
    expect(typeof r.surum?.versionCode).toBe("number");
  });
});

/**
 * INDIRILEN APK SHA256 ILE DOGRULANIR (denetim 2026-08-23, bulgu M11).
 *
 * OLCULEN DURUM: tek butunluk kapisi BOYUT esitligiydi; `MobilSurum.sha256` kod tabaninda hicbir
 * yerde okunmuyordu. Oysa yayindaki manifest'in kendi notu "SHA256 dogrular" diye SOZ VERIYOR ve
 * yayin runbook'u o soze guveniyordu — sha yanlis yazilsa kimse fark etmezdi. Launcher paketleri
 * `verify::verify_file` ile dogrulaniyor; APK zincirdeki TEK dogrulanmayan varlikti.
 *
 * SOZLESME:
 *   · Hash TUTMUYORSA paket SILINIR ve kurulum SUNULMAZ (bozuk/karisik indirme kurulmaz).
 *   · Hash HESAPLANAMIYORSA (eski APK'da yerel modul yok → bos dize) eski davranis SURER.
 *     Dogrulanamiyor diye engellemek, sahadaki eski surumleri KALICI guncellenemez yapardi.
 *   · Manifest sha256 TASIMIYORSA da akis surer (alan opsiyonel kalir).
 */
describe("apkIndir — sha256 dogrulamasi", () => {
  const SHA_IYI = "b".repeat(64);
  const S = (sha = SHA_IYI) =>
    ({
      version: "9.9.9", versionCode: 99, size: 1000, sha256: sha,
      url: "https://github.com/mert61-python/pemf-update/releases/download/t/PEMF_Vet_Mobil.apk",
    }) as never;

  const bilgiSirali = (...y: unknown[]) => {
    const f = jest.fn();
    y.forEach((x) => f.mockResolvedValueOnce(x));
    f.mockResolvedValue(y[y.length - 1]);
    return f;
  };

  const kur = (silinen: string[]) => ({
    createDownloadResumable: jest.fn().mockReturnValue({
      downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-99.apk", status: 200 }),
    }) as never,
    getInfoAsync: bilgiSirali({ exists: false }, { exists: true, size: 1000 }) as never,
    devamOku: jest.fn().mockResolvedValue(null) as never,
    devamYaz: jest.fn() as never,
    devamSil: jest.fn() as never,
    deleteAsync: jest.fn(async (u: string) => { silinen.push(u); }) as never,
    readDirectoryAsync: jest.fn().mockResolvedValue([]) as never,
  });

  it("KRITIK: hash TUTMAZSA paket reddedilir ve SILINIR", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    const silinen: string[] = [];
    const r = await apkIndir(S(), undefined, {
      ...kur(silinen),
      sha256Hesapla: jest.fn(async () => "c".repeat(64)) as never,   // BASKA bir dosya
    });
    expect(r.ok).toBe(false);
    expect(r.hata).toBe("butunluk");
    expect(silinen).toContain("file:///cache/pemf-vet-99.apk");
  });

  it("KARSIT-KANIT: hash TUTARSA kurulum sunulur", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    const r = await apkIndir(S(), undefined, {
      ...kur([]),
      sha256Hesapla: jest.fn(async () => SHA_IYI.toUpperCase()) as never,  // buyuk/kucuk harf farketmez
    });
    expect(r.ok).toBe(true);
  });

  it("KARSIT-KANIT: hash HESAPLANAMIYORSA akis surer (eski APK'lar kilitlenmesin)", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    const r = await apkIndir(S(), undefined, {
      ...kur([]),
      sha256Hesapla: jest.fn(async () => "") as never,   // yerel modul yok
    });
    expect(r.ok).toBe(true);
  });

  it("KARSIT-KANIT: manifest sha TASIMIYORSA akis surer", async () => {
    const { apkIndir } = require("@/services/mobileUpdate");
    const r = await apkIndir(S(""), undefined, {
      ...kur([]),
      sha256Hesapla: jest.fn(async () => "d".repeat(64)) as never,
    });
    expect(r.ok).toBe(true);
  });
});
