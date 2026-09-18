// Author: mertaygn, cglrgrkn
/**
 * [5.7a] UÇUŞTAKİ guncelle() ERTELEMEYİ OKUR (2. tur denetimi, sahip onayı 2026-08-20).
 *
 * Ölçülen kusur: kapıda "Güncelle"ye basılıp indirme sürerken "Şimdilik devam et" denirse kapı
 * açılıyor, kullanıcı uygulamada çalışmaya başlıyor; ama UÇUŞTAKİ guncelle() promise'i erteleme
 * kararından habersiz — indirme bitince Android paket yükleyicisi o anki işin ÜSTÜNE SORMADAN
 * açılıyordu (seans kapısı ayrı katman; seanssız kullanım korumasızdı).
 *
 * DÜZELTME: mobileUpdate'e ikinci bellek-içi bayrak (`kurulumunuErtele` — atlandiMi'den AYRI:
 * bandı SUSTURMAZ, yalnız otomatik yükleyici açılışını keser). guncelle() kurulumdan hemen önce
 * bayrağı okur; girişte ise TEMİZLER (açık kullanıcı niyeti — banttan "Güncelle"ye yeniden
 * dokunmak kalıcı kilide dönmemeli; "güncelleme ZORUNLU KILINAMAZ"ın ayna kuralı: erteleme de
 * KALICI ENGEL kılınamaz).
 */
jest.mock("@/services/apiClient", () => ({ apiGet: jest.fn() }));
jest.mock("@/services/mobileUpdate", () => {
  // Bayrak fonksiyonları GERÇEK: "çağrıldı mı" değil "işe yarıyor mu" sınanır.
  const gercek = jest.requireActual("@/services/mobileUpdate");
  return { ...gercek, apkIndir: jest.fn(), kurulumuBaslat: jest.fn() };
});

import { renderHook, act } from "@testing-library/react-native";

import { apiGet } from "@/services/apiClient";
import {
  apkIndir,
  kurulumuBaslat,
  kurulumunuErtele,
  kurulumErtelendiMi,
  _kurulumErtelemesiniSifirla,
} from "@/services/mobileUpdate";
import { useApkGuncelleme } from "@/hooks/useApkGuncelleme";

const mockApiGet = apiGet as jest.Mock;
const mockIndir = apkIndir as jest.Mock;
const mockKur = kurulumuBaslat as jest.Mock;

const SURUM = { version: "2.3.18", versionCode: 25, url: "https://x/y.apk", size: 1, sha256: "" } as never;

beforeEach(() => {
  mockApiGet.mockReset();
  mockIndir.mockReset();
  mockKur.mockReset();
  _kurulumErtelemesiniSifirla();
  mockApiGet.mockResolvedValue({ is_active: false, hardware_running: false });
  mockIndir.mockResolvedValue({ ok: true, dosyaUri: "file:///cache/p.apk" });
  mockKur.mockResolvedValue("acildi");
});

async function guncelle() {
  const h = renderHook(() => useApkGuncelleme(SURUM));
  await act(async () => {
    await h.result.current.guncelle();
  });
  return h;
}

it("KRİTİK [5.7a]: indirme SIRASINDA erteleme gelirse yükleyici AÇILMAZ, paket hazır bekler", async () => {
  // Gerçek sıra: guncelle() girişten geçti (temizlik koştu), indirme sürerken kapı
  // "Şimdilik devam et" ile kapatıldı → bayrak UÇUŞTA kondu.
  mockIndir.mockImplementation(async () => {
    kurulumunuErtele(25);
    return { ok: true, dosyaUri: "file:///cache/p.apk" };
  });
  const h = await guncelle();

  expect(mockKur).not.toHaveBeenCalled();
  expect(h.result.current.kurulumAcildi).toBe(false);
  expect(h.result.current.bilgi).toMatch(/ertele/i); // kullanıcı NEDENİNİ görür
  expect(h.result.current.paketHazir).toBe(true);    // paket diskte hazır — bant sunabilir
});

it("KARŞIT-KANIT: yeni bir 'Güncelle' dokunuşu ertelemeyi KALDIRIR ve kurar (kalıcı kilit yok)", async () => {
  kurulumunuErtele(25); // önceki açılış-içi erteleme duruyor
  await guncelle();     // açık kullanıcı niyeti: giriş temizler

  expect(kurulumErtelendiMi(25)).toBe(false);
  expect(mockKur).toHaveBeenCalledTimes(1);
});

it("KARŞIT-KANIT: erteleme yokken davranış AYNEN (yükleyici açılır)", async () => {
  const h = await guncelle();
  expect(mockKur).toHaveBeenCalledTimes(1);
  expect(h.result.current.paketHazir).toBe(true);
});

it("KARŞIT-KANIT: seans kapısı ertelemeden ÖNCELİKLİ kalır (tıbbi metin kaybolmaz)", async () => {
  mockApiGet.mockResolvedValue({ is_active: true });
  mockIndir.mockImplementation(async () => {
    kurulumunuErtele(25);
    return { ok: true, dosyaUri: "file:///cache/p.apk" };
  });
  const h = await guncelle();
  expect(mockKur).not.toHaveBeenCalled();
  expect(h.result.current.bilgi).toMatch(/tedavi sürüyor/);
});

it("[5.7c] paketHazir: başarılı indirmede true, düşen indirmede false", async () => {
  const h1 = await guncelle();
  expect(h1.result.current.paketHazir).toBe(true);

  mockIndir.mockResolvedValue({ ok: false, hata: "indirme" });
  const h2 = await guncelle();
  expect(h2.result.current.paketHazir).toBe(false);
});
