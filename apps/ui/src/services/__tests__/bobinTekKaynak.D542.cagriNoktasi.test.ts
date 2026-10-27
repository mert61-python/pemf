// Author: mertaygn, cglrgrkn
/**
 * D5.42 · İG-6.66 · A-65 — bobin sayısı / görünürlüğü TEK KAYNAK kapısı: tüketiciler TÜRETİLİR, her ÇAĞRI NOKTASI ölçülür.
 * ===================================================================================================================
 * ÖLÇÜLEN KÖRLÜK (D5): `tests/test_bobin_sayisi_tek_kaynak.py` sabit iki dosyada dosya başına TEK `gorunurBobinler(` metnini
 * yeterli sayıyordu → ControlScreen'in iki `<CoilSelector gorunur={gorunurBobinler}>` çağrı noktası kimlik işleviyle
 * (`gorunur={(l) => l}`) değiştirilince ve SensorMonitorScreen'in süzgeci kimlik yapılınca kapılar YEŞİL kalıyordu; tek kaynak
 * dışındaki bobin sabitleri (LiveDataContext `STM_COIL_MAX_ID = 5`, SurusKipiSecici `STM_BOBIN = 7` + `id <= 5`, CoilCard
 * `id <= 7`, CoilSelector / SensorMonitor / AiProPanel `{ length: 7 }`) hiç aranmıyordu.
 *
 * Bu kapı kaynağı TypeScript AST ile okur (yorum / dize kapıyı kandıramaz):
 *  1) ÇİZİM ÇAĞRI NOKTALARI: JSX döndüren her `.map(...)`un alıcısı bir canlı bobin listesine (`*.coils`) dayanıyorsa, o liste
 *     `gorunurBobinler(...)` (ya da CoilSelector'a enjekte edilen `gorunur(...)`) çağrısından geçmiş olmalı — aynı dosyadaki
 *     `const` tanımları izlenir. Tüketici kümesi elle yazılmaz, bu kuraldan TÜRETİLİR (en az 4 dosya).
 *  2) `<CoilSelector>` HER çağrı noktası `gorunur={gorunurBobinler}` geçmeli.
 *  3) TEK KAYNAK (`services/bobinGorunurlugu.ts`) DIŞINDA bobin sayısı sabiti YOK: adı COIL/BOBIN içeren sayısal sabit,
 *     `id`/`coilId`/`i` ile 5–8 sıralama karşılaştırması, `Array.from({ length: 5|7|8 })`, `[1, 2, …, N≥5]` dizisi.
 * A-65 (sahip): sürüş kipi seçicisinde bipolar yetenek YALNIZ backend alanından (`bipolarYetenek`) — `id <= 5` yedeği kalkar.
 */
import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";

const KOK = path.resolve(__dirname, "..", "..");
const TEK_KAYNAK = "services/bobinGorunurlugu.ts";

function uretimDosyalari(): string[] {
  const sonuc: string[] = [];
  const gez = (dizin: string) => {
    for (const ad of fs.readdirSync(dizin)) {
      const tam = path.join(dizin, ad);
      if (fs.statSync(tam).isDirectory()) {
        if (ad !== "__tests__" && ad !== "node_modules") gez(tam);
      } else if (/\.(ts|tsx)$/.test(ad) && !/\.d\.ts$/.test(ad)) sonuc.push(tam);
    }
  };
  gez(KOK);
  return sonuc;
}

const rel = (tam: string) => path.relative(KOK, tam).split(path.sep).join("/");

type Ihlal = string;

/** Bir ifadeyi kök listesine indir: parantez, `!`, `as`, `??` sol, `.filter/.slice/.sort/.map` zincirleri soyulur. */
function kokIfade(e: ts.Expression): ts.Expression {
  let n: ts.Expression = e;
  for (let i = 0; i < 20; i++) {
    if (ts.isParenthesizedExpression(n) || ts.isNonNullExpression(n) || ts.isAsExpression(n)) n = n.expression;
    else if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken) n = n.left;
    else if (
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      ["filter", "slice", "sort", "map", "concat"].includes(n.expression.name.text)
    )
      n = n.expression.expression;
    else break;
  }
  return n;
}

