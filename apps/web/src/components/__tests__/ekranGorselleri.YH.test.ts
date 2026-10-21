/**
 * YH B7 — ana sayfanın uygulama ekran görüntüleri galerisi İngilizce sayfada İNGİLİZCE arayüzlü çekimleri gösterir (`/screenshots/en/`,
 * aynı adlar); Türkçe sayfa ve Türkçe set DEĞİŞMEZ. Görsel boyut / sıkıştırma kapısı pytest'te (`test_YH_B7_site_ekran_gorselleri.py`).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })

const i18nMod = await import('../../i18n')
const dilMod = await import('../../i18n/dil')
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const { default: AppScreenshots, ekranGorseli } = await import('../AppScreenshots')

const TR_SET = Object.keys(import.meta.glob('../../../public/screenshots/*.jpg')).map((y) => y.split('/').pop())
const EN_SET = Object.keys(import.meta.glob('../../../public/screenshots/en/*.jpg')).map((y) => y.split('/').pop())

afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

describe('B7 · ekran görüntüleri iki dilde', () => {
  it('İngilizce set Türkçe setle AYNI adlar (8) — eksik / fazla görsel yok', () => {
    expect(TR_SET.length).toBe(8)
    expect([...EN_SET].sort()).toEqual([...TR_SET].sort())
  })

  it('adres: İngilizcede /screenshots/en/<ad>, Türkçede DEĞİŞMEZ', () => {
    expect(ekranGorseli('/screenshots/05-kontrol.jpg', 'en')).toBe('/screenshots/en/05-kontrol.jpg')
    expect(ekranGorseli('/screenshots/05-kontrol.jpg', 'tr')).toBe('/screenshots/05-kontrol.jpg')
  })

  it('galeri çizimi: Türkçe sayfa Türkçe seti, İngilizce sayfa İngilizce seti (8 görsel) gösterir', async () => {
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('tr')
    const tr = renderToString(createElement(AppScreenshots))
    expect(tr.match(/src="\/screenshots\/[0-9]/g)).toHaveLength(8)
    expect(tr).not.toContain('/screenshots/en/')
    await i18nMod.dilSec('en')
    const en = renderToString(createElement(AppScreenshots))
    expect(en.match(/src="\/screenshots\/en\/[0-9]/g)).toHaveLength(8)
  })
})
