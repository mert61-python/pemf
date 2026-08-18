// Author: mertaygn, cglrgrkn
import { supabase } from './supabase'

/* ============================================================
   KULLANIM SAYACI (2026-08-13) — "indirme" değil BENZERSİZ KULLANIM.

   Kaynak: Supabase `usage_counts()` RPC (bkz. database/supabase_kullanim_sayaci.sql).

   NEDEN DEĞİŞTİ: site GitHub Releases `download_count` gösteriyordu ve o sayı "kaç kişi"
   DEĞİL "kaç indirme"dir. İki şişme kaynağı ölçülmüştü: (1) client her sürümde kendini
   güncellerken kurulum dosyasını YENİDEN indirir → kurulu her cihaz, yeni kullanıcı olmadan
   sayacı artırır; (2) sürüm doğrulaması için yaptığımız kendi indirmelerimiz. Eski dosya
   (`downloadStats.ts`) bunu zaten dipnotta itiraf ediyordu; eksik olan gerçek kaynaktı.

   NE SAYILIYOR:
     accounts       → e-postası DOĞRULANMIŞ hesap. "Benzersiz kullanıcı" budur.
     devicesTotal   → kurulu cihaz (device_id MAC tabanlı birincil anahtar).
     devicesActive  → son 30 günde heartbeat gönderen cihaz.

   ⚠️ DÜRÜSTLÜK SINIRI: bir klinikte iki makine varsa `devices` 2 sayar; aynı kişi iki
   makinede çalışıyorsa `accounts` 1 sayar. İkisi FARKLI şeyleri ölçer, toplanmazlar.
   Android telefonlar `devices`e KAYDOLMAZ (yalnız okur) — mobil kurulum sayısı bu kaynakta
   YOKTUR ve uydurulmaz.
   ============================================================ */

export interface UsageStats {
  accounts: number
  devicesTotal: number
  devicesActive: number
  /** Veri ne zaman çekildi (epoch ms) */
  fetchedAt: number
}

/** RPC henüz deploy edilmemişse / ağ yoksa `null` döner — çağıran bölümü HİÇ göstermez.
 *  Eski ya da uydurma bir sayı göstermek, hiç göstermemekten kötüdür. */
export async function fetchUsageStats(signal?: AbortSignal): Promise<UsageStats | null> {
  if (!supabase) return null
  try {
    const { data, error } = await supabase.rpc('usage_counts')
    if (signal?.aborted || error) return null
    // RPC `returns table(...)` → tek satırlık dizi.
    const row = (Array.isArray(data) ? data[0] : data) as
      | { accounts?: number; devices_total?: number; devices_active?: number }
      | null
      | undefined
    if (!row) return null
    const accounts = Number(row.accounts ?? 0)
    const devicesTotal = Number(row.devices_total ?? 0)
    const devicesActive = Number(row.devices_active ?? 0)
    if (!Number.isFinite(accounts) || !Number.isFinite(devicesTotal)) return null
    return { accounts, devicesTotal, devicesActive, fetchedAt: Date.now() }
  } catch {
    return null
  }
}
