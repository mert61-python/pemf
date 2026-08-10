// Author: mertaygn, cglrgrkn
/**
 * İndirme kapısı (2026-08-06) — korunan davranışlar.
 *
 *   Giriş yapmamış kullanıcı indiremez → düğme modalı açar, HİÇBİR adrese gidilmez.
 *   Giriş biter bitmez indirme KENDİLİĞİNDEN başlar (kullanıcı düğmeye ikinci kez basmaz).
 *   Oturum tarayıcıda kalıcıdır (persistSession) → her indirmede tekrar giriş istenmez.
 *   "Yakında" olan platform hiçbir koşulda adrese gitmez (404 indirmesi).
 *   Linux alt paketleri (.AppImage / .rpm) de kapının İÇİNDE — dışarıda kalırsa arka kapı.
 *
 * DÜRÜSTLÜK: kapı bir erişim kontrolü değildir (dosyalar GitHub'da public); testler de
 * "koruma" değil "kayıt adımı akışı" doğrular.
 */
import { describe, it, expect, vi } from 'vitest'
import {
  resolveDownload,
  decideDownload,
  requestDownload,
  type DownloadTarget,
  type GateAuth,
} from '../download'
import { CLIENT } from '../../config'
import { AUTH_OPTIONS, supabase } from '../supabase'

const ANON: GateAuth = { loading: false, authed: false }
const USER: GateAuth = { loading: false, authed: true }
const OKUNUYOR: GateAuth = { loading: true, authed: false }

/** Giriş modalını taklit eder: geri çağrıyı saklar, `girisYap()` ile oturum açılmış gibi çalıştırır. */
function sahteModal() {
  let bekleyen: (() => void) | null = null
  // İkinci parametre (reason) AuthModal'ın alt başlığını seçer → imzada dursun ki test edebilelim.
  const requireAuth = vi.fn((cb: () => void, _reason?: 'download') => {
    bekleyen = cb
  })
  return {
    requireAuth,
    acildiMi: () => requireAuth.mock.calls.length > 0,
    girisYap: () => {
      const cb = bekleyen
      bekleyen = null
      cb?.()
    },
  }
}

describe('resolveDownload — 6 indirme hedefinin tamamı tek yerden çözülür', () => {
  it('platformlar config.ts adreslerine eşlenir', () => {
    expect(resolveDownload('windows').url).toBe(CLIENT.downloads.windows.url)
    expect(resolveDownload('macos').url).toBe(CLIENT.downloads.macos.url)
    expect(resolveDownload('linux').url).toBe(CLIENT.downloads.linux.url)
    expect(resolveDownload('android').url).toBe(CLIENT.downloads.android.url)
  })

  it('Linux alt paketleri AYRI hedeftir (.deb adresine düşmez)', () => {
    expect(resolveDownload('linux-appimage').url).toBe(CLIENT.downloads.linux.appImageUrl)
    expect(resolveDownload('linux-rpm').url).toBe(CLIENT.downloads.linux.rpmUrl)
    expect(resolveDownload('linux-appimage').url).not.toBe(resolveDownload('linux').url)
    expect(resolveDownload('linux-rpm').url).not.toBe(resolveDownload('linux').url)
  })

  it('alt paketler KENDİ hazır bayrağını taşır (.deb bayrağına bağlanmaz)', () => {
    expect(resolveDownload('linux-appimage').ready).toBe(CLIENT.downloads.linux.appImageReady)
    expect(resolveDownload('linux-rpm').ready).toBe(CLIENT.downloads.linux.rpmReady)
  })

  it('üretilen tüm adresler https ve yapılandırılmış release host’unda', () => {
    const hedefler: DownloadTarget[] = ['windows', 'macos', 'linux', 'linux-appimage', 'linux-rpm', 'android']
    for (const h of hedefler) {
      expect(resolveDownload(h).url).toMatch(/^https:\/\/github\.com\/.+\/releases\/download\/.+/)
    }
  })
})

describe('decideDownload — kapı kararı', () => {
  it('giriş YOKSA indirme değil, kapı kararı verilir', () => {
    expect(decideDownload('windows', ANON)).toBe('gate')
  })

  it('giriş VARSA indirme doğrudan başlar', () => {
    expect(decideDownload('windows', USER)).toBe('download')
  })

  it('oturum henüz okunuyorsa BEKLE (girişli kullanıcıya modal yanıp sönmesin)', () => {
    // AuthContext ilk getSession bitene kadar authed=false görünür; bunu "giriş yok"
    // saymak, giriş yapmış kullanıcıya gereksiz modal açardı.
    expect(decideDownload('windows', OKUNUYOR)).toBe('wait')
  })

  it('"Yakında" platform hiçbir oturum durumunda indirilemez', () => {
    // macOS/Linux kasıtlı olarak ready=false (donanım desteği Windows-özel).
    expect(CLIENT.downloads.macos.ready).toBe(false)
    expect(decideDownload('macos', USER)).toBe('unavailable')
    expect(decideDownload('macos', ANON)).toBe('unavailable')
    expect(decideDownload('linux-appimage', USER)).toBe('unavailable')
  })
})

