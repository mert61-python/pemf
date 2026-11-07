// Author: mertaygn, cglrgrkn
/**
 * KP-3 C · src/components/AccountButton.tsx · sözleşmeler (GERÇEK bileşen + GERÇEK `jetonBakiyesiniOku` / `cancelSubscription`; sahte EN ALT
 * katta — Supabase oturum belirteci + `fetch` (`/api/tokens`, `/api/cancel`)):
 *  - hazır değilken çizilmez; oturumsuz "Giriş yap" → giriş penceresi + çekmece kapatma,
 *  - "Hesabım" menüyü aç / kapa (aria-expanded); menü AÇILINCA bakiye çekilir (belirteçle), okunamazsa kutu yok; ücretsiz dönemde bakiye
 *    istenmez, iptal düğmesi yok, "test aşaması" notu,
 *  - dışarı tıklama / Esc kapatır, içeri tıklama kapatmaz, dinleyiciler kalkar; "Çıkış yap" kapatır + oturumu kapatır,
 *  - iptal: onay sorusu → vazgeç (istek yok) · evet → /api/cancel, sürerken iki düğme kilitli, başarı yeşil / ret Türkçe kırmızı.
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
  session: { user: { email: 'vet@ornek.test' } } as unknown,
  email: 'vet@ornek.test' as string | null,
  ready: true,
  requireAuth: null as unknown as ReturnType<typeof vi.fn>,
  signOut: null as unknown as ReturnType<typeof vi.fn>,
  belirtec: 'sb-belirtec-1' as string | null,
  ucretsiz: false,
}))
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ session: durum.session, email: durum.email, ready: durum.ready, signOut: durum.signOut, loading: false }),
  AuthProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../../context/AuthModal', () => ({
  useAuthModal: () => ({ requireAuth: durum.requireAuth }),
  AuthModalProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../../lib/supabase', () => ({
  supabaseReady: true,
  supabase: { auth: { getSession: async () => ({ data: { session: durum.belirtec ? { access_token: durum.belirtec } : null } }) } },
}))
vi.mock('../../config', async (orijinal) => {
  const o = await orijinal<typeof import('../../config')>()
  return {
    ...o,
    get FREE_MODE() {
      return durum.ucretsiz
    },
  }
})

/** Belge: dışarı tıklama / Esc dinleyicileri; i18n için asgari yüzey. */
const belge = {
  documentElement: { lang: '' },
  title: '',
  querySelector: () => null,
  dinleyici: new Map<string, Set<(e: unknown) => void>>(),
  addEventListener(t: string, f: (e: unknown) => void) {
    if (!belge.dinleyici.has(t)) belge.dinleyici.set(t, new Set())
    belge.dinleyici.get(t)!.add(f)
  },
  removeEventListener(t: string, f: (e: unknown) => void) {
    belge.dinleyici.get(t)?.delete(f)
  },
}
function kureselKur() {
  const depo = new Map<string, string>([['pemf.dil', 'tr']])
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => depo.get(k) ?? null,
    setItem: (k: string, v: string) => void depo.set(k, String(v)),
    removeItem: (k: string) => void depo.delete(k),
  })
  vi.stubGlobal('document', belge)
  vi.stubGlobal('window', { location: { origin: 'https://site-ornek.test' } })
}
kureselKur()

const i18n = (await import('../../i18n')).default
const AccountButton = (await import('../AccountButton')).default
const { sayi } = await import('../../lib/para')
const { odemeHatasiTurkce } = await import('../../lib/authHatalari')
const t = (k: string, o?: Record<string, unknown>) => i18n.t(k as never, o as never) as unknown as string

let c: MiniCizici
let istekler: { url: string; o: Record<string, any> }[]
let jetonYaniti: { ok: boolean; govde: unknown }
let iptalYaniti: { ok: boolean; govde: unknown }
let kapi: Promise<void> | null
let gezindi: ReturnType<typeof vi.fn<() => void>>

function fetchKur() {
  vi.stubGlobal('fetch', async (url: string, o: Record<string, any> = {}) => {
    istekler.push({ url, o })
    if (url === '/api/cancel' && kapi) await kapi
    const y = url === '/api/tokens' ? jetonYaniti : iptalYaniti
    return { ok: y.ok, json: async () => y.govde }
  })
}
async function ciz(props: Record<string, unknown> = {}) {
  c = new MiniCizici()
  c.ciz(<AccountButton onNavigate={gezindi} {...props} />)
  await c.bosalt()
}
const menu = () => hepsi(c.agac, (d) => d.props.role === 'menu')
const hesabim = () => dugme(c.agac, t('hesap.hesabim'))
async function ac() {
  await c.tikla(hesabim())
  await c.bosalt()
}
function belgeOlayi(tip: string, e: Record<string, unknown>) {
  for (const f of [...(belge.dinleyici.get(tip) ?? [])]) f(e)
}

