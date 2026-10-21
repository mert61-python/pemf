/**
 * YH B4 — dil seçici her yerde görünür ve erişilebilir: üst menü (masaüstü), mobil menü, alt bilgi (her sayfa, her genişlik); etiket geçilecek
 * dilin KENDİ adı ("English" / "Türkçe"); erişilebilir adı sayfa dilinde; klavye odağı görünür; bayrak kapalıyken HİÇBİR yerde çizilmez.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import HEADER_SRC from '../Header.tsx?raw'
import DUGME_SRC from '../DilDugmesi.tsx?raw'

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
const { MemoryRouter } = await import('react-router-dom')
const Footer = (await import('../Footer')).default

const altBilgi = () => renderToString(createElement(MemoryRouter, null, createElement(Footer)))

afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

describe('B4 · dil seçici', () => {
  it('alt bilgide (her sayfa) görünür: Türkçe sayfada "English", İngilizce sayfada "Türkçe"; erişilebilir ad sayfa dilinde', async () => {
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('tr')
    let h = altBilgi()
    expect(h).toContain('data-testid="dil-dugmesi-altbilgi"')
    expect(h).toContain('aria-label="Dili değiştir: English"')
    expect(h).toContain('<span lang="en">English</span>')
    expect(h).toContain('>Dil<')
    await i18nMod.dilSec('en')
    h = altBilgi()
    expect(h).toContain('aria-label="Change language: Türkçe"')
    expect(h).toContain('<span lang="tr">Türkçe</span>')
    expect(h).toContain('>Language<')
  })

  it('bayrak KAPALI: alt bilgide dil seçici (ve "Dil" etiketi) HİÇ yok', () => {
    dilMod.__bayrakTestiAyarla(false)
    const h = altBilgi()
    expect(h).not.toContain('dil-dugmesi')
    expect(h).not.toContain('>Dil<')
  })

  it('üst menü (masaüstü) + mobil menü: iki ayrı yerleşim, mobil kendi test kimliğiyle', () => {
    expect(HEADER_SRC.match(/<DilDugmesi\b[^>]*\/>/g)).toEqual(['<DilDugmesi />', '<DilDugmesi testId="dil-dugmesi-mobil" />'])
  })

  it('klavye: <button> + görünür odak halkası (focus-visible)', () => {
    expect(DUGME_SRC).toMatch(/<button\s+type="button"/)
    expect(DUGME_SRC).toContain('focus-visible:outline-2')
  })
})
