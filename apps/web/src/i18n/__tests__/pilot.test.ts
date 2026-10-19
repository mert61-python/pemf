/**
 * I18N-0 · SİTE PİLOTU — alt bilgi + üst menü bağlantıları + ana sayfa başlığı. Türkçe (bayrak kapalı) göç öncesiyle AYNI metin; bayrak
 * açık + İngilizce seçilince İngilizce. Menü ve başlık modül düzeyi sabitte ANAHTAR saklar (`config.ts` dil değişince yeniden
 * değerlendirilmez) — gösterimde çevrilir. GERÇEK `Footer` (sunucu tarafı çizim), gerçek katalog.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true
const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' } })

const i18nMod = await import('../index')
const dilMod = await import('../dil')
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const Footer = (await import('../../components/Footer')).default
const { NAV, BRAND } = await import('../../config')

const ciz = () => renderToString(createElement(MemoryRouter, null, createElement(Footer)))

afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

describe('site pilotu', () => {
  it('Türkçe (bayrak kapalı): alt bilgi ve menü göç öncesi metinle', () => {
    const h = ciz()
    for (const m of ['Menü', 'Yasal', 'Özellikler', 'Fiyatlandırma', 'İndir', 'Destek', 'Vergi Dairesi: ', 'MERSIS: ', '. Tüm hakları saklıdır.']) {
      expect(h).toContain(m)
    }
    expect(i18nMod.default.t(BRAND.sloganAnahtari)).toBe('Veteriner PEMF Terapisinde Yeni Kontrol Standardı')
  })

  it('bayrak AÇIK + İngilizce: alt bilgi, menü ve başlık İngilizce; Türkçe kalmaz', async () => {
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    const h = ciz()
    for (const m of ['Menu', 'Legal', 'Features', 'Pricing', 'Download', 'Support', 'Tax office: ', 'All rights reserved.']) {
      expect(h).toContain(m)
    }
    for (const tr of ['Menü', 'Yasal', 'Özellikler', 'Tüm hakları saklıdır']) expect(h).not.toContain(tr)
    expect(NAV.map((n) => i18nMod.default.t(n.anahtar))).toEqual(['Features', 'Pricing', 'Download', 'Support'])
    expect(i18nMod.default.t(BRAND.sloganAnahtari)).toMatch(/Veterinary PEMF/)
  })
})
