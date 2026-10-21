/**
 * YH B2 — sayfa başlığı + açıklama + Open Graph / Twitter etkin dilde; her sayfanın kendi başlığı iki dilde. Saf hesap gerçek kataloglarla;
 * DOM uygulayıcı sahte belgeyle.
 */
import { describe, expect, it } from 'vitest'
import { EN, TR } from '../../__tests__/_kaynakMetni'
import APP_SRC from '../../App.tsx?raw'
import INDEX_HTML from '../../../index.html?raw'
import { BILINEN_YOLLAR, type MetaBelgesi, type MetaOgesi, SITE_KOKU, metaUygula, sayfaMetasiHesapla } from '../sayfaMeta'

const YASAL: Record<string, string> = {
  'mesafeli-satis': 'icerik.yasal.mesafeliSatis',
  'on-bilgilendirme': 'icerik.yasal.onBilgilendirme',
  'iptal-iade': 'icerik.yasal.iptalIade',
  kvkk: 'hesap.kayit.kvkk',
  gizlilik: 'hesap.kayit.gizlilik',
  'cerez-politikasi': 'icerik.yasal.cerez',
  'kullanim-sartlari': 'hesap.kayit.kullanimSartlari',
}

/** Katalogdan i18next benzeri çevirmen (yalnız `{{ad}}` yer tutucusu). Eksik anahtar HATA (KATI). */
function cevirmen(k: Record<string, string>) {
  return (anahtar: string, s?: Record<string, unknown>) => {
    const v = k[anahtar]
    if (v === undefined) throw new Error(`katalogda yok: ${anahtar}`)
    return v.replace(/\{\{\s*(\w+)\s*\}\}/g, (_x, ad: string) => String(s?.[ad] ?? ''))
  }
}
const yasalBaslik = (k: Record<string, string>) => (slug: string) => (YASAL[slug] ? k[YASAL[slug]] : undefined)
const hesap = (yol: string, dil: 'tr' | 'en') => {
  const k = dil === 'tr' ? TR : EN
  return sayfaMetasiHesapla(yol, dil, cevirmen(k), yasalBaslik(k))
}
const statikBaslik = /<title>([^<]*)<\/title>/.exec(INDEX_HTML)?.[1]

describe('B2 · sayfa başlığı iki dilde', () => {
  const yollar = [...BILINEN_YOLLAR, ...Object.keys(YASAL).map((s) => `/${s}`)]

  it('ana sayfa: TR başlık index.html ile BİREBİR (JS öncesi = sonrası); EN genel başlık', () => {
    expect(statikBaslik).toBeTruthy()
    expect(hesap('/', 'tr').baslik).toBe(statikBaslik)
    expect(hesap('/', 'en').baslik).toBe(EN['ortak.sayfa.baslik'])
  })

  it('her alt sayfanın KENDİ başlığı var (iki dilde, ana başlıktan ve birbirinden farklı — eş yollar hariç)', () => {
    for (const dil of ['tr', 'en'] as const) {
      const basliklar = new Map<string, string>()
      for (const y of yollar.filter((y) => y !== '/')) {
        const b = hesap(y, dil).baslik
        expect(b).toMatch(/ — PEMF Vet$/)
        expect(b).not.toBe(hesap('/', dil).baslik)
        basliklar.set(y, b)
      }
      const essiz = new Set(basliklar.values())
      // eş yollar: /login = /giris · /register = /kayit · /forgot = /sifremi-unuttum
      expect(essiz.size).toBe(basliklar.size - 3)
    }
  })

  it('İngilizce başlıkta Türkçe harf yok; Türkçe başlık Türkçe', () => {
    for (const y of yollar) expect(hesap(y, 'en').baslik).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/)
    expect(hesap('/features', 'tr').baslik).toBe('Özellikler — PEMF Vet')
    expect(hesap('/features', 'en').baslik).toBe('Features — PEMF Vet')
    expect(hesap('/kvkk', 'en').baslik).toBe(`${EN['hesap.kayit.kvkk']} — PEMF Vet`)
  })

  it('bilinmeyen yol: "Sayfa bulunamadı — PEMF Vet" / "Page not found — PEMF Vet"; adres ana sayfa', () => {
    expect(hesap('/yok-boyle', 'tr').baslik).toBe(`${TR['bulunamadi.baslik']} — PEMF Vet`)
    expect(hesap('/yok-boyle', 'en').baslik).toBe(`${EN['bulunamadi.baslik']} — PEMF Vet`)
    expect(hesap('/yok-boyle', 'en').adres).toBe(`${SITE_KOKU}/`)
  })

  it('açıklama ve Open Graph yereli etkin dilde', () => {
    expect(hesap('/pricing', 'tr').aciklama).toBe(TR['ortak.sayfa.aciklama'])
    expect(hesap('/pricing', 'en').aciklama).toBe(EN['ortak.sayfa.aciklama'])
    expect([hesap('/', 'tr').ogLocale, hesap('/', 'tr').ogLocaleDiger]).toEqual(['tr_TR', 'en_US'])
    expect([hesap('/', 'en').ogLocale, hesap('/', 'en').ogLocaleDiger]).toEqual(['en_US', 'tr_TR'])
  })
})

