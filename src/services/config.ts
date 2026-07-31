import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

// Cihaz kimliği — ilk LAN bağlantısında /api/health'ten yakalanır, saklanır;
// sonra farklı ağda Supabase 'devices' tablosundan güncel tunnel_url'i bulmak için
// kullanılır (TEMASSIZ uzaktan erişim, QR'sız).
const DEVICE_ID_KEY = "@pemf_device_id";
// Oto-eşleştirme görünür onayı (#11): yeni/değişen device_id geldiğinde bu bayrak
// yazılır; AppShell mount'ta okuyup "Cihaz otomatik eşleştirildi" toast'ı gösterir.
const JUST_PAIRED_KEY = "@pemf_just_paired";
export async function setStoredDeviceId(id: string): Promise<void> {
  try {
    if (!id) return;
    // YENİ eşleşme: saklanan ESKİ id'den farklıysa (ilk kez veya değişince) bayrağı yaz.
    const prev = await AsyncStorage.getItem(DEVICE_ID_KEY);
    if (prev !== id) await AsyncStorage.setItem(JUST_PAIRED_KEY, id);
    await AsyncStorage.setItem(DEVICE_ID_KEY, id);
  } catch {
    /* ignore */
  }
}
export async function getStoredDeviceId(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(DEVICE_ID_KEY);
  } catch {
    return null;
  }
}

function getRuntimeBaseUrl(): string {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

function toWebSocketUrl(baseUrl: string): string {
  if (baseUrl.startsWith("https://")) {
    return baseUrl.replace(/^https:\/\//, "wss://") + "/ws";
  }
  return baseUrl.replace(/^http:\/\//, "ws://") + "/ws";
}

const runtimeBaseUrl = getRuntimeBaseUrl();

export let serviceConfig = {
  // REST API — FastAPI server (port 8000) — Tek port mimarisi
  apiBaseUrl: process.env.EXPO_PUBLIC_PEMF_API_BASE_URL ?? `${runtimeBaseUrl}/api`,
  // WebSocket — Artık FastAPI port 8000 üzerinden (5050 devre dışı)
  websocketUrl: process.env.EXPO_PUBLIC_PEMF_WS_URL ?? toWebSocketUrl(runtimeBaseUrl),
  // HTTP snapshot fallback
  bridgeBaseUrl: process.env.EXPO_PUBLIC_PEMF_BRIDGE_URL ?? `${runtimeBaseUrl}/api`,
  // Cihaz API token'ı — backend PEMF_REQUIRE_AUTH=1 iken zorunlu. Boşsa gönderilmez (auth kapalı = değişiklik yok).
  apiToken: process.env.EXPO_PUBLIC_PEMF_API_TOKEN ?? "",
};

const API_TOKEN_KEY = "@pemf_api_token";        // eski AsyncStorage anahtarı (web + migrasyon kaynağı)
const API_TOKEN_SECURE_KEY = "pemf_api_token";  // SecureStore anahtarı ('@' yasak)

// audit B-10.2: API token native'de SecureStore (iOS Keychain / Android Keystore) — eskiden
// AsyncStorage'da DÜZ-METİNDİ. Web'de SecureStore yok → AsyncStorage (tarayıcı-yerel, geriye uyumlu).
async function _secureSetToken(token: string): Promise<void> {
  if (Platform.OS === "web") {
    if (token) await AsyncStorage.setItem(API_TOKEN_KEY, token);
    else await AsyncStorage.removeItem(API_TOKEN_KEY);
    return;
  }
  if (token) await SecureStore.setItemAsync(API_TOKEN_SECURE_KEY, token);
  else await SecureStore.deleteItemAsync(API_TOKEN_SECURE_KEY);
}
async function _secureGetToken(): Promise<string | null> {
  if (Platform.OS === "web") return AsyncStorage.getItem(API_TOKEN_KEY);
  const s = await SecureStore.getItemAsync(API_TOKEN_SECURE_KEY);
  if (s) return s;
  // MİGRASYON: eski kurulumlarda token AsyncStorage'daydı → SecureStore'a taşı, düz-metini sil.
  const legacy = await AsyncStorage.getItem(API_TOKEN_KEY);
  if (legacy) {
    try {
      await SecureStore.setItemAsync(API_TOKEN_SECURE_KEY, legacy);
      await AsyncStorage.removeItem(API_TOKEN_KEY);
    } catch {
      /* ignore */
    }
    return legacy;
  }
  return null;
}

export async function setStoredApiToken(token: string): Promise<void> {
  try {
    serviceConfig.apiToken = token || "";
    await _secureSetToken(token || "");
  } catch {
    /* ignore */
  }
}
export async function loadStoredApiToken(): Promise<void> {
  try {
    const t = await _secureGetToken();
    if (t) serviceConfig.apiToken = t;
  } catch {
    /* ignore */
  }
}

/**
 * Yerel IP veya Cloudflare tünel URL'si ile tüm ayarları günceller.
 * Tünel URL'si http/https veya doğrudan IP olabilir.
 * Örn: "192.168.1.147" veya "https://abcd-xyz.trycloudflare.com"
 */
export const updateServiceConfig = (serverAddress: string): boolean => {
  let apiBase: string;
  let wsBase: string;

  // #63: trim + temel doğrulama — kullanıcı-girdisi adres trim'siz/doğrulamasız base-URL'e
  // çevriliyordu. Boş/geçersiz ise ayarı DEĞİŞTİRME + false dön (çağıran kullanıcıya hata gösterir).
  const addr = (serverAddress || "").trim();
  if (!addr) return false;

  // Cloudflare/ngrok tünelleri genelde https ile başlar. Local IP'ler http veya düz IP olabilir.
  // Eğer düz IP veya hostname verilmişse (örn: 192.168.1.147), varsayılan olarak http ve 8000 portunu ekle.
  let baseUrl = addr;
  if (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://")) {
    baseUrl = `http://${baseUrl}:8000`;
  }

  // Sondaki '/' işaretini kaldır (varsa)
  baseUrl = baseUrl.replace(/\/$/, "");

  // TÜM authority (host[:port]) geçerli karakterlerden oluşmalı — PATH/slash İÇERMESİN (aksi halde
  // "192.168.1.1/evil" → "http://192.168.1.1/evil:8000" bozuk base URL üretilirdi). Boşluk/kontrol/
  // kaçış da yasak. Hassas Bearer ayrıca apiClient.isSafeBackendBase ile https/RFC1918-taban'a geçitli.
  const _authority = baseUrl.replace(/^https?:\/\//, "");
  if (!_authority || !/^[A-Za-z0-9._:-]+$/.test(_authority)) return false;

  // URL'i oluştur
  apiBase = `${baseUrl}/api`;

  // WebSocket URL'ini http(s) protokolüne göre dinamik oluştur
  if (baseUrl.startsWith("https://")) {
    wsBase = baseUrl.replace(/^https:\/\//, "wss://") + "/ws";
  } else {
    wsBase = baseUrl.replace(/^http:\/\//, "ws://") + "/ws";
  }

  serviceConfig = {
    apiBaseUrl: apiBase,
    websocketUrl: wsBase,
    bridgeBaseUrl: apiBase,
    apiToken: serviceConfig.apiToken || "",
  };
  return true;
};
