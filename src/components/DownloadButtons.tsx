import { useEffect, useState } from 'react'
import { CLIENT } from '../config'
import { Windows, Apple, Linux, Android, Download } from './Icons'
import { detectOS, type OS } from '../lib/os'

type Dl = { key: string; label: string; url: string; ready: boolean }

/** Windows + macOS + Linux indirme butonları. Kullanıcının OS'u birincil olur; hazır
 *  olmayan platform (ör. macOS imzalı .dmg beklerken) "Yakında" gösterir. */
export default function DownloadButtons({ size = 'md' }: { size?: 'md' | 'lg' }) {
  const [os, setOs] = useState<OS>('other')
  useEffect(() => setOs(detectOS()), [])

  const pad = size === 'lg' ? '!px-6 !py-3.5 text-[15px]' : ''

  if (!CLIENT.ready) {
    return (
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <span className={`btn-primary ${pad} cursor-not-allowed opacity-60`} aria-disabled>
          <Download className="h-5 w-5" />
          Yakında · v{CLIENT.version}
        </span>
        <span className="text-sm text-muted">
          Çıkışında haberdar olmak için{' '}
          <a href="mailto:destek@v-pemf.com?subject=PEMF%20Vet%20Client%20bildirim" className="text-primary hover:underline">
            bize yazın
          </a>
          .
        </span>
      </div>
    )
  }

  const iconFor = (key: string) => (key === 'macos' ? Apple : key === 'linux' ? Linux : key === 'android' ? Android : Windows)

  // Kullanıcının OS'u öne; hazır olmayanlar sona.
  const all: Dl[] = [CLIENT.downloads.windows, CLIENT.downloads.macos, CLIENT.downloads.linux, CLIENT.downloads.android]
  const rank = (d: Dl) => (d.key === os ? 0 : 1) + (d.ready ? 0 : 10)
  const sorted = [...all].sort((a, b) => rank(a) - rank(b))

  const btn = (d: Dl, isPrimary: boolean) => {
    const Icon = iconFor(d.key)
    if (!d.ready) {
      return (
        <span key={d.key} className={`btn-ghost ${pad} cursor-not-allowed opacity-60`} aria-disabled>
          <Icon className="h-5 w-5" />
          {d.label} · Yakında
        </span>
      )
    }
    return (
      <a key={d.key} href={d.url} className={`${isPrimary ? 'btn-primary' : 'btn-ghost'} ${pad}`}>
        <Icon className="h-5 w-5" />
        {isPrimary ? `${d.label} için indir` : d.label}
      </a>
    )
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
      {sorted.map((d, i) => btn(d, i === 0))}
    </div>
  )
}
