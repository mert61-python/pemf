/**
 * YH B6 — kalan yüzeyler:
 *  (1) Fiyat / ödeme (ticari metin) İNGİLİZCEDE "bağlayıcı metin Türkçedir" notunu gösterir (yasal sayfalardaki desen); Türkçede not YOK
 *      (Türkçe sayfa eskisi gibi). Fiyat kuralı ve tutarlar DEĞİŞMEZ (yalnız not).
 *  (2) `apps/web/api` işlevleri kullanıcıya dönen her iletide makine-okur `error` kodu taşır (S-I18N.5: istemci koddan / sınıflandırıcıdan
 *      gösterir, `message` Türkçe yedektir); sitedeki iki tüketici (ödeme sayfası, hesap düğmesi iptali) hata metnini YALNIZ
 *      `odemeHatasiTurkce` sınıflandırıcısından geçirir → İngilizce kullanıcı sunucunun Türkçe iletisini GÖRMEZ.
 * Vercel'e istek YOK: yalnız kaynak + birim (i18n İngilizce).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import PRICING_SRC from '../pages/Pricing.tsx?raw'
import ODEME_SRC from '../pages/Odeme.tsx?raw'
import HESAP_SRC from '../components/AccountButton.tsx?raw'
import CHECKOUT_LIB from '../lib/checkout.ts?raw'
import API_CHECKOUT from '../../api/checkout.ts?raw'
import API_CANCEL from '../../api/cancel.ts?raw'
import API_TOKENS from '../../api/tokens.ts?raw'

const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })

const i18nMod = await import('../i18n')
const dilMod = await import('../i18n/dil')
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const TicariNot = (await import('../components/TicariNot')).default
const { odemeHatasiTurkce } = await import('../lib/authHatalari')

const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/

afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

describe('B6 · ticari metin notu', () => {
  it('İngilizcede not var ("Turkish text" bağlayıcı); Türkçede HİÇ çizilmez', async () => {
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('tr')
    expect(renderToString(createElement(TicariNot))).toBe('')
    await i18nMod.dilSec('en')
    const h = renderToString(createElement(TicariNot))
    expect(h).toContain('data-testid="ticari-not"')
    expect(h).toMatch(/binding version is the Turkish text/)
    expect(h).not.toMatch(TR_HARF)
  })

  it('fiyat sayfası ve ödeme sayfası (satış kapalı ekranı + onaydan önce) notu çizer', () => {
    expect(PRICING_SRC).toMatch(/import TicariNot from '\.\.\/components\/TicariNot'/)
    expect(PRICING_SRC.match(/<TicariNot\b/g)).toHaveLength(1)
    expect(ODEME_SRC.match(/<TicariNot\b/g)).toHaveLength(2)
    const ucretsiz = ODEME_SRC.slice(ODEME_SRC.indexOf('if (FREE_MODE)'), ODEME_SRC.indexOf('if (!plan)'))
    expect(ucretsiz).toMatch(/<TicariNot\b/)
    expect(ODEME_SRC.indexOf('<TicariNot />')).toBeLessThan(ODEME_SRC.indexOf("t('odeme.onay'"))
  })
})

describe('B6 · api iletileri', () => {
  const API: [string, string][] = [
    ['checkout', API_CHECKOUT],
    ['cancel', API_CANCEL],
    ['tokens', API_TOKENS],
  ]
  it('her kullanıcı iletisinde makine-okur error kodu', () => {
    let iletili = 0
    for (const [ad, src] of API) {
      for (const m of src.matchAll(/\.json\(\{([\s\S]*?)\}\)/g)) {
        if (!/message\s*:/.test(m[1])) continue
        iletili++
        const kod = /error\s*:\s*(?:'([^']*)'|sonuc\?\.sebep \?\? '([^']*)')/.exec(m[1])
        expect(kod, `${ad}: kodsuz ileti ${m[1].slice(0, 80)}`).not.toBeNull()
        expect(kod![1] ?? kod![2]).toMatch(/^[a-z_]+$/)
      }
    }
    expect(iletili).toBeGreaterThan(10) // boş eşleşme yeşil demesin
  })

  it('sitedeki tüketiciler hata metnini YALNIZ sınıflandırıcıdan geçirir (ham sunucu iletisi ekrana çıkmaz)', () => {
    // D6.30 (B-7.5): ödeme sayfası sunucunun makine-okur kodunu (409 · alan-özel 400) koruyan sınıflandırıcıdan geçirir; o da metni
    // kataloğdan kurar, tanımadığını `odemeHatasiTurkce`ye düşürür (ham metin yine basılmaz — zincir api/_lib/__tests__/odeme-baslatma-hatasi.D6_30).
    expect(ODEME_SRC).toMatch(/if \(error\) return setErr\(odemeBaslatmaHatasi\(\{ error, kod, alan, sebep \}\)\)/)
    expect(HESAP_SRC).toMatch(/:\s*odemeHatasiTurkce\(error\)/)
    expect(ODEME_SRC).not.toMatch(/setErr\(error\)/)
  })

  it('İngilizcede sınıflandırıcı her api / istemci Türkçe iletisini İngilizce metne çevirir', async () => {
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    const hamlar = new Set<string>()
    for (const src of [API_CHECKOUT, API_CANCEL, API_TOKENS, CHECKOUT_LIB]) {
      for (const m of src.matchAll(/(?:message|error)\s*:\s*'([^']*[çğıöşüÇĞİÖŞÜ][^']*)'/g)) hamlar.add(m[1])
      for (const m of src.matchAll(/\|\|\s*'([^']*[çğıöşüÇĞİÖŞÜ][^']*)'/g)) hamlar.add(m[1])
    }
    expect(hamlar.size).toBeGreaterThan(10)
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    for (const h of hamlar) expect(odemeHatasiTurkce(h), h).not.toMatch(TR_HARF)
    spy.mockRestore()
  })
})
