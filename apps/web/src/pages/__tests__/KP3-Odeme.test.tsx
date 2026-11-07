// Author: mertaygn, cglrgrkn
/**
 * KP-3 C · src/pages/Odeme.tsx · sözleşmeler (satış AÇIK sahtesi FREE_MODE=false; GERÇEK `initCheckout`; sahte EN ALT katta — Supabase oturum
 * belirteci + `fetch`):
 *  - giriş yoksa (hazır, oturum yok) açılışta giriş penceresi istenir ve formda "giriş yapın" uyarısı görünür; oturumsuz gönder → yine giriş
 *    penceresi, sunucuya GİDİLMEZ,
 *  - mesafeli satış onayı işaretlenmeden gönder → onay iletisi, sunucuya GİDİLMEZ,
 *  - onaylı gönder → `/api/checkout`'a plan (tier / yıllık / araştırma) + kutulara yazılan müşteri bilgisi + oturum belirteci; sürerken düğme
 *    "hazırlanıyor" + devre dışı; iyzico içeriği güvenli ödeme kartına GÖMÜLÜR (createContextualFragment — script'ler çalışsın), form kalkar,
 *  - sunucu hatası ham metin değil makine-okur koddan Türkçe (409 zaten abone · TC biçimi); belirteç yoksa (oturum düşmüş) giriş penceresi.
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
  ready: true,
  requireAuth: null as unknown as ReturnType<typeof vi.fn>,
  arama: 'tier=pro_plus&yearly=1&research=1',
  belirtec: 'sb-belirtec-1' as string | null,
  ucretsiz: false,
}))
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ session: durum.session, ready: durum.ready, email: null, loading: false }),
  AuthProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../../context/AuthModal', () => ({
  useAuthModal: () => ({ requireAuth: durum.requireAuth }),
  AuthModalProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('react-router-dom', () => ({
  useSearchParams: () => [new URLSearchParams(durum.arama)],
  Link: ({ to, className, children }: { to: string; className?: string; children: unknown }) =>
    React.createElement('a', { href: to, className }, children as React.ReactNode),
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

const parcalar: string[] = []
function kureselKur() {
  const depo = new Map<string, string>([['pemf.dil', 'tr']])
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => depo.get(k) ?? null,
    setItem: (k: string, v: string) => void depo.set(k, String(v)),
    removeItem: (k: string) => void depo.delete(k),
  })
  vi.stubGlobal('document', {
    documentElement: { lang: '' },
    title: '',
    querySelector: () => null,
    createRange: () => ({
      createContextualFragment: (h: string) => {
        parcalar.push(h)
        return { parca: h }
      },
    }),
  })
  vi.stubGlobal('window', { location: { origin: 'https://site-ornek.test' } })
}
kureselKur()

const i18n = (await import('../../i18n')).default
const Odeme = (await import('../Odeme')).default
const { PLANS, RESEARCH_ADDON } = await import('../../config')
const { tl } = await import('../../lib/para')
const t = (k: string, o?: Record<string, unknown>) => i18n.t(k as never, o as never) as unknown as string

let c: MiniCizici
let istekler: { url: string; govde: Record<string, any> }[]
let yanit: { ok: boolean; status: number; govde: unknown }
let kapi: Promise<void> | null

function fetchKur() {
  vi.stubGlobal('fetch', async (url: string, o: { body: string }) => {
    istekler.push({ url, govde: JSON.parse(o.body) })
    if (kapi) await kapi
    return { ok: yanit.ok, status: yanit.status, json: async () => yanit.govde }
  })
}
async function ciz() {
  c = new MiniCizici()
  c.ciz(<Odeme />)
  await c.bosalt()
}
const formlar = () => hepsi(c.agac, (d) => d.tip === 'form')
const yerTutucu = (anahtar: string) =>
  tek(c.agac, (d) => (d.tip === 'input' || d.tip === 'textarea') && d.props.placeholder === t(anahtar), anahtar)
const onay = () => tek(c.agac, (d) => d.tip === 'input' && d.props.type === 'checkbox', 'onay kutusu')
const gonderDugmesi = () => tek(c.agac, (d) => d.tip === 'button' && d.props.type === 'submit', 'gönder')
async function doldur() {
  await c.yaz(yerTutucu('odeme.ad'), 'Ayşe')
  await c.yaz(yerTutucu('odeme.soyad'), 'Yılmaz')
  await c.yaz(yerTutucu('odeme.tc'), '12345678901')
  await c.yaz(yerTutucu('odeme.telefon'), '+905551112233')
  await c.yaz(yerTutucu('hesap.alan.sehir'), 'İzmir')
  await c.yaz(yerTutucu('odeme.adres'), 'Atatürk Cd. 1')
  await c.yaz(yerTutucu('odeme.posta'), '35000')
}
const ICERIK = '<script src="https://iyzico.ornek/f.js"></script>'

beforeEach(async () => {
  istekler = []
  parcalar.length = 0
  kapi = null
  yanit = { ok: true, status: 200, govde: { content: ICERIK } }
  durum.session = { user: { email: 'vet@ornek.test' } }
  durum.ready = true
  durum.belirtec = 'sb-belirtec-1'
  durum.arama = 'tier=pro_plus&yearly=1&research=1'
  durum.requireAuth = vi.fn()
  durum.ucretsiz = false
  fetchKur()
  await ciz()
})
afterEach(() => {
  c.sokHepsi()
  vi.unstubAllGlobals()
  kureselKur()
})

describe('KP-3 · Odeme — giriş kapısı', () => {
  it('oturum YOKSA (hazır) açılışta giriş penceresi istenir, formda "giriş yapın" uyarısı; gönder → yine pencere, sunucuya GİDİLMEZ', async () => {
    c.sokHepsi()
    durum.session = null
    await ciz()
    expect(durum.requireAuth).toHaveBeenCalledTimes(1)
    expect(metin(c.agac)).toContain(t('odeme.girisYapin'))
    await c.isaretleKutu(onay(), true)
    await c.gonder(formlar()[0])
    expect(durum.requireAuth).toHaveBeenCalledTimes(2)
    expect(istekler).toHaveLength(0)
  })

  it('oturum hazır DEĞİLSE (yükleniyor) pencere istenmez; oturum VARKEN de istenmez, uyarı yok', async () => {
    expect(durum.requireAuth).not.toHaveBeenCalled()
    expect(metin(c.agac)).not.toContain(t('odeme.girisYapin'))
    c.sokHepsi()
    durum.session = null
    durum.ready = false
    await ciz()
    expect(durum.requireAuth).not.toHaveBeenCalled()
  })
})

describe('KP-3 · Odeme — onay ve gönderim', () => {
  it('mesafeli satış onayı İŞARETLENMEDEN gönder → onay iletisi, sunucuya GİDİLMEZ; düğme onaysız devre dışı', async () => {
    expect(gonderDugmesi().props.disabled).toBe(true)
    const e = await c.gonder(formlar()[0])
    expect(e.preventDefault).toHaveBeenCalled()
    expect(metin(c.agac)).toContain(t('odeme.onayGerekli'))
    expect(istekler).toHaveLength(0)
  })

  it('onaylı gönder → /api/checkout gövdesi plan + kutulardaki müşteri + belirteç; sürerken "hazırlanıyor"; iyzico içeriği GÖMÜLÜR, form kalkar', async () => {
    await doldur()
    await c.isaretleKutu(onay(), true)
    expect(gonderDugmesi().props.disabled).toBe(false)
    let ac!: () => void
    kapi = new Promise<void>((r) => (ac = r))
    const gonderim = c.gonder(formlar()[0])
    await c.bosalt()
    expect(metin(gonderDugmesi())).toBe(t('odeme.hazirlaniyor'))
    expect(gonderDugmesi().props.disabled).toBe(true)
    ac()
    await gonderim
    await c.bosalt()
    expect(istekler).toHaveLength(1)
    expect(istekler[0].url).toBe('/api/checkout')
    expect(istekler[0].govde).toMatchObject({
      tier: 'pro_plus',
      yearly: true,
      research: true,
      token: 'sb-belirtec-1',
      origin: 'https://site-ornek.test',
      customer: {
        name: 'Ayşe',
        surname: 'Yılmaz',
        identityNumber: '12345678901',
        gsmNumber: '+905551112233',
        city: 'İzmir',
        address: 'Atatürk Cd. 1',
        zipCode: '35000',
      },
    })
    expect(formlar()).toHaveLength(0)
    expect(metin(c.agac)).toContain(t('odeme.guvenliOdeme'))
    expect(parcalar).toEqual([ICERIK])
    const yuva = tek(c.agac, (d) => d.tip === 'div' && (d.dom.eklenen?.length ?? 0) === 1, 'script yuvası')
    expect(yuva.dom.eklenen[0]).toEqual({ parca: ICERIK })
    await c.bosalt()
    expect(parcalar).toHaveLength(1)
  })

  it('özet: yıllık Pro+ + Araştırma → bugün tahsil = yıllık plan + YILLIK eklenti (2 ay bedava eklentiye de); aylık eşdeğer satırı', () => {
    const plan = PLANS.find((p) => p.tier === 'pro_plus')!
    const yazi = metin(c.agac)
    expect(yazi).toContain(t('odeme.bugunTahsil'))
    expect(yazi).toContain(t('odeme.aylikEsdeger'))
    expect(yazi).toContain(t('odeme.arastirmaEklendi'))
    expect(yazi).toContain(tl(plan.yearly + RESEARCH_ADDON.yearly))
  })

  it('aylık Pro (araştırmasız) → tahsil = aylık plan; aylık eşdeğer satırı YOK', async () => {
    c.sokHepsi()
    durum.arama = 'tier=pro'
    await ciz()
    const plan = PLANS.find((p) => p.tier === 'pro')!
    const yazi = metin(c.agac)
    expect(yazi).toContain(tl(plan.monthly))
    expect(yazi).not.toContain(t('odeme.aylikEsdeger'))
    expect(yazi).not.toContain(t('odeme.arastirmaEklendi'))
  })
})

describe('KP-3 · Odeme — sunucu hataları', () => {
  async function hataliGonder(g: unknown, durumKodu = 400) {
    yanit = { ok: false, status: durumKodu, govde: g }
    await doldur()
    await c.isaretleKutu(onay(), true)
    await c.gonder(formlar()[0])
    await c.bosalt()
  }
  it('409 already_subscribed → "zaten abone" Türkçe iletisi (ham metin değil); form yerinde, düğme yeniden etkin, içerik GÖMÜLMEZ', async () => {
    await hataliGonder({ error: 'already_subscribed', message: 'Subscription exists (raw)' }, 409)
    const yazi = metin(c.agac)
    expect(yazi).toContain(t('hesap.odeme.zatenAbone'))
    expect(yazi).not.toContain('Subscription exists (raw)')
    expect(formlar()).toHaveLength(1)
    expect(gonderDugmesi().props.disabled).toBe(false)
    expect(parcalar).toHaveLength(0)
  })
  it('müşteri alanı biçim hatası (TC) → TC biçim iletisi', async () => {
    await hataliGonder({ error: 'customer', alan: 'identityNumber', sebep: 'bicim' })
    expect(metin(c.agac)).toContain(t('hesap.odeme.tcBicim'))
  })
  it('oturum belirteci YOKSA (oturum düştü) → giriş penceresi, sunucuya GİDİLMEZ, form yerinde', async () => {
    durum.belirtec = null
    await doldur()
    await c.isaretleKutu(onay(), true)
    await c.gonder(formlar()[0])
    await c.bosalt()
    expect(durum.requireAuth).toHaveBeenCalledTimes(1)
    expect(istekler).toHaveLength(0)
    expect(formlar()).toHaveLength(1)
  })
})

describe('KP-3 · Odeme — ücretsiz kip ve plan savunması', () => {
  it('FREE_MODE açıkken (adres çubuğundan /odeme) ödeme formu ÇİZİLMEZ, tahsilat başlamaz; "ücretsiz" + indirme bağlantısı', async () => {
    c.sokHepsi()
    durum.ucretsiz = true
    await ciz()
    expect(formlar()).toHaveLength(0)
    const yazi = metin(c.agac)
    expect(yazi).toContain(t('odeme.ucretsizBaslik'))
    expect(yazi).not.toContain(t('odeme.bugunTahsil'))
    expect(hepsi(c.agac, (d) => d.tip === 'a' && d.props.href === '/download')).toHaveLength(1)
    expect(istekler).toHaveLength(0)
  })

  it('istenen plan listede YOKSA (yapılandırma kayması) form ÇİZİLMEZ; "plan yok" + fiyatlandırmaya dönüş', async () => {
    const liste = PLANS as unknown as unknown[]
    const i = PLANS.findIndex((p) => p.tier === 'pro_plus')
    const [cikan] = liste.splice(i, 1)
    try {
      c.sokHepsi()
      durum.arama = 'tier=pro_plus'
      await ciz()
      expect(formlar()).toHaveLength(0)
      expect(metin(c.agac)).toContain(t('odeme.planYok'))
      expect(hepsi(c.agac, (d) => d.tip === 'a' && d.props.href === '/pricing')).toHaveLength(1)
    } finally {
      liste.splice(i, 0, cikan)
    }
  })
})
