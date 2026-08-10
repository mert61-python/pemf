// Author: mertaygn, cglrgrkn
import { useEffect, useState } from 'react'
import { fetchDownloadStats, type DownloadStats as Stats } from '../lib/downloadStats'

/**
 * İNDİRME SAYACI (2026-08-06)
 *
 * ⚠️ Bilinçli olarak "kullanıcı" DEĞİL "indirme" der: client oto-güncellenirken aynı kurulum
 * dosyasını yeniden indirir, dolayısıyla sayı benzersiz kişi sayısı DEĞİLDİR (bkz. lib/downloadStats.ts).
 * Veri çekilemezse (ağ / GitHub oran sınırı) bölüm HİÇ gösterilmez — eski ya da yanlış bir
 * sayı göstermek, hiç göstermemekten daha kötüdür.
 */
export function DownloadStats() {
  const [s, setS] = useState<Stats | null>(null)

  useEffect(() => {
    const ac = new AbortController()
    fetchDownloadStats(ac.signal).then(setS).catch(() => setS(null))
    return () => ac.abort()
  }, [])

  if (!s || s.total <= 0) return null

  return (
    <section className="mx-auto mt-10 max-w-3xl rounded-2xl border border-white/10 bg-white/5 p-6 text-center">
      <h2 className="text-lg font-semibold text-white">Toplam indirme</h2>
      <p className="mt-1 text-4xl font-bold text-teal-300">{s.total.toLocaleString('tr-TR')}</p>
      <div className="mt-4 flex flex-wrap justify-center gap-6 text-sm text-white/70">
        <Stat label="Windows" value={s.windows} />
        <Stat label="Android" value={s.android} />
        {s.other > 0 && <Stat label="macOS / Linux" value={s.other} />}
      </div>
      <p className="mt-4 text-xs text-white/40">
        Kaynak: GitHub Releases. Otomatik güncellemeler de bu sayıya dahildir; benzersiz
        kullanıcı sayısı değildir.
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
