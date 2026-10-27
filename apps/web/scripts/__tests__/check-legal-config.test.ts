/**
 * Yasal yapılandırma yayın kapısı — denetim bulgusu: satıcı kimliği, açık adres, vergi no,
 * MERSİS ve KVKK BAŞVURU E-POSTASI dahil 10 alan `[PLACEHOLDER]` olarak CANLI sitede
 * yayınlanıyordu (Mesafeli Satış Sözleşmesi / Ön Bilgilendirme / KVKK metinlerine basılıyor).
 * Değerleri kod uyduramaz → yapılacak doğru şey EKSİKKEN YAYINLANMASINI engellemektir.
 *
 * Bu test kapının gerçekten kapı olduğunu doğrular (sessizce "ok" demediğini).
 *
 * D5.09 (B-7.19): kapı yalnız `'[…]'` kalıbını arıyordu → `mersis: ''` / `taxNo: '   '` / alanın silinmesi "✓ tam" diyordu
 * (ölçüldü: `_inceleme/D5.09/sonda_bos_alan.sh`). Aşağıdaki küme GERÇEK `src/config.ts`ten TÜRETİLEN geçici kopyalarla (gerçek
 * dosyaya dokunmadan) boş / eksik alan senaryolarını koşar. Yasal değerler (MERSİS, vergi no …) değiştirilmez; yalnız kopyada.
 */
import { afterAll, describe, it, expect } from 'vitest'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const script = resolve(here, '../check-legal-config.mjs')

// spawnSync: hem stdout hem stderr gerekiyor (hata `console.error`, uyarı `console.warn` → stderr).
function run(env: Record<string, string> = {}, args: string[] = []): { code: number; out: string } {
  const r = spawnSync(process.execPath, [script, ...args], {
    encoding: 'utf8',
    env: { ...process.env, ...env },
  })
  return { code: r.status ?? 1, out: `${r.stdout ?? ''}${r.stderr ?? ''}` }
}

describe('check-legal-config kapısı', () => {
  it('KRİTİK: COMPANY placeholder içeriyorken build DURDURULUR (exit != 0)', () => {
    const { code, out } = run()
    // Alanlar doldurulduğunda bu test "geçer" hâle gelir; o zaman aşağıdaki iki dal da doğru kalır.
    if (code === 0) {
      expect(out).toContain('Yasal yapılandırma tam')
      return
    }
    expect(code).not.toBe(0)
    expect(out).toContain('BUILD DURDURULDU')
    expect(out).toContain('COMPANY.kvkkEmail')   // KVKK başvuru kanalı — yasal zorunluluk
  })

  it('ALLOW_LEGAL_PLACEHOLDERS=1 ile bilinçli geçilebilir ama UYARI basar', () => {
    const { code, out } = run({ ALLOW_LEGAL_PLACEHOLDERS: '1' })
    expect(code).toBe(0)
    // Placeholder varsa uyarı, yoksa "tam" mesajı — ikisi de kabul.
    expect(out).toMatch(/UYARI|Yasal yapılandırma tam/)
  })
})

