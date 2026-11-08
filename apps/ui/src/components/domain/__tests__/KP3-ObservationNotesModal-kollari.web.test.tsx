/**
 * @jest-environment jsdom
 */
/**
 * KP-3 C · ObservationNotesModal kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - Sunucudan HİÇ yanıt yoksa (bağlantı koptu) ekran AÇIK kalır, not DURUR ve "kaydedilmiş olabilir — tekrar denemek güvenli"
 *    denir ("ulaşmadı" diye yanlış teşhis yok).
 *  - Tepki çipine ikinci basış seçimi KALDIRIR: gönderilen gözlem notunda yalnız seçili kalan tepki + not yer alır.
 *  - "Atla" notu ve tepkileri SİLER ve ekranı kapatır (bir sonraki hastaya bulaşmaz); hiçbir şey gönderilmez.
 * SAHTE: fetch (ağ sınırı), güvenli alan kancası, `window.alert` (yakalanır), Supabase (en alt kat). GERÇEK: modal + apiClient.
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

const NOT = "Kuyruğunu salladı";
const OTURUM = { patientName: "Boncuk", mode: "Manuel", obsKey: 1, dbSessionId: 7 };
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
const notAlani = () => s.etiket("Gözlem notları") as HTMLTextAreaElement;

it("yanıt yoksa ekran açık, not durur; 'kaydedilmiş olabilir, tekrar denemek güvenli' denir", async () => {
  const ag = jest.fn(async () => { throw new TypeError("Failed to fetch"); });
  global.fetch = ag as unknown as typeof fetch;
  const kapat = jest.fn();
  await s.ciz(<ObservationNotesModal visible session={OTURUM} onClose={kapat} />);
  await s.yaz("Gözlem notları", NOT);
  await s.metneTikla("💾 Kaydet");
  expect(ag).toHaveBeenCalledTimes(1); // POST yeniden DENENMEZ (çift kayıt riski yok)
  expect(kapat).not.toHaveBeenCalled();
  expect(notAlani().value).toBe(NOT);
  const uyarilar = uyari.mock.calls.map((c) => String(c[0])).join(" | ");
  expect(uyarilar).toContain("Sunucudan yanıt alınamadı");
  expect(uyarilar).toContain("ikinci bir kayıt oluşmaz");
});

it("tepki çipine ikinci basış seçimi kaldırır; notta yalnız seçili kalan tepki gider", async () => {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => (yontem === "POST" && yol === "/session/notes" ? [200, { status: "success" }] : undefined));
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  const kapat = jest.fn();
  await s.ciz(<ObservationNotesModal visible session={OTURUM} onClose={kapat} />);
  await s.metneTikla("Sakinleşti");
  await s.metneTikla("Sakinleşti");
  await s.metneTikla("Uyudu");
  await s.yaz("Gözlem notları", NOT);
  await s.metneTikla("💾 Kaydet");
  const istek = sunucu.kayit.find((i) => i.yontem === "POST" && i.yol === "/session/notes");
  expect((istek?.govde as { notes: string }).notes).toBe(`Uyudu — ${NOT}`);
  expect(kapat).toHaveBeenCalledTimes(1);
});

it("'Atla' notu ve tepkileri siler, ekranı kapatır; hiçbir şey gönderilmez", async () => {
  const sunucu = sahteSunucu([]);
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  const kapat = jest.fn();
  await s.ciz(<ObservationNotesModal visible session={OTURUM} onClose={kapat} />);
  await s.metneTikla("Endişeli");
  await s.yaz("Gözlem notları", NOT);
  await s.metneTikla("Atla");
  expect(kapat).toHaveBeenCalledTimes(1);
  expect(notAlani().value).toBe("");
  expect(sunucu.kayit.filter((i) => i.yol === "/session/notes")).toHaveLength(0);
  // Seçili tepki de silindi: ardından yalnız not yazılıp kaydedilirse tepki ÖNEKİ olmaz.
  await s.yaz("Gözlem notları", "ikinci");
  await s.metneTikla("💾 Kaydet");
  const istek = sunucu.kayit.find((i) => i.yontem === "POST" && i.yol === "/session/notes");
  expect((istek?.govde as { notes: string }).notes).toBe("ikinci");
});
