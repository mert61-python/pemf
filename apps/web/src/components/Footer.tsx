// Author: mertaygn, cglrgrkn
import { Link } from 'react-router-dom'
import { BRAND, COMPANY, LEGAL_DOCS, MEDICAL_DISCLAIMER, NAV } from '../config'
import { Logo } from './Icons'
import { useTranslation } from 'react-i18next'

export default function Footer() {
  const { t } = useTranslation()
  return (
    <footer className="border-t border-border/70">
      <div className="mx-auto max-w-6xl 2xl:max-w-7xl px-5 py-12 sm:px-6">
        <div className="flex flex-col gap-8 md:flex-row md:justify-between">
          {/* Marka + satıcı kimliği (yasal zorunlu — 6563 sy. Kanun) */}
          <div className="max-w-sm">
            <div className="flex items-center gap-2.5">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/15 text-primary ring-1 ring-primary/25">
                <Logo className="h-4.5 w-4.5" />
              </span>
              <div className="text-sm font-bold">{BRAND.name}</div>
            </div>
            <div className="mt-3 space-y-0.5 text-xs leading-relaxed text-muted">
              <div className="font-medium text-fg/80">{COMPANY.legalName}</div>
              <div>{COMPANY.address}, {COMPANY.city}</div>
              {/* Telefon YOKSA hiç gösterilmez — boş "Tel:" satırı kırık görünür (2026-08-07). */}
              <div>{COMPANY.phone ? t('ortak.altBilgi.tel', { telefon: COMPANY.phone }) : ""}{COMPANY.email}</div>
              <div>{t('ortak.altBilgi.vergiDairesi')}{COMPANY.taxOffice}{t('ortak.altBilgi.vkn')}{COMPANY.taxNo}</div>
              <div>{t('ortak.altBilgi.mersis')}{COMPANY.mersis}</div>
            </div>
          </div>

          {/* Menü + Yasal bağlantılar */}
          {/* [W adım 9 / site-16] Bağlantı yüksekliği 44 px (.tap); satır aralığı `gap-y-0` ile
              telafi edildi → altbilgi görsel olarak büyümüyor. */}
          {/* [W adım 10 / site-16] 320 px'te iki sütun her birine 120 px bırakıyor ve
              "İptal, İade ve Cayma Hakkı" üç satıra sarıyordu. 400 px altında tek sütun. */}
          <div className="grid grid-cols-1 gap-y-6 text-sm text-muted min-[400px]:grid-cols-2 min-[400px]:gap-x-6 min-[400px]:gap-y-0 sm:gap-x-10">
            <div className="flex flex-col">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg/60">{t('ortak.menu')}</div>
              {NAV.map((n) => (
                <Link key={n.to} to={n.to} className="tap hover:text-fg">{t(n.anahtar)}</Link>
              ))}
            </div>
            <div className="flex flex-col">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg/60">{t('ortak.altBilgi.yasal')}</div>
              {LEGAL_DOCS.map((d) => (
                <Link key={d.slug} to={`/${d.slug}`} className="tap hover:text-fg">{d.title}</Link>
              ))}
            </div>
          </div>
        </div>

        {/* Tıbbi/veteriner sorumluluk uyarısı */}
        <p className="mt-8 rounded-lg border border-border/60 bg-bg-soft/40 px-4 py-3 text-xs leading-relaxed text-muted">
          {MEDICAL_DISCLAIMER}
        </p>

        <div className="mt-6 text-xs text-muted">
          © {BRAND.year} {COMPANY.legalName}{t('ortak.altBilgi.haklar')}
        </div>
      </div>
    </footer>
  )
}
