// Author: mertaygn, cglrgrkn
/**
 * useStageHeight — görüntü sahnesi yüksekliği  [S1 adım 7 / aihub-10, 2026-09-04 denetimi]
 * =======================================================================================
 * ÖLÇÜLEN DURUM: AI Hub önizleme kutusu / ısı haritası / Scratch sahnesi SABİT `rs(300)` idi.
 * Ölçek açılışta bir kez hesaplandığından PC'de kutu her zaman 390 px çıkıyordu; launcher asgari
 * penceresinde (700×540) kutu görünür alanın tamamını yiyor, "Analiz Et" düğmesi kaydırmadan
 * görünmüyordu. Yatay telefonda (yükseklik 360-430) kutu ekrandan taşıyordu.
 *
 * SÖZLEŞME: clamp(yükseklik × oran ; rs(180) ; rs(300)); kısa ekranda oran 0,45 → 0,40.
 *
 * ⚠️ MUTASYON: tavan (`Math.min`) kaldırılırsa 1080 px satırı; taban (`Math.max`) kaldırılırsa
 * yatay telefon satırı; kısa-ekran dalı silinirse 5. vaka KIRILIR.
 */
import { cihaziKur } from "@/theme/__tests__/olcek";

afterEach(() => {
  jest.resetModules();
  jest.dontMock("react-native");
});

/** Hook'u verilen cihazda taze yükleyip ölçer (RTL değil: resetModules sonrası kanca çakışır). */
function olc(width: number, height: number, os: "ios" | "android" | "web" = "web") {
  cihaziKur({ width, height, os });
  /* eslint-disable @typescript-eslint/no-require-imports */
  const React = require("react");
  const TestRenderer = require("react-test-renderer");
  const mod = require("@/hooks/useStageHeight") as typeof import("@/hooks/useStageHeight");
  const { rs } = require("@/theme/tokens") as typeof import("@/theme/tokens");
  /* eslint-enable @typescript-eslint/no-require-imports */
  const tut: { deger?: number } = {};
  function Sonda() {
    tut.deger = mod.useStageHeight();
    return null;
  }
  TestRenderer.act(() => {
    TestRenderer.create(React.createElement(Sonda));
  });
  if (tut.deger === undefined) throw new Error("hook okunamadı");
  return { h: tut.deger, tavan: rs(mod.SAHNE_TAVAN), taban: rs(mod.SAHNE_TABAN) };
}

describe("sahne yüksekliği", () => {
  it("telefon dikeyde eski davranış korunur (tavana yapışır)", () => {
    const { h, tavan } = olc(390, 844, "android");
    expect(h).toBe(tavan);
  });

  it("KRİTİK: launcher asgari penceresinde (700×540) kutu daralır", () => {
    const { h, tavan } = olc(700, 540);
    expect(h).toBeLessThan(tavan);
    expect(h).toBe(Math.round(540 * 0.45));
  });

  it("KRİTİK: yatay telefonda taban altına inmez ama küçülür", () => {
    const { h, tavan, taban } = olc(926, 428, "android");
    expect(h).toBeGreaterThanOrEqual(taban);
    expect(h).toBeLessThan(tavan);
  });

  it("geniş PC'de tavan aşılmaz (1080 px yüksekliğin %45'i 486)", () => {
    const { h, tavan } = olc(1920, 1080);
    expect(h).toBe(tavan);
  });

  it("KRİTİK: kısa ekranda oran 0,45 yerine 0,40", () => {
    // 480 px yükseklik SHORT_HEIGHT (500) altında → 0,40 çarpanı; taban da bunun altında olmalı ki
    // farkı gerçekten oran belirlesin.
    const { h, taban } = olc(1024, 480);
    expect(h).toBe(Math.max(taban, Math.round(480 * 0.4)));
    expect(h).toBeLessThan(Math.round(480 * 0.45));
  });
});
