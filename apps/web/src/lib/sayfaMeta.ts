/**
 * SAYFA META (YH B2 / B3) — SPA: `index.html`'deki statik başlık / açıklama / Open Graph / Twitter etiketleri (Türkçe; JS'ten önce okunur,
 * DEĞİŞMEZ) her yol ve dil değişiminde ETKİN DİLE göre yeniden yazılır; her sayfanın kendi başlığı iki dilde ("Özellikler — PEMF Vet").
 * Dil bağlantıları (S-YH: `?lang=`): `<link rel="alternate" hreflang="tr|en|x-default">` + canonical / `og:url` o dildeki adres;
 * x-default = parametresiz adres (dili tarayıcı seçer — Y161). Bilinmeyen yolda (404) dil bağlantısı YOK, canonical ana sayfa.
 * Saf hesap (`sayfaMetasiHesapla`) ile DOM uygulayıcı (`metaUygula`) ayrı: testte sahte belge. i18n / config İÇE AKTARILMAZ (döngü yok):
 * çevirmen ve yasal belge başlığı çağırandan gelir.
 */
export const SITE_KOKU = 'https://pemf-vet-web.vercel.app'
export const DIL_PARAMETRESI = 'lang'

export type SayfaDili = 'tr' | 'en'
export type Cevir = (anahtar: string, secenek?: Record<string, unknown>) => string
export type DilBaglantisi = { hreflang: 'tr' | 'en' | 'x-default'; href: string }
export type SayfaMetasi = {
  baslik: string
  aciklama: string
  /** Paylaşım önizlemesi (og / twitter) açıklaması — TR = `index.html`'deki statik metin (JS öncesi = sonrası; YLI-A1.2). */
  ogAciklama: string
  ogLocale: string
  ogLocaleDiger: string
  adres: string
  alternatifler: DilBaglantisi[]
}

/** Uygulamanın bilinen (yasal belge dışı) yolları — `App.tsx` rotalarıyla aynı küme (kapı: sayfaMeta.test.ts). */
export const BILINEN_YOLLAR = [
  '/',
  '/features',
  '/pricing',
  '/download',
  '/support',
  '/odeme',
  '/login',
  '/giris',
  '/register',
  '/kayit',
  '/forgot',
  '/sifremi-unuttum',
  '/sifre-sifirla',
] as const

const OG_LOCALE: Record<SayfaDili, string> = { tr: 'tr_TR', en: 'en_US' }

