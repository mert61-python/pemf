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

/** Plan referans kodu → ödeme dönemi ('monthly' | 'yearly'); tanınmayan kod → null. */
export function planDonemi(refCode: string): 'monthly' | 'yearly' | null {
  if (!refCode) return null
  for (const [key, name] of Object.entries(PLAN_ENV)) {
    if ((process.env[name] || '') === refCode) return key.endsWith('|yearly') ? 'yearly' : 'monthly'
  }
  return null
}

/** TA T1 · iyzico yanıtındaki ABONELİK nesnesi. Belgelenen v2 şekilleri (docs.iyzico.com, 2026-11-19):
 *  checkout form sonucu `{ status, conversationId, token, data: { referenceCode, subscriptionStatus, … } }`;
 *  abonelik detayı `{ status, data: { totalCount, items: [ { …, orders: [ { startPeriod, endPeriod, orderStatus } ] } ] } }`.
 *  Eski düz (sarmalsız) şekil de kabul edilir (testler / SDK sürüm farkı) — alan bulunamazsa yanıtın kendisi döner. */
export function abonelikVerisi(r: Record<string, unknown>): Record<string, unknown> {
  const d = r.data
  if (!d || typeof d !== 'object') return r
  const items = (d as { items?: unknown }).items
  if (Array.isArray(items)) return items[0] && typeof items[0] === 'object' ? (items[0] as Record<string, unknown>) : {}
  return d as Record<string, unknown>
}

/** iyzico tarih alanı (epoch ms sayı / sayı dizesi / ISO) → epoch ms; okunamazsa NaN. */
function zamanMs(v: unknown): number {
  let t = NaN
  if (typeof v === 'number') t = v
  else if (typeof v === 'string' && v.trim()) t = /^\d+$/.test(v.trim()) ? Number(v.trim()) : Date.parse(v.trim())
  // Date'in geçerli aralığı (±8.64e15 ms) dışı / sıfır / negatif → okunamaz (toISOString RangeError atmasın)
  return Number.isFinite(t) && t > 0 && t <= 8.64e15 ? t : NaN
}

/** `ms`e k dönem ekle (UTC takvim ayı; ayın son günü taşmaz: 31 Ocak + 1 ay = 28/29 Şubat). */
function donemEkle(ms: number, donem: 'monthly' | 'yearly', k: number): number {
  const d = new Date(ms)
  const gun = d.getUTCDate()
  d.setUTCDate(1)
  d.setUTCMonth(d.getUTCMonth() + (donem === 'yearly' ? 12 : 1) * k)
  const sonGun = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()
  d.setUTCDate(Math.min(gun, sonGun))
  return d.getTime()
}

/** TA T1 (Y292-1) · ÖDENMİŞ dönemin sonu (ISO) → `subscriptions.current_period_end`; bilinemiyorsa null (yazılmaz,
 *  satırdaki önceki değer KORUNUR — upsert `merge-duplicates`).
 *  KAYNAK sırası:
 *   1. iyzico'nun kendi dönem bilgisi: `orders[]` içinde `orderStatus = SUCCESS` (ÖDENMİŞ) siparişlerin EN GEÇ `endPeriod`u.
 *      Bekleyen / başarısız sipariş (WAITING / FAILED) dönem SAYILMAZ — ödenmemiş dönem hak vermez. Durumdan bağımsızdır:
 *      iptal / UNPAID abonelikte de son ödenmiş dönemin sonu budur.
 *   2. Sipariş bilgisi yoksa YALNIZ canlı abonelikte (iyzico ACTIVE = son tahsilat başarılı) "başlangıç + plan süresi":
 *      `startDate` + k × (1 ay | 1 yıl), k ≥ 1 ve "şimdi"yi içeren dönemin sonu (yenilenmiş abonelikte ilk dönem geçmişte kalır).
 *      PENDING (deneme) → `trialEndDate`. İptal / ödenmemiş abonelikte tahmin YAPILMAZ (null) — fazladan dönem verilmez. */
export function donemSonu(abonelik: Record<string, unknown>, simdi: number = Date.now()): string | null {
  const orders = Array.isArray(abonelik.orders) ? (abonelik.orders as unknown[]) : []
  let enGec = NaN
  for (const o of orders) {
    if (!o || typeof o !== 'object') continue
    const sip = o as Record<string, unknown>
    if (String(sip.orderStatus ?? '').toUpperCase() !== 'SUCCESS') continue
    const t = zamanMs(sip.endPeriod)
    if (Number.isNaN(t)) continue
    if (Number.isNaN(enGec) || t > enGec) enGec = t
  }
  if (!Number.isNaN(enGec)) return new Date(enGec).toISOString()
  const durum = String(abonelik.subscriptionStatus ?? '').toUpperCase()
  if (durum === 'PENDING') {
    const deneme = zamanMs(abonelik.trialEndDate)
    return Number.isNaN(deneme) ? null : new Date(deneme).toISOString()
  }
  if (durum !== 'ACTIVE') return null
  const donem = planDonemi(String(abonelik.pricingPlanReferenceCode ?? ''))
  const bas = zamanMs(abonelik.startDate)
  if (!donem || Number.isNaN(bas)) return null
  for (let k = 1; k <= 1200; k++) {
    const son = donemEkle(bas, donem, k)
    if (son > simdi) return new Date(son).toISOString()
  }
  return null // 100 yıldan eski başlangıç = bozuk veri → tahmin yok
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
