// Author: mertaygn, cglrgrkn
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

    // SÖZLEŞMEYE UYUM: yayınlanan Mesafeli Satış / İptal-İade metinleri "iptal, içinde bulunulan
    // (bedeli tahsil edilmiş) dönemin SONUNDA geçerli olur; bu dönem sonuna kadar erişim devam
    // eder" diyor. Kod ise tier'ı ANINDA 'baslangic'e düşürüp hakkı hemen kesiyordu → ödenmiş
    // dönemin ortasında erişim kaybı, yayınlanan sözleşmeye açık aykırılık. Tier KORUNUR; yalnız
    // yenileme durdurulur (status='canceled'), erişim `current_period_end`e kadar sürer.
    try {
      await upsertSubscription({
        user_id: user.id,
        status: 'canceled',
        updated_at: new Date().toISOString(),
      })
    } catch (e) {
      // iyzico iptali BAŞARILI oldu; yalnız yerel yansıtma patladı. Eskiden bu durumda
      // kullanıcıya "İptal edilemedi" deniyordu → aslında iptal edilmiş aboneliği tekrar
      // iptal etmeye çalışıyor, panikliyordu. Doğruyu söyle, senkron farkını logla.
      console.error('cancel: iyzico iptali başarılı ama Supabase yansıtması başarısız', e)
      return res.status(200).json({
        canceled: true,
        warning: 'Abonelik iptal edildi; hesap durumunuz birkaç dakika içinde güncellenecek.',
      })
    }
    return res.status(200).json({ canceled: true })
  } catch (e) {
    console.error('cancel error', e)
    return res.status(500).json({ error: 'server', message: 'İşlem tamamlanamadı. Lütfen daha sonra tekrar deneyin.' })
  }
}
