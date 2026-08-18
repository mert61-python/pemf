// Author: mertaygn, cglrgrkn
/* POST /api/webhook — iyzico abonelik bildirimi (ilk + tekrarlayan ödemeler).
   iyzico paneli: Ayarlar > Üye İşyeri > Abonelik Bildirimleri → bu URL.
   Güvenlik: imza doğrulanır (X-IYZ-SIGNATURE-V3); ANCAK subscription AYRICA iyzico'dan yeniden
   çekilir (authoritative) → sahte webhook gerçek olmayan veriyle hak veremez. İmza şeması iyzico'da
   sürümlenebildiğinden varsayılan STRICT DEĞİL (tutmazsa uyarır ama re-fetch ile işler);
   IYZICO_WEBHOOK_STRICT=1 → imza tutmazsa 401. */
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { upsertSubscription, mapIyzicoStatus, getUserBySubscriptionRef } from './_lib/util.js'
import { subRetrieveByRef, planMeta, verifyWebhookSignature } from './_lib/iyzico.js'

// HIZ SINIRI (kabaca): uç kimliksizdir ve her istek DIŞ bir iyzico API çağrısı + service_role
// Supabase sorgusu tetikler → sınırsız istek doğrudan maliyet ve kota tüketimi demektir.
// Vercel serverless'ta paylaşımlı durum yoktur; bu sayaç yalnız SICAK örnek ömrü boyunca geçerlidir
// (tam koruma değil, kötüye kullanımı büyük ölçüde kırar). Gerçek koruma iyzico imzasıdır;
// IYZICO_WEBHOOK_STRICT=1 ile imzasız istekler tümüyle reddedilebilir.
const RATE_WINDOW_MS = 60_000
const RATE_MAX_PER_REF = 10
const _hits = new Map<string, number[]>()
function rateLimited(key: string): boolean {
  const now = Date.now()
  const arr = (_hits.get(key) ?? []).filter((t) => now - t < RATE_WINDOW_MS)
  arr.push(now)
  _hits.set(key, arr)
  if (_hits.size > 500) {
    // Sınırsız büyümeyi engelle (bellek): en eski girdileri at.
    for (const k of Array.from(_hits.keys()).slice(0, 250)) _hits.delete(k)
  }
  return arr.length > RATE_MAX_PER_REF
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'method' })

  const body = (req.body ?? {}) as Record<string, unknown>
  const sigOk = verifyWebhookSignature(body, req.headers['x-iyz-signature-v3'] as string | undefined)
  if (!sigOk) {
    console.warn('iyzico webhook imza tutmadı', { event: body.iyziEventType })
    if ((process.env.IYZICO_WEBHOOK_STRICT ?? '0') === '1') {
      return res.status(401).json({ error: 'signature' })
    }
  }

  const subRef = String(body.subscriptionReferenceCode ?? '')
  if (!subRef) return res.status(200).json({ ignored: true })
  if (rateLimited(subRef)) {
    console.warn('iyzico webhook: hız sınırı aşıldı', { subRef })
    return res.status(429).json({ error: 'rate_limited' })
  }

  try {
    // AUTHORITATIVE: subscription'ı iyzico'dan yeniden çek (sahte payload'a güvenme)
    const sub = await subRetrieveByRef(subRef)
    // KURTARMA: kullanıcı eskiden YALNIZ callback'in yazdığı satırdan bulunabiliyordu. Callback
    // kaçarsa (tarayıcı kapandı / o an 500 alındı) satır hiç oluşmuyor, webhook userId bulamıyor
    // ve SESSİZCE 200 dönüyordu → iyzico "başarılı" sayıp bir daha DENEMİYOR. Sonuç: para tahsil
    // edilmiş kullanıcı kalıcı olarak haksız kalıyor, /api/cancel de 404 verdiği için iptal bile
    // edemiyor. Artık ikinci bir eşleme yolu var: initialize'da conversationId = user.id yazılıyor.
    const userId =
      (await getUserBySubscriptionRef(subRef)) || String((sub as { conversationId?: string }).conversationId ?? '')
    const meta = planMeta(String(sub.pricingPlanReferenceCode ?? ''))
    if (userId && meta) {
      await upsertSubscription({
        user_id: userId,
        tier: meta.tier,
        status: mapIyzicoStatus(String(sub.subscriptionStatus ?? '')),
        addons: meta.research ? ['research'] : [],
        stripe_subscription_id: subRef,
        stripe_customer_id: String(sub.customerReferenceCode ?? ''),
        updated_at: new Date().toISOString(),
      })
      return res.status(200).json({ received: true })
    }
    // Hâlâ eşleşmediyse SESSİZCE 200 DÖNME: 500 dönerek iyzico'nun tekrar denemesini sağla ve
    // elle müdahale için iz bırak (sır loglama yok, yalnız eşleme alanları).
    console.error('iyzico webhook: abonelik kullanıcıya eşlenemedi', {
      subRef,
      planRef: String(sub.pricingPlanReferenceCode ?? ''),
      planResolved: !!meta,
      hasUserId: !!userId,
      event: body.iyziEventType,
    })
    return res.status(500).json({ error: 'unmatched_subscription' })
  } catch (e) {
    console.error('iyzico webhook işleme hatası', e)
    return res.status(500).json({ error: e instanceof Error ? e.message : 'hata' }) // iyzico retry etsin
  }
}
