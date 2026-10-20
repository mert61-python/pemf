// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · AI etiketleri ve ortak AI yardımcıları iki dilde: aiDetail (etiket / değer / girdi tabloları), aiHataDetayi, canliKare, ckdOnKontrol,
 * gorselSahneSayfalari, takipSerisi. TR görünüm göç öncesiyle BAYT BAYT aynı; EN doğru ve sade.
 * ⚠️ VERİ YOLU: `trValue` (AI geçmişi kaydına / özete giden metin) arayüz dili EN iken de TR kalır — kayıt dilden bağımsız.
 */
import { act } from "@testing-library/react-native";
import i18n from "i18next";

import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { DETAIL_LABELS, INPUT_LABELS, degerAdi, detailRows, fmtVal, girdiAdi, trValue } from "@/utils/aiDetail";
import { aiDetayCumlesi } from "@/utils/aiHataDetayi";
import { canliJetonMetni, canliKareDurumu } from "@/utils/canliKare";
import { ckdOnKontrol } from "@/utils/ckdOnKontrol";
import { sahneSayfalari } from "@/utils/gorselSahneSayfalari";
import { IZLENEN_OLCUTLER, takipSerisiKur } from "@/utils/takipSerisi";

const depo = { setItem: async () => undefined };

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});
async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}

const DETAY = {
  fgs_total: 4,
  pain_level: "mild pain",
  detected: true,
  class_counts: { stone: 2, cyst: 1 },
  top_1_class: "feline asthma",
  perCoil: [{ id: 1 }, { id: 2 }, { id: 3 }],
  n_patients: 5,
  duty: 40,
  pose_type: "sphinx",
  model: "gizli-teknik-alan",
  nested: { a: { b: 1 } },
  bilinmeyen_alan: "yok",
};

describe("aiDetail — ekran (dile duyarlı)", () => {
  it("TR: etiketler ve değerler göç öncesiyle aynı", () => {
    expect(detailRows(DETAY)).toEqual([
      { label: "FGS ağrı skoru", value: "4" },
      { label: "Ağrı seviyesi", value: "Hafif ağrı" },
      { label: "Yüz tespit edildi", value: "Evet" },
      { label: "Sınıf sayıları", value: "Taş: 2, Kist: 1" },
      { label: "Tahmin", value: "Kedi Astımı" },
      { label: "Bobin ayarları", value: "3 öğe" },
      { label: "Örnek/hasta sayısı", value: "5" },
      { label: "Doluluk (%)", value: "40" },
      { label: "Poz tipi", value: "Sfenks (oturmuş, önden)" },
      { label: "nested", value: "1 alan" },
      { label: "bilinmeyen_alan", value: "yok" },
    ]);
    expect(fmtVal({ a: 1, b: { c: 1 } })).toBe("a: 1…");
    expect(fmtVal({ b: { c: 1 } })).toBe("1 alan");
    expect(girdiAdi("image")).toBe("Görüntü");
    expect(girdiAdi("csv")).toBe("CSV / tablo");
    expect(girdiAdi("yok")).toBe("");
  });

  it("EN: etiketler ve değerler; çoğul 'item(s)' / 'field(s)'; bilinmeyen alan AYNEN", async () => {
    await enYap();
    expect(detailRows(DETAY)).toEqual([
      { label: "FGS pain score", value: "4" },
      { label: "Pain level", value: "Mild pain" },
      { label: "Face detected", value: "Yes" },
      { label: "Class counts", value: "Stone: 2, Cyst: 1" },
      { label: "Prediction", value: "Feline Asthma" },
      { label: "Coil settings", value: "3 items" },
      { label: "Sample/patient count", value: "5" },
      { label: "Duty (%)", value: "40" },
      { label: "Pose type", value: "Sphinx (seated, front view)" },
      { label: "nested", value: "1 field" },
      { label: "bilinmeyen_alan", value: "yok" },
    ]);
    expect(detailRows({ perCoil: [{ id: 1 }] })).toEqual([{ label: "Coil settings", value: "1 item" }]);
    expect(fmtVal({ b: { c: 1 } })).toBe("1 field");
    expect(fmtVal({ b: { c: 1 }, d: { e: 1 } })).toBe("2 fields");
    expect(fmtVal(false)).toBe("No");
    expect(girdiAdi("image")).toBe("Image");
    expect(girdiAdi("clinical")).toBe("Clinical values");
  });

  it("KRİTİK VERİ: `trValue` arayüz dili EN iken de TÜRKÇE (kayda giden özet dilden bağımsız); `degerAdi` EN", async () => {
    const trSonuc = ["feline asthma", "mild pain", "sphinx", "stone", "kutu_butun", "yok-bilinmeyen", "", "  "].map((v) => trValue(v));
    expect(trSonuc).toEqual(["Kedi Astımı", "Hafif ağrı", "Sfenks (oturmuş, önden)", "Taş", "Tüm Vücut", "yok-bilinmeyen", "—", "—"]);
    await enYap();
    expect(["feline asthma", "mild pain", "sphinx", "stone", "kutu_butun", "yok-bilinmeyen", "", "  "].map((v) => trValue(v))).toEqual(trSonuc);
    expect(["feline asthma", "mild pain", "sphinx", "stone", "kutu_butun", "yok-bilinmeyen"].map((v) => degerAdi(v))).toEqual([
      "Feline Asthma",
      "Mild pain",
      "Sphinx (seated, front view)",
      "Stone",
      "Whole Body",
      "yok-bilinmeyen",
    ]);
    expect(trValue(0.25)).toBe("0.25"); // sayı: dilden bağımsız
  });

  it("tablolar kapalı küme: her girdi katalog anahtarı; iki dilde dolu; 'constructor' gibi ham dizgi çevrilmez", async () => {
    const hepsi = [...Object.values(DETAIL_LABELS), ...Object.values(INPUT_LABELS)];
    expect(hepsi.length).toBeGreaterThan(100);
    for (const k of hepsi) {
      expect(k).toMatch(/^ai\.(etiket|girdi)\./);
      expect(i18n.exists(k, { lng: "tr" })).toBe(true);
      expect(i18n.exists(k, { lng: "en" })).toBe(true);
    }
    expect(degerAdi("constructor")).toBe("constructor");
    await enYap();
    expect(degerAdi("toString")).toBe("toString");
  });
});

