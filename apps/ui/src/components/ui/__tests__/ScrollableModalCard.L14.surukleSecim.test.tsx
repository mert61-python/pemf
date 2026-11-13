// Author: mertaygn, cglrgrkn
/**
 * L14 (sahip 13 Kasım 2026): AI önerisinde doz kutusundaki değeri fare sol tuşu basılı SÜRÜKLEYEREK seçerken pencere kendi kendine
 * kapanıyordu. Web'de `onPress` = tarayıcı `click`i; basış kartta başlayıp perdede bırakılınca `click` PERDEYE gider. Sözleşme: kartta
 * BAŞLAYAN basıştan sonra perdeye düşen ilk `click` KAPATMAZ; perdede başlayan dokunuş kapatır; kart içi tıklama işareti temizler.
 */
import { fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Text } from "react-native";

import { ScrollableModalCard } from "../ScrollableModalCard";

function kur() {
  const kapat = jest.fn();
  const u = render(
    <ScrollableModalCard visible onRequestClose={() => {}} onBackdropPress={kapat} testID="kart">
      <Text>icerik</Text>
    </ScrollableModalCard>,
  );
  const kart = u.getByTestId("kart");
  return { u, kapat, kart };
}


it("KRİTİK L14: kartta başlayan basış (sürükleyerek seçim) perdede bitince pencere KAPANMAZ", () => {
  const { u, kapat, kart } = kur();
  const perde = u.getByTestId("kart-perde");
  fireEvent(kart, "pressIn");
  fireEvent.press(perde);
  expect(kapat).not.toHaveBeenCalled();
});

it("KARŞIT L14: perdede başlayan dokunuş eskisi gibi KAPATIR (ikinci tıklama da)", () => {
  const { u, kapat, kart } = kur();
  const perde = u.getByTestId("kart-perde");
  fireEvent.press(perde);
  expect(kapat).toHaveBeenCalledTimes(1);
  fireEvent(kart, "pressIn");
  fireEvent.press(perde); // sürükleme sonrası ilk click yutulur
  fireEvent.press(perde); // sonraki gerçek perde tıklaması kapatır
  expect(kapat).toHaveBeenCalledTimes(2);
});

it("KARŞIT L14: kart içinde başlayıp kart içinde biten tıklama işareti TEMİZLER → sonraki perde tıklaması kapatır", () => {
  const { u, kapat, kart } = kur();
  const perde = u.getByTestId("kart-perde");
  fireEvent(kart, "pressIn");
  fireEvent.press(kart);
  fireEvent.press(perde);
  expect(kapat).toHaveBeenCalledTimes(1);
});
