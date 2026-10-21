/**
 * Dil düğmesi (Y161; YH B4) — üst menü, mobil menü ve alt bilgide. İngilizce bayrağı KAPALIYKEN HİÇ ÇİZİLMEZ (Türkçe site göçten önceki gibi).
 * Düğme GEÇİLECEK dili kendi adıyla gösterir (Türkçe sayfada "English", İngilizce sayfada "Türkçe"; görünen ad `lang` o dilde);
 * erişilebilir adı sayfa dilinde "Dili değiştir: English" / "Change language: Türkçe". Klavyeyle odaklanır (görünür odak halkası).
 */
import { useTranslation } from 'react-i18next'
import { dilSec, dilSecimiGorunur, type Dil } from '../i18n'

export default function DilDugmesi({ className = '', testId = 'dil-dugmesi' }: { className?: string; testId?: string }) {
  const { t, i18n } = useTranslation()
  if (!dilSecimiGorunur()) return null
  const hedef: Dil = i18n.language === 'en' ? 'tr' : 'en'
  return (
    <button
      type="button"
      onClick={() => void dilSec(hedef)}
      aria-label={t('ortak.dil.dugmeEtiketi')}
      data-testid={testId}
      className={`grid h-9 min-w-9 place-items-center rounded-md px-3 text-xs font-bold text-muted ring-1 ring-border hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${className}`}
    >
      <span lang={hedef}>{t('ortak.dil.dugme')}</span>
    </button>
  )
}
