/**
 * KP-7 C · Y295 (17-11, sahip): sitede İngilizce sayı / para biçimi İNGİLİZ yerel ayarıyla (`en-GB`) — uygulamayla AYNI sözleşme
 * (tr → tr-TR, en → en-GB). Sayı ayraçları en-US ile aynıdır (1,234.56); para simgesi ₺ SABİT kalır (İngilizcede "TRY" yazısına
 * dönmez), tutar aynı. Türkçe AYNEN (₺1.990, 1.234,56). Dil AÇIKÇA kurulur (makine yereline yaslanmaz).
 * ÖNCE-KIRMIZI: `sayiYereli()` İngilizcede 'en-US' döndürüyordu.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true
const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })

const i18nMod = await import('../../i18n/index')
const dilMod = await import('../../i18n/dil')
const { sayiYereli, sayi, tl } = await import('../para')

afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

describe('KP-7 C · Y295 site sayı / para biçimi', () => {
  it('İngilizce: yerel ayar en-GB; 1,234.56 · ₺1,990 (simge ₺, "TRY" yok)', async () => {
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    expect(sayiYereli()).toBe('en-GB')
    expect(sayi(1234.56)).toBe('1,234.56')
    expect(tl(1990)).toBe('₺1,990')
    expect(tl(1990)).not.toMatch(/TRY/)
  })

  it('Türkçe AYNEN: yerel ayar tr-TR; 1.234,56 · ₺1.990', async () => {
    expect(sayiYereli()).toBe('tr-TR')
    expect(sayi(1234.56)).toBe('1.234,56')
    expect(tl(1990)).toBe('₺1.990')
  })
})
