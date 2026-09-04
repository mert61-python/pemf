// Author: mertaygn, cglrgrkn
/**
 * ORTAK TEST MOCK'U — `useResponsive` dönüşü.  [S2/S5, 2026-09-04 responsive denetimi]
 * (jest.config testMatch yalnız `*.test.ts(x)` topladığı için bu dosya TEST olarak koşmaz.)
 *
 * NEDEN: hook dönüşü genişledi (shellKind, contentWidth, isShort…). Testlerde elle yazılmış
 * eksik mock'lar `shellKind: undefined` verince AppShell `desktop = undefined !== "bottom"` →
 * TRUE okuyup masaüstü kabuğunu çiziyor ve alt bar testleri "Daha Fazla bulunamadı" ile
 * kırılıyordu (bu dosya tam da o kırılmadan sonra yazıldı). Tek kaynak: alan eklenince BURASI.
 *
 * KULLANIM (jest.mock fabrikası hoisted olduğu için içeride `require` ile çağrılır):
 *   jest.mock("@/hooks/useResponsive", () => ({
 *     useResponsive: () => require("@/hooks/__tests__/responsiveMock").sahteTelefon(),
 *   }));
 */
type Responsive = ReturnType<typeof import("@/hooks/useResponsive").useResponsive>;

/** Telefon (alt bar kabuğu) — varsayılan. */
export function sahteTelefon(over: Partial<Responsive> = {}): Responsive {
  return {
    width: 390,
    height: 844,
    layout: "phone",
    columns: 1,
    isCompact: true,
    isTablet: false,
    isDesktop: false,
    isShort: false,
    isLandscape: false,
    isLandscapePhone: false,
    shellKind: "bottom",
    sidebarWidth: 0,
    contentWidth: 342,
    isWeb: false,
    isNative: true,
    ...over,
  } as Responsive;
}

/** Masaüstü (tam kenar çubuğu). */
export function sahteMasaustu(over: Partial<Responsive> = {}): Responsive {
  return sahteTelefon({
    width: 1280,
    height: 800,
    layout: "desktop",
    columns: 3,
    isCompact: false,
    isDesktop: true,
    shellKind: "sidebar",
    sidebarWidth: 240,
    contentWidth: 992,
    ...over,
  });
}

/** İkon rayı (tablet dikey / yatay telefon / dar PC penceresi). */
export function sahteRay(over: Partial<Responsive> = {}): Responsive {
  return sahteTelefon({
    width: 768,
    height: 1024,
    layout: "tablet",
    columns: 2,
    isCompact: false,
    isTablet: true,
    shellKind: "rail",
    sidebarWidth: 72,
    contentWidth: 648,
    ...over,
  });
}
