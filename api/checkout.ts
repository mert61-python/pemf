/* POST /api/checkout — iyzico Abonelik CheckoutForm başlatır.
   Body: { tier:'pro'|'pro_plus', yearly, research, token:<supabase_jwt>, origin, customer:{...} }
   customer: name, surname, identityNumber(TC), gsmNumber, city, address, (zipCode). Döner:
   { content: checkoutFormContent, token } → frontend gömer; ödeme sonrası /api/callback. */
import type { VercelRequest, VercelResponse } from '@vercel/node'
import Iyzipay from 'iyzipay'
import { verifyUser } from './_lib/util.js'
import { planRef, subInitialize } from './_lib/iyzico.js'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'method' })
  try {
    const { tier, yearly, research, token, origin, customer } = (req.body ?? {}) as {
      tier?: string; yearly?: boolean; research?: boolean; token?: string; origin?: string
      customer?: Record<string, string>
    }
    if (tier !== 'pro' && tier !== 'pro_plus') return res.status(400).json({ error: 'tier' })

    const user = await verifyUser(token ?? '')
    if (!user) return res.status(401).json({ error: 'auth', message: 'Önce giriş yapın.' })

    const c = customer ?? {}
    const required = ['name', 'surname', 'identityNumber', 'gsmNumber', 'city', 'address']
    for (const f of required) {
      if (!String(c[f] ?? '').trim()) {
        return res.status(400).json({ error: 'customer', message: `Zorunlu alan eksik: ${f}` })
      }
    }

    const base = origin || process.env.PUBLIC_SITE_URL || `https://${req.headers.host}`
    const fullName = `${c.name} ${c.surname}`.trim()
    const address = {
      contactName: fullName,
      city: c.city,
      country: 'Turkey',
      address: c.address,
      zipCode: c.zipCode || '00000',
    }

    const result = await subInitialize({
      locale: Iyzipay.LOCALE.TR,
      conversationId: user.id, // callback bunu da okuyabilir (uid fallback ayrıca query'de)
      pricingPlanReferenceCode: planRef(tier, !!research, !!yearly),
      subscriptionInitialStatus: Iyzipay.SUBSCRIPTION_INITIAL_STATUS.ACTIVE,
      callbackUrl: `${base}/api/callback?uid=${encodeURIComponent(user.id)}`,
      customer: {
        name: c.name,
        surname: c.surname,
        email: user.email || c.email || 'no-reply@pemf.vet',
        identityNumber: c.identityNumber,
        gsmNumber: c.gsmNumber,
        billingAddress: address,
        shippingAddress: address,
      },
    })

    if (result.status !== 'success' || !result.checkoutFormContent) {
      console.error('iyzico initialize fail', result.errorCode, result.errorMessage)
      return res.status(502).json({ error: 'iyzico', message: result.errorMessage || 'Ödeme formu oluşturulamadı.' })
    }
    return res.status(200).json({ content: result.checkoutFormContent, token: result.token })
  } catch (e) {
    console.error('checkout error', e)
    const msg = e instanceof Error ? e.message : 'Sunucu hatası'
    return res.status(500).json({ error: 'server', message: msg })
  }
}
