// Author: mertaygn, cglrgrkn
/**
 * supabaseAuth — operatör hesabı SUPABASE AUTH ile (e-posta/şifre). Yerel auth_db devralındı.
 *
 * ⚠️ E-POSTA DOĞRULAMA KALDIRILDI (2026-08-06, sahip kararı).
 *   Supabase projesinde `mailer_autoconfirm = true` → kayıt ANINDA oturum açılır, doğrulama
 *   e-postası HİÇ gönderilmez. Uygulama tarafındaki doğrulama akışı (bekleme ekranı, "tekrar
 *   gönder" düğmesi, "önce e-postanı doğrula" mesajları) bu yüzden SÖKÜLDÜ: var olmayan bir
 *   e-postayı bekleten arayüz, operatörü giremediği bir hesapta kilitli sanmasına yol açıyordu.
 *   Supabase yalnız KAYIT + GİRİŞ için kullanılır.
 *   → Doğrulamayı geri istersen: Supabase panosunda "Confirm email" AÇ, sonra bu akışı geri ekle.
 *      Yalnız birini yapmak (panoda açıp uygulamada kapalı bırakmak) hesapları kilitler.
 *
 * Oturum supabase-js ile KALICI ve GÜVENLİ: native'de SecureStore (Keychain/Keystore, parçalı),
 * web'de AsyncStorage. Cihaz-token (X-API-Key) katmanı AYRI ve DEĞİŞMEDİ.
 *
 * Şifre SIFIRLAMA duruyor (doğrulamadan bağımsız bir özellik) — AUTH_RESET_URL üzerinden.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { createClient, Session } from "@supabase/supabase-js";

const SUPABASE_URL =
  process.env.EXPO_PUBLIC_SUPABASE_URL ?? "https://wmsxonunkphjeregpvuj.supabase.co";
const SUPABASE_KEY =
  process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? "sb_publishable_D2SaRML_PIhRtr3kqlXxaw_1cS75GKT";

// Şifre-sıfırlama linkinin döneceği GitHub Pages sayfası. Supabase "Redirect URLs" + "Site URL"
// ile BİREBİR eşleşmeli. Farklı repo/kullanıcı kullanırsan burayı değiştir.
// (AUTH_VERIFY_URL kaldırıldı — e-posta doğrulama akışı yok; bkz. dosya başı.)
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

/// Tek yeniden denemeli SecureStore yazımı.
///
/// ⚠️ DENETİM 2026-08-17: `_secSet` parçalı yolda ÖNCE eski parçaları siliyor, sonra yeni parçaları
/// yazıyor, meta'yı EN SON güncelliyor ve hiç `try/catch` içermiyordu (kardeşleri `_secGet`/
/// `_secRemove`'da var). GEÇİCİ bir Keystore/Keychain hatası (cihaz kilitli, keystore meşgul) ya da
/// birkaç ms'lik pencerede OS'un süreci öldürmesi hâlinde meta artık VAR OLMAYAN parçalara işaret
/// ediyordu → `_secGet` kalıcı `null` → veteriner bir sonraki açılışta e-posta+şifre ile TEKRAR
/// GİRİŞ yapmak zorunda kalıyordu. Ölçüldü: gerçekçi bir GoTrue oturumu 2735 karakter (profilsiz
/// bile 2074) → parçalı yol İSTİSNA DEĞİL, NORMAL yoldur; 1800 sınırının altına hiç inmiyor.
/// `@supabase/auth-js`in `_saveSession`ı `setItemAsync` etrafında try/catch içermiyor (kaynak
/// okundu) ve alternatif bir token kaynağı yok — yani telafi eden bir katman da yok.
///
/// ⚠️ YAZIM SIRASI BİLEREK DEĞİŞTİRİLMEDİ. "Önce yeni parçaları yaz, sonra meta, en son eski
/// artıkları sil" tutarlı ama BAYAT bir oturum bırakır; GoTrue o bayat/iptal edilmiş
/// `refresh_token` ile tazeleme deneyip 400 alır → `_removeSession` → `SIGNED_OUT` → tedavi
/// ORTASINDA AppShell (ve üzerindeki ACİL DURDUR) ekrandan kalkar. Bir yeniden giriş, tedavi
/// ortasında oturum düşmesinden iyidir. Bu yüzden düzeltme "sırayı çevirmek" değil, yazımı
/// GEÇİCİ hataya DAYANIKLI yapmaktır. İkinci deneme de patlarsa hata çağırana AYNEN gider
/// (bugünkü davranış korunur — sessizce bozuk durum bırakılmaz).
async function _secWrite(key: string, value: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(key, value);
  } catch {
    await new Promise((r) => setTimeout(r, 150));
    await SecureStore.setItemAsync(key, value);
  }
}

async function _secSet(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") { await AsyncStorage.setItem(key, value); return; }
  await _secClearChunks(key);
  if (value.length <= _SEC_CHUNK) { await _secWrite(key, value); return; }
  const n = Math.ceil(value.length / _SEC_CHUNK);
  for (let i = 0; i < n; i++) {
    await _secWrite(`${key}.${i}`, value.slice(i * _SEC_CHUNK, (i + 1) * _SEC_CHUNK));
  }
  await _secWrite(key, `${_SEC_MARK}${n}`);
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
}

/** Supabase hata mesajını kullanıcı-dostu Türkçe'ye çevir. */
function mapError(msg: string): string {
  const m = (msg || "").toLowerCase();
  // HESAP SAYIMI (enumeration): "Bu e-posta ile zaten bir hesap var" cevabı, kayıt formuna
  // e-posta girerek o adresin sistemde KAYITLI olup olmadığını kesin öğrenmeye yarıyordu —
  // klinik/veteriner hesaplarının hedeflenmesini kolaylaştırır. Supabase'in giriş tarafı bunu
  // zaten sızdırmıyor (doğrulanmamış hesaba da jenerik hata döner); kayıt tarafını da hizala.
  // Kullanıcı yönü kaybolmasın diye "giriş yapmayı deneyin" yönlendirmesi KORUNUR.
  if (m.includes("already registered") || m.includes("already been registered") || m.includes("user already"))
    return "Kayıt tamamlanamadı. Bu adresi zaten kullanıyorsanız giriş yapmayı ya da şifrenizi sıfırlamayı deneyin.";
  // Doğrulama akışı kaldırıldığı için mesaj artık SADE: hesap doğrulanmamış olamaz
  // (Supabase autoconfirm açık). Kullanıcıyı olmayan bir e-postayı beklemeye yönlendirme.
  // Boşluk ipucu bilinçli: şifrenin sonundaki görünmez boşluk gerçek bir giriş hatası sebebiydi.
  if (m.includes("invalid login") || m.includes("invalid credentials"))
    return "E-posta veya şifre hatalı. Şifrede istemsiz boşluk olabilir; büyük/küçük harfe de dikkat edin.";
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

/** Yeni hesap. Supabase autoconfirm AÇIK → oturum ANINDA kurulur; doğrulama e-postası YOK.
 *  `emailRedirectTo` de kaldırıldı (gönderilecek bir e-posta olmadığı için işlevsizdi). */
export async function signUpUser(
  email: string,
  password: string,
  meta?: Record<string, string>,
): Promise<AuthResult> {
  try {
    const { data, error } = await supabaseAuth.auth.signUp({
      email: (email || "").trim(),
      // Kayıt ve giriş AYNI kuralı uygulamalı; aksi halde boşlukla kaydolan hesap
      // boşluksuz giremez (ya da tersi) → kalıcı kilitlenme.
      password: trimPw(password),
      // options.data → Supabase user_metadata (veteriner/klinik profili; hesapla birlikte taşınır).
      options: { data: meta || {} },
    });
    if (error) return { ok: false, error: mapError(error.message) };
    // Oturum normalde HEMEN gelir (autoconfirm). Gelmediyse panoda "Confirm email" tekrar
    // AÇILMIŞ demektir — bu durumda kullanıcı giremez ve sebebini bilemez; açıkça söyle.
    if (!data.session) {
      return {
        ok: false,
        error: "Hesap oluşturuldu ama oturum açılamadı. Sunucuda e-posta onayı açık olabilir — yöneticinize bildirin.",
      };
    }
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: mapError(String(e?.message || e)) };
  }
}

