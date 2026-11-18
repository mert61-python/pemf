// Author: mertaygn, cglrgrkn
/**
 * ODD K maddeleri (ODK-B keşfi 18-11 "kullanıcı dostluğu") — birim düzeyi kapılar:
 *  K-4  kamera açıkken 3B konum rozeti "kamera açılınca ölçülür" DEMEZ ("ölçülüyor").
 *  K-6  harita başlığı SEÇİLEN dozda beklenen alanı söyler; hedef / çevre oranı ≈ 1 ise "bu dozda odak yok".
 *  K-8  geçmiş kartı tarihi etkin dilin biçiminde (Y295; EN'de ham ISO görünüyordu); yüzde TR "%100".
 *  K-11 canlı kart: AI Pro ODAK seansında "DUTY (AI planı, bobin 1)" yerine seçilen ODAK dozu + bobin sayısı; ilerleme TR "%2".
 *  K-2  araştırma profili sözlüğü (menü / arama / boş liste / özet / geçmiş araması / sahipsiz kayıt) — klinik AYNEN.
 */
import { act, render } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { KalibrasyonRozeti } from "@/components/domain/aipro/KalibrasyonRozeti";
import { OdakOzeti } from "@/components/domain/aipro/OdakOzeti";
import { SessionProgressCard } from "@/components/domain/SessionProgressCard";
import { seansTarihi } from "@/screens/TreatmentHistoryScreen";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { canliYogunluk, YOGUNLUK_ETIKETI_BUYUK } from "@/utils/yogunlukGosterimi";

jest.mock("@/i18n/kritik", () => ({ ...jest.requireActual("@/i18n/kritik"), useKritikDil: () => undefined }));

async function dil(d: "tr" | "en") {
  await act(async () => {
    await i18n.changeLanguage(d);
  });
}
afterEach(async () => {
  await dil("tr");
});

const metin = (u: ReturnType<typeof render>) => JSON.stringify(u.toJSON());

it("KRİTİK K-4: kamera açıkken (yöntem henüz yok) rozet 'ölçülüyor'; kapalıyken eski metin", () => {
  const acik = render(<KalibrasyonRozeti yontem="" kameraAcik />);
  expect(metin(acik)).toContain("3B konum ölçülüyor — kamera açık, ilk ölçüm bekleniyor.");
  expect(metin(acik)).not.toContain("kamera açılınca ölçülür");
  const kapali = render(<KalibrasyonRozeti yontem="" />);
  expect(metin(kapali)).toContain("kamera açılınca ölçülür");
});

const ODAK = { kip: "KUYUCUK", doz_mT: 0.6, beklenen_mT: 0.6, tavan_mT: 1.7, cevre_mT: 0.59, oran: 1.02, pay_yuzde: 5,
  kuyular: [{ etiket: "A1", px: [1, 1], mT: 0.6, secili: true }, { etiket: "A2", px: [2, 1], mT: 0.59 }] };

it("KRİTİK K-6: harita başlığı seçilen dozu söyler; oran ≈ 1 → 'bu dozda odak yok' (TR + EN)", async () => {
  const u = render(<OdakOzeti odak={ODAK} />);
  expect(u.getByTestId("odak-harita-baslik").props.children).toBe(
    "Kuyular — seçilen dozda (0,60 mT) beklenen tepe alan (mT), plaka kameradaki yönüyle",
  );
  expect(u.getByTestId("odak-odak-yok").props.children).toBe(
    "Bu dozda odak yok: hedef komşularından güçlü değil (oran 1,0×) — komşu kuyular da benzer alan alır.",
  );
  await dil("en");
  const e = render(<OdakOzeti odak={ODAK} />);
  expect(e.getByTestId("odak-odak-yok").props.children).toContain("No focus at this dose");
});

it("KARŞIT K-6: oran belirgin (≥ 1,1) ya da düzgünlük kipi → 'odak yok' YOK", () => {
  expect(render(<OdakOzeti odak={{ ...ODAK, oran: 1.6 }} />).queryByTestId("odak-odak-yok")).toBeNull();
  expect(render(<OdakOzeti odak={{ ...ODAK, kip: "TUM_PETRI", oran: 0.9 }} />).queryByTestId("odak-odak-yok")).toBeNull();
});

