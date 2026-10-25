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
import { eslesmeMesaji, type EslesmeSonuc } from "@/services/pairing";

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

  it("KARŞIT: bağlam yalnız ret metnini değiştirir, diğer TÜM sebepler aynı kalır", () => {
    // 1-B inceleme i5: yalnız yok/bayat/hata taranıyordu. Record anahtarı `EslesmeSonuc`'un TÜM dallarını ister
    // (yeni bir sebep eklenince tür denetimi bu listeyi de güncelletir).
    // D3.47 · A-60: `jeton_yok` da bir RET'tir (bağlantı önceki cihazda kalır) — bağlam kuralı onda da geçerli
    // (`pairing.A60.kimlikYoluJeton.D3_47.test.ts`); bu "diğer sebepler" listesinin dışında.
    const tumu: Record<Exclude<EslesmeSonuc["durum"], "kod_reddedildi" | "jeton_yok">, EslesmeSonuc[]> = {
      ok: [{ durum: "ok", url: "https://ornek.invalid", deviceId: "PEMF-SAHTE" }],
      yok: [{ durum: "yok" }],
      adres_yok: [{ durum: "adres_yok" }, { durum: "adres_yok", sonGorulme: "2026-01-01T00:00:00Z" }],
      bayat: [{ durum: "bayat" }],
      hata: [{ durum: "hata" }],
      ulasilamiyor: [{ durum: "ulasilamiyor" }],
      gecersiz_adres: [{ durum: "gecersiz_adres" }],
    };
    const hepsi = Object.values(tumu).flat();
    expect(hepsi).toHaveLength(8);
    for (const s of hepsi) {
      expect(eslesmeMesaji(s, { oncekiCihazaBagli: false })).toBe(eslesmeMesaji(s, { oncekiCihazaBagli: true }));
      expect(eslesmeMesaji(s, { oncekiCihazaBagli: true })).not.toMatch(/önceki cihazda kaldı/i);
    }
  });
});
