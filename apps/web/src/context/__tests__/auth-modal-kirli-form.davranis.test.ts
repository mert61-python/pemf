// Author: mertaygn, cglrgrkn
/**
 * D5.09 (B-7.18) — giriş/kayıt penceresinin KİRLİ FORM onayı DAVRANIŞLA ölçülür (kaynak metni / yorum araması DEĞİL).
 *
 * ÖLÇÜLEN KÖRLÜK: eski kapı (`auth-modal-focus.test.ts`) `expect(SRC).toContain('window.confirm')` ile yalnız bir YORUMDAKİ
 * kelimeyi buluyordu (ürün 2026-08-20'den beri modal İÇİ onay kullanıyor). `if (dirty)` → `if (void dirty)` (uzun kayıt formu tek
 * tıkla siliniyor) YEŞİL kalıyordu; yorumu yeniden yazan zararsız düzenleme ise KIRMIZIYA düşüyordu.
 *
 * DÜZENEK: site testlerinde DOM ortamı yok (jsdom / happy-dom kurulu değil). GERÇEK `AuthModal` işlevi — dışa aktarılmaz, GERÇEK
 * `AuthModalProvider`ın açıkken çizdiği öğeden alınır — küçük bir kanca koşucusuyla çizilir: `useState` / `useRef` / `useCallback` /
 * `useEffect` React sözleşmesiyle (yuva sırası, kararlı ayarlayıcı, bağımlılık karşılaştırması, efektten önce eski temizlik) taklit
 * edilir; dönen GERÇEK öğe ağacındaki GERÇEK işleyiciler (alanların onChange'i, kapat düğmesi, arka plan, Esc, onay düğmeleri) çağrılır.
 * "Pencere kapandı mı" = sağlayıcı artık modalı ÇİZMİYOR (bileşenin kendi `onClose` sözleşmesi uçtan uca). Katalog GERÇEK (Türkçe
 * metin); yalnız oturum bağlamı (AuthContext) sahtelenir.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true

const kanca = vi.hoisted(() => {
  type Yuva = { deger: unknown; deps?: readonly unknown[]; temizle?: unknown; ayar?: (v: unknown) => void }
  type Ornek = { yuvalar: Yuva[]; i: number; bekleyen: (() => void)[]; kirli: boolean }
  let aktif: Ornek | null = null
  const simdiki = (): Ornek => {
    if (!aktif) throw new Error('kanca çizim DIŞINDA çağrıldı')
    return aktif
  }
  const degisti = (a: readonly unknown[] | undefined, b: readonly unknown[] | undefined): boolean =>
    !a || !b || a.length !== b.length || a.some((x, j) => !Object.is(x, b[j]))
  return {
    yeni: (): Ornek => ({ yuvalar: [], i: 0, bekleyen: [], kirli: false }),
    /** Bileşeni çizer; efektleri çizimden SONRA koşar; durum değiştikçe (React gibi) yeniden çizer. */
    ciz(o: Ornek, bilesen: unknown, props: unknown): unknown {
      for (let tur = 0; tur < 25; tur++) {
        o.kirli = false
        o.i = 0
        o.bekleyen = []
        aktif = o
        let agac: unknown
        try {
          agac = (bilesen as (p: unknown) => unknown)(props)
        } finally {
          aktif = null
        }
        for (const f of o.bekleyen) f()
        if (!o.kirli) return agac
      }
      throw new Error('çizim durulmadı (sonsuz güncelleme)')
    },
    /** Söküm: efekt temizlikleri. */
    sok(o: Ornek): void {
      for (const y of o.yuvalar) if (typeof y?.temizle === 'function') (y.temizle as () => void)()
    },
    useState(bas: unknown): [unknown, (v: unknown) => void] {
      const o = simdiki()
      const k = o.i++
      if (!o.yuvalar[k]) {
        const y: Yuva = { deger: typeof bas === 'function' ? (bas as () => unknown)() : bas }
        y.ayar = (v: unknown) => {
          const yeni = typeof v === 'function' ? (v as (d: unknown) => unknown)(y.deger) : v
          if (!Object.is(yeni, y.deger)) {
            y.deger = yeni
            o.kirli = true
          }
        }
        o.yuvalar[k] = y
      }
      const y = o.yuvalar[k]
      return [y.deger, y.ayar!]
    },
    useRef(bas: unknown): unknown {
      const o = simdiki()
      const k = o.i++
      if (!o.yuvalar[k]) o.yuvalar[k] = { deger: { current: bas } }
      return o.yuvalar[k].deger
    },
    useCallback(fn: unknown, deps?: readonly unknown[]): unknown {
      const o = simdiki()
      const k = o.i++
      const y = o.yuvalar[k]
      if (!y || degisti(y.deps, deps)) o.yuvalar[k] = { deger: fn, deps }
      return o.yuvalar[k].deger
    },
    useEffect(fn: () => unknown, deps?: readonly unknown[]): void {
      const o = simdiki()
      const k = o.i++
      const y = o.yuvalar[k]
      if (y && !degisti(y.deps, deps)) return
      const yuva: Yuva = { deger: undefined, deps, temizle: y?.temizle }
      o.yuvalar[k] = yuva
      o.bekleyen.push(() => {
        if (typeof yuva.temizle === 'function') (yuva.temizle as () => void)()
        yuva.temizle = fn()
      })
    },
  }
})

