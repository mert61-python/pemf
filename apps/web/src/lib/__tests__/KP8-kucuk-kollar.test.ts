/**
 * KP-8 · site küçük kalan dallar (saf işlevler + sahte Supabase istemcisi / sahte fetch — canlı servis YOK):
 *  - `yoluSadelestir`: boş yol, yalnız sorgu / parça ("?x", "#y") ve yalnız eğik çizgilerden oluşan yol KÖK ("/") olur.
 *  - `jetonBakiyesiniOku`: `kalan` sayısı varken aylık hak / satın alınan alanları gelmezse 0 (eksik alan bakiye uydurmaz ama
 *    kalanın yanında 0 gösterilir).
 *  - `fetchUsageStats`: satırda hesap / cihaz sayısı yoksa 0.
 *  (api/_lib/util kolları: api/_lib/__tests__/KP8-util-kollari.test.ts — sunucu tsconfig'i.)
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

const rpc = vi.fn()
vi.mock('../supabase', () => ({
  supabase: {
    rpc: (...a: unknown[]) => rpc(...a),
    auth: { getSession: async () => ({ data: { session: { access_token: 'kullanici-jwt' } } }) },
  },
  supabaseReady: true,
}))

const { yoluSadelestir } = await import('../sayfaMeta')
const { jetonBakiyesiniOku } = await import('../jeton')
const { fetchUsageStats } = await import('../usageStats')

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('yoluSadelestir', () => {
  it('boş / yalnız sorgu / yalnız eğik çizgi → "/"', () => {
    expect(yoluSadelestir('')).toBe('/')
    expect(yoluSadelestir('?lang=en')).toBe('/')
    expect(yoluSadelestir('#ust')).toBe('/')
    expect(yoluSadelestir('///')).toBe('/')
    expect(yoluSadelestir('/fiyat/')).toBe('/fiyat')
  })
})

describe('jetonBakiyesiniOku', () => {
  it('kalan varken aylık hak / satın alınan yoksa 0', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ kalan: 7 }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    await expect(jetonBakiyesiniOku()).resolves.toEqual({ kalan: 7, aylikHak: 0, satinAlinan: 0, donemSonu: null })
  })
})

describe('fetchUsageStats', () => {
  it('satırda hesap / cihaz sayısı yoksa 0', async () => {
    rpc.mockResolvedValue({ data: [{ devices_active: 1 }], error: null })
    const s = await fetchUsageStats()
    expect(s).toMatchObject({ accounts: 0, devicesTotal: 0, devicesActive: 1 })
  })
})
