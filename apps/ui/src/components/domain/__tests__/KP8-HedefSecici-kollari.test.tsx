/**
 * KP-8 · AI Pro HedefSecici (halka + yedek liste) kalan dallar — GERÇEK bileşenler, sahte yok:
 *  - Görüntü konumu (pxn) eksik / tek koordinatlı aday halka olarak ÇİZİLMEZ (yanlış yere halka yok); yedek listede yine seçilebilir.
 *  - Kimliksiz aday sırasıyla anahtarlanır (test kimliği sıra no) ve seçilince 0 (otomatik) bildirir; güveni sayı değilse %0.
 */
import React from "react";
import { fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { HedefHalkalari, HedefListesi } from "../aipro/HedefSecici";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const ADAYLAR = [
  { label: "Kimliksiz", pxn: [0.5, 0.5], reliability: "bilinmiyor" },
  { id: 7, label: "Konumsuz", reliability: 0.9 },
  { id: 8, label: "Tek koordinat", pxn: [0.2], reliability: 0.4 },
];

it("halka: konumsuz / tek koordinatlı aday çizilmez; kimliksiz aday sıra kimliğiyle, %0 güven, seçilince 0", () => {
  const onSec = jest.fn();
  const u = render(<HedefHalkalari hedefler={ADAYLAR as never} seciliId={0} onSec={onSec} kutu={{ width: 200, height: 100 }} />);
  expect(u.queryByTestId("hedef-halka-7")).toBeNull();
  expect(u.queryByTestId("hedef-halka-8")).toBeNull();
  const halka = u.getByTestId("hedef-halka-0");
  expect(halka.props.accessibilityLabel).toBe(T("ai.pro.hedef.etiket", { sira: 1, toplam: 3, ad: "Kimliksiz", guven: 0, durum: "" }));
  fireEvent.press(halka);
  expect(onSec).toHaveBeenCalledWith(0);
});

it("yedek liste: konumsuz aday da satır olarak seçilebilir; kimliksiz satır sıra kimliğiyle, seçilince 0", () => {
  const onSec = jest.fn();
  const u = render(<HedefListesi hedefler={ADAYLAR as never} seciliId={0} onSec={onSec} />);
  fireEvent.press(u.getByTestId("hedef-satir-7"));
  expect(onSec).toHaveBeenLastCalledWith(7);
  fireEvent.press(u.getByTestId("hedef-satir-0"));
  expect(onSec).toHaveBeenLastCalledWith(0);
  expect(u.getByTestId("hedef-satir-0").props.accessibilityLabel).toContain("Kimliksiz");
});
