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
  type MobilSurum,
} from "../mobileUpdate";

const SURUM = (over: Partial<MobilSurum> = {}): MobilSurum => ({
  version: "2.3.7", versionCode: 14,
  url: "https://github.com/o/r/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "a".repeat(64), size: 1000, ...over,
});

const yanit = (body: unknown, ok = true) =>
  jest.fn().mockResolvedValue({ ok, json: async () => body }) as unknown as typeof fetch;

beforeEach(async () => {
  mockOS = "android";
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
      getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
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
    const r = await apkIndir(SURUM(), undefined, {
      createDownloadResumable: jest.fn().mockReturnValue({
        downloadAsync: jest.fn().mockRejectedValue(new Error("kesildi")),
      }) as never,
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
      getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
    });
    expect(oranlar).toEqual([0.5]);
  });

  it("dosya adı SÜRÜM KODUNA bağlanır — bayat APK yeni sanılmaz", async () => {
    const olustur = jest.fn().mockReturnValue({
      downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/pemf-vet-14.apk" }),
    });
    await apkIndir(SURUM({ versionCode: 14 }), undefined, {
      createDownloadResumable: olustur as never,
      getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
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
      getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
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
      getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
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
      getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
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
      getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
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
    });
    expect(r).toEqual({ ok: false, hata: "indirme" });
    expect(kayitSil).not.toHaveBeenCalled();   // ⚠️ iz SİLİNMEZ
    expect(sil).not.toHaveBeenCalled();        // ⚠️ kısmi dosya DURUR
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
