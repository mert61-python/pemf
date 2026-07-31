/**
 * supabaseAuth — operatör hesabı artık SUPABASE AUTH ile (e-posta/şifre + GERÇEK e-posta doğrulama
 * + e-posta ile şifre-sıfırlama; endüstri standardı, ücretsiz). Yerel auth_db devralındı.
 *
 * Akış: signUp → Supabase doğrulama e-postası gönderir → kullanıcı linke tıklar → AUTH_VERIFY_URL
 * (GitHub Pages "onaylandı" sayfası) açılır → uygulamaya dönüp giriş yapar. Oturum supabase-js ile
 * KALICI ve GÜVENLİ: native'de SecureStore (Keychain/Keystore, parçalı), web'de AsyncStorage.
 * Cihaz-token (X-API-Key) katmanı AYRI ve DEĞİŞMEDİ.
 *
 * ⚠️ Supabase panosunda YAPILMASI GEREKENLER (kodla yapılamaz):
 *   1) Authentication → Providers → Email AÇIK + "Confirm email" AÇIK
 *   2) Authentication → URL Configuration → Site URL + Redirect URLs = aşağıdaki AUTH_VERIFY_URL & AUTH_RESET_URL
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { createClient, Session } from "@supabase/supabase-js";

const SUPABASE_URL =
  process.env.EXPO_PUBLIC_SUPABASE_URL ?? "https://wmsxonunkphjeregpvuj.supabase.co";
const SUPABASE_KEY =
  process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? "sb_publishable_D2SaRML_PIhRtr3kqlXxaw_1cS75GKT";

// E-posta linklerinin döneceği GitHub Pages sayfaları. Supabase "Redirect URLs" + "Site URL"
// ile BİREBİR eşleşmeli. Farklı repo/kullanıcı kullanırsan burayı değiştir.
export const AUTH_VERIFY_URL = "https://mert61-python.github.io/pemf-update/auth/verified.html";
export const AUTH_RESET_URL = "https://mert61-python.github.io/pemf-update/auth/reset.html";

// ── Güvenli oturum saklama (SecureStore) ─────────────────────────────────────────────────────
// GÜVENLİK: Supabase oturumu (access + UZUN-ÖMÜRLÜ refresh_token + operatör PII) eskiden
// AsyncStorage'da DÜZ-METİNDİ → rootlu/yedekli cihazda refresh_token okunup hesap süresiz
// devralınabiliyordu (KVKK: telefon/adres de düz-metin). Native'de iOS Keychain / Android Keystore
// (SecureStore). SecureStore anahtar başına ~2KB sınırlı; oturum bunu aşabildiğinden PARÇALARIZ.
// Web'de SecureStore yok → AsyncStorage (tarayıcı-yerel) fallback; X-API-Key ile aynı desen.
const _SEC_CHUNK = 1800;
const _SEC_MARK = "__chunks__:";

async function _secClearChunks(key: string): Promise<void> {
  try {
    const meta = await SecureStore.getItemAsync(key);
    if (meta && meta.startsWith(_SEC_MARK)) {
      const n = parseInt(meta.slice(_SEC_MARK.length), 10) || 0;
      for (let i = 0; i < n; i++) {
        try { await SecureStore.deleteItemAsync(`${key}.${i}`); } catch { /* ignore */ }
      }
    }
  } catch { /* ignore */ }
}

async function _secSet(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") { await AsyncStorage.setItem(key, value); return; }
  await _secClearChunks(key);
  if (value.length <= _SEC_CHUNK) { await SecureStore.setItemAsync(key, value); return; }
  const n = Math.ceil(value.length / _SEC_CHUNK);
  for (let i = 0; i < n; i++) {
    await SecureStore.setItemAsync(`${key}.${i}`, value.slice(i * _SEC_CHUNK, (i + 1) * _SEC_CHUNK));
  }
  await SecureStore.setItemAsync(key, `${_SEC_MARK}${n}`);
}

async function _secGet(key: string): Promise<string | null> {
  if (Platform.OS === "web") return AsyncStorage.getItem(key);
  try {
    const meta = await SecureStore.getItemAsync(key);
    if (meta == null) {
      // MİGRASYON: eski kurulumda oturum AsyncStorage'da DÜZ-METİNDİ → SecureStore'a taşı, düz-metini sil.
      const legacy = await AsyncStorage.getItem(key);
      if (legacy != null) {
        try { await _secSet(key, legacy); await AsyncStorage.removeItem(key); } catch { /* ignore */ }
        return legacy;
      }
      return null;
    }
    if (!meta.startsWith(_SEC_MARK)) return meta;
    const n = parseInt(meta.slice(_SEC_MARK.length), 10) || 0;
    let out = "";
    for (let i = 0; i < n; i++) {
      const part = await SecureStore.getItemAsync(`${key}.${i}`);
      if (part == null) return null; // eksik parça → bozuk oturum, yeniden giriş iste
      out += part;
    }
    return out;
  } catch {
    return null;
  }
}

async function _secRemove(key: string): Promise<void> {
  if (Platform.OS === "web") { await AsyncStorage.removeItem(key); return; }
  await _secClearChunks(key);
  try { await SecureStore.deleteItemAsync(key); } catch { /* ignore */ }
}

const supabaseSecureStorage = { getItem: _secGet, setItem: _secSet, removeItem: _secRemove };

