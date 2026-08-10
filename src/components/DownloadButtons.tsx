// Author: mertaygn, cglrgrkn
import { useEffect, useState } from 'react'
import { CLIENT } from '../config'
import { Windows, Apple, Linux, Android, Download } from './Icons'
import { detectOS, type OS } from '../lib/os'
import { useDownloadGate, DownloadGateNote } from './DownloadGate'
import type { DownloadTarget } from '../lib/download'

// DENETIM 2026-08-06: `key` string idi ve tıklamada `as DownloadTarget` ile zorlanıyordu.
// config.ts'e kapıda tanımsız bir platform eklenirse (ör. 'ios') `resolveDownload` switch'i
// hiçbir dala girmeyip undefined döner → tıklamada TypeError, düğme sessizce ölür. Anahtarı
// hedef birleşimine bağla ki uyumsuzluğu derleyici yakalasın. `url` alanı da KALDIRILDI:
// adres çözümü yalnız lib/download.ts'in işi (yüzey adresi hiç görmesin).
type Dl = { key: DownloadTarget; label: string; ready: boolean }

/** Windows + macOS + Linux indirme butonları. Kullanıcının OS'u birincil olur; hazır
 *  olmayan platform (ör. macOS imzalı .dmg beklerken) "Yakında" gösterir. */
export default function DownloadButtons({ size = 'md' }: { size?: 'md' | 'lg' }) {
  const [os, setOs] = useState<OS>('other')
  useEffect(() => setOs(detectOS()), [])
  // İndirme kapısı (kayıt adımı — erişim kontrolü DEĞİL, bkz. lib/download.ts).
  // Hook koşulsuz çağrılmalı → aşağıdaki "Yakında" erken dönüşünden ÖNCE.
  const { loading, gated, download } = useDownloadGate()

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

  const iconFor = (key: DownloadTarget) => (key === 'macos' ? Apple : key === 'linux' ? Linux : key === 'android' ? Android : Windows)

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
    // `<a href>` DEĞİL `<button>`: bağlantıda sağ tık → "Bağlantıyı farklı kaydet" kapıyı atlardı.
    // (Adres paket içinde zaten açık olduğu için bu yalnızca akışı düzgün tutar, koruma sağlamaz.)
    return (
      <button
        key={d.key}
        type="button"
        onClick={() => download(d.key)}
        disabled={loading}
        aria-busy={loading}
        aria-label={gated ? `${d.label} için giriş yapıp indir` : `${d.label} için indir`}
        className={`${isPrimary ? 'btn-primary' : 'btn-ghost'} ${pad} cursor-pointer disabled:cursor-wait disabled:opacity-60`}
      >
        <Icon className="h-5 w-5" />
        {isPrimary ? (gated ? 'Giriş yap ve indir' : `${d.label} için indir`) : d.label}
      </button>
    )
  }

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        {sorted.map((d, i) => btn(d, i === 0))}
      </div>
      {/* Kapının gerekçesini kullanıcıya AÇIKÇA söyle (düğmeye basınca sürpriz modal çıkmasın). */}
      <DownloadGateNote />
    </>
  )
}
