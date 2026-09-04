// Author: mertaygn, cglrgrkn
/**
 * useResponsive — içerik-farkında düzen kararları  [S2+S5, 2026-09-04 responsive denetimi]
 * ========================================================================================
 * ÖLÇÜLEN DURUM: hook yalnız pencere GENİŞLİĞİNİ okuyordu. Kenar çubuğu düşülmediği için
 * ızgara/kompaktlık kararı gerçek içerik alanından bağımsızdı (768 px tablette 352 px'lik
 * alana 2 sütun) ve YÜKSEKLİK hiç okunmuyordu (yatay telefonda içerik ~150 px'e düşüyordu).
 *
 * ⚠️ İKİ TEST TUZAĞI (ikisi de bu dosyada ölçüldü):
 *  1. `jest.resetModules()` sonrası React'i tepeden import edersen hook BAŞKA bir React örneğine
 *     bağlanır → "Invalid hook call". React de taze kayıttan alınmalı.
 *  2. `@testing-library/react-native` test GÖVDESİNDE require edilemez (kendi afterEach/beforeAll
 *     kancalarını kaydetmeye çalışır → "Hooks cannot be defined inside tests"). Kanca kaydetmeyen
 *     `react-test-renderer` kullanılır.
 *
 * ⚠️ MUTASYON: `contentWidth < COMPACT_CONTENT` koşulu silinirse tablet satırı, `isShort`
 * kaldırılırsa yatay telefon satırı KIRILIR.
 */
import { cihaziKur } from "@/theme/__tests__/olcek";

afterEach(() => {
  jest.resetModules();
  jest.dontMock("react-native");
});

type Olcum = ReturnType<typeof import("@/hooks/useResponsive").useResponsive>;

/** Hook'u verilen cihazda taze yükleyip döndürdüğü değerleri okur. */
function olc(width: number, height: number, os: "ios" | "android" | "web" = "ios"): Olcum {
  cihaziKur({ width, height, os });
  /* eslint-disable @typescript-eslint/no-var-requires */
  const React = require("react");
  const TestRenderer = require("react-test-renderer");
  const { useResponsive } = require("@/hooks/useResponsive") as typeof import("@/hooks/useResponsive");
  /* eslint-enable @typescript-eslint/no-var-requires */
  let sonuc: Olcum | null = null;
  function Sonda() {
    sonuc = useResponsive();
    return null;
  }
  TestRenderer.act(() => {
    TestRenderer.create(React.createElement(Sonda));
  });
  if (!sonuc) throw new Error("hook okunamadı");
  return sonuc;
}

describe("useResponsive", () => {
  it("dar telefon: alt bar kabuğu, kompakt, kısa değil", () => {
    const r = olc(320, 568, "android");
    expect(r.shellKind).toBe("bottom");
    expect(r.sidebarWidth).toBe(0);
    expect(r.isCompact).toBe(true);
    expect(r.isShort).toBe(false);
  });

  it("KRİTİK: yatay telefon (926×428) kısa sayılır ve ray kabuğu alır", () => {
    const r = olc(926, 428, "android");
    expect(r.isShort).toBe(true);
    expect(r.isLandscape).toBe(true);
    expect(r.isLandscapePhone).toBe(true);
    expect(r.shellKind).toBe("rail");
  });

  it("KRİTİK: tablet dikeyde içerik genişliği kenar çubuğu DÜŞÜLEREK hesaplanır", () => {
    const r = olc(768, 1024, "android");
    expect(r.layout).toBe("tablet");
    expect(r.sidebarWidth).toBeGreaterThan(0);
    expect(r.contentWidth).toBeLessThan(768); // pencere genişliği DEĞİL
    expect(r.contentWidth).toBe(768 - r.sidebarWidth - 2 * r.width * 0 - 2 * 31); // spacing.xl = rs(24) = 31 (SCALE 1.3)
  });

  it("geniş PC: sidebar kabuğu, kompakt değil", () => {
    const r = olc(1920, 1080, "web");
    expect(r.shellKind).toBe("sidebar");
    expect(r.isCompact).toBe(false);
    expect(r.isShort).toBe(false);
  });

  it("KRİTİK: dar PC penceresi (700×540) ray alır — telefon kabuğu çizilmez", () => {
    const r = olc(700, 540, "web");
    expect(r.shellKind).toBe("rail");
  });
});