/** Şifrenin BAŞINDAKİ/SONUNDAKİ boşluğu at (iç boşluk korunur — gerçek parola karakteri olabilir).
 *  E-posta zaten trim ediliyordu ama ŞİFRE edilmiyordu: mobil klavye/pano/şifre yöneticisi sona
 *  boşluk eklediğinde Supabase bunu farklı bir şifre sayıp reddediyor, kullanıcı ise ekranda
 *  hiçbir fark göremediği için "E-posta veya şifre hatalı" mesajını çözemiyordu. */
const trimPw = (p: string): string => (p || "").replace(/^\s+|\s+$/g, "");

/** Giriş. Başarıda oturumu supabase-js kurar (onAuthStateChange yakalar). */
export async function signInUser(email: string, password: string): Promise<AuthResult> {
  try {
    const { error } = await supabaseAuth.auth.signInWithPassword({
      email: (email || "").trim(),
      password: trimPw(password),
    });
    if (error) return { ok: false, error: mapError(error.message) };
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

// `resendVerification` KALDIRILDI (2026-08-06): Supabase autoconfirm açıkken `auth.resend({type:
// "signup"})` gönderecek bir doğrulama e-postası bulamaz; düğme kullanıcıya "gönderildi" deyip
// hiçbir şey yapmıyordu. Doğrulama geri açılırsa bu fonksiyon da geri gelmeli.

export async function signOutUser(): Promise<void> {
  try {
    // ⚠️ KAPSAM 'local' (denetim 2026-08-18): supabase-js v2'de `signOut()` varsayılanı
    // `scope: 'global'`dir → `POST /auth/v1/logout?scope=global` kullanıcının TÜM refresh
    // token'larını sunucuda iptal eder. Üç istemci de AYNI Supabase projesini kullanıyor
    // (mobil burası, web `pemf-vet-web`, masaüstü `launcher/core/src/auth.rs`), dolayısıyla
    // telefondan çıkmak KLİNİKTEKİ launcher'ın oturumunu da düşürüyordu: launcher bir sonraki
    // jeton tazelemesinde `invalid_grant` alıp açılış kapısında e-posta+parola istiyor.
    // Yerel çıkış yeterli — jeton zaten bu cihazın SecureStore'undan siliniyor.
    await supabaseAuth.auth.signOut({ scope: "local" });
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
