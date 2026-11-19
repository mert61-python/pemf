// Author: mertaygn, cglrgrkn
/**
 * OTB T-9b (kum havuzu 19-11): TÜM PETRİ seansının mod metni "AI Pro · Petri Kuyu · Tüm petri" (VERİ, Türkçe) — gösterimde istek dilinde;
 * TR ham değerle AYNI. Python karşılığı `seans_durum.mod_etiketi` (tests/test_OTB_T9b_*).
 */
import { act } from "@testing-library/react-native";
import i18n from "i18next";
import type { TFunction } from "i18next";
import { modEtiketi } from "@/utils/seansDegerEtiketi";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const t = ((k: string, o?: object) => i18n.t(k, o as never)) as unknown as TFunction;
const MOD = "AI Pro · Petri Kuyu · Tüm petri";

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("TR: ham değer AYNEN", () => {
  expect(modEtiketi(t, MOD)).toBe(MOD);
});

it("KRİTİK EN: 'Tüm petri' İngilizce (Türkçe harf yok)", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const g = modEtiketi(t, MOD);
  expect(g).toContain("Whole well plate");
  expect(g).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/);
});
