// Author: mertaygn, cglrgrkn
/**
 * KP-2 · api/tokens.ts · sözleşmeler (TÜKETİM ucu, POST): geçersiz miktar / eksik-kısa idempotans anahtarı → 400 ve RPC'ye HİÇ
 * gidilmez · geçerli istek `jeton_tuket` RPC'sine kullanıcının KENDİ JWT'siyle, varsayılanlarıyla (`tur`='analiz', detay/cihaz null)
 * gider · RPC hatası → 502 sade mesaj · yetersiz bakiye → 402 ve mesaj tedavinin (seans / acil durdurma / sensör) ETKİLENMEDİĞİNİ
 * söyler · bakiye tanımsız → 402 · başka red → 400 + sebep · başarı → 200 (kalan, tekrar; yalnız kullandıkça-öde dalında model+borç) ·
 * desteklenmeyen yöntem → 405 · beklenmeyen istisna → 500 genel mesaj (iç ayrıntı sızmaz).
 * Jeton ücretlendirmesi Y194 ile cihazda KAPALI — bu dosya yalnız ucun BUGÜNKÜ davranışını sabitler.
 *
 * Sahte EN ALT katta: `fetch` (Supabase `/auth/v1/user` + RPC; gerçek `Response`). Anahtarlar açıkça sahte.
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

describe('POST /api/tokens — doğrulama', () => {
  it.each([
    ['miktar yok', { istek_id: 'istek-12345' }],
    ['miktar 0', { miktar: 0, istek_id: 'istek-12345' }],
    ['miktar negatif', { miktar: -3, istek_id: 'istek-12345' }],
    ['miktar kesirli', { miktar: 1.5, istek_id: 'istek-12345' }],
    ['miktar metin', { miktar: '2', istek_id: 'istek-12345' }],
  ])('%s → 400 {error:"miktar"} ve RPC çağrılmaz', async (_ad, govde) => {
    const res = await cagir(govde)
    expect(res.kod).toBe(400)
    expect(res.govde).toEqual({ error: 'miktar', message: 'Geçersiz jeton miktarı.' })
    expect(rpcCagrilari()).toHaveLength(0)
  })

  it.each([
    ['istek_id yok', { miktar: 1 }],
    ['istek_id 7 karakter', { miktar: 1, istek_id: '1234567' }],
    ['istek_id sayı', { miktar: 1, istek_id: 123456789 }],
  ])('%s → 400 {error:"istek_id"} ve RPC çağrılmaz (çift düşme kapısı açılmaz)', async (_ad, govde) => {
    const res = await cagir(govde)
    expect(res.kod).toBe(400)
    expect(res.govde).toEqual({ error: 'istek_id', message: 'Geçersiz istek kimliği.' })
    expect(rpcCagrilari()).toHaveLength(0)
  })
})

describe('POST /api/tokens — RPC çağrısı ve sonuçları', () => {
  it('geçerli istek → jeton_tuket RPC\'sine kullanıcı JWT\'si + anon anahtarla; tur varsayılanı "analiz", detay/cihaz null', async () => {
    rpcYanit = () => json({ ok: true, kalan: 7 })
    await cagir({ miktar: 2, istek_id: 'istek-12345678' })
    expect(rpcCagrilari()).toEqual([
      {
        url: 'https://proje-ornek.supabase.test/rest/v1/rpc/jeton_tuket',
        yontem: 'POST',
        basliklar: { apikey: 'test-anon-anahtari', Authorization: 'Bearer kullanici-jwt', 'Content-Type': 'application/json' },
        govde: { p_miktar: 2, p_tur: 'analiz', p_detay: null, p_istek_id: 'istek-12345678', p_cihaz_id: null },
      },
    ])
  })

  it('tur / detay / cihaz_id verilirse RPC gövdesine AYNEN geçer', async () => {
    await cagir({ miktar: 5, istek_id: 'istek-abcdefgh', tur: 'ai_pro', detay: 'seans-9', cihaz_id: 'cihaz-3' })
    expect(rpcCagrilari()[0].govde).toEqual({ p_miktar: 5, p_tur: 'ai_pro', p_detay: 'seans-9', p_istek_id: 'istek-abcdefgh', p_cihaz_id: 'cihaz-3' })
  })

  it('başarı (ön ödemeli) → 200 {ok, kalan, tekrar:false}; model/borç alanı GÖNDERİLMEZ', async () => {
    rpcYanit = () => json({ ok: true, kalan: 41 })
    const res = await cagir({ miktar: 1, istek_id: 'istek-12345678' })
    expect(res.kod).toBe(200)
    expect(res.govde).toEqual({ ok: true, kalan: 41, tekrar: false })
  })

  it('başarı + tekrar (idempotans) → tekrar:true; kalan yoksa 0', async () => {
    rpcYanit = () => json({ ok: true, tekrar: 1 })
    const res = await cagir({ miktar: 1, istek_id: 'istek-12345678' })
    expect(res.govde).toEqual({ ok: true, kalan: 0, tekrar: true })
  })

  it('başarı (kullandıkça-öde) → model:"kullandikca" + borç; borç yoksa 0', async () => {
    rpcYanit = () => json({ ok: true, kalan: 0, model: 'kullandikca', borc: 12 })
    expect((await cagir({ miktar: 1, istek_id: 'istek-12345678' })).govde).toEqual({ ok: true, kalan: 0, tekrar: false, model: 'kullandikca', borc: 12 })
    rpcYanit = () => json({ ok: true, kalan: 0, model: 'kullandikca' })
    expect((await cagir({ miktar: 1, istek_id: 'istek-12345678' })).govde).toEqual({ ok: true, kalan: 0, tekrar: false, model: 'kullandikca', borc: 0 })
  })

  it('yetersiz bakiye → 402 yetersiz_jeton, kalan; mesaj tedavinin ETKİLENMEDİĞİNİ söyler', async () => {
    rpcYanit = () => json({ ok: false, sebep: 'yetersiz', kalan: 3 })
    const res = await cagir({ miktar: 5, istek_id: 'istek-12345678' })
    expect(res.kod).toBe(402)
    expect(res.govde.error).toBe('yetersiz_jeton')
    expect(res.govde.kalan).toBe(3)
    expect(res.govde.message).toContain('yeni yapay zekâ analizi başlatılamadı')
    expect(res.govde.message).toContain('Seans, acil durdurma ve sensör izleme etkilenmez')
  })

  it('yetersiz bakiye, kalan alanı yok → kalan 0', async () => {
    rpcYanit = () => json({ ok: false, sebep: 'yetersiz' })
    expect((await cagir({ miktar: 5, istek_id: 'istek-12345678' })).govde.kalan).toBe(0)
  })

  it('bakiye tanımsız → 402 bakiye_yok, kalan 0', async () => {
    rpcYanit = () => json({ ok: false, sebep: 'bakiye_yok' })
    const res = await cagir({ miktar: 1, istek_id: 'istek-12345678' })
    expect(res.kod).toBe(402)
    expect(res.govde).toEqual({ error: 'bakiye_yok', kalan: 0, message: 'Hesabınızda jeton tanımlı değil.' })
  })

  it('başka red sebebi → 400 + o sebep; sebepsiz red → 400 "bilinmeyen"', async () => {
    rpcYanit = () => json({ ok: false, sebep: 'cihaz_kilitli' })
    const a = await cagir({ miktar: 1, istek_id: 'istek-12345678' })
    expect(a.kod).toBe(400)
    expect(a.govde).toEqual({ error: 'cihaz_kilitli', message: 'Jeton işlemi tamamlanamadı.' })
    rpcYanit = () => json(null)
    const b = await cagir({ miktar: 1, istek_id: 'istek-12345678' })
    expect(b.kod).toBe(400)
    expect(b.govde).toEqual({ error: 'bilinmeyen', message: 'Jeton işlemi tamamlanamadı.' })
  })

  it('RPC hatası (500) → 502 altyapi; sağlayıcı ayrıntısı YALNIZ günlüğe', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    rpcYanit = () => new Response('pg: relation "jeton_defteri" does not exist', { status: 500 })
    const res = await cagir({ miktar: 1, istek_id: 'istek-12345678' })
    expect(res.kod).toBe(502)
    expect(res.govde).toEqual({ error: 'altyapi', message: 'Jeton işlemi tamamlanamadı.' })
    expect(gunluk).toHaveBeenCalledWith('[jeton] RPC hatası:', 500, 'pg: relation "jeton_defteri" does not exist')
    expect(JSON.stringify(res.govde)).not.toContain('jeton_defteri')
  })
})

describe('/api/tokens — yöntem ve istisna', () => {
  it('PUT → 405 {error:"method"} (kimlik doğrulandıktan sonra)', async () => {
    const res = await cagir(undefined, 'PUT')
    expect(res.kod).toBe(405)
    expect(res.govde).toEqual({ error: 'method' })
  })

  it('kimlik doğrulama sırasında ağ istisnası → 500 genel mesaj; istisna metni yanıta sızmaz', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('fetch failed: getaddrinfo proje-ornek') }))
    const res = await cagir({ miktar: 1, istek_id: 'istek-12345678' })
    expect(res.kod).toBe(500)
    expect(res.govde).toEqual({ error: 'sunucu', message: 'Beklenmeyen bir hata oluştu.' })
    expect(gunluk).toHaveBeenCalledWith('[jeton] beklenmeyen hata:', expect.any(TypeError))
  })

  it('jeton gövdede (başlık yok) → aynı JWT RPC\'ye gider', async () => {
    const res = sahteRes()
    await handler({ method: 'POST', headers: {}, body: { token: 'govde-jwt', miktar: 1, istek_id: 'istek-12345678' } } as never, res as never)
    expect(res.kod).toBe(200)
    expect(rpcCagrilari()[0].basliklar.Authorization).toBe('Bearer govde-jwt')
  })
})
