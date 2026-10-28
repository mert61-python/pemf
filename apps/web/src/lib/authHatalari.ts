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

/** Ödeme formundaki kutuların ekran etiketleri (`Odeme.tsx` placeholder'larıyla AYNI anahtar) — hata metni kutuyu adıyla anar.
 *  Değişmez anahtarlı çağrılar (dinamik `t(degisken)` YOK — K-3 kapısı anahtarları katalogda doğrular). */
const ODEME_ALAN_ETIKETI: Record<string, () => string> = {
  name: () => i18n.t('odeme.ad'),
  surname: () => i18n.t('odeme.soyad'),
  identityNumber: () => i18n.t('odeme.tc'),
  gsmNumber: () => i18n.t('odeme.telefon'),
  city: () => i18n.t('hesap.alan.sehir'),
  address: () => i18n.t('odeme.adres'),
}

/**
 * ÖDEME BAŞLATMA HATASI (D6.30 · B-7.5): `api/checkout.ts` makine-okur `error` (kod) + `alan` + `sebep` döner; eskiden ekran HEPSİNİ
 * `odemeHatasiTurkce`ye sokuyordu → 409 "zaten aktif abonelik" ve "TC Kimlik No 11 haneli olmalı" gibi alan-özel iletiler genel
 * "İşlem tamamlanamadı … tekrar deneyin"e dönüşüyordu (kullanıcı neyi düzelteceğini / önce iptal etmesi gerektiğini bilemiyordu).
 * Ham sunucu metni YİNE ekrana basılmaz: metin koddan, kataloğdan kurulur; tanınmayan durum `odemeHatasiTurkce`ye düşer.
 */
export function odemeBaslatmaHatasi(h: { error?: string | null; kod?: string; alan?: string; sebep?: string }): string {
  if (h.kod === 'already_subscribed') return i18n.t('hesap.odeme.zatenAbone')
  if (h.kod === 'customer') {
    if (h.sebep === 'bicim' && h.alan === 'identityNumber') return i18n.t('hesap.odeme.tcBicim')
    if (h.sebep === 'bicim' && h.alan === 'gsmNumber') return i18n.t('hesap.odeme.telefonBicim')
    if (h.sebep === 'uzun') return i18n.t('hesap.odeme.adresUzun')
    const etiket = h.alan && Object.hasOwn(ODEME_ALAN_ETIKETI, h.alan) ? ODEME_ALAN_ETIKETI[h.alan] : undefined
    if (h.sebep === 'eksik' && etiket) return i18n.t('hesap.odeme.alanEksik', { alan: etiket() })
  }
  return odemeHatasiTurkce(h.error)
}
