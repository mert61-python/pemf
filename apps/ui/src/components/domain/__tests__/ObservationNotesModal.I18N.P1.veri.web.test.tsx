/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · VERİYE GİDEN DEĞER — gözlem notunun tepki çipleri. Çipin GÖRÜNEN adı dile göre değişir ("Sakinleşti" / "Calmed") ama notun
 * sunucuya GİDEN metni dilden BAĞIMSIZDIR: Türkçe tepki metni `POST /session/notes` gövdesine BAYT BAYT aynı yazılır (kayıtlar tek dilde
 * kalır; veri göçü YOK). Mutant: tepki etiketi (görünen ad) gönderilen değere sızarsa EN koşusu KIRMIZI olur.
 * GERÇEK: ObservationNotesModal + i18n; sahte: fetch (ağ sınırı), Supabase istemcisi, güvenli alan kancası.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("klinik@ortak.com");
});
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

import React, { act } from "react";
import { ObservationNotesModal } from "@/components/domain/ObservationNotesModal";
import { Sahne, sahteSunucu } from "../../../context/__tests__/operatorAparati";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const NOT = "Kulaklarını oynattı";
let s: Sahne;
beforeEach(() => {
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function kaydet(dil: "tr" | "en") {
  if (dil === "en") {
    __bayrakTestiAyarla(true);
    await act(async () => {
      await dilSec("en", depo);
    });
  }
  const sunucu = sahteSunucu([], (yol, _g, yontem) => (yontem === "POST" && yol === "/session/notes" ? [200, { status: "success", session_id: 1, updated: true }] : undefined));
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(<ObservationNotesModal visible session={{ patientName: "Boncuk", mode: "Manuel", obsKey: 1, dbSessionId: 1 }} onClose={jest.fn()} />);
  await s.metneTikla(dil === "tr" ? "Sakinleşti" : "Calmed");
  await s.metneTikla(dil === "tr" ? "Uyudu" : "Slept");
  await s.yaz(dil === "tr" ? "Gözlem notları" : "Observation notes", NOT);
  await s.metneTikla(dil === "tr" ? "💾 Kaydet" : "💾 Save");
  const istekler = sunucu.kayit.filter((i) => i.yontem === "POST" && i.yol === "/session/notes");
  expect(istekler).toHaveLength(1);
  return (istekler[0].govde as { notes: string }).notes;
}

it("Türkçe: seçilen tepkiler + not, göç öncesiyle AYNI biçimde gönderilir", async () => {
  expect(await kaydet("tr")).toBe(`Sakinleşti, Uyudu — ${NOT}`);
});

it("İngilizce: çipler İngilizce görünür ama GİDEN not metni Türkçe ile BAYT BAYT aynı", async () => {
  expect(await kaydet("en")).toBe(`Sakinleşti, Uyudu — ${NOT}`);
});
