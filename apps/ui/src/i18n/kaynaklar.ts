/**
 * KATALOG KAYNAKLARI — `src/i18n/{tr,en}/<ad-alanı>.json` dosyalarının PAKETE gömülü birleşimi (statik içe aktarma; ağdan yükleme YOK).
 *
 * Kural (KURALLAR.md §Adlandırma): dosya adı = anahtarın ilk parçası (`ayarlar.json` → `t("ayarlar.dil.baslik")`).
 * Yeni ad alanı: `scripts/i18n/katalog.py adalani-ekle <yuzey> <ad>` iki dilin dosyasını açar ve BU dosyayı günceller (elle de olur;
 * K-1 kapısı her `tr/*.json` için burada iki içe aktarma bekler).
 * `enKaynak` `typeof trKaynak` ile türlenir → İngilizcede EKSİK ad alanı / anahtar `npm run typecheck`te kırmızı.
 */
import trAyarlar from "./tr/ayarlar.json";
import trOrtak from "./tr/ortak.json";
import enAyarlar from "./en/ayarlar.json";
import enOrtak from "./en/ortak.json";

export const trKaynak = {
  ayarlar: trAyarlar,
  ortak: trOrtak,
};

export const enKaynak: typeof trKaynak = {
  ayarlar: enAyarlar,
  ortak: enOrtak,
};

export const kaynaklar = {
  tr: { translation: trKaynak },
  en: { translation: enKaynak },
} as const;
