// Author: mertaygn, cglrgrkn
/**
 * MOBİL OTO-GÜNCELLEME (2026-08-08) — "bir kere indirsin, hep güncel kalsın" isteğinin
 * mobil ayağı. Masaüstü zaten kendini güncelliyordu; mobilde HİÇBİR mekanizma yoktu.
 *
 * Kilitlenen davranışlar:
 *   * ağ/manifest hatası kullanıcıyı ENGELLEMEZ (internetsiz klinik normal açılır),
 *   * yalnız DAHA YENİ versionCode güncelleme sayılır (aynı/eski sürüm sessizce atlanır),
 *   * eksik alanlı manifest güncelleme TETİKLEMEZ,
 *   * yarım/bozuk inen APK SİLİNİR ve kurulum AÇILMAZ,
 *   * iOS'ta hiç denenmez.
 */
// ⚠️ 2026-08-17: kurulum artık YEREL native modülden geçiyor (paylaşım sayfası DEĞİL).
// Mock, modülün gerçekten çağrıldığını ve paylaşımın YEDEK olduğunu sınamayı sağlar.
const mockApkKur = jest.fn();
const mockIzinVarMi = jest.fn();
const mockIzinEkrani = jest.fn();
const mockServisBaslat = jest.fn(async () => true);
const mockServisDurdur = jest.fn(async () => true);
jest.mock("../../../modules/apk-installer", () => ({
  apkKur: (...a: unknown[]) => mockApkKur(...(a as [])),
  kurulumIzniVarMi: () => mockIzinVarMi(),
  izinEkraniniAc: () => mockIzinEkrani(),
  apkKuruculVarMi: () => true,
  // ⚠️ Yerel modul YOKMUS gibi bos dize doner (eski APK davranisi): akis SURMELI.
  // Gercek dogrulama vakalari `sha256Hesapla` enjeksiyonuyla ayri testlerde olculuyor.
  dosyaSha256: jest.fn(async () => ""),
  indirmeServisiniBaslat: (...a: unknown[]) => mockServisBaslat(...(a as [])),
  indirmeServisiniDurdur: () => mockServisDurdur(),
}));

// Ekran-uyanik-tut: kod `require("expo-keep-awake")` kullanir (statik import degil — gerekce
// mobileUpdate.ts::ekraniUyanikTut) → jest.mock require'i da keser, casuslar buradan olculur.
const mockUyanikTut = jest.fn(async () => {});
const mockUyanikBirak = jest.fn(async () => {});
jest.mock("expo-keep-awake", () => ({
  activateKeepAwakeAsync: (...a: unknown[]) => mockUyanikTut(...(a as [])),
  deactivateKeepAwake: (...a: unknown[]) => mockUyanikBirak(...(a as [])),
}));

const mockPaylas = jest.fn();
jest.mock("expo-sharing", () => ({
  // ⚠️ `__esModule: true` ŞART: `kurulumuBaslat` içinde DİNAMİK `await import("expo-sharing")`
  // var; bayrak olmadan namespace `{ default: {...} }` olarak sarılıyor ve alanlar undefined
  // görünüyor → yedek yol testte sessizce "hata"ya düşüyordu.
  __esModule: true,
  isAvailableAsync: async () => true,
  shareAsync: (...a: unknown[]) => mockPaylas(...(a as [])),
}));

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  createDownloadResumable: jest.fn(),
  getInfoAsync: jest.fn(),
  deleteAsync: jest.fn(),
  getContentUriAsync: jest.fn(),
}));

// ⚠️ RN'i `{...jest.requireActual("react-native")}` ile yaymayın: yayılım RN'in TEMBEL
// özelliklerini zorla değerlendirir, native modülleri (DevMenu/FlatList) çeker ve süit hiç
// başlamaz. Bu modül react-native'den YALNIZ `Platform` kullanıyor → yalnız onu sağla.
// `__esModule: true` şart: aksi halde derlenen import `Platform`u undefined görüyor.
let mockOS = "android";
// ⚠️ `AppState` burada BİLEREK bir CASUS olarak duruyor (2026-08-13). Modül onu KULLANMAMALI:
// indirme arka planda DURAKLATILMAZ (gerekçe aşağıdaki teste yazılı). Biri duraklatmayı geri
// eklerse `addEventListener` çağrılır ve o test kırmızıya döner.
const mockAppStateDinle = jest.fn(() => ({ remove: jest.fn() }));
jest.mock("react-native", () => ({
  __esModule: true,
  Platform: { get OS() { return mockOS; } },
  AppState: { addEventListener: (...a: unknown[]) => mockAppStateDinle(...(a as [])) },
}));

// `expo-constants` VARSAYILAN dışa aktarım kullanır; mock hem `default` hem düz alan olarak
// vermeli, yoksa derlenen import undefined görür. Getter → testler arası değiştirilebilir.
const mockCfg: { android: { versionCode: number } } = { android: { versionCode: 13 } };
jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { get expoConfig() { return mockCfg; } },
  get expoConfig() { return mockCfg; },
}));

