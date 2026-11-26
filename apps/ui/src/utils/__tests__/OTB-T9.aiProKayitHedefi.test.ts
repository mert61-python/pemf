// Author: mertaygn, cglrgrkn
/**
 * OTB T-9 (ODM tezgâhı 19-11, seans 36) — AI Pro seans KAYDININ hedefi (`target_condition` = mühür etiketi, VERİ, Türkçe saklanır):
 * "Tüm petri" (TÜM PETRİ önerisi artık bütün plakayı mühürler), "Kuyu C2" (KUYUCUK), "Tümör T1" (fantom). Geçmiş kartı / seans detayı
 * `hedefEtiketi` ile basar → İngilizce arayüzde Türkçe kalıyordu. TR görünüm = ham değer (değişmez); tanınmayan serbest metin AYNEN.
 * Python karşılığı `seans_durum.py::hedef_etiketi` (tests/test_OTB_T9_*).
 */
import { act } from "@testing-library/react-native";
import i18n from "i18next";
import type { TFunction } from "i18next";
import { hedefEtiketi } from "@/utils/seansDegerEtiketi";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const t = ((k: string, o?: object) => i18n.t(k, o as never)) as unknown as TFunction;
const CIFTLER: [string, string][] = [
  ["Tüm petri", "Whole well plate"],
  ["Kuyu C2", "Well C2"],
  ["Tümör T1", "Tumor T1"],
  ["Kuyu 3", "Well 3"],
];

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("TR: AI Pro kayıt hedefi ham değerle AYNI", () => {
  for (const [ham] of CIFTLER) expect(hedefEtiketi(t, ham)).toBe(ham);
});

it.each(CIFTLER)("KRİTİK EN: '%s' → '%s'", async (ham, en) => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  expect(hedefEtiketi(t, ham)).toBe(en);
});

it("EN: tanınmayan serbest metin AYNEN (uydurulmaz)", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  for (const s of ["Tümör modeli (DEMO)", "Kuyu", "Kuyucuk C2", ""]) expect(hedefEtiketi(t, s)).toBe(s);
});
