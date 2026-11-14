// Author: mertaygn, cglrgrkn
/**
 * AP-24 (ev denemesi 14 Kasım) — veteriner AI Pro açıklaması "kedi organ lokalizasyonu → em_kedi doz ÖNERİSİ" diyordu; ODK5'ten (12-13
 * Kasım) beri kedi ÖNERİSİ, AP-17'den (14 Kasım) beri kedi SÜRÜŞÜ hocanın em_kedi modelinden DEĞİL alan hesabından (ODAK · CST alan
 * tablosu). Dört not (web / mobil × öneri / seans) iki dilde: model adı (em_kedi) YOK, alan hesabı (CST) VAR (panel çizimi: I18N.P1).
 */
import { act } from "@testing-library/react-native";
import i18n from "i18next";

import { EN, TR } from "@/i18n/__tests__/kaynakMetni";

const NOTLAR = ["kediWebOneri", "kediWebSeans", "kediMobilOneri", "kediMobilSeans"].map((k) => `ai.pro.not.${k}`);

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK: dört kedi notu TR + EN'de em_kedi DEMEZ, alan hesabını (CST) söyler", () => {
  for (const k of NOTLAR) {
    for (const [dil, s] of [["tr", TR[k]], ["en", EN[k]]] as const) {
      expect(s).toBeTruthy();
      expect([dil, k, s]).toEqual([dil, k, expect.not.stringMatching(/em_kedi/)]);
      expect([dil, k, s]).toEqual([dil, k, expect.stringMatching(/CST/)]);
    }
  }
  expect(TR["ai.pro.not.kediWebOneri"]).toMatch(/alan hesab/);
  expect(EN["ai.pro.not.kediWebOneri"]).toMatch(/field calculation/);
  expect(EN["ai.pro.not.kediWebOneri"]).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/);
});

it("KARŞIT: öneri / seans ayrımı korunur (sürüş kapalı notu bobin sürülmez der, seans notu 7 bobin)", () => {
  expect(TR["ai.pro.not.kediWebOneri"]).toMatch(/bobin sürülmez/);
  expect(EN["ai.pro.not.kediWebOneri"]).toMatch(/no coil is driven/);
  expect(TR["ai.pro.not.kediWebSeans"]).toMatch(/7 bobin/);
  expect(EN["ai.pro.not.kediWebSeans"]).toMatch(/7 coils/);
  expect(i18n.t("ai.pro.not.kediWebOneri")).toBe(TR["ai.pro.not.kediWebOneri"]);
});
