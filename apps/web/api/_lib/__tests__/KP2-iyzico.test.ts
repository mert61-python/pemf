// Author: mertaygn, cglrgrkn
/**
 * KP-2 · api/_lib/iyzico.ts · sözleşmeler: istemci kurulumu FAIL-CLOSED (IYZICO_URI yoksa ve sandbox'a açıkça izin verilmemişse SDK
 * HİÇ kurulmaz) · tekil istemci · plan referansı ↔ (tier, research, dönem) eşlemesi iki yönde · SDK geri çağrılarının söze çevrilmesi
 * (başarı → sonuç, hata → red; istek gövdesi SDK'ya aynen) · webhook imzası (HMAC-SHA256, hex; eksik yapılandırma → false, fırlatmaz).
 *
 * Sahte EN ALT katta: `iyzipay` SDK sınıfı (ağ yok); ortam `vi.stubEnv`. Her test modülü TAZE yükler (`vi.resetModules`) — modül
 * düzeyi `_client` tekili testler arasında taşınmasın. Değerler açıkça sahte (`test-anahtar-1` …).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import crypto from 'node:crypto'

type Gc = (err: unknown, sonuc?: unknown) => void
const sdk = vi.hoisted(() => {
  const durum = {
    kurulum: [] as Record<string, unknown>[],
    cagri: [] as { yer: string; istek: unknown }[],
    /** Sıradaki SDK çağrısının geri çağrı argümanları. */
    yanit: [null, { status: 'success' }] as [unknown, unknown?],
  }
  class SahteIyzipay {
    static LOCALE = { TR: 'tr', EN: 'en' }
    static SUBSCRIPTION_INITIAL_STATUS = { ACTIVE: 'ACTIVE', PENDING: 'PENDING' }
    subscriptionCheckoutForm: Record<string, (r: unknown, cb: Gc) => void>
    subscription: Record<string, (r: unknown, cb: Gc) => void>
    constructor(cfg: Record<string, unknown>) {
      durum.kurulum.push(cfg)
      const yap = (yer: string) => (istek: unknown, cb: Gc) => {
        durum.cagri.push({ yer, istek })
        cb(durum.yanit[0], durum.yanit[1])
      }
      this.subscriptionCheckoutForm = { initialize: yap('form.initialize'), retrieve: yap('form.retrieve') }
      this.subscription = { retrieve: yap('abonelik.retrieve'), cancel: yap('abonelik.cancel') }
    }
  }
  return { durum, SahteIyzipay }
})
vi.mock('iyzipay', () => ({ default: sdk.SahteIyzipay }))

const PLAN_ENV: [tier: 'pro' | 'pro_plus', research: boolean, yearly: boolean, ad: string][] = [
  ['pro', false, false, 'IYZICO_PLAN_PRO_MONTHLY'],
  ['pro', false, true, 'IYZICO_PLAN_PRO_YEARLY'],
  ['pro', true, false, 'IYZICO_PLAN_PRO_RESEARCH_MONTHLY'],
  ['pro', true, true, 'IYZICO_PLAN_PRO_RESEARCH_YEARLY'],
  ['pro_plus', false, false, 'IYZICO_PLAN_PROPLUS_MONTHLY'],
  ['pro_plus', false, true, 'IYZICO_PLAN_PROPLUS_YEARLY'],
  ['pro_plus', true, false, 'IYZICO_PLAN_PROPLUS_RESEARCH_MONTHLY'],
  ['pro_plus', true, true, 'IYZICO_PLAN_PROPLUS_RESEARCH_YEARLY'],
]

async function taze() {
  vi.resetModules()
  return import('../iyzico')
}

