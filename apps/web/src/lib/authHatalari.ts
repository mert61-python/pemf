import { COMPANY } from '../config'
import type { ParseKeys } from 'i18next'
import i18n from '../i18n'
// Author: mertaygn, cglrgrkn
/**
 * GİRİŞ/KAYIT HATALARININ TÜRKÇESİ + TEK ŞİFRE KURALI (metin denetimi 1. parti, 2026-08-20).
 *
 * NEDEN VAR:
 *  1. `AuthContext` Supabase'in HAM İNGİLİZCE mesajını (`error.message`) doğrudan ekrana
 *     basıyordu → veteriner hekim "Invalid login credentials" ya da "For security purposes,
 *     you can only request this after 60 seconds" görüyordu. Hata mesajının işi kullanıcıya
 *     NE YAPACAĞINI söylemektir; anlamadığı bir dilde bunu yapamaz.
 *  2. Şifre kuralı İKİ YERDE FARKLIYDI: kayıt formu `minLength={6}`, şifre yenileme ekranı
 *     "en az 8 + büyük/küçük/rakam". Kayıtta kabul edilen şifre yenilemede reddediliyordu.
 *     Kural artık TEK KAYNAK; iki ekran da buradan okur.
 *
 * ⚠️ GİRİŞ yolunda bu kural DAYATILMAZ: aynı parola alanı hem giriş hem kayıt için kullanılır
 * ve sahadaki eski hesaplar 6 haneli şifrelerle açılmış olabilir — girişte uzunluk dayatmak
 * kullanıcıyı kendi hesabından kilitlerdi. Doğrulama yalnız KAYIT ve YENİLEME akışlarında.
 */

/** Kayıt + şifre yenileme için TEK politika (uygulamanın kendi kuralıyla aynı). */
export const SIFRE_KURALI = {
  minUzunluk: 8,
  /** Kullanıcıya gösterilecek tek cümlelik açıklama (iki ekranda da aynı metin) — etkin dile göre OKUNUR (getter). */
  get aciklama(): string {
    return i18n.t('hesap.sifreKurali')
  },
} as const

export function sifreGecerliMi(pw: string): boolean {
  return (
    pw.length >= SIFRE_KURALI.minUzunluk &&
    /[A-ZÇĞİÖŞÜ]/.test(pw) &&
    /[a-zçğıöşü]/.test(pw) &&
    /\d/.test(pw)
  )
}

/**
 * Supabase mesaj metinleri → kullanıcının anlayacağı, EYLEM SÖYLEYEN karşılık (etkin dilde; tablo katalog ANAHTARI saklar).
 *
 * Eşleşme KÜÇÜK HARFE indirgenmiş "içerir" mantığıyla yapılır: Supabase mesajları sürümler
 * arasında noktalama/ek kelime düzeyinde değişiyor, tam eşitlik kırılgan olurdu.
 */
const ESLESMELER: ReadonlyArray<readonly [RegExp, ParseKeys]> = [
  [/invalid login credentials|invalid credentials/i, 'hesap.hata.epostaSifreHatali'],
  [/email not confirmed|email_not_confirmed/i, 'hesap.hata.epostaDogrulanmadi'],
  [/user already registered|already been registered/i, 'hesap.hata.hesapZatenVar'],
  [/password should be at least|password is too short|weak password/i, 'hesap.hata.sifreZayif'],
  [/after (\d+) seconds?/i, 'hesap.hata.cokSikDenendi'],
  [/rate limit|too many requests/i, 'hesap.hata.cokFazlaDeneme'],
  [/unable to validate email|invalid email/i, 'hesap.hata.epostaGecersiz'],
  [/network|fetch failed|failed to fetch/i, 'hesap.hata.sunucuyaUlasilamadi'],
  [/email address .*invalid|email_address_invalid/i, 'hesap.hata.epostaKabulEdilmedi'],
  [/same password|new password should be different/i, 'hesap.hata.sifreAyni'],
]

/**
 * Ham hata metnini Türkçeye çevirir.
 *
 * ⚠️ TANINMAYAN mesaj YUTULMAZ: hatayı görünmez yapmak, kullanıcıyı sessizce takılı bırakır.
 * Genel ama Türkçe ve yol gösteren bir karşılık döner.
 */
export function authHatasiTurkce(ham?: string | null): string {
  const m = (ham ?? '').trim()
  if (!m) return i18n.t('hesap.hata.beklenmeyen')
  for (const [desen, anahtar] of ESLESMELER) if (desen.test(m)) return i18n.t(anahtar, { aciklama: SIFRE_KURALI.aciklama })
  return i18n.t('hesap.hata.islemTamamlanamadi', { email: COMPANY.email })
}

/**
 * ÖDEME/ABONELİK HATALARININ TÜRKÇESİ (6. parti, adversaryal inceleme bulgusu).
 *
 * `api/checkout.ts` ve `api/cancel.ts`, iyzico'nun `errorMessage` alanını olduğu gibi geçiriyor;
 * ödeme ekranı ve hesap menüsü onu basıyordu. Auth tarafına konan kural (ham sağlayıcı metni
 * kullanıcıya gösterilmez) ödeme tarafında da geçerli: sağlayıcı metni günlüğe, kullanıcıya
 * Türkçe ve eylem söyleyen karşılık.
 */
export function odemeHatasiTurkce(ham?: string | null): string {
  const m = (ham ?? '').trim()
  if (m) console.error('[ödeme] sağlayıcı mesajı:', m)
  if (/insufficient|limit|yetersiz/i.test(m)) {
    return i18n.t('hesap.odeme.tahsilEdilemedi')
  }
  if (/3d|secure|authenticat/i.test(m)) {
    return i18n.t('hesap.odeme.bankaDogrulamadi')
  }
  if (/not found|no_subscription|bulunamadı/i.test(m)) {
    return i18n.t('hesap.odeme.abonelikYok', { email: COMPANY.email })
  }
  return i18n.t('hesap.hata.islemTamamlanamadi', { email: COMPANY.email })
}
