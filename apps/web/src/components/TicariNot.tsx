/**
 * YH B6 — fiyat / ödeme sayfalarında İNGİLİZCE metin için "bağlayıcı metin Türkçedir" notu (yasal sayfalardaki `yasal.kabuk.baglayici`
 * deseni). Türkçede HİÇ çizilmez (Türkçe sayfa eskisi gibi). Fiyat kuralı, tutarlar ve ödeme akışı DEĞİŞMEZ — yalnız not.
 */
import { useTranslation } from 'react-i18next'

export default function TicariNot({ className = '' }: { className?: string }) {
  const { t, i18n } = useTranslation()
  if (i18n.language !== 'en') return null
  return (
    <p data-testid="ticari-not" className={`rounded-md border border-border/60 px-3 py-2 text-xs text-muted ${className}`}>
      {t('fiyat.ticariBaglayici')}
    </p>
  )
}
