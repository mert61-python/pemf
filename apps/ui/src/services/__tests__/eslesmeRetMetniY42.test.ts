// Author: mertaygn, cglrgrkn
/**
 * EŞLEŞTİRME KODU REDDİ — METİN BAĞLAMA GÖRE (sahip kararı Y42, 2026-10-01).
 *
 * A-52 metni ("… bağlantı önceki cihazda kaldı") YALNIZ uygulama zaten bir cihaza BAĞLIYKEN doğrudur.
 * Çevrimdışı eşleştirme rehberi (`DevicePairingGuide`) bağlantı YOKKEN açılır: orada "önceki cihaz" yoktur ve
 * cümle operatörü var olmayan bir bağlantıya güvenmeye yönlendirir. Y42 metni (birebir):
 *
 *   "Eşleştirme kodu kabul edilmedi. Bağlantı ayarı değiştirilmedi; kodu kontrol edip yeniden deneyin."
 *
 * Kural: "önceki cihazda kaldı" yalnız çağıran `oncekiCihazaBagli: true` derse söylenir; belirtilmezse
 * (yeni bir çağıran unutursa) DÜRÜST varsayılan Y42 metnidir.
 */
import { eslesmeMesaji } from "@/services/pairing";

const Y42 = "Eşleştirme kodu kabul edilmedi. Bağlantı ayarı değiştirilmedi; kodu kontrol edip yeniden deneyin.";

describe("Y42 — kod reddi metni", () => {
  it("KRİTİK: bağlantı YOKKEN metin Y42'nin BİREBİR aynısı", () => {
    expect(eslesmeMesaji({ durum: "kod_reddedildi" }, { oncekiCihazaBagli: false })).toBe(Y42);
  });

  it("KRİTİK: bağlam belirtilmezse 'önceki cihazda kaldı' DENMEZ (dürüst varsayılan)", () => {
    const m = eslesmeMesaji({ durum: "kod_reddedildi" });
    expect(m).toBe(Y42);
    expect(m).not.toMatch(/önceki cihaz/i);
  });

  it("KARŞIT (A-52): bir cihaza BAĞLIYKEN bağlantının önceki cihazda kaldığı söylenir", () => {
    const m = eslesmeMesaji({ durum: "kod_reddedildi" }, { oncekiCihazaBagli: true });
    expect(m).toMatch(/önceki cihazda kaldı/i);
    expect(m).toMatch(/kabul edilmedi/i);
  });

  it("KARŞIT: bağlam yalnız ret metnini değiştirir, diğer sebepler aynı kalır", () => {
    for (const s of [{ durum: "yok" } as const, { durum: "bayat" } as const, { durum: "hata" } as const]) {
      expect(eslesmeMesaji(s, { oncekiCihazaBagli: false })).toBe(eslesmeMesaji(s, { oncekiCihazaBagli: true }));
    }
  });
});
