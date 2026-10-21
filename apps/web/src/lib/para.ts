// Author: mertaygn, cglrgrkn
/* Sayı / para biçimi ETKİN DİLE göre (I18N): tr → 'tr-TR' (₺1.990), en → 'en-US' (₺1,990). Türkçe çıktı eski
   `toLocaleString('tr-TR')` ile BAYT BAYT aynıdır; İngilizce okuyucu "₺1.990"ı ₺1,99 sanmasın. */
import i18n from '../i18n'

export const sayiYereli = (): 'tr-TR' | 'en-US' => (i18n.language === 'en' ? 'en-US' : 'tr-TR')
export const sayi = (n: number): string => n.toLocaleString(sayiYereli())
export const tl = (n: number): string => `₺${sayi(n)}`
