// Author: mertaygn, cglrgrkn
/**
 * D6.28 (B-7.20) — CSP `connect-src` YALNIZ tarayıcının GERÇEKTEN bağlandığı kökenleri açar; açtığı her köken bir ÇAĞRI HEDEFİNE dayanır.
 *
 * 🔴 ÖLÇÜLEN (HEAD ebf1c3fe): `vercel.json` `connect-src` `https://api.github.com` içeriyordu ve `README.md` bunu "zorunlu" diye anlatıyordu
 * (indirme sayacı GitHub Releases API'sinden okunuyordu). Sayaç 2026-08-13'te Supabase `usage_counts()` RPC'sine taşındı
 * (`lib/usageStats.ts`); `apps/web/src` ve `apps/web/api` içinde `api.github.com` geçen tek satır yok — CSP izni sahipsiz kalmıştı.
 *
 * ÖLÇÜT (metin değil ÇAĞRI): tarayıcı paketinin (`src/`, testler hariç) TypeScript AST'sinde `fetch(…)`, `new WebSocket(…)`,
 * `new EventSource(…)`, `new Request(…)`, `sendBeacon(…)` ve Supabase `createClient(…)` çağrılarının İLK argümanı; argüman bir tanımlayıcıysa
 * `const` tanımına, `||` / `??` / `+` / `?:` / şablon parçalarına kadar izlenir. YORUMDAKİ ya da hiçbir çağrıya gitmeyen (ölü) dizgedeki
 * adres ÇAĞRI SAYILMAZ (önce-kırmızı tarifinin alt-dize araması bu iki yoldan kandırılıyordu — orkestratör notu C2b).
 *   (1) connect-src'deki her köken ya bir çağrı hedefiyle eşleşir ya da ÜÇÜNCÜ TARAF tablosundadır (yalnız iyzico: ödeme formu
 *       `checkoutFormContent` kendi script'ini enjekte eder, o script tarayıcıdan iyzico API'sine bağlanır — kanıtı ayrıca ölçülür);
 *   (2) ters yön: her mutlak çağrı hedefi connect-src'de bir kaynakla eşleşir (izin kalkarsa istek tarayıcıda SESSİZCE kesilir);
 *   (3) README CSP gerekçesi kaldırılan izni "zorunlu" diye anlatmaz, sayacın gerçek kaynağını (usage_counts) anar.
 * `api/` (Vercel sunucu işlevleri) tarayıcıda koşmaz → CSP'nin konusu DEĞİL, taranmaz.
 */
import { describe, expect, it } from 'vitest'
import ts from 'typescript'

import VERCEL_SRC from '../../vercel.json?raw'
import README_SRC from '../../README.md?raw'

