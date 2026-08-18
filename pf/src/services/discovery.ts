// Author: mertaygn, cglrgrkn
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
import { isPrivateHost } from "@/services/apiClient";

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

/** Adresin host kısmı (şema/port/yol olmadan). */
function hostOf(addr: string): string {
  return String(addr || "")
    .replace(/^https?:\/\//i, "")
    .split("/")[0]
    .split(":")[0]
    .toLowerCase();
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

/** Adresi uygula + kalıcılaştır. `updateServiceConfig` GEÇERSİZ adreste false döner; eskiden bu
 *  sonuç yok sayılıp adres yine de kaydediliyordu → "cihaz bulundu" denip trafik ESKİ adrese
 *  gitmeye devam ediyor, üstelik bozuk adres bir sonraki açılışa kalıyordu. */
async function apply(addr: string): Promise<boolean> {
  if (!updateServiceConfig(addr)) {
    console.warn("Keşif: geçersiz adres biçimi, uygulanmadı:", addr);
    return false;
  }
  await AsyncStorage.setItem(ADDR_KEY, addr).catch(() => {});
  return true;
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
      // AYRI try: eskiden ikisi aynı bloktaydı → `stop()` atarsa `removeDeviceListeners()` HİÇ
      // çalışmıyor ve 8 native dinleyici kalıcı olarak sızıyordu (7/24 açık kalan tıbbi cihazda
      // her keşif turunda birikir).
      try { zc?.stop?.(); } catch { /* ignore */ }
      try { zc?.removeDeviceListeners?.(); } catch { /* ignore */ }
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

/** Tarama sırasında bulunan aday — YAN ETKİSİZ. Kimlik/token yazımı KAZANAN adaya uygulanır. */
interface ProbeHit { ip: string; deviceId: string | null }

// YARIŞ (yan etkili paralel probe): `probeHost` eskiden yanıt veren HER host için setStoredDeviceId
// + provisionToken çağırıyordu ve tarama 40 host'u AYNI ANDA yokluyordu. İki PEMF cihazı olan bir
// klinikte ikisi de aynı parçada cevap verirse device_id ve api_token bir cihazdan, `Promise.
// allSettled` sonucundan seçilen bağlantı adresi ise DİĞERİNDEN olabiliyordu → uygulama A cihazına
// bağlanıp B cihazının token/kimliğini saklıyordu. Artık probe SALT-OKUR; yazma tek kazananda yapılır.
async function probeHost(ip: string, timeoutMs: number): Promise<ProbeHit | null> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    const res = await fetch(`http://${ip}:8000/api/health`, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return null;
    const d = await res.json();
    if (d?.service !== "PEMF-Vet") return null; // KESİN PEMF (rastgele :8000 sunucusuna bağlanma)
    return { ip, deviceId: d?.deviceId ? String(d.deviceId) : null };
  } catch {
    return null;
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
      const results = await Promise.allSettled(chunk.map((h) => probeHost(`${sub}.${h}`, 1200)));
      const hits: ProbeHit[] = results
        .filter((r): r is PromiseFulfilledResult<ProbeHit | null> => r.status === "fulfilled")
        .map((r) => r.value)
        .filter((v): v is ProbeHit => v !== null);
      if (hits.length === 0) continue;
      // Kayıtlı cihaz varsa ONU tercih et (çok cihazlı klinikte yanlış makineyi sürmemek için);
      // yoksa ilk bulunanı al. Yan etkiler (device_id + token) YALNIZ kazanana uygulanır.
      const winner = (requireDeviceId && hits.find((h) => h.deviceId === requireDeviceId)) || hits[0];
      if (hits.length > 1) {
        console.warn(`Keşif: ${hits.length} PEMF cihazı bulundu, ${winner.ip} seçildi.`);
      }
      const base = `http://${winner.ip}:8000`;
      if (winner.deviceId) await setStoredDeviceId(winner.deviceId).catch(() => {});
      await provisionToken(base); // yerel bulundu → token sakla (uzaktan erişim için)
      return base;
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
  if (isPrivateHost(hostOf(result.address))) return result; // zaten LAN → yükseltme gereksiz
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
        if (await apply(lanAddr)) return { address: lanAddr, source: "subnet" };
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
      // Ankor/tip hatası: bu regex hostname'lere de uyuyordu → `https://10.evil.com` "LAN" sayılıp
      // TÜNEL için ZORUNLU olan device_id kontrolünü atlatabiliyordu. Gerçek IP kontrolü kullan.
      const isLan = isPrivateHost(hostOf(saved));
      const requireId = isLan ? null : await getStoredDeviceId();
      if (await checkHealth(saved, requireId)) {
        if (await apply(saved)) return { address: saved, source: "saved" };
      }
    }
  } catch {}

  // 2) mDNS (aynı WiFi, sıfır-konfig — varsa anında bulur)
  const m = await discoverMdns();
  if (m && (await checkHealth(m)) && (await apply(m))) return { address: m, source: "mdns" };

  // 3) UZAKTAN (farklı WiFi): kayıtlı device_id ile Supabase tünel URL → subnet'ten ÖNCE
  //    (farklı ağda tam /24 subnet ~sn boşa harcıyordu; remote orada hızlı bağlar).
  const r = await discoverRemote();
  if (r && (await apply(r))) return { address: r, source: "remote" };

  // 4) Subnet tarama — HER ZAMAN son çare. Aynı WiFi'de mDNS başarısızsa cihazı bulan KANITLI yol.
  const s = await discoverSubnet();
  if (s && (await apply(s))) return { address: s, source: "subnet" };

  return null;
}