/** Aynı dosyadaki `const ad = <ilk>` tanımı. */
function tanim(sf: ts.SourceFile, ad: string): ts.Expression | undefined {
  let bulunan: ts.Expression | undefined;
  const ziyaret = (n: ts.Node) => {
    if (!bulunan && ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === ad && n.initializer)
      bulunan = n.initializer;
    ts.forEachChild(n, ziyaret);
  };
  ziyaret(sf);
  return bulunan;
}

type Kok = "tek_kaynak" | "ham_bobin" | "ilgisiz";

/** Alıcı bir canlı bobin listesine mi dayanıyor, tek kaynaktan mı geçmiş? */
function kokSinifi(sf: ts.SourceFile, e: ts.Expression, derinlik = 0): Kok {
  if (derinlik > 6) return "ilgisiz";
  const n = kokIfade(e);
  if (ts.isCallExpression(n)) {
    const ad = n.expression.getText(sf);
    if (ad === "gorunurBobinler" || ad === "gorunur") return "tek_kaynak";
    // Başka bir işlevden (ör. kimlik `((l) => l)(coils)`) geçen ham liste HÂLÂ ham listedir.
    for (const a of n.arguments) if (kokSinifi(sf, a, derinlik + 1) === "ham_bobin") return "ham_bobin";
    return "ilgisiz";
  }
  if (ts.isConditionalExpression(n)) {
    // `coils.length > 0 ? gorunur(coils) : Array.from({ length: STM_BOBIN_SAYISI }, …)` — boş liste yedeği tek kaynağın sayısıyla
    const a = kokSinifi(sf, n.whenTrue, derinlik + 1);
    const b = kokSinifi(sf, n.whenFalse, derinlik + 1);
    if (a === "ham_bobin" || b === "ham_bobin") return "ham_bobin";
    if (a === "tek_kaynak" || b === "tek_kaynak") return "tek_kaynak";
    return "ilgisiz";
  }
  if (ts.isPropertyAccessExpression(n) && n.name.text === "coils") return "ham_bobin";
  if (ts.isIdentifier(n)) {
    const t = tanim(sf, n.text);
    if (t) return kokSinifi(sf, t, derinlik + 1);
    return n.text === "coils" ? "ham_bobin" : "ilgisiz"; // bileşen özelliği `coils` (ör. CoilSelector) ham listedir
  }
  return "ilgisiz";
}

function jsxDondururMu(cb: ts.Node): boolean {
  let var_ = false;
  const z = (n: ts.Node) => {
    if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n) || ts.isJsxFragment(n)) var_ = true;
    if (!var_) ts.forEachChild(n, z);
  };
  z(cb);
  return var_;
}

const SAYI_ADI = /^(id|coilId|bobinId)$/;
function sayisalDeger(n: ts.Node): number | null {
  return ts.isNumericLiteral(n) ? Number(n.text) : null;
}