const TARAYICI_KAYNAKLARI = import.meta.glob(['../**/*.ts', '../**/*.tsx', '!../**/__tests__/**', '!../**/*.d.ts'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const CAGRI_ADLARI = new Set(['fetch', 'createClient', 'sendBeacon'])
const YENI_ADLARI = new Set(['WebSocket', 'EventSource', 'Request'])

/** Bilinmeyen (çözülemeyen) parça — birleştirmede yer tutar; böyle başlayan hedefin kökeni bilinmez. */
const BILINMEYEN = '\u0000'

/** Kaynaktaki ağ çağrılarının ilk argümanının OLASI TAM değerleri (AST; yorum düğüm değildir → hiç görülmez). */
export function cagriHedefleri(dosya: string, src: string): string[] {
  const sf = ts.createSourceFile(dosya, src, ts.ScriptTarget.Latest, true, dosya.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const tanimlar = new Map<string, ts.Expression>()
  const tanimTopla = (n: ts.Node): void => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer) tanimlar.set(n.name.text, n.initializer)
    ts.forEachChild(n, tanimTopla)
  }
  tanimTopla(sf)
  const birlestir = (sol: string[], sag: string[]): string[] =>
    (sol.length ? sol : [BILINMEYEN]).flatMap((a) => (sag.length ? sag : [BILINMEYEN]).map((b) => a + b)).slice(0, 64)
  const coz = (e: ts.Expression, derinlik: number): string[] => {
    if (derinlik > 10) return []
    if (ts.isStringLiteral(e) || ts.isNoSubstitutionTemplateLiteral(e)) return [e.text]
    if (ts.isTemplateExpression(e)) {
      let alt = [e.head.text]
      for (const s of e.templateSpans) alt = birlestir(birlestir(alt, coz(s.expression, derinlik + 1)), [s.literal.text])
      return alt
    }
    if (ts.isParenthesizedExpression(e) || ts.isAsExpression(e) || ts.isNonNullExpression(e) || ts.isSatisfiesExpression(e)) {
      return coz(e.expression, derinlik + 1)
    }
    if (ts.isBinaryExpression(e)) {
      const k = e.operatorToken.kind
      if (k === ts.SyntaxKind.BarBarToken || k === ts.SyntaxKind.QuestionQuestionToken) {
        return [...coz(e.left, derinlik + 1), ...coz(e.right, derinlik + 1)]
      }
      if (k === ts.SyntaxKind.PlusToken) return birlestir(coz(e.left, derinlik + 1), coz(e.right, derinlik + 1))
      return []
    }
    if (ts.isConditionalExpression(e)) return [...coz(e.whenTrue, derinlik + 1), ...coz(e.whenFalse, derinlik + 1)]
    if (ts.isIdentifier(e)) {
      const t = tanimlar.get(e.text)
      return t ? coz(t, derinlik + 1) : []
    }
    return []
  }
  const ad = (e: ts.Expression): string =>
    ts.isIdentifier(e) ? e.text : ts.isPropertyAccessExpression(e) ? e.name.text : ''
  const hedefler: string[] = []
  const gez = (n: ts.Node): void => {
    if (ts.isCallExpression(n) && CAGRI_ADLARI.has(ad(n.expression)) && n.arguments[0]) hedefler.push(...coz(n.arguments[0], 0))
    if (ts.isNewExpression(n) && YENI_ADLARI.has(ad(n.expression)) && n.arguments?.[0]) hedefler.push(...coz(n.arguments[0], 0))
    ts.forEachChild(n, gez)
  }
  gez(sf)
  return hedefler
}

/** Çağrı hedefinin kökeni (şema + host). Göreli yol ('/api/…') → `'self'`; başı bilinmeyen hedef → köken yok. */
export function kokenler(hedef: string): string[] {
  const m = /^((?:https?|wss?):\/\/[A-Za-z0-9.-]+)/.exec(hedef)
  if (m) return [m[1].toLowerCase()]
  return hedef.startsWith('/') && !hedef.startsWith('//') ? ["'self'"] : []
}

/** CSP kaynak ifadesi (`https://*.supabase.co`, `'self'`) bir kökeni kapsıyor mu. */
export function kaynakKapsar(kaynak: string, koken: string): boolean {
  if (kaynak === "'self'" || koken === "'self'") return kaynak === koken
  const km = /^(https?|wss?):\/\/(\*\.)?(.+)$/.exec(kaynak.toLowerCase())
  const om = /^(https?|wss?):\/\/(.+)$/.exec(koken)
  if (!km || !om || km[1] !== om[1]) return false
  return km[2] ? om[2].endsWith(`.${km[3]}`) : om[2] === km[3]
}

function csp(vercel: string): Record<string, string[]> {
  const j = JSON.parse(vercel) as { headers: { headers: { key: string; value: string }[] }[] }
  const deger = j.headers.flatMap((h) => h.headers).filter((h) => h.key === 'Content-Security-Policy')
  expect(deger, 'vercel.json içinde tek Content-Security-Policy başlığı olmalı').toHaveLength(1)
  const y: Record<string, string[]> = {}
  for (const parca of deger[0].value.split(';')) {
    const [ad, ...kaynaklar] = parca.trim().split(/\s+/)
    if (ad) y[ad] = kaynaklar
  }
  return y
}

/** Üçüncü taraf: kökene BİZİM kodumuz değil, gömdüğümüz iyzico formunun script'i bağlanır. Her satırın kanıtı ayrıca ölçülür. */
function iyzicoFormuGomulu(y: Record<string, string[]>, scriptKokeni: string): boolean {
  const odeme = Object.entries(TARAYICI_KAYNAKLARI).find(([yol]) => yol.endsWith('/pages/Odeme.tsx'))
  if (!odeme) return false
  const sf = ts.createSourceFile('Odeme.tsx', odeme[1], ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  let gomulu = false
  const gez = (n: ts.Node): void => {
    if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) && n.expression.name.text === 'createContextualFragment') gomulu = true
    ts.forEachChild(n, gez)
  }
  gez(sf)
  return gomulu && (y['script-src'] ?? []).includes(scriptKokeni)
}

const UCUNCU_TARAF: Record<string, (y: Record<string, string[]>) => boolean> = {
  'https://api.iyzipay.com': (y) => iyzicoFormuGomulu(y, 'https://static.iyzipay.com'),
  'https://sandbox-api.iyzipay.com': (y) => iyzicoFormuGomulu(y, 'https://sandbox-static.iyzipay.com'),
}

function tumHedefKokenleri(): Set<string> {
  const s = new Set<string>()
  for (const [yol, src] of Object.entries(TARAYICI_KAYNAKLARI)) for (const p of cagriHedefleri(yol, src)) for (const k of kokenler(p)) s.add(k)
  return s
}

