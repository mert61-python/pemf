// Author: mertaygn, cglrgrkn
/**
 * Button — çift-tık koruması.
 *
 * Denetim bulgusu: guard `onPress === lastFnRef.current` KİMLİK karşılaştırmasına dayanıyordu.
 * Çağrı yerlerinin çoğu satır-içi ok fonksiyonu kullanıyor (`onPress={() => analyzeImage()}`),
 * bunlar HER RENDER'da yeni referans üretir → kimlik hiç eşleşmez, koruma HİÇ devreye girmezdi.
 * Tıbbi cihazda "Seans Başlat"a hızlı çift dokunuş iki seans isteği demektir.
 *
 * Kilitlenen davranış: aynı EYLEM (aynı etiket) 400ms içinde iki kez ateşlenmez; ama toggle
 * butonlarında (Başlat↔Durdur, etiket değişir) ikinci dokunuş YUTULMAZ.
 */
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(async () => undefined), ImpactFeedbackStyle: { Light: "light" } }));

import React from "react";
import { render, fireEvent, act } from "@testing-library/react-native";
import { Button } from "@/components/ui/Button";

beforeEach(() => { jest.useFakeTimers(); });
afterEach(() => { jest.useRealTimers(); });

it("KRİTİK: satır-içi ok fonksiyonunda bile hızlı çift dokunuş TEK kez tetiklenir", () => {
  const spy = jest.fn();
  // Gerçek çağrı deseni: her render'da YENİ fonksiyon referansı.
  const { getByText } = render(<Button label="Seans Başlat" onPress={() => spy()} />);
  const btn = getByText("Seans Başlat");

  fireEvent.press(btn);
  fireEvent.press(btn);   // panik/kazara ikinci dokunuş
  fireEvent.press(btn);

  expect(spy).toHaveBeenCalledTimes(1);
});

it("400ms sonra aynı buton TEKRAR tetiklenebilir (kalıcı kilit değil)", () => {
  const spy = jest.fn();
  const { getByText } = render(<Button label="Seans Başlat" onPress={() => spy()} />);
  const btn = getByText("Seans Başlat");

  fireEvent.press(btn);
  act(() => { jest.advanceTimersByTime(500); });
  fireEvent.press(btn);

  expect(spy).toHaveBeenCalledTimes(2);
});

it("TOGGLE butonu: etiket değişince ikinci dokunuş YUTULMAZ (Başlat→Durdur)", () => {
  const start = jest.fn();
  const stop = jest.fn();
  const { getByText, rerender } = render(<Button label="Başlat" onPress={() => start()} />);
  fireEvent.press(getByText("Başlat"));
  expect(start).toHaveBeenCalledTimes(1);

  // Aynı instance, yeni eylem — kullanıcı hemen "Durdur"a basabilmeli.
  rerender(<Button label="Durdur" onPress={() => stop()} />);
  fireEvent.press(getByText("Durdur"));
  expect(stop).toHaveBeenCalledTimes(1);
});

it("disabled/loading iken hiç tetiklenmez", () => {
  const spy = jest.fn();
  const { getByText, rerender } = render(<Button label="Kaydet" onPress={spy} disabled />);
  fireEvent.press(getByText("Kaydet"));
  rerender(<Button label="Kaydet" onPress={spy} loading />);
  fireEvent.press(getByText("Kaydet"));
  expect(spy).not.toHaveBeenCalled();
});