beforeEach(async () => {
  istekler = []
  kapi = null
  jetonYaniti = { ok: true, govde: { kalan: 1234, aylik_hak: 1000, satin_alinan: 250, donem_sonu: null } }
  iptalYaniti = { ok: true, govde: { canceled: true } }
  durum.session = { user: { email: 'vet@ornek.test' } }
  durum.email = 'vet@ornek.test'
  durum.ready = true
  durum.belirtec = 'sb-belirtec-1'
  durum.ucretsiz = false
  durum.requireAuth = vi.fn()
  durum.signOut = vi.fn()
  gezindi = vi.fn<() => void>()
  belge.dinleyici.clear()
  fetchKur()
  await ciz()
})
afterEach(() => {
  c.sokHepsi()
  vi.unstubAllGlobals()
  kureselKur()
})

describe('KP-3 · AccountButton — giriş durumu', () => {
  it('oturum hazır DEĞİLKEN hiçbir şey çizilmez', async () => {
    c.sokHepsi()
    durum.ready = false
    await ciz()
    expect(metin(c.agac)).toBe('')
  })

  it('oturum YOKSA "Giriş yap" → giriş penceresi + çekmece kapatma geri çağrısı; menü YOK', async () => {
    c.sokHepsi()
    durum.session = null
    await ciz()
    await c.tikla(dugme(c.agac, t('hesap.girisYap')))
    expect(durum.requireAuth).toHaveBeenCalledTimes(1)
    expect(gezindi).toHaveBeenCalledTimes(1)
    expect(menu()).toHaveLength(0)
  })
})

describe('KP-3 · AccountButton — menü', () => {
  it('"Hesabım" menüyü açar / kapatır (aria-expanded); e-posta görünür; AÇILINCA bakiye çekilir (açılmadan istek YOK)', async () => {
    expect(istekler).toHaveLength(0)
    expect(hesabim().props['aria-expanded']).toBe(false)
    await ac()
    expect(hesabim().props['aria-expanded']).toBe(true)
    expect(menu()).toHaveLength(1)
    expect(metin(menu()[0])).toContain('vet@ornek.test')
    expect(istekler.map((x) => x.url)).toEqual(['/api/tokens'])
    expect(istekler[0].o.headers).toEqual({ Authorization: 'Bearer sb-belirtec-1' })
    const yazi = metin(menu()[0])
    expect(yazi).toContain(t('hesap.kalanJeton'))
    expect(yazi).toContain(sayi(1234))
    expect(yazi).toContain(t('hesap.jeton.aylikHak', { sayi: sayi(1000) }))
    expect(yazi).toContain(t('hesap.jeton.satinAlinan', { sayi: sayi(250) }))
    expect(yazi).toContain(t('hesap.jetonNotu'))
    await c.tikla(hesabim())
    expect(menu()).toHaveLength(0)
  })

  it('bakiye OKUNAMAZSA (sunucu hatası) kutu hiç çizilmez — yanlış sayı uydurulmaz', async () => {
    jetonYaniti = { ok: false, govde: {} }
    await ac()
    expect(metin(menu()[0])).not.toContain(t('hesap.kalanJeton'))
  })

  it('ÜCRETSİZ dönemde (FREE_MODE) bakiye İSTENMEZ, kutu ve iptal düğmesi yok; "test aşaması" notu', async () => {
    c.sokHepsi()
    durum.ucretsiz = true
    await ciz()
    await ac()
    expect(istekler).toHaveLength(0)
    const yazi = metin(menu()[0])
    expect(yazi).not.toContain(t('hesap.kalanJeton'))
    expect(yazi).toContain(t('hesap.abonelik.testAsamasi'))
    expect(hepsi(menu()[0].cocuklar, (d) => d.tip === 'button' && metin(d).includes(t('hesap.abonelik.iptalEt')))).toHaveLength(0)
  })

  it('dışarı tıklama ve Esc menüyü kapatır; menünün İÇİNE tıklamak kapatmaz; kapanınca dinleyiciler kalkar', async () => {
    await ac()
    const kutu = tek(c.agac, (d) => d.tip === 'div' && d.props.className === 'relative', 'menü kutusu')
    belgeOlayi('mousedown', { target: kutu.dom })
    await c.bosalt()
    expect(menu()).toHaveLength(1)
    belgeOlayi('keydown', { key: 'Enter' })
    await c.bosalt()
    expect(menu()).toHaveLength(1)
    belgeOlayi('mousedown', { target: { baska: true } })
    await c.bosalt()
    expect(menu()).toHaveLength(0)
    expect(belge.dinleyici.get('mousedown')?.size ?? 0).toBe(0)
    await ac()
    belgeOlayi('keydown', { key: 'Escape' })
    await c.bosalt()
    expect(menu()).toHaveLength(0)
    expect(belge.dinleyici.get('keydown')?.size ?? 0).toBe(0)
  })

  it('"Çıkış yap" menüyü kapatır ve oturumu kapatır', async () => {
    await ac()
    await c.tikla(dugme(c.agac, t('hesap.cikisYap')))
    expect(durum.signOut).toHaveBeenCalledTimes(1)
    expect(menu()).toHaveLength(0)
  })
})

