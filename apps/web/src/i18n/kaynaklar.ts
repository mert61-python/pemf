/**
 * SİTE KATALOG KAYNAKLARI — `src/i18n/{tr,en}/<ad-alanı>.json` (arayüzle AYNI düzen ve kural; bkz. `apps/ui/src/i18n/kaynaklar.ts`).
 * Yeni ad alanı: `scripts/i18n/katalog.py adalani-ekle site <ad>` (iki dilin dosyasını açar, bu dosyayı günceller).
 */
import trOrtak from './tr/ortak.json'
import enOrtak from './en/ortak.json'

export const trKaynak = {
  ortak: trOrtak,
}

export const enKaynak: typeof trKaynak = {
  ortak: enOrtak,
}

export const kaynaklar = {
  tr: { translation: trKaynak },
  en: { translation: enKaynak },
} as const