const ceviri = vi.hoisted(() => ({
  t: (k: string, _o?: Record<string, unknown>): string => k,
  i18n: { language: 'tr' } as unknown,
}))

vi.mock('react', async (asil) => {
  const gercek = await asil<Record<string, unknown>>()
  return {
    ...gercek,
    useState: kanca.useState,
    useRef: kanca.useRef,
    useCallback: kanca.useCallback,
    useEffect: kanca.useEffect,
  }
})
vi.mock('react-i18next', async (asil) => ({
  ...(await asil<Record<string, unknown>>()),
  useTranslation: () => ({ t: ceviri.t, i18n: ceviri.i18n }),
}))
vi.mock('../AuthContext', () => ({
  useAuth: () => ({
    session: null,
    ready: true,
    signIn: async () => ({}),
    signUp: async () => ({}),
    resetPassword: async () => ({}),
  }),
}))

// Belge: i18n açılışı + odak hapsi efekti (keydown dinleyicisi) için asgari yüzey; dinleyiciler Esc için saklanır.
const dinleyici = new Map<string, Set<(e: unknown) => void>>()
const sayac = { ekle: 0, cikar: 0 }
const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', {
  documentElement: { lang: '' },
  title: '',
  querySelector: () => null,
  activeElement: null,
  addEventListener: (tur: string, f: (e: unknown) => void) => {
    sayac.ekle++
    if (!dinleyici.has(tur)) dinleyici.set(tur, new Set())
    dinleyici.get(tur)!.add(f)
  },
  removeEventListener: (tur: string, f: (e: unknown) => void) => {
    sayac.cikar++
    dinleyici.get(tur)?.delete(f)
  },
})

const i18n = (await import('../../i18n')).default
const ceviriIslevi = i18n.t.bind(i18n) as unknown as (k: string, o?: Record<string, unknown>) => string
ceviri.t = (k: string, o?: Record<string, unknown>) => ceviriIslevi(k, o)
ceviri.i18n = i18n
const t = (k: string): string => ceviriIslevi(k)
const { AuthModalProvider } = await import('../AuthModal')

type Oge = { type: unknown; key: string | null; props: Record<string, unknown> & { children?: unknown } }

function* ogeler(d: unknown): Generator<Oge> {
  if (Array.isArray(d)) {
    for (const x of d) yield* ogeler(x)
    return
  }
  if (d && typeof d === 'object' && 'props' in d && 'type' in d) {
    const o = d as Oge
    yield o
    yield* ogeler(o.props.children)
  }
}

function metin(d: unknown): string {
  if (typeof d === 'string' || typeof d === 'number') return String(d)
  if (Array.isArray(d)) return d.map(metin).join('')
  if (d && typeof d === 'object' && 'props' in d) return metin((d as Oge).props.children)
  return ''
}

const KAPAT = () => t('hesap.kapat')
const SORU = () => t('hesap.pencere.kapatmaSorusu')
const FORMDA_KAL = () => t('hesap.pencere.formdaKal')

const acikPencereler: Pencere[] = []

/** GERÇEK sağlayıcı + onun çizdiği GERÇEK modal. */
class Pencere {
  private saglayici = kanca.yeni()
  private modal = kanca.yeni()
  private modalAgaci: Oge | null = null

  constructor(mod: 'login' | 'signup' = 'login') {
    acikPencereler.push(this)
    const ilk = kanca.ciz(this.saglayici, AuthModalProvider, { children: null }) as Oge
    const deger = ilk.props.value as { requireAuth: (cb?: () => void, r?: string, m?: string) => void }
    deger.requireAuth(undefined, 'checkout', mod)
    this.yenile()
    expect(this.acik, 'sağlayıcı requireAuth sonrası modalı ÇİZMEDİ — düzenek bozuk').toBe(true)
  }

  yenile(): void {
    const agac = kanca.ciz(this.saglayici, AuthModalProvider, { children: null }) as Oge
    const m = [...ogeler(agac.props.children)].find((o) => typeof o.type === 'function')
    if (!m) {
      if (this.modalAgaci) kanca.sok(this.modal)
      this.modalAgaci = null
      return
    }
    this.modalAgaci = kanca.ciz(this.modal, m.type, m.props) as Oge
  }

