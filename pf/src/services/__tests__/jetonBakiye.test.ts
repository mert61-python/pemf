// Author: mertaygn
/**
 * JETON ROZETİ — "sahte sayı gösterme" kapıları (sahip isteği 2026-09-13).
 *
 * Bakiye göstermek kolay, YANLIŞ bakiye göstermek tehlikeli. Korunan üç yalan sınıfı:
 *
 *  1. Ücretlendirme KAPALIYKEN "0" yazmak → sınırsız çalışan klinikte "hakkın bitti" sanısı.
 *     (Bugün canlıda `PEMF_JETON_ENFORCED=0` ve kimsenin bakiye satırı yok.)
 *  2. Okunamadığında "0" yazmak → internetsiz klinikte çalışan sistemi bitmiş göstermek.
 *     Bu ürün internetsiz çalışır; bakiye Supabase'den okunur ve o an düşer.
 *  3. Kullandıkça-öde modelinde "kalan" yazmak → o modelde bakiye KAVRAMI yok, borç birikir.
 */
import { bakiyeDurumu, bakiyeMetni, JETON_KAPALI } from "@/services/jetonBakiye";

describe("bakiyeMetni", () => {
  it("KRİTİK: ücretlendirme KAPALIYKEN null döner (rozet ÇİZİLMEZ)", () => {
    // MUTASYON: `if (!b || !b.etkin) return null` satırını sil → KIRMIZI.
    expect(bakiyeMetni(JETON_KAPALI)).toBeNull();
    expect(bakiyeMetni({ etkin: false })).toBeNull();
    expect(bakiyeMetni(null)).toBeNull();
    expect(bakiyeMetni(undefined)).toBeNull();
  });

  it("KRİTİK: okunamadığında '—' döner, '0' DEĞİL", () => {
    // MUTASYON: `if (b.bilinmiyor) return "—"` yerine `return "0"` → KIRMIZI.
    const m = bakiyeMetni({ etkin: true, bilinmiyor: true, sebep: "cevrimdisi" });
    expect(m).toBe("—");
    expect(m).not.toBe("0");
  });

  it("gerçek bakiyeyi sayı olarak yazar", () => {
    expect(bakiyeMetni({ etkin: true, bilinmiyor: false, kalan: 99 })).toBe("99");
  });

  it("KRİTİK: kullandıkça-ödede 'kalan' değil KULLANIM yazar", () => {
    // MUTASYON: `odemeModeli === "kullandikca"` dalını sil → KIRMIZI ("0" yazardı).
    const m = bakiyeMetni({ etkin: true, bilinmiyor: false, odemeModeli: "kullandikca", borc: 7 });
    expect(m).toBe("7 kullanım");
  });

  it("bakiye 0 ise '0' yazar (gerçek sıfır GİZLENMEZ)", () => {
    // Karşıt kanıt: kural "asla 0 yazma" değil — GERÇEKTEN 0 ise söylenmeli.
    expect(bakiyeMetni({ etkin: true, bilinmiyor: false, kalan: 0 })).toBe("0");
  });
});

describe("bakiyeDurumu", () => {
  it("kapalı/bilinmiyor ayrı durumlardır", () => {
    expect(bakiyeDurumu({ etkin: false })).toBe("yok");
    expect(bakiyeDurumu({ etkin: true, bilinmiyor: true })).toBe("bilinmiyor");
  });

  it("KRİTİK: en pahalı işlemin (5 jeton) altında UYARI verir", () => {
    // ⚠️ EŞİK GEREKÇESİ: AI Pro seansı 5 jeton. 5'in altındaki kullanıcı bir sonraki
    // seansı BAŞLATAMAZ — uyarı orada başlamalı, bitince değil.
    // MUTASYON: `kalan < 5` yerine `kalan < 1` yaz → KIRMIZI.
    expect(bakiyeDurumu({ etkin: true, bilinmiyor: false, kalan: 4 })).toBe("az");
    expect(bakiyeDurumu({ etkin: true, bilinmiyor: false, kalan: 5 })).toBe("normal");
    expect(bakiyeDurumu({ etkin: true, bilinmiyor: false, kalan: 99 })).toBe("normal");
  });

  it("sıfır bakiye 'bitti'dir", () => {
    expect(bakiyeDurumu({ etkin: true, bilinmiyor: false, kalan: 0 })).toBe("bitti");
  });

  it("KRİTİK: kullandıkça-ödede borç TAVANA yaklaşınca uyarır", () => {
    // Tavana ulaşmak, bakiyenin bitmesiyle AYNI sonucu doğurur (analiz reddedilir).
    // MUTASYON: `borc >= tavan` dalını sil → KIRMIZI.
    const t = { etkin: true, bilinmiyor: false, odemeModeli: "kullandikca", borcTavani: 300 };
    expect(bakiyeDurumu({ ...t, borc: 300 })).toBe("bitti");
    expect(bakiyeDurumu({ ...t, borc: 275 })).toBe("az");
    expect(bakiyeDurumu({ ...t, borc: 10 })).toBe("normal");
  });
});
