// Author: mertaygn, cglrgrkn
/* POST /api/checkout — iyzico Abonelik CheckoutForm başlatır.
   Body: { tier:'pro'|'pro_plus', yearly, research, token:<supabase_jwt>, origin, customer:{...} }
   customer: name, surname, identityNumber(TC), gsmNumber, city, address, (zipCode). Döner:
   { content: checkoutFormContent, token } → frontend gömer; ödeme sonrası /api/callback. */
import type { VercelRequest, VercelResponse } from '@vercel/node'
import Iyzipay from 'iyzipay'
import { verifyUser, getSubscriptionRefByUser, isAllowedOrigin } from './_lib/util.js'
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

    // ÇİFT ABONELİK / YETİM KAYIT: `subscriptions.user_id` PRIMARY KEY olduğundan ikinci bir
    // ödemenin callback'i satırı EZER ve `stripe_subscription_id` yeni referansla değişir. Eski
    // iyzico aboneliğinin referansı artık hiçbir yerde tutulmadığından /api/cancel onu bulamaz →
    // kullanıcı iki abonelikten de tahsil edilir ama yalnız yenisini iptal edebilir. Yeni abonelik
    // başlatmadan önce mevcut olanı engelle.
    const existingRef = await getSubscriptionRefByUser(user.id)
    if (existingRef) {
      return res.status(409).json({
        error: 'already_subscribed',
        message: 'Hesabınızda zaten aktif bir abonelik var. Plan değiştirmek için önce mevcut aboneliğinizi iptal edin.',
      })
    }

    const c = customer ?? {}
    // Metin denetimi 2026-08-20: eksik alan mesajı KOD ANAHTARINI basıyordu ("Zorunlu alan
    // eksik: identityNumber") — kullanıcı formda o adı göremediği için hangi kutuyu dolduracağını
    // bilmiyordu. Ekrandaki etiketin AYNISI gösterilir.
    const ZORUNLU: ReadonlyArray<readonly [string, string]> = [
      ['name', 'Ad'],
      ['surname', 'Soyad'],
      ['identityNumber', 'TC Kimlik No'],
      ['gsmNumber', 'Telefon'],
      ['city', 'Şehir'],
      ['address', 'Adres'],
    ]
    for (const [alan, etiket] of ZORUNLU) {
      if (!String(c[alan] ?? '').trim()) {
        return res.status(400).json({ error: 'customer', message: `Lütfen "${etiket}" alanını doldurun.` })
      }
    }
    // BİÇİM DOĞRULAMASI: alanlar eskiden yalnız "boş değil" diye kontrol ediliyordu → hatalı TC/GSM
    // iyzico'ya gidip anlamsız bir sağlayıcı hatasıyla dönüyordu; ayrıca sınırsız uzunlukta adres
    // kabul ediliyordu. Kullanıcıya net mesaj ver, uç noktayı da sınırla.
    if (!/^\d{11}$/.test(String(c.identityNumber).trim())) {
      return res.status(400).json({ error: 'customer', message: 'TC Kimlik No 11 haneli olmalıdır.' })
    }
    if (!/^\+?\d{10,15}$/.test(String(c.gsmNumber).replace(/\s/g, ''))) {
      return res.status(400).json({ error: 'customer', message: 'Telefon numarası geçersiz (ör. +905xxxxxxxxx).' })
    }
    if (String(c.address).trim().length > 400 || String(c.city).trim().length > 60) {
      return res.status(400).json({ error: 'customer', message: 'Adres veya şehir alanı çok uzun.' })
    }

    // AÇIK YÖNLENDİRME: `origin` İSTEMCİ GÖVDESİNDEN geliyordu ve doğrulanmadan iyzico
    // callbackUrl'ine yazılıyordu; `req.headers.host` yedeği de Host-header enjeksiyonuna açıktı.
    // Ödemenin geri dönüş adresi ASLA istemciye bırakılmamalı — sunucu yapılandırmasına sabitle.
    const configured = process.env.PUBLIC_SITE_URL || (req.headers.host ? `https://${req.headers.host}` : '')
    const base = isAllowedOrigin(origin) ? String(origin).replace(/\/$/, '') : configured
    if (!base) {
      return res.status(500).json({ error: 'server', message: 'Site adresi yapılandırılmamış.' })
    }
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
    // İç hata mesajı (eksik env değişkeninin ADI, PostgREST yanıt gövdesi vb.) eskiden istemciye
    // dönüyor ve kullanıcıya alert'leniyordu → yapılandırma/altyapı sızıntısı. Ayrıntı yalnız
    // sunucu log'unda kalsın.
    console.error('checkout error', e)
    return res.status(500).json({ error: 'server', message: 'Ödeme başlatılamadı. Lütfen daha sonra tekrar deneyin.' })
  }
}
