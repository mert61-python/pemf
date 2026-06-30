import { serviceConfig, setStoredApiToken } from "@/services/config";
import { Alert, Platform } from "react-native";

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
  platformAlert(title, message);
}

/** İstek opsiyonları — `silent: true` arka-plan poll'lerinde hata pop-up'ını bastırır. */
export interface ApiOpts {
  silent?: boolean;
}

/** Backend auth (PEMF_REQUIRE_AUTH=1) açıksa X-API-Key gönder. Token boşsa boş → geriye uyumlu. */
export function authHeaders(): Record<string, string> {
  return serviceConfig.apiToken ? { "X-API-Key": serviceConfig.apiToken } : {};
}

// Asılı bağlantı (yarı-açık tünel / backend restart / captive portal) UI'yi sonsuza dek
// DONDURMASIN diye HER isteğe zaman aşımı. (Audit P0: apiClient tek korumasız fetch yoluydu →
// pairing kodu render olmuyor / butonlar "Kaydediliyor…"de takılı kalıyordu.)
const REQUEST_TIMEOUT_MS = 8000;

/** 401 = token eksik/geçersiz. Eskimiş token'ı temizle → sonraki LAN keşfinde yeniden sağlanır
 *  (backend reinstall sonrası eski token'la kalıcı uzak-401 döngüsünü kırar). */
function onUnauthorized(): void {
  if (serviceConfig.apiToken) setStoredApiToken("").catch(() => {});
}

export async function apiGet<T>(path: string, fallback: T, opts?: ApiOpts): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url, { headers: authHeaders(), signal: ctrl.signal });
    if (!response.ok) {
      if (response.status === 401) onUnauthorized();
      console.error(`API GET Hatası [${response.status}]: ${url}`);
      if (!opts?.silent) showError("Sunucu Hatası", "Sunucu ile iletişimde bir sorun oluştu.");
      return fallback;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`API GET İstek Başarısız: ${path}`, error);
    if (!opts?.silent) showError("Bağlantı Koptu", "İnternet bağlantınız koptu veya sunucuya ulaşılamıyor.");
    return fallback;
  } finally {
    clearTimeout(timer);
  }
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
      if (response.status === 401) onUnauthorized();
      console.error(`API POST Hatası [${response.status}]: ${url}`);
      if (!opts?.silent) showError("Sunucu Hatası", "Sunucuya veri gönderilirken bir hata oluştu.");
      return fallback;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`API POST İstek Başarısız: ${path}`, error);
    if (!opts?.silent) showError("Bağlantı Koptu", "İnternet bağlantınız koptu veya sunucuya ulaşılamıyor.");
    return fallback;
  } finally {
    clearTimeout(timer);
  }
}
