// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 · Y299 — Ayarlar "Geliştirici modülleri": sunucudaki değer gelene dek anahtar kilitli; varsayılan KAPALI; değişim
 * sunucuya yazılır; yazılamazsa eylem metni; liste alınamazsa KAPALI gösterilir.
 */
const mockApi = { listele: jest.fn(), gorunurlukYaz: jest.fn() };
jest.mock("@/services/moduller", () => ({
  get modulApi() {
    return mockApi;
  },
}));

import React from "react";
import i18n from "i18next";
import { act, fireEvent, render } from "@testing-library/react-native";
import { GelistiriciModulleriKarti } from "@/components/domain/GelistiriciModulleriKarti";

const T = (k: string): string => (i18n.t as unknown as (a: string) => string)(k);

it("GA: anahtar — kilitli → kapalı → aç / yazılamadı", async () => {
  await i18n.changeLanguage("tr");
  let coz: (v: unknown) => void = () => {};
  mockApi.listele.mockReturnValue(new Promise((r) => (coz = r)));
  const u = render(<GelistiriciModulleriKarti />);
  expect(u.getByText(T("ayarlar.gelistiriciModulleri.baslik"))).toBeTruthy();
  expect(u.getByText(T("ayarlar.gelistiriciModulleri.aciklama"))).toBeTruthy();
  expect(u.getByTestId("gelistirici-modulleri-anahtar").props.disabled).toBe(true);
  await act(async () => coz({ tamam: true, veri: { gorunur: false } }));
  const a = () => u.getByTestId("gelistirici-modulleri-anahtar");
  expect(a().props.value).toBe(false);
  expect(a().props.disabled).toBe(false);
  mockApi.gorunurlukYaz.mockResolvedValueOnce({ tamam: true, veri: { gorunur: true } });
  await act(async () => fireEvent(a(), "valueChange", true));
  expect(mockApi.gorunurlukYaz).toHaveBeenCalledWith(true);
  expect(a().props.value).toBe(true);
  mockApi.gorunurlukYaz.mockResolvedValueOnce({ tamam: false, hata: { kod: "ayarYazilamadi", alan: "" } });
  await act(async () => fireEvent(a(), "valueChange", false));
  expect(a().props.value).toBe(true);
  expect(u.getByTestId("gelistirici-modulleri-hata").props.children).toBe(T("ayarlar.gelistiriciModulleri.hata"));
  u.unmount();
  mockApi.listele.mockResolvedValue({ tamam: false, hata: { kod: "baglanti", alan: "" } });
  const y = render(<GelistiriciModulleriKarti />);
  await act(async () => {});
  expect(y.getByTestId("gelistirici-modulleri-anahtar").props.value).toBe(false);
  y.unmount();
  let coz2: (v: unknown) => void = () => {};
  mockApi.listele.mockReturnValue(new Promise((r) => (coz2 = r)));
  const z = render(<GelistiriciModulleriKarti />);
  z.unmount();
  await act(async () => coz2({ tamam: true, veri: { gorunur: true } })); // söküldükten sonra yazılmaz
});
