// Author: mertaygn, cglrgrkn
/**
 * BOBİN SEÇİCİ — DOKUNMA ALANLARI BİNİŞMEZ  [S3 adım 6 / ekranB-15, 2026-09-04 denetimi]
 * =====================================================================================
 * ⚠️ HASTA GÜVENLİĞİ İLGİLİ: seçici, seansa hangi bobinlerin gireceğini belirler. Kutular
 * `rs(40)` (320 px'te 34 px), ızgara boşluğu `spacing.xs` (4 px), hitSlop ise HER YÖNDE 8 px'ti.
 * RN hit-test'inde iki komşu kutunun genişletilmiş alanları çakışıyor ve aradaki boşluğa yapılan
 * dokunuş SAĞDAKİ kardeşe gidiyordu → operatör 3'e basıp 4'ü seçebiliyordu.
 *
 * SÖZLEŞME:
 *  1. Kutu ölçekten bağımsız en az 44 px (dar telefonda da).
 *  2. hitSlop ≤ ızgara boşluğu / 2 → genişletilmiş alanlar BİNİŞMEZ.
 *  3. Seçili durum yalnız renkle değil, çerçeve kalınlığıyla da anlatılır.
 *
 * ⚠️ MUTASYON: hitSlop sabit 8'e döndürülürse 2. vaka; kutu `rs(40)`'a döndürülürse 1. vaka KIRILIR.
 */
import { cihaziKur } from "@/theme/__tests__/olcek";

afterEach(() => {
  jest.resetModules();
  jest.dontMock("react-native");
});

type Dugum = { props: Record<string, unknown> };

/** Dar telefonda seçici düğmesinin stilini ve hitSlop'unu ölç. */
function olc(width = 320, height = 568) {
  cihaziKur({ width, height, os: "android" });
  /* eslint-disable @typescript-eslint/no-require-imports */
  const { spacing, touch } = require("@/theme/tokens") as typeof import("@/theme/tokens");
  /* eslint-enable @typescript-eslint/no-require-imports */
  return { spacing, touch };
}

describe("bobin seçici dokunma alanı", () => {
  it("KRİTİK: kutu dar telefonda bile 44 px tabanının altına inmez", () => {
    const { touch } = olc();
    expect(touch.min).toBeGreaterThanOrEqual(44);
  });

  it("KRİTİK: hitSlop ızgara boşluğunun YARISINI aşmaz (komşu bobine dokunulmaz)", () => {
    const { spacing, touch } = olc();
    const slop = touch.slopFor(spacing.sm);
    expect(slop.left * 2).toBeLessThanOrEqual(spacing.sm);
    expect(slop.right * 2).toBeLessThanOrEqual(spacing.sm);
    expect(slop.left).toBeGreaterThan(0); // tampon tamamen kaybolmadı
  });

  it("tablette de kural bozulmaz (boşluk büyürken tampon da büyür)", () => {
    const { spacing, touch } = olc(768, 1024);
    const slop = touch.slopFor(spacing.sm);
    expect(slop.left * 2).toBeLessThanOrEqual(spacing.sm);
  });

  it("KRİTİK: kaynak sözleşmesi — seçici sabit hitSlop kullanmaz", () => {
    /* eslint-disable @typescript-eslint/no-require-imports */
    const fs = require("fs");
    const path = require("path");
    /* eslint-enable @typescript-eslint/no-require-imports */
    const src = fs.readFileSync(path.join(__dirname, "..", "ControlScreen.tsx"), "utf8") as string;
    const i = src.indexOf("coilSelectorBtn,");
    expect(i).toBeGreaterThan(-1);
    const pencere = src.slice(i, i + 1200);
    expect(pencere).toContain("touch.slopFor(spacing.sm)");
    expect(pencere).not.toContain("hitSlop={{ top: 8");
  });

  it("seçili durum çerçeve kalınlığıyla da anlatılır (renk körlüğü)", () => {
    /* eslint-disable @typescript-eslint/no-require-imports */
    const fs = require("fs");
    const path = require("path");
    /* eslint-enable @typescript-eslint/no-require-imports */
    const src = fs.readFileSync(path.join(__dirname, "..", "ControlScreen.tsx"), "utf8") as string;
    const i = src.indexOf("coilSelectorBtnActive:");
    expect(src.slice(i, i + 160)).toContain("borderWidth: 2");
  });
});
