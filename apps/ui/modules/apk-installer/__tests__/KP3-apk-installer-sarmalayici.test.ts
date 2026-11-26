/**
 * KP-3 C · modules/apk-installer — yerel modülün JS yüzü (her test bir DAVRANIŞ iddiası):
 *  - Yerel modül YOKSA (iOS / eski APK / kayıt düşmüş) hiçbir işlev atmaz: kurucu yok, kurulum izni VAR sayılır (eski davranış),
 *    izin ekranı / kurulum / servis false, sha256 boş dize (doğrulama atlanır — engellemez).
 *  - Yerel modül VARSA çağrılar aynen iletilir (yol, bildirim başlığı / metni / kanal).
 *  - Yerel çağrı atarsa güvenli varsayılan döner (izin true, diğerleri false / ""); servis işlevleri olmayan ESKİ yerel modül false döner.
 * SAHTE: expo-modules-core `requireOptionalNativeModule` + react-native Platform (platform sınırı; modül YÜKLENİRKEN okur → izole yüklenir).
 */
type Mod = typeof import("../index");

function yukle(os: string, yerli: unknown): Mod {
  let m: Mod | undefined;
  jest.isolateModules(() => {
    jest.doMock("react-native", () => ({ Platform: { OS: os } }));
    jest.doMock("expo-modules-core", () => ({ requireOptionalNativeModule: jest.fn(() => yerli) }));
    m = require("../index");
  });
  // YS1f (CI Node 22): `jest.doMock` kaydı `isolateModules` DIŞINA da sızar; sonradan expo'nun tembel `fetch` küreseli
  // yüklenince yalnız `requireOptionalNativeModule` taşıyan sahte `expo-modules-core`u alıp süiti düşürüyordu
  // ("requireNativeModule is not a function"). Sahte yalnız `../index`in yüklenmesi için → yüklemeden sonra geri alınır.
  jest.dontMock("react-native");
  jest.dontMock("expo-modules-core");
  return m!;
}

it("yerel modül yoksa (iOS) hiçbir işlev atmaz; güvenli varsayılanlar", async () => {
  const m = yukle("ios", { apkKur: jest.fn(async () => true) });
  expect(m.apkKuruculVarMi()).toBe(false);
  expect(m.kurulumIzniVarMi()).toBe(true);
  await expect(m.izinEkraniniAc()).resolves.toBe(false);
  await expect(m.apkKur("file:///a.apk")).resolves.toBe(false);
  await expect(m.dosyaSha256("file:///a.apk")).resolves.toBe("");
  await expect(m.indirmeServisiniBaslat("b", "m", "k")).resolves.toBe(false);
  await expect(m.indirmeServisiniDurdur()).resolves.toBe(false);
});

it("YS1f: sahte modüller yalnız yükleme içindir — yüklemeden sonra expo-modules-core / react-native GERÇEK (sızıntı yok)", () => {
  yukle("android", null);
  jest.isolateModules(() => {
    expect(typeof require("expo-modules-core").requireNativeModule).toBe("function");
    expect(require("react-native").Platform.OS).not.toBe("android");
  });
});

it("yerel modül varsa çağrılar aynen iletilir", async () => {
  const yerli = {
    kurulumIzniVarMi: jest.fn(() => false),
    izinEkraniniAc: jest.fn(async () => true),
    apkKur: jest.fn(async () => true),
    sha256: jest.fn(async () => "ab".repeat(32)),
    indirmeServisiniBaslat: jest.fn(async () => true),
    indirmeServisiniDurdur: jest.fn(async () => true),
  };
  const m = yukle("android", yerli);
  expect(m.apkKuruculVarMi()).toBe(true);
  expect(m.kurulumIzniVarMi()).toBe(false);
  await expect(m.izinEkraniniAc()).resolves.toBe(true);
  await expect(m.apkKur("file:///cache/pemf-vet-14.apk")).resolves.toBe(true);
  expect(yerli.apkKur).toHaveBeenCalledWith("file:///cache/pemf-vet-14.apk");
  await expect(m.dosyaSha256("file:///x")).resolves.toBe("ab".repeat(32));
  await expect(m.indirmeServisiniBaslat("Güncelleme", "İndiriliyor", "Kanal")).resolves.toBe(true);
  expect(yerli.indirmeServisiniBaslat).toHaveBeenCalledWith("Güncelleme", "İndiriliyor", "Kanal");
  await expect(m.indirmeServisiniDurdur()).resolves.toBe(true);
});

it("yerel çağrı atarsa güvenli varsayılan; servis işlevleri olmayan eski yerel modül false", async () => {
  const at = () => { throw new Error("yerel düştü"); };
  const m = yukle("android", {
    kurulumIzniVarMi: at, izinEkraniniAc: jest.fn(async () => at()), apkKur: jest.fn(async () => at()), sha256: jest.fn(async () => at()),
    indirmeServisiniBaslat: jest.fn(async () => at()), indirmeServisiniDurdur: jest.fn(async () => at()),
  });
  expect(m.kurulumIzniVarMi()).toBe(true);
  await expect(m.izinEkraniniAc()).resolves.toBe(false);
  await expect(m.apkKur("f")).resolves.toBe(false);
  await expect(m.dosyaSha256("f")).resolves.toBe("");
  await expect(m.indirmeServisiniBaslat("a", "b")).resolves.toBe(false);
  await expect(m.indirmeServisiniDurdur()).resolves.toBe(false);
  const eski = yukle("android", { kurulumIzniVarMi: () => true, izinEkraniniAc: async () => true, apkKur: async () => true, sha256: async () => "" });
  await expect(eski.indirmeServisiniBaslat("a", "b")).resolves.toBe(false);
  await expect(eski.indirmeServisiniDurdur()).resolves.toBe(false);
});