describe("aiHataDetayi / canliKare / ckdOnKontrol", () => {
  it("TR: hata cümleleri ve canlı kare durumları göç öncesiyle aynı", () => {
    expect(aiDetayCumlesi("")).toBe("Analiz sırasında bir hata oluştu.");
    expect(aiDetayCumlesi("Part exceeded maximum size of 1024KB")).toBe(
      "Görüntü/dosya çok büyük. Lütfen daha küçük çözünürlüklü bir görüntü seçip tekrar deneyin.",
    );
    expect(aiDetayCumlesi("cannot identify image file")).toBe("Görüntü okunamadı. Lütfen geçerli bir dosya seçin (.png, .jpg veya .tif).");
    expect(aiDetayCumlesi("Görüntü çok büyük (> 25 MB)")).toBe("Görüntü çok büyük (> 25 MB)"); // sunucunun Türkçe iletisi AYNEN
    expect(aiDetayCumlesi("some english internal text")).toBe("Analiz sırasında bir hata oluştu.");
    expect(canliJetonMetni(3)).toBe("Bu canlı oturumda 3 jeton (dakika başına 1; sonuçsuz kareler ücretsiz)");
    expect(canliKareDurumu("/vision/landmark", true, 200, { status: "success", detected: false }).metin).toBe(
      "Son kare: kedi yüzü bulunamadı — kedinin yüzünü kameraya karşıdan ve yakın tutun.",
    );
    expect(canliKareDurumu("/vision/segmentation", true, 200, { status: "success", cat_count: 0 }).metin).toBe(
      "Son kare: kedi bulunamadı — kedinin tümü kadraja girsin.",
    );
    expect(canliKareDurumu("/vision/x", true, 200, { status: "success", bulunamadi_mesaji: "Sunucu notu" })).toEqual({ tur: "bulunamadi", metin: "Son kare: Sunucu notu" });
    expect(canliKareDurumu("/vision/x", true, 200, { status: "success", girdi_dogrulama: { dogrulandi: false, uyari: "Düşük ışık" } })).toEqual({
      tur: "sonuc",
      metin: "Son kare analiz edildi — Düşük ışık",
    });
    expect(canliKareDurumu("/vision/x", true, 200, { status: "success" })).toEqual({ tur: "sonuc", metin: "Son kare analiz edildi." });
    expect(canliKareDurumu("/vision/x", false, 503, {})).toEqual({ tur: "red", metin: "Son kare analiz edilemedi: sunucu yanıtı 503" });
    expect(
      canliKareDurumu("/vision/thermal", false, 422, { detail: "Görüntü termal kamera görüntüsüne benzemiyor (örnek)" }).metin,
    ).toBe("Seçili kamera termal görüntü vermiyor — termal kamerayı seçin. (Görüntü termal kamera görüntüsüne benzemiyor (örnek))");
    expect(ckdOnKontrol({ sc: 1 })).toBe(
      "Analiz için en az 6 alan doldurun (şu an 1) ve böbrek işlevine dair en az bir değer girin: bu, sg, al, hemo. Bulgu düğmeleri tek başına yeterli değildir.",
    );
    expect(ckdOnKontrol({ a: 1, b: 2, c: 3, d: 4, e: 5, sc: 1 })).toBeNull();
  });

  it("EN: hata cümleleri, canlı kare durumları (+ jeton çoğulu) ve CKD ön kontrol; sunucudan gelen metin AYNEN", async () => {
    await enYap();
    expect(aiDetayCumlesi("")).toBe("An error occurred during the analysis.");
    expect(aiDetayCumlesi("Part exceeded maximum size of 1024KB")).toBe("The image/file is too large. Please choose an image with a lower resolution and try again.");
    expect(aiDetayCumlesi("cannot identify image file")).toBe("The image could not be read. Please choose a valid file (.png, .jpg or .tif).");
    expect(aiDetayCumlesi("Görüntü çok büyük (> 25 MB)")).toBe("Görüntü çok büyük (> 25 MB)"); // sunucu metni: sunucu dil katmanı ayrı grup
    expect(canliJetonMetni(1)).toBe("In this live session: 1 credit (1 per minute; frames with no result are free)");
    expect(canliJetonMetni(3)).toBe("In this live session: 3 credits (1 per minute; frames with no result are free)");
    expect(canliKareDurumu("/vision/landmark", true, 200, { status: "success", detected: false }).metin).toBe(
      "Last frame: cat face not found — hold the cat's face close to the camera, facing it.",
    );
    expect(canliKareDurumu("/vision/segmentation", true, 200, { status: "success", cat_count: 0 }).metin).toBe(
      "Last frame: cat not found — make sure the whole cat is in the frame.",
    );
    expect(canliKareDurumu("/vision/x", true, 200, { status: "success", bulunamadi_mesaji: "Sunucu notu" }).metin).toBe("Last frame: Sunucu notu");
    expect(canliKareDurumu("/vision/x", true, 200, { status: "success", girdi_dogrulama: { dogrulandi: false, uyari: "Düşük ışık" } }).metin).toBe(
      "Last frame analyzed — Düşük ışık",
    );
    expect(canliKareDurumu("/vision/x", true, 200, { status: "success" }).metin).toBe("Last frame analyzed.");
    expect(canliKareDurumu("/vision/x", false, 503, {})).toEqual({ tur: "red", metin: "Last frame could not be analyzed: server response 503" });
    // termal ret: eşleştirme sunucunun TR iletisinin parçasına bakar — EN arayüzde de çalışır
    expect(canliKareDurumu("/vision/thermal", false, 422, { detail: "Görüntü termal kamera görüntüsüne benzemiyor (örnek)" }).metin).toBe(
      "The selected camera is not giving a thermal image — select the thermal camera. (Görüntü termal kamera görüntüsüne benzemiyor (örnek))",
    );
    expect(ckdOnKontrol({ sc: 1 })).toBe(
      "Fill in at least 6 fields (currently 1) and enter at least one value related to kidney function: bu, sg, al, hemo. The finding buttons alone are not enough.",
    );
  });
});

