/**
 * SİTE i18n BAŞLATMA (T2) — i18next + react-i18next, kaynaklar pakette (statik içe aktarma), başlatma SENKRON, `useSuspense: false`.
 * Bayrak kapalıyken dil tr; açıkken adresteki `?lang=` (YH B3) > kayıtlı seçim > tarayıcı dili. `<html lang>` her dil değişiminde eşitlenir.
 * Test (vitest kurulumu): `globalThis.__PEMF_I18N_KATI__ = true` → katalogda olmayan anahtar HATA atar.
 */
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { kaynaklar } from './kaynaklar'
import {
  type Dil,
  bayrakAcik,
  dilKaydet,
  etkinDil,
  gecerliDil,
  htmlDiliAyarla,
  kayitliDil,
  tarayiciYereli,
  urlDili,
} from './dil'
import { DIL_PARAMETRESI } from '../lib/sayfaMeta'

export { dilSecimiGorunur, etkinDil, bayrakAcik, gecerliDil, urlDili } from './dil'
export type { Dil } from './dil'

const KATI = (globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ === true

function adresArama(): string | null {
  try {
    return globalThis.location?.search ?? null
  } catch {
    return null
  }
}

/** Paylaşılan bağlantının dili (`?lang=en`) bu ziyarette ve SONRAKİ gezintide (bağlantılar parametre taşımaz) geçerli olsun diye kaydedilir. */
const adresSecimi = urlDili(adresArama())
const ilk: Dil = etkinDil(adresSecimi ?? kayitliDil(), tarayiciYereli())
if (adresSecimi && bayrakAcik()) dilKaydet(ilk)

/** Dil düğmesiyle değişince adreste `?lang=` VARSA yeni dile eşitlenir (yeniden yüklemede eski dile dönmesin); yoksa adrese dokunulmaz. */
function adresDiliniEsitle(d: Dil): void {
  try {
    const loc = globalThis.location
    if (!loc || !urlDili(loc.search)) return
    const u = new URL(loc.href)
    u.searchParams.set(DIL_PARAMETRESI, d)
    globalThis.history?.replaceState(globalThis.history.state, '', u.pathname + u.search + u.hash)
  } catch {
    /* yok say */
  }
}

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
  adresDiliniEsitle(d)
  return { dil: d, kaydedildi }
}

export default i18n
