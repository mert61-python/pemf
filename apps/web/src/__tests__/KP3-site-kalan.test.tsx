// Author: mertaygn, cglrgrkn
/**
 * KP-3 C · sitenin kalan olay işleyicileri / efektleri (AŞAMA 0 + C1–C3 sonrası 12 dosyada 46 satır) · GERÇEK bileşenler; sahte EN ALT katta
 * (Supabase `rpc`, `window.location`, `navigator`, zamanlayıcı):
 *  - Pricing: satın alma yönü (aylık / yıllık, araştırma eklentisi → /odeme adresi; ücretsiz dönemde indirmeye),
 *  - AuthRoute: hazır değilken sessiz, girişliyse ana sayfaya, girişsizse doğru sekmede pencere + düğme,
 *  - indirme kapısı: girişli doğrudan indirir, girişsiz pencere (geri çağrı indirir), okuma asılırsa 8 sn sonra kilit açılır, işletim
 *    sistemi algılanır, indirme sayfasının birincil ve Linux alt paket düğmeleri,
 *  - DownloadStats: hesap + aktif cihaz (toplam gösterilmez), sıfır / hata → bölüm yok, ayrılınca iptal,
 *  - AppScreenshots kaydırma · PackageBuilder seçimi · ErrorBoundary kurtarma ekranı · Menu simgesi · dil düğmesi.
 * Düzenek: KP2 mini çizici (KP2-AuthModal.test.tsx'teki blok, AYNEN).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as React from 'react'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true

// ═══ KP2 MİNİ ÇİZİCİ (KP-2 bileşen testlerinde aynı blok; her dosya kendi kopyasını taşır) ═══════════════════════════════════════
type Cikti = Dugum | string
type Dugum = { tip: string; props: Record<string, any>; cocuklar: Cikti[]; dom: Record<string, any> }
type Yuva = { d?: any; deps?: readonly unknown[]; ilk?: boolean; temizle?: () => void; ayar?: (e: unknown) => void }
type Ornek = { tip: unknown; yuvalar: Yuva[]; ziyaret: boolean; sinif?: any }
const IC = (React as unknown as Record<string, any>).__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE
const S = {
  frag: Symbol.for('react.fragment'),
  ctx: Symbol.for('react.context'),
  cons: Symbol.for('react.consumer'),
  memo: Symbol.for('react.memo'),
  fwd: Symbol.for('react.forward_ref'),
  sarma: [Symbol.for('react.strict_mode'), Symbol.for('react.profiler'), Symbol.for('react.suspense')],
}
const degisti = (a?: readonly unknown[], b?: readonly unknown[]) =>
  !a || !b || a.length !== b.length || a.some((x, j) => !Object.is(x, b[j]))
function varsayilanDom(tip: string): Record<string, any> {
  const d: Record<string, any> = {
    tip,
    odak: 0,
    childElementCount: 0,
    eklenen: [] as unknown[],
    clientWidth: 1000,
    focus() {
      d.odak++
    },
    contains: (x: unknown) => x === d,
    querySelectorAll: () => [],
    scrollBy: vi.fn(),
    appendChild(c: unknown) {
      d.eklenen.push(c)
      d.childElementCount++
      return c
    },
  }
  return d
}
export class MiniCizici {
  agac: Cikti[] = []
  kirli = false
  private kok: unknown = null
  private ornekler = new Map<string, Ornek>()
  private domlar = new Map<string, Record<string, any>>()
  private baglam = new Map<unknown, unknown[]>()
  private aktif: Ornek | null = null
  private i = 0
  private yerelY: (() => void)[] = []
  private yerelP: (() => void)[] = []
  private yerlesim: (() => void)[] = []
  private pasif: (() => void)[] = []
  private ciziliyor = false
  private planli = false
  private sayac = 0
  private domUret: (tip: string, yol: string) => Record<string, any>
  constructor(domUret?: (tip: string, yol: string) => Record<string, any>) {
    this.domUret = domUret ?? varsayilanDom
  }
  ciz(kok: unknown): this {
    this.kok = kok
    this.yenile()
    return this
  }
  yenile(): void {
    this.ciziliyor = true
    try {
      for (let tur = 0; tur < 60; tur++) {
        this.kirli = false
        this.yerlesim = []
        this.pasif = []
        for (const o of this.ornekler.values()) o.ziyaret = false
        this.agac = this.genislet(this.kok, 'k')
        for (const [yol, o] of [...this.ornekler]) {
          if (!o.ziyaret) {
            this.sok(o)
            this.ornekler.delete(yol)
          }
        }
        const y = this.yerlesim
        const p = this.pasif
        this.yerlesim = []
        this.pasif = []
        for (const f of y) f()
        for (const f of p) f()
        if (!this.kirli) return
      }
      throw new Error('mini çizici: çizim durulmadı (sonsuz güncelleme)')
    } finally {
      this.ciziliyor = false
    }
  }
  /** Tüm ağacı söker (efekt temizlikleri + componentWillUnmount). */
  sokHepsi(): void {
    for (const o of this.ornekler.values()) this.sok(o)
    this.ornekler.clear()
    this.agac = []
    this.kok = null
  }
  /** Mikro görevleri ve (gerçek saatte) bir makro görevi — setImmediate; Windows'ta setTimeout(0) ~15 ms — boşaltır; bekleyen durum değişimlerini çizer. */
  async bosalt(): Promise<void> {
    for (let tur = 0; tur < 8; tur++) {
      for (let j = 0; j < 20; j++) await Promise.resolve()
      if (!vi.isFakeTimers()) await new Promise((r) => (globalThis as any).setImmediate(r))
      if (this.kirli) this.yenile()
    }
  }
  async tikla(d: Dugum, ek: Record<string, unknown> = {}): Promise<Record<string, any>> {
    const e = olay({ target: d.dom, currentTarget: d.dom, ...ek })
    d.props.onClick(e)
    await this.bosalt()
    return e
  }
  async yaz(d: Dugum, deger: string): Promise<void> {
    d.props.onChange(olay({ target: { value: deger } }))
    await this.bosalt()
  }
  async isaretleKutu(d: Dugum, deger: boolean): Promise<void> {
    d.props.onChange(olay({ target: { checked: deger } }))
    await this.bosalt()
  }
  async gonder(d: Dugum): Promise<Record<string, any>> {
    const e = olay()
    d.props.onSubmit(e)
    await this.bosalt()
    return e
  }
  private sok(o: Ornek): void {
    for (const y of o.yuvalar) {
      if (typeof y?.temizle === 'function') {
        const t = y.temizle
        y.temizle = undefined
        t()
      }
    }
    o.sinif?.componentWillUnmount?.()
  }
  private isaretle(): void {
    this.kirli = true
    if (!this.ciziliyor && !this.planli) {
      this.planli = true
      queueMicrotask(() => {
        this.planli = false
        if (this.kirli) this.yenile()
      })
    }
  }
  private oku(ctx: any): unknown {
    const y = this.baglam.get(ctx)
    return y && y.length ? y[y.length - 1] : ctx._currentValue
  }
  private yuva(ilk: () => Yuva): Yuva {
    const o = this.aktif
    if (!o) throw new Error('mini çizici: kanca çizim dışında çağrıldı')
    const k = this.i++
    if (!o.yuvalar[k]) o.yuvalar[k] = ilk()
    return o.yuvalar[k]
  }
  private efekt(f: () => unknown, deps: readonly unknown[] | undefined, yerlesim: boolean): void {
    const y = this.yuva(() => ({ ilk: true }))
    if (!y.ilk && deps && !degisti(y.deps, deps)) return
    y.ilk = false
    y.deps = deps
    ;(yerlesim ? this.yerelY : this.yerelP).push(() => {
      if (typeof y.temizle === 'function') y.temizle()
      const s = f()
      y.temizle = typeof s === 'function' ? (s as () => void) : undefined
    })
  }
  private dagitici: Record<string, any> = {
    readContext: (c: unknown) => this.oku(c),
    useContext: (c: unknown) => this.oku(c),
    use: (u: any) => {
      if (u && u.$$typeof === S.ctx) return this.oku(u)
      if (u && u.status === 'fulfilled') return u.value
      throw new Error('mini çizici: use() yalnız bağlam / çözülmüş söz destekler')
    },
    useReducer: (indir: (d: unknown, e: unknown) => unknown, bas: unknown, ilk?: (b: unknown) => unknown) => {
      const y = this.yuva(() => {
        const yv: Yuva = { d: ilk ? ilk(bas) : bas }
        yv.ayar = (e: unknown) => {
          const yeni = indir(yv.d, e)
          if (!Object.is(yeni, yv.d)) {
            yv.d = yeni
            this.isaretle()
          }
        }
        return yv
      })
      return [y.d, y.ayar]
    },
    useState: (bas: unknown) =>
      this.dagitici.useReducer(
        (d: unknown, e: unknown) => (typeof e === 'function' ? (e as (x: unknown) => unknown)(d) : e),
        bas,
        (b: unknown) => (typeof b === 'function' ? (b as () => unknown)() : b),
      ),
    useRef: (bas: unknown) => this.yuva(() => ({ d: { current: bas } })).d,
    useMemo: (f: () => unknown, deps?: readonly unknown[]) => {
      const y = this.yuva(() => ({ ilk: true }))
      if (y.ilk || !deps || degisti(y.deps, deps)) {
        y.d = f()
        y.deps = deps
        y.ilk = false
      }
      return y.d
    },
    useCallback: (f: unknown, deps?: readonly unknown[]) => this.dagitici.useMemo(() => f, deps),
    useEffect: (f: () => unknown, deps?: readonly unknown[]) => this.efekt(f, deps, false),
    useLayoutEffect: (f: () => unknown, deps?: readonly unknown[]) => this.efekt(f, deps, true),
    useInsertionEffect: (f: () => unknown, deps?: readonly unknown[]) => this.efekt(f, deps, true),
    useImperativeHandle: (ref: any, f: () => unknown, deps?: readonly unknown[]) =>
      this.efekt(
        () => {
          const v = f()
          if (typeof ref === 'function') ref(v)
          else if (ref) ref.current = v
        },
        deps,
        true,
      ),
    useSyncExternalStore: (abone: (cb: () => void) => () => void, anlik: () => unknown) => {
      const deger = anlik()
      const y = this.yuva(() => ({ d: deger }))
      y.d = deger
      this.efekt(
        () =>
          abone(() => {
            if (!Object.is(anlik(), y.d)) this.isaretle()
          }),
        [abone],
        false,
      )
      return deger
    },
    useId: () => this.yuva(() => ({ d: `:kp2-${++this.sayac}:` })).d,
    useDebugValue: () => {},
    useTransition: () => [false, (f: () => void) => f()],
    useDeferredValue: (v: unknown) => v,
    useEffectEvent: (f: (...a: unknown[]) => unknown) => {
      const r = this.yuva(() => ({ d: { current: f } })).d
      r.current = f
      return (...a: unknown[]) => r.current(...a)
    },
  }
  private islev(fn: (p: any) => unknown, props: any, yol: string, kimlik: any): Cikti[] {
    const ad = `${yol}:${kimlik?.displayName ?? kimlik?.name ?? 'anon'}`
    let o = this.ornekler.get(ad)
    if (!o || o.tip !== kimlik) {
      if (o) this.sok(o)
      o = { tip: kimlik, yuvalar: [], ziyaret: false }
      this.ornekler.set(ad, o)
    }
    o.ziyaret = true
    const onceki = { H: IC.H, aktif: this.aktif, i: this.i, y: this.yerelY, p: this.yerelP }
    const yerelY: (() => void)[] = []
    const yerelP: (() => void)[] = []
    this.aktif = o
    this.i = 0
    this.yerelY = yerelY
    this.yerelP = yerelP
    IC.H = this.dagitici
    let cikti: unknown
    try {
      cikti = fn(props)
    } finally {
      IC.H = onceki.H
      this.aktif = onceki.aktif
      this.i = onceki.i
      this.yerelY = onceki.y
      this.yerelP = onceki.p
    }
    const sonuc = this.genislet(cikti, ad)
    this.yerlesim.push(...yerelY)
    this.pasif.push(...yerelP)
    return sonuc
  }
  private sinifCiz(Tip: any, props: any, yol: string): Cikti[] {
    const ad = `${yol}:${Tip.name}`
    let o = this.ornekler.get(ad)
    if (!o || o.tip !== Tip) {
      const ornek = new Tip(props)
      ornek.updater = {
        isMounted: () => true,
        enqueueSetState: (inst: any, kismi: any) => {
          const y = typeof kismi === 'function' ? kismi(inst.state, inst.props) : kismi
          if (y != null) {
            inst.state = { ...inst.state, ...y }
            this.isaretle()
          }
        },
        enqueueReplaceState: (inst: any, y: any) => {
          inst.state = y
          this.isaretle()
        },
        enqueueForceUpdate: () => this.isaretle(),
      }
      o = { tip: Tip, yuvalar: [], ziyaret: false, sinif: ornek }
      this.ornekler.set(ad, o)
    }
    o.ziyaret = true
    const ornek = o.sinif
    ornek.props = props
    const yUz = this.yerlesim.length
    const pUz = this.pasif.length
    try {
      return this.genislet(ornek.render(), ad)
    } catch (e) {
      if (typeof Tip.getDerivedStateFromError !== 'function') throw e
      // Yarım çizilen alt ağaç: efektleri atılır, örnekleri ziyaret edilmemiş sayılır (sökülür).
      this.yerlesim.length = yUz
      this.pasif.length = pUz
      for (const [k, x] of this.ornekler) if (k !== ad && k.startsWith(ad)) x.ziyaret = false
      ornek.state = { ...ornek.state, ...Tip.getDerivedStateFromError(e) }
      ornek.componentDidCatch?.(e, { componentStack: '' })
      return this.genislet(ornek.render(), `${ad}!`)
    }
  }
  private genislet(el: any, yol: string): Cikti[] {
    if (el == null || typeof el === 'boolean') return []
    if (typeof el === 'string' || typeof el === 'number' || typeof el === 'bigint') return [String(el)]
    if (Array.isArray(el)) return el.flatMap((c, j) => this.genislet(c, `${yol}[${c?.key ?? j}]`))
    const tip = el.type
    const props = el.props ?? {}
    const anahtar = el.key != null ? `${yol}#${el.key}` : yol
    if (tip === S.frag || S.sarma.includes(tip)) return this.genislet(props.children, `${anahtar}/F`)
    if (typeof tip === 'string') {
      const dyol = `${anahtar}/${tip}`
      let dom = this.domlar.get(dyol)
      if (!dom) {
        dom = this.domUret(tip, dyol)
        this.domlar.set(dyol, dom)
      }
      const ref = props.ref
      if (typeof ref === 'function') ref(dom)
      else if (ref && typeof ref === 'object') ref.current = dom
      return [{ tip, props, cocuklar: this.genislet(props.children, dyol), dom }]
    }
    if (tip?.$$typeof === S.ctx) {
      const yigin = this.baglam.get(tip) ?? []
      yigin.push(props.value)
      this.baglam.set(tip, yigin)
      try {
        return this.genislet(props.children, `${anahtar}/P`)
      } finally {
        yigin.pop()
      }
    }
    if (tip?.$$typeof === S.cons) return this.genislet(props.children(this.oku(tip._context)), `${anahtar}/C`)
    if (tip?.$$typeof === S.memo) return this.genislet({ type: tip.type, props, key: null }, `${anahtar}/M`)
    if (tip?.$$typeof === S.fwd) return this.islev((p: any) => tip.render(p, p.ref ?? null), props, `${anahtar}/R`, tip)
    if (typeof tip === 'function') {
      return tip.prototype?.isReactComponent ? this.sinifCiz(tip, props, anahtar) : this.islev(tip, props, anahtar, tip)
    }
    throw new Error(`mini çizici: bilinmeyen öğe türü ${String(tip?.$$typeof ?? tip)}`)
  }
}
export function olay(ek: Record<string, unknown> = {}): Record<string, any> {
  const e: Record<string, any> = { button: 0, defaultPrevented: false, metaKey: false, altKey: false, ctrlKey: false, shiftKey: false, ...ek }
  e.preventDefault = vi.fn(() => {
    e.defaultPrevented = true
  })
  e.stopPropagation = vi.fn()
  return e
}
export function metin(c: Cikti | Cikti[]): string {
  if (Array.isArray(c)) return c.map(metin).join('')
  return typeof c === 'string' ? c : metin(c.cocuklar)
}
export function hepsi(c: Cikti[], kosul: (d: Dugum) => boolean): Dugum[] {
  const out: Dugum[] = []
  const gez = (x: Cikti) => {
    if (typeof x === 'string') return
    if (kosul(x)) out.push(x)
    x.cocuklar.forEach(gez)
  }
  c.forEach(gez)
  return out
}
export function tek(c: Cikti[], kosul: (d: Dugum) => boolean, ad: string): Dugum {
  const h = hepsi(c, kosul)
  if (h.length !== 1) throw new Error(`${ad}: ${h.length} eşleşme (1 beklendi)`)
  return h[0]
}
export const dugme = (c: Cikti[], yazi: string) => tek(c, (d) => d.tip === 'button' && metin(d).includes(yazi), `düğme "${yazi}"`)
// ═══ KP2 MİNİ ÇİZİCİ SONU ═══════════════════════════════════════════════════════════════════════════════════════════════════════