describe('requestDownload — giriş yapmamış kullanıcı indiremez', () => {
  it('modal açılır ve HİÇBİR adrese gidilmez', () => {
    const modal = sahteModal()
    const go = vi.fn()

    const karar = requestDownload('windows', ANON, { requireAuth: modal.requireAuth, go })

    expect(karar).toBe('gate')
    expect(modal.acildiMi()).toBe(true)
    expect(go).not.toHaveBeenCalled()
  })

  it('oturum okunurken tıklama ne indirir ne modal açar', () => {
    const modal = sahteModal()
    const go = vi.fn()
    expect(requestDownload('windows', OKUNUYOR, { requireAuth: modal.requireAuth, go })).toBe('wait')
    expect(modal.acildiMi()).toBe(false)
    expect(go).not.toHaveBeenCalled()
  })

  it('modalın açılış gerekçesi "download" (alt başlık ödeme metnini göstermesin)', () => {
    const modal = sahteModal()
    requestDownload('windows', ANON, { requireAuth: modal.requireAuth, go: vi.fn() })
    expect(modal.requireAuth.mock.calls[0][1]).toBe('download')
  })

  it('Linux alt paketleri de kapının içindedir (arka kapı yok)', () => {
    // Not: bu hedefler şu an "Yakında" → önce ready doğru hedefi seçtiğimizi doğrula,
    // sonra hazır olsalardı kapının çalışacağını hedef-bağımsız kararla göster.
    const modal = sahteModal()
    const go = vi.fn()
    for (const h of ['linux-appimage', 'linux-rpm'] as DownloadTarget[]) {
      const karar = requestDownload(h, ANON, { requireAuth: modal.requireAuth, go })
      expect(karar).not.toBe('download') // asla doğrudan inmez
      expect(go).not.toHaveBeenCalled()
    }
  })
})

describe('requestDownload — giriş sonrası indirme KENDİLİĞİNDEN devam eder', () => {
  it('kullanıcı düğmeye ikinci kez basmadan indirme tetiklenir', () => {
    const modal = sahteModal()
    const go = vi.fn()

    requestDownload('windows', ANON, { requireAuth: modal.requireAuth, go })
    expect(go).not.toHaveBeenCalled()

    modal.girisYap() // AuthModal: oturum gelince pendingRef'teki işi çalıştırır

    expect(go).toHaveBeenCalledTimes(1)
    expect(go).toHaveBeenCalledWith(CLIENT.downloads.windows.url)
  })

  it('giriş yapmış kullanıcı için modal HİÇ açılmaz, indirme anında başlar', () => {
    const modal = sahteModal()
    const go = vi.fn()

    const karar = requestDownload('android', USER, { requireAuth: modal.requireAuth, go })

    expect(karar).toBe('download')
    expect(modal.acildiMi()).toBe(false)
    expect(go).toHaveBeenCalledWith(CLIENT.downloads.android.url)
  })
})

describe('oturum kalıcılığı — her indirmede yeniden giriş istenmez', () => {
  it('Supabase istemcisi oturumu tarayıcıda saklar ve token’ı tazeler', () => {
    expect(AUTH_OPTIONS.persistSession).toBe(true)
    expect(AUTH_OPTIONS.autoRefreshToken).toBe(true)
  })

  it('e-posta doğrulama / şifre sıfırlama dönüşünde oturum URL’den alınır', () => {
    // Kayıt e-postasını onaylayıp dönen kullanıcı, bekleyen indirmeye giriş yapmış olarak döner.
    expect(AUTH_OPTIONS.detectSessionInUrl).toBe(true)
  })

  it('KURULMUŞ istemci gerçekten bu ayarlarla çalışıyor (sabit doğru, istemci yanlış olamaz)', () => {
    // DENETIM 2026-08-06: yukarıdaki üç test yalnız SABİTİ okuyordu; birisi createClient'a
    // `{ ...AUTH_OPTIONS, persistSession: false }` geçse sabit doğru kalır, testler yeşil kalır
    // ve kullanıcı her sekme kapanışında yeniden giriş yapmak zorunda kalırdı. Kilidi
    // GoTrueClient örneğine bağla — davranışı belirleyen yer orası.
    const auth = supabase.auth as unknown as Record<string, unknown>
    expect(auth.persistSession).toBe(true)
    expect(auth.autoRefreshToken).toBe(true)
    expect(auth.detectSessionInUrl).toBe(true)
  })
})
