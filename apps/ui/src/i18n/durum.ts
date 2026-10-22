/**
 * ETKİN DİLİN BAĞIMLILIKSIZ KOPYASI — `apiClient` `X-PEMF-Dil` başlığını buradan okur.
 *
 * Neden ayrı modül: `apiClient` her yerden içe aktarılır; i18next'i ya da i18n başlatmasını içe aktarsaydı başlatma sırası / döngüsel
 * içe aktarma riski doğardı. i18n katmanı (`i18n/index.ts`) dil her değiştiğinde (başlatma dahil) burayı EŞZAMANLI günceller →
 * dil seçildikten hemen sonraki ilk istek de doğru başlığı taşır (`PROFIL_BASLIGI` deseni).
 */
export type Dil = "tr" | "en";

let _etkin: Dil = "tr";

export function etkinDilDegeri(): Dil {
  return _etkin;
}

/**
 * Yalnız i18n katmanı çağırır. Geçersiz değer → `tr` (başlıksız / geçersiz = tr kuralıyla aynı).
 *
 * Y173 (S-YH.3): web çıktısında `<html lang>` da etkin dile eşitlenir — her dil değişiminde (başlatma, kayıtlı seçim, Ayarlar) bu
 * işlevden geçilir. CSS `text-transform: uppercase` Türkçe "i"yi yalnız belge dili `tr` iken "İ" yapar; Expo'nun ürettiği
 * `index.html` `lang="en"` taşıdığı için Türkçe arayüzde büyük harfli etiketler "I" gösteriyordu (DEMA'daki Y162'nin ikizi).
 * Türkçe METİN değişmez, yalnız büyük harf görünümü. Yerelde (Android / iOS) `document` yok → dokunulmaz.
 * Kapı: `__tests__/belgeDili.Y173.web.test.ts`.
 */
export function _etkinDiliAyarla(d: string | null | undefined): Dil {
  _etkin = d === "en" ? "en" : "tr";
  if (typeof document !== "undefined" && document.documentElement) document.documentElement.lang = _etkin;
  return _etkin;
}
