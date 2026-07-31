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
import { updateServiceConfig, serviceConfig, setStoredDeviceId, getStoredDeviceId, setStoredApiToken } from "@/services/config";
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

/** TEMASSIZ UZAKTAN AUTH: YERELken (LAN) cihazın api_token'ını çekip saklar. Backend bu endpoint'i
 *  UZAK (tünel) isteğe 403 verir → token YALNIZ aynı-WiFi'deyken alınır. Sonra farklı ağda tünel
 *  üzerinden HTTP (X-API-Key) + WS (?token=) bu token'la geçer. (Auth alanı UI'dan kaldırıldığı için
 *  uzaktan auth aksi halde imkânsızdı → "uzaktan bağlanıyor ama veri/WS 401" kök çözümü.) */
async function provisionToken(base: string): Promise<void> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), HEALTH_TIMEOUT_MS);
    const res = await fetch(`${base}/api/auth/token`, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return; // uzak=403 / eski-backend=404 → mevcut saklı token korunur
    const d = await res.json();
    if (d?.token) await setStoredApiToken(String(d.token));
  } catch {
    /* ignore */
  }
}

/** TEMASSIZ UZAKTAN PAIRING: 6-haneli eşleştirme kodunu cihaz api_token'ıyla takas eder (hiç
 *  LAN'a girmemiş telefon kod-yolu için — kodun kendisi kimlik; backend tünelden kabul eder,
 *  kaba-kuvvete karşı throttle'lı). Başarılıysa token saklanır → uzaktan HTTP + WS auth geçer. */
export async function exchangeCodeForToken(base: string, code: string): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), HEALTH_TIMEOUT_MS);
    const res = await fetch(`${toBase(base)}/api/auth/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
      signal: ctrl.signal,
    });
    clearTimeout(t);
    if (!res.ok) return false; // 403 yanlış kod / 429 throttle / 404 eski-backend
    const d = await res.json();
    if (d?.token) { await setStoredApiToken(String(d.token)); return true; }
    return false;
  } catch {
    return false;
  }
}

/** /api/health doğrular; başarılıysa deviceId + (yerelse) api_token'ı saklar (uzaktan erişim için).
 *  requireDeviceId verilirse SADECE o cihaza bağlan (yanlış-cihaz koruması; oto-keşifte kullanılır). */
export async function checkHealth(addr: string, requireDeviceId?: string | null): Promise<boolean> {
  try {
    const base = toBase(addr);
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), HEALTH_TIMEOUT_MS);
    const res = await fetch(`${base}/api/health`, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return false;
    const data = await res.json();
    // KESİN PEMF kimliği: 'status:online' TEK BAŞINA yetmez (router/NAS de döndürebilir) → service ŞART.
    if (data?.service !== "PEMF-Vet") return false;
    // YANLIŞ-CİHAZ KORUMASI: kayıtlı device_id varsa SADECE o cihaza bağlan (2-cihazlı klinikte
    // yanlış makineyi sürmek = tıbbi risk). requireDeviceId yoksa (ilk eşleşme / manuel) serbest.
    if (requireDeviceId && data?.deviceId && String(data.deviceId) !== requireDeviceId) return false;
    if (data?.deviceId) await setStoredDeviceId(String(data.deviceId)).catch(() => {});
    await provisionToken(base); // yerelse token sakla; uzaksa backend 403 → no-op
    return true;
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

/** Telefon WiFi'de mi? — WiFi'de YEREL keşif (mDNS/subnet) önce; aksi halde REMOTE önce denenir. */
async function _isOnWifi(): Promise<boolean> {
  try {
    // @ts-ignore - opsiyonel native modül
    const NetInfo = require("@react-native-community/netinfo").default;
    const st = await NetInfo.fetch();
    return st?.type === "wifi";
  } catch {
    return true; // bilinmiyorsa yerel-önce (eski davranış, güvenli)
  }
}

async function probeHost(ip: string, timeoutMs: number, _requireDeviceId?: string | null): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    const res = await fetch(`http://${ip}:8000/api/health`, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return false;
    const d = await res.json();
    if (d?.service !== "PEMF-Vet") return false; // KESİN PEMF (rastgele :8000 sunucusuna bağlanma)
    if (d?.deviceId) await setStoredDeviceId(String(d.deviceId)).catch(() => {}); // bulunan GERÇEK id'yi sakla
    await provisionToken(`http://${ip}:8000`); // yerel bulundu → token sakla (uzaktan için)
    return true;
  } catch {
    return false;
  }
}