it("KRİTİK K-8: geçmiş kartı tarihi etkin dilde (TR 18.11.2026 14:47 · EN 18/11/2026, 14:47); bozuk değer ham kalır", async () => {
  const s = { session_date: "2026-11-18", start_time: "14:47:52" };
  expect(seansTarihi(s)).toBe("18.11.2026 14:47");
  await dil("en");
  expect(seansTarihi(s)).toBe("18/11/2026, 14:47");
  expect(seansTarihi({ session_date: "dun", start_time: "" })).toBe("dun");
  const ep = new Date(2026, 10, 18, 9, 5).getTime() / 1000;
  expect(seansTarihi({ started_epoch: ep, session_date: "x" })).toBe("18/11/2026, 09:05");
});

it("KRİTİK K-11: ODAK seansında canlı yoğunluk = ODAK dozu + bobin sayısı; öncelik ölçülen > kayıt > ODAK > duty", async () => {
  const y = canliYogunluk({ odakDozMt: 0.6, odakBobinSayisi: 7, dutyTemsilYuzde: 36.2 });
  expect(y).toEqual({ tur: "odak", deger: "0.60 mT · 7 bobin" });
  expect(YOGUNLUK_ETIKETI_BUYUK.odak).toBe("ODAK DOZU (hedef)");
  expect(canliYogunluk({ odakDozMt: 0.6, odakBobinSayisi: 7, measuredIntensityMt: 0.5 }).tur).toBe("olculen");
  expect(canliYogunluk({ odakDozMt: 0, dutyTemsilYuzde: 36.2 }).tur).toBe("duty");
  expect(canliYogunluk({ odakDozMt: 0.6 }).deger).toBe("0.60 mT · 0 bobin");
  await dil("en");
  expect(canliYogunluk({ odakDozMt: 0.6, odakBobinSayisi: 1 }).deger).toBe("0.60 mT · 1 coil");
  expect(YOGUNLUK_ETIKETI_BUYUK.odak).toBe("ODAK DOSE (target)");
});

it("KRİTİK K-11: canlı kart ilerleme yüzdesi TR '%2' (EN '2%'); ODAK dozu kartta", async () => {
  const p = {
    isActive: true, mode: "AI Pro · Petri Kuyu · Kuyu C6", elapsedSec: 4, remainingSec: 176, durationSec: 180, frequencyHz: 100,
    intensityMt: 0, odakDozMt: 0.6, odakBobinSayisi: 7, onStop: () => {}, onEmergencyStop: () => {},
  };
  const u = render(<SessionProgressCard {...p} />);
  expect(metin(u)).toContain("%2");
  expect(metin(u)).toContain("0.60 mT · 7 bobin");
  expect(metin(u)).not.toContain("DUTY (AI planı, bobin 1)");
  await dil("en");
  expect(metin(render(<SessionProgressCard {...p} />))).toContain("2%");
});

it("KRİTİK K-2: araştırma sözlüğü Örnek / Numune dili; klinik AYNEN", () => {
  const a = profilSozlugu({ researcher: true });
  expect([a.menuAd, a.araYer, a.bosListe, a.ozetBaslik, a.gecmisAraYer, a.sahipsizKayit]).toEqual([
    "Örnekler", "Örnek ara...", "Henüz örnek kaydı yok.", "Örnek Özeti", "Örnek, not veya tarih ara...", "Sahipsiz örnek",
  ]);
  const k = profilSozlugu({});
  expect([k.menuAd, k.araYer, k.bosListe, k.ozetBaslik, k.gecmisAraYer, k.sahipsizKayit]).toEqual([
    "Hastalar", "Hasta veya Sahip Ara...", "Henüz hasta kaydı yok.", "Hasta Özeti", "Hasta, Not veya Tarih ara...", "Bilinmeyen Hasta",
  ]);
});
