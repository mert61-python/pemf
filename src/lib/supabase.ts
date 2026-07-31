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

export const supabase = createClient(url, anon, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
})
