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
  /** Kullanıcıya gösterilecek tek cümlelik açıklama (iki ekranda da aynı metin). */
  aciklama: 'En az 8 karakter; büyük harf, küçük harf ve rakam içermeli.',
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
 * Supabase mesaj metinleri → kullanıcının anlayacağı, EYLEM SÖYLEYEN Türkçe karşılık.
 *
 * Eşleşme KÜÇÜK HARFE indirgenmiş "içerir" mantığıyla yapılır: Supabase mesajları sürümler
 * arasında noktalama/ek kelime düzeyinde değişiyor, tam eşitlik kırılgan olurdu.
 */
const ESLESMELER: ReadonlyArray<readonly [RegExp, string]> = [
  [
    /invalid login credentials|invalid credentials/i,
    'E-posta veya şifre hatalı. Şifrenizi hatırlamıyorsanız "Şifremi unuttum" bağlantısını kullanın.',
  ],
  [
    /email not confirmed|email_not_confirmed/i,
    'E-posta adresiniz henüz doğrulanmadı. Size gönderdiğimiz doğrulama bağlantısına tıklayın, sonra tekrar giriş yapın.',
  ],
  [
    /user already registered|already been registered/i,
    'Bu e-posta adresiyle zaten kayıtlı bir hesap var. Giriş yapmayı ya da "Şifremi unuttum" ile şifrenizi yenilemeyi deneyin.',
  ],
  [
    /password should be at least|password is too short|weak password/i,
    `Şifre yeterince güçlü değil. ${SIFRE_KURALI.aciklama}`,
  ],
  [
    /after (\d+) seconds?/i,
    'Çok sık denendi. Güvenlik gereği kısa bir süre beklemeniz gerekiyor; birkaç saniye sonra tekrar deneyin.',
  ],
  [
    /rate limit|too many requests/i,
    'Çok fazla deneme yapıldı. Lütfen birkaç dakika sonra tekrar deneyin.',
  ],
  [
    /unable to validate email|invalid email/i,
    'E-posta adresi geçerli görünmüyor. Adresi kontrol edip tekrar deneyin.',
  ],
  [
    /network|fetch failed|failed to fetch/i,
    'Sunucuya ulaşılamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.',
  ],
  [
    /email address .*invalid|email_address_invalid/i,
    'Bu e-posta adresi kabul edilmedi. Farklı bir adres deneyin.',
  ],
  [
    /same password|new password should be different/i,
    'Yeni şifre eskisiyle aynı olamaz. Farklı bir şifre belirleyin.',
  ],
]

/**
 * Ham hata metnini Türkçeye çevirir.
 *
 * ⚠️ TANINMAYAN mesaj YUTULMAZ: hatayı görünmez yapmak, kullanıcıyı sessizce takılı bırakır.
 * Genel ama Türkçe ve yol gösteren bir karşılık döner.
 */
export function authHatasiTurkce(ham?: string | null): string {
  const m = (ham ?? '').trim()
  if (!m) return 'Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.'
  for (const [desen, karsilik] of ESLESMELER) if (desen.test(m)) return karsilik
  return 'İşlem tamamlanamadı. Lütfen tekrar deneyin; sorun sürerse destek@v-pemf.com adresine yazın.'
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
    return 'Ödeme kartınızdan tahsil edilemedi (limit/bakiye). Farklı bir kartla tekrar deneyebilirsiniz.'
  }
  if (/3d|secure|authenticat/i.test(m)) {
    return 'Bankanız işlemi doğrulayamadı. Kart bilgilerinizi kontrol edip tekrar deneyin.'
  }
  if (/not found|no_subscription|bulunamadı/i.test(m)) {
    return 'Hesabınızda aktif bir abonelik görünmüyor. Sorun sürerse destek@v-pemf.com adresine yazın.'
  }
  return 'İşlem tamamlanamadı. Lütfen tekrar deneyin; sorun sürerse destek@v-pemf.com adresine yazın.'
}
