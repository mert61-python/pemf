// Author: mertaygn, cglrgrkn
/**
 * KP-8 · api/webhook.ts kalan dallar (düzenek KP2-webhook ile AYNI: sahte `iyzipay` SDK + sahte `fetch`; imza GERÇEK):
 *  - gövdesiz istek → 200 {ignored} ve iyzico'ya / veritabanına GİDİLMEZ.
 *  - araştırma ekli plan → abonelik `addons: ['research']`; müşteri referansı gelmezse boş yazılır.
 *  - iyzico durumu boş gelirse (bilinmeyen) abonelik ASKIDA (past_due) yazılır ve jeton YÜKLENMEZ (ödenmemiş hak dağıtılmaz).
 *  - plan referansı gelmezse eşleme yok → 500 ve günlükte boş plan referansı (iyzico yeniden dener).
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


it('gövdesiz istek → 200 {ignored}; iyzico / veritabanı çağrısı YOK', async () => {
  const h = await yukle()
  const res = sahteRes()
  await h({ method: 'POST', headers: {} } as never, res as never)
  expect(res.kod).toBe(200)
  expect(res.govde).toEqual({ ignored: true })
  expect(sdk.durum.retrieve).toHaveLength(0)
  expect(kayit).toHaveLength(0)
})

it('araştırma ekli plan → addons research; müşteri referansı yoksa boş', async () => {
  vi.stubEnv('IYZICO_PLAN_PRO_RESEARCH_MONTHLY', 'plan-pro-arastirma')
  sdk.durum.abonelik = { pricingPlanReferenceCode: 'plan-pro-arastirma', subscriptionStatus: 'ACTIVE' }
  const h = await yukle()
  const g = govde('sub-ar')
  const res = await cagir(h, g, imza(g))
  expect(res.kod).toBe(200)
  const yazilan = kayit.find((k) => k.url.endsWith('/rest/v1/subscriptions'))?.govde as Record<string, unknown>
  expect(yazilan).toMatchObject({ tier: 'pro', addons: ['research'], stripe_customer_id: '', status: 'active' })
})

it('durum boş (bilinmeyen) → abonelik ASKIDA yazılır, jeton YÜKLENMEZ', async () => {
  sdk.durum.abonelik = { pricingPlanReferenceCode: 'plan-pro-aylik', customerReferenceCode: 'cus-1' }
  const h = await yukle()
  const g = govde('sub-bos')
  const res = await cagir(h, g, imza(g))
  expect(res.kod).toBe(200)
  expect((kayit.find((k) => k.url.endsWith('/rest/v1/subscriptions'))?.govde as Record<string, unknown>).status).toBe('past_due')
  expect(kayit.some((k) => k.url.includes('/rpc/jeton_donem_yenile'))).toBe(false)
})

it('plan referansı gelmezse eşleme yok → 500; günlükte boş plan referansı', async () => {
  const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
  sdk.durum.abonelik = { subscriptionStatus: 'ACTIVE' }
  const h = await yukle()
  const g = govde('sub-plansiz')
  const res = await cagir(h, g, imza(g))
  expect(res.kod).toBe(500)
  expect(res.govde).toEqual({ error: 'unmatched_subscription' })
  expect(gunluk).toHaveBeenCalledWith('iyzico webhook: abonelik kullanıcıya eşlenemedi', expect.objectContaining({ planRef: '', planResolved: false }))
})
