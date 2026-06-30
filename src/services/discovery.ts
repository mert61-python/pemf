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

// ── 3. Subnet tarama (mDNS fallback) — TAM /24 ──────────────────────────────
// KRİTİK FIX: eskiden yalnız SABİT host listesi [100,1,101,2,102,110,50,200,137] taranıyordu →
// backend DHCP ile ör. .40 alırsa BULUNAMIYORDU (mobil "otomatik bağlanmıyor" kök nedeni). Artık
// telefonun KENDİ alt-ağı (netinfo) + mevcut/yaygın alt-ağlarda TÜM /24 (1-254) paralel-parça taranır.
async function localSubnets(): Promise<string[]> {
  const subs: string[] = [];
  try {
    // @ts-ignore - opsiyonel native modül
    const NetInfo = require("@react-native-community/netinfo").default;
    const st = await NetInfo.fetch();
    const ip: string | undefined = st?.details?.ipAddress;
    if (ip && ip.includes(".")) {
      const p = ip.split(".");
      if (p.length === 4) subs.push(p.slice(0, 3).join("."));
    }
  } catch {}
  const cur = serviceConfig.apiBaseUrl.replace(/^https?:\/\//, "").split(":")[0];
  const cp = cur.split(".");
  if (cp.length === 4) subs.push(cp.slice(0, 3).join("."));
  subs.push("192.168.1", "192.168.0", "192.168.137");
  return subs.filter((v, i, a) => !!v && a.indexOf(v) === i);
}

async function probeHost(ip: string, timeoutMs: number): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    const res = await fetch(`http://${ip}:8000/api/health`, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return false;
    const d = await res.json();
    const ok = d?.service === "PEMF-Vet" || d?.status === "online";
    if (ok && d?.deviceId) await setStoredDeviceId(String(d.deviceId)).catch(() => {});
    return ok;
  } catch {
    return false;
  }
}

async function discoverSubnet(): Promise<string | null> {
  // Web'de tarayıcı keyfi IP'lere health bağlantısı yapamaz (CORS) → atla; web'de origin zaten doğru.
  if (Platform.OS === "web") return null;
  const subs = await localSubnets();
  // Yaygın hostlar ÖNCE (hızlı isabet, .40 dahil), sonra kalan TÜM /24 (DHCP IP herhangi biri olabilir).
  const priority = [1, 100, 2, 101, 102, 110, 50, 200, 137, 40, 10, 20, 30, 254];
  const order: number[] = [...priority];
  for (let h = 2; h <= 254; h++) if (!priority.includes(h)) order.push(h);
  for (const sub of subs) {
    for (let i = 0; i < order.length; i += 40) {
      const chunk = order.slice(i, i + 40);
      const results = await Promise.allSettled(
        chunk.map(async (h) => {
          const ip = `${sub}.${h}`;
          if (await probeHost(ip, 1200)) return ip;
          throw new Error("nf");
        })
      );
      for (const r of results) if (r.status === "fulfilled" && r.value) return `http://${r.value}:8000`;
    }
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

  // UZAKTAN (farklı WiFi): kayıtlı device_id ile Supabase'den güncel tünel URL → YEREL subnet taramasından
  // ÖNCE dene. Farklı WiFi'de subnet tarama backend'i bulamayıp ~15sn boşa harcıyordu; remote burada hızlı bağlar.
  const r = await discoverRemote();
  if (r) {
    await apply(r);
    return { address: r, source: "remote" };
  }

  const s = await discoverSubnet();
  if (s) {
    await apply(s);
    return { address: s, source: "subnet" };
  }

  return null;
}
