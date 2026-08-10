// Author: mertaygn, cglrgrkn
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
    // IDOR: `?uid=` KİMLİKSİZ bir sorgu parametresidir ve eskiden conversationId boşsa doğrudan
    // user_id olarak GÜVENİLİYORDU. Geçerli bir iyzico token'ı ele geçiren biri, aboneliği
    // istediği kullanıcıya yazdırabilir; `subscriptions.user_id` PRIMARY KEY olduğundan bu,
    // kurbanın satırını EZER (Pro+ → düşük tier "downgrade" saldırısı). Otorite iyzico'dan
    // dönen conversationId'dir; uid yalnız onunla BİREBİR eşleşirse yedek olarak kabul edilir.
    const conversationId = String(r.conversationId ?? '')
    if (uidQuery && conversationId && uidQuery !== conversationId) {
      console.error('callback: uid/conversationId uyuşmuyor — istek reddedildi', { conversationId })
      return res.redirect(302, '/pricing?checkout=error')
    }
    const userId = conversationId || uidQuery
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
    // GÖZLEMLENEBİLİRLİK: ödeme alınmış ama alan eşlemesi tutmamış olabilir (plan referans kodu
    // env'de tanımsız, conversationId boş, status beklenmedik). Eskiden sessizce 'incomplete'e
    // yönlendiriliyordu → para tahsil edilmiş kullanıcı hakkı olmadan kalıyor ve GERİYE DÖNÜK
    // teşhis için hiçbir iz bulunmuyordu. Sırları değil, yalnız eşleme alanlarını logla.
    console.error('callback: abonelik yazılamadı', {
      hasUserId: !!userId,
      planRef: String(r.pricingPlanReferenceCode ?? ''),
      planResolved: !!meta,
      subRef,
      status,
    })
    return res.redirect(302, '/pricing?checkout=incomplete')
  } catch (e) {
    console.error('callback error', e)
    return res.redirect(302, '/pricing?checkout=error')
  }
}
