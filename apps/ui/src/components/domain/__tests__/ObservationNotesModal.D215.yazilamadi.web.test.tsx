/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.15 (B-3.23) — gözlem notu YAZILAMAZSA not ekranı AÇIK kalır, not KAYBOLMAZ ve hekim gerekçeyi görür.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: backend kilitli DB'de notu yazamadığı hâlde `200 success` dönüyordu → ekran "kaydedildi" sanıp kapanıyor,
 * not SESSİZCE kayboluyordu (gerçek 5,7 sn'lik kilitle ölçüldü). `/session/notes` yanıtı GERÇEK backend'den üretilen
 * fikstürdür (`tests/test_gozlem_notu_YAZILAMAZSA_basari_DONMEZ_D215.py`, GERÇEK yazma kilidi altında GERÇEK uç) — jest
 * Python koşturamaz; fikstür bayatlarsa o kapı KIRMIZI.
 * GERÇEK: ObservationNotesModal, apiClient. Sahte: fetch (ağ sınırı), güvenli alan kancası, `window.alert` (yakalanır).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

import React from "react";
import { ObservationNotesModal } from "@/components/domain/ObservationNotesModal";
import { Sahne, sahteSunucu } from "../../../context/__tests__/operatorAparati";
import YAZILAMADI from "./__fixtures__/notYazilamadi.D215.json";

const NOT = "Kulaklarını oynattı, rahatladı";
let s: Sahne;
let uyari: jest.SpyInstance;
beforeEach(() => {
  s = new Sahne();
  uyari = jest.spyOn(window, "alert").mockImplementation(() => undefined);
});
afterEach(async () => {
  await s.sok();
  uyari.mockRestore();
});

async function notuKaydet(notlarYaniti: [number, unknown]) {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => (yontem === "POST" && yol === "/session/notes" ? notlarYaniti : undefined));
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  const kapat = jest.fn();
  await s.ciz(
    <ObservationNotesModal visible session={{ patientName: "Boncuk", mode: "Manuel", obsKey: 1, dbSessionId: 1 }} onClose={kapat} />,
  );
  await s.yaz("Gözlem notları", NOT);
  await s.metneTikla("💾 Kaydet");
  const istekler = sunucu.kayit.filter((i) => i.yontem === "POST" && i.yol === "/session/notes");
  expect(istekler).toHaveLength(1); // ARA: not GERÇEKTEN gönderildi
  return kapat;
}

it("KRİTİK D2.15: GERÇEK backend notu yazamayınca ekran KAPANMAZ, not DURUR, gerekçe gösterilir", async () => {
  const kapat = await notuKaydet([YAZILAMADI.durum, YAZILAMADI.govde]);
  expect(kapat).not.toHaveBeenCalled();
  expect((s.etiket("Gözlem notları") as HTMLTextAreaElement).value).toBe(NOT);
  const uyarilar = uyari.mock.calls.map((c) => String(c[0])).join(" | ");
  expect(uyarilar).toContain("Not kaydedilemedi");
  expect(uyarilar).toContain("kaydedilemedi —"); // sunucunun EYLEM söyleyen gerekçesi (genel metin değil)
});

it("KARŞIT D2.15: not yazılınca ekran kapanır, uyarı YOK", async () => {
  const kapat = await notuKaydet([200, { status: "success", session_id: 1, updated: true }]);
  expect(kapat).toHaveBeenCalledTimes(1);
  expect(uyari).not.toHaveBeenCalled();
});
