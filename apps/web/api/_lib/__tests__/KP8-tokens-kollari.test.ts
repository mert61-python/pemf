// Author: mertaygn, cglrgrkn
/**
 * KP-8 · api/tokens.ts kalan dallar (düzenek KP2-tokens ile AYNI: sahte `fetch` — Supabase `/auth/v1/user` + RPC):
 *  - ne `Authorization` başlığı ne gövde var → 401 ve Supabase'e GİDİLMEZ (kimlik yok).
 *  - jeton gövdeden de okunur (başlık yoksa).
 *  - bakiye satırında ödeme modeli / kullandıkça borcu yoksa varsayılan: ön ödemeli, borç 0.
 *  - gövdesiz tüketim isteği → 400 {miktar} ve RPC YOK.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import handler from '../../tokens'

type Kayit = { url: string; yontem: string; basliklar: Record<string, string>; govde: unknown }
let kayit: Kayit[] = []
let rpcYanit: () => Response = () => json({ ok: true, kalan: 0 })
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })

function agKur() {
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
      if (String(url).endsWith('/auth/v1/user')) return json({ id: 'u-1', email: 'vet@ornek.test' })
      return rpcYanit()
    }),
  )
}

function sahteRes() {
  const res = { kod: 0, govde: undefined as unknown } as { kod: number; govde: Record<string, unknown> } & Record<string, unknown>
  res.status = (k: number) => ((res.kod = k), res)
  res.json = (g: Record<string, unknown>) => ((res.govde = g), res)
  return res
}

async function cagir(govde: Record<string, unknown> | undefined, yontem = 'POST') {
  const res = sahteRes()
  await handler({ method: yontem, headers: { authorization: 'Bearer kullanici-jwt' }, body: govde } as never, res as never)
  return res
}
const rpcCagrilari = () => kayit.filter((k) => k.url.includes('/rpc/jeton_tuket'))

beforeEach(() => {
  vi.stubEnv('SUPABASE_URL', 'https://proje-ornek.supabase.test')
  vi.stubEnv('SUPABASE_ANON_KEY', 'test-anon-anahtari')
  rpcYanit = () => json({ ok: true, kalan: 0 })
  agKur()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})


async function ham(req: Record<string, unknown>) {
  const res = sahteRes()
  await handler(req as never, res as never)
  return res
}

it('başlık + gövde yok → 401; Supabase\'e GİDİLMEZ', async () => {
  const res = await ham({ method: 'GET', headers: {} })
  expect(res.kod).toBe(401)
  expect(kayit).toHaveLength(0)
})

it('jeton gövdeden okunur; bakiye satırında model / borç yoksa ön ödemeli + 0', async () => {
  rpcYanit = () => json([{ aylik_hak: 50, satin_alinan: 5, bekleyen_borc: 0, donem_sonu: null }])
  const res = await ham({ method: 'GET', headers: {}, body: { token: 'govdedeki-jwt' } })
  expect(res.kod).toBe(200)
  expect(res.govde).toMatchObject({ kalan: 55, odeme_modeli: 'on_odemeli', kullandikca_borc: 0 })
  expect(kayit.find((k) => k.url.endsWith('/auth/v1/user'))?.basliklar.Authorization).toBe('Bearer govdedeki-jwt')
})

it('gövdesiz tüketim → 400 {miktar}; RPC YOK', async () => {
  const res = await cagir(undefined)
  expect(res.kod).toBe(400)
  expect(res.govde).toEqual({ error: 'miktar', message: 'Geçersiz jeton miktarı.' })
  expect(rpcCagrilari()).toHaveLength(0)
})
