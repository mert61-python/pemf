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

/** Plan → aylık jeton hakkı — JETON-SISTEMI Adım 3 (2026-08-22).
 *  ⚠️ TEK KAYNAK `src/config.ts::JETON.planHaklari`dır; api/ katmanı src/'den import ETMEZ
 *  (Vercel işlev paketi sınırı) → değer burada ELLE eşlenir ve ayrışması testle kilitlidir
 *  (`jeton-yenileme.test.ts` — borç tavanının web↔cihaz paritesiyle aynı desen).
 *  `kullandikca` BİLEREK YOK: o üyeliğin aylık hakkı yoktur (harcadıkça faturalanır). */
export const JETON_HAKLARI: Record<string, number> = { baslangic: 50, pro: 500, pro_plus: 2000 }

/** Plan dönemi yenilendiğinde jeton hakkını yazar (service_role — RPC'yi kullanıcı çağıramaz;
 *  canlıda anon+authenticated execute'ları bilerek geri alındı, bkz. supabase_jetonlar.sql).
 *  ⚠️ İdempotan-ımsı: RPC aylık hakkı SET eder (toplamaz) → aynı dönemde iki kez çağrılması
 *  bakiyeyi şişirmez. Başarısızlıkta FIRLATIR — çağıran loglayıp yutar (sessiz kayıp olmasın). */
export async function jetonDonemYenile(userId: string, aylikHak: number): Promise<void> {
  const r = await fetch(`${SB_URL()}/rest/v1/rpc/jeton_donem_yenile`, {
    method: 'POST',
    headers: {
      apikey: SB_SERVICE(),
      Authorization: `Bearer ${SB_SERVICE()}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ p_user: userId, p_aylik_hak: aylikHak }),
  })
  if (!r.ok) throw new Error(`jeton_donem_yenile ${r.status}: ${await r.text()}`)
}

/** iyzico'da HÂLÂ CANLI sayılan abonelik durumları.
 *  `canceled` KASTEN yok: iptal edilmiş abonelik yeni satın almayı engellememeli. */
const CANLI_DURUMLAR = ['active', 'trialing', 'past_due'] as const

/** user_id → CANLI aboneliğin iyzico subscriptionReferenceCode'u (iptal + çift-abonelik kapısı).
 *
 *  ⚠️ DURUM FİLTRESİ ŞART (denetim 2026-08-18): filtre YOKTU ve `api/cancel.ts` iptalde
 *  `stripe_subscription_id`i satırda BIRAKIYOR (bilerek — `getUserBySubscriptionRef` webhook'ta
 *  o referansla kullanıcıyı buluyor). Sonuç: iptal eden kullanıcıya `api/checkout.ts` sonsuza dek
 *  409 "Hesabınızda zaten aktif bir abonelik var … önce mevcut aboneliğinizi iptal edin" diyordu →
 *  bir daha abone OLAMIYOR, plan da DEĞİŞTİREMİYOR ve mesaj ona zaten yaptığı şeyi söylüyordu.
 *  Tekrar "iptal et"e basınca iyzico zaten iptal edilmiş aboneliği reddediyor (502) → çıkışsız döngü.
 *  ⚠️ `past_due` CANLI sayılır: ödeme aksamış ama abonelik iyzico'da duruyor; onu ikizlemek
 *  kullanıcıyı iki kez tahsilata açardı (checkout.ts'teki yetim-kayıt gerekçesi).
 *  ⚠️ Filtre SUNUCUDA: iptal edilmiş aboneliğin referansı ağa hiç çıkmasın. */
export async function getSubscriptionRefByUser(userId: string): Promise<string | null> {
  if (!userId) return null
  const durumlar = `in.(${CANLI_DURUMLAR.join(',')})`
  const r = await fetch(
    `${SB_URL()}/rest/v1/subscriptions?user_id=eq.${encodeURIComponent(userId)}` +
      `&status=${encodeURIComponent(durumlar)}&select=stripe_subscription_id`,
    { headers: { apikey: SB_SERVICE(), Authorization: `Bearer ${SB_SERVICE()}` } },
  )
  // ⚠️ FAIL-CLOSED (denetim 2026-08-18): burada `if (!r.ok) return null` vardı ve iki çağıranın
  // ihtiyacı ZITTIR. `api/checkout.ts` için `null` = "aboneliği yok" demektir → Supabase 5xx /
  // anahtar / RLS hatası anında, zaten abonesi olan kullanıcıya İKİNCİ abonelik açılırdı: iki
  // iyzico aboneliğinden de tahsilat yapılır ve `subscriptions.user_id` PRIMARY KEY olduğundan
  // callback satırı EZER → eski referans kaybolur, `/api/cancel` onu bir daha BULAMAZ. Kapı tam
  // da bu "yetim kayıt"ı önlemek için yazılmıştı (checkout.ts:23-27) ama hata anında kendisi
  // açılıyordu. `api/cancel.ts` için `null` yalnız 404 "abonelik bulunamadı" demek — para
  // hareketi yok. Para hareketi olan yön belirleyicidir: BELİRSİZLİK HATA'dır.
  // İki uç da bu istisnayı zaten yakalıyor ve dürüst "sonra tekrar deneyin" mesajı dönüyor.
  if (!r.ok) throw new Error(`subscriptions okunamadı ${r.status}`)
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
  // sessizce iptal ediliyordu. Bilinmeyeni "askıda" say ve elle inceleme için iz bırak.
  //
  // ⚠️ DÜZELTİLMİŞ İDDİA (denetim 2026-08-18): buradaki eski yorum "erişim korunur" diyordu —
  // ÖLÇÜLDÜ, DOĞRU DEĞİL. Hakkı okuyan iki katman da `past_due`yu tıpkı `canceled` gibi PASİF
  // sayıyor: `guii/servers/entitlement.py` `_INACTIVE_STATUS` kümesinde `past_due` VAR (tier
  // 'baslangic'e düşer, eklentiler boşalır) ve `pf/src/config/entitlement.ts` `isActive` yalnız
  // `active`/`trialing` kabul ediyor. Yani bu eşleme YALNIZCA kaydedilen dizeyi değiştiriyor,
  // kullanıcının hakkını `canceled`dan farklı kılmıyor. Kazanç gerçek ama daha küçük: `past_due`
  // satırı `getSubscriptionRefByUser`ta CANLI sayıldığı için abonelik iptal edilebilir ve
  // yanlışlıkla ikinci bir abonelik açılmaz. Gerçekten "erişim korunsun" isteniyorsa karar
  // TÜKETİCİLERDE verilmeli (sahip kararı) — burada tek başına yapılamaz.
  console.warn('iyzico: bilinmeyen subscriptionStatus, past_due sayıldı', { status: s })
  return 'past_due'
}
