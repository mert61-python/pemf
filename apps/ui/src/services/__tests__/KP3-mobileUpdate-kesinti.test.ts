/**
 * KP-3 C · mobileUpdate KESİNTİ SONRASI OTOMATİK DEVAM — GERÇEK bekleme (`_kesintiSonrasiBekle`) ve TIKANMA BEKÇİSİ (mevcut testler bekleme
 * kancasını enjekte ettiği için bu yollar hiç koşmuyordu). Her test bir DAVRANIŞ iddiası:
 *  - Ön planda düşen deneme 3 sn nefesten SONRA yinelenir (daha önce değil); AppState'e abone OLUNMAZ.
 *  - Arka planda düşen deneme hak yakmaz: uygulama "active" olana dek BEKLER (10 dk sonra bile yeni deneme yok), etkin olunca hemen
 *    yinelenir ve geçici abonelik kaldırılır; hiç etkin olmazsa 30 dk tavanında yine denenir; abonelik kurulamazsa beklemeden denenir.
 *  - Tıkanma bekçisi: ön planda 90 sn tek bayt akmazsa yerel iş `pauseAsync` ile düşürülür ve döngü yeni denemeyle sürer; bayt aktıkça
 *    düşürülmez.
 *  - İndirme sonucu dosya adresi taşımıyorsa "indirme" hatası; bozuk devam kaydı (JSON değil) indirmeyi düşürmez.
 * SAHTE: expo-file-system işlemleri (enjeksiyon), AppState (platform), yerel modüller (mobileUpdate.test ile aynı).
 */
const mockAppState: { currentState?: string; dinleyici?: (d: string) => void; kaldirildi: number; abonelikAtar: boolean } = { kaldirildi: 0, abonelikAtar: false };
jest.mock("react-native", () => ({
  __esModule: true,
  Platform: { OS: "android" },
  AppState: {
    get currentState() { return mockAppState.currentState; },
    addEventListener: (_t: string, f: (d: string) => void) => {
      if (mockAppState.abonelikAtar) throw new Error("AppState yok");
      mockAppState.dinleyici = f;
      return { remove: () => { mockAppState.kaldirildi += 1; } };
    },
  },
}));
jest.mock("../../../modules/apk-installer", () => ({
  apkKur: jest.fn(), kurulumIzniVarMi: () => true, izinEkraniniAc: jest.fn(), apkKuruculVarMi: () => true,
  dosyaSha256: jest.fn(async () => ""), indirmeServisiniBaslat: jest.fn(async () => true), indirmeServisiniDurdur: jest.fn(async () => true),
}));
jest.mock("expo-keep-awake", () => ({ activateKeepAwakeAsync: jest.fn(async () => {}), deactivateKeepAwake: jest.fn(async () => {}) }));
jest.mock("expo-sharing", () => ({ __esModule: true, isAvailableAsync: async () => true, shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/", createDownloadResumable: jest.fn(), getInfoAsync: jest.fn(), deleteAsync: jest.fn(), getContentUriAsync: jest.fn(),
}));
jest.mock("expo-constants", () => ({ __esModule: true, default: { expoConfig: { android: { versionCode: 13 } } }, expoConfig: { android: { versionCode: 13 } } }));

import AsyncStorage from "@react-native-async-storage/async-storage";
import { apkIndir, _indirmeyiSifirla, type MobilSurum } from "../mobileUpdate";

const SURUM: MobilSurum = {
  version: "2.3.7", versionCode: 14, url: "https://github.com/mert61-python/pemf-update/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "", size: 1000,
};
const HEDEF = "file:///cache/pemf-vet-14.apk";
const bosalt = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };

