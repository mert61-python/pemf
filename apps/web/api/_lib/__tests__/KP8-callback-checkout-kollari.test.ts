// Author: mertaygn, cglrgrkn
/**
 * KP-8 · api/callback.ts + api/checkout.ts kalan dallar (düzenek KP2-callback-checkout ile AYNI: sahte `iyzipay` + sahte `fetch`):
 *  callback — gövdesiz ve sorgusuz dönüş hata sayfasına (ağ / yazım YOK); iyzico yanıtında plan / referans / durum yoksa
 *  "incomplete" ve günlükte boş alanlar; araştırma ekli plan → `addons: ['research']`.
 *  checkout — gövdesiz istek 400 {tier}; oturum jetonu HİÇ yoksa 401 ve Supabase'e gidilmez; müşteri bilgisi yoksa 400 (Ad eksik);
 *  hesapta e-posta yoksa formdaki e-posta, o da yoksa 'no-reply@pemf.vet'; iyzico hata metni vermezse genel metin (502).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Gc = (err: unknown, sonuc?: unknown) => void
const sdk = vi.hoisted(() => {
  const durum = {
    formSonuc: {} as Record<string, unknown>,
    formHata: null as unknown,
    initialize: [] as Record<string, unknown>[],
    initSonuc: {} as Record<string, unknown>,
  }
  class SahteIyzipay {
    static LOCALE = { TR: 'tr', EN: 'en' }
    static SUBSCRIPTION_INITIAL_STATUS = { ACTIVE: 'ACTIVE', PENDING: 'PENDING' }
    subscription = {}
    subscriptionCheckoutForm = {
      retrieve: (_istek: unknown, cb: Gc) => cb(durum.formHata, durum.formSonuc),
      initialize: (istek: Record<string, unknown>, cb: Gc) => {
        durum.initialize.push(istek)
        cb(null, durum.initSonuc)
      },
    }
  }
  return { durum, SahteIyzipay }
})
vi.mock('iyzipay', () => ({ default: sdk.SahteIyzipay }))

type Kayit = { url: string; yontem: string; govde: unknown }
let kayit: Kayit[] = []
let mevcutAbonelik: unknown[] = []
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })
function agKur() {
  kayit = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const u = String(url)
      kayit.push({ url: u, yontem: init.method ?? 'GET', govde: init.body ? JSON.parse(String(init.body)) : undefined })
      if (u.endsWith('/auth/v1/user')) return json({ id: 'u-7', email: 'klinik@ornek.test' })
      if (u.includes('/rest/v1/subscriptions?')) return json(mevcutAbonelik)
      if (u.endsWith('/rest/v1/subscriptions')) return new Response(null, { status: 201 })
      if (u.includes('/rpc/jeton_donem_yenile')) return new Response('', { status: 200 })
      throw new Error(`beklenmeyen ağ isteği: ${u}`)
    }),
  )
}

function sahteRes() {
  const res = { kod: 0, govde: undefined as unknown, gidilen: '' } as {
    kod: number
    govde: Record<string, unknown>
    gidilen: string
  } & Record<string, unknown>
  res.status = (k: number) => ((res.kod = k), res)
  res.json = (g: Record<string, unknown>) => ((res.govde = g), res)
  res.redirect = (k: number, u: string) => ((res.kod = k), (res.gidilen = u), res)
  return res
}

beforeEach(() => {
  vi.resetModules()
  vi.stubEnv('IYZICO_URI', 'https://api.ornek-odeme.test')
  vi.stubEnv('IYZICO_API_KEY', 'test-anahtar-1')
  vi.stubEnv('IYZICO_SECRET_KEY', 'test-gizli-1')
  vi.stubEnv('IYZICO_PLAN_PRO_MONTHLY', 'plan-pro-aylik')
  vi.stubEnv('IYZICO_PLAN_PROPLUS_RESEARCH_YEARLY', 'plan-proplus-arastirma-yillik')
  vi.stubEnv('SUPABASE_URL', 'https://proje-ornek.supabase.test')
  vi.stubEnv('SUPABASE_ANON_KEY', 'test-anon-anahtari')
  vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'test-servis-anahtari')
  vi.stubEnv('PUBLIC_SITE_URL', 'https://site-ornek.test')
  vi.stubEnv('EXTRA_ALLOWED_ORIGINS', '')
  sdk.durum.formHata = null
  sdk.durum.formSonuc = {}
  sdk.durum.initialize.length = 0
  sdk.durum.initSonuc = { status: 'success', checkoutFormContent: '<script>iyzi</script>', token: 'form-tk-1' }
  mevcutAbonelik = []
  agKur()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})


const MUSTERI = { name: 'Ayşe', surname: 'Kaya', identityNumber: '12345678901', gsmNumber: '+905551112233', city: 'İzmir', address: 'Bornova' }

describe('callback', () => {
  async function callback(query: Record<string, string> | undefined, body: Record<string, string> | undefined) {
    const h = (await import('../../callback')).default
    const res = sahteRes()
    await h({ body, query } as never, res as never)
    return res
  }

  it('gövdesiz + sorgusuz → hata sayfası; ağ / yazım YOK', async () => {
    const res = await callback(undefined, undefined)
    expect(res.gidilen).toBe('/pricing?checkout=error')
    expect(kayit).toHaveLength(0)
  })

  it('iyzico yanıtında plan / referans / durum yok → incomplete; günlükte boş alanlar', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    sdk.durum.formSonuc = { conversationId: 'u-7' }
    const res = await callback({}, { token: 'form-tk-1' })
    expect(res.gidilen).toBe('/pricing?checkout=incomplete')
    expect(gunluk).toHaveBeenCalledWith('callback: abonelik yazılamadı', expect.objectContaining({ planRef: '', subRef: '', planResolved: false }))
    expect(kayit.some((k) => k.url.endsWith('/rest/v1/subscriptions'))).toBe(false)
  })

  it('araştırma ekli plan → addons research', async () => {
    sdk.durum.formSonuc = {
      conversationId: 'u-7', pricingPlanReferenceCode: 'plan-proplus-arastirma-yillik', referenceCode: 'sub-9', subscriptionStatus: 'ACTIVE',
    }
    const res = await callback({}, { token: 'form-tk-1' })
    expect(res.gidilen).toBe('/download?checkout=success')
    expect(kayit.find((k) => k.url.endsWith('/rest/v1/subscriptions'))?.govde).toMatchObject({ tier: 'pro_plus', addons: ['research'], stripe_customer_id: '' })
  })
})

describe('checkout', () => {
  async function checkout(govde: Record<string, unknown> | undefined) {
    const h = (await import('../../checkout')).default
    const res = sahteRes()
    await h({ method: 'POST', headers: {}, body: govde } as never, res as never)
    return res
  }

  it('gövdesiz → 400 {tier}; jetonsuz → 401, Supabase\'e gidilmez; müşteri yok → 400 Ad eksik', async () => {
    expect((await checkout(undefined)).govde).toEqual({ error: 'tier' })
    const r401 = await checkout({ tier: 'pro' })
    expect(r401.kod).toBe(401)
    expect(kayit).toHaveLength(0)
    const r400 = await checkout({ tier: 'pro', token: 'oturum-1' })
    expect(r400.kod).toBe(400)
    expect(r400.govde).toMatchObject({ error: 'customer', alan: 'name', sebep: 'eksik' })
  })

  it('hesapta e-posta yoksa formdaki, o da yoksa no-reply; iyzico hata metni yoksa genel metin', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit = {}) => {
      const u = String(url)
      kayit.push({ url: u, yontem: init.method ?? 'GET', govde: init.body ? JSON.parse(String(init.body)) : undefined })
      if (u.endsWith('/auth/v1/user')) return new Response(JSON.stringify({ id: 'u-8' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (u.includes('/rest/v1/subscriptions?')) return new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } })
      throw new Error(`beklenmeyen ağ isteği: ${u}`)
    }))
    await checkout({ tier: 'pro', token: 'oturum-1', customer: { ...MUSTERI, email: 'form@ornek.test' } })
    expect((sdk.durum.initialize[0].customer as Record<string, unknown>).email).toBe('form@ornek.test')
    vi.resetModules()
    await checkout({ tier: 'pro', token: 'oturum-1', customer: MUSTERI })
    expect((sdk.durum.initialize[1].customer as Record<string, unknown>).email).toBe('no-reply@pemf.vet')
    sdk.durum.initSonuc = { status: 'failure' }
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.resetModules()
    const r = await checkout({ tier: 'pro', token: 'oturum-1', customer: MUSTERI })
    expect(r.kod).toBe(502)
    expect(r.govde).toEqual({ error: 'iyzico', message: 'Ödeme formu oluşturulamadı.' })
  })
})
