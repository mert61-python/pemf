// Author: A1 (2-C inceleme)
/**
 * C2-1.7 — KÖR KAPI: D2.E09 / Y87 yapısal kapısı yalnız AiHubScreen.tsx'teki `logAiResult(` çağrılarını sayar.
 * Ölçülen (A1 mutantları k3m1/k3m2, E09 kapısı 8/8 YEŞİL kaldı):
 *   k3m1 analiz sonunda `Object.assign(hasta, hastaAnligi())` — görüntü ilk await'ten önce alınmış ama SONRA yerinde
 *        tamamlanma anındaki hastayla eziliyor (`const` nesne değişebilir) → yapısal kapı geçer;
 *   k3m2 aynı analizde ikinci bir DOĞRUDAN `apiPost("/ai/log", …hastaAnligi()…)` yazıcısı → kapı görmez (yalnız `logAiResult`).
 * Bu kapı: (1) ürün kaynağının TAMAMINDA (`src/**`, testler hariç) "/ai/log" POST hedefi yalnız `logAiResult` içinde geçer;
 * (2) `hastaAnligi()` ile alınan bağ hiçbir işlevde yeniden atanmaz / yerinde değiştirilmez. KARŞIT araç kanıtı örneklerle.
 */
import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";

const SRC = path.join(__dirname, "..", "..");

function kaynaklar(dizin: string): string[] {
  const out: string[] = [];
  for (const ad of fs.readdirSync(dizin)) {
    const tam = path.join(dizin, ad);
    const st = fs.statSync(tam);
    if (st.isDirectory()) {
      if (ad === "__tests__" || ad === "node_modules") continue;
      out.push(...kaynaklar(tam));
    } else if (/\.(ts|tsx)$/.test(ad) && !/\.test\.(ts|tsx)$/.test(ad) && !/\.d\.ts$/.test(ad)) {
      out.push(tam);
    }
  }
  return out;
}

function kapsayanIslevAdi(d: ts.Node): string {
  let p: ts.Node | undefined = d.parent;
  while (p) {
    if (ts.isFunctionDeclaration(p) && p.name) return p.name.text;
    if ((ts.isArrowFunction(p) || ts.isFunctionExpression(p)) && ts.isVariableDeclaration(p.parent) && ts.isIdentifier(p.parent.name)) {
      return p.parent.name.text;
    }
    p = p.parent;
  }
  return "";
}

export function aiLogYazicilari(ad: string, metin: string): string[] {
  const sf = ts.createSourceFile(ad, metin, ts.ScriptTarget.Latest, true, ad.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const bulunan: string[] = [];
  const gez = (d: ts.Node) => {
    if ((ts.isStringLiteral(d) || ts.isNoSubstitutionTemplateLiteral(d)) && d.text === "/ai/log") {
      const islev = kapsayanIslevAdi(d);
      if (islev !== "logAiResult") bulunan.push(`${ad}:${sf.getLineAndCharacterOfPosition(d.getStart()).line + 1} (${islev || "modül"})`);
    }
    ts.forEachChild(d, gez);
  };
  gez(sf);
  return bulunan;
}

export function goruntuDegisimleri(ad: string, metin: string): string[] {
  const sf = ts.createSourceFile(ad, metin, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const baglar = new Set<string>();
  const topla = (d: ts.Node) => {
    if (ts.isVariableDeclaration(d) && ts.isIdentifier(d.name) && d.initializer && ts.isCallExpression(d.initializer)
        && ts.isIdentifier(d.initializer.expression) && d.initializer.expression.text === "hastaAnligi") baglar.add(d.name.text);
    ts.forEachChild(d, topla);
  };
  topla(sf);
  const ihlal: string[] = [];
  const satir = (d: ts.Node) => sf.getLineAndCharacterOfPosition(d.getStart()).line + 1;
  const kok = (e: ts.Expression): ts.Expression => {
    let x = e;
    while (ts.isPropertyAccessExpression(x) || ts.isElementAccessExpression(x) || ts.isParenthesizedExpression(x)) x = x.expression;
    return x;
  };
  const gez = (d: ts.Node) => {
    if (ts.isBinaryExpression(d) && d.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && d.operatorToken.kind <= ts.SyntaxKind.LastAssignment) {
      const k = kok(d.left);
      if (ts.isIdentifier(k) && baglar.has(k.text)) ihlal.push(`${satir(d)}: '${k.text}' değiştiriliyor`);
    }
    if (ts.isCallExpression(d) && ts.isPropertyAccessExpression(d.expression) && ts.isIdentifier(d.expression.expression)
        && d.expression.expression.text === "Object" && d.expression.name.text === "assign" && d.arguments[0]) {
      const k = kok(d.arguments[0]);
      if (ts.isIdentifier(k) && baglar.has(k.text)) ihlal.push(`${satir(d)}: Object.assign('${k.text}', …)`);
    }
    ts.forEachChild(d, gez);
  };
  gez(sf);
  return ihlal;
}

it("KRİTİK C2-1.7: ürün kaynağının TAMAMINDA '/ai/log' yazımı yalnız logAiResult içinde (Y87 görüntüsü tek yerden)", () => {
  const dosyalar = kaynaklar(SRC);
  expect(dosyalar.length).toBeGreaterThan(50); // araç kanıtı: kaynak ağacı gerçekten tarandı
  const ihlal = dosyalar.flatMap((f) => aiLogYazicilari(path.relative(SRC, f), fs.readFileSync(f, "utf8")));
  expect(ihlal).toEqual([]);
});

it("KRİTİK C2-1.7: hastaAnligi() görüntüsü hiçbir analizde SONRADAN değiştirilmez", () => {
  const f = path.join(SRC, "screens", "AiHubScreen.tsx");
  expect(goruntuDegisimleri("AiHubScreen.tsx", fs.readFileSync(f, "utf8"))).toEqual([]);
});

it("KARŞIT (araç kanıtı): doğrudan yazıcı ve yerinde değişim BULUNUR; logAiResult içi ve GET sorgusu sayılmaz", () => {
  const ornek = [
    "async function logAiResult(h: any) { await apiPost('/ai/log', {}); }",
    "const a = async () => { const hasta = hastaAnligi(); await f(); Object.assign(hasta, hastaAnligi()); };",
    "const b = async () => { const hasta = hastaAnligi(); await f(); hasta.name = 'x'; apiPost(\"/ai/log\", {}); };",
    "const c = async () => { apiGet('/ai/log?limit=200'); };",
  ].join("\n");
  expect(aiLogYazicilari("x.tsx", ornek)).toEqual(["x.tsx:3 (b)"]);
  expect(goruntuDegisimleri("x.tsx", ornek)).toEqual(["2: Object.assign('hasta', …)", "3: 'hasta' değiştiriliyor"]);
});