const durum = vi.hoisted(() => ({
  session: null as unknown,
  ready: true,
  loading: false,
  requireAuth: null as unknown as ReturnType<typeof vi.fn>,
  navigate: null as unknown as ReturnType<typeof vi.fn>,
  arama: '',
  ucretsiz: false,
  istatistik: { data: [{ accounts: 42, devices_total: 9, devices_active: 7 }], error: null } as { data: unknown; error: unknown },
  rpcKapi: null as Promise<void> | null,
}))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ session: durum.session, ready: durum.ready, loading: durum.loading, email: null }),
  AuthProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../context/AuthModal', () => ({
  useAuthModal: () => ({ requireAuth: durum.requireAuth }),
  AuthModalProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('react-router-dom', () => ({
  useNavigate: () => durum.navigate,
  useSearchParams: () => [new URLSearchParams(durum.arama)],
  Link: ({ to, className, children }: { to: string; className?: string; children: unknown }) =>
    React.createElement('a', { href: to, className }, children as React.ReactNode),
}))
vi.mock('../lib/supabase', () => ({
  supabaseReady: true,
  supabase: {
    rpc: async (ad: string) => {
      if (durum.rpcKapi) await durum.rpcKapi
      return ad === 'usage_counts' ? durum.istatistik : { data: null, error: { message: 'bilinmeyen' } }
    },
    auth: { getSession: async () => ({ data: { session: null } }) },
  },
}))
vi.mock('../config', async (orijinal) => {
  const o = await orijinal<typeof import('../config')>()
  return {
    ...o,
    get FREE_MODE() {
      return durum.ucretsiz
    },
  }
})

