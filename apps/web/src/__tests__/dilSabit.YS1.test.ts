/**
 * YS1c · Y320 (3) — site testlerinin dili makinenin yereline bağlı DEĞİL, TR'ye sabit (`_dilTr.kurulum.ts`, vitest `setupFiles`).
 * 25-11 site-ci: GitHub ubuntu koşucusunda `navigator.language` en-US → EN bayrağı açık site İngilizce açıldı → 12 dosya kırmızı.
 * Kapı (makineden bağımsız): (1) kurulum işlevi İngilizce yerelli SAHTE köke uygulanınca dil tr-TR olur, diğer özellikler gerçek
 * nesneden okunur; (2) vite.config bu kurulum dosyasını `setupFiles`'ta taşır; (3) süreçte etkin navigator dili tr-TR ve i18n TR açılır.
 * Sahte EN ALT katta: `navigator` nesnesi (ürün kodu — src/i18n — gerçek).
 */
import { describe, expect, it, vi } from 'vitest'
import VITE_YAPILANDIRMA from '../../vite.config.ts?raw'
import { dilTrSabitle } from './_dilTr.kurulum'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true

describe('YS1c site test dili TR sabit (Y320)', () => {
  it('KRİTİK: İngilizce yerelli kökte (GitHub koşucusu) dil tr-TR olur; diğer navigator özellikleri GERÇEK nesneden', () => {
    const gercek = { language: 'en-US', userAgent: 'Node.js/22', hardwareConcurrency: 4 }
    const kok: { navigator?: Navigator } = { navigator: gercek as unknown as Navigator }
    dilTrSabitle(kok)
    expect(kok.navigator?.language).toBe('tr-TR')
    expect(kok.navigator?.userAgent).toBe('Node.js/22')
    expect(kok.navigator?.hardwareConcurrency).toBe(4)
    expect(gercek.language).toBe('en-US') // gerçek nesne değiştirilmez (yalnız okuma sarmalanır)
  })

  it('KRİTİK: vite.config kurulum dosyasını setupFiles ile HER test dosyasından önce yükler', () => {
    expect(VITE_YAPILANDIRMA).toMatch(/setupFiles:\s*\[\s*'\.\/src\/__tests__\/_dilTr\.kurulum\.ts'\s*\]/)
  })

  it('bu süreçte navigator dili tr-TR ve i18n (bayrak açık, seçim / adres yok) TR açılır', async () => {
    expect(globalThis.navigator.language).toBe('tr-TR')
    expect(typeof globalThis.navigator.userAgent).toBe('string')
    vi.resetModules()
    const i18n = (await import('../i18n/index')).default
    expect(i18n.language).toBe('tr')
  })
})
