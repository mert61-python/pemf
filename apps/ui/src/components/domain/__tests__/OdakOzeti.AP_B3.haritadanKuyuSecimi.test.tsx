// Author: mertaygn, cglrgrkn
/**
 * AP · B3 (istem 48, tezgâh 13 Kasım 2026): onay penceresindeki 24 kuyu haritasından hedef seçilebilir — dolu kuyuya dokunmak seçer,
 * "Yeniden hesapla" o kuyu için YENİ öneri ister (mühür yeni öneride). Boş kuyu (ODK11) seçilemez. TÜM PETRİ kipindeyken kuyu seçmek
 * KUYUCUK kipine geçer (tek kuyu hedefi). Harita salt gösterimken (yeniden hesap yok) dokunulabilir DEĞİL.
 */
import { fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { OdakOzeti, type OdakOzet } from "../aipro/OdakOzeti";

const BOS = ["B1"];
const KUYULAR = Array.from({ length: 24 }, (_, i) => {
  const etiket = `${"ABCD"[Math.floor(i / 6)]}${(i % 6) + 1}`;
  return { etiket, px: [100 + 40 * (i % 6), 60 + 40 * Math.floor(i / 6)], mT: 0.6, secili: etiket === "C2", bos: BOS.includes(etiket) };
});
const odak = (kip = "KUYUCUK"): OdakOzet => ({ kip, doz_mT: 0.6, beklenen_mT: 0.6, tavan_mT: 1.2, pay_yuzde: 5, kuyular: KUYULAR });

it("KRİTİK B3: dolu kuyuya dokunmak seçer; 'Yeniden hesapla' seçilen kuyuyla yeni öneri ister", () => {
  const hesapla = jest.fn();
  const u = render(<OdakOzeti odak={odak()} onYenidenHesapla={hesapla} />);
  fireEvent.press(u.getByTestId("odak-kuyu-C6"));
  expect(u.getByTestId("odak-kuyu-C6").props.accessibilityState?.selected).toBe(true);
  expect(u.getByTestId("odak-kuyu-sec-ipucu").props.children).toBe(
    "Seçilen kuyu: C6 — öneriyi bu kuyu için almak üzere Yeniden hesapla'ya basın.",
  );
  fireEvent.press(u.getByTestId("odak-yeniden-hesapla"));
  expect(hesapla).toHaveBeenCalledWith(0.6, "KUYUCUK", "C6");
});

it("B3: boş kuyu (ODK11) dokunulamaz; mühürdeki kuyu seçiliyken yeniden hesap kuyu GÖNDERMEZ", () => {
  const hesapla = jest.fn();
  const u = render(<OdakOzeti odak={odak()} onYenidenHesapla={hesapla} />);
  fireEvent.press(u.getByTestId("odak-kuyu-B1"));
  expect(u.getByTestId("odak-kuyu-sec-ipucu").props.children).toBe(
    "Hedefi değiştirmek için dolu bir kuyuya dokunun, sonra Yeniden hesapla'ya basın.",
  );
  fireEvent.press(u.getByTestId("odak-yeniden-hesapla"));
  expect(hesapla).toHaveBeenCalledWith(0.6, "KUYUCUK", undefined);
});

it("B3: TÜM PETRİ kipindeyken kuyu seçmek KUYUCUK kipine geçer", () => {
  const hesapla = jest.fn();
  const u = render(<OdakOzeti odak={odak("TUM_PETRI")} onYenidenHesapla={hesapla} />);
  fireEvent.press(u.getByTestId("odak-kuyu-A3"));
  expect(u.getByTestId("odak-kip-KUYUCUK").props.accessibilityState?.checked).toBe(true);
  fireEvent.press(u.getByTestId("odak-yeniden-hesapla"));
  expect(hesapla).toHaveBeenCalledWith(0.6, "KUYUCUK", "A3");
});

it("salt gösterimde (yeniden hesap yok) harita dokunulabilir DEĞİL ve ipucu yok", () => {
  const u = render(<OdakOzeti odak={odak()} />);
  expect(u.getByTestId("odak-kuyu-C6").props.accessibilityRole).toBeUndefined();
  expect(u.queryByTestId("odak-kuyu-sec-ipucu")).toBeNull();
});
