// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 / B4 — örnek modül paneli: yalnız araç takımını kullanır; alanlar sayı olarak uygulanır; başlat / durdur; bobin durumu;
 * sunucu hata kodu eylem metniyle.
 */
const mockModul = {
  durum: null as Record<string, unknown> | null,
  hata: null as { kod: string; alan: string } | null,
  mesgul: false,
  uygula: jest.fn(async () => true),
  baslat: jest.fn(async () => true),
  durdur: jest.fn(async () => true),
};
jest.mock("@/moduller/arac", () => ({ useModul: () => mockModul }));

import React from "react";
import i18n from "i18next";
import { fireEvent, render } from "@testing-library/react-native";
import OrnekPanel from "@/moduller/ornek/Panel";

const T = (k: string, o?: object): string => (i18n.t as unknown as (a: string, b?: object) => string)(k, o);

it("GA: örnek panel — alanlar, komutlar, durum ve hata", async () => {
  await i18n.changeLanguage("tr");
  const u = render(<OrnekPanel />);
  expect(u.getByText(T("kontrol.modul.ornek.frekans"))).toBeTruthy();
  expect(u.getByText(T("kontrol.modul.ornek.duty"))).toBeTruthy();
  expect(u.getByText(T("kontrol.modul.ornek.sure"))).toBeTruthy();
  expect(u.getByTestId("modul-ornek-durum").props.children).toBe(T("kontrol.modul.ornek.durumYok"));
  fireEvent.changeText(u.getByTestId("modul-ornek-frekans_hz"), "120");
  fireEvent.press(u.getByTestId("modul-ornek-uygula"));
  expect(mockModul.uygula).toHaveBeenCalledWith({ frekans_hz: 120, duty_yuzde: 25, sure_dk: 10 });
  fireEvent.press(u.getByTestId("modul-ornek-baslat"));
  fireEvent.press(u.getByTestId("modul-ornek-durdur"));
  expect(mockModul.baslat).toHaveBeenCalled();
  expect(mockModul.durdur).toHaveBeenCalled();
  mockModul.durum = { bobin: true };
  u.rerender(<OrnekPanel />);
  expect(u.getByTestId("modul-ornek-durum").props.children).toBe(T("kontrol.modul.ornek.bobinAcik"));
  mockModul.durum = { bobin: false };
  mockModul.hata = { kod: "ayarSinirDisi", alan: "frekans_hz" };
  u.rerender(<OrnekPanel />);
  expect(u.getByTestId("modul-ornek-durum").props.children).toBe(T("kontrol.modul.ornek.bobinKapali"));
  expect(u.getByTestId("modul-ornek-hata").props.children).toBe(T("kontrol.modul.hata.ayarSinirDisi", { alan: "frekans_hz" }));
});