describe("gorselSahneSayfalari / takipSerisi", () => {
  const YANIT = { image_base64: "QUJD", image_w: 10, image_h: 10 };

  it("TR + EN: panelsiz sayfa adları (Girdi / Sonuç ↔ Input / Result); sunucunun panel adı AYNEN", async () => {
    expect(sahneSayfalari(YANIT, "file:///a.jpg").map((s) => s.ad)).toEqual(["Girdi", "Sonuç"]);
    await enYap();
    expect(sahneSayfalari(YANIT, "file:///a.jpg").map((s) => s.ad)).toEqual(["Input", "Result"]);
    expect(sahneSayfalari({ paneller: [{ k: "01_input", ad: "", image_base64: "x" }, { k: "02", ad: "Tespit", image_base64: "y" }] }, "file:///a.jpg").map((s) => s.ad)).toEqual([
      "Input",
      "Tespit",
    ]);
  });

  it("TR + EN: takip serisi başlığı ölçüt etiketinden (Kapanma / Closure; Güven / Confidence)", async () => {
    const kayit = (m: string, t: string, ek: object) => ({ module_id: m, created_at: t, ...ek });
    const kapanma = [
      kayit("cell_scratch", "2026-10-01T10:00:00Z", { result_detail: { closure_pct: 40 } }),
      kayit("cell_scratch", "2026-10-02T10:00:00Z", { result_detail: { closure_pct: 55 } }),
    ] as never;
    const guven = [kayit("disease", "2026-10-01T10:00:00Z", { confidence: 0.5 }), kayit("disease", "2026-10-02T10:00:00Z", { confidence: 0.6 })] as never;
    expect(takipSerisiKur(kapanma)?.baslik).toBe("Kapanma");
    expect(takipSerisiKur(guven)?.baslik).toBe("Güven");
    expect(IZLENEN_OLCUTLER.em_petri.etiket).toMatch(/^ai\./); // tablo: katalog ANAHTARI
    await enYap();
    expect(takipSerisiKur(kapanma)?.baslik).toBe("Closure");
    expect(takipSerisiKur(guven)?.baslik).toBe("Confidence");
    expect(takipSerisiKur(kapanma)?.noktalar.map((n) => n.deger)).toEqual([40, 55]); // sayılar dilden bağımsız
  });
});