const konum = { assign: vi.fn(), reload: vi.fn(), origin: 'https://site-ornek.test' }
function kureselKur(ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)') {
  const depo = new Map<string, string>([['pemf.dil', 'tr']])
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => depo.get(k) ?? null,
    setItem: (k: string, v: string) => void depo.set(k, String(v)),
    removeItem: (k: string) => void depo.delete(k),
  })
  vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })
  vi.stubGlobal('window', { location: konum })
  // node ≥ 21: `globalThis.navigator` salt-okur — tanımla (düz atama sessizce düşer, makinenin yereli sızar).
  Object.defineProperty(globalThis, 'navigator', { value: { userAgent: ua, platform: '', language: 'tr-TR' }, configurable: true })
}
kureselKur()

const i18n = (await import('../i18n')).default
const Pricing = (await import('../pages/Pricing')).default
const AuthRoute = (await import('../pages/AuthRoute')).default
const DownloadButtons = (await import('../components/DownloadButtons')).default
const DownloadPage = (await import('../pages/Download')).default
const { DownloadStats } = await import('../components/DownloadStats')
const AppScreenshots = (await import('../components/AppScreenshots')).default
const PackageBuilder = (await import('../components/PackageBuilder')).default
const { ErrorBoundary } = await import('../components/ErrorBoundary')
const { Menu } = await import('../components/Icons')
const DilDugmesi = (await import('../components/DilDugmesi')).default
const { PLANS, CLIENT, MODULES } = await import('../config')
const { sayi } = await import('../lib/para')
const t = (k: string, o?: Record<string, unknown>) => i18n.t(k as never, o as never) as unknown as string

