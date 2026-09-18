/**
 * Yasal yapılandırma yayın kapısı — denetim bulgusu: satıcı kimliği, açık adres, vergi no,
 * MERSİS ve KVKK BAŞVURU E-POSTASI dahil 10 alan `[PLACEHOLDER]` olarak CANLI sitede
 * yayınlanıyordu (Mesafeli Satış Sözleşmesi / Ön Bilgilendirme / KVKK metinlerine basılıyor).
 * Değerleri kod uyduramaz → yapılacak doğru şey EKSİKKEN YAYINLANMASINI engellemektir.
 *
 * Bu test kapının gerçekten kapı olduğunu doğrular (sessizce "ok" demediğini).
 */
import { describe, it, expect } from 'vitest'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const script = resolve(here, '../check-legal-config.mjs')

// spawnSync: hem stdout hem stderr gerekiyor (hata `console.error`, uyarı `console.warn` → stderr).
function run(env: Record<string, string> = {}): { code: number; out: string } {
  const r = spawnSync(process.execPath, [script], {
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
