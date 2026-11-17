/**
 * KP-8 · src/lib/planFiyat.ts kalan dal — ÜCRETSİZ DÖNEM (FREE_MODE=true — üretim ayarı): aylık ücreti tanımsız (null) ücretli plan
 * "şu an ücretsiz" der ve küçük nottaki "test sonrası" tutarı ₺0 yazar (uydurma rakam YOK, çökmez).
 */
import { describe, expect, it, vi } from 'vitest'

const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })

const i18n = (await import('../../i18n')).default
const { planFiyatGorunumu } = await import('../planFiyat')
const { tl } = await import('../para')
const { FREE_MODE, PLANS } = await import('../../config')

describe('ücretsiz dönem · aylık ücreti tanımsız ücretli plan', () => {
  it('büyük: şu an ücretsiz; küçük: test sonrası ₺0', () => {
    expect(FREE_MODE).toBe(true)
    const p = { ...PLANS.find((x) => x.paid)!, monthly: null, priceLabel: undefined }
    expect(planFiyatGorunumu(p, false)).toEqual({
      buyuk: i18n.t('fiyat.suAnUcretsiz'),
      kucuk: i18n.t('fiyat.testSonrasiAy', { tutar: tl(0) }),
    })
  })
})