import AsyncStorage from "@react-native-async-storage/async-storage";

import {
  apkIndir,
  atlandiMi,
  guncellemeVarMi,
  guncellemeyiAtla,
  mevcutVersionCode,
  _atlamayiSifirla,
  _indirmeyiSifirla,
  kurulumuBaslat,
  type MobilSurum,
} from "../mobileUpdate";

// ⚠️ URL GERÇEK YAYIN YOLUNU taşımalı (2026-08-23): `guncellemeVarMi` artık kaynağı pinliyor
// (`kaynakGuvenli` — masaüstü `net.rs` paritesi) ve uydurma bir depo yolu HAKLI OLARAK elenir.
// Pinin kendi vakaları ayrı dosyada: `mobileUpdate.kaynakPin.test.ts`.
const SURUM = (over: Partial<MobilSurum> = {}): MobilSurum => ({
  version: "2.3.7", versionCode: 14,
  url: "https://github.com/mert61-python/pemf-update/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "a".repeat(64), size: 1000, ...over,
});

/** ⚠️ `apkIndir` indirmeyi başlatmadan ÖNCE birkaç await geçer (kayıt oku → dosya bilgisi →
 *  kayıt yaz). Tek `await Promise.resolve()` yetmez; sıra tam boşalsın. */
const bosalt = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };

/** İndirme ÖNCESİ dosya YOK, sonraki çağrılarda gerçek bilgi.
 *  (2026-08-17: hazır-dosya hızlı yolu artık indirmeden ÖNCE de bakıyor; tek-değerli mock
 *  bütün testleri "dosya zaten tam" dalına düşürüyordu — YANLIŞ NEDENLE yeşil/kırmızı.) */
const bilgiSirasi = (sonrasi: unknown) =>
  jest.fn().mockResolvedValueOnce({ exists: false }).mockResolvedValue(sonrasi) as never;

const yanit = (body: unknown, ok = true) =>
  jest.fn().mockResolvedValue({ ok, json: async () => body }) as unknown as typeof fetch;

beforeEach(async () => {
  mockOS = "android";
  _indirmeyiSifirla();  // ⚠️ süren-indirme kaydı modül düzeyinde; testler arası sızarsa
                        // sonraki test indirmeyi hiç yapmadan aynı söze abone olur.
  mockApkKur.mockResolvedValue(true);
  mockIzinVarMi.mockReturnValue(true);
  mockIzinEkrani.mockResolvedValue(true);
  mockPaylas.mockResolvedValue(undefined);
  mockCfg.android.versionCode = 13;
  jest.clearAllMocks();
  // ⚠️ ŞART: yarım-indirme izi AsyncStorage'da tutuluyor ve resmî jest mock'u BELLEKTE kalıcı.
  // Temizlenmezse bir testin bıraktığı kayıt sonrakini "aynı iş" sanıyor ve o test, indirmeyi
  // hiç yapmadan "dosya zaten tam" yolundan geçiyordu — YANLIŞ NEDENLE yeşil.
  await AsyncStorage.clear();
});

describe("guncellemeVarMi", () => {
  it("daha yeni versionCode → güncelleme VAR", async () => {
    const r = await guncellemeVarMi(yanit({ mobile: { android: SURUM() } }));
    expect(r.varMi).toBe(true);
    expect(r.surum?.versionCode).toBe(14);
  });

  it("AYNI versionCode → güncelleme YOK", async () => {
    const r = await guncellemeVarMi(yanit({ mobile: { android: SURUM({ versionCode: 13 }) } }));
    expect(r).toEqual({ varMi: false, sebep: "guncel" });
  });

  it("KRİTİK: ESKİ versionCode güncelleme SAYILMAZ (sürüm düşürme yok)", async () => {
    const r = await guncellemeVarMi(yanit({ mobile: { android: SURUM({ versionCode: 5 }) } }));
    expect(r.varMi).toBe(false);
  });

  it("KRİTİK: ağ hatası kullanıcıyı ENGELLEMEZ — sessizce 'yok' döner", async () => {
    const patlar = jest.fn().mockRejectedValue(new Error("net")) as unknown as typeof fetch;
    await expect(guncellemeVarMi(patlar)).resolves.toEqual({ varMi: false, sebep: "manifest" });
  });

  it("HTTP hatası sessizce 'yok' döner", async () => {
    const r = await guncellemeVarMi(yanit({}, false));
    expect(r).toEqual({ varMi: false, sebep: "manifest" });
  });

  it("eksik alanlı manifest güncelleme TETİKLEMEZ", async () => {
    for (const eksik of [{ url: "" }, { versionCode: 0 }, { size: 0 }]) {
      const r = await guncellemeVarMi(yanit({ mobile: { android: SURUM(eksik as Partial<MobilSurum>) } }));
      expect(r.varMi).toBe(false);
      expect(r.sebep).toBe("eksik_alan");
    }
  });

  it("mobile bölümü hiç yoksa güncelleme YOK (eski manifest)", async () => {
    const r = await guncellemeVarMi(yanit({ layers: {} }));
    expect(r.varMi).toBe(false);
  });

  it("KRİTİK: iOS'ta hiç denenmez", async () => {
    mockOS = "ios";
    const f = yanit({ mobile: { android: SURUM() } });
    const r = await guncellemeVarMi(f);
    expect(r).toEqual({ varMi: false, sebep: "platform" });
    expect(f).not.toHaveBeenCalled();
  });

  it("mevcutVersionCode app.json'dan okunur", () => {
    expect(mevcutVersionCode()).toBe(13);
  });
});