describe('B2 · yapı', () => {
  it('App bileşeni meta yazıcıyı yönlendirici içinde ÇİZER (yol değişince çalışsın)', () => {
    expect(APP_SRC).toMatch(/import SayfaMetasi from '\.\/components\/SayfaMetasi'/)
    expect(APP_SRC).toMatch(/<SayfaMetasi \/>/)
  })

  it('BILINEN_YOLLAR = App.tsx rotaları (yasal belgeler ve * hariç) — yeni rota eklenince burası da', () => {
    const rotalar = [...APP_SRC.matchAll(/<Route path="([^"]+)"/g)].map((m) => m[1]).filter((p) => p !== '*')
    expect(new Set(rotalar)).toEqual(new Set(BILINEN_YOLLAR))
  })

  it('index.html (JS öncesi / betiksiz tarayıcı) Türkçe varsayılan kalır', () => {
    expect(INDEX_HTML).toContain('<html lang="tr">')
    expect(INDEX_HTML).toContain('<meta property="og:locale" content="tr_TR" />')
  })
})

// ── sahte belge (DOM yok — vitest node ortamı) ──────────────────────────────────────────────────────────────────
class Oge implements MetaOgesi {
  nitelik = new Map<string, string>()
  ad: string
  private ebeveyn: Bas
  constructor(ad: string, ebeveyn: Bas) {
    this.ad = ad
    this.ebeveyn = ebeveyn
  }
  setAttribute(a: string, d: string) {
    this.nitelik.set(a, d)
  }
  remove() {
    this.ebeveyn.ogeler = this.ebeveyn.ogeler.filter((o) => o !== this)
  }
}
class Bas {
  ogeler: Oge[] = []
  private uyan(o: Oge, secici: string): boolean {
    const m = /^(\w+)((?:\[[^\]]+\])+)$/.exec(secici)
    if (!m || m[1] !== o.ad) return false
    return [...m[2].matchAll(/\[([\w:-]+)(?:="([^"]*)")?\]/g)].every(([, a, d]) =>
      d === undefined ? o.nitelik.has(a) : o.nitelik.get(a) === d,
    )
  }
  querySelector(s: string) {
    return this.ogeler.find((o) => this.uyan(o, s)) ?? null
  }
  querySelectorAll(s: string) {
    return this.ogeler.filter((o) => this.uyan(o, s))
  }
  appendChild(o: Oge) {
    this.ogeler.push(o)
  }
}
function sahteBelge() {
  const head = new Bas()
  const b = { title: 'eski', head, createElement: (ad: string) => new Oge(ad, head) }
  return b as typeof b & MetaBelgesi
}
const deger = (b: ReturnType<typeof sahteBelge>, s: string, a = 'content') => b.head.querySelector(s)?.nitelik.get(a)

describe('B2 · metaUygula (sahte belge)', () => {
  it('başlık + açıklama + og + twitter + canonical yazılır; ikinci yazım etiket ÇOĞALTMAZ', () => {
    const b = sahteBelge()
    metaUygula(b, hesap('/features', 'tr'))
    metaUygula(b, hesap('/features', 'en'))
    expect(b.title).toBe('Features — PEMF Vet')
    expect(deger(b, 'meta[name="description"]')).toBe(EN['ortak.sayfa.aciklama'])
    expect(deger(b, 'meta[property="og:title"]')).toBe('Features — PEMF Vet')
    expect(deger(b, 'meta[property="og:description"]')).toBe(EN['ortak.sayfa.aciklama'])
    expect(deger(b, 'meta[property="og:locale"]')).toBe('en_US')
    expect(deger(b, 'meta[property="og:locale:alternate"]')).toBe('tr_TR')
    expect(deger(b, 'meta[property="og:url"]')).toBe(`${SITE_KOKU}/features`)
    expect(deger(b, 'meta[name="twitter:title"]')).toBe('Features — PEMF Vet')
    expect(deger(b, 'meta[name="twitter:description"]')).toBe(EN['ortak.sayfa.aciklama'])
    expect(deger(b, 'link[rel="canonical"]', 'href')).toBe(`${SITE_KOKU}/features`)
    expect(b.head.ogeler.filter((o) => o.ad === 'meta')).toHaveLength(8)
  })
})
