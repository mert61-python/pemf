/**
 * PEMF bağlantı KEŞİF MERDİVENİ — temassız, sıfır-konfig.
 * =======================================================
 * Sıra:
 *   1. Kayıtlı adres (AsyncStorage)
 *   2. mDNS / Bonjour  (_pemfvet._tcp:8000) — AYNI WiFi'de oto-bağlan
 *   3. Subnet tarama   (mDNS yoksa fallback)
 *   4. Supabase remote (device_id ile güncel tunnel_url) — FARKLI WiFi, QR YOK
 *
 * /api/health'ten dönen deviceId saklanır → sonraki uzaktan bağlantı için eşleşme.
 * Web'de (backend'den serve edilir) origin zaten doğrudur; hızlı geçilir.
 */
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { updateServiceConfig, serviceConfig, setStoredDeviceId, getStoredDeviceId } from "@/services/config";
import { getRemoteUrlForDevice } from "@/services/deviceRegistry";

const ADDR_KEY = "@pemf_server_address";
const HEALTH_TIMEOUT_MS = 2500;
const MDNS_TIMEOUT_MS = 4000;

export type DiscoverySource = "current" | "saved" | "mdns" | "subnet" | "remote" | "none";
export interface DiscoveryResult {
  address: string;
  source: DiscoverySource;
}

function toBase(addr: string): string {
  return addr.startsWith("http") ? addr.replace(/\/$/, "") : `http://${addr}:8000`;
}

/** /api/health doğrular; başarılıysa deviceId'yi saklar (uzaktan eşleşme için). */
export async function checkHealth(addr: string): Promise<boolean> {
  try {
    const base = toBase(addr);
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), HEALTH_TIMEOUT_MS);
    const res = await fetch(`${base}/api/health`, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return false;
    const data = await res.json();
    const ok = data?.service === "PEMF-Vet" || data?.status === "online";
    if (ok && data?.deviceId) await setStoredDeviceId(String(data.deviceId)).catch(() => {});
    return ok;
  } catch {
    return false;
  }
}

async function apply(addr: string): Promise<void> {
  updateServiceConfig(addr);
  await AsyncStorage.setItem(ADDR_KEY, addr).catch(() => {});
}

// ── 2. mDNS (aynı WiFi, sıfır-konfig) ───────────────────────────────────────
async function discoverMdns(): Promise<string | null> {
  if (Platform.OS === "web") return null;
  let Zeroconf: any;
  try {
    // @ts-ignore - opsiyonel native modül (yalnızca native platformda mevcut)
    Zeroconf = require("react-native-zeroconf").default;
  } catch {
    return null; // paket yoksa atla
  }
  return new Promise<string | null>((resolve) => {
    let done = false;
    let zc: any;
    const finish = (val: string | null) => {
      if (done) return;
      done = true;
      try {
        zc?.stop?.();
        zc?.removeDeviceListeners?.();
      } catch {}
      resolve(val);
    };
    try {
      zc = new Zeroconf();
      zc.on("resolved", (svc: any) => {
        const ip: string | undefined = (svc?.addresses || []).find(
          (a: string) => typeof a === "string" && a.includes(".") && !a.startsWith("169.254")
        );
        const port = svc?.port || 8000;
        if (ip) finish(`http://${ip}:${port}`);
      });
      zc.on("error", () => {});
      // Backend auto_discovery.py: _pemfvet._tcp.local. (port 8000)
      zc.scan("pemfvet", "tcp", "local.");
      setTimeout(() => finish(null), MDNS_TIMEOUT_MS);
    } catch {
      finish(null);
    }
  });
}

// ── 3. Subnet tarama (mDNS fallback) ────────────────────────────────────────
async function discoverSubnet(): Promise<string | null> {
  // Web'de tarayıcı keyfi IP'lere ham health/TCP bağlantısı yapamaz (CORS/sandbox) → subnet
  // taraması yalnız boşa hata üretir. Web'de origin zaten doğru (backend serve eder) → atla (audit).
  if (Platform.OS === "web") return null;
  const cur = serviceConfig.apiBaseUrl.replace("/api", "").replace(/^https?:\/\//, "").split(":")[0];
  const parts = cur.split(".");
  const here = parts.length === 4 ? parts.slice(0, 3).join(".") : null;
  const subnets = [here, "192.168.1", "192.168.0", "192.168.137", "10.0.0", "172.16.0"].filter(
    (v, i, a): v is string => !!v && a.indexOf(v) === i
  );
  const hosts = [100, 1, 101, 2, 102, 110, 50, 200, 137];
  for (const sub of subnets) {
    const results = await Promise.allSettled(
      hosts.map(async (h) => {
        const ip = `${sub}.${h}`;
        if (await checkHealth(ip)) return ip;
        throw new Error("nf");
      })
    );
    for (const r of results) if (r.status === "fulfilled" && r.value) return `http://${r.value}:8000`;
  }
  return null;
}

// ── 4. Supabase remote (farklı WiFi, QR YOK) ────────────────────────────────
async function discoverRemote(): Promise<string | null> {
  const id = await getStoredDeviceId();
  if (id) {
    const url = await getRemoteUrlForDevice(id);
    if (url && (await checkHealth(url))) return url;
  }
  // GÜVENLİK: device_id yoksa kodsuz/kimliksiz OTOMATİK eşleştirme YAPMA
  // (cross-tenant yanlış-bağlanma riski). Eşleştirme yalnız açık kod/kimlik ile.
  return null;
}

/**
 * Tam keşif merdiveni. Çalışan adresi config'e uygular + döndürür (yoksa null).
 */
export async function discoverBackend(): Promise<DiscoveryResult | null> {
  // Web: origin zaten doğru kaynaktır.
  if (Platform.OS === "web") {
    const origin = serviceConfig.apiBaseUrl.replace("/api", "");
    if (await checkHealth(origin)) return { address: origin, source: "current" };
  }

  try {
    const saved =
      (await AsyncStorage.getItem(ADDR_KEY)) || (await AsyncStorage.getItem("@pemf_server_ip"));
    if (saved && (await checkHealth(saved))) {
      await apply(saved);
      return { address: saved, source: "saved" };
    }
  } catch {}

  const m = await discoverMdns();
  if (m && (await checkHealth(m))) {
    await apply(m);
    return { address: m, source: "mdns" };
  }

  const s = await discoverSubnet();
  if (s) {
    await apply(s);
    return { address: s, source: "subnet" };
  }

  const r = await discoverRemote();
  if (r) {
    await apply(r);
    return { address: r, source: "remote" };
  }

  return null;
}
