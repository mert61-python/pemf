// Author: mertaygn, cglrgrkn
/**
 * KP-2 · scripts/check-legal-config.mjs · SÜREÇ İÇİ sözleşmeler (mevcut `check-legal-config.test.ts` betiği alt süreçte koşar → kapsamı
 * ölçülmüyordu; burada modül AYNI süreçte yüklenir, `process.exit` / `console` en alt katta sahte):
 *  - tüm zorunlu alanlar dolu → "✓ … tam" ve çıkış 0; hata çıktısı YOK,
 *  - placeholder / boş / yalnız boşluk alan → "BUILD DURDURULDU", alan adı + değeriyle, çıkış 1; ALLOW_LEGAL_PLACEHOLDERS=1 → UYARI + çıkış 0,
 *  - zorunlu alan YOK ya da COMPANY bloğu YOK → yapısal bulgu; ALLOW=1 ile bile çıkış 1 ve "kod hatasıdır" iletisi,
 *  - çift tırnak / ters tırnak değerleri de alan sayılır; `} as const` yoksa blok dosya sonuna dek okunur,
 *  - argümansız çağrı betiğin yanındaki `../src/config.ts`yi okur (açık yolla aynı sonuç).
 * Yapılandırma dosyaları yalnız geçici dizinde (gerçek `src/config.ts` YALNIZ OKUNUR).
 */
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const gecici = mkdtempSync(join(tmpdir(), 'kp2-yasal-'))
let sira = 0
afterAll(() => rmSync(gecici, { recursive: true, force: true }))
afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

class Cikis extends Error {
  constructor(public kod: number) {
    super(`process.exit(${kod})`)
  }
}

const ZORUNLU = ['legalName', 'address', 'city', 'country', 'phone', 'email', 'kvkkEmail', 'taxOffice', 'taxNo', 'mersis', 'tradeRegistry']

/** Sentetik yapılandırma: COMPANY bloğu + verilen alan satırları (varsayılan: tüm zorunlular DOLU). */
function yapilandirma(alanlar: Record<string, string> = {}, sonEk = '} as const'): string {
  const hepsi: Record<string, string> = { brandName: "'PEMF Vet'" }
  for (const a of ZORUNLU) hepsi[a] = `'DOLU-${a}'`
  Object.assign(hepsi, alanlar)
  const satirlar = Object.entries(hepsi)
    .filter(([, v]) => v !== '__SIL__')
    .map(([k, v]) => `  ${k}: ${v},`)
  return `export const SITE = 'x'\n\nexport const COMPANY = {\n${satirlar.join('\n')}\n${sonEk}\n\nexport const SONRAKI = {\n  ad: '[YER TUTUCU]',\n}\n`
}

async function kos(icerik: string | null, allow = '') {
  vi.restoreAllMocks() // aynı testte ikinci koşu önceki casusun çağrılarını taşımasın
  vi.resetModules()
  let yol: string | undefined
  if (icerik !== null) {
    yol = join(gecici, `config-${++sira}.ts`)
    writeFileSync(yol, icerik, 'utf8')
  }
  vi.stubEnv('ALLOW_LEGAL_PLACEHOLDERS', allow)
  const log = vi.spyOn(console, 'log').mockImplementation(() => {})
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
  const error = vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(process, 'exit').mockImplementation(((k?: number) => {
    throw new Cikis(k ?? 0)
  }) as never)
  const eskiArgv = process.argv
  process.argv = [eskiArgv[0], 'check-legal-config.mjs', ...(yol ? [yol] : [])]
  let kod = -1
  try {
    await import('../check-legal-config.mjs')
  } catch (e) {
    if (!(e instanceof Cikis)) throw e
    kod = e.kod
  } finally {
    process.argv = eskiArgv
  }
  const yaz = (s: { mock: { calls: unknown[][] } }) => s.mock.calls.map((c) => c.join(' ')).join('\n')
  return { kod, log: yaz(log), warn: yaz(warn), error: yaz(error) }
}

