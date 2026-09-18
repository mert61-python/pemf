/**
 * Yayın kapısı — yasal/kimlik alanlarında PLACEHOLDER kalmışsa build'i DURDUR.
 *
 * `src/config.ts` içindeki COMPANY bloğu canlı yasal sayfalara (Mesafeli Satış Sözleşmesi,
 * Ön Bilgilendirme Formu, KVKK Aydınlatma Metni) doğrudan basılıyor. Denetimde bu alanların
 * tamamı — açık adres, telefon, vergi dairesi/no, MERSİS, ticaret sicil ve KVKK BAŞVURU
 * E-POSTASI — `[KÖŞELİ PARANTEZ]` placeholder'ı olarak CANLI sitede yayınlanır durumdaydı.
 * Bu, ticari bir sitede satıcı kimliği yükümlülüğünü ve KVKK başvuru kanalı zorunluluğunu
 * karşılamaz; üstelik kimse fark etmeden yayında kalabilir.
 *
 * Değerler gizli değil ama sahibi tarafından girilmeli → kodda uyduramayız; yapılacak doğru şey
 * eksikken YAYINLANMASINI engellemektir. Bilinçli olarak yayınlamak gerekirse:
 *   ALLOW_LEGAL_PLACEHOLDERS=1 npm run build
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const configPath = resolve(here, '../src/config.ts')
const src = readFileSync(configPath, 'utf8')

// COMPANY bloğunu ayıkla ve içindeki [PLACEHOLDER] kalıplarını bul.
const block = src.slice(src.indexOf('export const COMPANY'))
const end = block.indexOf('} as const')
const companyBlock = end === -1 ? block : block.slice(0, end)

const placeholders = [...companyBlock.matchAll(/^\s*(\w+):\s*'(\[[^']*\])'/gm)].map((m) => ({
  field: m[1],
  value: m[2],
}))

if (placeholders.length === 0) {
  console.log('✓ Yasal yapılandırma tam — placeholder yok.')
  process.exit(0)
}

const allow = process.env.ALLOW_LEGAL_PLACEHOLDERS === '1'
const lines = placeholders.map((p) => `    • COMPANY.${p.field} = ${p.value}`).join('\n')
const msg =
  `\nYasal/satıcı kimlik alanlarında ${placeholders.length} placeholder kaldı:\n${lines}\n\n` +
  `  Bu alanlar canlı sitedeki Mesafeli Satış Sözleşmesi, Ön Bilgilendirme Formu ve KVKK\n` +
  `  Aydınlatma Metni'ne doğrudan basılıyor. src/config.ts içindeki COMPANY bloğunu doldurun.\n` +
  `  Bilerek yayınlamak için: ALLOW_LEGAL_PLACEHOLDERS=1 npm run build\n`

if (allow) {
  console.warn(`⚠️  UYARI (bilinçli atlandı):${msg}`)
  process.exit(0)
}
console.error(`✖ BUILD DURDURULDU:${msg}`)
process.exit(1)
