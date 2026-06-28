import { serviceConfig } from "@/services/config";
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
function authHeaders(): Record<string, string> {
  return serviceConfig.apiToken ? { "X-API-Key": serviceConfig.apiToken } : {};
}

export async function apiGet<T>(path: string, fallback: T, opts?: ApiOpts): Promise<T> {
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url, { headers: authHeaders() });
    if (!response.ok) {
      console.error(`API GET Hatası [${response.status}]: ${url}`);
      if (!opts?.silent) showError("Sunucu Hatası", "Sunucu ile iletişimde bir sorun oluştu.");
      return fallback;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`API GET İstek Başarısız: ${path}`, error);
    if (!opts?.silent) showError("Bağlantı Koptu", "İnternet bağlantınız koptu veya sunucuya ulaşılamıyor.");
    return fallback;
  }
}

export async function apiPost<T>(path: string, body: unknown, fallback: T, opts?: ApiOpts): Promise<T> {
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(body)
    });
    if (!response.ok) {
      console.error(`API POST Hatası [${response.status}]: ${url}`);
      if (!opts?.silent) showError("Sunucu Hatası", "Sunucuya veri gönderilirken bir hata oluştu.");
      return fallback;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`API POST İstek Başarısız: ${path}`, error);
    if (!opts?.silent) showError("Bağlantı Koptu", "İnternet bağlantınız koptu veya sunucuya ulaşılamıyor.");
    return fallback;
  }
}
