// Author: mertaygn, cglrgrkn
import { DOWNLOAD_HOST } from '../config'

/* ============================================================
   İNDİRME SAYACI (2026-08-06)

   Kaynak: GitHub Releases API — her asset'in `download_count` alanı.

   ⚠️ DÜRÜSTLÜK — BU SAYI "KAÇ KİŞİ" DEĞİL, "KAÇ İNDİRME"DİR. İki bilinen şişme kaynağı var:

     1. **Oto-güncelleme.** Client v1.9.3'ten beri kendini günceller ve bunu yaparken
        `PEMFVetClient-Setup.exe`'yi İNDİRİR (bkz. launcher self-update). Yani kurulu her
        cihaz, her yeni sürümde Windows sayacını bir artırır — yeni kullanıcı olmadan.
     2. **Geliştirme/test indirmeleri.** Sürüm doğrulaması için yapılan kendi indirmelerimiz
        de sayılır.

   Bu yüzden arayüzde "kullanıcı" DEĞİL "indirme" denir ve dipnotta oto-güncellemenin dahil
   olduğu yazılır. Gerçek benzersiz kullanıcı sayısı ancak cihaz kaydı (Supabase `devices`)
   üzerinden verilebilir; onu bu kaynakla karıştırmayın.
   ============================================================ */

const API = `https://api.github.com/repos/${DOWNLOAD_HOST.githubOwner}/${DOWNLOAD_HOST.githubRepo}/releases?per_page=100`

/** Sayılacak kurulum dosyaları. Paketler (base.zip / model zip'leri) HARİÇ — onlar
 *  client'ın kendi çektiği runtime bileşenleridir, "indirme" sayılırsa sayaç anlamsızca şişer. */
// ⚠️ AD DESENİ, SABİT AD DEĞİL (2026-08-10). Kurulum dosyası artık sürüm taşıyor
// (`PEMFVetClient-Setup-1.9.18.exe`). Sabit ada bakan eski liste, yeni sürümlerin indirmelerini
// HİÇ SAYMIYORDU → Windows sayacı sessizce 0'a düşerdi. Desen hem eski (`...-Setup.exe`) hem
// yeni (`...-Setup-<sürüm>.exe`) adları yakalar, böylece geçmiş sayı da korunur.
const WINDOWS_RE = /^PEMFVetClient-Setup(-\d+\.\d+\.\d+)?\.exe$/i
const ANDROID_RE = /^PEMF_Vet_Mobil(-\d+\.\d+\.\d+)?\.apk$/i

// ⚠️ macOS/Linux SAYILMAZ (2026-08-10, sahip kararı). O paketler yayında AMA site onları
// "Yakında" gösteriyor: donanım (STM seri + ESP MQTT + hotspot) Windows'a özel, o platformlarda
// cihaz sürülemez. İndirilemeyen bir platformun indirmesini toplama katmak sayıyı şişirir ve
// "kaç kişi kullanıyor" izlenimini bozar — o dosyalar çoğunlukla bizim kendi doğrulamalarımız.
// Toplam artık YALNIZ Windows + Android.

export interface DownloadStats {
  windows: number
  android: number
  total: number
  /** Veri ne zaman çekildi (epoch ms) */
  fetchedAt: number
}

const CACHE_KEY = 'pemf_dl_stats_v1'
/** GitHub kimliksiz API sınırı saatte 60 istek. 30 dk önbellek hem sınırı hem gürültüyü keser. */
const CACHE_MS = 30 * 60 * 1000

function readCache(): DownloadStats | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const v = JSON.parse(raw) as DownloadStats
    if (!v || typeof v.total !== 'number') return null
    if (Date.now() - v.fetchedAt > CACHE_MS) return null
    return v
  } catch {
    return null
  }
}

function writeCache(v: DownloadStats): void {
  try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(v)) } catch { /* kota/gizli mod */ }
}

interface GhAsset { name?: string; download_count?: number }
interface GhRelease { assets?: GhAsset[] }

/** API yanıtını topla. Saf fonksiyon → test edilebilir. */
export function aggregate(releases: GhRelease[]): Omit<DownloadStats, 'fetchedAt'> {
  let windows = 0, android = 0
  for (const r of releases || []) {
    for (const a of r?.assets || []) {
      const n = a?.name || ''
      const c = Number(a?.download_count)
      if (!Number.isFinite(c) || c < 0) continue
      if (WINDOWS_RE.test(n)) windows += c
      else if (ANDROID_RE.test(n)) android += c
    }
  }
  return { windows, android, total: windows + android }
}

/**
 * İndirme sayılarını getir. BAŞARISIZSA null döner — çağıran bölümü GİZLEMELİ.
 * Yanlış/eski bir sayı göstermektense hiç göstermemek daha dürüsttür.
 */
export async function fetchDownloadStats(signal?: AbortSignal): Promise<DownloadStats | null> {
  const cached = readCache()
  if (cached) return cached
  try {
    const res = await fetch(API, {
      signal,
      headers: { Accept: 'application/vnd.github+json' },
    })
    // 403 = kimliksiz oran sınırı (saatte 60). Sessizce gizle, kullanıcıya hata gösterme.
    if (!res.ok) return null
    const json = (await res.json()) as GhRelease[]
    if (!Array.isArray(json)) return null
    const v: DownloadStats = { ...aggregate(json), fetchedAt: Date.now() }
    writeCache(v)
    return v
  } catch {
    return null
  }
}
