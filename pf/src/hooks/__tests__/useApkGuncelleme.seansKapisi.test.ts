// Author: mertaygn, cglrgrkn
/**
 * 🔴 KIRMIZI ÇİZGİ (TIBBİ GÜVENLİK) — SÜREN SEANSTA KURULUM EKRANI AÇILMAZ.
 *
 * DENETİM BULGUSU (2026-08-17). `MobileUpdateBanner` süren seansta `return null` ediyordu, ama
 * `return null` bileşeni UNMOUNT ETMEZ ve uçuştaki `guncelle()` promise'i sürüyordu. İndirme
 * bittiğinde `kurulumuBaslat` çalışıyor ve Android paket yükleyicisi **bobinler hastanın üzerindeyken
 * operatörün seans ekranının üstüne tam ekran açılıyordu**. Onaylanırsa uygulama öldürülüp yeniden
 * kuruluyor → telefon kumandası seansın ortasında kayboluyordu.
 *
 * Düşen testle ölçüldü: seans başlatılıp bant gizlendikten sonra indirme bitirilince
 * `kurulumuBaslat` 1 kez çağrılıyordu (beklenen 0).
 *
 * ⚠️ NİYET KANITI: `MobileUpdateBanner` başlığı korumanın gerekçesini bizzat yazıyor —
 * "kurulum uygulamayı yeniden başlatır ve bobinler hastanın üzerindeyken operatörün ekranını
 * elinden almak kabul edilemez". Yani değişmez **teklifi gizlemek değil, kurulumun ekranı
 * almasını engellemek**. Aynı ilke `PemfApp.tsx`'te doğru uygulanmış (seans sürerken hareketsizlik
 * kilidi ERTELENİR).
 *
 * ⚠️ NEDEN KANCADA (iki yüzey birden): kapı `MobileUpdateGate` `<Stack/>`in ve `LiveDataProvider`ın
 * ÜSTÜNDE durur → context'ten `seansAktif`e erişemez. Kanca cihazın kendisine (`/session/active`)
 * sorduğu için AÇILIŞ KAPISI ve BANT aynı korumayı paylaşır. Bandın kendi `seansAktif` kapısı
 * (görünürlük) KALIR; bu ondan bağımsız ikinci bir katmandır.
 *
 * ⚠️ BİLİNÇLİ FAIL-OPEN: seans durumu ÖĞRENİLEMEZSE (cihaza ulaşılamıyor / farklı ağ) kurulum
 * ENGELLENMEZ. Aksi hâli, tıbbi bir cihazın uzaktan kumandasını KALICI güncellenemez yapardı —
 * sahibin açıkça yasakladığı sonuç ("güncelleme ZORUNLU KILINAMAZ", mobil 2.3.16 kararı). Yalnız
 * POZİTİF kanıt (`is_active: true`) kurulumu erteler. Karşı-kanıt testleri aşağıda.
 */
jest.mock("@/services/apiClient", () => ({ apiGet: jest.fn() }));
jest.mock("@/services/mobileUpdate", () => ({
  apkIndir: jest.fn(),
  kurulumuBaslat: jest.fn(),
  // [5.7a] kancanın erteleme kapısı — bu dosyanın konusu değil, nötr stub (erteleme yok):
  kurulumErtelendiMi: () => false,
  kurulumErtelemesiniKaldir: () => {},
}));

import { renderHook, act } from "@testing-library/react-native";
import { apiGet } from "@/services/apiClient";
import { apkIndir, kurulumuBaslat } from "@/services/mobileUpdate";
import { useApkGuncelleme } from "@/hooks/useApkGuncelleme";

const mockApiGet = apiGet as jest.Mock;
const mockIndir = apkIndir as jest.Mock;
const mockKur = kurulumuBaslat as jest.Mock;

const SURUM = { version: "2.3.18", versionCode: 25, url: "https://x/y.apk", size: 1, sha256: "" } as never;

