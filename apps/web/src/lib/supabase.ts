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

/* TA T2 (Y292-3) · ŞİFRE SIFIRLAMA YALNIZ GERÇEK KURTARMA OTURUMUNDA. Eskiden `/sifre-sifirla` sayfası düz `SIGNED_IN` olayını ve
   o an var olan HERHANGİ bir oturumu "kurtarma hazır" sayıyordu → geçersiz / süresi dolmuş bağlantıyla gelen (ya da sayfayı elle
   açan) kişi, tarayıcıda girişli kalan hesabın şifresini değiştirebiliyordu. Kurtarma kanıtı = Supabase'in `PASSWORD_RECOVERY`
   olayı (bağlantıdaki `type=recovery` belirteci GERÇEKTEN doğrulanınca yayılır). Olay, istemci URL'yi işlerken (sayfa bileşeni
   yüklenmeden ÖNCE) yayılabildiği için dinleyici istemciyle AYNI anda, modül düzeyinde kurulur; kimlik kaydedilir ve sayfa
   gönderimde oturumdaki kullanıcının bu kimlik olduğunu yeniden denetler. Çıkışta (SIGNED_OUT) unutulur. */
let _kurtarmaKullanicisi: string | null = null
supabase.auth.onAuthStateChange((olay, oturum) => {
  if (olay === 'PASSWORD_RECOVERY') _kurtarmaKullanicisi = oturum?.user?.id ?? null
  else if (olay === 'SIGNED_OUT') _kurtarmaKullanicisi = null
})
/** Bu sekmede e-postadaki kurtarma bağlantısıyla doğrulanan kullanıcının kimliği; kurtarma yoksa null. */
export const kurtarmaKullanicisi = (): string | null => _kurtarmaKullanicisi
