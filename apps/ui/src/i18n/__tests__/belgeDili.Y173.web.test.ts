/**
 * @jest-environment jsdom
 */
/**
 * Y173 (S-YH.3) · ANA ARAYÜZ WEB ÇIKTISINDA `<html lang>` SEÇİLİ DİLE EŞİT.
 *
 * ÖLÇÜLEN DURUM (YH, 2026-10-22): Expo'nun ürettiği `index.html` `<html lang="en">` taşıyor ve arayüz `documentElement.lang`'a hiç
 * dokunmuyordu → Türkçe arayüzde CSS `text-transform: uppercase` etiketleri (`MetricCard`, `AiHubScreen` ckdSection / ctSubLabel /
 * scMetricLbl, `AuthScreen` sectionLabel) tarayıcının İngilizce kuralıyla büyütülüyor, "i" → "I" (noktasız) çıkıyordu. DEMA'daki Y162'nin
 * ikizi. Kural: her dil değişiminde (başlatma, kayıtlı seçim, Ayarlar) tek geçit `_etkinDiliAyarla` belge dilini de eşitler. Türkçe
 * METİN değişmez.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import i18n from "i18next";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec, kayitliDiliUygula } from "@/i18n";
import { _etkinDiliAyarla } from "@/i18n/durum";

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await i18n.changeLanguage("tr");
  _etkinDiliAyarla("tr");
  await AsyncStorage.clear();
});

describe("Y173 · belge dili", () => {
  it("tek geçit belge dilini eşitler; geçersiz değer tr", () => {
    document.documentElement.lang = "en";
    _etkinDiliAyarla("tr");
    expect(document.documentElement.lang).toBe("tr");
    _etkinDiliAyarla("en");
    expect(document.documentElement.lang).toBe("en");
    _etkinDiliAyarla("xx");
    expect(document.documentElement.lang).toBe("tr");
  });

  it("Ayarlar'dan dil seçimi (bayrak açık) <html lang>'ı değiştirir — iki yön", async () => {
    __bayrakTestiAyarla(true);
    document.documentElement.lang = "en";
    await dilSec("tr", { setItem: async () => undefined });
    expect(document.documentElement.lang).toBe("tr");
    await dilSec("en", { setItem: async () => undefined });
    expect(document.documentElement.lang).toBe("en");
    await dilSec("tr", { setItem: async () => undefined });
    expect(document.documentElement.lang).toBe("tr");
  });

  it("kayıtlı seçim (açılış) <html lang>'ı uygular; depo yazılamasa da dil ve belge dili değişir", async () => {
    __bayrakTestiAyarla(true);
    document.documentElement.lang = "tr";
    await kayitliDiliUygula({ getItem: async () => "en" });
    expect(document.documentElement.lang).toBe("en");
    const r = await dilSec("tr", {
      setItem: async () => {
        throw new Error("depo yok");
      },
    });
    expect(r.kaydedildi).toBe(false);
    expect(document.documentElement.lang).toBe("tr");
  });

  it("bayrak KAPALIYKEN belge dili her zaman tr (İngilizce gizliyken Türkçe büyük harf)", async () => {
    __bayrakTestiAyarla(false);
    document.documentElement.lang = "en";
    await dilSec("en", { setItem: async () => undefined });
    expect(document.documentElement.lang).toBe("tr");
  });
});
