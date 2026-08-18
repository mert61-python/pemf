// Author: mertaygn, cglrgrkn
import { createClient } from '@supabase/supabase-js'

/* Tarayıcı Supabase istemcisi — abonelik için giriş (aynı hesap mobil/client ile).
   Public anahtarlar GÖMÜLÜ (fallback) → Vercel env OLMASA DA çalışır ve createClient boş-URL'de
   ÇÖKMEZ (aksi halde "supabaseUrl is required" throw → tüm SPA siyah ekran). anon/publishable
   anahtar RLS ile korunur, istemci paketinde zaten açıktır → gömmek güvenli. */
const SUPABASE_URL = 'https://wmsxonunkphjeregpvuj.supabase.co'
const SUPABASE_ANON = 'sb_publishable_D2SaRML_PIhRtr3kqlXxaw_1cS75GKT'

const url = (import.meta.env.VITE_SUPABASE_URL as string | undefined) || SUPABASE_URL
const anon = (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined) || SUPABASE_ANON

export const supabaseReady = Boolean(url && anon)

/** Oturum ayarları AYRI sabit: indirme kapısı buna dayanıyor — `persistSession` kapanırsa
 *  kullanıcı sekmeyi her kapattığında yeniden giriş yapmak zorunda kalır (kapı bir kayıt
 *  adımıdır, her indirmede tekrarlanan bir engel DEĞİL). Test bunu regresyona karşı kilitler. */
export const AUTH_OPTIONS = {
  persistSession: true, // localStorage → oturum tarayıcıda kalıcı
  autoRefreshToken: true, // uzun aradan sonra da geçerli oturum
  detectSessionInUrl: true, // e-posta doğrulama / şifre sıfırlama dönüşü
} as const

export const supabase = createClient(url, anon, { auth: { ...AUTH_OPTIONS } })
