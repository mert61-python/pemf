// Author: mertaygn, cglrgrkn
/**
 * I18NI-A1.5 — AI Pro seansının `treatment_mode` VERİSİ ("AI Pro · Kedi Organ · Böbrek", "AI Pro · Fantom Tümör · Tümör 2", "AI Pro · Petri Kuyu ·
 * Kuyu (otomatik)") Türkçe saklanır (doğru: `profil.ARASTIRMA_SEANS_ONEKLERI` bu metne göre profil türetir). EN1 (`seansDegerEtiketi.modEtiketi`)
 * yalnız "Manuel" / "Otomatik"u çevirir; AI Pro modu ham basılır → İngilizce arayüzde aktif seans kartı (Ana Ekran / Kontrol), Seans Geçmişi,
 * seans detayı ve KPI mod dağılımı Türkçe ("Kedi Organ · Böbrek"). Kaynak: `ai_router.py` `mode=f"AI Pro · {title} · {hedef_adi(...)}"`
 * (`ai_pro_hedef.py` title = "Kedi Organ" / "Fantom Tümör" / "Petri Kuyu", hedef etiketi "Tümör" / "Kuyu", organ adı `dil="tr"`).
 * Bugün KIRMIZI; gösterimde parça → anahtar eşlemesiyle YEŞİL. TR görünüm DEĞİŞMEZ (aynı test TR'de ham değeri bekler).
 */
import React from "react";
import { act, render } from "@testing-library/react-native";
import i18n from "i18next";
import type { TFunction } from "i18next";
import { modEtiketi } from "@/utils/seansDegerEtiketi";
import { SessionProgressCard } from "@/components/domain/SessionProgressCard";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/;
const t = ((k: string, o?: object) => i18n.t(k, o as never)) as unknown as TFunction;
const MODLAR = [
  "AI Pro · Kedi Organ · Böbrek",
  "AI Pro · Kedi Organ · Akciğer (sol)",
  "AI Pro · Kedi Organ",
  "AI Pro · Fantom Tümör · Tümör 2",
  "AI Pro · Fantom Tümör · Tümör (otomatik)",
  "AI Pro · Petri Kuyu · Kuyu 3",
];

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("TR: AI Pro modu göç öncesiyle AYNI (ham değer)", () => {
  for (const m of MODLAR) expect(modEtiketi(t, m)).toBe(m);
});

it.each(MODLAR)("EN: '%s' İngilizce gösterilir (Türkçe harf / sözcük yok)", async (m) => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const g = modEtiketi(t, m);
  expect(g.startsWith("AI Pro")).toBe(true);
  expect(g).not.toMatch(TR_HARF);
  expect(g).not.toMatch(/Kedi|Kuyu|Fantom|otomatik/);
});

it("EN: aktif seans kartı (Ana Ekran / Kontrol) AI Pro modunu İngilizce yazar", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const u = render(
    <SessionProgressCard
      isActive
      mode="AI Pro · Kedi Organ · Böbrek"
      elapsedSec={60}
      remainingSec={540}
      durationSec={600}
      frequencyHz={1}
      intensityMt={0}
      onStop={jest.fn()}
      onEmergencyStop={jest.fn()}
    />,
  );
  const metin = u.getAllByText(/AI Pro/).map((n) => String(n.props.children)).join(" | ");
  expect(metin).not.toMatch(TR_HARF);
  expect(metin).not.toMatch(/Kedi/);
});