export function bobinKapisiTara(dosyalar: { ad: string; kaynak: string }[]) {
  const cizenler: Record<string, string[]> = {};
  const ihlaller: Ihlal[] = [];
  const selektorler: string[] = [];
  for (const { ad, kaynak } of dosyalar) {
    const sf = ts.createSourceFile(ad, kaynak, ts.ScriptTarget.Latest, true, ad.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    const satir = (n: ts.Node) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
    const tekKaynak = ad === TEK_KAYNAK;
    const ziyaret = (n: ts.Node) => {
      // 1) çizim çağrı noktası
      if (
        ts.isCallExpression(n) &&
        ts.isPropertyAccessExpression(n.expression) &&
        n.expression.name.text === "map" &&
        n.arguments[0] &&
        jsxDondururMu(n.arguments[0])
      ) {
        const sinif = kokSinifi(sf, n.expression.expression);
        if (sinif !== "ilgisiz") (cizenler[ad] ??= []).push(`${satir(n)}:${sinif}`);
        if (sinif === "ham_bobin") ihlaller.push(`${ad}:${satir(n)} bobin listesi gorunurBobinler'den GEÇMEDEN çiziliyor`);
      }
      // 2) CoilSelector çağrı noktası
      if ((ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) && n.tagName.getText(sf) === "CoilSelector") {
        const g = n.attributes.properties.find((p) => ts.isJsxAttribute(p) && p.name.getText(sf) === "gorunur") as
          | ts.JsxAttribute
          | undefined;
        const deger = g?.initializer && ts.isJsxExpression(g.initializer) ? g.initializer.expression?.getText(sf) : undefined;
        selektorler.push(`${ad}:${satir(n)}`);
        if (deger !== "gorunurBobinler") ihlaller.push(`${ad}:${satir(n)} <CoilSelector gorunur=${deger ?? "YOK"}> tek kaynak değil`);
      }
      // 3) tek kaynak dışı bobin sabitleri
      if (!tekKaynak) {
        if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && /COIL|BOBIN/i.test(n.name.text) && n.initializer) {
          const v = sayisalDeger(n.initializer);
          if (v !== null && Number.isInteger(v) && v >= 5 && v <= 8) ihlaller.push(`${ad}:${satir(n)} sabit ${n.name.text} = ${v}`);
        }
        if (
          ts.isBinaryExpression(n) &&
          [
            ts.SyntaxKind.LessThanToken,
            ts.SyntaxKind.LessThanEqualsToken,
            ts.SyntaxKind.GreaterThanToken,
            ts.SyntaxKind.GreaterThanEqualsToken,
          ].includes(n.operatorToken.kind)
        ) {
          for (const [taraf, sayi] of [
            [n.left, n.right],
            [n.right, n.left],
          ] as const) {
            const v = sayisalDeger(sayi);
            const son = ts.isPropertyAccessExpression(taraf) ? taraf.name.text : ts.isIdentifier(taraf) ? taraf.text : "";
            if (v !== null && v >= 5 && v <= 8 && SAYI_ADI.test(son))
              ihlaller.push(`${ad}:${satir(n)} bobin sınırı sabiti: ${n.getText(sf)}`);
          }
        }
        // `Array.from({ length: N }, …)` YALNIZ bobin kimliği üretiyorsa (geri çağrı `id:` alanı ya da `i + 1` döndürür) — grafik ızgarası sayılmaz.
        if (ts.isCallExpression(n) && n.expression.getText(sf) === "Array.from" && n.arguments.length === 2) {
          const [nesne, cb] = n.arguments;
          const uzunluk = ts.isObjectLiteralExpression(nesne)
            ? nesne.properties.find((p) => ts.isPropertyAssignment(p) && p.name.getText(sf) === "length")
            : undefined;
          const v = uzunluk && ts.isPropertyAssignment(uzunluk) ? sayisalDeger(uzunluk.initializer) : null;
          if (v !== null && [5, 7, 8].includes(v) && /\bid\s*:|\+\s*1\b/.test(cb.getText(sf)))
            ihlaller.push(`${ad}:${satir(n)} bobin sayısı sabiti Array.from({ length: ${v} })`);
        }
        if (ts.isArrayLiteralExpression(n) && n.elements.length >= 5) {
          const d = n.elements.map((e) => sayisalDeger(e));
          if (d.every((x, i) => x === i + 1)) ihlaller.push(`${ad}:${satir(n)} bobin kimliği dizisi [1..${d.length}]`);
        }
      }
      ts.forEachChild(n, ziyaret);
    };
    ziyaret(sf);
  }
  return { cizenler, ihlaller, selektorler };
}

const URETIM = uretimDosyalari()
  .map((tam) => ({ ad: rel(tam), kaynak: fs.readFileSync(tam, "utf8") }))
  .filter((d) => /coil|bobin/i.test(d.kaynak));