beforeEach(() => {
  sdk.durum.kurulum.length = 0
  sdk.durum.cagri.length = 0
  sdk.durum.yanit = [null, { status: 'success' }]
  vi.stubEnv('IYZICO_URI', '')
  vi.stubEnv('IYZICO_ALLOW_SANDBOX', '')
  vi.stubEnv('IYZICO_API_KEY', 'test-anahtar-1')
  vi.stubEnv('IYZICO_SECRET_KEY', 'test-gizli-1')
  vi.stubEnv('IYZICO_MERCHANT_ID', 'test-isyeri-1')
  for (const [, , , ad] of PLAN_ENV) vi.stubEnv(ad, '')
})
afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('iyzico() — istemci kurulumu fail-closed', () => {
  it('IYZICO_URI yok + sandbox izni yok → "Eksik ortam değişkeni: IYZICO_URI" fırlatır ve SDK HİÇ kurulmaz', async () => {
    const m = await taze()
    expect(() => m.iyzico()).toThrow(/Eksik ortam değişkeni: IYZICO_URI/)
    expect(() => m.iyzico()).toThrow(/IYZICO_ALLOW_SANDBOX=1/)
    expect(sdk.durum.kurulum).toHaveLength(0)
  })

  it('IYZICO_ALLOW_SANDBOX=1 + URI yok → SDK sandbox adresiyle ve ortamdaki anahtarlarla kurulur', async () => {
    vi.stubEnv('IYZICO_ALLOW_SANDBOX', '1')
    const m = await taze()
    m.iyzico()
    expect(sdk.durum.kurulum).toEqual([
      { apiKey: 'test-anahtar-1', secretKey: 'test-gizli-1', uri: 'https://sandbox-api.iyzipay.com' },
    ])
  })

  it('IYZICO_URI verildi → O adres kullanılır (sandbox izni olsa bile) ve istemci TEKİLDİR (ikinci çağrı yeni SDK kurmaz)', async () => {
    vi.stubEnv('IYZICO_URI', 'https://api.ornek-odeme.test')
    vi.stubEnv('IYZICO_ALLOW_SANDBOX', '1')
    const m = await taze()
    const a = m.iyzico()
    const b = m.iyzico()
    expect(a).toBe(b)
    expect(sdk.durum.kurulum).toHaveLength(1)
    expect(sdk.durum.kurulum[0].uri).toBe('https://api.ornek-odeme.test')
  })

  it('URI var ama IYZICO_API_KEY boş → anahtar adıyla fırlatır (boş anahtarla SDK kurulmaz)', async () => {
    vi.stubEnv('IYZICO_URI', 'https://api.ornek-odeme.test')
    vi.stubEnv('IYZICO_API_KEY', '')
    const m = await taze()
    expect(() => m.iyzico()).toThrow('Eksik ortam değişkeni: IYZICO_API_KEY')
    expect(sdk.durum.kurulum).toHaveLength(0)
  })
})

describe('planRef / planMeta — plan referans kodu eşlemesi', () => {
  it.each(PLAN_ENV)('planRef(%s, research=%s, yearly=%s) → %s ortam değerini döner', async (tier, research, yearly, ad) => {
    vi.stubEnv(ad, `plan-${ad.toLowerCase()}`)
    const m = await taze()
    expect(m.planRef(tier, research, yearly)).toBe(`plan-${ad.toLowerCase()}`)
  })

  it('planRef: plan ortam değişkeni boşsa → değişkenin ADIYLA fırlatır (boş referansla ödeme başlatılmaz)', async () => {
    const m = await taze()
    expect(() => m.planRef('pro', false, false)).toThrow('Eksik ortam değişkeni: IYZICO_PLAN_PRO_MONTHLY')
  })

  it('planRef: bilinmeyen tier → "Geçersiz plan kombinasyonu: <anahtar>" fırlatır', async () => {
    const m = await taze()
    expect(() => m.planRef('kurumsal' as never, false, true)).toThrow('Geçersiz plan kombinasyonu: kurumsal|false|yearly')
  })

  it.each(PLAN_ENV)('planMeta: %s/research=%s/yearly=%s referansı → { tier, research } (dönem bilgisi dönmez)', async (tier, research, _y, ad) => {
    vi.stubEnv(ad, 'plan-aranan')
    const m = await taze()
    expect(m.planMeta('plan-aranan')).toEqual({ tier, research })
  })

  it('planMeta: boş referans → null; yapılandırmada OLMAYAN referans → null (yanlış plana hak yazılmaz)', async () => {
    vi.stubEnv('IYZICO_PLAN_PRO_MONTHLY', 'plan-var')
    const m = await taze()
    expect(m.planMeta('')).toBeNull()
    expect(m.planMeta('plan-yok')).toBeNull()
  })
})

