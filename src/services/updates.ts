/**
 * Uzaktan güncelleme kontrolü — GitHub 'pemf-update' repo'su (branch başına manifest).
 * =================================================================================
 * • EXE (backend/cihaz yazılımı): bağlı backend'in /api/update/status'ü → yeni sürüm varsa
 *   operatör /api/update/apply ile ONAYLAR (backend kendini günceller). Bildirim + tek-tık.
 * • MOBİL (APK): mobil branch latest.json → yeni sürüm varsa APK indirme linki açılır (sideload).
 */
import { Platform } from "react-native";
import { apiGet, apiPost } from "@/services/apiClient";

const MOBILE_MANIFEST = "https://raw.githubusercontent.com/mert61-python/pemf-update/mobil/latest.json";

// Uygulamanın kendi sürümü (app.json version) — expo-constants'tan; yoksa güvenli fallback.
let APP_VERSION = "0.0.0";
try {
  // @ts-ignore - expo-constants opsiyonel
  APP_VERSION = require("expo-constants").default?.expoConfig?.version || "0.0.0";
} catch {
  /* ignore */
}

function vtuple(v: string): number[] {
  try {
    return String(v).replace(/^v/i, "").split(".").slice(0, 3).map((n) => parseInt(n, 10) || 0);
  } catch {
    return [0, 0, 0];
  }
}
function isNewer(latest: string, current: string): boolean {
  const A = vtuple(latest), B = vtuple(current);
  for (let i = 0; i < 3; i++) {
    if ((A[i] || 0) > (B[i] || 0)) return true;
    if ((A[i] || 0) < (B[i] || 0)) return false;
  }
  return false;
}

// ── EXE / backend (cihaz yazılımı) ──────────────────────────────────────────
export interface BackendUpdate {
  available: boolean;
  currentVersion?: string;
  latestVersion?: string;
  notes?: string;
  applying?: boolean;
}
export async function checkBackendUpdate(): Promise<BackendUpdate> {
  const s = await apiGet<any>("/update/status", { available: false }, { silent: true });
  return {
    available: !!s?.available,
    currentVersion: s?.currentVersion,
    latestVersion: s?.latestVersion,
    notes: s?.notes,
    applying: !!s?.applying,
  };
}
export async function applyBackendUpdate(): Promise<{ ok: boolean; message?: string; error?: string }> {
  return apiPost<{ ok: boolean; message?: string; error?: string }>(
    "/update/apply", {}, { ok: false, error: "İstek başarısız" }, { silent: true }
  );
}

// ── MOBİL / APK ─────────────────────────────────────────────────────────────
export interface MobileUpdate {
  available: boolean;
  latestVersion?: string;
  apkUrl?: string;
  notes?: string;
}
export async function checkMobileUpdate(): Promise<MobileUpdate> {
  if (Platform.OS === "web") return { available: false }; // web'de APK güncellemesi anlamsız
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 8000);
    const res = await fetch(MOBILE_MANIFEST + "?t=" + Date.now(), { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return { available: false };
    const m = await res.json();
    const latest = String(m?.version || "");
    return {
      available: !!latest && isNewer(latest, APP_VERSION),
      latestVersion: latest,
      apkUrl: m?.apkUrl,
      notes: m?.notes,
    };
  } catch {
    return { available: false };
  }
}

export function getAppVersion(): string {
  return APP_VERSION;
}
