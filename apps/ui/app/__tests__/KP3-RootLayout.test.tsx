/**
 * KP-3 C · app/_layout.tsx (RootLayout) — her test bir DAVRANIŞ iddiası:
 *  - Native: yazı tipleri dosyadan gömülü → BEKLEMEDEN açılış kapısı (MobileUpdateGate) + yönlendirici çizilir; global Inter uygulanır.
 *  - Web: yazı tipi yüklenene dek boş arka plan (yazı tipsiz titreme yok); yüklenince içerik; HİÇ yüklenmezse 4 sn sonra yine açılır
 *    (yazı tipi sunucusu düştü diye uygulama kilitlenmez).
 * SAHTE (platform / çerçeve sınırı): expo-font kancası, expo-router Stack, durum çubuğu, güvenli alan, güncelleme kapısı (yer tutucu).
 * Platform.OS modül YÜKLENİRKEN okunduğu için her kip izole yüklenir.
 */
import React from "react";
import { act, render } from "@testing-library/react-native";

type Durum = { fontYuklendi: boolean; inter: jest.Mock };
function yukle(os: string, d: Durum) {
  let Kok: React.ComponentType | undefined;
  jest.isolateModules(() => {
    // Yalıtılmış kayıt KENDİ React kopyasını yüklerdi → işleyici (dış React) ile kancalar ayrı örnekte kalır ("useState of null").
    // Tek React örneği: yalıtılmış kayıtta da dıştaki modül.
    jest.doMock("react", () => React);
    jest.doMock("react-native", () => {
      const RN = jest.requireActual("react-native");
      RN.Platform.OS = os;
      return RN;
    });
    jest.doMock("@/theme/fonts", () => ({ useFonts: () => [d.fontYuklendi], INTER_FONTS: { Inter: 1 }, applyGlobalInter: d.inter }));
    jest.doMock("expo-router", () => {
      const { Text } = jest.requireActual("react-native");
      return { Stack: () => <Text>YONLENDIRICI</Text> };
    });
    jest.doMock("expo-status-bar", () => ({ StatusBar: () => null }));
    jest.doMock("react-native-safe-area-context", () => ({ SafeAreaProvider: ({ children }: { children: unknown }) => children, useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
    jest.doMock("@/components/domain/MobileUpdateGate", () => {
      const { Text } = jest.requireActual("react-native");
      return { MobileUpdateGate: ({ children }: { children: unknown }) => <>{<Text>KAPI</Text>}{children as React.ReactNode}</> };
    });
    Kok = require("../_layout").default;
  });
  return Kok!;
}

afterEach(() => jest.useRealTimers());

it("native: beklemeden kapı + yönlendirici; global Inter uygulanır", () => {
  const d: Durum = { fontYuklendi: false, inter: jest.fn() };
  const Kok = yukle("ios", d);
  const u = render(<Kok />);
  expect(u.getByText("KAPI")).toBeTruthy();
  expect(u.getByText("YONLENDIRICI")).toBeTruthy();
  expect(d.inter).toHaveBeenCalledTimes(1);
});

it("web: yazı tipi yüklenene dek boş; yüklenince içerik", () => {
  const d: Durum = { fontYuklendi: false, inter: jest.fn() };
  const Kok = yukle("web", d);
  const u = render(<Kok />);
  expect(u.queryByText("YONLENDIRICI")).toBeNull();
  d.fontYuklendi = true;
  u.rerender(<Kok />);
  expect(u.getByText("YONLENDIRICI")).toBeTruthy();
});

it("web: yazı tipi hiç yüklenmezse 4 sn sonra yine açılır (3,999 sn'de değil)", () => {
  jest.useFakeTimers();
  const d: Durum = { fontYuklendi: false, inter: jest.fn() };
  const Kok = yukle("web", d);
  const u = render(<Kok />);
  act(() => { jest.advanceTimersByTime(3999); });
  expect(u.queryByText("YONLENDIRICI")).toBeNull();
  act(() => { jest.advanceTimersByTime(1); });
  expect(u.getByText("YONLENDIRICI")).toBeTruthy();
});
