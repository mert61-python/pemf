/**
 * I18N-0 · SİTE ALTYAPISI — senkron TR başlatma, KATI kip (eksik anahtar HATA), dil kuralı (tr* → tr, diğer → en), bayrak (kapalıyken tr,
 * düğme gizli), `<html lang>` eşitlemesi, seçimin tarayıcıda saklanması. KATI kip yalnız BU dosyada açılır (diğer site testleri kaynak
 * tarar, i18n'i içe aktarmaz) — bu yüzden modül, bayrak atandıktan SONRA dinamik içe aktarılır.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true
const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
const belge = { documentElement: { lang: '' } }
vi.stubGlobal('document', belge)

const i18nMod = await import('../index')
const dilMod = await import('../dil')
const i18n = i18nMod.default
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const DilDugmesi = (await import('../../components/DilDugmesi')).default

beforeEach(() => depo.clear())
afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18n.changeLanguage('tr')
})

describe('başlatma', () => {
  it('TR + senkron: içe aktarma biter bitmez çeviri hazır; <html lang="tr">', () => {
    expect(i18n.isInitialized).toBe(true)
    expect(i18n.language).toBe('tr')
    expect(i18n.t('ortak.dil.dugme')).toBe('EN')
    expect(belge.documentElement.lang).toBe('tr')
  })

  it('KATI kip: katalogda olmayan anahtar HATA atar', () => {
    expect(() => (i18n.t as unknown as (k: string) => string)('olmayan.anahtar')).toThrow(/katalogda olmayan anahtar/)
  })
})

describe('dil kuralı + bayrak', () => {
  it('tarayıcı dili: tr* → tr, diğer → en, boş → tr', () => {
    expect(dilMod.dileIndirge('tr-TR')).toBe('tr')
    expect(dilMod.dileIndirge('en-US')).toBe('en')
    expect(dilMod.dileIndirge('de')).toBe('en')
    expect(dilMod.dileIndirge(undefined)).toBe('tr')
  })

  it('bayrak KAPALI: İngilizce tarayıcıda da tr; düğme gizli', () => {
    dilMod.__bayrakTestiAyarla(false) // kapalı dal AÇIKÇA (depo bayrağı 14-I18N-INCELEME'de açıldı)
    expect(dilMod.dilSecimiGorunur()).toBe(false)
    expect(dilMod.etkinDil(null, 'en-US')).toBe('tr')
    expect(dilMod.etkinDil('en', 'en-US')).toBe('tr')
  })

  it('bayrak AÇIK: seçim saklanır, dil ve <html lang> değişir', async () => {
    dilMod.__bayrakTestiAyarla(true)
    expect(dilMod.dilSecimiGorunur()).toBe(true)
    const r = await i18nMod.dilSec('en')
    expect(r).toEqual({ dil: 'en', kaydedildi: true })
    expect(depo.get('pemf.dil')).toBe('en')
    expect(i18n.t('ortak.dil.dugme')).toBe('TR')
    expect(belge.documentElement.lang).toBe('en')
    expect(dilMod.etkinDil(dilMod.kayitliDil(), 'tr-TR')).toBe('en')
  })

  it('üst menü dil düğmesi bayrak kapalıyken HİÇ çizilmez; açıkken geçilecek dili gösterir', async () => {
    dilMod.__bayrakTestiAyarla(false)
    expect(renderToString(createElement(DilDugmesi))).toBe('')
    dilMod.__bayrakTestiAyarla(true)
    expect(renderToString(createElement(DilDugmesi))).toContain('>EN</button>')
    await i18nMod.dilSec('en')
    expect(renderToString(createElement(DilDugmesi))).toContain('>TR</button>')
  })

  it('bayrak kapalıyken dilSec("en") tr kalır', async () => {
    dilMod.__bayrakTestiAyarla(false)
    const r = await i18nMod.dilSec('en')
    expect(r.dil).toBe('tr')
    expect(i18n.language).toBe('tr')
  })

  it('varsayılan (gerçek) bayrak AÇIK (14-I18N-INCELEME, 2026-10-21): seçenek görünür, İngilizce tarayıcı İngilizce', () => {
    expect(dilMod.dilSecimiGorunur()).toBe(true)
    expect(dilMod.etkinDil(null, 'en-US')).toBe('en')
    expect(dilMod.etkinDil(null, 'tr-TR')).toBe('tr')
  })
})
