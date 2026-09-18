// Author: mertaygn, cglrgrkn
/**
 * useKeyboard + KAV davranış sabitleri  [S4 adım 1, 2026-09-04 responsive denetimi]
 * ================================================================================
 * ÖLÇÜLEN DURUM: `KeyboardAvoidingView` uygulamada YALNIZ AuthScreen'de vardı ve orada da
 * `Platform.OS === "ios" ? "padding" : undefined` diyordu. Android 11+ (API 30) edge-to-edge
 * pencerede aktivite klavyeyle DARALMAZ (gradle.properties edgeToEdgeEnabled=true; manifest
 * adjustResize tek başına yetmez) → Android'de hiçbir kaçınma olmuyordu.
 *
 * İKİ FARKLI DAVRANIŞ, TEK KAYNAK:
 *  · KAV_BEHAVIOR_PENCERE — normal ekranlar: iOS veya Android API ≥ 30 → 'padding'.
 *  · KAV_BEHAVIOR_MODAL   — RN Modal içi: YALNIZ iOS. Android'de Modal kendi penceresini açar ve
 *    adjustResize ile zaten daralır; padding eklemek ÇİFT boşluk yapar.
 *
 * ⚠️ MUTASYON: PENCERE sabitindeki Android dalı silinirse 2. vaka; MODAL sabitine Android eklenirse
 * 5. vaka; web dalı (abone olmama) kaldırılırsa 8. vaka KIRILIR.
 */
type Dinleyici = (e?: { endCoordinates?: { height?: number } }) => void;

/** Verilen platformda modülü taze yükler; Keyboard dinleyicilerini yakalar. */
function yukle(os: "ios" | "android" | "web", version: number | string = 34) {
  jest.resetModules();
  const kayit: Record<string, Dinleyici> = {};
  const kaldirildi: string[] = [];
  jest.doMock("react-native", () => {
    const gercek = jest.requireActual("react-native");
    return new Proxy(gercek, {
      get(hedef, anahtar) {
        if (anahtar === "Platform") return { ...gercek.Platform, OS: os, Version: version };
        if (anahtar === "Keyboard") {
          return {
            addListener: (ad: string, cb: Dinleyici) => {
              kayit[ad] = cb;
              return { remove: () => kaldirildi.push(ad) };
            },
          };
        }
        return Reflect.get(hedef, anahtar);
      },
    });
  });
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const mod = require("@/hooks/useKeyboard") as typeof import("@/hooks/useKeyboard");
  return { mod, kayit, kaldirildi };
}

/** Hook'u çalıştırır ve son durumu döndürür (taze React kaydından). */
function kos(os: "ios" | "android" | "web", version: number | string = 34) {
  const { mod, kayit, kaldirildi } = yukle(os, version);
  /* eslint-disable @typescript-eslint/no-require-imports */
  const React = require("react");
  const TestRenderer = require("react-test-renderer");
  /* eslint-enable @typescript-eslint/no-require-imports */
  const tut: { durum?: { acik: boolean; yukseklik: number }; agac?: { unmount: () => void } } = {};
  function Sonda() {
    tut.durum = mod.useKeyboard();
    return null;
  }
  TestRenderer.act(() => {
    tut.agac = TestRenderer.create(React.createElement(Sonda));
  });
  const yayinla = (ad: string, e?: { endCoordinates?: { height?: number } }) => {
    TestRenderer.act(() => {
      kayit[ad]?.(e);
    });
  };
  return { mod, kayit, kaldirildi, tut, yayinla };
}

afterEach(() => {
  jest.resetModules();
  jest.dontMock("react-native");
});

describe("KAV davranış sabitleri", () => {
  it("iOS: pencere ve modal davranışı 'padding'", () => {
    const { mod } = yukle("ios");
    expect(mod.KAV_BEHAVIOR_PENCERE).toBe("padding");
    expect(mod.KAV_BEHAVIOR_MODAL).toBe("padding");
  });

  it("KRİTİK: Android 11+ (API 30) edge-to-edge pencerede de 'padding'", () => {
    expect(yukle("android", 34).mod.KAV_BEHAVIOR_PENCERE).toBe("padding");
    expect(yukle("android", 30).mod.KAV_BEHAVIOR_PENCERE).toBe("padding");
  });

  it("Android 10 (API 29) legacy resize: kaçınma gereksiz", () => {
    expect(yukle("android", 29).mod.KAV_BEHAVIOR_PENCERE).toBeUndefined();
  });

  it("Platform.Version sayı değilse (beklenmedik) kaçınma uygulanmaz", () => {
    expect(yukle("android", "34").mod.KAV_BEHAVIOR_PENCERE).toBeUndefined();
  });

  it("KRİTİK: Android'de MODAL davranışı undefined — Modal kendi penceresini daraltır", () => {
    expect(yukle("android", 34).mod.KAV_BEHAVIOR_MODAL).toBeUndefined();
  });

  it("web: her iki davranış da undefined", () => {
    const { mod } = yukle("web");
    expect(mod.KAV_BEHAVIOR_PENCERE).toBeUndefined();
    expect(mod.KAV_BEHAVIOR_MODAL).toBeUndefined();
  });
});

describe("useKeyboard durumu", () => {
  it("Android: didShow yüksekliği yuvarlayarak verir, didHide sıfırlar", () => {
    const { tut, yayinla } = kos("android", 34);
    expect(tut.durum).toEqual({ acik: false, yukseklik: 0 });
    yayinla("keyboardDidShow", { endCoordinates: { height: 312.4 } });
    expect(tut.durum).toEqual({ acik: true, yukseklik: 312 });
    yayinla("keyboardDidHide");
    expect(tut.durum).toEqual({ acik: false, yukseklik: 0 });
  });

  it("iOS: will* olaylarını dinler (did* değil — animasyonla eşzamanlı)", () => {
    const { kayit, yayinla, tut } = kos("ios");
    expect(Object.keys(kayit).sort()).toEqual(["keyboardWillHide", "keyboardWillShow"]);
    yayinla("keyboardWillShow", { endCoordinates: { height: 291 } });
    expect(tut.durum).toEqual({ acik: true, yukseklik: 291 });
  });

  it("KRİTİK: web'de HİÇ abone olunmaz (RNW Keyboard olayı yaymaz)", () => {
    const { kayit, tut } = kos("web");
    expect(Object.keys(kayit)).toHaveLength(0);
    expect(tut.durum).toEqual({ acik: false, yukseklik: 0 });
  });

  it("yükseklik gelmezse 0 kabul edilir (çökme yok)", () => {
    const { tut, yayinla } = kos("android", 34);
    yayinla("keyboardDidShow", {});
    expect(tut.durum).toEqual({ acik: true, yukseklik: 0 });
  });

  it("unmount'ta dinleyiciler kaldırılır (sızıntı yok)", () => {
    const { tut, kaldirildi } = kos("android", 34);
    TestRendererUnmount(tut);
    expect(kaldirildi.sort()).toEqual(["keyboardDidHide", "keyboardDidShow"]);
  });
});

/** Taze kayıttaki renderer ile unmount (üstteki React örneğiyle karışmasın). */
function TestRendererUnmount(tut: { agac?: { unmount: () => void } }) {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const TestRenderer = require("react-test-renderer");
  TestRenderer.act(() => {
    tut.agac?.unmount();
  });
}
