/**
 * KP-4 B1 · src/screens/DemaSimulatorScreen.tsx (WEB — iframe yolu) — yükleme göstergesi çerçeve YÜKLENİNCE kalkar (sonsuz dönme yok);
 * "Yeniden yükle" çerçeveyi yeniden kurar ve göstergeyi geri getirir, yeni çerçeve yüklenince yine kalkar. (Yerel WebView yolu KP-3.)
 * SAHTE: Platform.OS="web" (import anında → mock ÖNCE); yerel WebView modülü (web yolunda çizilmez); E-alanı bandı (konu dışı).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("react-native-webview", () => ({ WebView: () => null })); // yerel modül (web yolunda kullanılmaz)

import React from "react";
import { ActivityIndicator } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { DemaSimulatorScreen } from "@/screens/DemaSimulatorScreen";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
const yukleniyor = (u: ReturnType<typeof render>) => u.UNSAFE_queryAllByType(ActivityIndicator).length > 0;
const cerceve = (u: ReturnType<typeof render>) => u.UNSAFE_getByType("iframe" as unknown as React.ComponentType);

it("KRİTİK: web çerçevesi yüklenince gösterge kalkar; 'Yeniden yükle' yeni çerçeve + gösterge, yüklenince yine kalkar", () => {
  const u = render(<DemaSimulatorScreen />);
  expect(yukleniyor(u)).toBe(true);
  const ilk = cerceve(u);
  act(() => { ilk.props.onLoad(); });
  expect(yukleniyor(u)).toBe(false);
  act(() => { fireEvent.press(u.getByLabelText(T("dema.yenidenYukleEtiketi"))); });
  expect(yukleniyor(u)).toBe(true);
  act(() => { cerceve(u).props.onLoad(); });
  expect(yukleniyor(u)).toBe(false);
});