let c: MiniCizici
async function ciz(el: React.ReactElement) {
  c = new MiniCizici()
  c.ciz(el)
  await c.bosalt()
}

beforeEach(() => {
  durum.session = null
  durum.ready = true
  durum.loading = false
  durum.requireAuth = vi.fn()
  durum.navigate = vi.fn()
  durum.arama = ''
  durum.ucretsiz = false
  durum.istatistik = { data: [{ accounts: 42, devices_total: 9, devices_active: 7 }], error: null }
  durum.rpcKapi = null
  konum.assign = vi.fn()
  konum.reload = vi.fn()
})
afterEach(async () => {
  c?.sokHepsi()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  kureselKur()
  if (i18n.language !== 'tr') await i18n.changeLanguage('tr')
})

describe('KP-3 · Pricing — satın alma yönü', () => {
  const ucretli = () => PLANS.filter((p) => p.paid)
  const planDugmesi = (cta: string) => tek(c.agac, (d) => d.tip === 'button' && metin(d) === cta, `plan düğmesi ${cta}`)
  it('satış açık: varsayılan YILLIK (2 ay bedava öne çıkar), araştırmasız → /odeme?tier=…&yearly=1&research=0', async () => {
    await ciz(<Pricing />)
    const p = ucretli()[0]
    await c.tikla(planDugmesi(p.cta))
    expect(durum.navigate).toHaveBeenCalledWith(`/odeme?tier=${p.tier}&yearly=1&research=0`)
  })
  it('yıllık düğmesi + araştırma kutusu → seçim adrese taşınır; aylığa geri dönülebilir', async () => {
    await ciz(<Pricing />)
    await c.tikla(tek(c.agac, (d) => d.tip === 'button' && metin(d).startsWith(t('fiyat.yillik')), 'yıllık'))
    await c.isaretleKutu(tek(c.agac, (d) => d.tip === 'input' && d.props.type === 'checkbox', 'araştırma'), true)
    const p = ucretli()[ucretli().length - 1]
    await c.tikla(planDugmesi(p.cta))
    expect(durum.navigate).toHaveBeenLastCalledWith(`/odeme?tier=${p.tier}&yearly=1&research=1`)
    await c.tikla(tek(c.agac, (d) => d.tip === 'button' && metin(d) === t('fiyat.aylik'), 'aylık'))
    await c.tikla(planDugmesi(p.cta))
    expect(durum.navigate).toHaveBeenLastCalledWith(`/odeme?tier=${p.tier}&yearly=0&research=1`)
  })
  it('ücretsiz dönemde (FREE_MODE) ücretli plan düğmesi ödemeye DEĞİL indirmeye götürür', async () => {
    durum.ucretsiz = true
    await ciz(<Pricing />)
    const p = ucretli()[0]
    await c.tikla(planDugmesi(p.cta))
    expect(durum.navigate).toHaveBeenCalledWith('/download')
    expect(String(durum.navigate.mock.calls[0][0])).not.toContain('/odeme')
  })
})

