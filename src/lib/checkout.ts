// Author: mertaygn, cglrgrkn
import { supabase } from './supabase'

/* iyzico akışı: /odeme sayfası müşteri bilgisini toplar → initCheckout → checkoutFormContent döner
   → sayfa iyzico formunu gömer → ödeme sonrası /api/callback → Supabase subscriptions. */

export type CheckoutCustomer = {
  name: string
  surname: string
  identityNumber: string
  gsmNumber: string
  city: string
  address: string
  zipCode?: string
}
export type CheckoutPayload = {
  tier: 'pro' | 'pro_plus'
  yearly: boolean
  research: boolean
  customer: CheckoutCustomer
}

async function accessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

/** Aboneliği başlat → iyzico checkoutFormContent (gömülecek HTML/script) döner. */
export async function initCheckout(
  p: CheckoutPayload,
): Promise<{ content?: string; error?: string; needAuth?: boolean }> {
  const token = await accessToken()
  if (!token) return { needAuth: true }
  // Timeout YOKTU: yarı-açık bağlantıda istek ne çözülüyor ne reddediliyordu → "Hazırlanıyor…"
  // butonu sonsuza dek kilitli kalıyor, kullanıcı ödemeye geçemiyordu.
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 20000)
  try {
    const r = await fetch('/api/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...p, token, origin: window.location.origin }),
      signal: ctrl.signal,
    })
    const j = (await r.json().catch(() => ({}))) as { content?: string; message?: string; error?: string }
    if (!r.ok || !j.content) return { error: j.message || j.error || 'Ödeme başlatılamadı.' }
    return { content: j.content }
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') {
      return { error: 'Ödeme sunucusu yanıt vermedi (zaman aşımı). Tekrar deneyin.' }
    }
    return { error: 'Ağ hatası — tekrar deneyin.' }
  } finally {
    clearTimeout(timer)
  }
}

/** Aboneliği iptal et (iyzico'da hosted portal yok). */
export async function cancelSubscription(): Promise<{ ok?: boolean; error?: string }> {
  const token = await accessToken()
  if (!token) return { error: 'Önce giriş yapın.' }
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 20000)
  try {
    const r = await fetch('/api/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
      signal: ctrl.signal,
    })
    const j = (await r.json().catch(() => ({}))) as { canceled?: boolean; message?: string }
    if (!r.ok || !j.canceled) return { error: j.message || 'İptal edilemedi.' }
    return { ok: true }
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') {
      return { error: 'Sunucu yanıt vermedi (zaman aşımı). Aboneliğinizin durumunu birazdan kontrol edin.' }
    }
    return { error: 'Ağ hatası — tekrar deneyin.' }
  } finally {
    clearTimeout(timer)
  }
}
