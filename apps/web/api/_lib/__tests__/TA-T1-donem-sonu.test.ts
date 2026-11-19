// Author: mertaygn, cglrgrkn
/**
 * TA T1 (Y292-1) · İPTAL / GECİKME = ÖDENMİŞ DÖNEM SONUNA KADAR ERİŞİM — yazan taraf (ödeme yolları).
 *
 * Önce: `subscriptions.current_period_end` sütununa HİÇBİR yol değer yazmıyordu (callback / webhook / cancel) → tüketiciler
 * dönem sonunu bilemiyor, iptalde erişim ödenmiş dönemin ORTASINDA kesiliyordu. Ayrıca iyzico v2 yanıtı `data` sarmalında
 * (checkout sonucu `data`, abonelik detayı `data.items[0]`) → düz alan okuyan kod gerçek yanıtta planı / durumu bulamıyordu.
 *
 * Düzenek: sahte `iyzipay` SDK (EN ALT kat) + sahte `fetch` (Supabase REST). `iyzico.ts` / `util.ts` GERÇEK koşar.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Gc = (err: unknown, sonuc?: unknown) => void
const sdk = vi.hoisted(() => {
  const durum = {
    form: {} as Record<string, unknown>,
    abonelik: {} as Record<string, unknown> | Error,
    iptal: { status: 'success' } as Record<string, unknown>,
    cagri: [] as string[],
  }
  class SahteIyzipay {
    subscriptionCheckoutForm = {
      retrieve: (_i: unknown, cb: Gc) => (durum.cagri.push('form'), cb(null, durum.form)),
    }
    subscription = {
      retrieve: (_i: unknown, cb: Gc) => {
        durum.cagri.push('abonelik')
        return durum.abonelik instanceof Error ? cb(durum.abonelik) : cb(null, durum.abonelik)
      },
      cancel: (_i: unknown, cb: Gc) => (durum.cagri.push('iptal'), cb(null, durum.iptal)),
    }
  }
  return { durum, SahteIyzipay }
})
vi.mock('iyzipay', () => ({ default: sdk.SahteIyzipay }))

import { abonelikVerisi, donemSonu, planDonemi } from '../iyzico'

type Kayit = { url: string; govde: Record<string, unknown> | undefined }
let kayit: Kayit[] = []
let ag = { kullanici: 200, aboRef: 200, aboSatir: [{ stripe_subscription_id: 'sub-1' }] as unknown[], upsert: 201 }
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })
function agKur() {
  kayit = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const u = String(url)
      kayit.push({ url: u, govde: init.body ? JSON.parse(String(init.body)) : undefined })
      if (u.endsWith('/auth/v1/user')) return json({ id: 'u-1', email: 'deneme@ornek.test' }, ag.kullanici)
      if (u.includes('/rpc/jeton_donem_yenile')) return new Response('', { status: 200 })
      if (u.includes('/rest/v1/subscriptions?user_id=')) return json(ag.aboSatir, ag.aboRef)
      if (u.includes('/rest/v1/subscriptions?stripe_subscription_id=')) return json([{ user_id: 'u-1' }])
      if (u.endsWith('/rest/v1/subscriptions')) return new Response(ag.upsert === 201 ? null : 'patladi', { status: ag.upsert })
      throw new Error(`beklenmeyen ağ isteği: ${u}`)
    }),
  )
}
const yazilan = () => kayit.find((k) => k.url.endsWith('/rest/v1/subscriptions'))?.govde as Record<string, unknown>

function sahteRes() {
  const res = { kod: 0, govde: undefined as unknown, yer: '' } as Record<string, unknown> & { kod: number; govde: unknown; yer: string }
  res.status = (k: number) => ((res.kod = k), res)
  res.json = (g: unknown) => ((res.govde = g), res)
  res.redirect = (k: number, yer: string) => ((res.kod = k), (res.yer = yer), res)
  return res
}

const GUN = 864e5
const SIMDI = Date.UTC(2026, 10, 19, 12, 0, 0) // 19 Kasım 2026 12:00 UTC
const iso = (ms: number) => new Date(ms).toISOString()

beforeEach(() => {
  vi.stubEnv('IYZICO_URI', 'https://api.ornek-odeme.test')
  vi.stubEnv('IYZICO_API_KEY', 'test-anahtar-1')
  vi.stubEnv('IYZICO_SECRET_KEY', 'test-gizli-1')
  vi.stubEnv('IYZICO_MERCHANT_ID', 'test-isyeri-1')
  vi.stubEnv('IYZICO_WEBHOOK_STRICT', '')
  vi.stubEnv('IYZICO_PLAN_PRO_MONTHLY', 'plan-pro-aylik')
  vi.stubEnv('IYZICO_PLAN_PROPLUS_YEARLY', 'plan-proplus-yillik')
  vi.stubEnv('SUPABASE_URL', 'https://proje-ornek.supabase.test')
  vi.stubEnv('SUPABASE_ANON_KEY', 'test-anon')
  vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'test-servis-anahtari')
  sdk.durum.cagri.length = 0
  sdk.durum.iptal = { status: 'success' }
  ag = { kullanici: 200, aboRef: 200, aboSatir: [{ stripe_subscription_id: 'sub-1' }], upsert: 201 }
  agKur()
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(SIMDI)
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('iyzico.ts · yanıt açma + dönem sonu', () => {
  it('abonelikVerisi: checkout `data` · detay `data.items[0]` · düz şekil · boş liste', () => {
    expect(abonelikVerisi({ data: { referenceCode: 'a' } })).toEqual({ referenceCode: 'a' })
    expect(abonelikVerisi({ data: { items: [{ referenceCode: 'b' }] } })).toEqual({ referenceCode: 'b' })
    expect(abonelikVerisi({ data: { items: [] } })).toEqual({})
    expect(abonelikVerisi({ data: { items: [null] } })).toEqual({})
    expect(abonelikVerisi({ referenceCode: 'c' })).toEqual({ referenceCode: 'c' })
    expect(abonelikVerisi({ data: 'metin', referenceCode: 'd' })).toEqual({ data: 'metin', referenceCode: 'd' })
  })

  it('planDonemi: aylık / yıllık / tanınmayan / boş', () => {
    expect(planDonemi('plan-pro-aylik')).toBe('monthly')
    expect(planDonemi('plan-proplus-yillik')).toBe('yearly')
    expect(planDonemi('baska-plan')).toBeNull()
    expect(planDonemi('')).toBeNull()
  })

  it('KAYNAK 1: ödenmiş (SUCCESS) siparişlerin EN GEÇ endPeriod\'u; WAITING / FAILED dönem SAYILMAZ (durumdan bağımsız)', () => {
    const a = {
      subscriptionStatus: 'CANCELED',
      orders: [
        { orderStatus: 'SUCCESS', startPeriod: SIMDI - 40 * GUN, endPeriod: SIMDI - 10 * GUN },
        { orderStatus: 'success', startPeriod: SIMDI - 10 * GUN, endPeriod: SIMDI + 20 * GUN },
        { orderStatus: 'SUCCESS', endPeriod: SIMDI - 5 * GUN },
        { orderStatus: 'WAITING', endPeriod: SIMDI + 50 * GUN },
        { orderStatus: 'FAILED', endPeriod: SIMDI + 80 * GUN },
        { orderStatus: 'SUCCESS', endPeriod: 'bozuk' },
        { endPeriod: SIMDI + 90 * GUN },
        null,
        'metin',
      ],
    }
    expect(donemSonu(a)).toBe(iso(SIMDI + 20 * GUN))
  })

  it('tarih biçimleri: sayı dizesi ve ISO da okunur; sıfır / sonsuz / aralık dışı okunmaz', () => {
    const tek = (endPeriod: unknown) => donemSonu({ orders: [{ orderStatus: 'SUCCESS', endPeriod }] })
    expect(tek(String(SIMDI + GUN))).toBe(iso(SIMDI + GUN))
    expect(tek('2026-12-19T12:00:00.000Z')).toBe('2026-12-19T12:00:00.000Z')
    for (const v of [0, -5, Infinity, NaN, 9e15, '99999999999999999999', '', '   ', true]) expect(tek(v)).toBeNull()
  })

  it('KAYNAK 2: sipariş yoksa ACTIVE → başlangıç + plan süresi (ilk dönem) · yenilenmişte "şimdi"yi içeren dönemin sonu', () => {
    const bas = SIMDI - 3 * GUN
    expect(donemSonu({ subscriptionStatus: 'ACTIVE', pricingPlanReferenceCode: 'plan-pro-aylik', startDate: bas })).toBe(
      iso(Date.UTC(2026, 11, 16, 12, 0, 0)),
    )
    // 3 ay önce başlamış aylık abonelik → 19 Kasım'ı içeren dönem 1 Aralık'ta biter
    const eski = Date.UTC(2026, 7, 1)
    expect(donemSonu({ subscriptionStatus: 'ACTIVE', pricingPlanReferenceCode: 'plan-pro-aylik', startDate: eski })).toBe(
      iso(Date.UTC(2026, 11, 1)),
    )
    // yıllık
    expect(
      donemSonu({ subscriptionStatus: 'ACTIVE', pricingPlanReferenceCode: 'plan-proplus-yillik', startDate: Date.UTC(2026, 0, 10) }),
    ).toBe(iso(Date.UTC(2027, 0, 10)))
  })

  it('ay sonu taşmaz: 31 Ocak + 1 ay = 28 Şubat (artık yılda 29)', () => {
    vi.setSystemTime(Date.UTC(2027, 1, 1))
    expect(donemSonu({ subscriptionStatus: 'ACTIVE', pricingPlanReferenceCode: 'plan-pro-aylik', startDate: Date.UTC(2027, 0, 31) })).toBe(
      iso(Date.UTC(2027, 1, 28)),
    )
    vi.setSystemTime(Date.UTC(2028, 1, 1))
    expect(donemSonu({ subscriptionStatus: 'ACTIVE', pricingPlanReferenceCode: 'plan-pro-aylik', startDate: Date.UTC(2028, 0, 31) })).toBe(
      iso(Date.UTC(2028, 1, 29)),
    )
  })

  it('PENDING (deneme) → trialEndDate; deneme bitişi yoksa null', () => {
    expect(donemSonu({ subscriptionStatus: 'PENDING', trialEndDate: SIMDI + 7 * GUN })).toBe(iso(SIMDI + 7 * GUN))
    expect(donemSonu({ subscriptionStatus: 'PENDING' })).toBeNull()
  })

  it('KARŞIT: iptal / ödenmemiş / bilinmeyen durumda TAHMİN YOK; plan / başlangıç okunamazsa null; 100 yıldan eski null', () => {
    const t = { pricingPlanReferenceCode: 'plan-pro-aylik', startDate: SIMDI - GUN }
    for (const s of ['CANCELED', 'UNPAID', 'EXPIRED', '', 'RETRY']) expect(donemSonu({ ...t, subscriptionStatus: s })).toBeNull()
    expect(donemSonu({ subscriptionStatus: 'ACTIVE', pricingPlanReferenceCode: 'yok', startDate: SIMDI })).toBeNull()
    expect(donemSonu({ subscriptionStatus: 'ACTIVE', pricingPlanReferenceCode: 'plan-pro-aylik' })).toBeNull()
    expect(donemSonu({ subscriptionStatus: 'ACTIVE', startDate: SIMDI })).toBeNull()
    expect(donemSonu({ subscriptionStatus: 'ACTIVE', pricingPlanReferenceCode: 'plan-pro-aylik', startDate: 1 }, Date.UTC(2100, 0, 1))).toBeNull()
  })

  it('simdi parametresi verilirse saat yerine o kullanılır', () => {
    const bas = Date.UTC(2026, 0, 1)
    expect(donemSonu({ subscriptionStatus: 'ACTIVE', pricingPlanReferenceCode: 'plan-pro-aylik', startDate: bas }, Date.UTC(2026, 0, 2))).toBe(
      iso(Date.UTC(2026, 1, 1)),
    )
  })
})

describe('callback · GERÇEK iyzico şekli (data sarmalı) + dönem sonu yazımı', () => {
  it('KRİTİK: `data` sarmallı checkout sonucu → abonelik yazılır ve current_period_end = başlangıç + 1 ay', async () => {
    const bas = SIMDI - 60_000
    sdk.durum.form = {
      status: 'success',
      conversationId: 'u-1',
      token: 'tk-1',
      data: {
        referenceCode: 'sub-1',
        customerReferenceCode: 'cus-1',
        pricingPlanReferenceCode: 'plan-pro-aylik',
        subscriptionStatus: 'ACTIVE',
        startDate: bas,
      },
    }
    vi.resetModules()
    const h = (await import('../../callback')).default
    const res = sahteRes()
    await h({ query: { token: 'tk-1' }, body: {} } as never, res as never)
    expect(res.yer).toBe('/download?checkout=success')
    expect(yazilan()).toMatchObject({
      user_id: 'u-1',
      tier: 'pro',
      status: 'active',
      stripe_subscription_id: 'sub-1',
      stripe_customer_id: 'cus-1',
      current_period_end: iso(Date.UTC(2026, 11, 19, 11, 59, 0)),
    })
  })

  it('düz (eski) şekil de çalışır; dönem bilinemezse alan YAZILMAZ (null basılmaz)', async () => {
    sdk.durum.form = { conversationId: 'u-1', referenceCode: 'sub-1', pricingPlanReferenceCode: 'plan-pro-aylik', subscriptionStatus: 'ACTIVE' }
    vi.resetModules()
    const h = (await import('../../callback')).default
    const res = sahteRes()
    await h({ query: { token: 'tk-1' }, body: {} } as never, res as never)
    expect(res.yer).toBe('/download?checkout=success')
    expect(yazilan()).toMatchObject({ status: 'active', stripe_subscription_id: 'sub-1' })
    expect(yazilan()).not.toHaveProperty('current_period_end')
  })
})

describe('webhook · abonelik detayı (data.items[0].orders) → dönem sonu', () => {
  async function cagir() {
    vi.resetModules()
    const h = (await import('../../webhook')).default
    const res = sahteRes()
    await h({ method: 'POST', headers: {}, body: { subscriptionReferenceCode: 'sub-1', iyziEventType: 'x' } } as never, res as never)
    return res
  }

  it('KRİTİK: yenileme (ACTIVE) → son ödenmiş siparişin endPeriod\'u yazılır', async () => {
    sdk.durum.abonelik = {
      status: 'success',
      data: {
        totalCount: 1,
        items: [
          {
            referenceCode: 'sub-1',
            customerReferenceCode: 'cus-1',
            pricingPlanReferenceCode: 'plan-pro-aylik',
            subscriptionStatus: 'ACTIVE',
            orders: [
              { orderStatus: 'SUCCESS', endPeriod: SIMDI - 5 * GUN },
              { orderStatus: 'SUCCESS', endPeriod: SIMDI + 25 * GUN },
            ],
          },
        ],
      },
    }
    const res = await cagir()
    expect(res.kod).toBe(200)
    expect(yazilan()).toMatchObject({ user_id: 'u-1', tier: 'pro', status: 'active', current_period_end: iso(SIMDI + 25 * GUN) })
  })

  it('KRİTİK: ödeme aksadı (UNPAID → past_due) → durum yazılır, dönem sonu SON ÖDENMİŞ siparişten (bekleyen sayılmaz)', async () => {
    sdk.durum.abonelik = {
      data: {
        items: [
          {
            pricingPlanReferenceCode: 'plan-pro-aylik',
            subscriptionStatus: 'UNPAID',
            orders: [
              { orderStatus: 'SUCCESS', endPeriod: SIMDI + 2 * GUN },
              { orderStatus: 'FAILED', endPeriod: SIMDI + 32 * GUN },
            ],
          },
        ],
      },
    }
    const res = await cagir()
    expect(res.kod).toBe(200)
    expect(yazilan()).toMatchObject({ status: 'past_due', current_period_end: iso(SIMDI + 2 * GUN) })
  })

  it('KARŞIT: iptal bildirimi sipariş bilgisi olmadan gelirse dönem sonu YAZILMAZ (satırdaki önceki değer korunur)', async () => {
    sdk.durum.abonelik = { data: { items: [{ pricingPlanReferenceCode: 'plan-pro-aylik', subscriptionStatus: 'CANCELED' }] } }
    const res = await cagir()
    expect(res.kod).toBe(200)
    expect(yazilan()).toMatchObject({ status: 'canceled' })
    expect(yazilan()).not.toHaveProperty('current_period_end')
  })
})

describe('cancel · iptalde ödenmiş dönemin sonu yazılır', () => {
  async function cagir() {
    vi.resetModules()
    const h = (await import('../../cancel')).default
    const res = sahteRes()
    await h({ method: 'POST', body: { token: 'jwt-1' } } as never, res as never)
    return res
  }

  it('KRİTİK: iptal başarılı → abonelik yeniden okunur, status canceled + current_period_end = son ödenmiş dönem sonu', async () => {
    sdk.durum.abonelik = {
      data: { items: [{ subscriptionStatus: 'CANCELED', orders: [{ orderStatus: 'SUCCESS', endPeriod: SIMDI + 11 * GUN }] }] },
    }
    const res = await cagir()
    expect(res.kod).toBe(200)
    expect(res.govde).toEqual({ canceled: true })
    expect(sdk.durum.cagri).toEqual(['iptal', 'abonelik'])
    expect(yazilan()).toMatchObject({ user_id: 'u-1', status: 'canceled', current_period_end: iso(SIMDI + 11 * GUN) })
  })

  it('yeniden okuma patlarsa iptal YİNE başarılı: yalnız status yazılır (önceki dönem sonu korunur), iz bırakılır', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    sdk.durum.abonelik = new Error('iyzico-okuma-yok')
    const res = await cagir()
    expect(res.kod).toBe(200)
    expect(res.govde).toEqual({ canceled: true })
    expect(yazilan()).toMatchObject({ status: 'canceled' })
    expect(yazilan()).not.toHaveProperty('current_period_end')
    expect(gunluk).toHaveBeenCalledWith('cancel: dönem sonu okunamadı (iptal BAŞARILI; önceki dönem sonu korunur)', expect.any(Error))
  })

  it('sipariş bilgisi yoksa dönem sonu yazılmaz', async () => {
    sdk.durum.abonelik = { data: { items: [{ subscriptionStatus: 'CANCELED' }] } }
    const res = await cagir()
    expect(res.kod).toBe(200)
    expect(yazilan()).not.toHaveProperty('current_period_end')
  })

  it('dönüş kolları (önceden testsizdi): GET 405 · oturum yok 401 · abonelik yok 404 · iyzico reddi 502', async () => {
    vi.resetModules()
    const h = (await import('../../cancel')).default
    const get = sahteRes()
    await h({ method: 'GET' } as never, get as never)
    expect([get.kod, get.govde]).toEqual([405, { error: 'method' }])

    ag.kullanici = 401
    const r401 = sahteRes()
    await h({ method: 'POST' } as never, r401 as never)
    expect([r401.kod, (r401.govde as Record<string, unknown>).error]).toEqual([401, 'auth'])

    ag.kullanici = 200
    ag.aboSatir = []
    const r404 = sahteRes()
    await h({ method: 'POST', body: { token: 'jwt-1' } } as never, r404 as never)
    expect([r404.kod, (r404.govde as Record<string, unknown>).error]).toEqual([404, 'no_subscription'])

    ag.aboSatir = [{ stripe_subscription_id: 'sub-1' }]
    sdk.durum.iptal = { status: 'failure', errorMessage: 'iyzico reddetti' }
    const r502 = sahteRes()
    await h({ method: 'POST', body: { token: 'jwt-1' } } as never, r502 as never)
    expect([r502.kod, r502.govde]).toEqual([502, { error: 'iyzico', message: 'iyzico reddetti' }])
    sdk.durum.iptal = { status: 'failure' }
    const r502b = sahteRes()
    await h({ method: 'POST', body: { token: 'jwt-1' } } as never, r502b as never)
    expect(r502b.govde).toEqual({ error: 'iyzico', message: 'İptal edilemedi.' })
    expect(kayit.some((k) => k.url.endsWith('/rest/v1/subscriptions'))).toBe(false) // iptal olmadıysa satır yazılmaz
  })

  it('Supabase yansıtması patlarsa iptal YİNE başarılı + uyarı; abonelik okunamazsa 500 (iptal denenmez)', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    sdk.durum.abonelik = { data: { items: [{ orders: [{ orderStatus: 'SUCCESS', endPeriod: SIMDI + GUN }] }] } }
    ag.upsert = 500
    const r = await cagir()
    expect(r.kod).toBe(200)
    expect(r.govde).toMatchObject({ canceled: true, warning: expect.stringContaining('iptal edildi') })

    ag.upsert = 201
    ag.aboRef = 500
    sdk.durum.cagri.length = 0
    const r500 = await cagir()
    expect([r500.kod, (r500.govde as Record<string, unknown>).error]).toEqual([500, 'server'])
    expect(sdk.durum.cagri).toEqual([])
    expect(gunluk).toHaveBeenCalledWith('cancel error', expect.any(Error))
  })
})
