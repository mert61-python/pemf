/**
 * `aiHataMesaji` — AI isteği hatasını EYLEM söyleyen mesaja çeviren tek yer.
 *
 * SAHA 2026-09-08: masaüstünde tarayıcı `fetch(blob:)`'u CSP ile kesti → `TypeError: Failed to fetch`
 * → arayüz "Ağ veya sunucu hatası." dedi; kullanıcı "internet yokken modeller çalışmıyor" sandı,
 * backend günlüğünde iz yoktu. Bu test dört sınıfı AYRIK tutar: zaman aşımı / gönderilemedi /
 * geçersiz yanıt / bağlama-özel varsayılan. (Mutasyon: TypeError dalı silinince 2. test düşer.)
 */
import {
  AI_GECERSIZ_YANIT_MESAJI,
  AI_ISTEK_GONDERILEMEDI_MESAJI,
  AI_ZAMAN_ASIMI_MESAJI,
  aiHataMesaji,
} from "@/services/apiClient";

function adli(name: string, message: string): Error {
  const e = new Error(message);
  e.name = name;
  return e;
}

describe("aiHataMesaji sınıflandırması", () => {
  it("AbortError/TimeoutError → zaman aşımı mesajı (tekrar denemek işe yarar)", () => {
    expect(aiHataMesaji(adli("AbortError", "signal is aborted without reason"))).toBe(AI_ZAMAN_ASIMI_MESAJI);
    expect(aiHataMesaji(adli("TimeoutError", "x"))).toBe(AI_ZAMAN_ASIMI_MESAJI);
  });

  it("KRİTİK: tarayıcı fetch reddi (TypeError: Failed to fetch / Network request failed) → GÖNDERİLEMEDİ + eylem", () => {
    const m1 = aiHataMesaji(new TypeError("Failed to fetch"));
    expect(m1).toBe(AI_ISTEK_GONDERILEMEDI_MESAJI);
    expect(aiHataMesaji(new TypeError("Network request failed"))).toBe(AI_ISTEK_GONDERILEMEDI_MESAJI);
    expect(aiHataMesaji(new TypeError("Load failed"))).toBe(AI_ISTEK_GONDERILEMEDI_MESAJI);
    // Mesaj EYLEM söyler ve ham teknik metin içermez
    expect(m1).toMatch(/Çevrimdışı/);
    expect(m1).toMatch(/yeniden seç/);
    expect(m1).not.toMatch(/Failed to fetch|CSP|TypeError/);
    // Eski genel metin artık bu sınıfta KULLANILMAZ
    expect(m1).not.toBe("Ağ veya sunucu hatası.");
  });

  it("kod hatası kaynaklı TypeError (fetch reddi değil) → bağlam varsayılanı (yanlış 'ağ' teşhisi yok)", () => {
    expect(aiHataMesaji(new TypeError("Cannot read properties of undefined (reading 'x')"), "Analiz başarısız.")).toBe(
      "Analiz başarısız.",
    );
  });

  it("SyntaxError (response.json JSON değil) → geçersiz yanıt mesajı", () => {
    expect(aiHataMesaji(adli("SyntaxError", "Unexpected token < in JSON at position 0"))).toBe(AI_GECERSIZ_YANIT_MESAJI);
  });

  it("sınıflandırılamayan hata → çağıranın varsayılanı; verilmezse genel metin", () => {
    expect(aiHataMesaji(new Error("x"), "Bağlantı hatası.")).toBe("Bağlantı hatası.");
    expect(aiHataMesaji(new Error("x"))).toBe("Ağ veya sunucu hatası.");
    expect(aiHataMesaji(null)).toBe("Ağ veya sunucu hatası.");
  });
});
