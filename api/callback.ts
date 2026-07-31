/* GET/POST /api/callback — iyzico ödeme sonrası buraya yönlendirir (token). Aboneliği retrieve ile
   AUTHORITATIVE çeker → Supabase subscriptions'a yazar → kullanıcıyı sonuç sayfasına redirect eder.
   user_id: retrieve.conversationId (initialize'da set edildi) veya ?uid fallback. */
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { upsertSubscription, mapIyzicoStatus } from './_lib/util.js'
import { subRetrieveByToken, planMeta } from './_lib/iyzico.js'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const body = (req.body ?? {}) as Record<string, string>
  const token = String(body.token || (req.query?.token as string) || '')
  const uidQuery = String((req.query?.uid as string) || '')

  if (!token) return res.redirect(302, '/pricing?checkout=error')

  try {
    const r = await subRetrieveByToken(token)
    const userId = String(r.conversationId ?? '') || uidQuery
    const meta = planMeta(String(r.pricingPlanReferenceCode ?? ''))
    const subRef = String(r.referenceCode ?? '')
    const custRef = String(r.customerReferenceCode ?? '')
    const status = mapIyzicoStatus(String(r.subscriptionStatus ?? ''))

    if (userId && meta && subRef && (status === 'active' || status === 'trialing')) {
      await upsertSubscription({
        user_id: userId,
        tier: meta.tier,
        status,
        addons: meta.research ? ['research'] : [],
        stripe_subscription_id: subRef, // iyzico subscriptionReferenceCode (sütun yeniden kullanıldı)
        stripe_customer_id: custRef, // iyzico customerReferenceCode
        updated_at: new Date().toISOString(),
      })
      return res.redirect(302, '/download?checkout=success')
    }
    return res.redirect(302, '/pricing?checkout=incomplete')
  } catch (e) {
    console.error('callback error', e)
    return res.redirect(302, '/pricing?checkout=error')
  }
}
