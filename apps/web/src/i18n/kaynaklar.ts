/**
 * SİTE KATALOG KAYNAKLARI — `src/i18n/{tr,en}/<ad-alanı>.json` (arayüzle AYNI düzen ve kural; bkz. `apps/ui/src/i18n/kaynaklar.ts`).
 * Yeni ad alanı: `scripts/i18n/katalog.py adalani-ekle site <ad>` (iki dilin dosyasını açar, bu dosyayı günceller).
 */
import trOrtak from './tr/ortak.json'
import enOrtak from './en/ortak.json'
import trAna from './tr/ana.json'
import enAna from './en/ana.json'
import trEkranlar from './tr/ekranlar.json'
import enEkranlar from './en/ekranlar.json'
import trHata from './tr/hata.json'
import enHata from './en/hata.json'
import trBaslatici from './tr/baslatici.json'
import enBaslatici from './en/baslatici.json'
import trOzellikler from './tr/ozellikler.json'
import enOzellikler from './en/ozellikler.json'
import trDestek from './tr/destek.json'
import enDestek from './en/destek.json'
import trBulunamadi from './tr/bulunamadi.json'
import enBulunamadi from './en/bulunamadi.json'

export const trKaynak = {
  ortak: trOrtak,
  ana: trAna,
  ekranlar: trEkranlar,
  hata: trHata,
  baslatici: trBaslatici,
  ozellikler: trOzellikler,
  destek: trDestek,
  bulunamadi: trBulunamadi,
}

export const enKaynak: typeof trKaynak = {
  ortak: enOrtak,
  ana: enAna,
  ekranlar: enEkranlar,
  hata: enHata,
  baslatici: enBaslatici,
  ozellikler: enOzellikler,
  destek: enDestek,
  bulunamadi: enBulunamadi,
}

export const kaynaklar = {
  tr: { translation: trKaynak },
  en: { translation: enKaynak },
} as const
