// Author: mertaygn, cglrgrkn
import { useEffect, useState } from 'react'
import { fetchUsageStats, type UsageStats } from '../lib/usageStats'

/**
 * KULLANIM SAYACI (2026-08-13) — eskiden İNDİRME sayacıydı.
 *
 * ⚠️ NEDEN DEĞİŞTİ: GitHub `download_count` "kaç kişi" DEĞİL "kaç indirme"dir. Client her
 * sürümde kendini güncellerken kurulum dosyasını YENİDEN indirir → kurulu her cihaz, yeni
 * kullanıcı olmadan sayacı artırıyordu; buna kendi doğrulama indirmelerimiz de ekleniyordu.
 * Sayı bu yüzden gerçeğin üstündeydi ve dipnotta "benzersiz kullanıcı sayısı değildir" diye
 * itiraf ediliyordu. Artık kaynak Supabase `usage_counts()` RPC'si: doğrulanmış hesap sayısı.
 *
 * ⚠️ İKİ SAYI FARKLI ŞEYİ ÖLÇER, TOPLANMAZ: bir klinikte iki makine varsa "kurulu cihaz" 2,
 * aynı kişi iki makinede çalışıyorsa "kullanıcı" 1'dir. Bu yüzden tek bir "toplam" verilmez.
 *
 * Veri çekilemezse (RPC deploy edilmemiş / ağ) bölüm HİÇ gösterilmez — eski ya da uydurma bir
 * sayı göstermek, hiç göstermemekten daha kötüdür.
 */
export function DownloadStats() {
  const [s, setS] = useState<UsageStats | null>(null)

  useEffect(() => {
    const ac = new AbortController()
    fetchUsageStats(ac.signal).then(setS).catch(() => setS(null))
    return () => ac.abort()
  }, [])

  if (!s || s.accounts <= 0) return null

  return (
    <section className="mx-auto mt-10 max-w-3xl rounded-2xl border border-white/10 bg-white/5 p-6 text-center">
      <h2 className="text-lg font-semibold text-white">Benzersiz kullanıcı</h2>
      <p className="mt-1 text-4xl font-bold text-teal-300">{s.accounts.toLocaleString('tr-TR')}</p>
      {/* ⚠️ "Kurulu cihaz TOPLAMI" BİLEREK GÖSTERİLMİYOR (2026-08-13, ölçümle):
          `get_unique_device_id()` kimliği veri kökündeki `device_id.txt`te saklar; kök silinince
          (kaldırma / yeniden kurulum) `uuid.getnode()` bu makinelerde kararsız olduğu için YENİ
          kimlik üretilir ve ESKİ satır tabloda kalır. Ölçüldü: toplam 20 / aktif 14 — aradaki 6
          satır tek bir makinenin yeniden kurulumlarıydı. Yani toplam, "kaç klinik" sorusuna
          ŞİŞMİŞ cevap verir. Son 30 günde heartbeat gönderen cihaz sayısı ise bayat satırları
          kendiliğinden eler ve gerçekten kullanımda olanı gösterir. */}
      {s.devicesActive > 0 && (
        <div className="mt-4 flex flex-wrap justify-center gap-6 text-sm text-white/70">
          <Stat label="Aktif cihaz (30 gün)" value={s.devicesActive} />
        </div>
      )}
      <p className="mt-4 text-xs text-white/40">
        “Kullanıcı” e-postası doğrulanmış hesap sayısıdır. “Aktif cihaz” son 30 günde bağlanan
        ayrı makinedir — bir kullanıcının birden fazla cihazı olabilir, bu yüzden toplanmazlar.
      </p>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xl font-semibold text-white">{value.toLocaleString('tr-TR')}</div>
      <div className="text-xs uppercase tracking-wide text-white/50">{label}</div>
    </div>
  )
}
