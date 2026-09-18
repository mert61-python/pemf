// Author: mertaygn, cglrgrkn
/**
 * Supabase 'devices' device-registry okuyucu — TEMASSIZ uzaktan erişim.
 * ====================================================================
 * Backend (servers/sync_worker) güncel tunnel_url'i Supabase 'devices' tablosuna
 * yazar. Burada device_id ile çekip, aynı WiFi'de bulunamayan cihaza QR OKUTMADAN
 * uzaktan bağlanırız. 'last_seen' taze değilse cihaz offline sayılır.
 *
 * Tablo SQL'i: guii/database/supabase_devices.sql
 */
import { createClient, SupabaseClient } from "@supabase/supabase-js";

// audit B-10.2: ÖNCE EXPO_PUBLIC_* env (build-time); yoksa gömülü varsayılan. Bu anahtar
// Supabase **publishable/anon** (istemci-güvenli, tasarımı gereği paylaşılır — service_role DEĞİL) +
// güvenlik RLS + SECURITY DEFINER RPC'lerdedir (anon tablo dökemez; bkz. database/supabase_*.sql).
// Yine de kendi projenizde EXPO_PUBLIC_* ile override edip anahtarı rotate edebilirsiniz.
const SUPABASE_URL =
  process.env.EXPO_PUBLIC_SUPABASE_URL ?? "https://wmsxonunkphjeregpvuj.supabase.co";
const SUPABASE_KEY =
  process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? "sb_publishable_D2SaRML_PIhRtr3kqlXxaw_1cS75GKT";

// last_seen bu süreden eskiyse cihazı "canlı değil" say (heartbeat 60sn).
const STALE_MS = 5 * 60 * 1000;

let _client: SupabaseClient | null = null;
function client(): SupabaseClient | null {
  if (_client) return _client;
  try {
    _client = createClient(SUPABASE_URL, SUPABASE_KEY, { auth: { persistSession: false } });
  } catch {
    _client = null;
  }
  return _client;
}

export interface RemoteDevice {
  device_id: string;
  name?: string;
  tunnel_url?: string | null;
  local_ip?: string | null;
  last_seen?: string;
}

function isFresh(lastSeen?: string): boolean {
  if (!lastSeen) return false; // heartbeat yoksa CANLI sayma
  const age = Date.now() - new Date(lastSeen).getTime();
  return age <= STALE_MS;
}

/** RPC dönüş satırını RemoteDevice'a maple. */
function rowToRemoteDevice(row: Record<string, unknown>): RemoteDevice {
  return {
    device_id: String(row.device_id ?? ""),
    name: row.name == null ? undefined : String(row.name),
    tunnel_url: (row.tunnel_url as string | null) ?? null,
    local_ip: (row.local_ip as string | null) ?? null,
    last_seen: row.last_seen == null ? undefined : String(row.last_seen),
  };
}

// audit (skor-4 kalan: Supabase timeout): asılı RPC cihaz-keşfini DONDURMASIN. Timeout'ta reddeder →
// çağıran fail-secure `null` döner (RPC arka planda biterse zararsız; supabase-js'in kendi timeout'u yok).
const RPC_TIMEOUT_MS = 6000;
function withTimeout<T>(p: PromiseLike<T>, ms = RPC_TIMEOUT_MS): Promise<T> {
  // Zamanlayıcı, RPC erken bitse bile temizlenmiyordu: her çağrı 6sn boyunca yaşayan bir timer +
  // closure bırakıyordu (keşif merdiveni bunu sık çağırır). `finally` ile iptal et.
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([
    Promise.resolve(p),
    new Promise<T>((_, reject) => {
      timer = setTimeout(() => reject(new Error("supabase timeout")), ms);
    }),
  ]).finally(() => {
    if (timer) clearTimeout(timer);
  });
}