type Deneme = { downloadAsync: () => Promise<unknown>; pauseAsync?: () => Promise<unknown> };
function dunya(denemeler: Array<(ilerle: (b: number) => void) => Deneme>) {
  let inen = false;
  let sira = 0;
  type Ilerleme = (p: { totalBytesWritten: number; totalBytesExpectedToWrite: number }) => void;
  const olustur: jest.Mock = jest.fn((_u: string, _h: string, _o: unknown, cb: Ilerleme): Deneme => {
    const d: Deneme = denemeler[sira++]((b) => cb({ totalBytesWritten: b, totalBytesExpectedToWrite: 1000 }));
    return { ...d, downloadAsync: async () => { const r = await d.downloadAsync(); inen = true; return r; } };
  });
  return {
    olustur,
    deps: {
      createDownloadResumable: olustur as never,
      getInfoAsync: (async () => (inen ? { exists: true, size: 1000 } : { exists: false })) as never,
      deleteAsync: (async () => undefined) as never,
      readDirectoryAsync: (async () => []) as never,
      devamYaz: async () => undefined,
      devamSil: async () => undefined,
      devamOku: async () => null,
    },
  };
}
const dus = (): Deneme => ({ downloadAsync: async () => { throw new Error("Network request failed"); } });
const in_ = (): Deneme => ({ downloadAsync: async () => ({ uri: HEDEF, status: 200 }) });

beforeEach(async () => {
  jest.useFakeTimers();
  _indirmeyiSifirla();
  mockAppState.currentState = "active";
  mockAppState.dinleyici = undefined;
  mockAppState.kaldirildi = 0;
  mockAppState.abonelikAtar = false;
  await AsyncStorage.clear();
});
afterEach(() => jest.useRealTimers());

it("ön planda düşen deneme 3 sn nefesten SONRA yinelenir; AppState'e abone olunmaz", async () => {
  const d = dunya([dus, in_]);
  const p = apkIndir(SURUM, undefined, d.deps);
  await bosalt();
  expect(d.olustur).toHaveBeenCalledTimes(1);
  await act(2999);
  expect(d.olustur).toHaveBeenCalledTimes(1);
  await act(1);
  await expect(p).resolves.toEqual({ ok: true, dosyaUri: HEDEF });
  expect(d.olustur).toHaveBeenCalledTimes(2);
  expect(mockAppState.dinleyici).toBeUndefined();
});

it("arka planda hak yakılmaz: etkin olana dek bekler, etkin olunca hemen yinelenir ve abonelik kaldırılır", async () => {
  mockAppState.currentState = "background";
  const d = dunya([dus, in_]);
  const p = apkIndir(SURUM, undefined, d.deps);
  await bosalt();
  await act(10 * 60 * 1000);
  expect(d.olustur).toHaveBeenCalledTimes(1);
  mockAppState.dinleyici!("inactive");
  await bosalt();
  expect(d.olustur).toHaveBeenCalledTimes(1);
  mockAppState.currentState = "active";
  mockAppState.dinleyici!("active");
  await bosalt();
  await expect(p).resolves.toEqual({ ok: true, dosyaUri: HEDEF });
  expect(d.olustur).toHaveBeenCalledTimes(2);
  expect(mockAppState.kaldirildi).toBe(1);
});

it("hiç etkin olmazsa 30 dk tavanında yine denenir; abonelik kurulamazsa beklemeden denenir", async () => {
  mockAppState.currentState = "background";
  let d = dunya([dus, in_]);
  let p = apkIndir(SURUM, undefined, d.deps);
  await bosalt();
  await act(30 * 60 * 1000 - 1);
  expect(d.olustur).toHaveBeenCalledTimes(1);
  await act(1);
  await expect(p).resolves.toMatchObject({ ok: true });
  expect(mockAppState.kaldirildi).toBe(1);

  _indirmeyiSifirla();
  mockAppState.abonelikAtar = true;
  d = dunya([dus, in_]);
  p = apkIndir(SURUM, undefined, d.deps);
  await bosalt();
  await expect(p).resolves.toMatchObject({ ok: true });
  expect(d.olustur).toHaveBeenCalledTimes(2);
});

