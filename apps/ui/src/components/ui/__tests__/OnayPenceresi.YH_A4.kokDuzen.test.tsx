// Author: mertaygn, cglrgrkn
/**
 * YH-A4 — kök düzen (`app/_layout.tsx`) uygulama içi onay sağlayıcısını TAKAR: gerçek uygulamada web onayları köprüye düşer.
 * ==========================================================================
 * NEDEN AYRI DOSYA (YH-B1): sağlayıcı kısa ekran için `ScrollableModalCard`a geçince (`react-native-safe-area-context` içe aktarır)
 * bu test `OnayPenceresi.YH_A4.test.tsx` içinde KIRMIZI oldu — o dosya sağlayıcıyı en üstte içe aktardığı için güvenli alan modülü
 * DIŞ kayıtta önbelleğe alınıyor; jest yalıtılmış kayıtta `doMock` fabrikası yerine önbellekteki kurulum taklidini (gerçek
 * `SafeAreaProvider` — ölçü yokken çocuk ÇİZMEZ) döndürüyor → kök düzen boş çiziliyor, sağlayıcı hiç takılmıyordu (ürün kusuru
 * DEĞİL; ölçüldü: ağaç `RNCSafeAreaProvider`, çocuk null). Burada dış kayıt o modülü yüklemez (KP3-RootLayout deseni).
 */
import React from "react";
import { Platform } from "react-native";
import { act, render } from "@testing-library/react-native";

const asilOS = Platform.OS;
beforeEach(() => {
  (Platform as { OS: string }).OS = "web";
});
afterEach(() => {
  (Platform as { OS: string }).OS = asilOS;
});

it("KRİTİK: kök düzen (app/_layout) sağlayıcıyı TAKAR — gerçek uygulamada web onayları köprüye düşer", () => {
  // KP3-RootLayout deseni: yalıtılmış kayıtta kök düzen + AYNI kayıttaki köprü (tek React örneği).
  let Kok: React.ComponentType | undefined;
  let kopru: typeof import("@/services/onayKoprusu") | undefined;
  jest.isolateModules(() => {
    jest.doMock("react", () => React);
    jest.doMock("@/theme/fonts", () => ({ useFonts: () => [true], INTER_FONTS: {}, applyGlobalInter: () => undefined }));
    jest.doMock("expo-router", () => ({ Stack: () => null }));
    jest.doMock("expo-status-bar", () => ({ StatusBar: () => null }));
    jest.doMock("react-native-safe-area-context", () => ({
      SafeAreaProvider: ({ children }: { children: unknown }) => children,
      useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    }));
    jest.doMock("@/components/domain/MobileUpdateGate", () => ({
      MobileUpdateGate: ({ children }: { children: unknown }) => children,
    }));
    Kok = require("../../../../app/_layout").default;
    kopru = require("@/services/onayKoprusu");
  });
  expect(kopru!.uygulamaIciOnay({ baslik: "x", govde: "y", tur: "onay" })).toBeNull(); // aparat: takılmadan önce boş
  const u = render(React.createElement(Kok!));
  let soz: Promise<boolean> | null = null;
  act(() => {
    soz = kopru!.uygulamaIciOnay({ baslik: "x", govde: "y", tur: "onay" });
  });
  expect(soz).not.toBeNull();
  u.unmount();
  return expect(soz).resolves.toBe(false);
});
