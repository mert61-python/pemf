// Author: mertaygn, cglrgrkn
import { useRef } from 'react'
import { ArrowRight } from './Icons'
import { useTranslation } from 'react-i18next'

/** Uygulama ekran görüntüleri — telefon çerçeveli, yatay kaydırmalı galeri. YH B7: İngilizce sayfada aynı ekranların İngilizce arayüzlü
 *  çekimi (`/screenshots/en/` — aynı adlar, 560×1116 JPEG; yalıtılmış kum havuzunda, yalnız UYDURMA demo verisiyle); Türkçe set DEĞİŞMEDİ. */
const SHOTS = [
  { src: '/screenshots/01-profil.jpg',    baslik: 'ekranlar.ekran.profil.baslik',        aciklama: 'ekranlar.ekran.profil.aciklama' },
  { src: '/screenshots/02-teshis.jpg',    baslik: 'ekranlar.ekran.teshis.baslik',        aciklama: 'ekranlar.ekran.teshis.aciklama' },
  { src: '/screenshots/03-modeller.jpg',  baslik: 'ekranlar.ekran.modeller.baslik',    aciklama: 'ekranlar.ekran.modeller.aciklama' },
  { src: '/screenshots/04-aipro.jpg',     baslik: 'ekranlar.ekran.aipro.baslik', aciklama: 'ekranlar.ekran.aipro.aciklama' },
  { src: '/screenshots/05-kontrol.jpg',   baslik: 'ekranlar.ekran.kontrol.baslik',       aciklama: 'ekranlar.ekran.kontrol.aciklama' },
  { src: '/screenshots/06-dashboard.jpg', baslik: 'ekranlar.ekran.panel.baslik',      aciklama: 'ekranlar.ekran.panel.aciklama' },
  { src: '/screenshots/07-hastalar.jpg',  baslik: 'ekranlar.ekran.hastalar.baslik',     aciklama: 'ekranlar.ekran.hastalar.aciklama' },
  { src: '/screenshots/08-gecmis.jpg',    baslik: 'ekranlar.ekran.gecmis.baslik',    aciklama: 'ekranlar.ekran.gecmis.aciklama' },
] as const

/** Etkin dile göre görsel adresi: İngilizcede `/screenshots/en/<ad>`, Türkçede değişmeden `/screenshots/<ad>`. */
export function ekranGorseli(src: string, dil: string): string {
  return dil === 'en' ? src.replace('/screenshots/', '/screenshots/en/') : src
}

export default function AppScreenshots() {
  const { t, i18n } = useTranslation()
  const trackRef = useRef<HTMLDivElement>(null)

  const scroll = (dir: -1 | 1) => {
    const el = trackRef.current
    /* istanbul ignore if -- ULASILAMAZ: kaydırma düğmeleri şeritle AYNI çizimde; düğme varken ref hep dolu */
    if (!el) return
    el.scrollBy({ left: dir * Math.min(el.clientWidth * 0.8, 720), behavior: 'smooth' })
  }

  return (
    <section className="border-b border-border/60">
      <div className="mx-auto max-w-6xl 2xl:max-w-7xl px-5 py-20 sm:px-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div className="max-w-xl">
            <span className="chip">{t('ekranlar.rozet')}</span>
            <h2 className="mt-4 text-3xl font-bold sm:text-4xl">{t('ekranlar.baslik')}</h2>
            <p className="mt-3 text-muted">
              {t('ekranlar.aciklama')}
            </p>
          </div>
          <div className="hidden shrink-0 gap-2 md:flex">
            <button
              type="button"
              onClick={() => scroll(-1)}
              aria-label={t('ekranlar.onceki')}
              className="grid h-10 w-10 place-items-center rounded-full border border-border bg-bg/60 text-muted transition hover:border-border-strong hover:text-fg"
            >
              <ArrowRight className="h-4 w-4 rotate-180" />
            </button>
            <button
              type="button"
              onClick={() => scroll(1)}
              aria-label={t('ekranlar.sonraki')}
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
                  src={ekranGorseli(s.src, i18n.language)}
                  alt={t('ekranlar.altMetin', { title: t(s.baslik) })}
                  width={560}
                  height={1116}
                  loading="lazy"
                  className="w-full rounded-[1.6rem]"
                />
              </div>
              <figcaption className="mt-4 text-center">
                <div className="text-sm font-semibold">{t(s.baslik)}</div>
                <div className="mt-0.5 text-xs text-muted">{t(s.aciklama)}</div>
              </figcaption>
            </figure>
          ))}
        </div>

        <p className="mt-2 text-center text-xs text-muted/70 md:hidden">{t('ekranlar.kaydirin')}</p>
      </div>
    </section>
  )
}
