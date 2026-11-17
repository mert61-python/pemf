// Author: mertaygn, cglrgrkn
/* Sayı / para biçimi ETKİN DİLE göre (I18N): tr → 'tr-TR' (₺1.990), en → 'en-GB' (₺1,990). Türkçe çıktı eski
   `toLocaleString('tr-TR')` ile BAYT BAYT aynıdır; İngilizce okuyucu "₺1.990"ı ₺1,99 sanmasın.
   Y295 (17-11, sahip): İngilizce biçim İNGİLİZ (`en-GB` — uygulamayla aynı sözleşme; sayı ayraçları en-US ile aynı: 1,234.56).
   Para simgesi ₺ sabit kalır (EN'de "TRY" yazısına dönmez), tutar aynı. */
import i18n from '../i18n'

export const sayiYereli = (): 'tr-TR' | 'en-GB' => (i18n.language === 'en' ? 'en-GB' : 'tr-TR')
export const sayi = (n: number): string => n.toLocaleString(sayiYereli())
export const tl = (n: number): string => `₺${sayi(n)}`
