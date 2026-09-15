// Author: mertaygn
/**
 * KPI GRAFİK EKSENİ — "Son 7 Gün — Seans Sayısı" (sahip bildirimi 2026-09-12).
 * ===========================================================================
 * "bu grafiği daha belirgin ve tasarım olarak daha güzel hale getir."
 *
 * ⚠️ EN GÖZE BATAN KUSUR TASARIM DEĞİL, ANLAMDI: y ekseni "11.00 · 8.25 · 5.50 · 2.75 · 0.00"
 * yazıyordu (sahibin ekran görüntüsü). Seans sayısı TAM SAYIDIR — "8,25 seans" diye bir birim
 * yoktur. Ekseni okuyan ya çeyrek seans diye bir şey olduğunu sanar ya da okumayı bırakır.
 *
 * `react-native-chart-kit` bölüt sayısını sabit 4 alır ve etiketleri `max/4` adımıyla üretir:
 * 11 sessizce 2,75'lik adımlara bölünür. Bölüt sayısı tepe değeri TAM BÖLERSE her etiket
 * tam sayı olur.
 */
import { barBolumSayisi, eksenBolumSayisi } from "@/utils/kpiGrafik";

// ============================================================================
// 1. ⚠️ ASIL KAPI — HER EKSEN ETİKETİ TAM SAYI
// ============================================================================

/** chart-kit'in ürettiği etiketler: i * (max / bolut), i = 0..bolut. */
function eksenEtiketleri(enBuyuk: number): number[] {
  const bolut = eksenBolumSayisi(enBuyuk);
  return Array.from({ length: bolut + 1 }, (_, i) => (i * enBuyuk) / bolut);
}

test("KRITIK: eksen etiketlerinin HEPSI TAM SAYI (8.25 seans yok)", () => {
  // MUTASYON: `eksenBolumSayisi`yi `() => 4` yap (chart-kit varsayılanı) → KIRMIZI
  // (11 için 2.75 · 5.5 · 8.25 çıkar — sahibin ekran görüntüsündeki tam değerler).
  for (let enBuyuk = 0; enBuyuk <= 60; enBuyuk++) {
    for (const etiket of eksenEtiketleri(enBuyuk)) {
      expect(Number.isInteger(etiket)).toBe(true);
    }
  }
});

test("KRITIK: sahibin ekranindaki 11 degeri artik ONDALIK uretmiyor", () => {
  // Ekran görüntüsündeki tam vaka: tepe 11.
  expect(eksenEtiketleri(11)).toEqual([0, 11]);
});

test("bolunebilen tepe degerlerinde IZGARA ZENGIN kalir", () => {
  // ⚠️ KARŞIT KANIT: tam sayı uğruna her grafiği tek çizgiye düşürmek, okunaklılığı
  // düzeltirken bilgiyi yok ederdi. Bölünebiliyorsa çok çizgi tercih edilir.
  expect(eksenBolumSayisi(20)).toBe(5); // 0 · 4 · 8 · 12 · 16 · 20
  expect(eksenBolumSayisi(12)).toBe(4); // 0 · 3 · 6 · 9 · 12
  expect(eksenBolumSayisi(9)).toBe(3);
  expect(eksenBolumSayisi(10)).toBe(5);
});

test("KRITIK: en cok 5 bolut (izgara kalabaliklasmasin)", () => {
  for (let n = 0; n <= 200; n++) {
    expect(eksenBolumSayisi(n)).toBeLessThanOrEqual(5);
    expect(eksenBolumSayisi(n)).toBeGreaterThanOrEqual(1);
  }
});

// ============================================================================
// 2. BOŞ / BOZUK VERİ — GRAFİK ÇÖKMEZ, ÖLÇEK UYDURMAZ
// ============================================================================

test("KRITIK: BOS veride olcek UYDURULMAZ", () => {
  // ⚠️ Veri yokken 4 ızgara çizgisi çizmek, olmayan bir ölçeği varmış gibi göstermektir.
  expect(barBolumSayisi([])).toBe(1);
  expect(barBolumSayisi(undefined)).toBe(1);
  expect(barBolumSayisi([0, 0, 0, 0, 0, 0, 0])).toBe(1);
});

test("bozuk sayilar COKERTMEZ (NaN/null/metin)", () => {
  // Backend `count` alanını null/metin gönderirse grafik NaN ölçekle bozulurdu.
  expect(barBolumSayisi([NaN, 12, 3] as number[])).toBe(4);
  expect(barBolumSayisi([null as unknown as number, 20])).toBe(5);
  expect(eksenBolumSayisi(NaN)).toBe(1);
  expect(eksenBolumSayisi(-5)).toBe(1);
  expect(eksenBolumSayisi(2.7)).toBe(2); // tam sayıya indirilir
});

test("KRITIK: bolut sayisi veri dizisinin TEPESINDEN turetilir", () => {
  // MUTASYON: `reduce(Math.max)` yerine `veri[0]` kullan → KIRMIZI.
  expect(barBolumSayisi([1, 0, 20, 3])).toBe(eksenBolumSayisi(20));
});

// ============================================================================
// 3. ⚠️ KAYNAK ÇIPASI NEREDE
// ============================================================================
//
// Ekranın bu hesabı GERÇEKTEN kullandığını ölçen çıpalar `tests/test_kpi_grafik_kapisi.py`
// dosyasındadır.
//
// ⚠️ NEDEN BURADA DEĞİL — ÖLÇÜLDÜ (2026-09-12): çıpalar önce burada, düz
// `src.includes("decimalPlaces: 0")` biçiminde yazılmıştı ve MUTASYONDA YEŞİL KALDI:
// o ifadeler ekranın AÇIKLAMA YORUMLARINDA da geçiyordu, yani kapı kodu değil kendi
// yorumumu ölçüyordu. Bu deponun "yorum kapıyı kandırdı" hatasının ALTINCI tekrarı.
// Python tarafında `c_soyucu.c_soy` yorumları söküyor; çıpa oraya taşındı.
