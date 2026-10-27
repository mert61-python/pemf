/**
 * Yayın kapısı — yasal/kimlik alanlarında PLACEHOLDER kalmışsa, zorunlu alan BOŞSA ya da HİÇ YOKSA build'i DURDUR.
 *
 * `src/config.ts` içindeki COMPANY bloğu canlı yasal sayfalara (Mesafeli Satış Sözleşmesi,
 * Ön Bilgilendirme Formu, KVKK Aydınlatma Metni) doğrudan basılıyor. Denetimde bu alanların
 * tamamı — açık adres, telefon, vergi dairesi/no, MERSİS, ticaret sicil ve KVKK BAŞVURU
 * E-POSTASI — `[KÖŞELİ PARANTEZ]` placeholder'ı olarak CANLI sitede yayınlanır durumdaydı.
 * Bu, ticari bir sitede satıcı kimliği yükümlülüğünü ve KVKK başvuru kanalı zorunluluğunu
 * karşılamaz; üstelik kimse fark etmeden yayında kalabilir.
 *
 * ⚠️ D5.09 (B-7.19): kapı yalnız `'[…]'` kalıbını arıyordu → `mersis: ''`, `taxNo: '   '`, alanın SİLİNMESİ ya da COMPANY
 * bloğunun adının değişmesi "✓ tam" diyordu (yasal sayfaya boş satıcı kimliği basılırdı). Artık:
 *   - COMPANY'deki HER dize alanı: placeholder ya da boş/yalnız boşluk → bulgu,
 *   - ZORUNLU_ALANLAR'ın her biri dize değişmezi olarak VAR olmalı (yoksa → yapısal bulgu),
 *   - COMPANY bloğu bulunamazsa → yapısal bulgu.
 * Betik içerik YAZMAZ ve değer UYDURMAZ; yalnız denetler (değerleri sahibi girer).
 *
 * Değerler gizli değil ama sahibi tarafından girilmeli → kodda uyduramayız; yapılacak doğru şey
 * eksikken YAYINLANMASINI engellemektir. Bilinçli olarak yayınlamak gerekirse (placeholder / boş değer için):
 *   ALLOW_LEGAL_PLACEHOLDERS=1 npm run build
 * Yapısal bulgular (alan ya da blok YOK) bu bayrakla da GEÇMEZ — o bir içerik eksiği değil, kod hatasıdır.
 *
 * Kullanım: `node scripts/check-legal-config.mjs [yapılandırma.ts]` — argüman verilmezse `src/config.ts`. Argüman kapının
 * kendi testi içindir (gerçek yapılandırmanın türetilmiş geçici kopyası; gerçek dosyaya dokunulmaz).
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

/** Yasal sayfalara basılan ve dize değişmezi olarak BULUNMASI zorunlu satıcı kimlik alanları (yalnız ALAN ADLARI). */
const ZORUNLU_ALANLAR = [
  'legalName',
  'address',
  'city',
  'country',
  'phone',
  'email',
  'kvkkEmail',
  'taxOffice',
  'taxNo',
  'mersis',
  'tradeRegistry',
]

const here = dirname(fileURLToPath(import.meta.url))
const configPath = process.argv[2] ? resolve(process.argv[2]) : resolve(here, '../src/config.ts')
const src = readFileSync(configPath, 'utf8')

/** @type {{ field: string, value: string, yapisal: boolean }[]} */
const bulgular = []

const bas = src.indexOf('export const COMPANY')
if (bas === -1) {
  bulgular.push({ field: '(blok)', value: "`export const COMPANY` bulunamadı — yasal alanlar denetlenemedi", yapisal: true })
} else {
  // COMPANY bloğunu ayıkla; dize değişmezi alanları ('…' / "…" / `…`) oku.
  const block = src.slice(bas)
  const end = block.indexOf('} as const')
  const companyBlock = end === -1 ? block : block.slice(0, end)
  /** @type {Map<string, string>} */
  const alanlar = new Map()
  const kalip = /^[ \t]*(\w+)[ \t]*:[ \t]*(?:'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`([^`]*)`)/gm
  for (const m of companyBlock.matchAll(kalip)) alanlar.set(m[1], m[2] ?? m[3] ?? m[4] ?? '')

  for (const [field, value] of alanlar) {
    if (/^\[[\s\S]*\]$/.test(value)) bulgular.push({ field, value, yapisal: false })
    else if (value.trim() === '') bulgular.push({ field, value: `'${value}' (BOŞ)`, yapisal: false })
  }
  for (const field of ZORUNLU_ALANLAR) {
    if (!alanlar.has(field)) {
      bulgular.push({ field, value: 'alan YOK (dize değeri olarak tanımlı değil)', yapisal: true })
    }
  }
}

if (bulgular.length === 0) {
  console.log(`✓ Yasal yapılandırma tam — placeholder / boş alan yok (${ZORUNLU_ALANLAR.length} zorunlu alan dolu).`)
  process.exit(0)
}

const allow = process.env.ALLOW_LEGAL_PLACEHOLDERS === '1'
const yapisal = bulgular.some((b) => b.yapisal)
const lines = bulgular.map((p) => `    • COMPANY.${p.field} = ${p.value}`).join('\n')
const msg =
  `\nYasal/satıcı kimlik alanlarında ${bulgular.length} eksik (placeholder / boş / yok):\n${lines}\n\n` +
  `  Bu alanlar canlı sitedeki Mesafeli Satış Sözleşmesi, Ön Bilgilendirme Formu ve KVKK\n` +
  `  Aydınlatma Metni'ne doğrudan basılıyor. src/config.ts içindeki COMPANY bloğunu doldurun.\n` +
  (yapisal
    ? `  Alan ya da COMPANY bloğu YOK — bu bir kod hatasıdır; ALLOW_LEGAL_PLACEHOLDERS ile geçilemez.\n`
    : `  Bilerek yayınlamak için: ALLOW_LEGAL_PLACEHOLDERS=1 npm run build\n`)

if (allow && !yapisal) {
  console.warn(`⚠️  UYARI (bilinçli atlandı):${msg}`)
  process.exit(0)
}
console.error(`✖ BUILD DURDURULDU:${msg}`)
process.exit(1)
