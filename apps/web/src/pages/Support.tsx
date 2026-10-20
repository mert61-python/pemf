// Author: mertaygn, cglrgrkn
import { Link } from 'react-router-dom'
import { COMPANY, FAQ } from '../config'
import { ArrowRight } from '../components/Icons'
import { useTranslation } from 'react-i18next'

export default function Support() {
  const { t } = useTranslation()
  return (
    <>
      <section className="bg-hero border-b border-border/60">
        <div className="mx-auto max-w-3xl px-5 py-16 text-center sm:px-6 sm:py-20">
          <span className="chip">{t('ortak.nav.destek')}</span>
          <h1 className="mt-5 text-4xl font-extrabold sm:text-5xl">{t('destek.baslik')}</h1>
          <p className="mx-auto mt-4 max-w-xl text-muted">
            {t('destek.aciklama')}
          </p>
        </div>
      </section>

      <section className="border-b border-border/60">
        <div className="mx-auto max-w-3xl px-5 py-14 sm:px-6">
          <div className="space-y-3">
            {FAQ.map((f, i) => (
              <details key={i} className="card group p-0">
                <summary className="flex cursor-pointer items-center justify-between gap-4 px-6 py-4 font-semibold [&::-webkit-details-marker]:hidden">
                  {f.q}
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-border-strong text-muted transition-transform group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="px-6 pb-5 text-sm leading-relaxed text-muted">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-3xl px-5 py-16 sm:px-6">
          <div className="card p-8 text-center sm:p-10">
            <h2 className="text-2xl font-bold">{t('destek.yardim.baslik')}</h2>
            <p className="mx-auto mt-3 max-w-md text-muted">
              {t('destek.yardim.aciklama')}
            </p>
            {/* Metin denetimi 2026-08-20: destek sayfasında TELEFON yoktu (config'te var, yalnız
                alt bilgide görünüyordu) ve yanıt süresi yazmıyordu — tek çıkış e-postaydı. */}
            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <a href={`mailto:${COMPANY.email}`} className="btn-primary">{COMPANY.email}</a>
              <a href={`tel:${COMPANY.phone.replace(/\s/g, '')}`} className="btn-ghost">{COMPANY.phone}</a>
              <Link to="/download" className="btn-ghost">
                {t('ortak.indirDugmesi')} <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
            <p className="mt-4 text-xs text-muted">
              {t('destek.yardim.saatler')}
            </p>
          </div>
        </div>
      </section>
    </>
  )
}
