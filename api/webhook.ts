/* POST /api/webhook — iyzico abonelik bildirimi (ilk + tekrarlayan ödemeler).
   iyzico paneli: Ayarlar > Üye İşyeri > Abonelik Bildirimleri → bu URL.
   Güvenlik: imza doğrulanır (X-IYZ-SIGNATURE-V3); ANCAK subscription AYRICA iyzico'dan yeniden
   çekilir (authoritative) → sahte webhook gerçek olmayan veriyle hak veremez. İmza şeması iyzico'da
   sürümlenebildiğinden varsayılan STRICT DEĞİL (tutmazsa uyarır ama re-fetch ile işler);
   IYZICO_WEBHOOK_STRICT=1 → imza tutmazsa 401. */
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { upsertSubscription, mapIyzicoStatus, getUserBySubscriptionRef } from './_lib/util.js'
import { subRetrieveByRef, planMeta, verifyWebhookSignature } from './_lib/iyzico.js'

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

  try {
    // AUTHORITATIVE: subscription'ı iyzico'dan yeniden çek (sahte payload'a güvenme)
    const sub = await subRetrieveByRef(subRef)
    const userId = await getUserBySubscriptionRef(subRef)
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
    }
    return res.status(200).json({ received: true })
  } catch (e) {
    console.error('iyzico webhook işleme hatası', e)
    return res.status(500).json({ error: e instanceof Error ? e.message : 'hata' }) // iyzico retry etsin
  }
}
