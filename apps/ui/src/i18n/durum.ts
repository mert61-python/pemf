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

/** Yalnız i18n katmanı çağırır. Geçersiz değer → `tr` (başlıksız / geçersiz = tr kuralıyla aynı). */
export function _etkinDiliAyarla(d: string | null | undefined): Dil {
  _etkin = d === "en" ? "en" : "tr";
  return _etkin;
}
