// Author: mertaygn, cglrgrkn
/**
 * KP-2 · api/webhook.ts · sözleşmeler: imza tutmazsa varsayılan kipte UYARIP işler, IYZICO_WEBHOOK_STRICT=1'de 401 · aynı abonelik
 * referansına 60 sn içinde 10'dan fazla istek → 429 ve iyzico'ya GİDİLMEZ; pencere geçince sayaç sıfırlanır; 500'den fazla referans
 * birikince en eski kayıtlar atılır (bellek sınırı) · jeton yükleme patlarsa abonelik YAZILMIŞ kalır, 200 döner ve iz bırakılır ·
 * abonelik kullanıcıya / plana eşlenemezse SESSİZ 200 DEĞİL 500 (iyzico yeniden dener) ve günlükte sır yok.
 *
 * Sahte EN ALT katta: `iyzipay` SDK (abonelik retrieve) + `fetch` (Supabase REST). İmza doğrulaması GERÇEK (`node:crypto`). Her test
 * modülü TAZE yükler (`vi.resetModules`): hız sınırı sayacı ve iyzico istemcisi modül düzeyindedir.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import crypto from 'node:crypto'

type Gc = (err: unknown, sonuc?: unknown) => void
const sdk = vi.hoisted(() => {
  const durum = { retrieve: [] as unknown[], abonelik: {} as Record<string, unknown> }
  class SahteIyzipay {
    static LOCALE = { TR: 'tr', EN: 'en' }
    static SUBSCRIPTION_INITIAL_STATUS = { ACTIVE: 'ACTIVE', PENDING: 'PENDING' }
    subscriptionCheckoutForm = {}
    subscription = {
      retrieve: (istek: unknown, cb: Gc) => {
        durum.retrieve.push(istek)
        cb(null, durum.abonelik)
      },
    }
  }
  return { durum, SahteIyzipay }
})
vi.mock('iyzipay', () => ({ default: sdk.SahteIyzipay }))

type Kayit = { url: string; yontem: string; govde: unknown }
let kayit: Kayit[] = []
let ag: { kullanici: unknown[]; upsert: number; jeton: number } = { kullanici: [], upsert: 201, jeton: 200 }
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })
function agKur() {
  kayit = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const u = String(url)
      kayit.push({ url: u, yontem: init.method ?? 'GET', govde: init.body ? JSON.parse(String(init.body)) : undefined })
      if (u.includes('/rpc/jeton_donem_yenile')) return new Response(ag.jeton === 200 ? '' : 'rpc patladi', { status: ag.jeton })
      if (u.includes('/rest/v1/subscriptions?')) return json(ag.kullanici)
      if (u.endsWith('/rest/v1/subscriptions')) return new Response(null, { status: ag.upsert })
      throw new Error(`beklenmeyen ağ isteği: ${u}`)
    }),
  )
}

function sahteRes() {
  const res = { kod: 0, govde: undefined as unknown } as { kod: number; govde: Record<string, unknown> } & Record<string, unknown>
  res.status = (k: number) => ((res.kod = k), res)
  res.json = (g: Record<string, unknown>) => ((res.govde = g), res)
  return res
}

const govde = (ref: string) => ({
  iyziEventType: 'subscription.order.success',
  subscriptionReferenceCode: ref,
  orderReferenceCode: 'ord-1',
  customerReferenceCode: 'cus-1',
})
const imza = (g: Record<string, string>) =>
  crypto
    .createHmac('sha256', 'test-gizli-1')
    .update('test-isyeri-1' + 'test-gizli-1' + g.iyziEventType + g.subscriptionReferenceCode + g.orderReferenceCode + g.customerReferenceCode, 'utf8')
    .digest('hex')

async function yukle() {
  vi.resetModules()
  return (await import('../../webhook')).default
}
async function cagir(h: Awaited<ReturnType<typeof yukle>>, g: Record<string, string>, sig?: string) {
  const res = sahteRes()
  await h({ method: 'POST', headers: { 'x-iyz-signature-v3': sig }, body: g } as never, res as never)
  return res
}

beforeEach(() => {
  vi.stubEnv('IYZICO_URI', 'https://api.ornek-odeme.test')
  vi.stubEnv('IYZICO_API_KEY', 'test-anahtar-1')
  vi.stubEnv('IYZICO_SECRET_KEY', 'test-gizli-1')
  vi.stubEnv('IYZICO_MERCHANT_ID', 'test-isyeri-1')
  vi.stubEnv('IYZICO_WEBHOOK_STRICT', '')
  vi.stubEnv('IYZICO_PLAN_PRO_MONTHLY', 'plan-pro-aylik')
  vi.stubEnv('SUPABASE_URL', 'https://proje-ornek.supabase.test')
  vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'test-servis-anahtari')
  sdk.durum.retrieve.length = 0
  sdk.durum.abonelik = { pricingPlanReferenceCode: 'plan-pro-aylik', subscriptionStatus: 'ACTIVE', customerReferenceCode: 'cus-1' }
  ag = { kullanici: [{ user_id: 'u-1' }], upsert: 201, jeton: 200 }
  agKur()
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('imza kipi', () => {
  it('STRICT=1 + imza tutmuyor → 401 {error:"signature"} ve iyzico\'ya / veritabanına GİDİLMEZ', async () => {
    vi.stubEnv('IYZICO_WEBHOOK_STRICT', '1')
    const h = await yukle()
    const res = await cagir(h, govde('sub-1'), 'f'.repeat(64))
    expect(res.kod).toBe(401)
    expect(res.govde).toEqual({ error: 'signature' })
    expect(sdk.durum.retrieve).toHaveLength(0)
    expect(kayit).toHaveLength(0)
  })

  it('STRICT=1 + DOĞRU imza → işlenir (200 received)', async () => {
    vi.stubEnv('IYZICO_WEBHOOK_STRICT', '1')
    const h = await yukle()
    const g = govde('sub-1')
    const res = await cagir(h, g, imza(g))
    expect(res.kod).toBe(200)
    expect(res.govde).toEqual({ received: true })
  })

  it('varsayılan kip + imza tutmuyor → uyarır ama abonelik iyzico\'dan YENİDEN çekilerek işlenir', async () => {
    const uyari = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const h = await yukle()
    const res = await cagir(h, govde('sub-1'), 'yanlis')
    expect(uyari).toHaveBeenCalledWith('iyzico webhook imza tutmadı', { event: 'subscription.order.success' })
    expect(sdk.durum.retrieve).toEqual([{ subscriptionReferenceCode: 'sub-1' }])
    expect(res.kod).toBe(200)
  })
})

describe('hız sınırı', () => {
  it('aynı referansa 11. istek (60 sn içinde) → 429 rate_limited ve iyzico çağrılmaz', async () => {
    const h = await yukle()
    for (let i = 0; i < 10; i++) expect((await cagir(h, govde('sub-yogun'))).kod).toBe(200)
    expect(sdk.durum.retrieve).toHaveLength(10)
    const res = await cagir(h, govde('sub-yogun'))
    expect(res.kod).toBe(429)
    expect(res.govde).toEqual({ error: 'rate_limited' })
    expect(sdk.durum.retrieve).toHaveLength(10)
  })

  it('başka referans aynı anda sınırdan ETKİLENMEZ', async () => {
    const h = await yukle()
    for (let i = 0; i < 11; i++) await cagir(h, govde('sub-yogun'))
    expect((await cagir(h, govde('sub-sakin'))).kod).toBe(200)
  })

  it('60 sn pencere geçince aynı referans yeniden kabul edilir', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-11-02T10:00:00Z'))
    const h = await yukle()
    for (let i = 0; i < 11; i++) await cagir(h, govde('sub-yogun'))
    vi.setSystemTime(new Date('2026-11-02T10:01:00.001Z'))
    expect((await cagir(h, govde('sub-yogun'))).kod).toBe(200)
  })

  it('500\'den fazla referans birikince EN ESKİ kayıtlar atılır: sınırdaki eski referans yeniden kabul edilir (bellek sınırı)', async () => {
    const h = await yukle()
    for (let i = 0; i < 10; i++) await cagir(h, govde('sub-eski'))
    // Atılmadan önce sınırda: 11. istek 429 olurdu. 500 yeni referans → toplam 501 anahtar > 500 → ilk 250 (sub-eski dahil) silinir.
    for (let i = 0; i < 500; i++) await cagir(h, govde(`sub-${i}`))
    const res = await cagir(h, govde('sub-eski'))
    expect(res.kod).toBe(200)
  })

  it('KARŞIT: 500 referansa kadar atma YOK — sınırdaki eski referans hâlâ 429', async () => {
    const h = await yukle()
    for (let i = 0; i < 10; i++) await cagir(h, govde('sub-eski'))
    for (let i = 0; i < 499; i++) await cagir(h, govde(`sub-${i}`))
    expect((await cagir(h, govde('sub-eski'))).kod).toBe(429)
  })
})

describe('jeton yükleme ve eşleme hataları', () => {
  it('jeton RPC\'si patlarsa → abonelik YAZILMIŞ kalır, 200 received ve elle yükleme izi bırakılır', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    ag.jeton = 500
    const h = await yukle()
    const res = await cagir(h, govde('sub-1'))
    expect(res.kod).toBe(200)
    expect(res.govde).toEqual({ received: true })
    const upsert = kayit.find((k) => k.url.endsWith('/rest/v1/subscriptions'))
    expect(upsert?.govde).toMatchObject({ user_id: 'u-1', tier: 'pro', status: 'active', stripe_subscription_id: 'sub-1' })
    expect(kayit.find((k) => k.url.includes('/rpc/jeton_donem_yenile'))?.govde).toEqual({ p_user: 'u-1', p_aylik_hak: 500 })
    expect(gunluk).toHaveBeenCalledWith(
      'webhook: jeton yüklenemedi (abonelik YAZILDI — elle yükleme gerekir)',
      expect.objectContaining({ userId: 'u-1', tier: 'pro' }),
    )
  })

  it('kullanıcı bulunamadı (satır yok, conversationId yok) → 500 unmatched_subscription; günlükte yalnız eşleme alanları', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    ag.kullanici = []
    const h = await yukle()
    const res = await cagir(h, govde('sub-yetim'))
    expect(res.kod).toBe(500)
    expect(res.govde).toEqual({ error: 'unmatched_subscription' })
    expect(gunluk).toHaveBeenCalledWith('iyzico webhook: abonelik kullanıcıya eşlenemedi', {
      subRef: 'sub-yetim',
      planRef: 'plan-pro-aylik',
      planResolved: true,
      hasUserId: false,
      event: 'subscription.order.success',
    })
    expect(JSON.stringify(gunluk.mock.calls)).not.toContain('test-gizli-1')
    expect(kayit.some((k) => k.url.endsWith('/rest/v1/subscriptions'))).toBe(false)
  })

  it('plan yapılandırmada yok (kullanıcı var) → 500 unmatched_subscription, planResolved:false; abonelik yazılmaz', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    sdk.durum.abonelik = { pricingPlanReferenceCode: 'plan-bilinmeyen', subscriptionStatus: 'ACTIVE' }
    const h = await yukle()
    const res = await cagir(h, govde('sub-1'))
    expect(res.kod).toBe(500)
    expect(gunluk).toHaveBeenCalledWith(
      'iyzico webhook: abonelik kullanıcıya eşlenemedi',
      expect.objectContaining({ planRef: 'plan-bilinmeyen', planResolved: false, hasUserId: true }),
    )
    expect(kayit.some((k) => k.url.endsWith('/rest/v1/subscriptions'))).toBe(false)
  })
})

describe('KP-2 tur 2', () => {
  it('abonelik referansı YOK (geçerli imzalı olay) → 200 {ignored: true}; iyzico / veritabanına GİDİLMEZ', async () => {
    const h = await yukle()
    const g = { ...govde(''), subscriptionReferenceCode: '' }
    const res = await cagir(h, g, imza(g))
    expect(res.kod).toBe(200)
    expect(res.govde).toEqual({ ignored: true })
    expect(kayit).toHaveLength(0)
  })
})
