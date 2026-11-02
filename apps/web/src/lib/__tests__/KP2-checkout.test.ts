// Author: mertaygn, cglrgrkn
/**
 * KP-2 · src/lib/checkout.ts · sözleşmeler:
 *  initCheckout — oturum yoksa `needAuth` ve AĞA ÇIKILMAZ · istek gövdesi = yük + kullanıcı JWT'si + sayfanın KENDİ kökeni ·
 *  sunucu hatasında makine-okur alanlar (kod / alan / sebep) korunur, mesaj önceliği message > error > yedek · JSON olmayan yanıt
 *  yedek mesaj · 20 sn'de yanıt yoksa istek İPTAL edilir ve zaman aşımı mesajı döner · ağ hatası ayrı mesaj · zamanlayıcı her yolda temizlenir.
 *  cancelSubscription — oturum yoksa 'Önce giriş yapın.' · başarı yalnız `canceled:true` ile · aksi mesaj / yedek · zaman aşımı + ağ hatası.
 *
 * Sahte EN ALT katta: Supabase istemcisi (`./supabase` → yalnız `auth.getSession`), `fetch` (gerçek `Response`), `window.location`,
 * saat (`vi.useFakeTimers`, gerçek bekleme yok).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const oturum = vi.hoisted(() => ({ jeton: 'kullanici-jwt' as string | null }))
vi.mock('../supabase', () => ({
  supabase: {
    auth: { getSession: async () => ({ data: { session: oturum.jeton ? { access_token: oturum.jeton } : null } }) },
  },
}))

import { cancelSubscription, initCheckout, type CheckoutPayload } from '../checkout'

type Kayit = { url: string; yontem: string; basliklar: Record<string, string>; govde: unknown; sinyal: AbortSignal | undefined }
let kayit: Kayit[] = []
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })
function agKur(yanitla: (init: RequestInit) => Response | Promise<Response>) {
  kayit = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      kayit.push({
        url: String(url),
        yontem: init.method ?? 'GET',
        basliklar: { ...(init.headers as Record<string, string>) },
        govde: init.body ? JSON.parse(String(init.body)) : undefined,
        sinyal: init.signal ?? undefined,
      })
      return yanitla(init)
    }),
  )
}
/** Yarı-açık bağlantı: yanıt hiç gelmez; yalnız sinyal iptal edilince gerçek fetch gibi AbortError ile reddedilir. */
const asili = (init: RequestInit) =>
  new Promise<Response>((_, red) => {
    init.signal?.addEventListener('abort', () => red(new DOMException('This operation was aborted', 'AbortError')))
  })

const YUK: CheckoutPayload = {
  tier: 'pro',
  yearly: true,
  research: false,
  customer: { name: 'Ayşe', surname: 'Vet', identityNumber: '10000000146', gsmNumber: '+905551112233', city: 'İzmir', address: 'Adres 1' },
}

