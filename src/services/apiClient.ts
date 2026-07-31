import { serviceConfig } from "@/services/config";
import { Alert, Platform } from "react-native";
import { emitToast } from "@/services/toastBridge";

/** Web-güvenli uyarı — Alert.alert web'de no-op olduğundan window.alert'e düşer. */
export function platformAlert(title: string, message: string) {
  if (Platform.OS === "web") {
    if (typeof window !== "undefined") window.alert(`${title}\n${message}`);
  } else {
    Alert.alert(title, message);
  }
}

/** Web-güvenli onay diyaloğu — Alert.alert çoklu-buton web'de tetiklenmez (window.confirm'e düşer). */
export function platformConfirm(title: string, message: string, confirmLabel = "Onayla"): Promise<boolean> {
  if (Platform.OS === "web") {
    return Promise.resolve(typeof window !== "undefined" ? window.confirm(`${title}\n\n${message}`) : false);
  }
  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: "İptal", style: "cancel", onPress: () => resolve(false) },
      { text: confirmLabel, style: "destructive", onPress: () => resolve(true) },
    ]);
  });
}

function showError(title: string, message: string) {
  // F-6: önce non-blocking toast (medikal konsolda bloklayan window.alert kötü UX); ToastProvider
  // kayıtlı değilse (mount öncesi / native provider'sız) bloklayan alert'e fallback. platformConfirm
  // (yıkıcı-onay) DEĞİŞMEDİ — native dialog doğru.
  if (!emitToast(`${title}: ${message}`, "error")) platformAlert(title, message);
}

/** İstek opsiyonları — `silent: true` arka-plan poll'lerinde hata pop-up'ını bastırır. */
export interface ApiOpts {
  silent?: boolean;
}

// Entitlement (abonelik tier/eklenti) header'ları — EntitlementContext günceller; backend
// tier-enforcement (PEMF_TIER_ENFORCED) AÇIKKEN kullanılır. Kapalıyken backend yok sayar (zararsız).
let _entitlementHeaders: Record<string, string> = {};
export function setEntitlementHeaders(tier: string | null, addons: string[] = []): void {
  _entitlementHeaders = tier ? { "X-PEMF-Tier": tier, "X-PEMF-Addons": addons.join(",") } : {};
}

// Supabase erişim JWT'si — backend bunu Supabase'e iletip tier'ı DOĞRULAR (spoof-proof). Device
// auth X-API-Key kullandığından Authorization serbest. Bayatsa backend fail-open (tedavi bloklanmaz).
let _authBearer: string | null = null;
export function setAuthBearer(token: string | null): void {
  _authBearer = token || null;
}

/** Backend tabanı GÜVENLİ mi: https (tünel, TLS) VEYA RFC1918-LAN/localhost (yerel cihaz TLS'siz).
 * Keşfedilen/elle-girilen KEYFİ bir host'a (zehirli Supabase devices kaydı / sahte tünel) kurbanın
 * Supabase JWT'sini teslim etmemek için Authorization yalnız buraya eklenir. */
export function isSafeBackendBase(baseUrl: string): boolean {
  if (!baseUrl) return false;
  if (baseUrl.startsWith("https://")) return true; // tünel = TLS
  const m = baseUrl.match(/^http:\/\/([^/:]+)/i);
  if (!m) return false;
  const host = m[1].toLowerCase();
  // RFC1918 özel aralıklar + localhost (yerel klinik cihazı)
  return (
    host === "localhost" ||
    /^127\./.test(host) ||
    /^10\./.test(host) ||
    /^192\.168\./.test(host) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host)
  );
}

/** Backend auth (PEMF_REQUIRE_AUTH=1) açıksa X-API-Key + entitlement + Supabase-Bearer gönder. Token boşsa geriye uyumlu. */
export function authHeaders(): Record<string, string> {
  const bearerSafe = _authBearer && isSafeBackendBase(serviceConfig.apiBaseUrl);
  return {
    ...(serviceConfig.apiToken ? { "X-API-Key": serviceConfig.apiToken } : {}),
    ..._entitlementHeaders,
    // Supabase Bearer'ı YALNIZ güvenli tabana ekle: aksi halde poisoned/sahte host kurbanın
    // ~1sa RLS-kapsamlı JWT'sini ele geçirir (public-plaintext http'de de sızmasın).
    ...(bearerSafe ? { Authorization: `Bearer ${_authBearer}` } : {}),
  };
}

