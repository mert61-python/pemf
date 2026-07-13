import { useEffect, useState } from 'react'
import { CLIENT } from '../config'
import { Windows, Apple, Download } from './Icons'
import { detectOS, type OS } from '../lib/os'

/** Windows + macOS indirme butonları. Kullanıcının OS'u birincil olur;
 *  client henüz yayınlanmadıysa (CLIENT.ready=false) "Yakında" gösterir. */
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

  const win = CLIENT.downloads.windows
  const mac = CLIENT.downloads.macos
  const primary = os === 'macos' ? mac : win
  const secondary = os === 'macos' ? win : mac
  const PIcon = primary.key === 'macos' ? Apple : Windows
  const SIcon = secondary.key === 'macos' ? Apple : Windows

  return (
    <div className="flex flex-col gap-3 sm:flex-row">
      <a href={primary.url} className={`btn-primary ${pad}`}>
        <PIcon className="h-5 w-5" />
        {primary.label} için indir
      </a>
      <a href={secondary.url} className={`btn-ghost ${pad}`}>
        <SIcon className="h-5 w-5" />
        {secondary.label}
      </a>
    </div>
  )
}