export function yoluSadelestir(yol: string): string {
  const y = (yol || '/').split(/[?#]/)[0] || '/'
  return y.length > 1 ? y.replace(/\/+$/, '') || '/' : '/'
}

/** `dil` verilirse `?lang=<dil>`, verilmezse parametresiz (x-default) adres. */
export function dilAdresi(yol: string, dil?: SayfaDili): string {
  const y = yoluSadelestir(yol)
  return `${SITE_KOKU}${y}${dil ? `?${DIL_PARAMETRESI}=${dil}` : ''}`
}

/** Yol → sayfa başlığı (etkin dilde). Ana sayfa genel başlık; alt sayfa "<ad> — PEMF Vet"; bilinmeyen yol "Sayfa bulunamadı — PEMF Vet". */
export function sayfaBasligi(yol: string, t: Cevir, yasalBaslik: (slug: string) => string | undefined): string {
  const alt = (sayfa: string) => t('ortak.sayfa.alt', { sayfa })
  switch (yoluSadelestir(yol)) {
    case '/':
      return t('ortak.sayfa.baslik')
    case '/features':
      return alt(t('ortak.nav.ozellikler'))
    case '/pricing':
      return alt(t('ortak.nav.fiyatlandirma'))
    case '/download':
      return alt(t('ortak.nav.indir'))
    case '/support':
      return alt(t('ortak.nav.destek'))
    case '/odeme':
      return alt(t('ortak.sayfa.odeme'))
    case '/login':
    case '/giris':
      return alt(t('ortak.sayfa.giris'))
    case '/register':
    case '/kayit':
      return alt(t('ortak.sayfa.kayit'))
    case '/forgot':
    case '/sifremi-unuttum':
      return alt(t('ortak.sayfa.sifremiUnuttum'))
    case '/sifre-sifirla':
      return alt(t('hesap.sifirla.baslik'))
    default: {
      const yasal = yasalBaslik(yoluSadelestir(yol).slice(1))
      return alt(yasal ?? t('bulunamadi.baslik'))
    }
  }
}

export function sayfaMetasiHesapla(
  yol: string,
  dil: SayfaDili,
  t: Cevir,
  yasalBaslik: (slug: string) => string | undefined,
): SayfaMetasi {
  const y = yoluSadelestir(yol)
  const bilinen = (BILINEN_YOLLAR as readonly string[]).includes(y) || yasalBaslik(y.slice(1)) !== undefined
  return {
    baslik: sayfaBasligi(y, t, yasalBaslik),
    aciklama: t('ortak.sayfa.aciklama'),
    ogAciklama: t('ortak.sayfa.ogAciklama'),
    ogLocale: OG_LOCALE[dil],
    ogLocaleDiger: OG_LOCALE[dil === 'tr' ? 'en' : 'tr'],
    adres: bilinen ? dilAdresi(y, dil) : `${SITE_KOKU}/`,
    alternatifler: bilinen
      ? [
          { hreflang: 'tr', href: dilAdresi(y, 'tr') },
          { hreflang: 'en', href: dilAdresi(y, 'en') },
          { hreflang: 'x-default', href: dilAdresi(y) },
        ]
      : [],
  }
}

/** DOM'un kullanılan parçası (gerçek `document` ya da test belgesi). */
export type MetaBelgesi = {
  title: string
  head: {
    querySelector(secici: string): MetaOgesi | null
    querySelectorAll(secici: string): ArrayLike<MetaOgesi>
    appendChild(o: MetaOgesi): unknown
  }
  createElement(ad: string): MetaOgesi
}
export type MetaOgesi = { setAttribute(ad: string, deger: string): void; remove(): void }

function etiket(belge: MetaBelgesi, ad: 'meta' | 'link', anahtar: [string, string], deger: [string, string]): void {
  const secici = `${ad}[${anahtar[0]}="${anahtar[1]}"]`
  let o = belge.head.querySelector(secici)
  if (!o) {
    o = belge.createElement(ad)
    o.setAttribute(anahtar[0], anahtar[1])
    belge.head.appendChild(o)
  }
  o.setAttribute(deger[0], deger[1])
}

/** Hesaplanan metayı belgeye yazar (eksik etiket oluşturulur; eski dil bağlantıları silinip yeniden yazılır). */
export function metaUygula(belge: MetaBelgesi, m: SayfaMetasi): void {
  belge.title = m.baslik
  etiket(belge, 'meta', ['name', 'description'], ['content', m.aciklama])
  etiket(belge, 'meta', ['property', 'og:title'], ['content', m.baslik])
  etiket(belge, 'meta', ['property', 'og:description'], ['content', m.ogAciklama])
  etiket(belge, 'meta', ['property', 'og:locale'], ['content', m.ogLocale])
  etiket(belge, 'meta', ['property', 'og:locale:alternate'], ['content', m.ogLocaleDiger])
  etiket(belge, 'meta', ['property', 'og:url'], ['content', m.adres])
  etiket(belge, 'meta', ['name', 'twitter:title'], ['content', m.baslik])
  etiket(belge, 'meta', ['name', 'twitter:description'], ['content', m.ogAciklama])
  etiket(belge, 'link', ['rel', 'canonical'], ['href', m.adres])
  const eski = belge.head.querySelectorAll('link[rel="alternate"][hreflang]')
  for (let i = eski.length - 1; i >= 0; i--) eski[i].remove()
  for (const a of m.alternatifler) {
    const l = belge.createElement('link')
    l.setAttribute('rel', 'alternate')
    l.setAttribute('hreflang', a.hreflang)
    l.setAttribute('href', a.href)
    belge.head.appendChild(l)
  }
}
