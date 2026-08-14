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
// ⚠️ `AppState` de SAĞLANMALI (2026-08-13): modül artık arka plana geçişte indirmeyi duraklatıp
// devam bilgisini diske yazıyor. Mock'ta yoksa `addEventListener` üzerinden TypeError atılıyor,
// dış `catch` onu yutuyor ve testler "indirme hatası" görüyordu (üç test bu yüzden düştü).
const mockAppStateAbone = { remove: jest.fn() };
let mockAppStateCb: ((s: string) => void) | null = null;
jest.mock("react-native", () => ({
  __esModule: true,
  Platform: { get OS() { return mockOS; } },
  AppState: {
    addEventListener: (_t: string, cb: (s: string) => void) => {
      mockAppStateCb = cb;
      return mockAppStateAbone;
    },
  },
}));

// `expo-constants` VARSAYILAN dışa aktarım kullanır; mock hem `default` hem düz alan olarak
// vermeli, yoksa derlenen import undefined görür. Getter → testler arası değiştirilebilir.
const mockCfg: { android: { versionCode: number } } = { android: { versionCode: 13 } };
jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { get expoConfig() { return mockCfg; } },
  get expoConfig() { return mockCfg; },
}));

import { apkIndir, guncellemeVarMi, mevcutVersionCode, type MobilSurum } from "../mobileUpdate";

const SURUM = (over: Partial<MobilSurum> = {}): MobilSurum => ({
  version: "2.3.7", versionCode: 14,
  url: "https://github.com/o/r/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "a".repeat(64), size: 1000, ...over,
});

const yanit = (body: unknown, ok = true) =>
  jest.fn().mockResolvedValue({ ok, json: async () => body }) as unknown as typeof fetch;

beforeEach(() => {
  mockOS = "android";
  mockCfg.android.versionCode = 13;
  jest.clearAllMocks();
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
  beforeEach(() => { mockAppStateCb = null; });
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

  // ── KALDIĞI YERDEN DEVAM + ARKA PLAN GÜVENLİĞİ (saha bildirimi 2026-08-13) ──────────────
  // ARIZA 1: indirme %10'dayken uygulama kapatılıp açılınca SIFIRDAN başlıyordu.
  //          `createDownloadResumable` kullanılıyordu ama `savable()` HİÇ saklanmıyordu.
  // ARIZA 2: başka uygulamaya geçince / ekran kilitlenince indirme sessizce asılı kalıyordu.
  //          Artık arka plana geçişte DURAKLATILIR + diske yazılır, öne dönünce SÜRER.

  const KAYIT = (over: Record<string, unknown> = {}) => ({
    versionCode: 20, url: "https://x/y.apk", fileUri: "file:///cache/x.apk",
    resumeData: "TOKEN", ...over,
  });

  it("KRITIK: kayıtlı devam bilgisiyle SIFIRDAN başlamaz (resumeAsync + token)", async () => {
    const resumeAsync = jest.fn().mockResolvedValue({ uri: "file:///cache/x.apk" });
    const downloadAsync = jest.fn();
    const olustur = jest.fn().mockReturnValue({ resumeAsync, downloadAsync, pauseAsync: jest.fn() });
    const r = await apkIndir(
      { ...SURUM(), versionCode: 20, url: "https://x/y.apk", size: 1000 } as never,
      undefined,
      {
        createDownloadResumable: olustur as never,
        getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
        devamOku: jest.fn().mockResolvedValue(KAYIT()) as never,
        devamYaz: jest.fn() as never,
        devamSil: jest.fn() as never,
      },
    );
    expect(r.ok).toBe(true);
    expect(resumeAsync).toHaveBeenCalled();
    expect(downloadAsync).not.toHaveBeenCalled();          // ⚠️ baştan indirme YOK
    expect(olustur.mock.calls[0][4]).toBe("TOKEN");         // devam token'ı geçirildi
  });

  it("BAŞKA sürümün yarım dosyası ÇÖPTÜR: kayıt silinir, dosya silinir, baştan iner", async () => {
    const downloadAsync = jest.fn().mockResolvedValue({ uri: "file:///cache/x.apk" });
    const olustur = jest.fn().mockReturnValue({ downloadAsync, resumeAsync: jest.fn(), pauseAsync: jest.fn() });
    const sil = jest.fn(); const kayitSil = jest.fn();
    await apkIndir(
      { ...SURUM(), versionCode: 21, url: "https://x/YENI.apk", size: 1000 } as never,
      undefined,
      {
        createDownloadResumable: olustur as never,
        getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
        deleteAsync: sil as never,
        devamOku: jest.fn().mockResolvedValue(KAYIT()) as never,   // ESKİ sürüm kaydı
        devamYaz: jest.fn() as never,
        devamSil: kayitSil as never,
      },
    );
    expect(kayitSil).toHaveBeenCalled();
    expect(sil).toHaveBeenCalledWith("file:///cache/x.apk", { idempotent: true });
    expect(downloadAsync).toHaveBeenCalled();               // devam DEĞİL, baştan
    expect(olustur.mock.calls[0][4]).toBeUndefined();       // token geçirilmedi
  });

  it("KRITIK: arka plana geçince DURAKLATIR ve devam bilgisini YAZAR", async () => {
    const savable = { url: "https://x/y.apk", fileUri: "file:///cache/x.apk", options: {}, resumeData: "T2" };
    const pauseAsync = jest.fn().mockResolvedValue(savable);
    let bitir: (v: unknown) => void = () => {};
    const downloadAsync = jest.fn(() => new Promise((c) => { bitir = c; }));
    const yaz = jest.fn();
    const p = apkIndir(
      { ...SURUM(), versionCode: 20, url: "https://x/y.apk", size: 1000 } as never,
      undefined,
      {
        createDownloadResumable: jest.fn().mockReturnValue({ downloadAsync, pauseAsync, resumeAsync: jest.fn() }) as never,
        getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
        devamOku: jest.fn().mockResolvedValue(null) as never,
        devamYaz: yaz as never,
        devamSil: jest.fn() as never,
      },
    );
    // ⚠️ ÖNCE bir tik bekle: `apkIndir` ilk `await`ine (devam kaydını okuma) kadar senkron
    // ilerler; dinleyici HENÜZ kaydolmamıştır. Beklemeden tetiklemek olayı boşa harcıyordu.
    await new Promise((r) => setTimeout(r, 0));
    mockAppStateCb?.("background");                          // ekran kilitlendi / başka uygulama
    await new Promise((r) => setTimeout(r, 0));
    expect(pauseAsync).toHaveBeenCalled();
    expect(yaz).toHaveBeenCalledWith(expect.objectContaining({ resumeData: "T2", versionCode: 20 }));
    bitir({ uri: "file:///cache/x.apk" });                   // indirme tamamlansın, test kapansın
    await p;
  });

  it("tamamlanınca yarım-indirme kaydı TEMİZLENİR", async () => {
    const kayitSil = jest.fn();
    await apkIndir(
      { ...SURUM(), versionCode: 20, size: 1000 } as never,
      undefined,
      {
        createDownloadResumable: jest.fn().mockReturnValue({
          downloadAsync: jest.fn().mockResolvedValue({ uri: "file:///cache/x.apk" }),
          pauseAsync: jest.fn(), resumeAsync: jest.fn(),
        }) as never,
        getInfoAsync: jest.fn().mockResolvedValue({ exists: true, size: 1000 }) as never,
        devamOku: jest.fn().mockResolvedValue(null) as never,
        devamYaz: jest.fn() as never,
        devamSil: kayitSil as never,
      },
    );
    expect(kayitSil).toHaveBeenCalled();
  });

});
