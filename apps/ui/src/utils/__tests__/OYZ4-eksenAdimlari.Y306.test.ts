// Author: mertaygn, cglrgrkn
/**
 * Y306 (sahip 19-11 tezgâh denemesi 4a): seans detayı grafiğinde dar aralıkta eksen etiketi yineleniyordu ("1.35" iki kez) ve dakika
 * ekseni 0 / 2 / 5 / 7 / 10 düzensizdi. SÖZLEŞME (`eksenAdimlari`): adım 1 / 2 / 5 × 10^k; sınırlar adımın katı ve veriyi kapsar;
 * etiket basamağı adımdan (en az istenen) → `basamak`a yuvarlanan komşu etiketler FARKLI.
 */
import { eksenAdimlari } from "@/utils/eksenAdimlari";

const metinler = (e: ReturnType<typeof eksenAdimlari>) => e.degerler.map((v) => v.toFixed(e.basamak));

it("KRİTİK: tezgâhtaki dar MLX aralığı (1,35–1,38 mT, 2 basamak) → 1,35 / 1,36 / 1,37 / 1,38 — yineleme YOK", () => {
  const e = eksenAdimlari(1.351, 1.379, 4, 2);
  expect(metinler(e)).toEqual(["1.35", "1.36", "1.37", "1.38"]);
  expect(e.min).toBeLessThanOrEqual(1.351);
  expect(e.max).toBeGreaterThanOrEqual(1.379);
});

it("KRİTİK: dakika ekseni düzenli adımlar (10 dk → 0 / 2 / 4 / 6 / 8 / 10; 6 dk → 0 / 2 / 4 / 6)", () => {
  expect(eksenAdimlari(0, 10, 5).degerler).toEqual([0, 2, 4, 6, 8, 10]);
  expect(eksenAdimlari(0, 5.95, 5).degerler).toEqual([0, 2, 4, 6]);
  const kisa = eksenAdimlari(0, 0.5, 5);
  expect(kisa.basamak).toBe(1);
  expect(metinler(kisa)).toEqual(["0.0", "0.1", "0.2", "0.3", "0.4", "0.5"]);
});

it("adım 1 / 2 / 5 × 10^k, sınırlar katı; en az basamak korunur; eşit / ters / geçersiz aralık", () => {
  const e = eksenAdimlari(0.4, 1.18, 4, 2);
  expect(e.adim).toBeCloseTo(0.2, 12);
  expect(metinler(e)).toEqual(["0.40", "0.60", "0.80", "1.00", "1.20"]);
  expect(metinler(eksenAdimlari(31, 31, 4, 1))).toEqual(["30.0", "30.5", "31.0", "31.5", "32.0"]);
  expect(eksenAdimlari(5, 1).degerler).toEqual(eksenAdimlari(1, 5).degerler);
  expect(eksenAdimlari(Number.NaN, Number.NaN).degerler.length).toBeGreaterThan(1);
  expect(eksenAdimlari(0, 7, 0).adim).toBe(10); // azami 0 → 1 bölme
});

it("KRİTİK özellik: 500 rastgele aralıkta etiketler YİNELENMEZ, veri kapsanır, adım düzgün, bölme ≤ 2 × azami", () => {
  let tohum = 7;
  const r = () => ((tohum = (tohum * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 500; i++) {
    const a = (r() - 0.5) * 10 ** Math.floor(r() * 6 - 2);
    const b = a + r() * 10 ** Math.floor(r() * 6 - 3) + 1e-6;
    const enAz = Math.floor(r() * 3);
    const e = eksenAdimlari(a, b, 4, enAz);
    const m = metinler(e);
    expect(new Set(m).size).toBe(m.length);
    expect(e.min).toBeLessThanOrEqual(a + 1e-9);
    expect(e.max).toBeGreaterThanOrEqual(b - 1e-9);
    for (const s of [e.min, e.max]) expect(Math.abs(s / e.adim - Math.round(s / e.adim))).toBeLessThan(1e-6); // sınırlar adımın KATI
    const oran = e.adim / 10 ** Math.floor(Math.log10(e.adim) + 1e-9);
    expect([1, 2, 5].some((k) => Math.abs(oran - k) < 1e-6)).toBe(true);
    expect(e.degerler.length - 1).toBeLessThanOrEqual(8);
    expect(e.basamak).toBeGreaterThanOrEqual(enAz);
  }
});
