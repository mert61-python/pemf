/**
 * KP-4 B1 · src/services/mobileUpdate.ts — SÜREN indirmeye katılan ikinci çağıran (kapıda başlayan indirme + bantta "Güncelle"):
 * mevcut yüzdeyi HEMEN, sonraki ilerlemeyi de canlı görür ve indirme bitince İLK çağıranla AYNI sonucu (aynı dosya) alır; tek dosya
 * yazıcısı vardır (ikinci indirme başlamaz). Bitişten sonra ikinci çağıranın aboneliği bırakılır.
 * SAHTE: expo-file-system işlemleri (enjeksiyon), yerel modüller ve platform (mobileUpdate.test ile aynı düzenek).
 */
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
  _indirmeyiSifirla,
  type MobilSurum,
} from "../mobileUpdate";

// ⚠️ URL GERÇEK YAYIN YOLUNU taşımalı (2026-08-23): `guncellemeVarMi` artık kaynağı pinliyor
// (`kaynakGuvenli` — masaüstü `net.rs` paritesi) ve uydurma bir depo yolu HAKLI OLARAK elenir.
// Pinin kendi vakaları ayrı dosyada: `mobileUpdate.kaynakPin.test.ts`.
const SURUM = (): MobilSurum => ({
  version: "2.3.7", versionCode: 14,
  url: "https://github.com/mert61-python/pemf-update/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "a".repeat(64), size: 1000,
});
const bosalt = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };

beforeEach(async () => {
  mockOS = "android";
  _indirmeyiSifirla();
  jest.clearAllMocks();
  await AsyncStorage.clear();
});

it("KRİTİK: süren indirmeye katılan çağıran mevcut + canlı yüzdeyi görür ve AYNI sonucu alır; ikinci indirme başlamaz", async () => {
  let bildir: (p: { totalBytesWritten: number; totalBytesExpectedToWrite: number }) => void = () => {};
  let bitir: (v: { uri: string }) => void = () => {};
  const olustur = jest.fn((_u: string, _h: string, _o: unknown, cb: typeof bildir) => {
    bildir = cb;
    return { downloadAsync: () => new Promise<{ uri: string }>((r) => { bitir = r; }) };
  });
  const ortak = {
    createDownloadResumable: olustur as never,
    getInfoAsync: (jest.fn().mockResolvedValueOnce({ exists: false }).mockResolvedValue({ exists: true, size: 1000 })) as never,
    deleteAsync: jest.fn() as never,
    devamOku: (async () => null) as never,
    devamYaz: (async () => {}) as never,
    devamSil: (async () => {}) as never,
  };
  const ilk = apkIndir(SURUM(), undefined, ortak);
  await bosalt();
  bildir({ totalBytesWritten: 600, totalBytesExpectedToWrite: 1000 });
  const gorulen: number[] = [];
  const ikinci = apkIndir(SURUM(), (o) => gorulen.push(o), ortak);
  await bosalt();
  expect(gorulen).toEqual([0.6]);
  bildir({ totalBytesWritten: 900, totalBytesExpectedToWrite: 1000 });
  expect(gorulen[gorulen.length - 1]).toBeCloseTo(0.9, 5);
  bitir({ uri: "file:///cache/pemf-vet-14.apk" });
  const [r1, r2] = await Promise.all([ilk, ikinci]);
  expect(r2).toEqual(r1);
  expect(r2).toEqual({ ok: true, dosyaUri: expect.stringContaining("pemf-vet-14.apk") });
  expect(olustur).toHaveBeenCalledTimes(1);
});