/** Uzak cihaz çözümlemesinin AYRIŞTIRILMIŞ sonucu.
 *
 * ⚠️ SAHA BİLDİRİMİ 2026-08-12: kullanıcı doğru eşleştirme kodunu girdiği hâlde
 * "Bu kod/kimlikle eşleşen kayıtlı cihaz bulunamadı. Kodu kontrol edin." görüyordu ve
 * kodu defalarca kontrol etti. Oysa cihaz KAYITLIYDI ve kod DOĞRUYDU; yalnız cihazın
 * `tunnel_url`i boştu (uzaktan erişim cihazda açık değil). Eski kod iki DURUMU da `null`
 * döndürdüğü için ekran ikisini ayırt edemiyordu.
 *
 * Bunlar farklı sorunlar ve farklı çözümleri var:
 *   yok       → kod/kimlik yanlış (ya da cihaz hiç kaydolmamış)  → kullanıcı kodu düzeltir
 *   adres_yok → cihaz kayıtlı ama uzak adresi yok                 → CİHAZDA uzaktan erişimi aç
 *   bayat     → adres var ama heartbeat eski → cihaz kapalı/çevrimdışı
 *   hata      → Supabase'e ulaşılamadı (zaman aşımı) → İNTERNETİ kontrol et, kodu değil
 */
export type UzakCozumleme =
  | { durum: "bulundu"; device: RemoteDevice; url: string } // url NON-NULL: değişmez tipte
  | { durum: "adres_yok"; device: RemoteDevice }
  | { durum: "bayat"; device: RemoteDevice }
  | { durum: "yok" }
  | { durum: "hata" };

/** `resolve_device` RPC'sini çağırır ve sonucu SEBEBİYLE birlikte döndürür. */
async function _cozumle(params: Record<string, string>): Promise<UzakCozumleme> {
  const c = client();
  if (!c) return { durum: "hata" };
  try {
    const { data, error } = await withTimeout(c.rpc("resolve_device", params));
    if (error) return { durum: "hata" };
    const row = (data as Record<string, unknown>[] | null)?.[0];
    if (!row) return { durum: "yok" };
    const device = rowToRemoteDevice(row);
    if (!device.tunnel_url) return { durum: "adres_yok", device };
    if (!isFresh(device.last_seen)) return { durum: "bayat", device };
    return { durum: "bulundu", device, url: device.tunnel_url };
  } catch {
    return { durum: "hata" }; // zaman aşımı da "kod yanlış" DEĞİLDİR
  }
}

/** Eşleştirme kodu ile çöz (sebebiyle). */
export function uzakCihaziKodlaCoz(code: string): Promise<UzakCozumleme> {
  const trimmed = code.trim();
  if (!trimmed) return Promise.resolve({ durum: "yok" });
  return _cozumle({ p_code: trimmed });
}

/** Cihaz kimliği ile çöz (sebebiyle). */
export function uzakCihaziKimlikleCoz(deviceId: string): Promise<UzakCozumleme> {
  const trimmed = deviceId.trim();
  if (!trimmed) return Promise.resolve({ durum: "yok" });
  return _cozumle({ p_device_id: trimmed });
}

/** Belirli device_id için güncel (taze) tunnel_url (keşif merdiveni kullanır).
 *
 * ⚠️ Kendi RPC çağrısını YAPMAZ: `_cozumle`ye devreder. Eskiden aynı sorgu iki yerde ayrı
 * yazılıydı; birinin tazelik/adres kuralı değişip diğerininki kalırsa keşif ile elle-bağlanma
 * FARKLI kararlar verir. Tek yol → ayrışma imkânsız.
 */
export async function getRemoteUrlForDevice(deviceId: string): Promise<string | null> {
  const c = await uzakCihaziKimlikleCoz(deviceId);
  return c.durum === "bulundu" ? c.url : null;
}

// NOT: listRecentDevices() KALDIRILDI (P1). Anon tüm 'devices' tablosunu listeliyordu
// (cross-tenant dump). Güvenli RLS'te zaten boş dönerdi + hiçbir yerde kullanılmıyordu.
// Eşleştirme YALNIZ açık device_id/pairing_code ile resolve_device RPC'si üzerinden yapılır.
// NOT: getDeviceByPairingCode() KALDIRILDI (2026-08-12) — `uzakCihaziKodlaCoz` ile aynı işi
// yapıyordu ama SEBEBİ yutuyordu; iki paralel yol tutmak ayrışma davetiydi.
