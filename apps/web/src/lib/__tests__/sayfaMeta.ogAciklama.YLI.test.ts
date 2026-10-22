/**
 * YLI-A1.2 (YLI bağımsız inceleme) — YH B2 Türkçe Open Graph / Twitter AÇIKLAMASINI sessizce değiştirdi.
 * `index.html`'deki statik (JS öncesi; paylaşım önizlemesi betik koşturmayan tüketicide BUNU görür) TR og:description / twitter:description
 * "PEMF Vet'i indirin; uygulama, yapay zekâ modelleri ve güncellemeler sizin için kurulur." iken B2'nin `metaUygula`'sı JS koşunca ikisini
 * `ortak.sayfa.aciklama`ya (sayfa açıklaması — başka metin) çeviriyor; TR'de JS öncesi ≠ sonrası (YH'nin kendi ilkesi başlıkta "JS öncesi =
 * sonrası"). EN paylaşım metni ayrı bir İngilizce karşılık almalı.
 * Yer: apps/web/src/lib/__tests__/ (kalıcı kapı adayı). Gerçek katalog + gerçek `metaUygula`; yalnız belge sahte.
 */
import { describe, expect, it } from 'vitest'
import { EN, TR } from '../../__tests__/_kaynakMetni'
import INDEX_HTML from '../../../index.html?raw'
import { type MetaBelgesi, type MetaOgesi, metaUygula, sayfaMetasiHesapla } from '../sayfaMeta'

function cevirmen(k: Record<string, string>) {
  return (anahtar: string, s?: Record<string, unknown>) => {
    const v = k[anahtar]
    if (v === undefined) throw new Error(`katalogda yok: ${anahtar}`)
    return v.replace(/\{\{\s*(\w+)\s*\}\}/g, (_x, ad: string) => String(s?.[ad] ?? ''))
  }
}

class Oge implements MetaOgesi {
  n = new Map<string, string>()
  ad: string
  private bas: Bas
  constructor(ad: string, bas: Bas) {
    this.ad = ad
    this.bas = bas
  }
  setAttribute(a: string, d: string) {
    this.n.set(a, d)
  }
  remove() {
    this.bas.ogeler = this.bas.ogeler.filter((o) => o !== this)
  }
}
class Bas {
  ogeler: Oge[] = []
  private uyar(o: Oge, s: string) {
    const m = /^(\w+)((?:\[[^\]]+\])+)$/.exec(s)
    if (!m || m[1] !== o.ad) return false
    return [...m[2].matchAll(/\[([\w:-]+)(?:="([^"]*)")?\]/g)].every(([, a, d]) => (d === undefined ? o.n.has(a) : o.n.get(a) === d))
  }
  querySelector(s: string) {
    return this.ogeler.find((o) => this.uyar(o, s)) ?? null
  }
  querySelectorAll(s: string) {
    return this.ogeler.filter((o) => this.uyar(o, s))
  }
  appendChild(o: Oge) {
    this.ogeler.push(o)
  }
}
function uygula(yol: string, dil: 'tr' | 'en') {
  const head = new Bas()
  const b = { title: '', head, createElement: (ad: string) => new Oge(ad, head) }
  const k = dil === 'tr' ? TR : EN
  metaUygula(b as unknown as MetaBelgesi, sayfaMetasiHesapla(yol, dil, cevirmen(k), () => undefined))
  return (s: string) => head.querySelector(s)?.n.get('content')
}
const statik = (ozellik: string) =>
  new RegExp(`(?:property|name)="${ozellik.replace(':', '\\:')}"\\s+content="([^"]*)"`).exec(INDEX_HTML)?.[1]

describe('YLI-A1.2 · Open Graph / Twitter açıklaması', () => {
  it('TR: og:description ve twitter:description JS sonrası index.html (JS öncesi) ile BİREBİR', () => {
    const ogStatik = statik('og:description')
    const twStatik = statik('twitter:description')
    expect(ogStatik).toBeTruthy()
    expect(twStatik).toBe(ogStatik)
    for (const yol of ['/', '/features', '/pricing']) {
      const d = uygula(yol, 'tr')
      expect(d('meta[property="og:description"]')).toBe(ogStatik)
      expect(d('meta[name="twitter:description"]')).toBe(twStatik)
    }
  })

  it('EN: paylaşım açıklaması İngilizce (Türkçe harf yok) ve sayfa açıklamasından ayrı anahtar', () => {
    const d = uygula('/', 'en')
    const og = d('meta[property="og:description"]')
    expect(og).toBeTruthy()
    expect(og).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/)
    expect(og).not.toBe(statik('og:description'))
    expect(d('meta[name="twitter:description"]')).toBe(og)
    // meta description (arama motoru) sayfa açıklaması olarak kalır
    expect(d('meta[name="description"]')).toBe(EN['ortak.sayfa.aciklama'])
  })
})