async function discoverSubnet(requireDeviceId?: string | null): Promise<string | null> {
  // Web'de tarayıcı keyfi IP'lere health bağlantısı yapamaz (CORS) → atla; web'de origin zaten doğru.
  if (Platform.OS === "web") return null;
  // NOT: isOnWifi() ile ATLANMAZ — açılışta NetInfo henüz hazır değilken false dönüp aynı-WiFi yerel
  // keşfini KIRIYORDU (regresyon). Subnet farklı ağda zaten EN SON denendiğinden (remote'tan sonra)
  // ekstra maliyet sadece remote da başarısızken oluşur — kabul edilebilir.
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
          if (await probeHost(ip, 1200, requireDeviceId)) return ip;
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
    if (url && (await checkHealth(url, id))) return url;
  }
  // GÜVENLİK: device_id yoksa kodsuz/kimliksiz OTOMATİK eşleştirme YAPMA
  // (cross-tenant yanlış-bağlanma riski). Eşleştirme yalnız açık kod/kimlik ile.
  return null;
}

/**
 * Tam keşif merdiveni. Çalışan adresi config'e uygular + döndürür (yoksa null).
 */
/** AYNI-WiFi LAN ÖNCELİĞİ (kök-neden fix). Bağlanılan adres TÜNEL/uzak ise, cihazın /api/health'ten
 *  dönen `localIp`'sini telefondan DOĞRUDAN dener; ulaşılıyorsa LAN'a GEÇER.
 *
 *  NEDEN: Keşif merdiveni (mDNS başarısızsa) remote-tüneli subnet-taramasından ÖNCE bağlıyordu →
 *  telefon aynı WiFi'de cihaza HTTP ile ulaşabildiği hâlde TÜNEL üzerinden bağlanıp orada kalıyordu.
 *  Tünel auth-ister (reinstall api_token'ı değişince app'in bayat token'ı → 401); LAN ise auth-MUAF.
 *  localIp-yükseltmesi hem "aynı-WiFi'de otomatik bağlanmıyor" hem "uzaktan bağlanıyor ama 401" kökünü
 *  çözer + checkHealth(lan) provisionToken ile GÜNCEL token'ı çeker (bayat-token'ı tazeler). */
async function preferLanIfReachable(result: DiscoveryResult | null): Promise<DiscoveryResult | null> {
  if (!result) return result;
  if (Platform.OS === "web") return result; // web origin zaten doğru
  const isLan = /\/\/(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.|localhost)/i.test(result.address);
  if (isLan) return result; // zaten LAN → yükseltme gereksiz
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), HEALTH_TIMEOUT_MS);
    const res = await fetch(`${toBase(result.address)}/api/health`, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return result;
    const d = await res.json();
    const lan: string | undefined = d?.localIp;
    if (lan && /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(lan)) {
      const lanAddr = `http://${lan}:8000`;
      // Telefon aynı-WiFi'de mi? checkHealth GERÇEK LAN erişimini dener + (yerelse) güncel token'ı saklar.
      if (await checkHealth(lanAddr)) {
        await apply(lanAddr);
        return { address: lanAddr, source: "subnet" };
      }
    }
  } catch {
    /* ulaşılamadı → tünel adresinde kal (farklı WiFi) */
  }
  return result;
}

