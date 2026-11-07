// Author: mertaygn, cglrgrkn
/**
 * KP-3 C · src/pages/ResetPassword.tsx · sözleşmeler (GERÇEK sayfa + GERÇEK şifre kuralı / hata çevirisi; sahte EN ALT katta — Supabase
 * `onAuthStateChange` / `getSession` / `updateUser`):
 *  - kurtarma oturumu gelmeden alanlar + düğme kilitli, "doğrulanıyor" + ana sayfa bağlantısı; PASSWORD_RECOVERY / SIGNED_IN ya da hazır
 *    oturum kilidi açar, ilgisiz olay açmaz; ayrılınca abonelik kalkar; Supabase yoksa dinleyici kurulmaz,
 *  - zayıf / eşleşmeyen şifre sunucuya GİTMEZ; geçerli → updateUser({password}), sürerken kilitli, başarı ekranı; ret Türkçe, yeni denemede silinir.
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

const sb = vi.hoisted(() => {
  const d = {
    hazir: true,
    oturum: null as unknown,
    dinleyiciler: [] as ((olay: string) => void)[],
    abonelikKalkti: 0,
    cagri: [] as unknown[],
    hata: null as null | { message: string },
    kapi: null as Promise<void> | null,
  }
  const auth = {
    onAuthStateChange: (f: (olay: string) => void) => {
      d.dinleyiciler.push(f)
      return { data: { subscription: { unsubscribe: () => void d.abonelikKalkti++ } } }
    },
    getSession: async () => ({ data: { session: d.oturum } }),
    updateUser: async (a: unknown) => {
      d.cagri.push(a)
      if (d.kapi) await d.kapi
      return { data: {}, error: d.hata }
    },
  }
  return { d, istemci: { auth } }
})
vi.mock('../../lib/supabase', () => ({
  get supabaseReady() {
    return sb.d.hazir
  },
  supabase: sb.istemci,
}))
vi.mock('react-router-dom', () => ({
  Link: ({ to, className, children }: { to: string; className?: string; children: unknown }) =>
    React.createElement('a', { href: to, className }, children as React.ReactNode),
}))

function kureselKur() {
  const depo = new Map<string, string>([['pemf.dil', 'tr']])
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => depo.get(k) ?? null,
    setItem: (k: string, v: string) => void depo.set(k, String(v)),
    removeItem: (k: string) => void depo.delete(k),
  })
  vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })
}
kureselKur()

const i18n = (await import('../../i18n')).default
const ResetPassword = (await import('../ResetPassword')).default
const { authHatasiTurkce, SIFRE_KURALI } = await import('../../lib/authHatalari')
const t = (k: string, o?: Record<string, unknown>) => i18n.t(k as never, o as never) as unknown as string

let c: MiniCizici
const GECERLI = 'Guclu-Sifre-2026!'

async function ciz() {
  c = new MiniCizici()
  c.ciz(<ResetPassword />)
  await c.bosalt()
}
const sifre = (anahtar: string) => tek(c.agac, (d) => d.tip === 'input' && d.props.placeholder === t(anahtar), anahtar)
const formu = () => tek(c.agac, (d) => d.tip === 'form', 'form')
const gonderDugmesi = () => tek(c.agac, (d) => d.tip === 'button' && d.props.type === 'submit', 'gönder')
async function kurtarmaGelir() {
  sb.d.dinleyiciler[0]('PASSWORD_RECOVERY')
  await c.bosalt()
}
async function doldurGonder(a: string, b: string) {
  await c.yaz(sifre('hesap.sifirla.yeniSifre'), a)
  await c.yaz(sifre('hesap.sifirla.yeniSifreTekrar'), b)
  await c.gonder(formu())
  await c.bosalt()
}

beforeEach(async () => {
  sb.d.hazir = true
  sb.d.oturum = null
  sb.d.dinleyiciler = []
  sb.d.abonelikKalkti = 0
  sb.d.cagri = []
  sb.d.hata = null
  sb.d.kapi = null
  await ciz()
})
afterEach(() => {
  c.sokHepsi()
  vi.unstubAllGlobals()
  kureselKur()
})

describe('KP-3 · ResetPassword — kurtarma oturumu', () => {
  it('kurtarma oturumu GELMEDEN alanlar ve düğme kilitli, "doğrulanıyor" + ana sayfa bağlantısı', () => {
    expect(sifre('hesap.sifirla.yeniSifre').props.disabled).toBe(true)
    expect(sifre('hesap.sifirla.yeniSifreTekrar').props.disabled).toBe(true)
    expect(gonderDugmesi().props.disabled).toBe(true)
    expect(metin(c.agac)).toContain(t('hesap.sifirla.dogrulaniyor'))
    expect(hepsi(c.agac, (d) => d.tip === 'a' && d.props.href === '/')).toHaveLength(1)
  })

  it('PASSWORD_RECOVERY (ya da SIGNED_IN) olayı kilidi açar; ilgisiz olay AÇMAZ', async () => {
    sb.d.dinleyiciler[0]('TOKEN_REFRESHED')
    await c.bosalt()
    expect(gonderDugmesi().props.disabled).toBe(true)
    await kurtarmaGelir()
    expect(gonderDugmesi().props.disabled).toBe(false)
    expect(metin(c.agac)).not.toContain(t('hesap.sifirla.dogrulaniyor'))
    c.sokHepsi()
    await ciz()
    sb.d.dinleyiciler[sb.d.dinleyiciler.length - 1]('SIGNED_IN')
    await c.bosalt()
    expect(gonderDugmesi().props.disabled).toBe(false)
  })

  it('bağlantıyla zaten kurulmuş oturum varsa (getSession) olay beklenmeden kilit açılır; ayrılınca abonelik kalkar', async () => {
    c.sokHepsi()
    const once = sb.d.abonelikKalkti
    expect(once).toBe(1)
    sb.d.oturum = { user: { email: 'vet@ornek.test' } }
    await ciz()
    expect(gonderDugmesi().props.disabled).toBe(false)
  })

  it('Supabase yapılandırılmamışsa dinleyici KURULMAZ, sayfa kilitli kalır (çökme yok)', async () => {
    c.sokHepsi()
    sb.d.dinleyiciler = []
    sb.d.hazir = false
    await ciz()
    expect(sb.d.dinleyiciler).toHaveLength(0)
    expect(gonderDugmesi().props.disabled).toBe(true)
  })
})

describe('KP-3 · ResetPassword — yeni şifre', () => {
  it('zayıf şifre → kural iletisi, sunucuya GİDİLMEZ', async () => {
    await kurtarmaGelir()
    await doldurGonder('kisa', 'kisa')
    expect(metin(c.agac)).toContain(t('hesap.hata.sifreZayif', { aciklama: SIFRE_KURALI.aciklama }))
    expect(sb.d.cagri).toHaveLength(0)
  })

  it('iki şifre eşleşmiyor → eşleşmiyor iletisi, sunucuya GİDİLMEZ', async () => {
    await kurtarmaGelir()
    await doldurGonder(GECERLI, GECERLI + 'x')
    expect(metin(c.agac)).toContain(t('hesap.hata.sifrelerEslesmiyor'))
    expect(sb.d.cagri).toHaveLength(0)
  })

  it('geçerli + eşleşen → updateUser({password}); sürerken "güncelleniyor" + kilitli; başarı → "güncellendi" ekranı, form kalkar', async () => {
    await kurtarmaGelir()
    let ac!: () => void
    sb.d.kapi = new Promise<void>((r) => (ac = r))
    await c.yaz(sifre('hesap.sifirla.yeniSifre'), GECERLI)
    await c.yaz(sifre('hesap.sifirla.yeniSifreTekrar'), GECERLI)
    const g = c.gonder(formu())
    await c.bosalt()
    expect(metin(gonderDugmesi())).toBe(t('hesap.sifirla.guncelleniyor'))
    expect(gonderDugmesi().props.disabled).toBe(true)
    ac()
    await g
    await c.bosalt()
    expect(sb.d.cagri).toEqual([{ password: GECERLI }])
    expect(hepsi(c.agac, (d) => d.tip === 'form')).toHaveLength(0)
    expect(metin(c.agac)).toContain(t('hesap.sifirla.guncellendi'))
    expect(metin(c.agac)).toContain(t('hesap.sifirla.girisYapabilirsiniz'))
  })

  it('sunucu reddi → ham İngilizce değil Türkçe karşılık; form yerinde, düğme yeniden etkin; önceki hata yeni denemede SİLİNİR', async () => {
    await kurtarmaGelir()
    sb.d.hata = { message: 'New password should be different from the old password.' }
    await doldurGonder(GECERLI, GECERLI)
    const beklenen = authHatasiTurkce('New password should be different from the old password.')
    expect(metin(c.agac)).toContain(beklenen)
    expect(metin(c.agac)).not.toContain('New password should be different')
    expect(gonderDugmesi().props.disabled).toBe(false)
    sb.d.hata = null
    // tur 2 (yaşayan mutant: yeni denemede eski hata silinmiyordu): ikinci deneme SÜRERKEN eski hata görünmemeli
    let ac!: () => void
    sb.d.kapi = new Promise<void>((r) => (ac = r))
    const g = c.gonder(formu())
    await c.bosalt()
    expect(metin(gonderDugmesi())).toBe(t('hesap.sifirla.guncelleniyor'))
    expect(metin(c.agac)).not.toContain(beklenen)
    ac()
    await g
    await c.bosalt()
    expect(metin(c.agac)).toContain(t('hesap.sifirla.guncellendi'))
  })
})
