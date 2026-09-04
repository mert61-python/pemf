// Author: mertaygn, cglrgrkn
/**
 * DOKUNMA HEDEFİ TABANI ÖLÇEKLE KÜÇÜLMEZ  [S3 / ilkel-7, 2026-09-04 responsive denetimi]
 * =====================================================================================
 * ÖLÇÜLEN DURUM: minimumlar `rs()` ile ölçekleniyordu → 320 px telefonda SCALE 0.853 ile
 * `rs(44)=38`, `rs(46)=39`, `rs(38)=32`. Yani tam da dokunmanın en zor olduğu dar cihazda
 * hedefler WCAG/Android alt sınırının ALTINA düşüyordu (20'den fazla bileşenin kök nedeni).
 *
 * SÖZLEŞME: `touch.min ≥ 44` ve `touch.sm ≥ 40` HER cihazda; büyük ekranda büyüyebilir.
 * `touch.slopFor(gap) ≤ gap/2` — komşu hedeflerin dokunma alanları binişmez (ekranB-15).
 *
 * ⚠️ MUTASYON: `Math.max(44, rs(44))` → `rs(44)` yapılırsa 320 px satırı KIRILIR.
 */
import { tokenlariYukle } from "@/theme/__tests__/olcek";

afterEach(() => {
  jest.resetModules();
  jest.dontMock("react-native");
});

describe("touch tabanları", () => {
  it("KRİTİK: 320 px telefonda min 44, sm 40 (ölçek 0,85 aşağı çekemez)", () => {
    const { touch, rs } = tokenlariYukle({ width: 320, height: 568, os: "android" });
    expect(rs(44)).toBeLessThan(44); // ölçek gerçekten aşağı çekiyor (kanıt)
    expect(touch.min).toBeGreaterThanOrEqual(44);
    expect(touch.sm).toBeGreaterThanOrEqual(40);
  });

  it("375 px referans telefonda taban korunur", () => {
    const { touch } = tokenlariYukle({ width: 375, height: 812, os: "ios" });
    expect(touch.min).toBeGreaterThanOrEqual(44);
    expect(touch.sm).toBeGreaterThanOrEqual(40);
  });

  it("büyük ekranda taban BÜYÜYEBİLİR (tavan yok, alt sınır var)", () => {
    const { touch, rs } = tokenlariYukle({ width: 1280, height: 800, os: "web" });
    expect(touch.min).toBe(Math.max(44, rs(44)));
    expect(touch.min).toBeGreaterThanOrEqual(44);
  });

  it("slopFor: hitSlop komşu boşluğun yarısını AŞMAZ (yanlış bobin seçimi kökü)", () => {
    const { touch } = tokenlariYukle({ width: 320, height: 568, os: "android" });
    for (const gap of [0, 3, 4, 8, 12, 16]) {
      const s = touch.slopFor(gap);
      expect(s.left).toBeLessThanOrEqual(gap / 2);
      expect(s.left).toBe(s.right);
      expect(s.top).toBe(s.bottom);
      expect(s.left).toBeGreaterThanOrEqual(0);
    }
  });
});

describe("layoutMax — ekran konteyner tavanları ölçeksiz", () => {
  it("KRİTİK: tavan değerleri her cihazda AYNI (PC'de 1100 → 1430 olmuyor)", () => {
    const dar = tokenlariYukle({ width: 320, height: 568, os: "android" }).layoutMax;
    const genis = tokenlariYukle({ width: 1920, height: 1080, os: "web" }).layoutMax;
    expect(dar.icerik).toBe(1100);
    expect(genis.icerik).toBe(1100);
    expect(genis.genis).toBe(1200);
    expect(genis.aiHub).toBe(980);
  });
});

describe("MAX_FONT_SCALE — sistem yazı ölçeği tavanı (sahip kararı: 1,2)", () => {
  it("1,2 ve erişilebilirliği tamamen kapatmaz (>1)", () => {
    const { MAX_FONT_SCALE } = tokenlariYukle({ width: 375, height: 812, os: "android" });
    expect(MAX_FONT_SCALE).toBe(1.2);
    expect(MAX_FONT_SCALE).toBeGreaterThan(1);
  });
});
