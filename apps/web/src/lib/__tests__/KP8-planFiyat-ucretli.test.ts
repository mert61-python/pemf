/**
 * KP-8 · src/lib/planFiyat.ts kalan dallar — SATIŞ AÇIK (FREE_MODE=false sahtelenir; ticari-12d-ucretli-P1 deseni):
 * fiyatı tanımsız (null) ücretli plan ekranı ÇÖKERTMEZ ve uydurma rakam yazmaz: aylıkta ₺0, yıllıkta ₺0 / dönem notu ₺0, kısa özet ₺0 / ay.
 */
import { describe, expect, it, vi } from 'vitest'

const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })
vi.mock('../../config', async (orijinal) => ({
  ...(await orijinal<typeof import('../../config')>()),
  FREE_MODE: false,
}))

const i18n = (await import('../../i18n')).default
const { planFiyatGorunumu, planKisaFiyat } = await import('../planFiyat')
const { tl } = await import('../para')
const { PLANS } = await import('../../config')

const fiyatsiz = { ...PLANS.find((p) => p.paid)!, monthly: null, yearly: null, priceLabel: undefined }

describe('satış açık · fiyatı tanımsız ücretli plan', () => {
  it('aylık: ₺0 + dönem; yıllık: ₺0 + yıllık notunda ₺0; kısa özet ₺0 / ay', () => {
    expect(planFiyatGorunumu(fiyatsiz, false)).toEqual({ buyuk: tl(0), kucuk: fiyatsiz.period })
    expect(planFiyatGorunumu(fiyatsiz, true)).toEqual({
      buyuk: tl(0),
      kucuk: i18n.t('fiyat.donemYillik', { donem: fiyatsiz.period, tutar: tl(0) }),
    })
    expect(planKisaFiyat(fiyatsiz)).toBe(i18n.t('fiyat.tlAy', { tutar: tl(0) }))
  })
})