// Asılı bağlantı (yarı-açık tünel / backend restart / captive portal) UI'yi sonsuza dek
// DONDURMASIN diye HER isteğe zaman aşımı. (Audit P0: apiClient tek korumasız fetch yoluydu →
// pairing kodu render olmuyor / butonlar "Kaydediliyor…"de takılı kalıyordu.)
const REQUEST_TIMEOUT_MS = 8000;

// NOT: 401'de token ASLA SİLİNMEZ. Kullanıcı bir kez (LAN veya uzaktan) bağlandıysa token
// saklı kalır; bir daha uğraştırılmaz. Yanlış/eski token, telefon LAN'a girince keşifteki
// provisionToken (/api/auth/token) ile OTOMATİK ve koşulsuz tazelenir. Silmek gereksiz olduğu
// gibi tünelde "bağlı ama kalıcı 401" tuzağı yaratıyordu.

// ORTA fix: 2xx yanıt gövdesi BOŞ veya JSON-OLMAYAN (captive-portal HTML) olabilir. Ham `response.json()`
// "Unexpected end of JSON input" fırlatıp BAŞARILI isteği hata sayıyordu → POST'ta çift-submit / yanlış hata.
// Güvenli: boş gövde = başarı (boş sonuç `{}`); JSON-olmayan gövde = gerçek hata → fallback.
async function parseJsonSafe<T>(response: Response, fallback: T): Promise<T> {
  const text = await response.text();
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

export async function apiGet<T>(path: string, fallback: T, opts?: ApiOpts): Promise<T> {
  const url = `${serviceConfig.apiBaseUrl}${path}`;
  // audit B-10.3: GET İDEMPOTENT → geçici ağ hatasında (fetch throw/timeout) 1 kez daha dene
  // (400ms sonra). HTTP hatasında (sunucu yanıt verdi) TEKRAR DENENMEZ. POST asla denenmez.
  const MAX_ATTEMPTS = 2;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(url, { headers: authHeaders(), signal: ctrl.signal });
      if (!response.ok) {
        console.error(`API GET Hatası [${response.status}]: ${url}`);
        if (!opts?.silent) showError("Sunucu Hatası", "Sunucu ile iletişimde bir sorun oluştu.");
        return fallback;
      }
      return await parseJsonSafe(response, fallback);
    } catch (error) {
      if (attempt < MAX_ATTEMPTS) {
        await new Promise((r) => setTimeout(r, 400)); // kısa geri-çekilme, sonra bir kez daha
        continue;
      }
      console.error(`API GET İstek Başarısız (${MAX_ATTEMPTS} deneme): ${path}`, error);
      // Bağlantı kopması BLOKLAYAN uyarı GÖSTERMEZ — global çevrimdışı banner durumu bildirir.
      return fallback;
    } finally {
      clearTimeout(timer);
    }
  }
  return fallback;
}

export async function apiPost<T>(path: string, body: unknown, fallback: T, opts?: ApiOpts): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!response.ok) {
      console.error(`API POST Hatası [${response.status}]: ${url}`);
      if (!opts?.silent) showError("Sunucu Hatası", "Sunucuya veri gönderilirken bir hata oluştu.");
      return fallback;
    }
    return await parseJsonSafe(response, fallback);
  } catch (error) {
    console.error(`API POST İstek Başarısız: ${path}`, error);
    // Bağlantı kopması BLOKLAYAN uyarı GÖSTERMEZ — global çevrimdışı banner + sağ-üst "Çevrimdışı"
    // göstergesi zaten durumu bildirir; her tab-geçişi/mount fetch'inde pop-up spam'i olmasın.
    return fallback;
  } finally {
    clearTimeout(timer);
  }
}
