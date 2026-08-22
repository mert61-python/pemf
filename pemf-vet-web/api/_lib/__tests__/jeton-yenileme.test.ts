// Author: mertaygn, cglrgrkn
/**
 * ÖDEME YENİLEMESİ JETONA BAĞLANIR — JETON-SISTEMI Adım 3 (2026-08-22).
 *
 * ÖLÇÜLEN DURUM: `api/callback.ts` ve `api/webhook.ts` yalnız `upsertSubscription` çağırıyordu;
 * `jeton_donem_yenile` HİÇ çağrılmıyordu. Yani bugün ödeme alınsa abonelik yazılır ama bakiye
 * 0 kalır — kullanıcı parasını öder, tek bir analiz yapamaz (bayrak açıldığı gün patlayacak
 * sessiz bir para-yolu kusuru).
 *
 * SÖZLEŞME:
 *  1. Callback başarı dalında (active/trialing) plan hakkı kadar jeton yüklenir.
 *  2. Webhook YENİLEME olayında da yüklenir (ilk ay gelip ikinci ay gelmemesin) — ama YALNIZ
 *     canlı durumlarda: iptal/past_due olayı jeton DOLDURMAZ (iptal eden aya hak yazmak,
 *     ödenmemiş hak dağıtmaktır).
 *  3. ⚠️ Jeton yüklemesi BAŞARISIZSA abonelik yazımı GERİ ALINMAZ ve akış kırılmaz: kullanıcı
 *     parasını ödemiştir; hakkı yazılamadıysa loglanır, destek elle yükler. (Callback yine
 *     success sayfasına yönlendirir.)
 *  4. Tier→hak eşlemesi TEK KAYNAKLA (src/config.ts::JETON.planHaklari) birebir aynıdır.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const OLD = { ...process.env }

vi.mock('../iyzico.js', () => ({
  subRetrieveByToken: vi.fn(),
  subRetrieveByRef: vi.fn(),
  planMeta: vi.fn(),
  verifyWebhookSignature: vi.fn().mockReturnValue(true),
}))

import * as iyzico from '../iyzico.js'
import * as util from '../util.js'
import { JETON } from '../../../src/config'

function sahteRes() {
  const res: Record<string, unknown> = {}
  res.statusCode = 0
  res.gidilen = ''
  res.status = vi.fn().mockImplementation((k: number) => ((res.statusCode = k), res))
  res.json = vi.fn().mockReturnValue(res)
  res.redirect = vi.fn().mockImplementation((k: number, u: string) => ((res.statusCode = k), (res.gidilen = u), res))
  return res as unknown as { statusCode: number; gidilen: string } & Record<string, ReturnType<typeof vi.fn>>
}

beforeEach(() => {
  process.env.SUPABASE_URL = 'https://proje.supabase.co'
  process.env.SUPABASE_SERVICE_ROLE_KEY = 'servis-anahtari-testte'
  process.env.SUPABASE_ANON_KEY = 'anon-testte'
  vi.restoreAllMocks()
})
afterEach(() => {
  vi.unstubAllGlobals()
  process.env = { ...OLD }
})

describe('tek kaynak: tier→hak eşlemesi', () => {
  it('KRİTİK: util.JETON_HAKLARI src/config.ts::JETON.planHaklari ile BİREBİR aynı', () => {
    // api/ katmanı src/'den import etmez (Vercel işlev paketi sınırı) — değer elle eşlenir;
    // bu test ayrışmayı kilitler (borç tavanı web↔cihaz paritesiyle aynı desen).
    expect(util.JETON_HAKLARI).toEqual(JETON.planHaklari)
  })
})

describe('jetonDonemYenile (util)', () => {
  it('KRİTİK: service_role ile rpc/jeton_donem_yenile çağrılır, gövde doğru', async () => {
    const cagrilar: Array<{ url: string; init: RequestInit }> = []
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      cagrilar.push({ url, init })
      return { ok: true, text: async () => '', json: async () => ({}) } as unknown as Response
    })
    await util.jetonDonemYenile('uid-1', 500)
    expect(cagrilar.length).toBe(1)
    expect(cagrilar[0].url).toContain('/rest/v1/rpc/jeton_donem_yenile')
    const govde = JSON.parse(String(cagrilar[0].init.body))
    expect(govde).toEqual({ p_user: 'uid-1', p_aylik_hak: 500 })
    const basliklar = cagrilar[0].init.headers as Record<string, string>
    expect(basliklar.Authorization).toContain('servis-anahtari-testte')
  })

  it('KRİTİK: RPC başarısızsa fırlatır (çağıran loglayıp yutar — sessiz kayıp olmaz)', async () => {
    vi.stubGlobal('fetch', async () => ({ ok: false, status: 500, text: async () => 'patladi' }) as unknown as Response)
    await expect(util.jetonDonemYenile('uid-1', 500)).rejects.toThrow()
  })
})

describe('callback → jeton yükleme', () => {
  async function callbackKos(status = 'ACTIVE') {
    vi.mocked(iyzico.subRetrieveByToken).mockResolvedValue({
      conversationId: 'uid-7',
      pricingPlanReferenceCode: 'plan-pro',
      referenceCode: 'sub-1',
      customerReferenceCode: 'cust-1',
      subscriptionStatus: status,
    } as never)
    vi.mocked(iyzico.planMeta).mockReturnValue({ tier: 'pro', research: false, yearly: false } as never)

    const yenileCagrilari: Array<[string, number]> = []
    const upsertSpy = vi.spyOn(util, 'upsertSubscription').mockResolvedValue()
    const yenileSpy = vi
      .spyOn(util, 'jetonDonemYenile')
      .mockImplementation(async (u: string, h: number) => void yenileCagrilari.push([u, h]))

    const { default: handler } = await import('../../callback.js')
    const res = sahteRes()
    await handler({ body: { token: 't-1' }, query: {} } as never, res as never)
    return { res, yenileCagrilari, upsertSpy, yenileSpy }
  }

  it('KRİTİK: başarılı ödemede plan hakkı kadar jeton yüklenir', async () => {
    const { res, yenileCagrilari } = await callbackKos()
    expect(res.gidilen).toContain('checkout=success')
    expect(yenileCagrilari).toEqual([['uid-7', JETON.planHaklari.pro]])
  })

  it('KRİTİK: jeton yüklemesi PATLASA bile kullanıcı success görür (abonelik geri alınmaz)', async () => {
    vi.mocked(iyzico.subRetrieveByToken).mockResolvedValue({
      conversationId: 'uid-7',
      pricingPlanReferenceCode: 'plan-pro',
      referenceCode: 'sub-1',
      customerReferenceCode: 'cust-1',
      subscriptionStatus: 'ACTIVE',
    } as never)
    vi.mocked(iyzico.planMeta).mockReturnValue({ tier: 'pro', research: false, yearly: false } as never)
    vi.spyOn(util, 'upsertSubscription').mockResolvedValue()
    vi.spyOn(util, 'jetonDonemYenile').mockRejectedValue(new Error('rpc down'))

    const { default: handler } = await import('../../callback.js')
    const res = sahteRes()
    await handler({ body: { token: 't-1' }, query: {} } as never, res as never)
    expect(res.gidilen).toContain('checkout=success')
  })
})

describe('webhook → yenileme olayında jeton', () => {
  async function webhookKos(subscriptionStatus: string) {
    vi.mocked(iyzico.subRetrieveByRef).mockResolvedValue({
      conversationId: 'uid-9',
      pricingPlanReferenceCode: 'plan-proplus',
      subscriptionStatus,
      customerReferenceCode: 'cust-9',
    } as never)
    vi.mocked(iyzico.planMeta).mockReturnValue({ tier: 'pro_plus', research: false, yearly: false } as never)

    const yenileCagrilari: Array<[string, number]> = []
    vi.spyOn(util, 'upsertSubscription').mockResolvedValue()
    vi.spyOn(util, 'getUserBySubscriptionRef').mockResolvedValue('uid-9')
    vi.spyOn(util, 'jetonDonemYenile').mockImplementation(
      async (u: string, h: number) => void yenileCagrilari.push([u, h])
    )

    const { default: handler } = await import('../../webhook.js')
    const res = sahteRes()
    await handler(
      {
        method: 'POST',
        headers: {},
        body: { subscriptionReferenceCode: `sub-${subscriptionStatus}-${Math.random()}`, iyziEventType: 'subscription.order.success' },
      } as never,
      res as never
    )
    return { res, yenileCagrilari }
  }

  it('KRİTİK: aktif yenilemede jeton yüklenir (ilk ay gelip ikinci ay gelmemesin)', async () => {
    const { res, yenileCagrilari } = await webhookKos('ACTIVE')
    expect(res.statusCode).toBe(200)
    expect(yenileCagrilari).toEqual([['uid-9', JETON.planHaklari.pro_plus]])
  })

  it('KARŞIT-KANIT: iptal olayı jeton DOLDURMAZ (ödenmemiş hak dağıtılmaz)', async () => {
    const { yenileCagrilari } = await webhookKos('CANCELED')
    expect(yenileCagrilari).toEqual([])
  })
})
