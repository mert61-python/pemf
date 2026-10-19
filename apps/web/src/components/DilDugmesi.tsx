/**
 * Üst menüdeki dil düğmesi (Y161) — İngilizce bayrağı KAPALIYKEN HİÇ ÇİZİLMEZ (Türkçe site göçten önceki gibi).
 * Düğme GEÇİLECEK dili gösterir (Türkçe sayfada "EN", İngilizce sayfada "TR"); erişilebilir adı hedef dili kendi dilinde söyler.
 */
import { useTranslation } from 'react-i18next'
import { dilSec, dilSecimiGorunur, type Dil } from '../i18n'

export default function DilDugmesi({ className = '' }: { className?: string }) {
  const { t, i18n } = useTranslation()
  if (!dilSecimiGorunur()) return null
  const hedef: Dil = i18n.language === 'en' ? 'tr' : 'en'
  return (
    <button
      type="button"
      onClick={() => void dilSec(hedef)}
      aria-label={t('ortak.dil.dugmeEtiketi')}
      data-testid="dil-dugmesi"
      className={`grid h-9 min-w-9 place-items-center rounded-md px-2 text-xs font-bold text-muted ring-1 ring-border hover:text-fg ${className}`}
    >
      {t('ortak.dil.dugme')}
    </button>
  )
}