describe('KP-3 · AuthRoute — hesap rotaları', () => {
  it('oturum hazır DEĞİLKEN hiçbir yönlendirme / pencere yok', async () => {
    durum.ready = false
    await ciz(<AuthRoute kind="register" />)
    expect(durum.navigate).not.toHaveBeenCalled()
    expect(durum.requireAuth).not.toHaveBeenCalled()
  })
  it('zaten girişliyse ana sayfaya (replace) döner, pencere AÇILMAZ', async () => {
    durum.session = { user: {} }
    await ciz(<AuthRoute kind="login" />)
    expect(durum.navigate).toHaveBeenCalledWith('/', { replace: true })
    expect(durum.requireAuth).not.toHaveBeenCalled()
  })
  it('girişsiz /kayit → pencere KAYIT sekmesinde açılır; giriş bitince ana sayfaya; düğme pencereyi yeniden açar', async () => {
    await ciz(<AuthRoute kind="register" />)
    expect(durum.requireAuth).toHaveBeenCalledTimes(1)
    const [cb, akis, sekme] = durum.requireAuth.mock.calls[0]
    expect([akis, sekme]).toEqual(['download', 'signup'])
    cb()
    expect(durum.navigate).toHaveBeenCalledWith('/', { replace: true })
    await c.tikla(dugme(c.agac, t('hesap.rota.kayit.dugme')))
    expect(durum.requireAuth).toHaveBeenCalledTimes(2)
    expect(durum.requireAuth.mock.calls[1].slice(1)).toEqual(['download', 'signup'])
    durum.requireAuth.mock.calls[1][0]()
    expect(durum.navigate).toHaveBeenCalledTimes(2)
  })
  it('girişsiz /giris → GİRİŞ sekmesi', async () => {
    await ciz(<AuthRoute kind="login" />)
    expect(durum.requireAuth.mock.calls[0].slice(1)).toEqual(['download', 'login'])
  })
})

