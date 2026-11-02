// Author: mertaygn, cglrgrkn
/**
 * KP-2 · src/i18n/dil.ts + src/i18n/index.ts (savunma yolları) · sözleşmeler: dil kuralları tarayıcı yüzeyi BOZUKKEN de fırlatmaz —
 *  urlDili: ayrıştırılamayan arama girdisi → null · tarayiciYereli: `navigator` erişimi istisna atarsa → null · kayitliDil: depo erişimi
 *  istisna atarsa (gizli pencere / SecurityError) → null · index: açılışta `location` OKUNAMAZSA modül yine yüklenir ve kayıtlı seçim
 *  kullanılır (adres dili yok sayılır).
 *
 * Sahte EN ALT katta: `navigator` / `location` / `localStorage` küreselleri (özellik tanımlayıcısıyla; test sonunda AYNEN geri konur).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { kayitliDil, tarayiciYereli, urlDili } from '../dil'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true

const geriAl: (() => void)[] = []
/** Küresel özelliği istisna atan bir okuyucuyla değiştirir; test sonunda ÖZGÜN tanımlayıcı geri konur. */
function patlayanOkuyucu(ad: 'navigator' | 'location', hata: Error) {
  const ozgun = Object.getOwnPropertyDescriptor(globalThis, ad)
  Object.defineProperty(globalThis, ad, {
    configurable: true,
    get() {
      throw hata
    },
  })
  geriAl.push(() => {
    if (ozgun) Object.defineProperty(globalThis, ad, ozgun)
    else delete (globalThis as Record<string, unknown>)[ad]
  })
}

afterEach(() => {
  while (geriAl.length) geriAl.pop()!()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('dil.ts savunma yolları', () => {
  it('urlDili: yinelenirken istisna atan arama girdisi → null (fırlatmaz)', () => {
    const bozuk = {
      [Symbol.iterator]() {
        throw new TypeError('yinelenemez')
      },
    }
    expect(urlDili(bozuk as never)).toBeNull()
  })

  it('KARŞIT urlDili: geçerli "?lang=en" → "en"; geçersiz değer → null', () => {
    expect(urlDili('?lang=en')).toBe('en')
    expect(urlDili('?lang=de')).toBeNull()
  })

  it('tarayiciYereli: navigator erişimi istisna atarsa → null', () => {
    patlayanOkuyucu('navigator', new Error('erişim engellendi'))
    expect(tarayiciYereli()).toBeNull()
  })

  it('KARŞIT tarayiciYereli: navigator.language "tr-TR" → "tr-TR"; boş dil → null', () => {
    vi.stubGlobal('navigator', { language: 'tr-TR' })
    expect(tarayiciYereli()).toBe('tr-TR')
    vi.stubGlobal('navigator', { language: '' })
    expect(tarayiciYereli()).toBeNull()
  })

  it('kayitliDil: depo okuması SecurityError atarsa → null', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new DOMException('The operation is insecure.', 'SecurityError')
      },
    })
    expect(kayitliDil()).toBeNull()
  })

  it('KARŞIT kayitliDil: depoda "en" → "en"', () => {
    vi.stubGlobal('localStorage', { getItem: (k: string) => (k === 'pemf.dil' ? 'en' : null) })
    expect(kayitliDil()).toBe('en')
  })
})

describe('index.ts açılışı — location okunamaz', () => {
  function depo(secim: string | null) {
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => (k === 'pemf.dil' ? secim : null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    })
  }

  it('location erişimi istisna atar → modül yüklenir; ilk dil KAYITLI seçimden ("en") gelir', async () => {
    depo('en')
    vi.stubGlobal('navigator', { language: 'tr-TR' })
    patlayanOkuyucu('location', new Error('çapraz köken'))
    vi.resetModules()
    const i18n = (await import('../index')).default
    expect(i18n.language).toBe('en')
  })

  it('KARŞIT: location okunabilir ve "?lang=tr" taşıyorsa adres dili KAYITLI seçimin önüne geçer', async () => {
    depo('en')
    vi.stubGlobal('navigator', { language: 'en-US' })
    vi.stubGlobal('location', { search: '?lang=tr', href: 'https://site-ornek.test/?lang=tr', pathname: '/', hash: '' })
    vi.resetModules()
    const i18n = (await import('../index')).default
    expect(i18n.language).toBe('tr')
  })
})