  get acik(): boolean {
    return this.modalAgaci !== null
  }

  /** Söküm (efekt temizliği: keydown dinleyicisi kalkar). */
  sok(): void {
    if (this.modalAgaci) kanca.sok(this.modal)
    this.modalAgaci = null
  }

  get agac(): Oge {
    expect(this.modalAgaci, 'pencere KAPALI').not.toBeNull()
    return this.modalAgaci!
  }

  olay(f: () => void): void {
    f()
    this.yenile()
  }

  bul(kosul: (o: Oge) => boolean, ne: string): Oge {
    const o = [...ogeler(this.agac)].find(kosul)
    expect(o, `${ne} bulunamadı`).toBeTruthy()
    return o!
  }

  dugme(etiket: string): Oge {
    return this.bul((o) => o.type === 'button' && !o.props['aria-label'] && metin(o).trim() === etiket, `'${etiket}' düğmesi`)
  }

  kapatDugmesi(): void {
    const d = this.bul((o) => o.type === 'button' && o.props['aria-label'] === KAPAT(), 'başlıktaki kapat (×) düğmesi')
    this.olay(() => (d.props.onClick as () => void)())
  }

  esc(): void {
    this.olay(() => {
      for (const f of [...(dinleyici.get('keydown') ?? [])]) f({ key: 'Escape', shiftKey: false, preventDefault: () => {} })
    })
  }

  girdiler(): Oge[] {
    return [...ogeler(this.agac)].filter((o) => o.type === 'input' && typeof o.props.onChange === 'function')
  }

  yaz(anahtar: string, deger: string): void {
    const g = this.girdiler().find((o) => girdiAnahtari(o) === anahtar)
    expect(g, `'${anahtar}' alanı bulunamadı`).toBeTruthy()
    this.olay(() => (g!.props.onChange as (e: unknown) => void)({ target: { value: deger } }))
  }

  hesapTuru(id: string): void {
    const d = this.bul((o) => o.type === 'button' && o.key === id, `hesap türü '${id}' düğmesi`)
    this.olay(() => (d.props.onClick as () => void)())
  }

  get soruVar(): boolean {
    return metin(this.agac).includes(SORU())
  }

  deger(anahtar: string): unknown {
    return this.girdiler().find((o) => girdiAnahtari(o) === anahtar)?.props.value
  }
}

/** E-posta / şifre `type` ile, diğer alanlar GERÇEK katalogdaki yer tutucu metniyle tanınır. */
function girdiAnahtari(o: Oge): string {
  const tur = String(o.props.type)
  return tur === 'email' || tur === 'password' ? tur : String(o.props.placeholder)
}

afterEach(() => {
  for (const p of acikPencereler.splice(0)) p.sok()
  dinleyici.clear()
  sayac.ekle = 0
  sayac.cikar = 0
})

