/**
 * SİTE i18n BAŞLATMA (T2) — i18next + react-i18next, kaynaklar pakette (statik içe aktarma), başlatma SENKRON, `useSuspense: false`.
 * Bayrak kapalıyken dil tr; açıkken kayıtlı seçim > tarayıcı dili. `<html lang>` her dil değişiminde eşitlenir.
 * Test (vitest kurulumu): `globalThis.__PEMF_I18N_KATI__ = true` → katalogda olmayan anahtar HATA atar.
 */
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { kaynaklar } from './kaynaklar'
import { type Dil, dilKaydet, etkinDil, gecerliDil, htmlDiliAyarla, kayitliDil, tarayiciYereli } from './dil'

export { dilSecimiGorunur, etkinDil, bayrakAcik, gecerliDil } from './dil'
export type { Dil } from './dil'

const KATI = (globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ === true

const ilk: Dil = etkinDil(kayitliDil(), tarayiciYereli())

/** index.html'deki statik `<title>` / `<meta name=description>` (SEO, JS'ten önce) çalışma anında etkin dile göre yeniden yazılır; TR değer index.html ile birebir aynı. */
function sayfaMetniniAyarla(): void {
  try {
    if (typeof document === 'undefined') return
    document.title = i18n.t('ortak.sayfa.baslik')
    document.querySelector('meta[name="description"]')?.setAttribute('content', i18n.t('ortak.sayfa.aciklama'))
  } catch {
    /* yok say: sayfa metni statik kalır */
  }
}
try {
  void i18n.use(initReactI18next).init({
    resources: kaynaklar,
    lng: ilk,
    fallbackLng: 'tr',
    supportedLngs: ['tr', 'en'],
    load: 'languageOnly',
    nsSeparator: false,
    keySeparator: '.',
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
    returnNull: false,
    returnEmptyString: false,
    initAsync: false,
    saveMissing: KATI,
    missingKeyHandler: KATI
      ? (_dil: readonly string[], _ns: string, anahtar: string) => {
          throw new Error(`[i18n] katalogda olmayan anahtar: "${anahtar}"`)
        }
      : false,
  })
  i18n.on('languageChanged', (l: string) => {
    htmlDiliAyarla(gecerliDil(l) ?? 'tr')
    sayfaMetniniAyarla()
  })
} catch {
  /* başlatma bozuksa sayfa yine açılır; t() anahtar döner */
}
htmlDiliAyarla(ilk)
sayfaMetniniAyarla()

/** Kullanıcı dil seçti (üst menü düğmesi). Bayrak kapalıyken tr kalır. Kayıt düşerse dil yine değişir; dönüş: kaydedildi mi. */
export async function dilSec(istenen: Dil): Promise<{ dil: Dil; kaydedildi: boolean }> {
  const d = etkinDil(istenen, null)
  const kaydedildi = dilKaydet(d)
  try {
    await i18n.changeLanguage(d)
  } catch {
    /* yok say */
  }
  htmlDiliAyarla(d)
  return { dil: d, kaydedildi }
}

export default i18n