describe('D6.28 · ölçücü KARŞIT kanıtı (AST: yorum ve ölü dizge çağrı DEĞİL)', () => {
  it('yalnız YORUMDA geçen adres çağrı hedefi sayılmaz', () => {
    const src = "// fetch('https://api.github.com/repos/x/y/releases')\n/* new WebSocket('wss://api.github.com') */\nexport const a = 1\n"
    expect(cagriHedefleri('a.ts', src).flatMap(kokenler)).toEqual([])
  })
  it('hiçbir çağrıya gitmeyen ÖLÜ dizge çağrı hedefi sayılmaz', () => {
    const src = "const GITHUB = 'https://api.github.com/repos/x'\nexport const b = GITHUB.length\nfetch('/api/tokens')\n"
    expect(cagriHedefleri('b.ts', src).flatMap(kokenler)).toEqual(["'self'"])
  })
  it('tanımlayıcı, `||` yedeği ve şablon üzerinden giden çağrı hedefi BULUNUR', () => {
    const src = [
      "const VARSAYILAN = 'https://abc.supabase.co'",
      'const url = (import.meta.env.X as string | undefined) || VARSAYILAN',
      'createClient(url, anon)',
      "const API = 'https://api.github.com'",
      'fetch(`${API}/repos/x`)',
    ].join('\n')
    expect(new Set(cagriHedefleri('c.ts', src).flatMap(kokenler))).toEqual(new Set(['https://abc.supabase.co', 'https://api.github.com']))
  })
  it('joker kaynak yalnız alt alan adını kapsar; şema farklıysa kapsamaz', () => {
    expect(kaynakKapsar('https://*.supabase.co', 'https://abc.supabase.co')).toBe(true)
    expect(kaynakKapsar('https://*.supabase.co', 'https://supabase.co.evil.example')).toBe(false)
    expect(kaynakKapsar('https://*.supabase.co', 'wss://abc.supabase.co')).toBe(false)
    expect(kaynakKapsar('https://api.github.com', 'https://api.github.com')).toBe(true)
  })
})

describe('D6.28 · vercel.json connect-src ↔ tarayıcı çağrıları', () => {
  const y = csp(VERCEL_SRC)
  const connect = y['connect-src'] ?? []
  const hedefler = tumHedefKokenleri()

  it('VAKUM: tarayıcı kaynağı taranıyor ve bilinen çağrılar bulunuyor', () => {
    expect(Object.keys(TARAYICI_KAYNAKLARI).length).toBeGreaterThan(20)
    expect([...hedefler]).toContain("'self'")
    expect([...hedefler].some((k) => k.endsWith('.supabase.co'))).toBe(true)
  })

  it("KRİTİK: connect-src'deki HER köken bir çağrı hedefine (ya da kanıtlı üçüncü tarafa) dayanır — kullanılmayan izin YOK", () => {
    const sahipsiz = connect.filter((kaynak) => {
      if ([...hedefler].some((k) => kaynakKapsar(kaynak, k))) return false
      const ucuncu = UCUNCU_TARAF[kaynak]
      return !(ucuncu && ucuncu(y))
    })
    expect(
      sahipsiz,
      `connect-src'de tarayıcı kodunun HİÇ bağlanmadığı köken(ler): ${sahipsiz.join(', ')} — izin kaldırılmalı (yorumdaki ya da ölü dizgedeki adres çağrı sayılmaz)`,
    ).toEqual([])
  })

  it("KRİTİK: her mutlak çağrı hedefi connect-src'de izinli (izin kalkarsa istek tarayıcıda sessizce kesilir)", () => {
    const izinsiz = [...hedefler].filter((k) => !connect.some((kaynak) => kaynakKapsar(kaynak, k)))
    expect(izinsiz, `connect-src bu çağrı hedeflerine izin vermiyor: ${izinsiz.join(', ')}`).toEqual([])
  })

  it('üçüncü taraf (iyzico) satırlarının kanıtı GERÇEK: ödeme formu gömülüyor ve script kökeni script-src’de', () => {
    for (const [kaynak, kanit] of Object.entries(UCUNCU_TARAF)) {
      if (connect.includes(kaynak)) expect(kanit(y), `${kaynak}: iyzico formu gömülmüyor ya da script-src kökeni yok`).toBe(true)
    }
  })
})

describe('D6.28 · README CSP gerekçesi kodla aynı', () => {
  it('README kaldırılan api.github.com iznini "zorunlu" diye anlatmaz; sayaç kaynağı usage_counts', () => {
    expect(README_SRC).not.toMatch(/api\.github\.com[^\n]{0,60}(?:zorunda|zorunlu|şart|gerekir|gerekli)/)
    expect(README_SRC).not.toMatch(/DownloadStats\.tsx[^\n]*GitHub/)
    expect(README_SRC).toMatch(/usage_counts\(\)/)
  })
})