export const supabaseAuth = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: {
    storage: supabaseSecureStorage as unknown as any, // native=SecureStore(parçalı), web=AsyncStorage
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false, // native: URL-token ayrıştırma yok
  },
});

export interface AuthResult {
  ok: boolean;
  error?: string;
  needsVerification?: boolean; // kayıt sonrası doğrulama e-postası bekleniyor / giriş öncesi doğrula
}

/** Supabase hata mesajını kullanıcı-dostu Türkçe'ye çevir. */
function mapError(msg: string): string {
  const m = (msg || "").toLowerCase();
  if (m.includes("already registered") || m.includes("already been registered") || m.includes("user already"))
    return "Bu e-posta ile zaten bir hesap var. Giriş yapın.";
  if (m.includes("invalid login") || m.includes("invalid credentials"))
    return "E-posta veya şifre hatalı.";
  if (m.includes("email not confirmed") || m.includes("not confirmed"))
    return "Önce e-postanı doğrula (gelen kutunu kontrol et).";
  if (m.includes("rate") || m.includes("too many") || m.includes("29 seconds") || m.includes("security purposes"))
    return "Çok fazla deneme. Biraz bekleyip tekrar dene.";
  if (m.includes("network") || m.includes("fetch") || m.includes("failed to"))
    return "Sunucuya ulaşılamadı. İnternet bağlantını kontrol et.";
  if (m.includes("password") && m.includes("6"))
    return "Şifre en az 6 karakter olmalı.";
  if (m.includes("504") || m.includes("503") || m.includes("502") || m.includes("timeout") || m.includes("timed out") || m.includes("gateway") || /"status":\s*5\d\d/.test(m))
    return "Sunucu şu an yanıt vermiyor. Birkaç dakika sonra tekrar dene.";
  return msg || "İşlem başarısız.";
}

/** Yeni hesap — Supabase doğrulama e-postası gönderir. Confirm-email açıkken session NULL döner → doğrula. */
export async function signUpUser(
  email: string,
  password: string,
  meta?: Record<string, string>,
): Promise<AuthResult> {
  try {
    const { data, error } = await supabaseAuth.auth.signUp({
      email: (email || "").trim(),
      password,
      // options.data → Supabase user_metadata (veteriner/klinik profili; hesapla birlikte taşınır).
      options: { emailRedirectTo: AUTH_VERIFY_URL, data: meta || {} },
    });
    if (error) return { ok: false, error: mapError(error.message) };
    // Confirm-email AÇIK → user oluşur, session yok → doğrulama gerekli.
    if (!data.session) return { ok: true, needsVerification: true };
    return { ok: true }; // (confirm-email kapalıysa doğrudan giriş — onAuthStateChange yakalar)
  } catch (e: any) {
    return { ok: false, error: mapError(String(e?.message || e)) };
  }
}

/** Giriş. E-posta doğrulanmamışsa net mesaj + needsVerification. Başarıda oturumu supabase-js kurar (onAuthStateChange). */
export async function signInUser(email: string, password: string): Promise<AuthResult> {
  try {
    const { error } = await supabaseAuth.auth.signInWithPassword({
      email: (email || "").trim(),
      password,
    });
    if (error) {
      const needsVerify = /not confirmed|confirm your email/i.test(error.message);
      return { ok: false, error: mapError(error.message), needsVerification: needsVerify };
    }
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: mapError(String(e?.message || e)) };
  }
}

/** Şifre-sıfırlama e-postası gönder (link → AUTH_RESET_URL 'yeni şifre belirle' sayfası). */
export async function sendPasswordReset(email: string): Promise<AuthResult> {
  try {
    const { error } = await supabaseAuth.auth.resetPasswordForEmail((email || "").trim(), {
      redirectTo: AUTH_RESET_URL,
    });
    if (error) return { ok: false, error: mapError(error.message) };
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: mapError(String(e?.message || e)) };
  }
}

/** Doğrulama e-postasını yeniden gönder (kullanıcı ilkini bulamazsa). */
export async function resendVerification(email: string): Promise<AuthResult> {
  try {
    const { error } = await supabaseAuth.auth.resend({
      type: "signup",
      email: (email || "").trim(),
      options: { emailRedirectTo: AUTH_VERIFY_URL },
    });
    if (error) return { ok: false, error: mapError(error.message) };
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: mapError(String(e?.message || e)) };
  }
}

export async function signOutUser(): Promise<void> {
  try {
    await supabaseAuth.auth.signOut();
  } catch {
    /* yok say — yerelde de temizlenecek */
  }
}

/** Veteriner/klinik profilini güncelle (Supabase user_metadata). Başarıda onAuthStateChange (USER_UPDATED)
 * session.profile'ı otomatik tazeler. E-posta/şifre DEĞİŞMEZ; yalnız profil alanları. */
export async function updateProfile(meta: Record<string, string>): Promise<AuthResult> {
  try {
    const { error } = await supabaseAuth.auth.updateUser({ data: meta });
    if (error) return { ok: false, error: mapError(error.message) };
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: mapError(String(e?.message || e)) };
  }
}

export async function getCurrentSession(): Promise<Session | null> {
  try {
    const { data } = await supabaseAuth.auth.getSession();
    return data.session ?? null;
  } catch {
    return null;
  }
}
