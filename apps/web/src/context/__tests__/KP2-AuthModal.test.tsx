// Author: mertaygn, cglrgrkn
/**
 * KP-2 · src/context/AuthModal.tsx · sözleşmeler (GERÇEK AuthProvider + AuthModalProvider; sahte EN ALT katta — Supabase istemcisi):
 *  - requireAuth(cb) → pencere açılır; oturum GELİNCE pencere kapanır ve bekleyen iş TAM BİR KEZ çalışır; kullanıcı pencereyi
 *    kapattıysa sonraki girişte bekleyen iş ÇALIŞMAZ,
 *  - giriş: e-posta kırpılır, şifre aynen; sürerken düğme "bekleyin" + devre dışı; hata ürünün Türkçe karşılığıyla gösterilir,
 *  - kayıt: zayıf şifre sunucuya GİTMEDEN Türkçe kural iletisiyle reddedilir; hesap türüne göre YALNIZ ilgili profil alanları
 *    (kırpılmış; isteğe bağlı alan boşsa hiç) `user_metadata`ya yazılır; doğrulama bekleniyorsa akışa göre (indirme / abonelik) bilgi,
 *  - "Şifremi unuttum": e-posta boşsa sunucuya gitmeden uyarı; doluysa kırpılmış e-postayla sıfırlama + bilgi / hata,
 *  - Esc pencereyi kapatır (form boşken); Tab / Shift+Tab odağı diyalog İÇİNDE döndürür; iç tıklama arka plana YAYILMAZ;
 *    yalnız arka planın KENDİSİNE basmak kapatır; kapanınca odak önceki öğeye döner ve tuş dinleyicisi kalkar,
 *  - giriş ↔ kayıt geçişi başlığı / düğmeyi değiştirir ve eski hata iletisini siler; Supabase yoksa servis uyarısı + gönder kapalı,
 *  - sağlayıcı dışında `useAuthModal` → açık hata.
 * Metinler ürünün GERÇEK kataloğundan (`i18n.t`, Türkçe). Düzenek: KP2 mini çizici (aşağıdaki blok; gerekçe KP2-AuthContext.test.tsx).
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
    dinleyiciler: [] as ((olay: string, s: unknown) => void)[],
    cagri: [] as [string, unknown][],
    kapi: null as Promise<void> | null,
    girisHata: null as null | { message: string },
    kayitSonuc: { data: { session: null as unknown }, error: null as null | { message: string } },
    sifirlaHata: null as null | { message: string },
  }
  const auth = {
    getSession: async () => ({ data: { session: null } }),
    onAuthStateChange: (f: (olay: string, s: unknown) => void) => {
      d.dinleyiciler.push(f)
      return { data: { subscription: { unsubscribe: () => void (d.dinleyiciler = d.dinleyiciler.filter((x) => x !== f)) } } }
    },
    signInWithPassword: async (a: unknown) => {
      d.cagri.push(['signInWithPassword', a])
      if (d.kapi) await d.kapi
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
    signOut: async () => ({ error: null }),
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

/** Belge: odak hapsi için keydown dinleyicileri + activeElement; i18n için asgari yüzey. */
const belge = {
  documentElement: { lang: '' },
  title: '',
  querySelector: () => null,
  activeElement: null as unknown,
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
const { AuthProvider } = await import('../AuthContext')
const { AuthModalProvider, useAuthModal } = await import('../AuthModal')
const { authHatasiTurkce, SIFRE_KURALI } = await import('../../lib/authHatalari')
const t = (k: string, o?: Record<string, unknown>) => i18n.t(k as never, o as never) as unknown as string

let modal: ReturnType<typeof useAuthModal> | null = null
function Tetik() {
  modal = useAuthModal()
  return null
}
let c: MiniCizici

const pencere = () => hepsi(c.agac, (d) => d.props.role === 'dialog')
const diyalog = () => tek(c.agac, (d) => d.props.role === 'dialog', 'diyalog')
const arkaPlan = () => tek(c.agac, (d) => d.tip === 'div' && String(d.props.className).includes('fixed inset-0'), 'arka plan')
const girdi = (kosul: (p: Record<string, any>) => boolean, ad: string) => tek(c.agac, (d) => d.tip === 'input' && kosul(d.props), ad)
const eposta = () => girdi((p) => p.type === 'email', 'e-posta')
const sifre = () => girdi((p) => p.type === 'password', 'şifre')
const yerTutucu = (anahtar: string) => girdi((p) => p.placeholder === t(anahtar), anahtar)
const form = () => tek(c.agac, (d) => d.tip === 'form', 'form')
const gonderDugmesi = () => tek(c.agac, (d) => d.tip === 'button' && d.props.type === 'submit', 'gönder')
function tus(key: string, shiftKey = false) {
  const e = olay({ key, shiftKey })
  for (const f of [...(belge.dinleyici.get('keydown') ?? [])]) f(e)
  return e
}
async function ac(cb?: () => void, neden?: 'checkout' | 'download', kip?: 'login' | 'signup') {
  modal!.requireAuth(cb, neden, kip)
  await c.bosalt()
}
async function kayitSekmesi() {
  await c.tikla(dugme(c.agac, t('hesap.kayitOlun')))
}

beforeEach(async () => {
  sb.d.hazir = true
  sb.d.dinleyiciler = []
  sb.d.cagri = []
  sb.d.kapi = null
  sb.d.girisHata = null
  sb.d.kayitSonuc = { data: { session: null }, error: null }
  sb.d.sifirlaHata = null
  belge.activeElement = null
  belge.dinleyici.clear()
  modal = null
  c = new MiniCizici()
  c.ciz(
    <AuthProvider>
      <AuthModalProvider>
        <Tetik />
      </AuthModalProvider>
    </AuthProvider>,
  )
  await c.bosalt()
})
afterEach(() => {
  c.sokHepsi()
  vi.unstubAllGlobals()
  kureselKur()
  vi.restoreAllMocks()
})

describe('AuthModalProvider — bekleyen iş', () => {
  it('requireAuth(cb) → pencere açılır; oturum gelince pencere KAPANIR ve cb TAM BİR KEZ çalışır', async () => {
    const cb = vi.fn()
    expect(pencere()).toHaveLength(0)
    await ac(cb)
    expect(pencere()).toHaveLength(1)
    expect(cb).not.toHaveBeenCalled()
    sb.d.dinleyiciler[0]('SIGNED_IN', { user: { email: 'vet@ornek.test' } })
    await c.bosalt()
    expect(pencere()).toHaveLength(0)
    expect(cb).toHaveBeenCalledTimes(1)
    sb.d.dinleyiciler[0]('TOKEN_REFRESHED', { user: { email: 'vet@ornek.test' } })
    await c.bosalt()
    expect(cb).toHaveBeenCalledTimes(1)
  })

  it('cb verilmeden açılan pencere de oturum gelince kapanır (bekleyen iş yok → çökme yok)', async () => {
    await ac()
    sb.d.dinleyiciler[0]('SIGNED_IN', { user: { email: 'vet@ornek.test' } })
    await c.bosalt()
    expect(pencere()).toHaveLength(0)
  })

  it('kullanıcı pencereyi KAPATTIYSA sonraki girişte vazgeçtiği iş ÇALIŞMAZ', async () => {
    const cb = vi.fn()
    await ac(cb)
    await c.tikla(tek(c.agac, (d) => d.tip === 'button' && d.props['aria-label'] === t('hesap.kapat'), 'kapat'))
    expect(pencere()).toHaveLength(0)
    await ac()
    sb.d.dinleyiciler[0]('SIGNED_IN', { user: { email: 'vet@ornek.test' } })
    await c.bosalt()
    expect(cb).not.toHaveBeenCalled()
  })

  it('sağlayıcı dışında useAuthModal → "useAuthModal must be used within AuthModalProvider"', () => {
    const d = new MiniCizici()
    expect(() => d.ciz(<Tetik />)).toThrow('useAuthModal must be used within AuthModalProvider')
  })
})

describe('AuthModal — giriş', () => {
  it('giriş: e-posta KIRPILIR, şifre aynen; sürerken düğme "bekleyin" + devre dışı, bitince geri döner', async () => {
    let birak!: () => void
    sb.d.kapi = new Promise<void>((r) => (birak = r))
    await ac()
    await c.yaz(eposta(), '  vet@ornek.test  ')
    await c.yaz(sifre(), ' Gizli 123 ')
    const e = await c.gonder(form())
    expect(e.preventDefault).toHaveBeenCalled()
    expect(sb.d.cagri).toContainEqual(['signInWithPassword', { email: 'vet@ornek.test', password: ' Gizli 123 ' }])
    expect(metin(gonderDugmesi())).toBe(t('hesap.bekleyin'))
    expect(gonderDugmesi().props.disabled).toBe(true)
    birak()
    await c.bosalt()
    expect(metin(gonderDugmesi())).toBe(t('hesap.girisYap'))
    expect(gonderDugmesi().props.disabled).toBe(false)
  })

  it('giriş hatası → ürünün Türkçe karşılığı pencerede görünür (ham İngilizce değil)', async () => {
    sb.d.girisHata = { message: 'Invalid login credentials' }
    await ac()
    await c.yaz(eposta(), 'vet@ornek.test')
    await c.yaz(sifre(), 'yanlis')
    await c.gonder(form())
    const yazi = metin(diyalog())
    expect(yazi).toContain(authHatasiTurkce('Invalid login credentials'))
    expect(yazi).not.toContain('Invalid login credentials')
  })

  it('Supabase yapılandırılmamış → servis uyarısı (destek e-postasıyla) ve gönder düğmesi devre dışı', async () => {
    sb.d.hazir = false
    c.sokHepsi()
    c = new MiniCizici()
    c.ciz(
      <AuthProvider>
        <AuthModalProvider>
          <Tetik />
        </AuthModalProvider>
      </AuthProvider>,
    )
    await c.bosalt()
    await ac()
    const { COMPANY } = await import('../../config')
    expect(metin(diyalog())).toContain(t('hesap.pencere.servisYok', { eposta: COMPANY.email }))
    expect(gonderDugmesi().props.disabled).toBe(true)
  })
})

describe('AuthModal — kayıt', () => {
  it('zayıf şifre → sunucuya GİTMEDEN Türkçe kural iletisi', async () => {
    await ac(undefined, 'checkout', 'signup')
    await c.yaz(eposta(), 'vet@ornek.test')
    await c.yaz(sifre(), 'kisa')
    await c.gonder(form())
    expect(sb.d.cagri.filter(([ad]) => ad === 'signUp')).toHaveLength(0)
    expect(metin(diyalog())).toContain(t('hesap.hata.sifreZayif', { aciklama: SIFRE_KURALI.aciklama }))
  })

  it('bireysel hesap → meta YALNIZ hesap türü + kırpılmış ad; abonelik akışında doğrulama bilgisi', async () => {
    await ac(undefined, 'checkout', 'signup')
    await c.yaz(yerTutucu('hesap.alan.adSoyad'), '  Ayşe Yılmaz ')
    await c.yaz(eposta(), ' vet@ornek.test ')
    await c.yaz(sifre(), 'GucluSifre1')
    await c.gonder(form())
    expect(sb.d.cagri).toContainEqual([
      'signUp',
      { email: 'vet@ornek.test', password: 'GucluSifre1', options: { data: { account_type: 'individual', full_name: 'Ayşe Yılmaz' } } },
    ])
    expect(metin(diyalog())).toContain(t('hesap.bilgi.dogrulama'))
    expect(metin(diyalog())).not.toContain(t('hesap.bilgi.dogrulamaIndirme'))
  })

  it('veteriner → klinik / şehir / telefon kırpılmış yazılır; oda no BOŞSA hiç yazılmaz; indirme akışında indirme bilgisi', async () => {
    await ac(undefined, 'download', 'signup')
    await c.tikla(dugme(c.agac, t('hesap.tur.veteriner')))
    expect(dugme(c.agac, t('hesap.tur.veteriner')).props['aria-pressed']).toBe(true)
    await c.yaz(yerTutucu('hesap.alan.adSoyad'), 'Dr. Can')
    await c.yaz(yerTutucu('hesap.alan.klinikAdi'), ' Can Klinik ')
    await c.yaz(yerTutucu('hesap.alan.sehir'), ' İzmir ')
    await c.yaz(yerTutucu('hesap.alan.telefon'), ' 0555 ')
    await c.yaz(yerTutucu('hesap.alan.veterinerOda'), '   ')
    await c.yaz(eposta(), 'can@ornek.test')
    await c.yaz(sifre(), 'GucluSifre1')
    await c.gonder(form())
    expect(sb.d.cagri).toContainEqual([
      'signUp',
      {
        email: 'can@ornek.test',
        password: 'GucluSifre1',
        options: {
          data: { account_type: 'veterinarian', full_name: 'Dr. Can', clinic_name: 'Can Klinik', clinic_city: 'İzmir', phone: '0555' },
        },
      },
    ])
    expect(metin(diyalog())).toContain(t('hesap.bilgi.dogrulamaIndirme'))
  })

  it('veteriner oda no DOLUYSA kırpılıp vet_license olarak yazılır', async () => {
    await ac(undefined, 'download', 'signup')
    await c.tikla(dugme(c.agac, t('hesap.tur.veteriner')))
    await c.yaz(yerTutucu('hesap.alan.veterinerOda'), ' 35-123 ')
    await c.yaz(eposta(), 'can@ornek.test')
    await c.yaz(sifre(), 'GucluSifre1')
    await c.gonder(form())
    const kayit = sb.d.cagri.find(([ad]) => ad === 'signUp')![1] as { options: { data: Record<string, string> } }
    expect(kayit.options.data.vet_license).toBe('35-123')
  })

  it('araştırmacı → kurum / bölüm yazılır, unvan doluysa academic_title; kurumsal e-posta yer tutucusu', async () => {
    await ac(undefined, 'checkout', 'signup')
    await c.tikla(dugme(c.agac, t('hesap.tur.arastirmaci')))
    expect(eposta().props.placeholder).toBe(t('hesap.alan.epostaKurumsal'))
    await c.yaz(yerTutucu('hesap.alan.kurumAdi'), ' İKÇÜ ')
    await c.yaz(yerTutucu('hesap.alan.bolum'), ' EEM ')
    await c.yaz(yerTutucu('hesap.alan.unvan'), ' Doç. Dr. ')
    await c.yaz(eposta(), 'ars@ornek.test')
    await c.yaz(sifre(), 'GucluSifre1')
    await c.gonder(form())
    const kayit = sb.d.cagri.find(([ad]) => ad === 'signUp')![1] as { options: { data: Record<string, string> } }
    expect(kayit.options.data).toEqual({
      account_type: 'researcher',
      full_name: '',
      institution: 'İKÇÜ',
      department: 'EEM',
      academic_title: 'Doç. Dr.',
    })
  })

  it('araştırmacı unvan BOŞSA academic_title hiç yazılmaz', async () => {
    await ac(undefined, 'checkout', 'signup')
    await c.tikla(dugme(c.agac, t('hesap.tur.arastirmaci')))
    await c.yaz(eposta(), 'ars@ornek.test')
    await c.yaz(sifre(), 'GucluSifre1')
    await c.gonder(form())
    const kayit = sb.d.cagri.find(([ad]) => ad === 'signUp')![1] as { options: { data: Record<string, string> } }
    expect(kayit.options.data).not.toHaveProperty('academic_title')
  })

  it('kayıt hatası → Türkçe karşılık gösterilir, doğrulama bilgisi GÖSTERİLMEZ', async () => {
    sb.d.kayitSonuc = { data: { session: null }, error: { message: 'User already registered' } }
    await ac(undefined, 'download', 'signup')
    await c.yaz(eposta(), 'vet@ornek.test')
    await c.yaz(sifre(), 'GucluSifre1')
    await c.gonder(form())
    expect(metin(diyalog())).toContain(authHatasiTurkce('User already registered'))
    expect(metin(diyalog())).not.toContain(t('hesap.bilgi.dogrulamaIndirme'))
  })

  it('doğrulama gerekmiyorsa (oturum döndü) bilgi iletisi YOK', async () => {
    sb.d.kayitSonuc = { data: { session: { access_token: 'jwt' } }, error: null }
    await ac(undefined, 'checkout', 'signup')
    await c.yaz(eposta(), 'vet@ornek.test')
    await c.yaz(sifre(), 'GucluSifre1')
    await c.gonder(form())
    expect(metin(diyalog())).not.toContain(t('hesap.bilgi.dogrulama'))
  })
})

describe('AuthModal — şifremi unuttum', () => {
  it('e-posta boş → "e-posta girin" uyarısı ve sunucuya GİDİLMEZ', async () => {
    await ac()
    await c.yaz(eposta(), '   ')
    await c.tikla(dugme(c.agac, t('hesap.sifremiUnuttum')))
    expect(metin(diyalog())).toContain(t('hesap.hata.epostaGirin'))
    expect(sb.d.cagri.filter(([ad]) => ad === 'resetPasswordForEmail')).toHaveLength(0)
  })

  it('e-posta dolu → KIRPILMIŞ e-postayla sıfırlama; başarıda "gönderildi" bilgisi', async () => {
    await ac()
    await c.yaz(eposta(), ' vet@ornek.test ')
    await c.tikla(dugme(c.agac, t('hesap.sifremiUnuttum')))
    expect(sb.d.cagri).toContainEqual(['resetPasswordForEmail', ['vet@ornek.test', { redirectTo: 'https://site-ornek.test/sifre-sifirla' }]])
    expect(metin(diyalog())).toContain(t('hesap.bilgi.sifirlamaGonderildi'))
  })

  it('sıfırlama hatası → Türkçe karşılık; "gönderildi" bilgisi YOK', async () => {
    sb.d.sifirlaHata = { message: 'Email rate limit exceeded' }
    await ac()
    await c.yaz(eposta(), 'vet@ornek.test')
    await c.tikla(dugme(c.agac, t('hesap.sifremiUnuttum')))
    expect(metin(diyalog())).toContain(authHatasiTurkce('Email rate limit exceeded'))
    expect(metin(diyalog())).not.toContain(t('hesap.bilgi.sifirlamaGonderildi'))
  })
})

describe('AuthModal — klavye, odak ve tıklama', () => {
  it('açılınca odak diyaloğa alınır; Esc (form boş) → preventDefault ve pencere kapanır; kapanınca odak ÖNCEKİ öğeye döner, dinleyici kalkar', async () => {
    const onceki = { focus: vi.fn() }
    belge.activeElement = onceki
    await ac()
    expect(diyalog().dom.odak).toBe(1)
    expect(belge.dinleyici.get('keydown')?.size).toBe(1)
    const e = tus('Escape')
    expect(e.preventDefault).toHaveBeenCalled()
    await c.bosalt()
    expect(pencere()).toHaveLength(0)
    expect(onceki.focus).toHaveBeenCalledTimes(1)
    expect(belge.dinleyici.get('keydown')?.size).toBe(0)
  })

  it('Esc dolu formda → kapatmaz, pencere içi onay sorusu çıkar', async () => {
    await ac()
    await c.yaz(eposta(), 'vet@ornek.test')
    tus('Escape')
    await c.bosalt()
    expect(pencere()).toHaveLength(1)
    expect(metin(diyalog())).toContain(t('hesap.pencere.kapatmaSorusu'))
  })

  it('Tab son öğedeyken → İLK öğeye döner; Shift+Tab ilk öğedeyken → SONA; ortadaki öğede tarayıcıya bırakılır', async () => {
    await ac()
    const ilk = { focus: vi.fn() }
    const orta = { focus: vi.fn() }
    const son = { focus: vi.fn() }
    diyalog().dom.querySelectorAll = () => [ilk, orta, son]
    belge.activeElement = son
    const e1 = tus('Tab')
    expect(e1.preventDefault).toHaveBeenCalled()
    expect(ilk.focus).toHaveBeenCalledTimes(1)
    belge.activeElement = ilk
    const e2 = tus('Tab', true)
    expect(e2.preventDefault).toHaveBeenCalled()
    expect(son.focus).toHaveBeenCalledTimes(1)
    belge.activeElement = orta
    const e3 = tus('Tab')
    expect(e3.preventDefault).not.toHaveBeenCalled()
    expect(ilk.focus).toHaveBeenCalledTimes(1)
  })

  it('odaklanabilir öğe yoksa Tab ve başka tuşlar bir şey yapmaz', async () => {
    await ac()
    diyalog().dom.querySelectorAll = () => []
    expect(tus('Tab').preventDefault).not.toHaveBeenCalled()
    expect(tus('a').preventDefault).not.toHaveBeenCalled()
    await c.bosalt()
    expect(pencere()).toHaveLength(1)
  })

  it('diyalog İÇİNE basmak arka plana yayılmaz (stopPropagation); arka planın kendisine basmak (boş form) kapatır, çocuğuna basmak kapatmaz', async () => {
    await ac()
    const ic = olay()
    diyalog().props.onMouseDown(ic)
    expect(ic.stopPropagation).toHaveBeenCalled()
    const ap = arkaPlan()
    ap.props.onMouseDown(olay({ target: diyalog().dom, currentTarget: ap.dom }))
    await c.bosalt()
    expect(pencere()).toHaveLength(1)
    const ap2 = arkaPlan()
    ap2.props.onMouseDown(olay({ target: ap2.dom, currentTarget: ap2.dom }))
    await c.bosalt()
    expect(pencere()).toHaveLength(0)
  })
})

describe('AuthModal — sekme geçişi', () => {
  it('giriş → kayıt → giriş: başlık / gönder metni değişir, eski hata iletisi silinir; alt başlık akışa göre', async () => {
    sb.d.girisHata = { message: 'Invalid login credentials' }
    await ac(undefined, 'download')
    expect(metin(diyalog())).toContain(t('hesap.pencere.indirmeAciklama'))
    await c.yaz(eposta(), 'vet@ornek.test')
    await c.yaz(sifre(), 'x')
    await c.gonder(form())
    expect(metin(diyalog())).toContain(authHatasiTurkce('Invalid login credentials'))
    await kayitSekmesi()
    expect(tek(c.agac, (d) => d.tip === 'h2', 'başlık').cocuklar).toEqual([t('hesap.hesapOlustur')])
    expect(metin(gonderDugmesi())).toBe(t('hesap.kayitOl'))
    expect(metin(diyalog())).not.toContain(authHatasiTurkce('Invalid login credentials'))
    await c.tikla(dugme(c.agac, t('hesap.girisYapin')))
    expect(tek(c.agac, (d) => d.tip === 'h2', 'başlık').cocuklar).toEqual([t('hesap.girisYap')])
    expect(metin(gonderDugmesi())).toBe(t('hesap.girisYap'))
  })

  it('kayıt sekmesinden girişe dönerken bilgi iletisi de silinir', async () => {
    await ac(undefined, 'checkout', 'signup')
    await c.yaz(eposta(), 'vet@ornek.test')
    await c.yaz(sifre(), 'GucluSifre1')
    await c.gonder(form())
    expect(metin(diyalog())).toContain(t('hesap.bilgi.dogrulama'))
    await c.tikla(dugme(c.agac, t('hesap.girisYapin')))
    expect(metin(diyalog())).not.toContain(t('hesap.bilgi.dogrulama'))
    expect(metin(diyalog())).toContain(t('hesap.pencere.abonelikAciklama'))
  })
})
