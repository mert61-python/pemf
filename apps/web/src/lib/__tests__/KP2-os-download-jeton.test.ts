// Author: mertaygn, cglrgrkn
/**
 * KP-2 · src/lib/os.ts + src/lib/download.ts (navigateTo) + src/lib/jeton.ts (hata yolu) · sözleşmeler:
 *  detectOS — `navigator` yoksa (SSR) 'other'; Windows / macOS (iPhone / iPad dahil) / Linux sezilir; Android 'linux' içerse de 'other'
 *  (hedef platform değil); tanınmayan 'other'.
 *  navigateTo — `window` yoksa (SSR) sessizce hiçbir şey yapmaz; varsa `location.assign(url)` (gizli <a download> değil).
 *  jetonBakiyesiniOku — oturum okuması ya da ağ İSTİSNA atarsa ekranı bozmaz: null (bakiye bölümü hiç çizilmez).
 *
 * Sahte EN ALT katta: `navigator`, `window` (globals), Supabase istemcisi (`../supabase`), `fetch`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

const oturum = vi.hoisted(() => ({ hata: null as Error | null, yok: false }))
vi.mock('../supabase', () => ({
  supabase: {
    auth: {
      getSession: async () => {
        if (oturum.hata) throw oturum.hata
        return { data: { session: oturum.yok ? null : { access_token: 'kullanici-jwt' } } }
      },
    },
  },
}))

import { detectOS } from '../os'
import { navigateTo } from '../download'
import { jetonBakiyesiniOku } from '../jeton'

afterEach(() => {
  oturum.hata = null
  oturum.yok = false
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('detectOS', () => {
  const ua = (userAgent: string, platform: string) => vi.stubGlobal('navigator', { userAgent, platform })

  it('navigator yok (SSR) → "other"', () => {
    vi.stubGlobal('navigator', undefined)
    expect(detectOS()).toBe('other')
  })

  it.each([
    ['Windows', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130', 'Win32', 'windows'],
    ['macOS', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Safari/605.1.15', 'MacIntel', 'macos'],
    ['iPhone', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)', 'iPhone', 'macos'],
    ['iPad (platform yalnız)', 'Mozilla/5.0 AppleWebKit', 'iPad', 'macos'],
    ['Android (UA linux içerir)', 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36', 'Linux armv81', 'other'],
    ['Linux masaüstü', 'Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/131.0', 'Linux x86_64', 'linux'],
    ['yalnız X11 (BSD)', 'Mozilla/5.0 (X11; FreeBSD amd64)', 'FreeBSD amd64', 'linux'],
    ['tanınmayan', 'Mozilla/5.0 (PlayStation 5)', 'PS5', 'other'],
  ])('%s → %s', (_ad, userAgent, platform, beklenen) => {
    ua(userAgent, platform)
    expect(detectOS()).toBe(beklenen)
  })

  it('büyük/küçük harf duyarsız: "WINDOWS" platformu → windows', () => {
    ua('Ozel Tarayici', 'WINDOWS')
    expect(detectOS()).toBe('windows')
  })
})

describe('navigateTo', () => {
  it('window yok (SSR) → çökmez, hiçbir şey yapmaz', () => {
    vi.stubGlobal('window', undefined)
    expect(() => navigateTo('https://indir.ornek.test/kurulum.exe')).not.toThrow()
  })

  it('window var → location.assign TAM bu adresle bir kez çağrılır', () => {
    const assign = vi.fn()
    vi.stubGlobal('window', { location: { assign } })
    navigateTo('https://indir.ornek.test/kurulum.exe')
    expect(assign).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith('https://indir.ornek.test/kurulum.exe')
  })
})

describe('jetonBakiyesiniOku — istisna yolu', () => {
  it('oturum okuması istisna atarsa → null ve /api/tokens\'a GİDİLMEZ', async () => {
    oturum.hata = new Error('navigator.locks zaman aşımı')
    const ag = vi.fn()
    vi.stubGlobal('fetch', ag)
    await expect(jetonBakiyesiniOku()).resolves.toBeNull()
    expect(ag).not.toHaveBeenCalled()
  })

  it('ağ istisnası (fetch reddedildi) → null', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await expect(jetonBakiyesiniOku()).resolves.toBeNull()
  })

  it('KARŞIT: aynı düzenekte geçerli yanıt → bakiye nesnesi (null istisnadan geliyor, düzenekten değil)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ kalan: 12, aylik_hak: 10, satin_alinan: 2, donem_sonu: null }), { status: 200 })),
    )
    await expect(jetonBakiyesiniOku()).resolves.toEqual({ kalan: 12, aylikHak: 10, satinAlinan: 2, donemSonu: null })
  })

  it('KP-2 tur 2: oturum yok (giriş yapılmamış) → null ve /api/tokens\'a GİDİLMEZ', async () => {
    oturum.yok = true
    const ag = vi.fn()
    vi.stubGlobal('fetch', ag)
    await expect(jetonBakiyesiniOku()).resolves.toBeNull()
    expect(ag).not.toHaveBeenCalled()
  })

  it('KP-2 tur 2: sunucu 2xx DEĞİL (ör. 401) → null (gövde bakiye gibi görünse bile okunmaz)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ kalan: 12, aylik_hak: 10, satin_alinan: 2, donem_sonu: null }), { status: 401 })),
    )
    await expect(jetonBakiyesiniOku()).resolves.toBeNull()
  })
})
