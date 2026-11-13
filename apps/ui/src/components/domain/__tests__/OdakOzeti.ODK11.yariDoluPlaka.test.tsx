// Author: mertaygn, cglrgrkn
/**
 * ODK11 (istem 45 · sahip 13 Kasım 2026, tezgâh B: "zaten hepsi dolu olmayacak ki … kaç tane bulursa ona göre başlamalı"): yarı dolu
 * plakada ODAK planı 24 kuyuyu verir; kamerada sıvı görülmeyen kuyular `bos` — haritada SOLUK çizilir, erişilebilirlik etiketi "boş kuyu"
 * der ve altta kaç kuyunun boş olduğu + yerlerinin görülen kuyulardan hesaplandığı SÖYLENİR. Tam plakada açıklama YOK. ⚠️ Metinler sabit.
 */
import { render } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";
import { StyleSheet } from "react-native";

import { KuyuHaritasi } from "../aipro/OdakOzeti";

const BOS = ["A6", "B5", "C1", "D3", "D6"];
const KUYULAR = Array.from({ length: 24 }, (_, i) => {
  const etiket = `${"ABCD"[Math.floor(i / 6)]}${(i % 6) + 1}`;
  return { etiket, px: [100 + 40 * (i % 6), 60 + 40 * Math.floor(i / 6)], mT: 0.6 + 0.01 * i, secili: etiket === "B3", bos: BOS.includes(etiket) };
});

afterEach(async () => {
  await i18n.changeLanguage("tr");
});

it("KRİTİK ODK11: boş kuyular SOLUK + etiket 'boş kuyu' + açıklama (TR)", async () => {
  await i18n.changeLanguage("tr");
  const u = render(<KuyuHaritasi kuyular={KUYULAR} />);
  expect(u.getByTestId("odak-bos-kuyu").props.children).toBe(
    "Soluk kuyular boş (5 kuyu; kamerada sıvı görülmedi) — yerleri plakanın görülen kuyularından hesaplandı.",
  );
  const d3 = u.getByTestId("odak-kuyu-D3");
  expect(d3.props.accessibilityLabel).toBe("D3: boş kuyu, 0,80 mT");
  expect(StyleSheet.flatten(d3.props.style).opacity).toBe(0.35);
  const a1 = u.getByTestId("odak-kuyu-A1");
  expect(StyleSheet.flatten(a1.props.style).opacity).toBeUndefined();
  expect(u.getByTestId("odak-kuyu-secili")).toBeTruthy();
});

it("KRİTİK ODK11: EN metinleri (Y168: 'petri' yok)", async () => {
  await i18n.changeLanguage("en");
  const u = render(<KuyuHaritasi kuyular={KUYULAR} />);
  const metin = u.getByTestId("odak-bos-kuyu").props.children as string;
  expect(metin).toBe(
    "Faded wells are empty (5 wells; no liquid seen by the camera) — their positions were computed from the plate's visible wells.",
  );
  expect(metin.toLowerCase()).not.toContain("petri");
  expect(u.getByTestId("odak-kuyu-D6").props.accessibilityLabel).toMatch(/^D6: empty well, /);
});

it("KARŞIT ODK11: tam plakada (boş yok) açıklama GÖSTERİLMEZ", async () => {
  await i18n.changeLanguage("tr");
  const u = render(<KuyuHaritasi kuyular={KUYULAR.map((k) => ({ ...k, bos: false }))} />);
  expect(u.queryByTestId("odak-bos-kuyu")).toBeNull();
});
