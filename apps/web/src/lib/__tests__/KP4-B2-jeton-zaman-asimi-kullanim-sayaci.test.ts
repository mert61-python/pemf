// Author: mertaygn, cglrgrkn
/**
 * KP-4 · B2 · kapsanmamış iki dönüş:
 *  jetonBakiyesiniOku — yarı-açık bağlantıda istek 6 sn sonra İPTAL edilir (AbortController) ve menü "…"da asılı kalmaz: null.
 *  fetchUsageStats — RPC sayı OLMAYAN sayaç döndürürse (NaN) uydurma sayı gösterilmez: null (bölüm gizlenir).
 *
 * Sahte EN ALT katta: Supabase istemcisi (`../supabase`), `fetch` (sinyale uyan, kendiliğinden hiç yanıtlamayan istek), sahte saat.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

const rpc = vi.hoisted(() => vi.fn())
vi.mock('../supabase', () => ({
  supabase: {
    auth: { getSession: async () => ({ data: { session: { access_token: 'kullanici-jwt' } } }) },
    rpc: (...a: unknown[]) => rpc(...a),
  },
  supabaseReady: true,
}))

import { jetonBakiyesiniOku } from '../jeton'
import { fetchUsageStats } from '../usageStats'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  rpc.mockReset()
})

describe('jetonBakiyesiniOku — zaman aşımı', () => {
  it('6 sn yanıt yoksa istek iptal edilir ve null döner (menü asılı kalmaz)', async () => {
    vi.useFakeTimers()
    let sinyal: AbortSignal | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit = {}) =>
          new Promise((_coz, reddet) => {
            sinyal = init.signal ?? undefined
            sinyal?.addEventListener('abort', () => reddet(new DOMException('aborted', 'AbortError')))
          }),
      ),
    )
    const sonuc = jetonBakiyesiniOku()
    await vi.advanceTimersByTimeAsync(5999)
    expect(sinyal?.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    expect(sinyal?.aborted).toBe(true)
    await expect(sonuc).resolves.toBeNull()
  })
})

describe('fetchUsageStats — sayı olmayan sayaç', () => {
  it.each([
    [{ accounts: 'yok', devices_total: 3 }],
    [{ accounts: 4, devices_total: 'bilinmiyor' }],
  ])('%o → null (uydurma sayı gösterilmez)', async (satir) => {
    rpc.mockResolvedValue({ data: [satir], error: null })
    await expect(fetchUsageStats()).resolves.toBeNull()
  })
})
