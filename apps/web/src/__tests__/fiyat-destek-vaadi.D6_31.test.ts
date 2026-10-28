// Author: mertaygn, cglrgrkn
/**
 * D6.31 (B-7.1 · B-7.15) — fiyat sayfası kaldırılan "Anında analiz" vaadini ÇİZMEZ; destek sayfasının yanıt süresi plan karşılaştırmasıyla ÇELİŞMEZ.
 *
 * 🔴 ÖLÇÜLEN (HEAD ebf1c3fe):
 *  (1) `config.ts:465` Pro+ `get badge() { return i18n.t('icerik.plan.proPlus.rozet') }` → `icerik.json` "Anında analiz" / "Instant analysis";
 *      `pages/Pricing.tsx:174-177` rozeti Pro+ kartının üstüne `<Bolt/>` ile çiziyordu. Hız / kuyruk vaadi 2026-08-20'de kaldırıldı (config.ts:345-350
 *      notu); ödeme sayfasındaki ikizi 8. partide silinmişti (`kullandikca-ode.test.ts:115`), fiyat kartındaki kaldı (yokluk kapısı onu BİLEREK
 *      dışarıda bırakmıştı — "12c [İNCELE]").
 *  (2) `pages/Support.tsx:44,:56` "en geç BİR iş günü içinde dönüş" ↔ `config.ts:605` COMPARE "Destek yanıt süresi": Başlangıç "2 iş günü".
 *      Ücretsiz plandaki kullanıcıya sayfa, plan tablosunun verdiğinden hızlı yanıt vaat ediyordu. Çelişkide KÜÇÜK (gerçek) vaat söylenir.
 *
 * ÖLÇÜT: GERÇEK sayfalar sunucu tarafı çizilir (Türkçe ve bayrak açık İngilizce); metin ÇİZİLEN HTML'den okunur (yorum / ölü dizge sayılmaz).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true
const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ session: null, email: null, ready: true, loading: false, signOut: () => {} }),
  AuthProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../context/AuthModal', () => ({
  useAuthModal: () => ({ requireAuth: () => {} }),
  AuthModalProvider: ({ children }: { children: unknown }) => children,
}))

const i18nMod = await import('../i18n')
const dilMod = await import('../i18n/dil')
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const Pricing = (await import('../pages/Pricing')).default
const Support = (await import('../pages/Support')).default
const Home = (await import('../pages/Home')).default
const { COMPARE, PLANS } = await import('../config')

afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

async function dil(d: 'tr' | 'en') {
  dilMod.__bayrakTestiAyarla(d === 'en')
  await i18nMod.dilSec(d)
}

function metin(bilesen: unknown, adres = '/'): string {
  const html = renderToString(createElement(MemoryRouter, { initialEntries: [adres] }, createElement(bilesen as never)))
  return html.replace(/<!--.*?-->/g, '').replace(/<[^>]+>/g, ' ').replace(/&#x27;/g, "'").replace(/&amp;/g, '&').replace(/\s+/g, ' ')
}

const HIZ_VAADI_TR = /anında analiz|anında sonuç|öncelikli işlem|kuyrukta beklemeden/i
const HIZ_VAADI_EN = /instant analys[ie]s|instant results?|priority processing|without queu/i

describe('D6.31 (1) · "Anında analiz" vaadi hiçbir plan kartında çizilmez', () => {
  it('KRİTİK (TR): fiyat sayfası ve ana sayfa çiziminde hız vaadi YOK', async () => {
    await dil('tr')
    for (const [ad, s] of [['Pricing', metin(Pricing, '/pricing')], ['Home', metin(Home)]] as const) {
      expect(s, `${ad}: çizilen sayfada kaldırılan hız vaadi`).not.toMatch(HIZ_VAADI_TR)
    }
  })
  it('KRİTİK (EN): aynı sayfalar İngilizcede de hız vaadi çizmez', async () => {
    await dil('en')
    for (const [ad, s] of [['Pricing', metin(Pricing, '/pricing')], ['Home', metin(Home)]] as const) {
      expect(s, `${ad} EN: çizilen sayfada kaldırılan hız vaadi`).not.toMatch(HIZ_VAADI_EN)
    }
  })
  it('KRİTİK: PLANS[*] (rozet dahil, sayfaya hangi yoldan gelirse gelsin) hız vaadi taşımaz', async () => {
    for (const d of ['tr', 'en'] as const) {
      await dil(d)
      for (const p of PLANS) {
        const hepsi = [p.badge ?? '', p.jetonHakki, p.desc, ...p.features].join(' ')
        expect(hepsi, `${d} · ${p.tier}`).not.toMatch(d === 'tr' ? HIZ_VAADI_TR : HIZ_VAADI_EN)
      }
    }
  })
})

/** Metindeki destek yanıt süreleri (iş günü) — "aynı iş günü" = 0. */
function isGunleri(s: string): number[] {
  const SAYI: Record<string, number> = { aynı: 0, same: 0, bir: 1, one: 1, iki: 2, two: 2, üç: 3, three: 3 }
  const g: number[] = []
  for (const m of s.matchAll(/(\d+|aynı|bir|iki|üç|same|one|two|three)\s+(?:iş günü|business days?)/gi)) {
    const k = m[1].toLowerCase()
    g.push(/^\d+$/.test(k) ? Number(k) : SAYI[k])
  }
  return g
}

describe('D6.31 (2) · destek sayfasının yanıt süresi plan karşılaştırmasıyla çelişmez', () => {
  for (const d of ['tr', 'en'] as const) {
    it(`KRİTİK (${d}): destek sayfasının vaat ettiği süre, COMPARE'deki EN UZUN plan süresinden kısa değil`, async () => {
      await dil(d)
      const satir = COMPARE.find((c) => /destek|support/i.test(c.label))
      expect(satir, 'COMPARE "Destek yanıt süresi" satırı yok — kapı bayat').toBeDefined()
      const planlar = Object.values(satir!.values).flatMap(isGunleri)
      expect(planlar.length, 'COMPARE süreleri okunamadı').toBeGreaterThanOrEqual(3)
      const enUzun = Math.max(...planlar)
      // Yalnız GENEL destek vaadi (iletişim kartı) ölçülür: SSS'teki plana-özel süreler (Pro 1 gün, Pro+ aynı gün) COMPARE'le aynıdır.
      const sayfa = metin(Support, '/support')
      const kart = sayfa.indexOf(i18nMod.default.t('destek.yardim.baslik'))
      expect(kart, 'destek sayfasında iletişim kartı başlığı yok — kapı bayat').toBeGreaterThan(-1)
      const destek = isGunleri(sayfa.slice(kart))
      expect(destek.length, 'destek sayfası yanıt süresi söylemiyor').toBeGreaterThan(0)
      for (const g of destek) {
        expect(g, `destek sayfası "${g} iş günü" diyor; ücretsiz plan tablosu ${enUzun} iş günü (Başlangıç) — sayfa plan tablosundan hızlı yanıt vaat edemez`).toBeGreaterThanOrEqual(enUzun)
      }
    })
  }
})
