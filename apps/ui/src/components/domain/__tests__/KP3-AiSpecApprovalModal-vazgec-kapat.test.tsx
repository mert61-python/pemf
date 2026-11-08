/**
 * KP-3 C · AiSpecApprovalModal red akışının çıkışları — her test bir DAVRANIŞ iddiası (hekim onay ekranı yarım bir red durumunda
 * KİLİTLİ kalmaz ve önceki önerinin gerekçesi sonrakine BULAŞMAZ):
 *  - "Reddet" → gerekçe kutusu; "Vazgeç" onay satırına geri döndürür (red GÖNDERİLMEZ).
 *  - Pencere kapatılınca (X) red kipi ve yazılan gerekçe SİLİNİR: yeniden açılınca onay satırı görünür, red kutusu boş.
 * GERÇEK: AiSpecApprovalModal. SAHTE: yok (geri çağrılar kaydedilir).
 */
import { fireEvent, render } from "@testing-library/react-native";
import React from "react";
import i18n from "i18next";
import { AiSpecApprovalModal } from "../AiSpecApprovalModal";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
const SPECS = { organ_id: 3, duration_minutes: 20, coil_ids: [1, 2, 3], D: [0.5, 0.5, 0], P: [0, 0, 0], e_field: 0.07 };

function ciz(p: { visible: boolean; onReject?: jest.Mock; onDismiss?: jest.Mock }) {
  return (
    <AiSpecApprovalModal
      visible={p.visible}
      specs={SPECS}
      meta={{ reliability: 0.8 }}
      organName="Karaciğer"
      onApprove={jest.fn()}
      onReject={p.onReject ?? jest.fn()}
      onDismiss={p.onDismiss ?? jest.fn()}
    />
  );
}

it("'Vazgeç' red kutusundan onay satırına döndürür; red gönderilmez", () => {
  const red = jest.fn();
  const u = render(ciz({ visible: true, onReject: red }));
  fireEvent.press(u.getByLabelText(T("ai.pro.onay.oneriyiReddet")));
  expect(u.getByLabelText(T("ai.pro.degerlendirme.redGerekcesi"))).toBeTruthy();
  fireEvent.press(u.getByText(T("ortak.vazgec")));
  expect(u.queryByLabelText(T("ai.pro.degerlendirme.redGerekcesi"))).toBeNull();
  expect(u.getByLabelText(T("ai.pro.onay.oneriyiReddet"))).toBeTruthy();
  expect(red).not.toHaveBeenCalled();
});

it("kapatınca red kipi ve gerekçe silinir; yeniden açılınca onay satırı + boş gerekçe", () => {
  const kapandi = jest.fn();
  const u = render(ciz({ visible: true, onDismiss: kapandi }));
  fireEvent.press(u.getByLabelText(T("ai.pro.onay.oneriyiReddet")));
  fireEvent.changeText(u.getByLabelText(T("ai.pro.degerlendirme.redGerekcesi")), "Önceki hastanın gerekçesi");
  fireEvent.press(u.getByLabelText(T("ortak.kapat")));
  expect(kapandi).toHaveBeenCalledTimes(1);
  u.rerender(ciz({ visible: false, onDismiss: kapandi }));
  u.rerender(ciz({ visible: true, onDismiss: kapandi }));
  expect(u.queryByLabelText(T("ai.pro.degerlendirme.redGerekcesi"))).toBeNull();
  fireEvent.press(u.getByLabelText(T("ai.pro.onay.oneriyiReddet")));
  expect(u.getByLabelText(T("ai.pro.degerlendirme.redGerekcesi")).props.value).toBe("");
});
