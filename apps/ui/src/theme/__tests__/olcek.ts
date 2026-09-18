// Author: mertaygn, cglrgrkn
/**
 * ORTAK TEST YARDIMCISI — ölçek/boyut bağımlı modülleri belirli bir cihazda yeniden yükler.
 * (jest.config testMatch yalnız `*.test.ts(x)` topladığı için bu dosya TEST olarak koşmaz.)
 *
 * ⚠️ TUZAK (2026-09-03'te ölçüldü): `jest.isolateModules` kayıt defteri YALNIZ callback içinde
 * etkindir; react-native'in tembel `Platform` getter'ı callback DIŞINDA ANA kayda çözülür →
 * izole kayıtta yapılan mutasyon görünmez ve test sahte-yeşil/sahte-kırmızı olur.
 * DOĞRU DESEN: `jest.resetModules()` + `jest.doMock("react-native", …)` + `require(...)`.
 * `Proxy` kullanılır çünkü react-native'i yaymak (spread) tüm tembel getter'ları tetikler.
 */

export interface CihazSecenek {
  width: number;
  height: number;
  os?: "ios" | "android" | "web";
  fontScale?: number;
}

/** react-native'i verilen cihaz ölçüleriyle sahteleyip modül kaydını sıfırlar. */
export function cihaziKur({ width, height, os = "ios", fontScale = 1 }: CihazSecenek): void {
  jest.resetModules();
  jest.doMock("react-native", () => {
    const gercek = jest.requireActual("react-native");
    const olculer = { width, height, scale: 2, fontScale };
    return new Proxy(gercek, {
      get(hedef, anahtar) {
        if (anahtar === "Dimensions") return { ...gercek.Dimensions, get: () => olculer };
        if (anahtar === "Platform") return { ...gercek.Platform, OS: os };
        if (anahtar === "useWindowDimensions") return () => olculer;
        return Reflect.get(hedef, anahtar);
      },
    });
  });
}

/** Cihazı kurup `@/theme/tokens`i taze yükler. */
export function tokenlariYukle(secenek: CihazSecenek): typeof import("@/theme/tokens") {
  cihaziKur(secenek);
  return require("@/theme/tokens") as typeof import("@/theme/tokens");
}

/** Cihazı kurup `@/hooks/useResponsive`i taze yükler. */
export function responsiveYukle(secenek: CihazSecenek): typeof import("@/hooks/useResponsive") {
  cihaziKur(secenek);
  return require("@/hooks/useResponsive") as typeof import("@/hooks/useResponsive");
}