describe('check-legal-config (süreç içi)', () => {
  it('tüm zorunlu alanlar dolu → "✓ Yasal yapılandırma tam … (11 zorunlu alan dolu)" ve çıkış 0, hata çıktısı yok', async () => {
    const r = await kos(yapilandirma())
    expect(r.kod).toBe(0)
    expect(r.log).toBe('✓ Yasal yapılandırma tam — placeholder / boş alan yok (11 zorunlu alan dolu).')
    expect(r.error).toBe('')
    expect(r.warn).toBe('')
  })

  it('placeholder → BUILD DURDURULDU, "COMPANY.mersis = [MERSİS NO]", sayaç 1, ALLOW ipucu; çıkış 1', async () => {
    const r = await kos(yapilandirma({ mersis: "'[MERSİS NO]'" }))
    expect(r.kod).toBe(1)
    expect(r.error).toContain('✖ BUILD DURDURULDU:')
    expect(r.error).toContain('Yasal/satıcı kimlik alanlarında 1 eksik (placeholder / boş / yok):')
    expect(r.error).toContain('    • COMPANY.mersis = [MERSİS NO]')
    expect(r.error).toContain('Bilerek yayınlamak için: ALLOW_LEGAL_PLACEHOLDERS=1 npm run build')
    expect(r.error).not.toContain('kod hatasıdır')
    expect(r.log).toBe('')
  })

  it('boş ve yalnız-boşluk alanlar BOŞ sayılır: değer tırnaklı gösterilir, sayaç 2', async () => {
    const r = await kos(yapilandirma({ taxNo: "''", phone: "'   '" }))
    expect(r.kod).toBe(1)
    expect(r.error).toContain("COMPANY.taxNo = '' (BOŞ)")
    expect(r.error).toContain("COMPANY.phone = '   ' (BOŞ)")
    expect(r.error).toContain('alanlarında 2 eksik')
  })

  it('ALLOW_LEGAL_PLACEHOLDERS=1 + placeholder → UYARI (bilinçli atlandı) ve çıkış 0; hata çıktısı yok', async () => {
    const r = await kos(yapilandirma({ kvkkEmail: "'[KVKK E-POSTA]'" }), '1')
    expect(r.kod).toBe(0)
    expect(r.warn).toContain('⚠️  UYARI (bilinçli atlandı):')
    expect(r.warn).toContain('COMPANY.kvkkEmail = [KVKK E-POSTA]')
    expect(r.error).toBe('')
  })

  it('ALLOW yalnız "1" ile açılır: "true" değeri placeholder\'ı GEÇİRMEZ', async () => {
    const r = await kos(yapilandirma({ mersis: "'[MERSİS]'" }), 'true')
    expect(r.kod).toBe(1)
  })

  it('zorunlu alan SİLİNMİŞ → yapısal bulgu "alan YOK", ALLOW=1 ile bile çıkış 1 ve kod hatası iletisi', async () => {
    const r = await kos(yapilandirma({ tradeRegistry: '__SIL__' }), '1')
    expect(r.kod).toBe(1)
    expect(r.error).toContain('COMPANY.tradeRegistry = alan YOK (dize değeri olarak tanımlı değil)')
    expect(r.error).toContain('Alan ya da COMPANY bloğu YOK — bu bir kod hatasıdır; ALLOW_LEGAL_PLACEHOLDERS ile geçilemez.')
    expect(r.error).not.toContain('Bilerek yayınlamak için')
    expect(r.warn).toBe('')
  })

  it('zorunlu alan dize DEĞİL (değişken başvurusu) → "alan YOK" sayılır', async () => {
    const r = await kos(yapilandirma({ email: 'DESTEK_EPOSTASI' }))
    expect(r.kod).toBe(1)
    expect(r.error).toContain('COMPANY.email = alan YOK')
  })

  it('COMPANY bloğu yok → "(blok)" yapısal bulgusu, ALLOW=1 ile bile çıkış 1', async () => {
    const r = await kos(yapilandirma().replace('export const COMPANY', 'export const SIRKET'), '1')
    expect(r.kod).toBe(1)
    expect(r.error).toContain('COMPANY.(blok) = `export const COMPANY` bulunamadı — yasal alanlar denetlenemedi')
    expect(r.error).toContain('kod hatasıdır')
  })

  it('çift tırnak ve ters tırnak değerleri de alan sayılır (boş ters tırnak BOŞ bulgusu verir)', async () => {
    const dolu = await kos(yapilandirma({ taxNo: '"1234567890"', mersis: '`0123456789012345`' }))
    expect(dolu.kod).toBe(0)
    const bos = await kos(yapilandirma({ mersis: '``' }))
    expect(bos.kod).toBe(1)
    expect(bos.error).toContain("COMPANY.mersis = '' (BOŞ)")
  })

  it('`} as const` sonlandırıcısı yoksa blok dosya SONUNA dek okunur: sonraki nesnedeki placeholder da bulgu olur', async () => {
    const r = await kos(yapilandirma({}, '}'))
    expect(r.kod).toBe(1)
    expect(r.error).toContain('COMPANY.ad = [YER TUTUCU]')
  })

  it('KARŞIT: sonlandırıcı varken blok DIŞINDAKİ placeholder bulgu SAYILMAZ', async () => {
    const r = await kos(yapilandirma())
    expect(r.kod).toBe(0)
    expect(r.error).not.toContain('COMPANY.ad')
  })

  it('argümansız çağrı betiğin yanındaki ../src/config.ts dosyasını okur (aynı dosyanın açık yoluyla AYNI sonuç)', async () => {
    const burasi = dirname(fileURLToPath(import.meta.url))
    const gercek = readFileSync(resolve(burasi, '../../src/config.ts'), 'utf8')
    const acik = await kos(gercek)
    const argumansiz = await kos(null)
    expect(argumansiz.kod).toBe(acik.kod)
    expect(argumansiz.error).toBe(acik.error)
    expect(argumansiz.log).toBe(acik.log)
  })
})
