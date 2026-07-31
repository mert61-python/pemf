/* POST /api/cancel — aboneliği iptal eder (iyzico'da hosted billing portal yok).
   Body: { token:<supabase_jwt> }. Kullanıcının subscriptionReferenceCode'u Supabase'ten alınır. */
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { verifyUser, getSubscriptionRefByUser, upsertSubscription } from './_lib/util.js'
import { subCancel } from './_lib/iyzico.js'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'method' })
  try {
    const { token } = (req.body ?? {}) as { token?: string }
    const user = await verifyUser(token ?? '')
    if (!user) return res.status(401).json({ error: 'auth', message: 'Önce giriş yapın.' })

    const subRef = await getSubscriptionRefByUser(user.id)
    if (!subRef) return res.status(404).json({ error: 'no_subscription', message: 'Aktif abonelik bulunamadı.' })

    const result = await subCancel(subRef)
    if (result.status !== 'success') {
      return res.status(502).json({ error: 'iyzico', message: result.errorMessage || 'İptal edilemedi.' })
    }

    // Supabase'i anında yansıt (webhook de gelir). Hak baslangic'e düşer.
    await upsertSubscription({
      user_id: user.id,
      tier: 'baslangic',
      status: 'canceled',
      addons: [],
      updated_at: new Date().toISOString(),
    })
    return res.status(200).json({ canceled: true })
  } catch (e) {
    console.error('cancel error', e)
    const msg = e instanceof Error ? e.message : 'Sunucu hatası'
    return res.status(500).json({ error: 'server', message: msg })
  }
}
