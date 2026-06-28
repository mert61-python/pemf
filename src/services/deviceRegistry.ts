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

/** Belirli device_id için güncel (taze) tunnel_url. */
export async function getRemoteUrlForDevice(deviceId: string): Promise<string | null> {
  const c = client();
  if (!c || !deviceId) return null;
  // GÜVENLİ: YALNIZ resolve_device RPC (anon tabloyu DÖKEMEZ, tek taze satır döner).
  // Doğrudan-tablo fallback'i KALDIRILDI (P1) — RLS deploy edilmemişse cross-tenant
  // dump riski taşıyordu. Fail-secure: RPC yoksa/hata verirse null döner (sızdırmaz).
  try {
    const { data, error } = await c.rpc("resolve_device", { p_device_id: deviceId });
    if (error) return null;
    const row = (data as Record<string, unknown>[] | null)?.[0];
    if (row) {
      const dev = rowToRemoteDevice(row);
      if (dev.tunnel_url && isFresh(dev.last_seen)) return dev.tunnel_url;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * 6-haneli eşleştirme kodu ile cihaz bul (büyük/küçük harf duyarsız).
 * tunnel_url'i olan ve TAZE (canlı) ilk cihazı döndürür, yoksa null.
 */
export async function getDeviceByPairingCode(code: string): Promise<RemoteDevice | null> {
  const c = client();
  const trimmed = code.trim();
  if (!c || !trimmed) return null;
  // GÜVENLİ: YALNIZ resolve_device RPC (anon kodla TEK satır çözer, listeleyemez/dökemez).
  // Doğrudan-tablo fallback'i KALDIRILDI (P1, dump riski). Fail-secure: RPC yoksa null.
  try {
    const { data, error } = await c.rpc("resolve_device", { p_code: trimmed });
    if (error) return null;
    const row = (data as Record<string, unknown>[] | null)?.[0];
    if (row) {
      const dev = rowToRemoteDevice(row);
      if (dev.tunnel_url && isFresh(dev.last_seen)) return dev;
    }
    return null;
  } catch {
    return null;
  }
}

// NOT: listRecentDevices() KALDIRILDI (P1). Anon tüm 'devices' tablosunu listeliyordu
// (cross-tenant dump). Güvenli RLS'te zaten boş dönerdi + hiçbir yerde kullanılmıyordu.
// Eşleştirme YALNIZ açık device_id/pairing_code ile resolve_device RPC'si üzerinden yapılır.