describe("apkIndir", () => {
  const indirmeKur = (uri: string | null) =>
    jest.fn().mockReturnValue({ downloadAsync: jest.fn().mockResolvedValue(uri ? { uri } : null) });

  it("boyut tutarsa başarılı", async () => {
    const r = await apkIndir(SURUM(), undefined, {
      createDownloadResumable: indirmeKur("file:///cache/x.apk") as never,
      getInfoAsync: bilgiSirasi({ exists: true, size: 1000 }),
    });
    expect(r).toEqual({ ok: true, dosyaUri: "file:///cache/x.apk" });
  });

  it("KRİTİK: boyut TUTMAZSA dosya SİLİNİR ve kurulum açılmaz", async () => {
    const sil = jest.fn().mockResolvedValue(undefined);
    const r = await apkIndir(SURUM(), undefined, {
      createDownloadResumable: indirmeKur("file:///cache/x.apk") as never,
      getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 42 }) as never,   // yarım indi
      deleteAsync: sil as never,
    });
    expect(r.ok).toBe(false);
    expect(r.hata).toBe("boyut");
    expect(sil).toHaveBeenCalledWith("file:///cache/x.apk", { idempotent: true });
  });

  it("dosya oluşmadıysa 'boyut' hatası ve silme denenir", async () => {
    const sil = jest.fn().mockResolvedValue(undefined);
    const r = await apkIndir(SURUM(), undefined, {
      createDownloadResumable: indirmeKur("file:///cache/x.apk") as never,
      getInfoAsync: jest.fn().mockResolvedValue({ exists: false }) as never,
      deleteAsync: sil as never,
    });
    expect(r.hata).toBe("boyut");
  });

  it("indirme çökerse 'indirme' hatası döner (çökme YOK)", async () => {
    // azamiYenidenDeneme: 0 → otomatik-devam döngüsü kapalı; bu test TEK denemenin
    // sözleşmesini ölçer (döngünün kendi kilidi ayrı: "kesinti sonrası ... sürer").
    const r = await apkIndir(SURUM(), undefined, {
      createDownloadResumable: jest.fn().mockReturnValue({
        downloadAsync: jest.fn().mockRejectedValue(new Error("kesildi")),
      }) as never,
      azamiYenidenDeneme: 0,
    });
    expect(r).toEqual({ ok: false, hata: "indirme" });
  });

  it("ilerleme geri çağrısı 0-1 arası oran verir", async () => {
    const oranlar: number[] = [];
    const olustur = jest.fn().mockImplementation((_u, _h, _o, cb) => {
      cb({ totalBytesWritten: 500, totalBytesExpectedToWrite: 1000 });
      return { downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/x.apk" }) };
    });
    await apkIndir(SURUM(), (o) => oranlar.push(o), {
      createDownloadResumable: olustur as never,
      getInfoAsync: bilgiSirasi({ exists: true, size: 1000 }),
    });
    expect(oranlar).toEqual([0.5]);
  });

  it("dosya adı SÜRÜM KODUNA bağlanır — bayat APK yeni sanılmaz", async () => {
    const olustur = jest.fn().mockReturnValue({
      downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-14.apk" }),
    });
    await apkIndir(SURUM({ versionCode: 14 }), undefined, {
      createDownloadResumable: olustur as never,
      getInfoAsync: bilgiSirasi({ exists: true, size: 1000 }),
    });
    expect(olustur.mock.calls[0][1]).toBe("file:///cache/pemf-vet-14.apk");
  });

  // ── KALDIĞI YERDEN DEVAM (saha bildirimi 2026-08-13) ───────────────────────────────────
  // ARIZA 1: indirme %10'dayken uygulama kapatılıp açılınca SIFIRDAN başlıyordu.
  // ARIZA 2 (sahip): "başka uygulama açtığımda / ekran kilitlendiğinde indirme güvenli şekilde
  //          TAMAMLANMALI".
  //
  // ⚠️ DEVAM NOKTASI DİSKTEN OKUNUR, `savable()`DEN DEĞİL. Android'de `resumeData` opak bir
  // jeton değil, kısmi dosyanın BAYT SAYISIDIR (yerel modül `file.length().toString()` üretir,
  // `Range: bytes=N-` gönderir). `pauseAsync()`e bağlanmak, uygulama ÇÖKERSE/ÖLDÜRÜLÜRSE —
  // devam etmenin asıl gerekli olduğu durumda — kaydı yazma fırsatı bırakmazdı.

  const KAYIT = (over: Record<string, unknown> = {}) => ({
    versionCode: 20, url: "https://x/y.apk", fileUri: "file:///cache/pemf-vet-20.apk", ...over,
  });
  const S20 = (over: Partial<MobilSurum> = {}) =>
    ({ ...SURUM(), versionCode: 20, url: "https://x/y.apk", size: 1000, ...over }) as MobilSurum;
  /** 1. çağrı = kısmi dosya sorgusu, 2. çağrı = indirme sonrası doğrulama. */
  const bilgiSirali = (...yanitlar: unknown[]) => {
    const f = jest.fn();
    yanitlar.forEach((y) => f.mockResolvedValueOnce(y));
    f.mockResolvedValue(yanitlar[yanitlar.length - 1]);
    return f;
  };

  it("KRITIK: yarım dosya varsa SIFIRDAN başlamaz — devam noktası DİSK BOYUTUDUR", async () => {
    const downloadAsync = jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-20.apk" });
    const olustur = jest.fn().mockReturnValue({ downloadAsync });
    const r = await apkIndir(S20(), undefined, {
      createDownloadResumable: olustur as never,
      getInfoAsync: bilgiSirali({ exists: true, size: 400 }, { exists: true, size: 1000 }) as never,
      devamOku: jest.fn().mockResolvedValue(KAYIT()) as never,
      devamYaz: jest.fn() as never,
      devamSil: jest.fn() as never,
    });
    expect(r.ok).toBe(true);
    expect(olustur.mock.calls[0][4]).toBe("400");   // ⚠️ Range: bytes=400-
  });

  it("KRITIK: arka planda DURAKLATILMAZ — indirme kendi kendine tamamlanır", async () => {
    // Yerel modül indirmeyi `Dispatchers.IO` coroutine'inde yürütür (JS iş parçacığında DEĞİL) ve
    // Android'de arka planda koşmaya devam eder. `AppState` ile duraklatmak, TAMAMLANACAK bir
    // indirmeyi DURDURMAK olurdu — sahibin isteğinin tam tersi. Bu test o regresyonu kilitler.
    const pauseAsync = jest.fn();
    await apkIndir(S20(), undefined, {
      createDownloadResumable: jest.fn().mockReturnValue({
        downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-20.apk" }),
        pauseAsync,
      }) as never,
      getInfoAsync: bilgiSirasi({ exists: true, size: 1000 }),
      devamOku: jest.fn().mockResolvedValue(null) as never,
      devamYaz: jest.fn() as never,
      devamSil: jest.fn() as never,
    });
    expect(mockAppStateDinle).not.toHaveBeenCalled();  // AppState'e HİÇ abone olunmaz
    expect(pauseAsync).not.toHaveBeenCalled();         // duraklatma YOK
  });

  it("KRITIK: kayıt indirme BAŞLAMADAN yazılır (süreç öldürülse bile iz kalsın)", async () => {
    const yaz = jest.fn();
    const sira: string[] = [];
    yaz.mockImplementation(() => { sira.push("yaz"); });
    const olustur = jest.fn(() => {
      sira.push("indir");
      return { downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-20.apk" }) };
    });
    await apkIndir(S20(), undefined, {
      createDownloadResumable: olustur as never,
      getInfoAsync: bilgiSirasi({ exists: true, size: 1000 }),
      devamOku: jest.fn().mockResolvedValue(null) as never,
      devamYaz: yaz as never,
      devamSil: jest.fn() as never,
    });
    expect(yaz).toHaveBeenCalledWith({
      versionCode: 20, url: "https://x/y.apk", fileUri: "file:///cache/pemf-vet-20.apk",
    });
    expect(sira).toEqual(["yaz", "indir"]);            // ⚠️ sıra ÖNEMLİ
  });

  it("dosya TAM inmişse yeniden İNDİRİLMEZ (kurulum onayı verilmeden kapatılmıştı)", async () => {
    const olustur = jest.fn();
    const kayitSil = jest.fn();
    const r = await apkIndir(S20(), undefined, {
      createDownloadResumable: olustur as never,
      // ⚠️ Bu testin AMACI hızlı yolun kendisi: dosya İLK bakışta tam olmalı
      // (`bilgiSirasi` kullanmayın, o indirme-öncesi "yok" döndürür).
      getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
      devamOku: jest.fn().mockResolvedValue(KAYIT()) as never,
      devamYaz: jest.fn() as never,
      devamSil: kayitSil as never,
    });
    expect(r).toEqual({ ok: true, dosyaUri: "file:///cache/pemf-vet-20.apk" });
    expect(olustur).not.toHaveBeenCalled();
    expect(kayitSil).toHaveBeenCalled();
  });

  it("beklenenden BÜYÜK kısmi dosya (bozuk ekleme) SİLİNİR ve sıfırdan iner", async () => {
    const sil = jest.fn();
    const olustur = jest.fn().mockReturnValue({
      downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-20.apk" }),
    });
    await apkIndir(S20(), undefined, {
      createDownloadResumable: olustur as never,
      getInfoAsync: bilgiSirali({ exists: true, size: 1500 }, { exists: true, size: 1000 }) as never,
      deleteAsync: sil as never,
      devamOku: jest.fn().mockResolvedValue(KAYIT()) as never,
      devamYaz: jest.fn() as never,
      devamSil: jest.fn() as never,
    });
    expect(sil).toHaveBeenCalledWith("file:///cache/pemf-vet-20.apk", { idempotent: true });
    expect(olustur.mock.calls[0][4]).toBeUndefined();  // devam noktası YOK → baştan
  });

  it("BAŞKA sürümün yarım dosyası ÇÖPTÜR: kayıt+dosya silinir, baştan iner", async () => {
    const olustur = jest.fn().mockReturnValue({
      downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-21.apk" }),
    });
    const sil = jest.fn(); const kayitSil = jest.fn();
    await apkIndir(S20({ versionCode: 21, url: "https://x/YENI.apk" }), undefined, {
      createDownloadResumable: olustur as never,
      getInfoAsync: bilgiSirasi({ exists: true, size: 1000 }),
      deleteAsync: sil as never,
      devamOku: jest.fn().mockResolvedValue(KAYIT()) as never,   // ESKİ sürümün kaydı
      devamYaz: jest.fn() as never,
      devamSil: kayitSil as never,
    });
    expect(kayitSil).toHaveBeenCalled();
    expect(sil).toHaveBeenCalledWith("file:///cache/pemf-vet-20.apk", { idempotent: true });
    expect(olustur.mock.calls[0][4]).toBeUndefined();
  });

  it("tamamlanınca yarım-indirme izi TEMİZLENİR", async () => {
    const kayitSil = jest.fn();
    await apkIndir(S20(), undefined, {
      createDownloadResumable: jest.fn().mockReturnValue({
        downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-20.apk" }),
      }) as never,
      getInfoAsync: bilgiSirasi({ exists: true, size: 1000 }),
      devamOku: jest.fn().mockResolvedValue(null) as never,
      devamYaz: jest.fn() as never,
      devamSil: kayitSil as never,
    });
    expect(kayitSil).toHaveBeenCalled();
  });

  it("KRITIK: ağ koparsa iz BIRAKILIR — sonraki deneme kaldığı yerden sürsün", async () => {
    const kayitSil = jest.fn(); const sil = jest.fn();
    const r = await apkIndir(S20(), undefined, {
      createDownloadResumable: jest.fn().mockReturnValue({
        downloadAsync: jest.fn().mockRejectedValue(new Error("ağ koptu")),
      }) as never,
      getInfoAsync: bilgiSirali({ exists: true, size: 400 }) as never,
      deleteAsync: sil as never,
      devamOku: jest.fn().mockResolvedValue(KAYIT()) as never,
      devamYaz: jest.fn() as never,
      devamSil: kayitSil as never,
      azamiYenidenDeneme: 0, // tek-deneme sözleşmesi (otomatik-devam döngüsünün kendi kilidi ayrı)
    });
    expect(r).toEqual({ ok: false, hata: "indirme" });
    expect(kayitSil).not.toHaveBeenCalled();   // ⚠️ iz SİLİNMEZ
    expect(sil).not.toHaveBeenCalled();        // ⚠️ kısmi dosya DURUR
  });

  // ── KESİNTİ-SONRASI OTOMATİK DEVAM (2026-08-27 saha bildirimi: "sürekli kesilmesin") ──
  it("KRITIK: kesinti sonrası KENDİLİĞİNDEN yeni deneme açılır ve KALDIĞI BAYTTAN sürer", async () => {
    // 1. deneme: 400 baytta ağ kopar (reddedilir). 2. deneme: diskte 700 bayt bulunur →
    // devam noktası "700" ile açılır ve tamamlanır. Kullanıcı HİÇBİR ŞEYE dokunmaz.
    const cagrilar: Array<string | undefined> = [];
    let deneme = 0;
    const olustur = jest.fn().mockImplementation((_u, _h, _o, _cb, devam) => {
      cagrilar.push(devam);
      deneme++;
      return deneme === 1
        ? { downloadAsync: jest.fn().mockRejectedValue(new Error("ağ koptu")) }
        : { downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-20.apk", status: 206 }) };
    });
    // getInfoAsync sırası: [1. deneme hazır-kontrol] 400/kısmi → [2. deneme hazır-kontrol] 700/kısmi
    // → [2. deneme boyut kapısı] 1000/tam.
    const bilgi = jest.fn()
      .mockResolvedValueOnce({ exists: true, size: 400 })
      .mockResolvedValueOnce({ exists: true, size: 700 })
      .mockResolvedValue({ exists: true, size: 1000 });
    const bekle = jest.fn().mockResolvedValue(undefined);
    const r = await apkIndir(S20(), undefined, {
      createDownloadResumable: olustur as never,
      getInfoAsync: bilgi as never,
      deleteAsync: jest.fn() as never,
      devamOku: jest.fn().mockResolvedValue(KAYIT()) as never,
      devamYaz: jest.fn() as never,
      devamSil: jest.fn() as never,
      azamiYenidenDeneme: 3,
      kesintiBekle: bekle,
    });
    expect(r.ok).toBe(true);
    expect(bekle).toHaveBeenCalledTimes(1);          // kesintiden sonra beklendi ve devam edildi
    expect(cagrilar).toEqual(["400", "700"]);        // ⚠️ 2. deneme SIFIRDAN değil, 700. bayttan
  });

  it("KRITIK: indirme boyunca ekran uyanık + ön-plan servisi; bitince İKİSİ DE bırakılır", async () => {
    // (2026-08-27 saha bildirimi: ekran kilidi/arka plan kesintisi.) Başarı YOLUNDA da hata
    // yolunda da 'finally' temizliği çalışmalı — bildirim asılı kalmasın, ekran kilitlenebilsin.
    mockServisBaslat.mockClear(); mockServisDurdur.mockClear();
    mockUyanikTut.mockClear(); mockUyanikBirak.mockClear();
    const tamam = await apkIndir(SURUM(), undefined, {
      createDownloadResumable: jest.fn().mockReturnValue({
        downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-14.apk", status: 200 }),
      }) as never,
      getInfoAsync: jest.fn()
        .mockResolvedValueOnce({ exists: false })
        .mockResolvedValue({ exists: true, size: 1000 }) as never,
      deleteAsync: jest.fn() as never,
      devamOku: jest.fn().mockResolvedValue(null) as never,
      devamYaz: jest.fn() as never,
      devamSil: jest.fn() as never,
    });
    expect(tamam.ok).toBe(true);
    expect(mockUyanikTut).toHaveBeenCalledTimes(1);
    expect(mockUyanikBirak).toHaveBeenCalledTimes(1);
    expect(mockServisBaslat).toHaveBeenCalledTimes(1);
    expect(String((mockServisBaslat.mock.calls[0] as unknown[])[0])).toContain("2.3.7"); // bildirim sürümü söyler
    expect(mockServisDurdur).toHaveBeenCalledTimes(1);

    // hata yolunda da temizlik (finally):
    mockServisDurdur.mockClear(); mockUyanikBirak.mockClear();
    _indirmeyiSifirla();
    await apkIndir(SURUM(), undefined, {
      createDownloadResumable: jest.fn().mockReturnValue({
        downloadAsync: jest.fn().mockRejectedValue(new Error("koptu")),
      }) as never,
      azamiYenidenDeneme: 0,
    });
    expect(mockUyanikBirak).toHaveBeenCalledTimes(1);
    expect(mockServisDurdur).toHaveBeenCalledTimes(1);
  });

  it("KARŞIT: deterministik hatalar ('sunucu') YENİDEN DENENMEZ — tekrar durumu değiştirmez", async () => {
    const bekle = jest.fn().mockResolvedValue(undefined);
    const olustur = jest.fn().mockReturnValue({
      downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-20.apk", status: 404 }),
    });
    const r = await apkIndir(S20(), undefined, {
      createDownloadResumable: olustur as never,
      getInfoAsync: jest.fn().mockResolvedValue({ exists: false }) as never,
      deleteAsync: jest.fn() as never,
      devamOku: jest.fn().mockResolvedValue(null) as never,
      devamYaz: jest.fn() as never,
      devamSil: jest.fn() as never,
      azamiYenidenDeneme: 5,
      kesintiBekle: bekle,
    });
    expect(r).toEqual({ ok: false, hata: "sunucu" });
    expect(olustur).toHaveBeenCalledTimes(1);  // tek deneme
    expect(bekle).not.toHaveBeenCalled();
  });

  it("devam ederken ilerleme GERİ GİTMEZ (yüzde sıfırlanmaz)", async () => {
    const oranlar: number[] = [];
    const olustur = jest.fn().mockImplementation((_u, _h, _o, cb) => {
      cb({ totalBytesWritten: 600, totalBytesExpectedToWrite: 1000 });  // yerel modül devamı ekler
      return { downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-20.apk" }) };
    });
    await apkIndir(S20(), (o) => oranlar.push(o), {
      createDownloadResumable: olustur as never,
      getInfoAsync: bilgiSirali({ exists: true, size: 400 }, { exists: true, size: 1000 }) as never,
      devamOku: jest.fn().mockResolvedValue(KAYIT()) as never,
      devamYaz: jest.fn() as never,
      devamSil: jest.fn() as never,
    });
    expect(oranlar).toEqual([0.6]);
  });
});

describe("erteleme kaydı (açılış kapısı ↔ uygulama içi bant)", () => {
  beforeEach(() => { _atlamayiSifirla(); });

  it("ertelenen sürüm işaretlenir, başkası işaretlenmez", () => {
    expect(atlandiMi(30)).toBe(false);
    guncellemeyiAtla(30);
    expect(atlandiMi(30)).toBe(true);
    expect(atlandiMi(31)).toBe(false);
    expect(atlandiMi(29)).toBe(false);
  });

  it("KRİTİK: erteleme DİSKE YAZILMAZ — sonraki soğuk açılışta kapı yeniden sorar", async () => {
    guncellemeyiAtla(30);
    // Kalıcı yazsaydık kullanıcı bir kez \"sonra\" deyip düzeltme taşıyan bir yayını SONSUZA DEK
    // kapatabilirdi. Tüm AsyncStorage anahtarları taranır: hiçbirinde bu iz olmamalı.
    const anahtarlar = await AsyncStorage.getAllKeys();
    for (const a of anahtarlar) {
      const v = await AsyncStorage.getItem(a);
      expect(String(v ?? "")).not.toContain("atlan");
    }
    expect(anahtarlar.some((a) => a.toLowerCase().includes("atla"))).toBe(false);
  });

  it("0 / geçersiz sürüm kodu hiçbir şeyi ertelemiş SAYMAZ", () => {
    guncellemeyiAtla(0);
    expect(atlandiMi(0)).toBe(false);
    guncellemeyiAtla(Number.NaN);
    expect(atlandiMi(Number.NaN)).toBe(false);
  });

  it("son çağrı geçerlidir (kullanıcı yeni sürümü ertelediğinde eskisi takılı kalmaz)", () => {
    guncellemeyiAtla(30);
    guncellemeyiAtla(31);
    expect(atlandiMi(31)).toBe(true);
    expect(atlandiMi(30)).toBe(false);
  });
});

describe("🔴 SAHA BİLDİRİMİ 2026-08-17 — kurulum ve yeniden indirme", () => {
  it("🔴 TAM inmiş dosya KAYIT OLMADAN tanınır — 'yüzde 0'dan başladı' arızası", async () => {
    // Sahip: "geri çıkma tuşuna bastım, tekrar yüzde 0'dan başladı."
    // Kök neden: indirme bitince `kayitSil()` izi siler; hızlı yol ise `ayniIs` (yani KAYIT)
    // kapısının içindeydi → hazır 128 MB yeniden iniyordu. Kayıt YOKKEN de tanınmalı.
    const s = SURUM();
    const olustur = jest.fn();
    const r = await apkIndir(s, undefined, {
      createDownloadResumable: olustur as never,
      getInfoAsync: (jest.fn().mockResolvedValue({ exists: true, size: s.size })) as never,
      deleteAsync: jest.fn() as never,
      devamOku: (async () => null) as never, // ← KAYIT YOK
      devamYaz: (async () => {}) as never,
      devamSil: (async () => {}) as never,
    });
    expect(r).toEqual({ ok: true, dosyaUri: expect.stringContaining(`pemf-vet-${s.versionCode}.apk`) });
    expect(olustur).not.toHaveBeenCalled(); // tek bayt bile inmedi
  });

  it("🔴 aynı sürüm için İKİNCİ çağrı yeni indirme BAŞLATMAZ (tek yazıcı)", async () => {
    // Kapıda indirmeye başlayıp "şimdilik devam et" diyen kullanıcı bantta yine "Güncelle"ye
    // basabilir. İki yazıcı aynı dosyayı bozar → boyut tutmaz → sebepsiz "eksik kaldı".
    const s = SURUM();
    const olustur = jest.fn(() => ({ downloadAsync: () => new Promise(() => {}) }));
    const ortak = {
      createDownloadResumable: olustur as never,
      getInfoAsync: (jest.fn().mockResolvedValue({ exists: false })) as never,
      deleteAsync: jest.fn() as never,
      devamOku: (async () => null) as never,
      devamYaz: (async () => {}) as never,
      devamSil: (async () => {}) as never,
    };
    void apkIndir(s, undefined, ortak);
    await bosalt();
    void apkIndir(s, undefined, ortak);
    await bosalt();
    expect(olustur).toHaveBeenCalledTimes(1);
  });

  it("ikinci abone MEVCUT yüzdeyi görür — bant 0'dan başlamaz", async () => {
    const s = SURUM();
    let bildir: (p: { totalBytesWritten: number; totalBytesExpectedToWrite: number }) => void = () => {};
    const ortak = {
      createDownloadResumable: ((_u: string, _h: string, _o: unknown, cb: typeof bildir) => {
        bildir = cb;
        return { downloadAsync: () => new Promise(() => {}) };
      }) as never,
      getInfoAsync: (jest.fn().mockResolvedValue({ exists: false })) as never,
      deleteAsync: jest.fn() as never,
      devamOku: (async () => null) as never,
      devamYaz: (async () => {}) as never,
      devamSil: (async () => {}) as never,
    };
    void apkIndir(s, undefined, ortak);
    await bosalt();
    bildir({ totalBytesWritten: 600, totalBytesExpectedToWrite: 1000 });

    const gorulen: number[] = [];
    void apkIndir(s, (o) => gorulen.push(o), ortak);
    await bosalt();
    expect(gorulen[0]).toBeCloseTo(0.6, 5); // 0 DEĞİL
  });

  it("FARKLI sürüm süren indirmeye abone OLMAZ (kendi indirmesini başlatır)", async () => {
    const olustur = jest.fn(() => ({ downloadAsync: () => new Promise(() => {}) }));
    const ortak = {
      createDownloadResumable: olustur as never,
      getInfoAsync: (jest.fn().mockResolvedValue({ exists: false })) as never,
      deleteAsync: jest.fn() as never,
      devamOku: (async () => null) as never,
      devamYaz: (async () => {}) as never,
      devamSil: (async () => {}) as never,
    };
    void apkIndir(SURUM({ versionCode: 14 }), undefined, ortak);
    await bosalt();
    void apkIndir(SURUM({ versionCode: 15 }), undefined, ortak);
    await bosalt();
    expect(olustur).toHaveBeenCalledTimes(2);
  });
});

describe("🔴 kurulumuBaslat — paylaşım sayfası DEĞİL, paket yükleyici", () => {
  it("🔴 SAHİP BİLDİRİMİ: doğrudan yükleyici açılır, PAYLAŞIM AÇILMAZ", async () => {
    // "indirme bitince paylaşma ekranı geliyor... paylaşıp napcak kullanıcı apk'yı"
    const sonuc = await kurulumuBaslat("file:///cache/pemf-vet-23.apk");
    expect(sonuc).toBe("acildi");
    expect(mockApkKur).toHaveBeenCalledWith("file:///cache/pemf-vet-23.apk");
    expect(mockPaylas).not.toHaveBeenCalled(); // ← asıl arıza buydu
  });

  it("🔴 'bilinmeyen kaynak' izni yoksa İZİN EKRANI açılır (sessiz ret yok)", async () => {
    mockIzinVarMi.mockReturnValue(false);
    const sonuc = await kurulumuBaslat("file:///cache/x.apk");
    expect(sonuc).toBe("izin_gerekli");
    expect(mockIzinEkrani).toHaveBeenCalled();
    expect(mockApkKur).not.toHaveBeenCalled(); // anlaşılmaz bir ret gösterme
  });

  it("yerel modül kaydolmamışsa PAYLAŞIM yedeğine düşer (akış ölmez)", async () => {
    mockApkKur.mockResolvedValue(false);
    const sonuc = await kurulumuBaslat("file:///cache/x.apk");
    expect(sonuc).toBe("paylasim");
    expect(mockPaylas).toHaveBeenCalled();
  });

  it("hiçbir yol açılamazsa 'hata' döner", async () => {
    mockApkKur.mockResolvedValue(false);
    mockPaylas.mockRejectedValue(new Error("yok"));
    expect(await kurulumuBaslat("file:///cache/x.apk")).toBe("hata");
  });

  it("KRİTİK: iOS'ta hiç denenmez", async () => {
    mockOS = "ios";
    expect(await kurulumuBaslat("file:///cache/x.apk")).toBe("hata");
    expect(mockApkKur).not.toHaveBeenCalled();
    expect(mockPaylas).not.toHaveBeenCalled();
  });

  it("KRİTİK [17. parti]: AYNI URI için EŞZAMANLI iki çağrı TEK yükleyici niyetine düşer", async () => {
    // Adversaryal inceleme RISK'i: kapı indirme uçuştayken "Şimdilik devam et" + banttan
    // "Güncelle" dokunuşu, aynı indirme sözüne abone İKİ kanca örneğini (kapının ölü örneği +
    // bandınki) aynı anda kurulum kapısından geçirebiliyordu → iki ACTION_VIEW niyeti (izin
    // yoksa izin ekranı İKİ KEZ). Uçuştaki açılış sözü URI başına paylaşılmalı.
    let coz: (v: boolean) => void = () => {};
    mockApkKur.mockImplementation(() => new Promise<boolean>((r) => { coz = r; }));

    const s1 = kurulumuBaslat("file:///cache/ayni.apk");
    const s2 = kurulumuBaslat("file:///cache/ayni.apk"); // uçuşta — aynı söze abone olmalı
    coz(true);
    expect(await s1).toBe("acildi");
    expect(await s2).toBe("acildi");
    expect(mockApkKur).toHaveBeenCalledTimes(1);
  });

  it("KARŞIT-KANIT [17. parti]: söz ÇÖZÜLDÜKTEN sonra yeni çağrı yükleyiciyi YİNE açar", async () => {
    // Tekilleştirme yalnız UÇUŞTAKİ çağrıyı kapsar — "Kurulumu tekrar aç" düğmesi çalışmalı.
    expect(await kurulumuBaslat("file:///cache/ayni.apk")).toBe("acildi");
    expect(await kurulumuBaslat("file:///cache/ayni.apk")).toBe("acildi");
    expect(mockApkKur).toHaveBeenCalledTimes(2);
  });
});
