// Author: mertaygn, cglrgrkn
/**
 * D6.30 (B-7.6) — yıllık + Araştırma'da "Aylık eşdeğeri" O AN TAHSİL EDİLEN dönem bedeliyle tutarlı (×12 farkı ≤ 12 TL, yuvarlama payı).
 *
 * 🔴 ÖLÇÜLEN (HEAD ebf1c3fe): `Odeme.tsx:56` `total = monthly + RESEARCH_ADDON.monthly` — yıllıkta eklentinin AYLIK tarifesi (₺390) ekleniyordu,
 * oysa tahsil edilen yıllık bedel eklentiyi de "2 ay bedava" ile katar (`RESEARCH_ADDON.yearly` ₺3.900). Pro yıllık + Araştırma: ekranda
 * "Aylık eşdeğeri ₺1.215/ay" (× 12 = ₺14.580) ↔ "Bugün tahsil edilecek ₺13.800/yıl" → ₺780 çelişki (ön bilgilendirme ekranında).
 *
 * ÖLÇÜT: GERÇEK `Odeme` sayfası sunucu tarafı çizilir (satış AÇIK sahtesi — `FREE_MODE: false`, ticari-12d-ucretli deseni); ekrandaki iki tutar
 * çizilen METİNDEN okunur. Ayrıca ekranın hata yolu `odemeBaslatmaHatasi`ndan geçer (D6.30 a kolu; zincir `api/_lib/__tests__/
 * odeme-baslatma-hatasi.D6_30.test.ts`).
 */
import { describe, expect, it, vi } from 'vitest'
import ts from 'typescript'
import ODEME_SRC from '../Odeme.tsx?raw'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true
const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ session: null, email: null, ready: true, loading: false, signOut: () => {} }),
  AuthProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../../context/AuthModal', () => ({
  useAuthModal: () => ({ requireAuth: () => {} }),
  AuthModalProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../../config', async (orijinal) => ({
  ...(await orijinal<typeof import('../../config')>()),
  FREE_MODE: false, // satış AÇIK sahtesi: ödeme özeti çizilsin
}))

await import('../../i18n')
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const Odeme = (await import('../Odeme')).default
const { PLANS, RESEARCH_ADDON } = await import('../../config')

function duzMetin(adres: string): string {
  const html = renderToString(createElement(MemoryRouter, { initialEntries: [adres] }, createElement(Odeme)))
  return html.replace(/<!--.*?-->/g, '').replace(/<[^>]+>/g, '\u0001').replace(/&#x27;/g, "'").replace(/&amp;/g, '&')
}

/** Etiketten sonraki İLK `₺…` tutarı (tr-TR biçimi: nokta binlik ayırıcı). */
function tutar(metin: string, etiket: string): number | null {
  const i = metin.indexOf(etiket)
  if (i < 0) return null
  const m = /₺\s?([\d.]+)/.exec(metin.slice(i + etiket.length))
  return m ? Number(m[1].replace(/\./g, '')) : null
}

const DURUMLAR: [tier: 'pro' | 'pro_plus', research: boolean][] = [
  ['pro', true],
  ['pro_plus', true],
  ['pro', false],
  ['pro_plus', false],
]

describe('D6.30 · yıllık ödemede "Aylık eşdeğeri" × 12 ≈ tahsil edilen yıllık bedel', () => {
  for (const [tier, research] of DURUMLAR) {
    it(`KRİTİK: ${tier} yıllık${research ? ' + Araştırma' : ''} — |eşdeğer × 12 − tahsil| ≤ 12 TL`, () => {
      const metin = duzMetin(`/odeme?tier=${tier}&yearly=1&research=${research ? 1 : 0}`)
      const tahsil = tutar(metin, 'Bugün tahsil edilecek')
      const esdeger = tutar(metin, 'Aylık eşdeğeri')
      const plan = PLANS.find((p) => p.tier === tier)!
      // Tahsil tutarı tek kaynaktan (planın yıllığı + eklentinin yıllığı) — kapı ona çapalı, ekrandan değil.
      expect(tahsil, 'tahsil tutarı ekranda bulunamadı').toBe((plan.yearly ?? 0) + (research ? RESEARCH_ADDON.yearly : 0))
      expect(esdeger, '"Aylık eşdeğeri" ekranda bulunamadı').not.toBeNull()
      expect(
        Math.abs(esdeger! * 12 - tahsil!),
        `Aylık eşdeğeri ₺${esdeger} × 12 = ₺${esdeger! * 12} ↔ tahsil ₺${tahsil} (yıllık eklentide de "2 ay bedava" uygulanır)`,
      ).toBeLessThanOrEqual(12)
    })
  }

  it('KARŞIT: aylık ödemede "Aylık eşdeğeri" satırı YOK, tahsil = aylık plan + aylık eklenti', () => {
    const metin = duzMetin('/odeme?tier=pro&yearly=0&research=1')
    expect(metin).not.toContain('Aylık eşdeğeri')
    expect(tutar(metin, 'Bugün tahsil edilecek')).toBe((PLANS.find((p) => p.tier === 'pro')!.monthly ?? 0) + RESEARCH_ADDON.monthly)
  })
})

describe('D6.30 · ekranın hata yolu kodu korur (409 / alan-özel → katalog metni)', () => {
  it('submit hata dalı `odemeBaslatmaHatasi`na sunucunun kod / alan / sebep alanlarını geçirir; ham `odemeHatasiTurkce(error)` YOK', () => {
    const sf = ts.createSourceFile('Odeme.tsx', ODEME_SRC, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const cagrilar: ts.CallExpression[] = []
    const gez = (n: ts.Node): void => {
      if (ts.isCallExpression(n) && ts.isIdentifier(n.expression)) cagrilar.push(n)
      ts.forEachChild(n, gez)
    }
    gez(sf)
    const ad = (c: ts.CallExpression) => (c.expression as ts.Identifier).text
    expect(cagrilar.filter((c) => ad(c) === 'odemeHatasiTurkce'), 'ekran hatayı hâlâ ham sınıflandırıcıya sokuyor').toHaveLength(0)
    const yeni = cagrilar.filter((c) => ad(c) === 'odemeBaslatmaHatasi')
    expect(yeni).toHaveLength(1)
    const arg = yeni[0].arguments[0]
    expect(arg && ts.isObjectLiteralExpression(arg), 'odemeBaslatmaHatasi nesneyle çağrılmalı').toBe(true)
    const alanlar = (arg as ts.ObjectLiteralExpression).properties.map((p) => p.name?.getText(sf))
    for (const a of ['error', 'kod', 'alan', 'sebep']) expect(alanlar, `odemeBaslatmaHatasi({…}) içinde "${a}" yok`).toContain(a)
  })
})