describe('SDK çağrılarının söze çevrilmesi', () => {
  async function kurulu() {
    vi.stubEnv('IYZICO_URI', 'https://api.ornek-odeme.test')
    return taze()
  }

  it('subInitialize: istek SDK formuna AYNEN gider; geri çağrı (null, sonuç) → söz sonuçla çözülür', async () => {
    const m = await kurulu()
    sdk.durum.yanit = [null, { status: 'success', checkoutFormContent: '<div>form</div>', token: 'tk-1' }]
    const istek = { locale: 'tr', pricingPlanReferenceCode: 'plan-1' }
    await expect(m.subInitialize(istek)).resolves.toEqual({ status: 'success', checkoutFormContent: '<div>form</div>', token: 'tk-1' })
    expect(sdk.durum.cagri).toEqual([{ yer: 'form.initialize', istek }])
  })

  it('subInitialize: geri çağrı hata verirse → söz O hatayla reddedilir', async () => {
    const m = await kurulu()
    const hata = new Error('sdk zaman aşımı')
    sdk.durum.yanit = [hata]
    await expect(m.subInitialize({})).rejects.toBe(hata)
  })

  it('subRetrieveByToken: { checkoutFormToken } ile FORM retrieve çağrılır; başarı → sonuç, hata → red', async () => {
    const m = await kurulu()
    sdk.durum.yanit = [null, { status: 'success', referenceCode: 'sub-1' }]
    await expect(m.subRetrieveByToken('tk-9')).resolves.toEqual({ status: 'success', referenceCode: 'sub-1' })
    expect(sdk.durum.cagri.at(-1)).toEqual({ yer: 'form.retrieve', istek: { checkoutFormToken: 'tk-9' } })
    sdk.durum.yanit = [new Error('form-yok')]
    await expect(m.subRetrieveByToken('tk-9')).rejects.toThrow('form-yok')
  })

  it('subRetrieveByRef: { subscriptionReferenceCode } ile ABONELİK retrieve çağrılır; başarı → sonuç, hata → red', async () => {
    const m = await kurulu()
    sdk.durum.yanit = [null, { subscriptionStatus: 'ACTIVE' }]
    await expect(m.subRetrieveByRef('sub-7')).resolves.toEqual({ subscriptionStatus: 'ACTIVE' })
    expect(sdk.durum.cagri.at(-1)).toEqual({ yer: 'abonelik.retrieve', istek: { subscriptionReferenceCode: 'sub-7' } })
    sdk.durum.yanit = [new Error('abonelik-yok')]
    await expect(m.subRetrieveByRef('sub-7')).rejects.toThrow('abonelik-yok')
  })

  it('subCancel: { subscriptionReferenceCode } ile ABONELİK cancel çağrılır; başarı → sonuç, hata → red', async () => {
    const m = await kurulu()
    sdk.durum.yanit = [null, { status: 'success' }]
    await expect(m.subCancel('sub-8')).resolves.toEqual({ status: 'success' })
    expect(sdk.durum.cagri.at(-1)).toEqual({ yer: 'abonelik.cancel', istek: { subscriptionReferenceCode: 'sub-8' } })
    sdk.durum.yanit = [new Error('iptal-reddedildi')]
    await expect(m.subCancel('sub-8')).rejects.toThrow('iptal-reddedildi')
  })

  it('istemci kurulamıyorsa (URI yok) SDK çağrısının sözü REDDEDİLİR — sessizce sandbox\'a gidilmez', async () => {
    const m = await taze()
    await expect(m.subCancel('sub-1')).rejects.toThrow(/IYZICO_URI/)
    expect(sdk.durum.cagri).toHaveLength(0)
    expect(sdk.durum.kurulum).toHaveLength(0)
  })
})

describe('verifyWebhookSignature — X-IYZ-SIGNATURE-V3', () => {
  const govde = {
    iyziEventType: 'subscription.order.success',
    subscriptionReferenceCode: 'sub-1',
    orderReferenceCode: 'ord-1',
    customerReferenceCode: 'cus-1',
  }
  /** Bağımsız hesap (testin kendisi): HMAC-SHA256(merchantId+secret+olay+abonelik+sipariş+müşteri, key=secret) hex. */
  const imza = (g: Record<string, string>, secret = 'test-gizli-1', isyeri = 'test-isyeri-1') =>
    crypto
      .createHmac('sha256', secret)
      .update(isyeri + secret + g.iyziEventType + g.subscriptionReferenceCode + g.orderReferenceCode + g.customerReferenceCode, 'utf8')
      .digest('hex')

  it('doğru imza → true', async () => {
    const m = await taze()
    expect(m.verifyWebhookSignature(govde, imza(govde))).toBe(true)
  })

  it('gövdenin TEK alanı değişirse (ör. abonelik referansı) aynı imza → false', async () => {
    const m = await taze()
    expect(m.verifyWebhookSignature({ ...govde, subscriptionReferenceCode: 'sub-2' }, imza(govde))).toBe(false)
  })

  it('başka gizli anahtarla üretilmiş imza (aynı uzunluk) → false', async () => {
    const m = await taze()
    expect(m.verifyWebhookSignature(govde, imza(govde, 'baska-gizli'))).toBe(false)
  })

  it('eksik alanlar boş dize sayılır: alansız gövdenin doğru imzası → true', async () => {
    const m = await taze()
    const bos = { iyziEventType: '', subscriptionReferenceCode: '', orderReferenceCode: '', customerReferenceCode: '' }
    expect(m.verifyWebhookSignature({}, imza(bos))).toBe(true)
  })

  it('başlık YOK ya da farklı uzunlukta → false (timingSafeEqual fırlatmaz)', async () => {
    const m = await taze()
    expect(m.verifyWebhookSignature(govde, undefined)).toBe(false)
    expect(m.verifyWebhookSignature(govde, imza(govde).slice(0, 10))).toBe(false)
  })

  it('IYZICO_MERCHANT_ID yapılandırılmamış → false (istisna dışarı sızmaz)', async () => {
    vi.stubEnv('IYZICO_MERCHANT_ID', '')
    const m = await taze()
    expect(m.verifyWebhookSignature(govde, imza(govde))).toBe(false)
  })
})