describe('KP-3 · AccountButton — abonelik iptali', () => {
  it('iptal → onay sorusu; "vazgeç" soruyu kapatır, sunucuya GİDİLMEZ', async () => {
    await ac()
    await c.tikla(dugme(c.agac, t('hesap.abonelik.iptalEt')))
    expect(metin(menu()[0])).toContain(t('hesap.abonelik.iptalSorusu'))
    await c.tikla(dugme(c.agac, t('hesap.abonelik.vazgec')))
    expect(metin(menu()[0])).not.toContain(t('hesap.abonelik.iptalSorusu'))
    expect(istekler.filter((x) => x.url === '/api/cancel')).toHaveLength(0)
  })

  it('"evet, iptal" → /api/cancel belirteçle; sürerken "iptal ediliyor" + iki düğme devre dışı; başarı → yeşil "iptal edildi", iptal düğmesi gizli', async () => {
    await ac()
    await c.tikla(dugme(c.agac, t('hesap.abonelik.iptalEt')))
    let ac2!: () => void
    kapi = new Promise<void>((r) => (ac2 = r))
    const tiklama = c.tikla(dugme(c.agac, t('hesap.abonelik.evetIptal')))
    await c.bosalt()
    expect(dugme(c.agac, t('hesap.abonelik.iptalEdiliyor')).props.disabled).toBe(true)
    expect(dugme(c.agac, t('hesap.abonelik.vazgec')).props.disabled).toBe(true)
    ac2()
    await tiklama
    await c.bosalt()
    const iptal = istekler.filter((x) => x.url === '/api/cancel')
    expect(iptal).toHaveLength(1)
    expect(JSON.parse(iptal[0].o.body)).toEqual({ token: 'sb-belirtec-1' })
    const p = tek(c.agac, (d) => d.tip === 'p' && metin(d) === t('hesap.abonelik.iptalEdildi'), 'sonuç')
    expect(String(p.props.className)).toContain('text-success')
    expect(metin(menu()[0])).not.toContain(t('hesap.abonelik.iptalSorusu'))
    expect(hepsi(c.agac, (d) => d.tip === 'button' && metin(d) === t('hesap.abonelik.iptalEt'))).toHaveLength(0)
  })

  it('sunucu reddi → ham metin değil Türkçe karşılık, kırmızı; menü kapatılıp açılınca sonuç silinir ve iptal yeniden önerilir', async () => {
    iptalYaniti = { ok: false, govde: { message: 'Subscription not found' } }
    await ac()
    await c.tikla(dugme(c.agac, t('hesap.abonelik.iptalEt')))
    await c.tikla(dugme(c.agac, t('hesap.abonelik.evetIptal')))
    await c.bosalt()
    const beklenen = odemeHatasiTurkce('Subscription not found')
    const p = tek(c.agac, (d) => d.tip === 'p' && metin(d) === beklenen, 'hata sonucu')
    expect(String(p.props.className)).toContain('text-danger')
    await c.tikla(hesabim())
    await ac()
    expect(hepsi(c.agac, (d) => d.tip === 'p' && metin(d) === beklenen)).toHaveLength(0)
    expect(dugme(c.agac, t('hesap.abonelik.iptalEt'))).toBeTruthy()
  })
})