beforeEach(() => {
  mockApiGet.mockReset();
  mockIndir.mockReset();
  mockKur.mockReset();
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

it("KRİTİK: seans SÜRÜYORSA kurulum ekranı AÇILMAZ", async () => {
  mockApiGet.mockResolvedValue({ is_active: true });
  const h = await guncelle();

  expect(mockIndir).toHaveBeenCalledTimes(1); // indirme YAPILIR (paket hazır beklesin)
  expect(mockKur).not.toHaveBeenCalled();     // ama yükleyici AÇILMAZ
  expect(h.result.current.kurulumAcildi).toBe(false);
});

it("KRİTİK [2.tur 2.1]: SEANSSIZ çalışan bobin varken de kurulum ekranı AÇILMAZ", async () => {
  // Bobinler seans olmadan da sürülür (CoilParameterPanel → /coil/{id}/control, is_active'e
  // dokunmaz; ControlScreen bunu 'hardwareRunningOutOfSession' banner'ıyla ayrı durum sayar).
  // Kapı yalnız is_active'e bakarsa, bobinler hayvanın üzerindeyken yükleyici yine açılır —
  // 1. tur düzeltmesinin 'seanssız bobin' varyantı. Backend artık hardware_running alanı taşıyor.
  mockApiGet.mockResolvedValue({ is_active: false, hardware_running: true });
  const h = await guncelle();

  expect(mockIndir).toHaveBeenCalledTimes(1); // indirme yine YAPILIR (paket hazır beklesin)
  expect(mockKur).not.toHaveBeenCalled();
  expect(h.result.current.kurulumAcildi).toBe(false);
});

it("KARŞIT-KANIT [2.tur 2.1]: seans yok + bobin yok → kurulum AÇILIR", async () => {
  mockApiGet.mockResolvedValue({ is_active: false, hardware_running: false });
  await guncelle();

  expect(mockKur).toHaveBeenCalledTimes(1);
});

it("KARŞIT-KANIT [2.tur 2.1]: ESKİ backend (alan yok) → fail-open korunur, kurulum AÇILIR", async () => {
  // Geriye uyum: sahadaki eski backend hardware_running taşımaz; yalnız POZİTİF kanıt erteler
  // (bilinçli fail-open — 'güncelleme ZORUNLU KILINAMAZ' sahip kararı bozulmamalı).
  mockApiGet.mockResolvedValue({ is_active: false });
  await guncelle();

  expect(mockKur).toHaveBeenCalledTimes(1);
});

it("KRİTİK: ertelendiğinde operatöre SEBEP söylenir (sessiz hiçbir şey olmaması yok)", async () => {
  mockApiGet.mockResolvedValue({ is_active: true });
  const h = await guncelle();

  const mesaj = `${h.result.current.bilgi} ${h.result.current.hata}`;
  expect(mesaj).toMatch(/seans/i);
  // Paket diskte hazır: kullanıcı seans bitince tek dokunuşla kurabilir → bunu SÖYLE.
  expect(mesaj).toMatch(/indirildi|hazır/i);
});

it("karşı-kanıt: seans YOKSA kurulum normal şekilde açılır", async () => {
  mockApiGet.mockResolvedValue({ is_active: false });
  const h = await guncelle();

  expect(mockKur).toHaveBeenCalledTimes(1);
  expect(h.result.current.kurulumAcildi).toBe(true);
});

it("karşı-kanıt: seans durumu ÖĞRENİLEMEZSE kurulum ENGELLENMEZ (fail-open)", async () => {
  // Cihaza ulaşılamıyor → apiGet çağıranın fallback'ini döner. Fail-closed olsaydı farklı ağdaki
  // bir telefon bir daha ASLA güncellenemezdi (sahibin yasakladığı kalıcı kilit).
  mockApiGet.mockResolvedValue(null);
  const h = await guncelle();

  expect(mockKur).toHaveBeenCalledTimes(1);
  expect(h.result.current.kurulumAcildi).toBe(true);
});

it("karşı-kanıt: seans sorgusu PATLASA bile kurulum engellenmez", async () => {
  mockApiGet.mockRejectedValue(new Error("ağ"));
  const h = await guncelle();

  expect(mockKur).toHaveBeenCalledTimes(1);
});

it("karşı-kanıt: seans kapısı İNDİRMEYİ engellemez (paket hazır beklemeli)", async () => {
  mockApiGet.mockResolvedValue({ is_active: true });
  await guncelle();

  // İndirme bittiği için sonraki denemede hazır-dosya hızlı yolu çalışır; 128 MB tekrar inmez.
  expect(mockIndir).toHaveBeenCalledTimes(1);
});

it("seans sorgusu İNDİRME BİTTİKTEN sonra yapılır (yarış: indirme dakikalar sürebilir)", async () => {
  // Sıra kritik: indirme başlarken seans yoktu ama BİTERKEN olabilir. Kapı, kurulumdan HEMEN
  // ÖNCE sorulmalı — başlangıçtaki duruma güvenmek bulgunun kendisiydi.
  const sira: string[] = [];
  mockIndir.mockImplementation(async () => {
    sira.push("indirme");
    return { ok: true, dosyaUri: "file:///cache/p.apk" };
  });
  mockApiGet.mockImplementation(async () => {
    sira.push("seans-sorgusu");
    return { is_active: true };
  });
  await guncelle();

  expect(sira).toEqual(["indirme", "seans-sorgusu"]);
});
