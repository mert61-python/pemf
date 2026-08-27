// Author: mertaygn, cglrgrkn
/**
 * İNDİRME KALAN-SÜRESİ (ETA) — 2026-08-27 sahip isteği: "mobil güncelleme indirilirken de
 * anlık internet hızına göre kalan süre görünsün" (launcher indirme kartının mobil eşi).
 *
 * Kilitlenenler:
 *  1) etaMetni biçimi: sn / dk+sn / sa+dk; geçersiz girdi → boş.
 *  2) Kanca: ilerleme örneklerinden ANLIK hız → kalan süre; ilk saniyelerde (ölçüm gürültülü)
 *     GÖSTERİLMEZ; indirme bitince/düşünce temizlenir.
 *  3) KARŞIT: hız ölçülemiyorsa (tek örnek / ilerleme yok) eta boş kalır — "NaN sn" basılmaz.
 */
jest.mock("@/services/apiClient", () => ({ apiGet: jest.fn().mockResolvedValue(null) }));
jest.mock("@/services/mobileUpdate", () => ({
  apkIndir: jest.fn(),
  kurulumuBaslat: jest.fn().mockResolvedValue("acildi"),
  kurulumErtelendiMi: () => false,
  kurulumErtelemesiniKaldir: () => {},
}));

import { act, renderHook } from "@testing-library/react-native";

import { etaMetni, useApkGuncelleme } from "@/hooks/useApkGuncelleme";
import { apkIndir } from "@/services/mobileUpdate";

const mockIndir = apkIndir as jest.Mock;

const SURUM = {
  version: "2.3.26", versionCode: 33,
  url: "https://github.com/mert61-python/pemf-update/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "", size: 100_000_000, // 100 MB — hesap elde doğrulanabilir olsun
} as never;

describe("etaMetni", () => {
  it("saniye / dakika / saat biçimleri", () => {
    expect(etaMetni(4)).toBe("~4 sn kaldı");
    expect(etaMetni(0.2)).toBe("~1 sn kaldı"); // 0 sn "bitti" yanılgısı vermez
    expect(etaMetni(200)).toBe("~3 dk 20 sn kaldı");
    expect(etaMetni(3_900)).toBe("~1 sa 5 dk kaldı");
  });
  it("KARŞIT: geçersiz girdi boş döner (NaN/negatif ekrana sızmaz)", () => {
    expect(etaMetni(Number.NaN)).toBe("");
    expect(etaMetni(-5)).toBe("");
    expect(etaMetni(Number.POSITIVE_INFINITY)).toBe("");
  });
});

describe("useApkGuncelleme eta", () => {
  beforeEach(() => {
    jest.useFakeTimers({ now: 1_000_000 });
    mockIndir.mockReset();
  });
  afterEach(() => jest.useRealTimers());

  it("KRITIK: anlık hızdan kalan süre — 10 sn'de %50 inen 100 MB için '~10 sn kaldı'", async () => {
    // apkIndir'i elde tut: ilerleme geri çağrılarını sahte saatle biz süreriz.
    let ilerleme: (o: number) => void = () => {};
    let coz: (v: unknown) => void = () => {};
    mockIndir.mockImplementation((_s: never, cb: (o: number) => void) => {
      ilerleme = cb;
      return new Promise((r) => { coz = r; });
    });

    const h = renderHook(() => useApkGuncelleme(SURUM));
    let guncelleSozu!: Promise<void>;
    await act(async () => { guncelleSozu = h.result.current.guncelle(); });

    // t=0: ilk örnek → henüz hız yok → eta BOŞ (KARŞIT-kanıt: tek örnekle uydurma sayı basılmaz)
    await act(async () => { ilerleme(0); });
    expect(h.result.current.eta).toBe("");

    // t=+10 sn: %50 → hız 5 MB/sn → kalan 50 MB → ~10 sn
    await act(async () => {
      jest.setSystemTime(1_000_000 + 10_000);
      ilerleme(0.5);
    });
    expect(h.result.current.eta).toBe("~10 sn kaldı");
    expect(h.result.current.oran).toBe(0.5);

    // indirme biter → eta TEMİZLENİR (bayat "kaldı" metni ekranda asılı kalmaz)
    await act(async () => {
      coz({ ok: true, dosyaUri: "file:///cache/p.apk" });
      await guncelleSozu;
    });
    expect(h.result.current.eta).toBe("");
    expect(h.result.current.oran).toBeNull();
  });

  it("KARŞIT: ilk ~3 sn içinde gösterilmez (gürültülü ölçüm) — sonra görünür", async () => {
    let ilerleme: (o: number) => void = () => {};
    mockIndir.mockImplementation((_s: never, cb: (o: number) => void) => {
      ilerleme = cb;
      return new Promise(() => {}); // hiç bitmesin — yalnız akışı ölçüyoruz
    });
    const h = renderHook(() => useApkGuncelleme(SURUM));
    await act(async () => { void h.result.current.guncelle(); });

    await act(async () => { ilerleme(0.01); });
    await act(async () => {
      jest.setSystemTime(1_000_000 + 1_000); // yalnız 1 sn geçti
      ilerleme(0.05);
    });
    expect(h.result.current.eta).toBe(""); // ETA_ASGARI_SN dolmadan gösterme

    await act(async () => {
      jest.setSystemTime(1_000_000 + 5_000);
      ilerleme(0.25);
    });
    expect(h.result.current.eta).not.toBe(""); // artık ölçülebilir
    expect(h.result.current.eta).toMatch(/kaldı$/);
  });
});
