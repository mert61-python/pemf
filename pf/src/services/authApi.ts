// Author: mertaygn, cglrgrkn
/**
 * authApi — operatör hesabı DOĞRULAMA yardımcıları + oturum-şekli.
 * Auth AKSİYONLARI (kayıt/giriş/şifre-sıfırlama/e-posta-doğrulama) artık SUPABASE AUTH'ta:
 * services/supabaseAuth.ts. Oturum supabase-js ile kalıcı; cihaz-token (X-API-Key) katmanı ayrı.
 * Şifre kuralı: ≥8 karakter + büyük + küçük + rakam (Supabase min-6'dan güçlü — biz öneriyoruz).
 * `.edu` içeren e-posta → araştırma modu.
 */

/** Kullanıcı profili — kayıt formunda toplanır, Supabase user_metadata'da saklanır.
 *
 * ⚠️ ALANLAR PROFİLE GÖRE AYRIŞIR (2026-08-07): profil HER AÇILIŞTA seçilir ve kalıcı
 * değildir (bilinçli karar) → aynı hesap bugün veteriner, yarın araştırmacı olabilir.
 * Bu yüzden TÜM alanlar tek şemada saklanır, ama Ayarlar ekranı yalnız AKTİF profile ait
 * olanları gösterir/düzenler. Gösterilmeyen alanlar KAYBOLMAZ — kaydederken korunur. */
export interface VetProfile {
  // ── Ortak (her profilde) ──
  first_name?: string;
  last_name?: string;
  full_name?: string;
  title?: string;        // ünvan (örn. Vet. Hekim / Dr. Öğr. Üyesi)
  phone?: string;        // kişisel cep
  city?: string;
  district?: string;
  address?: string;
  // ── Yalnız VETERİNER profili ──
  clinic_name?: string;
  clinic_phone?: string; // klinik acil telefon (AiHub arama)
  // ── Yalnız ARAŞTIRMA profili ──
  institution?: string;    // üniversite / kurum / enstitü
  department?: string;     // bölüm / anabilim dalı
  academic_title?: string; // akademik ünvan (opsiyonel)
}

export interface AuthSession {
  email: string;
  token: string;
  profile?: VetProfile;
}

// ── Doğrulama (UI + kayıt öncesi) ─────────────────────────────────────────────
export function passwordChecks(pw: string) {
  const s = pw || "";
  return {
    length: s.length >= 8,
    upper: /[A-Z]/.test(s),
    lower: /[a-z]/.test(s),
    digit: /\d/.test(s),
  };
}
export function isPasswordValid(pw: string): boolean {
  const c = passwordChecks(pw);
  return c.length && c.upper && c.lower && c.digit;
}
export function isEmailValid(email: string): boolean {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test((email || "").trim());
}
/** `.edu` akademik e-posta → kayıtta klinik alanları opsiyonel (araştırmacının kliniği yok).
 *  NOT: araştırma MODU erişimi artık buna bağlı DEĞİL (WelcomeScreen'de .edu gate kaldırıldı). */
export function isResearchEmail(email: string): boolean {
  return (email || "").toLowerCase().includes(".edu");
}
