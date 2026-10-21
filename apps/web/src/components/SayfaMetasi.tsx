/**
 * Sayfa başlığı / açıklama / Open Graph / Twitter / canonical / hreflang — yol ya da dil değişince etkin dile göre yazılır (YH B2 / B3;
 * hesap `lib/sayfaMeta.ts`). Hiçbir şey çizmez. Meta yazılamazsa sayfa yine çalışır (sessiz).
 */
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LEGAL_DOCS } from '../config'
import { gecerliDil } from '../i18n'
import { type Cevir, type MetaBelgesi, metaUygula, sayfaMetasiHesapla } from '../lib/sayfaMeta'

export default function SayfaMetasi() {
  const { pathname } = useLocation()
  const { t, i18n } = useTranslation()
  useEffect(() => {
    try {
      // anahtarlar sayfaMeta.ts'te SABİT (K-3 görür); tür daraltması yalnız imza uyumu için
      const cevir = t as unknown as Cevir
      const m = sayfaMetasiHesapla(pathname, gecerliDil(i18n.language) ?? 'tr', cevir, (slug) =>
        LEGAL_DOCS.find((d) => d.slug === slug)?.title,
      )
      metaUygula(document as unknown as MetaBelgesi, m)
    } catch {
      /* yok say: statik index.html metası kalır */
    }
  }, [pathname, i18n.language, t])
  return null
}
