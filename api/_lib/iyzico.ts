// Author: mertaygn, cglrgrkn
/* iyzico Abonelik (Subscription) sarmalayıcı — SDK callback'lerini promisify eder + plan çözer +
   webhook imza doğrular. Plan referans kodları iyzico panelinde oluşturulur (Ürün → Ödeme Planı),
   env'e girilir. */
import Iyzipay from 'iyzipay'
import crypto from 'node:crypto'
import { env } from './util.js'

export type Tier = 'pro' | 'pro_plus'
type Result = Record<string, unknown> & { status?: string; errorMessage?: string }

let _client: Iyzipay | null = null
export function iyzico(): Iyzipay {
  if (!_client) {
    // FAIL-CLOSED: varsayılan SANDBOX'tı. Vercel'de `IYZICO_URI` girilmeyi unutulursa üretim
    // sitesi sessizce test ortamına bağlanır → kullanıcı "ödeme başarılı" ekranı görür, iyzico
    // test onayı döner, callback aboneliği AKTİF yazar; ama GERÇEK tahsilat HİÇ yapılmamıştır.
    // Böyle bir yanlış yapılandırma sessizce ücretsiz abonelik dağıtır. Üretimde uri ZORUNLU;
    // sandbox'a düşmek yalnız açıkça izin verildiğinde (IYZICO_ALLOW_SANDBOX=1) mümkün.
    const explicitUri = process.env.IYZICO_URI
    const allowSandbox = (process.env.IYZICO_ALLOW_SANDBOX ?? '0') === '1'
    if (!explicitUri && !allowSandbox) {
      throw new Error(
        'Eksik ortam değişkeni: IYZICO_URI (üretimde https://api.iyzipay.com). ' +
        'Test ortamı için IYZICO_ALLOW_SANDBOX=1 gerekir.'
      )
    }
    _client = new Iyzipay({
      apiKey: env('IYZICO_API_KEY'),
      secretKey: env('IYZICO_SECRET_KEY'),
      uri: explicitUri || 'https://sandbox-api.iyzipay.com',
    })
  }
  return _client
}

// (tier | research | period) → plan referans kodu env adı (8 kombinasyon).
const PLAN_ENV: Record<string, string> = {
  'pro|false|monthly': 'IYZICO_PLAN_PRO_MONTHLY',
  'pro|false|yearly': 'IYZICO_PLAN_PRO_YEARLY',
  'pro|true|monthly': 'IYZICO_PLAN_PRO_RESEARCH_MONTHLY',
  'pro|true|yearly': 'IYZICO_PLAN_PRO_RESEARCH_YEARLY',
  'pro_plus|false|monthly': 'IYZICO_PLAN_PROPLUS_MONTHLY',
  'pro_plus|false|yearly': 'IYZICO_PLAN_PROPLUS_YEARLY',
  'pro_plus|true|monthly': 'IYZICO_PLAN_PROPLUS_RESEARCH_MONTHLY',
  'pro_plus|true|yearly': 'IYZICO_PLAN_PROPLUS_RESEARCH_YEARLY',
}

/** (tier, research, yearly) → plan referans kodu (env'den). */
export function planRef(tier: Tier, research: boolean, yearly: boolean): string {
  const key = `${tier}|${research}|${yearly ? 'yearly' : 'monthly'}`
  const name = PLAN_ENV[key]
  if (!name) throw new Error(`Geçersiz plan kombinasyonu: ${key}`)
  return env(name)
}

/** Plan referans kodu → {tier, research} (callback/webhook: ödenen plandan hakkı çöz). */
export function planMeta(refCode: string): { tier: Tier; research: boolean } | null {
  if (!refCode) return null
  for (const [key, name] of Object.entries(PLAN_ENV)) {
    if ((process.env[name] || '') === refCode) {
      const [tier, research] = key.split('|')
      return { tier: tier as Tier, research: research === 'true' }
    }
  }
  return null
}

// ── Promisified SDK çağrıları ───────────────────────────────────────────────
export function subInitialize(request: Record<string, unknown>): Promise<Result> {
  return new Promise((resolve, reject) => {
    iyzico().subscriptionCheckoutForm.initialize(request, (err, result) =>
      err ? reject(err) : resolve(result as Result),
    )
  })
}
export function subRetrieveByToken(checkoutFormToken: string): Promise<Result> {
  return new Promise((resolve, reject) => {
    iyzico().subscriptionCheckoutForm.retrieve({ checkoutFormToken }, (err, result) =>
      err ? reject(err) : resolve(result as Result),
    )
  })
}
export function subRetrieveByRef(subscriptionReferenceCode: string): Promise<Result> {
  return new Promise((resolve, reject) => {
    iyzico().subscription.retrieve({ subscriptionReferenceCode }, (err, result) =>
      err ? reject(err) : resolve(result as Result),
    )
  })
}
export function subCancel(subscriptionReferenceCode: string): Promise<Result> {
  return new Promise((resolve, reject) => {
    iyzico().subscription.cancel({ subscriptionReferenceCode }, (err, result) =>
      err ? reject(err) : resolve(result as Result),
    )
  })
}

/** Webhook imza doğrula: X-IYZ-SIGNATURE-V3 = HMAC-SHA256(merchantId+secretKey+eventType+
 *  subscriptionReferenceCode+orderReferenceCode+customerReferenceCode), key=secretKey, hex.
 *  NOT: iyzico imza şeması sürümler arası değişebildiğinden webhook AYRICA subscription'ı
 *  yeniden çeker (authoritative) → imza tek güvenlik dayanağı DEĞİL. */
export function verifyWebhookSignature(
  body: Record<string, unknown>,
  headerSig: string | undefined,
): boolean {
  try {
    const merchantId = env('IYZICO_MERCHANT_ID')
    const secretKey = env('IYZICO_SECRET_KEY')
    const msg =
      merchantId +
      secretKey +
      String(body.iyziEventType ?? '') +
      String(body.subscriptionReferenceCode ?? '') +
      String(body.orderReferenceCode ?? '') +
      String(body.customerReferenceCode ?? '')
    const computed = crypto.createHmac('sha256', secretKey).update(msg, 'utf8').digest('hex')
    const a = Buffer.from(computed)
    const b = Buffer.from(String(headerSig ?? ''))
    return a.length === b.length && crypto.timingSafeEqual(a, b)
  } catch {
    return false
  }
}