beforeEach(() => {
  oturum.jeton = 'kullanici-jwt'
  vi.stubGlobal('window', { location: { origin: 'https://site-ornek.test' } })
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('initCheckout', () => {
  it('oturum yok → { needAuth: true } ve fetch ÇAĞRILMAZ', async () => {
    oturum.jeton = null
    agKur(() => json({ content: 'x' }))
    await expect(initCheckout(YUK)).resolves.toEqual({ needAuth: true })
    expect(kayit).toHaveLength(0)
  })

  it('başarı → { content }; POST /api/checkout gövdesi = yük + JWT + sayfanın kökeni, iptal sinyali bağlı', async () => {
    agKur(() => json({ content: '<div id="iyzi">form</div>' }))
    await expect(initCheckout(YUK)).resolves.toEqual({ content: '<div id="iyzi">form</div>' })
    expect(kayit).toHaveLength(1)
    expect(kayit[0].url).toBe('/api/checkout')
    expect(kayit[0].yontem).toBe('POST')
    expect(kayit[0].basliklar).toEqual({ 'Content-Type': 'application/json' })
    expect(kayit[0].govde).toEqual({ ...YUK, token: 'kullanici-jwt', origin: 'https://site-ornek.test' })
    expect(kayit[0].sinyal).toBeInstanceOf(AbortSignal)
  })

  it('409 zaten abone → error=message, kod=error korunur', async () => {
    agKur(() => json({ error: 'already_subscribed', message: 'Hesabınızda zaten aktif bir abonelik var.' }, 409))
    await expect(initCheckout(YUK)).resolves.toEqual({
      error: 'Hesabınızda zaten aktif bir abonelik var.',
      kod: 'already_subscribed',
      alan: undefined,
      sebep: undefined,
    })
  })

  it('400 alan hatası → alan + sebep makine-okur korunur', async () => {
    agKur(() => json({ error: 'customer', alan: 'identityNumber', sebep: 'bicim', message: 'TC Kimlik No 11 haneli olmalıdır.' }, 400))
    await expect(initCheckout(YUK)).resolves.toEqual({
      error: 'TC Kimlik No 11 haneli olmalıdır.',
      kod: 'customer',
      alan: 'identityNumber',
      sebep: 'bicim',
    })
  })

  it('mesajsız hata → error alanı kodun kendisi; o da yoksa "Ödeme başlatılamadı."', async () => {
    agKur(() => json({ error: 'iyzico' }, 502))
    expect((await initCheckout(YUK)).error).toBe('iyzico')
    agKur(() => json({}, 500))
    expect((await initCheckout(YUK)).error).toBe('Ödeme başlatılamadı.')
  })

  it('200 ama içerik yok → hata (boş form gömülmez)', async () => {
    agKur(() => json({ token: 'tk' }))
    const r = await initCheckout(YUK)
    expect(r.content).toBeUndefined()
    expect(r.error).toBe('Ödeme başlatılamadı.')
  })

  it('JSON olmayan yanıt (HTML hata sayfası) → yedek mesaj, istisna sızmaz', async () => {
    agKur(() => new Response('<html>504</html>', { status: 504 }))
    expect((await initCheckout(YUK)).error).toBe('Ödeme başlatılamadı.')
  })

  it('20 sn içinde yanıt yok → istek iptal edilir, zaman aşımı mesajı', async () => {
    vi.useFakeTimers()
    agKur(asili)
    const p = initCheckout(YUK)
    await vi.advanceTimersByTimeAsync(19_999)
    expect(kayit[0].sinyal?.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    await expect(p).resolves.toEqual({ error: 'Ödeme sunucusu yanıt vermedi (zaman aşımı). Tekrar deneyin.' })
    expect(kayit[0].sinyal?.aborted).toBe(true)
  })

  it('ağ hatası (TypeError) → "Ağ hatası — tekrar deneyin."', async () => {
    agKur(() => {
      throw new TypeError('Failed to fetch')
    })
    await expect(initCheckout(YUK)).resolves.toEqual({ error: 'Ağ hatası — tekrar deneyin.' })
  })

  it('her yolda zaman aşımı zamanlayıcısı TEMİZLENİR (başarı ve hata sonrası bekleyen zamanlayıcı yok)', async () => {
    vi.useFakeTimers()
    agKur(() => json({ content: 'x' }))
    await initCheckout(YUK)
    expect(vi.getTimerCount()).toBe(0)
    agKur(() => {
      throw new TypeError('Failed to fetch')
    })
    await initCheckout(YUK)
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('cancelSubscription', () => {
  it('oturum yok → "Önce giriş yapın." ve fetch ÇAĞRILMAZ', async () => {
    oturum.jeton = null
    agKur(() => json({ canceled: true }))
    await expect(cancelSubscription()).resolves.toEqual({ error: 'Önce giriş yapın.' })
    expect(kayit).toHaveLength(0)
  })

  it('başarı (canceled:true) → { ok: true }; POST /api/cancel gövdesi yalnız JWT', async () => {
    agKur(() => json({ canceled: true }))
    await expect(cancelSubscription()).resolves.toEqual({ ok: true })
    expect(kayit[0].url).toBe('/api/cancel')
    expect(kayit[0].yontem).toBe('POST')
    expect(kayit[0].govde).toEqual({ token: 'kullanici-jwt' })
    expect(kayit[0].sinyal).toBeInstanceOf(AbortSignal)
  })

  it('200 ama canceled yok → hata (iptal edildi sanılmaz)', async () => {
    agKur(() => json({}))
    await expect(cancelSubscription()).resolves.toEqual({ error: 'İptal edilemedi.' })
  })

  it('sunucu mesajı varsa o döner (404 abonelik bulunamadı)', async () => {
    agKur(() => json({ message: 'Abonelik bulunamadı.' }, 404))
    await expect(cancelSubscription()).resolves.toEqual({ error: 'Abonelik bulunamadı.' })
  })

  it('JSON olmayan hata yanıtı → "İptal edilemedi."', async () => {
    agKur(() => new Response('bad gateway', { status: 502 }))
    await expect(cancelSubscription()).resolves.toEqual({ error: 'İptal edilemedi.' })
  })

  it('20 sn yanıt yok → iptal edilir; mesaj durumu birazdan kontrol etmeyi söyler', async () => {
    vi.useFakeTimers()
    agKur(asili)
    const p = cancelSubscription()
    await vi.advanceTimersByTimeAsync(20_000)
    await expect(p).resolves.toEqual({
      error: 'Sunucu yanıt vermedi (zaman aşımı). Aboneliğinizin durumunu birazdan kontrol edin.',
    })
    expect(vi.getTimerCount()).toBe(0)
  })

  it('ağ hatası → "Ağ hatası — tekrar deneyin."', async () => {
    agKur(() => Promise.reject(new TypeError('Failed to fetch')))
    await expect(cancelSubscription()).resolves.toEqual({ error: 'Ağ hatası — tekrar deneyin.' })
  })
})
