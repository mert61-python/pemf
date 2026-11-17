/**
 * KP-8 · src/pages/Download.tsx · Home.tsx · components/PackageBuilder.tsx kalan dallar — sunucu tarafı çizim (ticari-12d-ucretli-P1
 * deseni; oturum bağlamları sahte). SATIŞ AÇIK (FREE_MODE=false) + bir profil modülü PLANA DAHİL DEĞİL (ücretli eklenti) sahtelenir:
 *  - Ödeme dönüşü (`?checkout=success`) indirme sayfasının üstünde "aboneliğiniz başladı" bandı görünür; dönüş yoksa bant YOK.
 *  - Dahil olmayan modül: indirme ve ana sayfa kartında "aylık +₺X ek", paket oluşturucuda "aylık eklenti +₺X" (DAHİL yazmaz).
 */
import { describe, expect, it, vi } from 'vitest'

const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    session: null, email: null, ready: true, loading: false,
    signOut: () => {}, signIn: async () => ({}), signUp: async () => ({}), resetPassword: async () => ({}),
  }),
  AuthProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../../context/AuthModal', () => ({
  useAuthModal: () => ({ requireAuth: () => {} }),
  AuthModalProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../../config', async (orijinal) => {
  const o = await orijinal<typeof import('../../config')>()
  return {
    ...o,
    FREE_MODE: false,
    // son modül ücretli eklenti olsun (getter'lar korunur: nesne kopyalanmaz, vekille yalnız `included` ezilir)
    MODULES: o.MODULES.map((m, i) =>
      i === o.MODULES.length - 1 ? new Proxy(m, { get: (h, k) => (k === 'included' ? false : Reflect.get(h, k)) }) : m,
    ),
  }
})

const i18n = (await import('../../i18n')).default
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const Download = (await import('../Download')).default
const Home = (await import('../Home')).default
const PackageBuilder = (await import('../../components/PackageBuilder')).default
const { MODULES } = await import('../../config')
const { tl } = await import('../../lib/para')

const ciz = (bilesen: unknown, konum = '/') =>
  renderToString(createElement(MemoryRouter, { initialEntries: [konum] }, createElement(bilesen as never)))
const duz = (html: string) => html.replace(/<!-- -->/g, '').replace(/&#x27;/g, "'").replace(/&amp;/g, '&')

describe('satış açık · ücretli eklenti modülü', () => {
  const ek = MODULES[MODULES.length - 1]

  it('ödeme dönüşünde indirme sayfası "abonelik başladı" bandı; dönüş yoksa yok', () => {
    expect(duz(ciz(Download, '/download?checkout=success'))).toContain(i18n.t('indirme.abonelikBasladi'))
    expect(duz(ciz(Download, '/download'))).not.toContain(i18n.t('indirme.abonelikBasladi'))
  })

  it('dahil olmayan modül: indirme + ana sayfada "aylık ek", paket oluşturucuda "aylık eklenti +₺X"', () => {
    expect(ek.included).toBe(false)
    const ekMetni = i18n.t('ana.ekAylik', { addonMonthly: ek.addonMonthly })
    expect(duz(ciz(Download, '/download'))).toContain(ekMetni)
    expect(duz(ciz(Home))).toContain(ekMetni)
    expect(duz(ciz(PackageBuilder))).toContain(i18n.t('indirme.paket.aylikEklentiEk', { tutar: tl(ek.addonMonthly) }))
  })
})