let _discoverInFlight: Promise<DiscoveryResult | null> | null = null;
// ORTA fix: örtüşen keşif FIRTINASINI önle — WS düşünce onNeedRediscovery HER başarısızlıkta çağrılıyor;
// önceki uzun (~70sn) subnet taraması bitmeden yenisi başlıyordu (80+ eşzamanlı fetch + yarışlı apply/
// AsyncStorage yazımı → WS hedefi çırpınıyordu). Aynı anda TEK keşif; ikinci çağrı mevcut Promise'i döndürür.
export function discoverBackend(): Promise<DiscoveryResult | null> {
  if (_discoverInFlight) return _discoverInFlight;
  // Sonuç TÜNEL ise LAN'a yükselt (aynı-WiFi önceliği) → tünel-401 + LAN-gölgeleme kök çözümü.
  _discoverInFlight = _discoverBackendImpl()
    .then(preferLanIfReachable)
    .finally(() => { _discoverInFlight = null; });
  return _discoverInFlight;
}
async function _discoverBackendImpl(): Promise<DiscoveryResult | null> {
  // Web: origin zaten doğru kaynaktır.
  if (Platform.OS === "web") {
    const origin = serviceConfig.apiBaseUrl.replace("/api", "");
    if (await checkHealth(origin)) return { address: origin, source: "current" };
  }

  // NOT: Oto-keşifte device_id EŞLEŞTİRMESİ YAPILMAZ. Saklanan device_id bayat/yanlış olabiliyordu
  // (allowBackup ile reinstall'da geri yüklenen ESKİ id; ya da çok-arabirimli MAC'te getnode() farkı) →
  // eşleşmeme yüzünden LAN'daki GERÇEK cihaz reddedilip "Çevrimdışı" kalıyordu (regresyon, logcat
  // ile kanıtlandı: probe .40'ı buldu ama id farkı yüzünden reddetti). Artık LAN'daki herhangi
  // "PEMF-Vet" cihazına bağlanır + bulunan GERÇEK id'yi saklar (kendi kendini onarır). Çok-cihazlı
  // klinik için elle kod/kimlik girişi var.

  // 1) Kayıtlı adres (en hızlı)
  try {
    const saved =
      (await AsyncStorage.getItem(ADDR_KEY)) || (await AsyncStorage.getItem("@pemf_server_ip"));
    if (saved) {
      // YÜKSEK fix: LAN IP'de device_id GEVŞEK kalsın (yukarıdaki regresyon: bayat id gerçek LAN cihazını
      // reddediyordu). Ama TÜNEL/https adreste device_id ŞART: bayat trycloudflare URL'si BAŞKA kiracıya
      // atanabilir → yanlışlıkla başka kliniğin cihazına + BAŞKA HASTANIN verisine bağlanma riski.
      const isLan = /\/\/(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.|localhost)/i.test(saved);
      const requireId = isLan ? null : await getStoredDeviceId();
      if (await checkHealth(saved, requireId)) {
        await apply(saved);
        return { address: saved, source: "saved" };
      }
    }
  } catch {}

  // 2) mDNS (aynı WiFi, sıfır-konfig — varsa anında bulur)
  const m = await discoverMdns();
  if (m && (await checkHealth(m))) { await apply(m); return { address: m, source: "mdns" }; }

  // 3) UZAKTAN (farklı WiFi): kayıtlı device_id ile Supabase tünel URL → subnet'ten ÖNCE
  //    (farklı ağda tam /24 subnet ~sn boşa harcıyordu; remote orada hızlı bağlar).
  const r = await discoverRemote();
  if (r) { await apply(r); return { address: r, source: "remote" }; }

  // 4) Subnet tarama — HER ZAMAN son çare. Aynı WiFi'de mDNS başarısızsa cihazı bulan KANITLI yol.
  const s = await discoverSubnet();
  if (s) { await apply(s); return { address: s, source: "subnet" }; }

  return null;
}
