import { useRef } from 'react'
import { ArrowRight } from './Icons'

/** Uygulama ekran görüntüleri — telefon çerçeveli, yatay kaydırmalı galeri. */
const SHOTS = [
  { src: '/screenshots/01-profil.jpg',    title: 'Profil Seçimi',        desc: 'Ev Sahibi · Veteriner · Araştırma' },
  { src: '/screenshots/02-teshis.jpg',    title: 'Akıllı Teşhis',        desc: 'Kameradan anlık ağrı analizi' },
  { src: '/screenshots/03-modeller.jpg',  title: 'AI Tanı Modülleri',    desc: 'Görüntü, ses ve sinyal modelleri' },
  { src: '/screenshots/04-aipro.jpg',     title: 'AI Pro · Otonom Tedavi', desc: 'Kapalı-döngü otomatik terapi' },
  { src: '/screenshots/05-kontrol.jpg',   title: 'Cihaz Kontrolü',       desc: '8 bobin, frekans ve süre ayarı' },
  { src: '/screenshots/06-dashboard.jpg', title: 'Canlı Dashboard',      desc: 'Seans ve sensör telemetrisi' },
  { src: '/screenshots/07-hastalar.jpg',  title: 'Hasta Veritabanı',     desc: 'Klinik içi hasta ve seans kaydı' },
  { src: '/screenshots/08-gecmis.jpg',    title: 'AI Analiz Geçmişi',    desc: 'Şifreli, aranabilir analiz arşivi' },
]

export default function AppScreenshots() {
  const trackRef = useRef<HTMLDivElement>(null)

  const scroll = (dir: -1 | 1) => {
    const el = trackRef.current
    if (!el) return
    el.scrollBy({ left: dir * Math.min(el.clientWidth * 0.8, 720), behavior: 'smooth' })
  }

  return (
    <section className="border-b border-border/60">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div className="max-w-xl">
            <span className="chip">Uygulama</span>
            <h2 className="mt-4 text-3xl font-bold sm:text-4xl">Ekranlarla tanıyın</h2>
            <p className="mt-3 text-muted">
              Profil seçiminden yapay zekâ teşhisine, otonom tedaviden hasta arşivine —
              mobil ve masaüstünde aynı arayüz.
            </p>
          </div>
          <div className="hidden shrink-0 gap-2 md:flex">
            <button
              type="button"
              onClick={() => scroll(-1)}
              aria-label="Önceki"
              className="grid h-10 w-10 place-items-center rounded-full border border-border bg-bg/60 text-muted transition hover:border-border-strong hover:text-fg"
            >
              <ArrowRight className="h-4 w-4 rotate-180" />
            </button>
            <button
              type="button"
              onClick={() => scroll(1)}
              aria-label="Sonraki"
              className="grid h-10 w-10 place-items-center rounded-full border border-border bg-bg/60 text-muted transition hover:border-border-strong hover:text-fg"
            >
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div
          ref={trackRef}
          className="mt-12 flex snap-x snap-mandatory gap-6 overflow-x-auto pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {SHOTS.map((s) => (
            <figure key={s.src} className="w-[200px] shrink-0 snap-center sm:w-[224px]">
              <div className="relative rounded-[2rem] border border-border-strong bg-[#0b0f19] p-1.5 shadow-2xl ring-1 ring-white/5 transition-transform duration-300 hover:-translate-y-1">
                <img
                  src={s.src}
                  alt={`PEMF Vet — ${s.title}`}
                  width={560}
                  height={1116}
                  loading="lazy"
                  className="w-full rounded-[1.6rem]"
                />
              </div>
              <figcaption className="mt-4 text-center">
                <div className="text-sm font-semibold">{s.title}</div>
                <div className="mt-0.5 text-xs text-muted">{s.desc}</div>
              </figcaption>
            </figure>
          ))}
        </div>

        <p className="mt-2 text-center text-xs text-muted/70 md:hidden">← kaydırın →</p>
      </div>
    </section>
  )
}