describe('AuthModal kirli-form onayı (D5.09 · B-7.18) — GERÇEK bileşen davranışı', () => {
  it('KARŞIT: BOŞ formda kapat (×) pencereyi HEMEN kapatır — soru sorulmaz', () => {
    const p = new Pencere()
    expect(p.soruVar).toBe(false)
    p.kapatDugmesi()
    expect(p.acik, 'boş form kapanmadı (onay kapısı her şeyi engelliyor olabilir)').toBe(false)
  })

  it('KRİTİK: e-posta yazılıyken kapat (×) pencereyi KAPATMAZ; modal İÇİ onay sorusu çıkar, veri durur', () => {
    const p = new Pencere()
    p.yaz('email', 'hekim@klinik.com')
    p.kapatDugmesi()
    expect(p.acik, 'DOLU form tek tıkla kapandı — girilen veri kayboldu').toBe(true)
    expect(p.soruVar, 'onay sorusu ("Girdiğiniz bilgiler kaybolacak…") görünmedi').toBe(true)
    expect(SORU()).toContain('Girdiğiniz bilgiler kaybolacak')
    expect(p.deger('email')).toBe('hekim@klinik.com')
  })

  it('onay sorusunda "Vazgeç, formda kal" soruyu kaldırır ve veri KORUNUR; "Kapat" pencereyi kapatır', () => {
    const p = new Pencere()
    p.yaz('password', 'gizli-sifre-1')
    p.kapatDugmesi()
    expect(p.soruVar).toBe(true)
    const kal = p.dugme(FORMDA_KAL())
    p.olay(() => (kal.props.onClick as () => void)())
    expect(p.acik).toBe(true)
    expect(p.soruVar).toBe(false)
    expect(p.deger('password')).toBe('gizli-sifre-1')

    p.kapatDugmesi()
    const kapat = p.dugme(KAPAT())
    p.olay(() => (kapat.props.onClick as () => void)())
    expect(p.acik, 'kullanıcı onayladı ama pencere KAPANMADI').toBe(false)
  })

  it('KRİTİK: Esc — yazmadan ÖNCE kurulan dinleyici GÜNCEL formu görür (bayat kapanış yok); boş formda Esc kapatır', () => {
    const dolu = new Pencere()
    expect(dinleyici.get('keydown')?.size, 'odak hapsi keydown dinleyicisi kurulmadı').toBe(1)
    dolu.yaz('email', 'a@b.co')
    dolu.esc()
    expect(dolu.acik, 'Esc DOLU formu onaysız kapattı (açılıştaki boş formun requestClose\'u çağrılıyor)').toBe(true)
    expect(dolu.soruVar).toBe(true)
    dolu.sok()
    expect(dinleyici.get('keydown')?.size, 'söküm keydown dinleyicisini kaldırmadı').toBe(0)

    const bos = new Pencere()
    bos.esc()
    expect(bos.acik, 'Esc boş formu kapatmadı').toBe(false)
  })

  it('arka plana (diyalog DIŞI) basmak dolu formu onaysız SİLMEZ; diyalog içinden kabaran basış hiçbir şey yapmaz', () => {
    const p = new Pencere()
    p.yaz('email', 'x@y.z')
    const kok = p.agac
    const ic = { ad: 'diyalog içi' }
    p.olay(() => (kok.props.onMouseDown as (e: unknown) => void)({ target: ic, currentTarget: kok }))
    expect(p.acik).toBe(true)
    expect(p.soruVar, 'diyalog içi basış onay sorusu açtı').toBe(false)
    p.olay(() => (kok.props.onMouseDown as (e: unknown) => void)({ target: kok, currentTarget: kok }))
    expect(p.acik, 'arka plan basışı DOLU formu kapattı').toBe(true)
    expect(p.soruVar).toBe(true)
  })

  // Kayıt formunun HER alanı tek başına "kirli" sayılmalı (uzun klinik/kurum formu). Tablo GERÇEK çizimden türetilen alan kümesiyle
  // karşılaştırılır: yeni alan eklenip tabloya girmezse aşağıdaki VAKUM testi kırmızı olur.
  const ALANLAR: [string, string, () => string][] = [
    ['fullName', 'individual', () => t('hesap.alan.adSoyad')],
    ['email', 'individual', () => 'email'],
    ['pw', 'individual', () => 'password'],
    ['clinicName', 'veterinarian', () => t('hesap.alan.klinikAdi')],
    ['city', 'veterinarian', () => t('hesap.alan.sehir')],
    ['phone', 'veterinarian', () => t('hesap.alan.telefon')],
    ['vetLicense', 'veterinarian', () => t('hesap.alan.veterinerOda')],
    ['institution', 'researcher', () => t('hesap.alan.kurumAdi')],
    ['department', 'researcher', () => t('hesap.alan.bolum')],
    ['academicTitle', 'researcher', () => t('hesap.alan.unvan')],
  ]

  it('VAKUM: tablo, kayıt formunun ÇİZİLEN tüm alanlarını (3 hesap türü) kapsar', () => {
    const cizilen = new Set<string>()
    for (const tur of ['individual', 'veterinarian', 'researcher']) {
      const p = new Pencere('signup')
      p.hesapTuru(tur)
      for (const g of p.girdiler()) cizilen.add(girdiAnahtari(g))
    }
    expect([...cizilen].sort()).toEqual(ALANLAR.map(([, , a]) => a()).sort())
    expect(cizilen.size).toBe(10)
  })

  it.each(ALANLAR)('KRİTİK: kayıt formunda YALNIZ %s doluyken de kapat onay sorar (%s)', (_ad, tur, anahtar) => {
    const p = new Pencere('signup')
    p.hesapTuru(tur)
    p.yaz(anahtar(), 'dolu')
    p.kapatDugmesi()
    expect(p.acik, `yalnız ${_ad} doluyken form tek tıkla kapandı`).toBe(true)
    expect(p.soruVar).toBe(true)
  })

  it('odak hapsi yazarken YENİDEN KURULMAZ (her tuşta keydown sök/tak yok — mobil klavye kapanması regresyonu, 2026-08-06)', () => {
    const p = new Pencere()
    for (const s of ['h', 'he', 'hek', 'heki', 'hekim']) p.yaz('email', s)
    expect(sayac.ekle, 'keydown dinleyicisi her tuşta yeniden kuruluyor').toBe(1)
    expect(sayac.cikar).toBe(0)
  })
})
