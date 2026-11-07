/**
 * KP-3 C · AiReviewControls "Vazgeç" kolu — DAVRANIŞ iddiası: kayıt başarısız olunca görünen hata, "Vazgeç" ile form kapanırken
 * TEMİZLENİR ve yazılan gerekçe silinir; form yeniden açıldığında eski hata / metin GÖRÜNMEZ (yeni denemede bayat uyarı yok).
 * GERÇEK: bileşen + katalog (AiReviewControls.test düzeneği).
 */
import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { AiReviewControls, kaydedilemediMetni } from "../AiReviewControls";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);

it("kayıt hatası 'Vazgeç' ile temizlenir; yeniden açılan formda hata ve eski gerekçe yok", async () => {
  const onSubmit = jest.fn(async () => false);
  const u = render(<AiReviewControls onSubmit={onSubmit} />);
  fireEvent.press(u.getByLabelText(T("ai.pro.degerlendirme.reddetEtiket")));
  fireEvent.changeText(u.getByLabelText(T("ai.pro.degerlendirme.redGerekcesi")), "Klinik bulgularla uyuşmuyor");
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.degerlendirme.rediKaydet"))); });
  expect(u.getByText(kaydedilemediMetni())).toBeTruthy();
  fireEvent.press(u.getByText(T("ortak.vazgec")));
  expect(u.queryByText(kaydedilemediMetni())).toBeNull();
  expect(u.queryByLabelText(T("ai.pro.degerlendirme.redGerekcesi"))).toBeNull();
  fireEvent.press(u.getByLabelText(T("ai.pro.degerlendirme.reddetEtiket")));
  expect(u.queryByText(kaydedilemediMetni())).toBeNull();
  expect(u.getByLabelText(T("ai.pro.degerlendirme.redGerekcesi")).props.value).toBe("");
});
