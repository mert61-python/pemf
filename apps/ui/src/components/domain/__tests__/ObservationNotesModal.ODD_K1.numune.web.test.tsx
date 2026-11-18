/**
 * @jest-environment jsdom
 */
/**
 * ODD K-1 (ODK-B keşfi 18-11, kum 20_durdur): petri seansı bitince "Seans Gözlem Notu → Hasta tepkisi: Sakinleşti / Hareket etti / Uyudu /
 * Endişeli…" — numune için anlamsız. Araştırma profilinde (`numune`) tepki çipleri YOK; başlık ve not alanı numune gözlemi der; not aynı
 * uca aynı biçimle gider. Veteriner profili AYNEN. Düzen `KP3-ObservationNotesModal-kollari` ile aynı (react-native-web + sahte sunucu).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("klinik@ortak.com");
});
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

import React from "react";
import { ObservationNotesModal } from "@/components/domain/ObservationNotesModal";
import { Sahne, sahteSunucu } from "../../../context/__tests__/operatorAparati";

const OTURUM = { patientName: "Plaka-7", mode: "AI Pro · Petri Kuyu", obsKey: 1, dbSessionId: 7 };
let s: Sahne;
beforeEach(() => {
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
});
const metin = () => document.body.textContent || "";

it("KRİTİK K-1: numune (araştırma) → tepki çipleri YOK, başlık + not alanı numune gözlemi; not aynı uca gider", async () => {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => (yontem === "POST" && yol === "/session/notes" ? [200, { status: "success" }] : undefined));
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  const kapat = jest.fn();
  await s.ciz(<ObservationNotesModal visible session={OTURUM} onClose={kapat} numune />);
  expect(metin()).toContain("📝 Numune Gözlem Notu");
  expect(metin()).not.toContain("Sakinleşti");
  expect(metin()).not.toContain("Hasta tepkisi");
  const alan = s.etiket("Gözlem notları") as HTMLTextAreaElement;
  expect(alan.getAttribute("placeholder")).toBe("Numune gözlemi (renk, bulanıklık, sıvı seviyesi, kontaminasyon…)");
  await s.yaz("Gözlem notları", "Kuyu C6 hafif bulanık");
  await s.metneTikla("💾 Kaydet");
  expect(kapat).toHaveBeenCalled();
});

it("KARŞIT K-1: veteriner profili (numune yok) çipler ve başlık AYNEN", async () => {
  await s.ciz(<ObservationNotesModal visible session={{ ...OTURUM, patientName: "Boncuk" }} onClose={jest.fn()} />);
  expect(metin()).toContain("📝 Seans Gözlem Notu");
  expect(metin()).toContain("Sakinleşti");
});