it("tıkanma bekçisi: 90 sn bayt akmazsa pauseAsync ile düşürülür ve yinelenir; bayt aktıkça düşürülmez", async () => {
  let reddet: (e: Error) => void = () => undefined;
  const durdur = jest.fn(async () => { reddet(new Error("paused")); });
  let ilerlet: (b: number) => void = () => undefined;
  const tikali = (i: (b: number) => void): Deneme => {
    ilerlet = i;
    return { downloadAsync: () => new Promise((_c, r) => { reddet = r; }), pauseAsync: durdur };
  };
  const d = dunya([tikali, in_]);
  const p = apkIndir(SURUM, undefined, d.deps);
  await bosalt();
  for (let i = 0; i < 8; i++) { ilerlet(100 + i); await act(15_000); } // 120 sn ama bayt akıyor
  expect(durdur).not.toHaveBeenCalled();
  await act(105_000); // 90 sn+ sessizlik
  expect(durdur).toHaveBeenCalledTimes(1);
  await act(3000);
  await expect(p).resolves.toMatchObject({ ok: true });
  expect(d.olustur).toHaveBeenCalledTimes(2);
});

// KP-7 B (işlev ölçüsü): YAN bağımlılıklar reddetse de güncelleme iner — ekranı uyanık tutma (aç / kapat), ön plan indirme servisi
// (başlat / durdur), eski APK temizliği (silme) ve tıkanma bekçisinin duraklatması "kolaylık"tır; hiçbiri indirmeyi düşürmez.
it("uyanık tutma / indirme servisi / eski APK silme / duraklatma REDDETSE de indirme tamamlanır; eski APK silinmeye çalışılır", async () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const ka = require("expo-keep-awake") as { activateKeepAwakeAsync: jest.Mock; deactivateKeepAwake: jest.Mock };
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const apk = require("../../../modules/apk-installer") as { indirmeServisiniBaslat: jest.Mock; indirmeServisiniDurdur: jest.Mock };
  ka.activateKeepAwakeAsync.mockRejectedValueOnce(new Error("uyanık tutma yok"));
  ka.deactivateKeepAwake.mockRejectedValueOnce(new Error("uyanık tutma yok"));
  apk.indirmeServisiniBaslat.mockRejectedValueOnce(new Error("servis başlamadı"));
  apk.indirmeServisiniDurdur.mockRejectedValueOnce(new Error("servis durmadı"));
  let reddet: (e: Error) => void = () => undefined;
  const durdur = jest.fn(async () => {
    reddet(new Error("paused"));
    throw new Error("pauseAsync desteklenmiyor");
  });
  const tikali = (): Deneme => ({ downloadAsync: () => new Promise((_c, r) => { reddet = r; }), pauseAsync: durdur });
  const d = dunya([tikali, in_]);
  const silinen: string[] = [];
  const deps = {
    ...d.deps,
    readDirectoryAsync: (async () => ["pemf-vet-12.apk", "pemf-vet-14.apk", "baska.apk"]) as never,
    deleteAsync: (async (u: string) => {
      silinen.push(u);
      if (u.endsWith("pemf-vet-12.apk")) throw new Error("dosya kilitli");
    }) as never,
  };
  const p = apkIndir(SURUM, undefined, deps);
  await bosalt();
  await act(105_000); // tıkanma: 90 sn+ sessizlik → duraklatma (reddeder)
  expect(durdur).toHaveBeenCalledTimes(1);
  await act(3000);
  await expect(p).resolves.toEqual({ ok: true, dosyaUri: HEDEF });
  expect(silinen).toContain("file:///cache/pemf-vet-12.apk");
  expect(silinen).not.toContain("file:///cache/baska.apk");
  expect(apk.indirmeServisiniDurdur).toHaveBeenCalled();
  expect(ka.deactivateKeepAwake).toHaveBeenCalled();
});

it("sonuç dosya adresi taşımıyorsa 'indirme' hatası; bozuk devam kaydı indirmeyi düşürmez", async () => {
  const d = dunya([() => ({ downloadAsync: async () => undefined })]);
  await expect(apkIndir(SURUM, undefined, { ...d.deps, azamiYenidenDeneme: 0 })).resolves.toEqual({ ok: false, hata: "indirme" });
  _indirmeyiSifirla();
  await AsyncStorage.setItem("@pemf_apk_indirme", "{bozuk-json");
  const d2 = dunya([in_]);
  const { devamOku: _atla, ...gercekOkuyla } = d2.deps;
  void _atla;
  await expect(apkIndir(SURUM, undefined, gercekOkuyla)).resolves.toEqual({ ok: true, dosyaUri: HEDEF });
});

async function act(ms: number) {
  jest.advanceTimersByTime(ms);
  await bosalt();
}
