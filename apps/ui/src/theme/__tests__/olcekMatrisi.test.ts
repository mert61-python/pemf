// Author: mertaygn, cglrgrkn
/**
 * ÖLÇEK MATRİSİ — telefon değişmezliği + büyük ekran tavanı
 * [S1, 2026-09-04 responsive denetimi · sahip kararı: büyük ekran tavanı %110]
 * =========================================================================
 * ÖLÇÜLEN DURUM: tek tavan (1,30) vardı; kısa kenarı 488 px'i geçen HER yüzey (tablet, WebView2
 * penceresi, LAN tarayıcısı) ona yapışıyordu → kenar çubuğu 322 px, gövde 17 px, maxWidth 1430 px.
 *
 * SÖZLEŞMENİN İKİ YARISI:
 *  1. TELEFON DEĞİŞMEZLİĞİ — native kısa kenar < 600 px'te formül BİREBİR eski (APK'da sıfır fark).
 *     Bu, "önce/sonra ekran görüntüsü piksel-eş" kanıtının test karşılığıdır.
 *  2. BÜYÜK EKRAN TAVANI — tablet/PC/LAN tarayıcısında en fazla 1,10.
 *
 * ⚠️ MUTASYON: `_buyukEkran` dalı silinirse (tek tavan 1,30'a dönülürse) tablet/PC satırları KIRILIR;
 * telefon tavanı 1,10'a çekilirse "430 px telefon" satırı KIRILIR.
 */
import { tokenlariYukle } from "@/theme/__tests__/olcek";

afterEach(() => {
  jest.resetModules();
  jest.dontMock("react-native");
});

/** Eski (denetim öncesi) formül — telefon değişmezliğinin referansı. */
function eskiOlcek(kisaKenar: number): number {
  return Math.min(Math.max(kisaKenar / 375, 0.85), 1.3);
}

describe("ölçek — telefon DEĞİŞMEZLİĞİ (native kısa kenar < 600)", () => {
  const telefonlar: [string, number, number][] = [
    ["dar telefon", 320, 568],
    ["referans telefon", 375, 812],
    ["büyük telefon", 430, 932],
    ["phablet (sınır altı)", 599, 900],
  ];
  it.each(telefonlar)("%s (%ix%i) eski formülle AYNI", (_ad, w, h) => {
    const { OLCEK } = tokenlariYukle({ width: w, height: h, os: "android" });
    expect(OLCEK).toBeCloseTo(eskiOlcek(Math.min(w, h)), 5);
  });

  it("KRİTİK: 430 px telefon hâlâ 1,3'e kadar büyüyebilir (tavan telefona uygulanmaz)", () => {
    const { OLCEK } = tokenlariYukle({ width: 430, height: 932, os: "android" });
    expect(OLCEK).toBeGreaterThan(1.1);
  });
});

describe("ölçek — büyük ekran tavanı (%110)", () => {
  const buyukler: [string, number, number, "android" | "web"][] = [
    ["tablet dikey", 768, 1024, "android"],
    ["tablet yatay", 1024, 768, "android"],
    ["native sınır (600)", 600, 900, "android"],
    ["PC penceresi (launcher min)", 700, 540, "web"],
    ["PC 1366@%150", 911, 512, "web"],
    ["PC geniş", 1920, 1080, "web"],
  ];
  it.each(buyukler)("%s (%ix%i, %s) → tavan 1,10", (_ad, w, h, os) => {
    const { OLCEK, OLCEK_TAVAN_BUYUK_EKRAN } = tokenlariYukle({ width: w, height: h, os });
    expect(OLCEK).toBe(OLCEK_TAVAN_BUYUK_EKRAN);
    expect(OLCEK).toBe(1.1);
  });

  it("KRİTİK: telefon TARAYICISI (LAN, kısa kenar < 480) telefon formülünde kalır", () => {
    const { OLCEK } = tokenlariYukle({ width: 390, height: 844, os: "web" });
    expect(OLCEK).toBeCloseTo(eskiOlcek(390), 5);
    expect(OLCEK).toBeGreaterThan(1.0);
  });
});

describe("ölçek — türetilmiş boyutlar", () => {
  it("PC'de kenar çubuğu artık %30 büyümüyor (ölçeksiz sabit) ve boşluklar ölçülü", () => {
    const pc = tokenlariYukle({ width: 1920, height: 1080, os: "web" });
    expect(pc.spacing.xl).toBe(Math.round(24 * 1.1)); // 31 → 26
    expect(pc.typography.body).toBeLessThanOrEqual(16); // 17 → 15
  });

  it("dokunma tabanı tavandan BAĞIMSIZ olarak 44'ün altına inmez", () => {
    for (const [w, h, os] of [
      [320, 568, "android"],
      [768, 1024, "android"],
      [1920, 1080, "web"],
    ] as [number, number, "android" | "web"][]) {
      const { touch } = tokenlariYukle({ width: w, height: h, os });
      expect(touch.min).toBeGreaterThanOrEqual(44);
    }
  });
});
