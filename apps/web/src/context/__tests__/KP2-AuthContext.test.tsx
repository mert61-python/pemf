// Author: mertaygn, cglrgrkn
/**
 * KP-2 · src/context/AuthContext.tsx · sözleşmeler:
 *  - Supabase yapılandırılmamış → yükleme HEMEN biter, oturum okunmaz / dinlenmez, `ready:false`,
 *  - açılışta oturum okunur (e-posta oturumdan), okuma REDDEDİLİRSE de yükleme biter (sonsuz "yükleniyor" yok),
 *  - oturum değişimi (TOKEN_REFRESHED / SIGNED_OUT) bağlama yansır; söküldüğünde abonelik iptal edilir,
 *  - signIn / signUp / resetPassword sağlayıcının HAM İngilizce hatasını ürünün Türkçe karşılığına çevirir; signUp profil bilgisini
 *    `options.data`ya yazar (yoksa options YOK) ve doğrulama bekleniyorsa `needConfirm` döner; resetPassword dönüş adresi
 *    `<köken>/sifre-sifirla`; signOut YALNIZ bu tarayıcıda (`scope:'local'`),
 *  - sağlayıcı dışında `useAuth` → açık hata.
 *
 * DÜZENEK: site testlerinde DOM yok (jsdom kurulu değil). GERÇEK bileşenler küçük bir "mini çizici" ile çizilir: React'in kanca
 * dağıtıcısı (`__CLIENT_INTERNALS…H`) çizim süresince bu dosyadaki sözleşmeye uygun bir dağıtıcıyla değiştirilir (durum / ref / memo /
 * efekt — önce yerleşim, sonra pasif, çocuk-önce — bağlam yığını, useSyncExternalStore); ürün ve kütüphane (react-i18next) kancaları
 * GERÇEK React API'sinden geçer. Katalog GERÇEK (Türkçe). Sahte EN ALT katta: Supabase istemcisi (`../../lib/supabase`), `window.location`.
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

const sb = vi.hoisted(() => {
  const d = {
    hazir: true,
    oturum: null as null | Record<string, unknown>,
    oturumHata: null as Error | null,
    dinleyiciler: [] as ((olay: string, s: unknown) => void)[],
    iptal: 0,
    cagri: [] as [string, unknown][],
    girisHata: null as null | { message: string },
    kayitSonuc: { data: { session: null as unknown }, error: null as null | { message: string } },
    sifirlaHata: null as null | { message: string },
  }
  const auth = {
    getSession: async () => {
      d.cagri.push(['getSession', null])
      if (d.oturumHata) throw d.oturumHata
      return { data: { session: d.oturum } }
    },
    onAuthStateChange: (f: (olay: string, s: unknown) => void) => {
      d.dinleyiciler.push(f)
      return {
        data: {
          subscription: {
            unsubscribe: () => {
              d.iptal++
              d.dinleyiciler = d.dinleyiciler.filter((x) => x !== f)
            },
          },
        },
      }
    },
    signInWithPassword: async (a: unknown) => {
      d.cagri.push(['signInWithPassword', a])
      return { data: {}, error: d.girisHata }
    },
    signUp: async (a: unknown) => {
      d.cagri.push(['signUp', a])
      return d.kayitSonuc
    },
    resetPasswordForEmail: async (e: string, o: unknown) => {
      d.cagri.push(['resetPasswordForEmail', [e, o]])
      return { data: {}, error: d.sifirlaHata }
    },
    signOut: async (o: unknown) => {
      d.cagri.push(['signOut', o])
      return { error: null }
    },
  }
  return { d, istemci: { auth } }
})
vi.mock('../../lib/supabase', () => ({
  get supabaseReady() {
    return sb.d.hazir
  },
  supabase: sb.istemci,
  AUTH_OPTIONS: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
}))

const depo = new Map<string, string>([['pemf.dil', 'tr']])
vi.stubGlobal('localStorage', {
  getItem: (k: string) => depo.get(k) ?? null,
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })

await import('../../i18n')
const { AuthProvider, useAuth } = await import('../AuthContext')
const { authHatasiTurkce } = await import('../../lib/authHatalari')

type Baglam = ReturnType<typeof useAuth>
let son: Baglam | null = null
function Yakala() {
  son = useAuth()
  return null
}
let c: MiniCizici
const baglam = () => son as Baglam

beforeEach(() => {
  sb.d.hazir = true
  sb.d.oturum = null
  sb.d.oturumHata = null
  sb.d.dinleyiciler = []
  sb.d.iptal = 0
  sb.d.cagri = []
  sb.d.girisHata = null
  sb.d.kayitSonuc = { data: { session: null }, error: null }
  sb.d.sifirlaHata = null
  son = null
  vi.stubGlobal('window', { location: { origin: 'https://site-ornek.test' } })
  c = new MiniCizici()
})
afterEach(() => {
  c.sokHepsi()
  vi.unstubAllGlobals()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => depo.get(k) ?? null,
    setItem: (k: string, v: string) => void depo.set(k, String(v)),
    removeItem: (k: string) => void depo.delete(k),
  })
  vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })
  vi.restoreAllMocks()
})

describe('AuthProvider — oturum yaşam döngüsü', () => {
  it('Supabase yapılandırılmamış → yükleme HEMEN biter, oturum okunmaz/dinlenmez, ready:false', async () => {
    sb.d.hazir = false
    c.ciz(<AuthProvider><Yakala /></AuthProvider>)
    await c.bosalt()
    expect(baglam().loading).toBe(false)
    expect(baglam().ready).toBe(false)
    expect(baglam().session).toBeNull()
    expect(sb.d.cagri.filter(([ad]) => ad === 'getSession')).toHaveLength(0)
    expect(sb.d.dinleyiciler).toHaveLength(0)
  })

  it('KARŞIT: yapılandırılmış → ilk çizimde loading:true, oturum okununca e-posta oturumdan gelir ve loading:false', async () => {
    sb.d.oturum = { user: { email: 'vet@ornek.test' }, access_token: 'jwt' }
    c.ciz(<AuthProvider><Yakala /></AuthProvider>)
    expect(baglam().loading).toBe(true)
    await c.bosalt()
    expect(baglam().loading).toBe(false)
    expect(baglam().ready).toBe(true)
    expect(baglam().session).toBe(sb.d.oturum)
    expect(baglam().email).toBe('vet@ornek.test')
  })

  it('oturum okuması REDDEDİLİRSE → oturum null ve loading:false (sonsuz "yükleniyor" yok)', async () => {
    sb.d.oturumHata = new Error('navigator.locks zaman aşımı')
    c.ciz(<AuthProvider><Yakala /></AuthProvider>)
    await c.bosalt()
    expect(baglam().session).toBeNull()
    expect(baglam().email).toBeNull()
    expect(baglam().loading).toBe(false)
  })

  it('oturum değişimi (TOKEN_REFRESHED → SIGNED_OUT) bağlama yansır', async () => {
    c.ciz(<AuthProvider><Yakala /></AuthProvider>)
    await c.bosalt()
    expect(sb.d.dinleyiciler).toHaveLength(1)
    sb.d.dinleyiciler[0]('TOKEN_REFRESHED', { user: { email: 'yeni@ornek.test' } })
    await c.bosalt()
    expect(baglam().email).toBe('yeni@ornek.test')
    sb.d.dinleyiciler[0]('SIGNED_OUT', null)
    await c.bosalt()
    expect(baglam().session).toBeNull()
    expect(baglam().email).toBeNull()
  })

  it('sökülünce oturum aboneliği İPTAL edilir (dinleyici kalmaz)', async () => {
    c.ciz(<AuthProvider><Yakala /></AuthProvider>)
    await c.bosalt()
    c.sokHepsi()
    expect(sb.d.iptal).toBe(1)
    expect(sb.d.dinleyiciler).toHaveLength(0)
  })

  it('sağlayıcı dışında useAuth → "useAuth must be used within AuthProvider"', () => {
    expect(() => c.ciz(<Yakala />)).toThrow('useAuth must be used within AuthProvider')
  })
})

describe('AuthProvider — işlemler', () => {
  async function hazirla() {
    c.ciz(<AuthProvider><Yakala /></AuthProvider>)
    await c.bosalt()
    return baglam()
  }

  it('signIn başarı → {error: undefined}; sağlayıcıya e-posta + şifre AYNEN', async () => {
    const b = await hazirla()
    await expect(b.signIn('vet@ornek.test', 'Gizli123')).resolves.toEqual({ error: undefined })
    expect(sb.d.cagri).toContainEqual(['signInWithPassword', { email: 'vet@ornek.test', password: 'Gizli123' }])
  })

  it('signIn hata → HAM İngilizce mesaj DEĞİL, ürünün Türkçe karşılığı', async () => {
    sb.d.girisHata = { message: 'Invalid login credentials' }
    const b = await hazirla()
    const r = await b.signIn('vet@ornek.test', 'yanlis')
    expect(r.error).toBe(authHatasiTurkce('Invalid login credentials'))
    expect(r.error).not.toContain('Invalid login credentials')
  })

  it('signUp profil bilgisiyle → options.data = profil; oturum yoksa needConfirm:true', async () => {
    const b = await hazirla()
    const meta = { account_type: 'veterinarian', full_name: 'Ayşe' }
    await expect(b.signUp('vet@ornek.test', 'Gizli123', meta)).resolves.toEqual({ error: undefined, needConfirm: true })
    expect(sb.d.cagri).toContainEqual(['signUp', { email: 'vet@ornek.test', password: 'Gizli123', options: { data: meta } }])
  })

  it('signUp profilsiz → options YOK; oturum döndüyse needConfirm:false', async () => {
    sb.d.kayitSonuc = { data: { session: { access_token: 'jwt' } }, error: null }
    const b = await hazirla()
    await expect(b.signUp('vet@ornek.test', 'Gizli123')).resolves.toEqual({ error: undefined, needConfirm: false })
    expect(sb.d.cagri).toContainEqual(['signUp', { email: 'vet@ornek.test', password: 'Gizli123', options: undefined }])
  })

  it('signUp hata → Türkçe karşılık', async () => {
    sb.d.kayitSonuc = { data: { session: null }, error: { message: 'User already registered' } }
    const b = await hazirla()
    const r = await b.signUp('vet@ornek.test', 'Gizli123')
    expect(r.error).toBe(authHatasiTurkce('User already registered'))
  })

  it('resetPassword → dönüş adresi <köken>/sifre-sifirla; başarıda error yok, hatada Türkçe karşılık', async () => {
    const b = await hazirla()
    await expect(b.resetPassword('vet@ornek.test')).resolves.toEqual({ error: undefined })
    expect(sb.d.cagri).toContainEqual(['resetPasswordForEmail', ['vet@ornek.test', { redirectTo: 'https://site-ornek.test/sifre-sifirla' }]])
    sb.d.sifirlaHata = { message: 'Email rate limit exceeded' }
    expect((await b.resetPassword('vet@ornek.test')).error).toBe(authHatasiTurkce('Email rate limit exceeded'))
  })

  it('signOut → YALNIZ bu tarayıcı (scope:"local"; mobil / masaüstü oturumları düşmez)', async () => {
    const b = await hazirla()
    await b.signOut()
    expect(sb.d.cagri).toContainEqual(['signOut', { scope: 'local' }])
  })
})
