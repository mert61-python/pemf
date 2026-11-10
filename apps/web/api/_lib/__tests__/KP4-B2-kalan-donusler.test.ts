// Author: mertaygn, cglrgrkn
/**
 * KP-4 · B2 · site API'sinin kapsanmamış ERKEN DÖNÜŞLERİ (KP-3 sonu: satırlar kapsanmış, dönüş deyimleri koşmamış) · sözleşmeler:
 *  tokens — oturum doğrulanamazsa (Supabase `/auth/v1/user` 401) 401 "Önce giriş yapın." ve RPC'ye HİÇ gidilmez · RPC hata verip
 *  gövdesi de OKUNAMAZSA (text() reddi) yine 502 sade mesaj (günlüğe boş ayrıntı; istisna sızmaz).
 *  checkout — geçersiz / eksik plan kademesi 400 {error:'tier'} ve ne Supabase'e ne iyzico'ya gidilir.
 *  webhook — POST dışı yöntem 405 {error:'method'} (imza / gövde işlenmez).
 *  util — `getSubscriptionRefByUser('')` ağa ÇIKMADAN null.
 *
 * Sahte EN ALT katta: `fetch` (Supabase REST / auth) ve `iyzipay` SDK (checkout modülü yükleyebilsin diye). Anahtarlar açıkça sahte.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('iyzipay', () => ({
  default: class {
    static LOCALE = { TR: 'tr', EN: 'en' }
    subscription = {}
    subscriptionCheckoutForm = {}
  },
}))

import checkout from '../../checkout'
import tokens from '../../tokens'
import webhook from '../../webhook'
import { getSubscriptionRefByUser } from '../util'

type Kayit = { url: string; yontem: string }
let kayit: Kayit[] = []
let ag: (url: string) => Response | Record<string, unknown> = () => json({})
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })

function sahteRes() {
  const res = { kod: 0, govde: undefined as unknown } as { kod: number; govde: Record<string, unknown> } & Record<string, unknown>
  res.status = (k: number) => ((res.kod = k), res)
  res.json = (g: Record<string, unknown>) => ((res.govde = g), res)
  return res
}

beforeEach(() => {
  vi.stubEnv('SUPABASE_URL', 'https://proje-ornek.supabase.test')
  vi.stubEnv('SUPABASE_ANON_KEY', 'test-anon-anahtari')
  kayit = []
  ag = () => json({})
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      kayit.push({ url: String(url), yontem: init.method ?? 'GET' })
      return ag(String(url))
    }),
  )
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('tokens — oturum ve RPC gövdesi', () => {
  it('oturum doğrulanamazsa 401 ve RPC çağrılmaz', async () => {
    ag = (url) => (url.endsWith('/auth/v1/user') ? json({ msg: 'invalid JWT' }, 401) : json({ ok: true, kalan: 1 }))
    const res = sahteRes()
    await tokens({ method: 'POST', headers: { authorization: 'Bearer bayat-jwt' }, body: { miktar: 1, istek_id: 'istek-12345' } } as never, res as never)
    expect(res.kod).toBe(401)
    expect(res.govde).toEqual({ error: 'auth', message: 'Önce giriş yapın.' })
    expect(kayit.filter((k) => k.url.includes('/rpc/'))).toHaveLength(0)
  })

  it('RPC hatası + gövde okunamazsa yine 502 sade mesaj, ayrıntı günlüğe boş düşer', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    ag = (url) =>
      url.endsWith('/auth/v1/user')
        ? json({ id: 'u-1', email: 'vet@ornek.test' })
        : { ok: false, status: 503, text: () => Promise.reject(new Error('akış koptu')), json: async () => ({}) }
    const res = sahteRes()
    await tokens({ method: 'POST', headers: { authorization: 'Bearer kullanici-jwt' }, body: { miktar: 1, istek_id: 'istek-12345' } } as never, res as never)
    expect(res.kod).toBe(502)
    expect(res.govde).toEqual({ error: 'altyapi', message: 'Jeton işlemi tamamlanamadı.' })
    expect(gunluk).toHaveBeenCalledWith('[jeton] RPC hatası:', 503, '')
  })
})

describe('checkout — plan kademesi', () => {
  it.each([[undefined], ['basic'], ['PRO']])('kademe %s → 400 tier, ağa gidilmez', async (tier) => {
    const res = sahteRes()
    await checkout({ method: 'POST', headers: {}, body: { tier, token: 'kullanici-jwt' } } as never, res as never)
    expect(res.kod).toBe(400)
    expect(res.govde).toEqual({ error: 'tier' })
    expect(kayit).toHaveLength(0)
  })
})

describe('webhook — yöntem', () => {
  it.each(['GET', 'PUT', 'DELETE'])('%s → 405 method, gövde işlenmez', async (yontem) => {
    const res = sahteRes()
    await webhook({ method: yontem, headers: {}, body: { iyziEventType: 'X' } } as never, res as never)
    expect(res.kod).toBe(405)
    expect(res.govde).toEqual({ error: 'method' })
    expect(kayit).toHaveLength(0)
  })
})

describe('util — abonelik referansı', () => {
  it('kullanıcı kimliği boşsa ağa çıkmadan null', async () => {
    await expect(getSubscriptionRefByUser('')).resolves.toBeNull()
    expect(kayit).toHaveLength(0)
  })
})
