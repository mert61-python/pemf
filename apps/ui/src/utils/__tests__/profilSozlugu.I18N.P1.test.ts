// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · profil sözlüğü (hasta / örnek / evcil hayvanım) iki dilde: TR göç öncesiyle BAYT BAYT aynı, EN'de her alan dolu ve profile göre
 * AYRI (araştırmada "patient" YOK, veterinerde "sample" YOK). `belirtme` / `tumKapsamKucuk` / `kayitlarAd` İngilizcede cümle içi ad olarak
 * kullanılır ("Start without a {{belirtme}}", "All {{tumKapsamKucuk}} {{kayitlarAd}}") — sözcük sırası bozulmasın diye çekimsiz.
 */
import { act } from "@testing-library/react-native";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { profilSozlugu } from "@/utils/profilSozlugu";

const depo = { setItem: async () => undefined };
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

const PROFILLER = [
  ["veteriner", {}],
  ["evcil hayvan sahibi", { petOwner: true }],
  ["araştırmacı", { researcher: true }],
] as const;

it("Türkçe: üç profilin sözlüğü göç öncesiyle aynı (örnek alanlar)", () => {
  expect(profilSozlugu({})).toMatchObject({ tekil: "Hasta", belirtme: "hastaya", sizBaslat: "Hastasız başlat", tumKapsamKucuk: "klinik", kayitlarAd: "hastaları", veritabani: "Hasta Veritabanı" });
  expect(profilSozlugu({ petOwner: true })).toMatchObject({ tekil: "Evcil Hayvanım", belirtme: "hayvanınıza", tumKapsamKucuk: "klinik", seansGecmisiGiris: "Hastalarınıza ait geçmiş seans kayıtları ve raporlamalar." });
  expect(profilSozlugu({ researcher: true })).toMatchObject({ tekil: "Örnek / Denek", belirtme: "örneğe", tumKapsamKucuk: "ekip", tumKapsam: "Tüm Ekip", tumListeCipi: "Tüm örnekler" });
});

it("İngilizce: her alan dolu, profile göre ayrı terim; Türkçe harf kalmadı", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  for (const [ad, secenek] of PROFILLER) {
    const s = profilSozlugu(secenek) as unknown as Record<string, string>;
    for (const [alan, deger] of Object.entries(s)) {
      expect(String(deger).trim()).not.toBe("");
      expect(deger).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/);
      expect(deger).not.toMatch(/^hasta\./); // ham anahtar sızmadı
      void alan;
    }
    void ad;
  }
  expect(profilSozlugu({}).tekil).toBe("Patient");
  expect(profilSozlugu({}).belirtme).toBe("patient");
  expect(profilSozlugu({ researcher: true }).tekil).toBe("Sample / Subject");
  expect(JSON.stringify(profilSozlugu({ researcher: true }))).not.toMatch(/patient/i);
  expect(JSON.stringify(profilSozlugu({}))).not.toMatch(/sample/i);
  expect(profilSozlugu({ petOwner: true }).tekilKisa).toBe("Your pet");
});
