// Author: mertaygn, cglrgrkn
/**
 * I18NI-A1.7 — göçün [İNCELE] ile 14'e bıraktığı ham Türkçe VERİ değeri İngilizce ekranda: FGS yüz analizi kedi yüzü BULUNAMAYINCA sunucu
 * `pain_level = "Kedi yüzü tespit edilemedi"` döner (`ai_router.py:548`; kapsam defteri ai_router muafı "[İNCELE] arayüzde ham Türkçe
 * görünür; ai.deger tablosuyla eşlenmeli (10d / 14)"). Arayüz sonuç ayrıntısı (`aiDetail.detailRows` → AI sonuç kartı / AI Geçmişi ayrıntısı)
 * değeri `VALUE_LABELS`'ta bulamaz → EN'de Türkçe cümle. Bugün KIRMIZI; değer → anahtar eşlemesiyle YEŞİL; TR görünüm aynı.
 */
import { act } from "@testing-library/react-native";
import { detailRows } from "@/utils/aiDetail";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/;
// Sunucunun gerçek yanıtı (yüz yok): detected=false, fgs_total=null, pain_level=TR sabit
const YANIT = { status: "success", detected: false, fgs_total: null, pain_level: "Kedi yüzü tespit edilemedi" };

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("TR: ayrıntı satırı göç öncesiyle AYNI ('Kedi yüzü tespit edilemedi')", () => {
  const satir = detailRows(YANIT).find((r) => r.value.includes("Kedi"));
  expect(satir?.value).toBe("Kedi yüzü tespit edilemedi");
});

it("EN: FGS 'yüz yok' ayrıntısı İngilizce (Türkçe harf yok)", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const metin = detailRows(YANIT).map((r) => `${r.label}: ${r.value}`).join(" | ");
  expect(metin).not.toMatch(TR_HARF);
});