describe('KP-3 · indirme kapısı (DownloadButtons / DownloadPage)', () => {
  const windowsDugmesi = () =>
    tek(c.agac, (d) => d.tip === 'button' && String(d.props['aria-label'] ?? '').includes('Windows'), 'Windows düğmesi')
  it('girişli → tıklama DOĞRUDAN indirir (window.location.assign), pencere yok', async () => {
    durum.session = { user: {} }
    await ciz(<DownloadButtons />)
    await c.tikla(windowsDugmesi())
    expect(konum.assign).toHaveBeenCalledWith(CLIENT.downloads.windows.url)
    expect(durum.requireAuth).not.toHaveBeenCalled()
  })
  it('girişsiz → giriş penceresi (indirme bekletilir); pencere geri çağrısı indirmeyi başlatır', async () => {
    await ciz(<DownloadButtons />)
    await c.tikla(windowsDugmesi())
    expect(konum.assign).not.toHaveBeenCalled()
    expect(durum.requireAuth).toHaveBeenCalledTimes(1)
    durum.requireAuth.mock.calls[0][0]()
    expect(konum.assign).toHaveBeenCalledWith(CLIENT.downloads.windows.url)
  })
  it('oturum OKUNURKEN düğmeler kilitli; 8 sn bekleme aşılınca kilit açılır (asılı getSession kalıcı kilit olmaz); okuma bitince bekleme sıfırlanır', async () => {
    vi.useFakeTimers()
    durum.loading = true
    await ciz(<DownloadButtons />)
    expect(windowsDugmesi().props.disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(7999)
    await c.bosalt()
    expect(windowsDugmesi().props.disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(2)
    await c.bosalt()
    expect(windowsDugmesi().props.disabled).toBe(false)
    durum.loading = false
    c.kirli = true
    await c.bosalt()
    expect(windowsDugmesi().props.disabled).toBe(false)
  })
  it('işletim sistemi ALGILANIR (efekt): hazır bir platformun tarayıcısında o platform BİRİNCİL olur (Linux X11 → Linux önde)', async () => {
    const linux = CLIENT.downloads.linux as { ready: boolean }
    const once = linux.ready
    linux.ready = true
    try {
      kureselKur('Mozilla/5.0 (X11; Linux x86_64)')
      await ciz(<DownloadButtons />)
      const ilk = hepsi(c.agac, (d) => d.tip === 'button')[0]
      expect(String(ilk.props['aria-label'])).toContain('Linux')
      c.sokHepsi()
      kureselKur()
      await ciz(<DownloadButtons />)
      expect(String(hepsi(c.agac, (d) => d.tip === 'button')[0].props['aria-label'])).toContain('Windows')
    } finally {
      linux.ready = once
    }
  })
  it('indirme sayfası: Windows kartı indirir; Linux .AppImage / .rpm alt düğmeleri (hazırsa) kendi adreslerine gider', async () => {
    const linux = CLIENT.downloads.linux as { ready: boolean; appImageReady: boolean; rpmReady: boolean }
    const once = { ...linux }
    Object.assign(linux, { ready: true, appImageReady: true, rpmReady: true })
    try {
      durum.session = { user: {} }
      await ciz(<DownloadPage />)
      await c.tikla(tek(c.agac, (d) => d.tip === 'button' && d.props['data-kapi'] === 'indir', 'birincil indirme'))
      expect(konum.assign).toHaveBeenLastCalledWith(CLIENT.downloads.windows.url)
      await c.tikla(tek(c.agac, (d) => d.tip === 'button' && metin(d).includes(t('indirme.appImage')), 'AppImage'))
      expect(konum.assign).toHaveBeenLastCalledWith(CLIENT.downloads.linux.appImageUrl)
      await c.tikla(tek(c.agac, (d) => d.tip === 'button' && metin(d).includes('.rpm (Fedora / RHEL)'), 'rpm'))
      expect(konum.assign).toHaveBeenLastCalledWith(CLIENT.downloads.linux.rpmUrl)
    } finally {
      Object.assign(linux, once)
    }
  })
})

describe('KP-3 · DownloadStats — kullanım sayacı', () => {
  it('RPC hesap sayısı + son 30 gün aktif cihaz; toplam cihaz (şişmiş) GÖSTERİLMEZ', async () => {
    await ciz(<DownloadStats />)
    const yazi = metin(c.agac)
    expect(yazi).toContain(t('indirme.istatistik.kayitliKullanici'))
    expect(yazi).toContain(sayi(42))
    expect(yazi).toContain(t('indirme.istatistik.aktifCihaz'))
    expect(yazi).toContain(sayi(7))
    expect(yazi).not.toContain(sayi(9))
  })
  it('aktif cihaz 0 → cihaz satırı yok; hesap 0 ya da RPC hatası → bölüm HİÇ yok (uydurma sayı yok)', async () => {
    durum.istatistik = { data: [{ accounts: 5, devices_total: 3, devices_active: 0 }], error: null }
    await ciz(<DownloadStats />)
    expect(metin(c.agac)).not.toContain(t('indirme.istatistik.aktifCihaz'))
    c.sokHepsi()
    durum.istatistik = { data: [{ accounts: 0, devices_total: 3, devices_active: 1 }], error: null }
    await ciz(<DownloadStats />)
    expect(metin(c.agac)).toBe('')
    c.sokHepsi()
    durum.istatistik = { data: null, error: { message: 'rpc yok' } }
    await ciz(<DownloadStats />)
    expect(metin(c.agac)).toBe('')
  })
  it('bileşen ayrılınca istek İPTAL edilir: geç gelen yanıt çizilmez', async () => {
    let ac!: () => void
    durum.rpcKapi = new Promise<void>((r) => (ac = r))
    await ciz(<DownloadStats />)
    c.sokHepsi()
    ac()
    await c.bosalt()
    expect(c.agac).toEqual([])
  })
})

describe('KP-3 · AppScreenshots / PackageBuilder / ErrorBoundary / simge / dil düğmesi', () => {
  it('ekran görüntüsü şeridi: önceki / sonraki → genişliğin yüzde 80i, en çok 720 px, yumuşak kaydırma', async () => {
    await ciz(<AppScreenshots />)
    const serit = tek(c.agac, (d) => d.tip === 'div' && String(d.props.className ?? '').includes('overflow-x-auto'), 'şerit')
    await c.tikla(tek(c.agac, (d) => d.tip === 'button' && d.props['aria-label'] === t('ekranlar.sonraki'), 'sonraki'))
    expect(serit.dom.scrollBy).toHaveBeenLastCalledWith({ left: 720, behavior: 'smooth' })
    serit.dom.clientWidth = 500
    await c.tikla(tek(c.agac, (d) => d.tip === 'button' && d.props['aria-label'] === t('ekranlar.onceki'), 'önceki'))
    expect(serit.dom.scrollBy).toHaveBeenLastCalledWith({ left: -400, behavior: 'smooth' })
  })
  it('paket seçici: modül kartı seçimi aç / kapa (aria-pressed); varsayılan Ev Sahibi + Veteriner', async () => {
    await ciz(<PackageBuilder />)
    const kart = (id: string) => {
      const m = MODULES.find((x) => x.id === id)!
      return tek(c.agac, (d) => d.tip === 'button' && d.props['aria-pressed'] !== undefined && metin(d).includes(m.name), `kart ${id}`)
    }
    expect(kart('home').props['aria-pressed']).toBe(true)
    expect(kart('research').props['aria-pressed']).toBe(false)
    await c.tikla(kart('research'))
    expect(kart('research').props['aria-pressed']).toBe(true)
    await c.tikla(kart('home'))
    expect(kart('home').props['aria-pressed']).toBe(false)
  })
  it('hata sınırı: alt bileşen çizimde patlarsa beyaz ekran yerine kurtarma ekranı + günlük; "yenile" sayfayı yeniler', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    function Patlayan(): React.ReactElement {
      throw new Error('çizim hatası')
    }
    await ciz(
      <ErrorBoundary>
        <Patlayan />
      </ErrorBoundary>,
    )
    expect(metin(c.agac)).toContain(i18n.t('hata.baslik'))
    expect(gunluk).toHaveBeenCalledWith('Uygulama hatası:', expect.objectContaining({ message: 'çizim hatası' }))
    await c.tikla(dugme(c.agac, i18n.t('hata.yenile')))
    expect(konum.reload).toHaveBeenCalledTimes(1)
    gunluk.mockRestore()
  })
  it('hata yoksa çocuklar aynen çizilir', async () => {
    await ciz(
      <ErrorBoundary>
        <p>içerik</p>
      </ErrorBoundary>,
    )
    expect(metin(c.agac)).toBe('içerik')
  })
  it('menü simgesi üç çizgili SVG', async () => {
    await ciz(<Menu className="h-6 w-6" />)
    const svg = tek(c.agac, (d) => d.tip === 'svg', 'svg')
    expect(tek(svg.cocuklar, (d) => d.tip === 'path', 'path').props.d).toBe('M4 6h16M4 12h16M4 18h16')
  })
  it('dil düğmesi: Türkçe ekranda İngilizceye, İngilizcede Türkçeye geçirir', async () => {
    await ciz(<DilDugmesi />)
    const d = hepsi(c.agac, (x) => x.tip === 'button')
    if (d.length === 0) return // seçim görünmüyorsa (bayrak kapalı) düğme yok — sözleşme dilSecimiGorunur'de
    await c.tikla(d[0])
    await c.bosalt()
    expect(i18n.language).toBe('en')
    c.kirli = true
    await c.bosalt()
    await c.tikla(hepsi(c.agac, (x) => x.tip === 'button')[0])
    await c.bosalt()
    expect(i18n.language).toBe('tr')
  })
})
