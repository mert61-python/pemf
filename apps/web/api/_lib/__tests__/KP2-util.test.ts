// Author: mertaygn, cglrgrkn
/**
 * KP-2 · api/_lib/util.ts · sözleşmeler: `upsertSubscription` service_role anahtarıyla, birleştirme tercihiyle (`Prefer:
 * resolution=merge-duplicates`) `subscriptions`e satırı AYNEN yazar; başarısız yanıtta durum kodu + gövdeyle FIRLATIR (sessiz kayıp yok) ·
 * `getUserBySubscriptionRef` referansı URL-kodlayıp yalnız `user_id` seçer; boş referansta AĞA ÇIKMAZ; okunamazsa / satır yoksa null.
 *
 * Sahte EN ALT katta: `fetch` (gerçek `Response` nesneleri); ortam `vi.stubEnv`. Anahtarlar açıkça sahte.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getUserBySubscriptionRef, upsertSubscription } from '../util'

type Kayit = { url: string; yontem: string; basliklar: Record<string, string>; govde: unknown }
let kayit: Kayit[] = []
function agKur(yanitla: (url: string) => Response) {
  kayit = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      kayit.push({
        url: String(url),
        yontem: init.method ?? 'GET',
        basliklar: { ...(init.headers as Record<string, string>) },
        govde: init.body ? JSON.parse(String(init.body)) : undefined,
      })
      return yanitla(String(url))
    }),
  )
}
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  vi.stubEnv('SUPABASE_URL', 'https://proje-ornek.supabase.test')
  vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'test-servis-anahtari')
  vi.stubEnv('SUPABASE_ANON_KEY', 'test-anon-anahtari')
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('upsertSubscription', () => {
  it('başarılı yanıt → service_role başlıklarıyla POST /rest/v1/subscriptions, gövde satırın KENDİSİ, birleştirme tercihi', async () => {
    agKur(() => new Response(null, { status: 201 }))
    const satir = { user_id: 'u-1', tier: 'pro', status: 'active', addons: ['research'] }
    await expect(upsertSubscription(satir)).resolves.toBeUndefined()
    expect(kayit).toEqual([
      {
        url: 'https://proje-ornek.supabase.test/rest/v1/subscriptions',
        yontem: 'POST',
        basliklar: {
          apikey: 'test-servis-anahtari',
          Authorization: 'Bearer test-servis-anahtari',
          'Content-Type': 'application/json',
          Prefer: 'resolution=merge-duplicates',
        },
        govde: satir,
      },
    ])
  })

  it('başarısız yanıt (409) → "subscriptions upsert 409: <gövde>" fırlatır', async () => {
    agKur(() => new Response('duplicate key', { status: 409 }))
    await expect(upsertSubscription({ user_id: 'u-1' })).rejects.toThrow('subscriptions upsert 409: duplicate key')
  })

  it('SUPABASE_SERVICE_ROLE_KEY yok → ağa çıkmadan anahtar adıyla fırlatır', async () => {
    vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', '')
    agKur(() => json({}))
    await expect(upsertSubscription({ user_id: 'u-1' })).rejects.toThrow('Eksik ortam değişkeni: SUPABASE_SERVICE_ROLE_KEY')
    expect(kayit).toHaveLength(0)
  })
})

describe('getUserBySubscriptionRef', () => {
  it('boş referans → null ve AĞA ÇIKILMAZ', async () => {
    agKur(() => json([{ user_id: 'olmamali' }]))
    await expect(getUserBySubscriptionRef('')).resolves.toBeNull()
    expect(kayit).toHaveLength(0)
  })

  it('satır var → ilk satırın user_id\'si; referans URL-kodlanır, yalnız user_id seçilir, service_role ile okunur', async () => {
    agKur(() => json([{ user_id: 'u-42' }, { user_id: 'u-ikinci' }]))
    await expect(getUserBySubscriptionRef('sub a&b=c')).resolves.toBe('u-42')
    expect(kayit).toHaveLength(1)
    expect(kayit[0].url).toBe(
      'https://proje-ornek.supabase.test/rest/v1/subscriptions?stripe_subscription_id=eq.sub%20a%26b%3Dc&select=user_id',
    )
    expect(kayit[0].yontem).toBe('GET')
    expect(kayit[0].basliklar).toEqual({ apikey: 'test-servis-anahtari', Authorization: 'Bearer test-servis-anahtari' })
  })

  it('satır yok → null', async () => {
    agKur(() => json([]))
    await expect(getUserBySubscriptionRef('sub-1')).resolves.toBeNull()
  })

  it('satırda user_id alanı yok → null (boş dize uydurulmaz)', async () => {
    agKur(() => json([{}]))
    await expect(getUserBySubscriptionRef('sub-1')).resolves.toBeNull()
  })

  it('okuma başarısız (500) → null (webhook ikinci eşleme yoluna düşer)', async () => {
    agKur(() => json({ message: 'boom' }, 500))
    await expect(getUserBySubscriptionRef('sub-1')).resolves.toBeNull()
  })
})
