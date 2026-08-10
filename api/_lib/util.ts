// Author: mertaygn, cglrgrkn
/* Ortak yardımcılar (Vercel serverless) — SAĞLAYICI-AGNOSTİK Supabase katmanı.
   A1: abonelik web'de satılır (iyzico), webhook Supabase `subscriptions`e yazar (service_role);
   mobil/backend yalnız okur. `_lib` → Vercel endpoint saymaz. */

export function env(name: string, required = true): string {
  const v = process.env[name] ?? ''
  if (required && !v) throw new Error(`Eksik ortam değişkeni: ${name}`)
  return v
}

const SB_URL = () => env('SUPABASE_URL')
const SB_ANON = () => env('SUPABASE_ANON_KEY')
const SB_SERVICE = () => env('SUPABASE_SERVICE_ROLE_KEY')

/** İstemciden gelen `origin` yalnız İZİN LİSTESİNDEYSE kabul edilir (ödeme geri-dönüş adresi
 *  keyfi bir host'a yönlendirilemesin). Liste: PUBLIC_SITE_URL + EXTRA_ALLOWED_ORIGINS (virgüllü)
 *  + Vercel önizleme dağıtımları (*.vercel.app). */
export function isAllowedOrigin(origin: unknown): boolean {
  if (typeof origin !== 'string' || !origin) return false
  let u: URL
  try {
    u = new URL(origin)
  } catch {
    return false
  }
  if (u.protocol !== 'https:') return false
  const allow = [process.env.PUBLIC_SITE_URL ?? '', ...(process.env.EXTRA_ALLOWED_ORIGINS ?? '').split(',')]
    .map((s) => s.trim())
    .filter(Boolean)
  for (const a of allow) {
    try {
      if (new URL(a).host === u.host) return true
    } catch {
      /* bozuk yapılandırma girdisi — atla */
    }
  }
  return u.host.endsWith('.vercel.app')
}

/** Supabase JWT doğrula → kullanıcı (id, email). Geçersiz/eksikse null. */
export async function verifyUser(token: string): Promise<{ id: string; email: string } | null> {
  if (!token) return null
  const r = await fetch(`${SB_URL()}/auth/v1/user`, {
    headers: { apikey: SB_ANON(), Authorization: `Bearer ${token}` },
  })
  if (!r.ok) return null
  const u = (await r.json()) as { id?: string; email?: string }
  return u?.id ? { id: u.id, email: u.email ?? '' } : null
}

/** service_role ile subscriptions upsert (RLS bypass — kullanıcı asla yazamaz, yalnız webhook/callback). */
export async function upsertSubscription(row: Record<string, unknown>): Promise<void> {
  const r = await fetch(`${SB_URL()}/rest/v1/subscriptions`, {
    method: 'POST',
    headers: {
      apikey: SB_SERVICE(),
      Authorization: `Bearer ${SB_SERVICE()}`,
      'Content-Type': 'application/json',
      Prefer: 'resolution=merge-duplicates',
    },
    body: JSON.stringify(row),
  })
  if (!r.ok) throw new Error(`subscriptions upsert ${r.status}: ${await r.text()}`)
}

/** user_id → iyzico subscriptionReferenceCode (iptal için). */
export async function getSubscriptionRefByUser(userId: string): Promise<string | null> {
  if (!userId) return null
  const r = await fetch(
    `${SB_URL()}/rest/v1/subscriptions?user_id=eq.${encodeURIComponent(userId)}&select=stripe_subscription_id`,
    { headers: { apikey: SB_SERVICE(), Authorization: `Bearer ${SB_SERVICE()}` } },
  )
  if (!r.ok) return null
  const rows = (await r.json()) as Array<{ stripe_subscription_id?: string }>
  return rows?.[0]?.stripe_subscription_id ?? null
}

/** iyzico subscriptionReferenceCode → user_id. Callback'te yazıldı; webhook (recurring) burdan bulur. */
export async function getUserBySubscriptionRef(refCode: string): Promise<string | null> {
  if (!refCode) return null
  const r = await fetch(
    `${SB_URL()}/rest/v1/subscriptions?stripe_subscription_id=eq.${encodeURIComponent(refCode)}&select=user_id`,
    { headers: { apikey: SB_SERVICE(), Authorization: `Bearer ${SB_SERVICE()}` } },
  )
  if (!r.ok) return null
  const rows = (await r.json()) as Array<{ user_id?: string }>
  return rows?.[0]?.user_id ?? null
}

/** iyzico subscriptionStatus → tablo status enum. Bilinmeyen/pasif → canceled. */
export function mapIyzicoStatus(s: string): 'trialing' | 'active' | 'past_due' | 'canceled' {
  const v = (s || '').toUpperCase()
  if (v === 'ACTIVE') return 'active'
  if (v === 'PENDING') return 'trialing'
  if (v === 'UNPAID') return 'past_due'
  if (v === 'CANCELED' || v === 'EXPIRED' || v === 'UPGRADED') return 'canceled'
  // BİLİNMEYEN durum eskiden koşulsuz 'canceled'a düşüyordu: iyzico yeni/beklenmedik bir statü
  // (ör. 'RETRY', boş gövde, geçici sağlayıcı hatası) döndüğünde ÖDEYEN kullanıcının hakkı
  // sessizce iptal ediliyordu. Bilinmeyeni "askıda" say (erişim korunur, tahsilat takibi sürer)
  // ve elle inceleme için iz bırak.
  console.warn('iyzico: bilinmeyen subscriptionStatus, past_due sayıldı', { status: s })
  return 'past_due'
}
