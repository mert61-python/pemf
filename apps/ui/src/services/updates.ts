// Author: mertaygn, cglrgrkn
/**
 * Uzaktan güncelleme kontrolü — GitHub 'pemf-update' repo'su (branch başına manifest).
 * =================================================================================
 * • MOBİL (APK): mobil branch latest.json → yeni sürüm varsa APK indirme linki açılır (sideload).
 *
 * ⚠️ EXE / cihaz yazılımı KALDIRILDI (2026-08-09 denetimi, Tier 3 — "tek güncelleme kanalı").
 * Cihaz yazılımını artık PEMF Vet Client (launcher) günceller: katmanlı paket, atomik takas,
 * sağlık kapılı geri alma. Buradaki eski yol backend'in `/api/update/apply` ucunu çağırıyordu;
 * o uç bir Inno installer'ı çalıştırıp launcher'ın yönettiği kurulumun YANINA ikinci bir backend
 * + ikinci veri kökü kurardı → SPLIT-BRAIN HASTA VERİTABANI. Uç zaten kapalı; düğmeyi de
 * bırakmak "dokun ve güncelle" diyen ama hata veren bir buton demekti.
 */
import { Platform } from "react-native";

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

// ── MOBİL / APK ─────────────────────────────────────────────────────────────
export interface MobileUpdate {
  available: boolean;
  latestVersion?: string;
  apkUrl?: string;
  notes?: string;
  /** Yayınlanan APK SHA256 (manifest'ten). NOT: tam in-app kriptografik doğrulama + release-imza
   *  (debug-keystore yerine özel keystore) BUILD/RELEASE-ALTYAPISI işidir (owner); burada değer
   *  yüzeye çıkarılır ki güncelleme banner'ı operatöre gösterip bilinçli onay isteyebilsin. */
  sha256?: string;
}
// GÜVENLİK (DÜŞÜK — backend K2 simetrisi): apkUrl'yi HTTPS + bilinen GitHub-release host'una pinle.
// apkUrl sonra Linking.openURL ile açılıyor → manifest ele geçse bile sideload'ı keyfi/zararlı APK'ya
// yönlendirme engellenir. Geçersiz/beklenmeyen host → undefined (banner "İndir" göstermez).
function _safeApkUrl(url: unknown): string | undefined {
  if (typeof url !== "string" || !url) return undefined;
  if (/^https:\/\/(github\.com|[a-z0-9.-]*\.githubusercontent\.com)\//i.test(url)) return url;
  return undefined;
}

export async function checkMobileUpdate(): Promise<MobileUpdate> {
  // #89: APK güncellemesi YALNIZ Android'de anlamlı. iOS'ta APK sideload edilemez → yanıltıcı/
  // karşılanamayan banner gösterme; web'de de anlamsız.
  if (Platform.OS !== "android") return { available: false };
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 8000);
    const res = await fetch(MOBILE_MANIFEST + "?t=" + Date.now(), { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return { available: false };
    const m = await res.json();
    const latest = String(m?.version || "");
    const apkUrl = _safeApkUrl(m?.apkUrl);
    const sha256 = typeof m?.sha256 === "string" && /^[a-f0-9]{64}$/i.test(m.sha256) ? m.sha256 : undefined;
    return {
      available: !!latest && !!apkUrl && isNewer(latest, APP_VERSION),
      latestVersion: latest,
      apkUrl,
      notes: m?.notes,
      sha256,
    };
  } catch {
    return { available: false };
  }
}
