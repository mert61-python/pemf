/**
 * KP-3 C · DemaSimulatorScreen (native WebView yolu) — her test bir DAVRANIŞ iddiası:
 *  - Yükleme göstergesi sayfa yüklenmeye başlayınca görünür, bitince ya da HATADA kalkar (sonsuz dönme yok).
 *  - Sayfanın bildirdiği içerik yüksekliği (240–12000 px arası) çerçeveye uygulanır; sayı olmayan / aralık dışı bildirim yok sayılır.
 *  - "Yeniden yükle" çerçeveyi yeniden kurar (yeni anahtar) ve göstergeyi geri getirir.
 * SAHTE: react-native-webview (platform; aldığı props kaydedilir) · E-alanı bandı (bu dosyanın konusu değil).
 */
const mockGorunum: Record<string, any>[] = [];
jest.mock("react-native-webview", () => ({ WebView: (p: Record<string, any>) => { mockGorunum.push(p); return null; } }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));

import React from "react";
import { ActivityIndicator, View } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { DemaSimulatorScreen } from "@/screens/DemaSimulatorScreen";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
const son = () => mockGorunum[mockGorunum.length - 1];
const yukleniyor = (u: ReturnType<typeof render>) => u.UNSAFE_queryAllByType(ActivityIndicator).length > 0;
const cerceveYuksekligi = (u: ReturnType<typeof render>) => {
  const kap = u.UNSAFE_getAllByType(View).find((v) => ([] as unknown[]).concat(v.props.style).flat().some((s) => s && typeof (s as { height?: unknown }).height === "number" && (s as { height: number }).height > 240));
  return ([] as unknown[]).concat(kap!.props.style).flat().map((s) => (s as { height?: number })?.height).find((h) => typeof h === "number");
};

beforeEach(() => { mockGorunum.length = 0; });

it("gösterge: yükleme başlayınca görünür, bitince ve HATADA kalkar", () => {
  const u = render(<DemaSimulatorScreen />);
  expect(yukleniyor(u)).toBe(true);
  act(() => { son().onLoadEnd(); });
  expect(yukleniyor(u)).toBe(false);
  act(() => { son().onLoadStart(); });
  expect(yukleniyor(u)).toBe(true);
  act(() => { son().onError(); });
  expect(yukleniyor(u)).toBe(false);
});

it("bildirilen içerik yüksekliği 240–12000 arasındaysa uygulanır; sayı olmayan / aralık dışı yok sayılır", () => {
  const u = render(<DemaSimulatorScreen />);
  const ilk = cerceveYuksekligi(u);
  for (const veri of ["abc", "200", "20000"]) act(() => { son().onMessage({ nativeEvent: { data: veri } }); });
  expect(cerceveYuksekligi(u)).toBe(ilk);
  act(() => { son().onMessage({ nativeEvent: { data: "1500" } }); });
  expect(cerceveYuksekligi(u)).toBe(1500);
});

it("'Yeniden yükle' çerçeveyi yeniden kurar ve göstergeyi geri getirir", async () => {
  const u = render(<DemaSimulatorScreen />);
  act(() => { son().onLoadEnd(); });
  const ilkAnahtar = mockGorunum.length;
  await act(async () => { fireEvent.press(u.getByLabelText(T("dema.yenidenYukleEtiketi"))); });
  expect(yukleniyor(u)).toBe(true);
  expect(mockGorunum.length).toBeGreaterThan(ilkAnahtar);
  expect(son().source.uri).toContain("/simulator/index.html");
});
