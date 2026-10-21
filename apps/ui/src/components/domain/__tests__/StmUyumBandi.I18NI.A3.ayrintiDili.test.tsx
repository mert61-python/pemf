// Author: mertaygn, cglrgrkn
/**
 * I18NI-A3.7 — kart uyumsuzluk bandının açılır teknik ayrıntısı (WS `stm_uyum.ayrinti` ← çekirdeğin `sebep`i, `utils/stm32_kimlik.uyum_karari`)
 * DESTEK metnidir ve Türkçe üretilir; İngilizce arayüzde düğme "Technical details (for support)" deyip Türkçe paragraf açıyordu (habersiz).
 * S-I18NI.2 [ÖNERİLEN UYGULANDI]: uyum kapısı modülüne (STM firmware uyum kararı) dokunmadan, EN düğme / erişilebilirlik etiketi ayrıntının
 * Türkçe olduğunu SÖYLER ("in Turkish"). Başlık (operatör eylemi) zaten iki dilde. Tam çeviri (`ayrintilar {tr,en}`) yayın hazırlığı listesinde.
 * TR görünüm birebir.
 */
let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot }),
}));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";

import { StmUyumBandi } from "@/components/domain/StmUyumBandi";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const SEBEP = "Kart uygulamanin 88 baytlik paketini SISTEMATIK reddediyor (arada STM_OK olmadan ard arda 3 STM_NACK: CRC).";

beforeEach(() => {
  mockSnapshot = { stm: "online", stmUyum: { uyumlu: false, kod: "FW-PAKET", mesaj: "x", ayrinti: SEBEP } };
});

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("TR: ayrıntı düğmesi ve açılan metin göç öncesiyle aynı", () => {
  const u = render(<StmUyumBandi />);
  expect(u.getByLabelText("Teknik ayrıntıyı göster (destek için)")).toBeTruthy();
  fireEvent.press(u.getByText("Teknik ayrıntı (destek için)"));
  expect(u.getByText(SEBEP)).toBeTruthy();
});

it("EN: düğme ve erişilebilirlik etiketi ayrıntının TÜRKÇE (destek metni) olduğunu söyler", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const u = render(<StmUyumBandi />);
  expect(u.getByLabelText("Show technical details (in Turkish, for support)")).toBeTruthy();
  fireEvent.press(u.getByText("Technical details (in Turkish, for support)"));
  expect(u.getByText(SEBEP)).toBeTruthy();
});
