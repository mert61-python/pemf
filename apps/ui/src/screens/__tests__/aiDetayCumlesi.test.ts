// Author: mertaygn, cglrgrkn
/**
 * AI HATA DETAYI — kullanıcı-dostu geri bildirim (saha bulgusu 2026-08-30).
 *
 * Yara analizinde kullanıcı ham "Part exceeded maximum size of 1024KB" (Starlette İngilizce
 * teknik mesajı) görüyor, ne yapacağını anlamıyordu. 10+ AI modülü backend `detail`ini AYNEN
 * gösteriyordu. aiDetayCumlesi çerçeveden sızan İngilizce teknik metni eyleme çevirir; backend'in
 * kendi Türkçe mesajlarına DOKUNMAZ.
 */
import { aiDetayCumlesi } from "../../utils/aiHataDetayi";

describe("aiDetayCumlesi", () => {
  it("KRITIK: Starlette boyut hatası → EYLEM söyleyen Türkçe cümle", () => {
    for (const ham of [
      "Part exceeded maximum size of 1024KB.",
      "Field exceeded maximum size of 1024KB.",
      "Request Entity Too Large",
    ]) {
      const c = aiDetayCumlesi(ham);
      expect(c).toContain("çok büyük");
      expect(c).toContain("daha küçük");
      expect(c).not.toContain("exceeded"); // ham İngilizce sızmamalı
    }
  });

  it("görüntü çözümlenemedi (İngilizce) → dosya seçme yönergesi", () => {
    expect(aiDetayCumlesi("cannot identify image file")).toContain(".png");
  });

  it("KRITIK: backend TÜRKÇE mesajı AYNEN korunur (ezilmez)", () => {
    const tr = "Görüntü çok büyük (> 25 MB sınırı).";
    expect(aiDetayCumlesi(tr)).toBe(tr);
    expect(aiDetayCumlesi("Hücre tespit edilemedi.")).toBe("Hücre tespit edilemedi.");
    expect(aiDetayCumlesi("Hasta seçilmeden analiz yapılamaz.")).toContain("Hasta");
  });

  it("boş/tanınmayan → modüle-özel varsayılan", () => {
    expect(aiDetayCumlesi("", "Teşhis hatası.")).toBe("Teşhis hatası.");
    expect(aiDetayCumlesi(null, "X")).toBe("X");
    expect(aiDetayCumlesi(undefined, "X")).toBe("X");
    // saf-ASCII teknik (Türkçe ipucu yok) → varsayılan (ham İngilizce gösterme)
    expect(aiDetayCumlesi("NoneType object has no attribute foo", "Y")).toBe("Y");
  });
});