describe("D5.42 — bobin tek kaynak: türetilmiş tüketiciler, çağrı noktaları, sabit yasağı", () => {
  const sonuc = bobinKapisiTara(URETIM);

  it("KRİTİK: tek kaynak dışında bobin sayısı sabiti ve tek kaynaktan geçmeyen çizim / CoilSelector çağrı noktası YOK", () => {
    expect(sonuc.ihlaller).toEqual([]);
  });

  it("vakum değil: türetilen çizen dosyalar ve CoilSelector çağrı noktaları gerçekten bulundu", () => {
    const cizen = Object.keys(sonuc.cizenler).sort();
    for (const beklenen of ["screens/DashboardScreen.tsx", "screens/ControlScreen.tsx", "screens/SensorMonitorScreen.tsx", "screens/KpiDashboardScreen.tsx"])
      expect(cizen).toContain(beklenen);
    expect(sonuc.selektorler.filter((s) => s.startsWith("screens/ControlScreen.tsx")).length).toBeGreaterThanOrEqual(2);
  });

  it("KRİTİK A-65: sürüş kipi seçicisinin bipolar yeteneği YALNIZ backend alanından (`bipolarYetenek`)", () => {
    const k = fs.readFileSync(path.join(KOK, "components/domain/SurusKipiSecici.tsx"), "utf8");
    const sf = ts.createSourceFile("s.tsx", k, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const govdeler: string[] = [];
    const z = (n: ts.Node) => {
      if (ts.isVariableDeclaration(n) && n.name.getText(sf) === "bipolarYetenek" && n.initializer) govdeler.push(n.initializer.getText(sf));
      ts.forEachChild(n, z);
    };
    z(sf);
    expect(govdeler).toHaveLength(1);
    expect(govdeler[0]).toMatch(/bipolarYetenek\s*===\s*true/);
    expect(govdeler[0]).not.toMatch(/\.id\b/);
    // başlangıç isteği de aynı kural: `?? i < 5` gibi sıra / kimlik yedeği YOK (5 ile hiçbir karşılaştırma kalmaz)
    const bes: string[] = [];
    const z2 = (n: ts.Node) => {
      if (ts.isBinaryExpression(n) && [n.left, n.right].some((x) => ts.isNumericLiteral(x) && x.text === "5")) bes.push(n.getText(sf));
      ts.forEachChild(n, z2);
    };
    z2(sf);
    expect(bes).toEqual([]);
  });

  it.each([
    ["ham liste çizimi", "const X = () => snap.coils.map((c) => <A key={c.id} />);", 1],
    ["const üzerinden ham liste", "const coils = snapshot.coils ?? [];\nconst X = () => coils.map((c) => <A key={c.id} />);", 1],
    ["tek kaynak", "const coils = gorunurBobinler(snapshot.coils ?? []);\nconst X = () => coils.map((c) => <A key={c.id} />);", 0],
    ["kimlik selektör", "const X = () => <CoilSelector coils={coils} gorunur={(l) => l} />;", 1],
    ["tek kaynak selektör", "const X = () => <CoilSelector coils={coils} gorunur={gorunurBobinler} />;", 0],
    ["kimlik işlevinden geçen ham liste", "const coils = snapshot.coils ?? [];\nconst ids = ((l: C[]) => l)(coils).map((c) => c.id);\nconst X = () => ids.map((id) => <A key={id} />);", 1],
    ["sabit adı", "const STM_COIL_MAX_ID = 5;", 1],
    ["sınır", "const f = (c: { id: number }) => c.id <= 7;", 1],
    ["uzunluk", "const a = Array.from({ length: 7 }, (_, i) => i + 1);", 1],
    ["uzunluk nesne", "const a = Array.from({ length: 8 }, (_, index) => ({ id: index + 1 }));", 1],
    ["ızgara uzunluğu", "const a = Array.from({ length: 5 }, (_, i) => <G key={i} y={i * 4} />);", 0],
    ["direnç sabiti", "const BOBIN_DIRENCI_OHM = 8.9;", 0],
    ["dizi", "const s = new Set([1, 2, 3, 4, 5, 6, 7, 8]);", 1],
    ["yorumdaki sabit", "// const STM_COIL_MAX_ID = 5; c.id <= 7\nconst ok = 1;", 0],
    ["ilgisiz map", "const X = () => [1, 2].map((n) => <A key={n} />);", 0],
  ])("tarayıcı karşıt kanıtı: %s", (_ad, kaynak, beklenen) => {
    expect(bobinKapisiTara([{ ad: "screens/Ornek.tsx", kaynak }]).ihlaller).toHaveLength(beklenen);
  });
});
