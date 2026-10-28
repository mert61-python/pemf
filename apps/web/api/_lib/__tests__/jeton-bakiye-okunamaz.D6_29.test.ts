// Author: mertaygn, cglrgrkn
/**
 * D6.29 (B-7.9) — jeton bakiyesi OKUNAMAZSA site hesap menüsü uydurma "Kalan jeton 0" GÖSTERMEZ (okunamayan bakiye hiç çizilmez).
 *
 * 🔴 ÖLÇÜLEN (HEAD ebf1c3fe): `api/tokens.ts:48` RPC hatasını (`!r.ok`) "satır yok" ile AYNI `null`a çeviriyordu; `:65-71` o `null`u
 * 200 {kalan: 0, kayit_yok: true} yapıyordu → `src/lib/jeton.ts` 200'ü bakiye sayıp {kalan: 0} döndürüyor → `AccountButton.tsx:109`
 * "Kalan jeton 0" çiziyordu. Supabase kesintisinde kullanıcı jetonunun SIFIRLANDIĞINI görüyordu (07 E1/E2).
 *
 * ÖLÇÜT (sahte YALNIZ ağ kenarında): Supabase uçları (`/auth/v1/user`, `rpc/jeton_bakiyem`) sahte; `/api/tokens` isteği GERÇEK
 * `api/tokens.ts` handler'ına yönlenir; GERÇEK `jetonBakiyesiniOku()` çağrılır. Menü kutusu yalnız `jeton &&` koşulu altında (AST).
 * KARŞIT: satırı OLMAYAN kullanıcı (RPC 200 `[]`) GERÇEK okumadır → 200 `kayit_yok` + kalan 0 (cihaz `servers/jeton.py::_bakiye_satiri_oku`
 * ile aynı anlam); satırı olan kullanıcı → gerçek toplam.
 * ⚠️ DOM YOK: menü durumu (`acik`, `jeton`) etkiyle dolar, sunucu çiziminde açılmaz → kutu koşulu kaynağın AST'sinden ölçülür.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ts from 'typescript'

import ACCOUNT_SRC from '../../../src/components/AccountButton.tsx?raw'

vi.mock('../../../src/lib/supabase', () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: { access_token: 'jwt-kullanici' } } }) } },
}))

const OLD = { ...process.env }
const durum: { rpc: () => Response; api: null | (() => Response); sonApi: { kod: number; govde: unknown } | null } = {
  rpc: () => new Response('[]', { status: 200 }),
  api: null,
  sonApi: null,
}

const { default: handler } = await import('../../tokens.js')
const { jetonBakiyesiniOku } = await import('../../../src/lib/jeton')

async function gercekHandlerdan(yetki: string): Promise<Response> {
  let kod = 0
  let govde: unknown = null
  const res = {
    status(k: number) { kod = k; return res },
    json(g: unknown) { govde = g; return res },
  }
  await handler({ method: 'GET', headers: { authorization: yetki }, body: undefined } as never, res as never)
  durum.sonApi = { kod, govde }
  return new Response(JSON.stringify(govde), { status: kod, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  process.env.SUPABASE_URL = 'https://proje.supabase.co'
  process.env.SUPABASE_ANON_KEY = 'anon-anahtar-testte'
  durum.api = null
  durum.sonApi = null
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.stubGlobal('fetch', async (girdi: unknown, init?: { headers?: Record<string, string> }) => {
    const url = String(girdi)
    if (url === 'https://proje.supabase.co/auth/v1/user') return new Response(JSON.stringify({ id: 'u-1', email: 'v@k.tr' }), { status: 200 })
    if (url === 'https://proje.supabase.co/rest/v1/rpc/jeton_bakiyem') return durum.rpc()
    if (url === '/api/tokens') return durum.api ? durum.api() : gercekHandlerdan(init?.headers?.Authorization ?? '')
    throw new Error(`beklenmeyen ağ isteği: ${url}`)
  })
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  process.env = { ...OLD }
})

describe('D6.29 · okunamayan bakiye "0" DEĞİLDİR (RPC → api/tokens → lib/jeton zinciri)', () => {
  it('KRİTİK: jeton_bakiyem 503 → /api/tokens 5xx (kalan YOK) → jetonBakiyesiniOku() null', async () => {
    durum.rpc = () => new Response('{"message":"upstream"}', { status: 503 })
    const b = await jetonBakiyesiniOku()
    expect(durum.sonApi?.kod, 'RPC hatası 200 ile sunuldu (uydurma bakiye)').toBeGreaterThanOrEqual(500)
    expect(durum.sonApi?.govde).not.toHaveProperty('kalan')
    expect(b, 'okunamayan bakiye menüye sayı olarak gitti').toBeNull()
  })

  it('KRİTİK: RPC 200 ama dizi DEĞİL (beklenmeyen biçim) → okunamadı sayılır, "0" uydurulmaz', async () => {
    durum.rpc = () => new Response('{"code":"PGRST","message":"x"}', { status: 200 })
    const b = await jetonBakiyesiniOku()
    expect(durum.sonApi?.kod).toBeGreaterThanOrEqual(500)
    expect(b).toBeNull()
  })

  it('KARŞIT: satırı OLMAYAN kullanıcı (RPC 200 []) gerçek okumadır → 200 kayit_yok + kalan 0', async () => {
    durum.rpc = () => new Response('[]', { status: 200 })
    const b = await jetonBakiyesiniOku()
    expect(durum.sonApi).toEqual({ kod: 200, govde: expect.objectContaining({ kalan: 0, kayit_yok: true }) })
    expect(b).toEqual({ kalan: 0, aylikHak: 0, satinAlinan: 0, donemSonu: null })
  })

  it('KARŞIT: satırı olan kullanıcı → aylık hak + satın alınan', async () => {
    durum.rpc = () =>
      new Response(JSON.stringify([{ aylik_hak: 10, satin_alinan: 5, bekleyen_borc: 0, odeme_modeli: 'on_odemeli', kullandikca_borc: 0, donem_sonu: null }]), { status: 200 })
    const b = await jetonBakiyesiniOku()
    expect(durum.sonApi?.kod).toBe(200)
    expect(b).toEqual({ kalan: 15, aylikHak: 10, satinAlinan: 5, donemSonu: null })
  })
})

describe('D6.29 · istemci (lib/jeton) yalnız GERÇEK bakiyeyi kabul eder', () => {
  it('5xx yanıtın gövdesinde sayı olsa bile bakiye sayılmaz', async () => {
    durum.api = () => new Response(JSON.stringify({ kalan: 0, aylik_hak: 0 }), { status: 502 })
    expect(await jetonBakiyesiniOku()).toBeNull()
  })
  it('200 ama `kalan` alanı yok / sayı değil → null (eksik alan "0" diye uydurulmaz)', async () => {
    durum.api = () => new Response(JSON.stringify({ error: 'x' }), { status: 200 })
    expect(await jetonBakiyesiniOku()).toBeNull()
    durum.api = () => new Response(JSON.stringify({ kalan: '7' }), { status: 200 })
    expect(await jetonBakiyesiniOku()).toBeNull()
  })
})

describe('D6.29 · AccountButton kutusu yalnız okunmuş bakiyeyle çizilir', () => {
  it('"Kalan jeton" satırı YALNIZ `jeton && (…)` koşulunun içinde', () => {
    const sf = ts.createSourceFile('AccountButton.tsx', ACCOUNT_SRC, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const korunan: ts.Node[] = []
    const gez = (n: ts.Node): void => {
      if (
        ts.isBinaryExpression(n) &&
        n.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken &&
        ts.isIdentifier(n.left) &&
        n.left.text === 'jeton'
      ) korunan.push(n.right)
      ts.forEachChild(n, gez)
    }
    gez(sf)
    const kalanJeton = [...ACCOUNT_SRC.matchAll(/t\('hesap\.kalanJeton'\)/g)].map((m) => m.index ?? -1)
    expect(kalanJeton.length, 'hesap.kalanJeton çağrısı bulunamadı — kapı bayat').toBeGreaterThan(0)
    for (const konum of kalanJeton) {
      const icinde = korunan.some((d) => d.getStart(sf) <= konum && konum < d.getEnd())
      expect(icinde, `hesap.kalanJeton (konum ${konum}) "jeton &&" koşulunun DIŞINDA — okunamayan bakiye çizilebilir`).toBe(true)
    }
  })
})

// TUR 2 (çürütücü kolu): menü HER açılışta bakiyeyi yeniden okur — okunamayan (null) sonuç da `setJeton`'a gitmeli; yoksa ilk açılıştaki
// sayı, sonraki açılışta Supabase kesintisinde EKRANDA KALIR (okunamayan bakiye bayat sayı olarak gösterilir). Mutant `cur629_n3`
// (`.then((b) => { if (b) setJeton(b) })`) bu dosyada ve site kümesinde YAŞIYORDU (site vitest'inde DOM / jsdom yok → kaynak AST'si).
describe('D6.29 · tur 2 — her okuma sonucu (null dahil) bakiyeyi DEĞİŞTİRİR', () => {
  it('jetonBakiyesiniOku() sonucu KOŞULSUZ setJeton\'a gider (okunamayan yeniden okuma önceki sayıyı bırakmaz)', () => {
    const sf = ts.createSourceFile('AccountButton.tsx', ACCOUNT_SRC, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const okumalar: ts.CallExpression[] = []
    const gez = (n: ts.Node): void => {
      if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === 'jetonBakiyesiniOku') okumalar.push(n)
      ts.forEachChild(n, gez)
    }
    gez(sf)
    expect(okumalar.length, 'jetonBakiyesiniOku() çağrısı bulunamadı — kapı bayat').toBeGreaterThan(0)
    for (const c of okumalar) {
      const p = c.parent
      // Kabul: `.then(setJeton)` ya da `.then((b) => setJeton(b))` (eşdeğer yeniden yazım kapıyı bozmasın).
      const dogrudanAyar = (a: ts.Expression | undefined): boolean =>
        !!a &&
        ((ts.isIdentifier(a) && a.text === 'setJeton') ||
          (ts.isArrowFunction(a) && a.parameters.length === 1 && ts.isCallExpression(a.body) &&
            ts.isIdentifier(a.body.expression) && a.body.expression.text === 'setJeton' && a.body.arguments.length === 1 &&
            a.body.arguments[0].getText(sf) === a.parameters[0].name.getText(sf)))
      const thenIle =
        ts.isPropertyAccessExpression(p) && p.name.text === 'then' && ts.isCallExpression(p.parent) &&
        p.parent.arguments.length === 1 && dogrudanAyar(p.parent.arguments[0])
      const awaitIle =
        ts.isAwaitExpression(p) && ts.isCallExpression(p.parent) && ts.isIdentifier(p.parent.expression) &&
        p.parent.expression.text === 'setJeton'
      expect(
        thenIle || awaitIle,
        `okuma sonucu setJeton'a KOŞULSUZ gitmiyor (${p.parent.getText(sf).slice(0, 80)}) — null (okunamadı) önceki bakiyeyi silmez, bayat sayı görünür`,
      ).toBe(true)
    }
  })
})