describe('check-legal-config — BOŞ / EKSİK zorunlu alan (D5.09 · B-7.19)', () => {
  // Testin BAĞIMSIZ listesi (betiktekinden ayrı yazılır: betiğin listesinden bir ad düşerse silinme testi yakalar).
  const ZORUNLU = [
    'legalName', 'address', 'city', 'country', 'phone', 'email', 'kvkkEmail',
    'taxOffice', 'taxNo', 'mersis', 'tradeRegistry',
  ]
  const GERCEK = readFileSync(resolve(here, '../../src/config.ts'), 'utf8')
  const gecici = mkdtempSync(join(tmpdir(), 'yasal-kapi-'))
  let sira = 0
  afterAll(() => rmSync(gecici, { recursive: true, force: true }))

  /** Türetilmiş yapılandırmayı geçici dosyaya yazıp kapıyı ONA karşı koşar (ALLOW bayrağı ortamdan sızmaz). */
  function kopyada(src: string, env: Record<string, string> = {}): { code: number; out: string } {
    const yol = join(gecici, `config-${++sira}.ts`)
    writeFileSync(yol, src, 'utf8')
    return run({ ALLOW_LEGAL_PLACEHOLDERS: '', ...env }, [yol])
  }

  /** COMPANY bloğunun içinde (yalnız orada) değişiklik yapar. */
  function blokta(src: string, f: (blok: string) => string): string {
    const bas = src.indexOf('export const COMPANY')
    const son = src.indexOf('} as const', bas)
    expect(bas, 'gerçek config.ts\'de COMPANY bloğu yok').toBeGreaterThan(-1)
    expect(son).toBeGreaterThan(bas)
    return src.slice(0, bas) + f(src.slice(bas, son)) + src.slice(son)
  }

  const alanKalibi = (alan: string) => new RegExp(`^([ \\t]*${alan}[ \\t]*:[ \\t]*)'[^'\\n]*'`, 'm')

  function alanDegeri(src: string, alan: string, yeni: string): string {
    return blokta(src, (blok) => {
      expect(alanKalibi(alan).test(blok), `COMPANY.${alan} dize alanı bulunamadı`).toBe(true)
      return blok.replace(alanKalibi(alan), (_t, on: string) => `${on}'${yeni}'`)
    })
  }

  function alanSil(src: string, alan: string): string {
    return blokta(src, (blok) => {
      const satir = new RegExp(`^[ \\t]*${alan}[ \\t]*:[^\\n]*\\n`, 'm')
      expect(satir.test(blok), `COMPANY.${alan} satırı bulunamadı`).toBe(true)
      return blok.replace(satir, '')
    })
  }

  // Taban: tüm dize alanları DOLU (gerçek değerler yerine işaretli dolgu — yalnız geçici kopyada). Böylece her senaryoda YALNIZ
  // bozulan alan bulgu üretir; gerçek yapılandırmada ileride placeholder olsa da bu küme anlamını korur.
  const DOLU = blokta(GERCEK, (blok) => blok.replace(/^([ \t]*(\w+)[ \t]*:[ \t]*)'[^'\n]*'/gm, (_t, on: string, ad: string) => `${on}'DOLU-${ad}'`))

  it('VAKUM: zorunlu alanların HER BİRİ gerçek COMPANY bloğunda dize olarak var', () => {
    const blok = GERCEK.slice(GERCEK.indexOf('export const COMPANY'), GERCEK.indexOf('} as const', GERCEK.indexOf('export const COMPANY')))
    for (const alan of ZORUNLU) expect(alanKalibi(alan).test(blok), `COMPANY.${alan}`).toBe(true)
  })

  it('KARŞIT: tüm alanları DOLU türetilmiş kopya GEÇER (yol argümanı düzeneği sahte kırmızı üretmez)', () => {
    const { code, out } = kopyada(DOLU)
    expect(out).toContain('Yasal yapılandırma tam')
    expect(code).toBe(0)
  })

  it('KARŞIT: gerçek yapılandırmanın DEĞİŞMEMİŞ kopyası gerçek dosyayla AYNI sonucu verir', () => {
    const gercek = run({ ALLOW_LEGAL_PLACEHOLDERS: '' })
    expect(kopyada(GERCEK).code).toBe(gercek.code)
  })

  it.each(ZORUNLU)('KRİTİK: COMPANY.%s BOŞ (\'\') iken build DURDURULUR', (alan) => {
    const { code, out } = kopyada(alanDegeri(DOLU, alan, ''))
    expect(out, `COMPANY.${alan} boşken kapı "tam" dedi`).not.toContain('Yasal yapılandırma tam')
    expect(code).toBe(1)
    expect(out).toContain('BUILD DURDURULDU')
    expect(out).toContain(`COMPANY.${alan}`)
  })

  it('KRİTİK: yalnız boşluk (taxNo = \'   \') da BOŞ sayılır', () => {
    const { code, out } = kopyada(alanDegeri(DOLU, 'taxNo', '   '))
    expect(code).toBe(1)
    expect(out).toContain('COMPANY.taxNo')
  })

  it('zorunlu OLMAYAN dize alanı (brandName) boşsa da yakalanır — COMPANY\'deki her dize sayfaya basılıyor', () => {
    const { code, out } = kopyada(alanDegeri(DOLU, 'brandName', ''))
    expect(code).toBe(1)
    expect(out).toContain('COMPANY.brandName')
  })

  it.each(['mersis', 'taxNo', 'kvkkEmail'])('KRİTİK: COMPANY.%s SİLİNİRSE (ad değişikliği) ALLOW_LEGAL_PLACEHOLDERS=1 ile bile DURUR', (alan) => {
    const { code, out } = kopyada(alanSil(DOLU, alan), { ALLOW_LEGAL_PLACEHOLDERS: '1' })
    expect(code).toBe(1)
    expect(out).toContain('BUILD DURDURULDU')
    expect(out).toContain(`COMPANY.${alan}`)
  })

  it('KRİTİK: COMPANY bloğu bulunamazsa (ad değişikliği) ALLOW=1 ile bile DURUR — sessiz "tam" YOK', () => {
    const { code, out } = kopyada(DOLU.replace('export const COMPANY', 'export const SIRKET'), { ALLOW_LEGAL_PLACEHOLDERS: '1' })
    expect(out).not.toContain('Yasal yapılandırma tam')
    expect(code).toBe(1)
  })

  it('placeholder hâlâ yakalanır; ALLOW=1 ile bilinçli geçilir ama UYARI basar', () => {
    const src = alanDegeri(DOLU, 'mersis', '[MERSİS NO]')
    const red = kopyada(src)
    expect(red.code).toBe(1)
    expect(red.out).toContain('COMPANY.mersis = [MERSİS NO]')
    const izin = kopyada(src, { ALLOW_LEGAL_PLACEHOLDERS: '1' })
    expect(izin.code).toBe(0)
    expect(izin.out).toContain('UYARI')
  })

  it('BOŞ alan ALLOW=1 ile bilinçli geçilir ama UYARI basar ve alanı adıyla söyler', () => {
    const { code, out } = kopyada(alanDegeri(DOLU, 'taxNo', ''), { ALLOW_LEGAL_PLACEHOLDERS: '1' })
    expect(code).toBe(0)
    expect(out).toContain('UYARI')
    expect(out).toContain('COMPANY.taxNo')
  })
})
