// I18N — TS / TSX BASİT DURUM DÖNÜŞTÜRÜCÜSÜ (`scripts/i18n/uygula.py` çağırır; tek başına da çalışır).
//
// Desteklenen (gerisi REDDEDİLİR → elle, KURALLAR.md örnekleriyle):
//   · jsx-metin (ifadeyle karışık DEĞİL)       → {t("anahtar")}   (satır sonlu baş/son boşluk korunur, aynı satırdaki boşluk katalogda)
//   · görünür öznitelik  baslik="X"            → baslik={t("anahtar")}
//   · bileşen İÇİNDE dizgi değişmezi            → t("anahtar")     (ileti / jsx-ifade / nesne / dönüş / dizi / çağrı / atama)
//   · bileşen İÇİNDE şablon `a ${x} b`          → t("anahtar", { x })  (iç içe şablon / koşullu parça HARİÇ)
// Reddedilen: modül düzeyi sabit, bileşen / hook olmayan işlev (yardımcı), `+` birleştirme, iç içe şablon, ifadeyle karışık JSX metni,
// gövdesi blok olmayan ok işlevi bileşen, kapsamda çeviri işlevini GÖLGELEYEN başka bir `t` (`.map((t) => …)`, yerel `const t`).
// `t` kapsamda değilse bileşen gövdesinin başına `const { t } = useTranslation();`, dosyaya `useTranslation` içe aktarması eklenir.
// Tırnak ve noktalı virgül dosyanın kendi biçimini izler (arayüz "…"; — site '…').
//
// Girdi (stdin JSON): { dosya, metin, islemler: [{ satir, sutun, metin, anahtar }] }   Çıktı: { metin, uygulanan: [...], reddedilen: [...] }
"use strict";

const { cikarKaynak, tsYukle } = require("./cikar_ts.cjs");

const IZINLI_TUR = new Set(["jsx-metin", "oznitelik", "ileti", "jsx-ifade", "nesne", "donus", "dizi", "cagri", "atama", "sabit", "sablon", "dizgi", "hata"]);
const ANAHTAR = /^[a-z][A-Za-z0-9]*(\.[A-Za-z0-9_]+)+$/;

function uygulaKaynak(metin, dosya, islemler, secenek) {
  const ts = (secenek && secenek.ts) || tsYukle();
  const tur = /\.tsx$/i.test(dosya) ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(dosya, metin, ts.ScriptTarget.Latest, true, tur);
  const { adaylar } = cikarKaynak(metin, dosya, { ts });
  const iceAktarmalar = sf.statements.filter((s) => ts.isImportDeclaration(s));
  const tek = (metin.match(/from '/g) || []).length;
  const cift = (metin.match(/from "/g) || []).length;
  const q = tek > cift ? "'" : '"';
  const sonIceAktarma = iceAktarmalar.length ? iceAktarmalar[iceAktarmalar.length - 1] : null;
  const nv = sonIceAktarma && !sonIceAktarma.getText(sf).trim().endsWith(";") ? "" : ";";
  const tCagri = (anahtar, ek) => `t(${q}${anahtar}${q}${ek || ""})`;
  const duzenler = []; // {bas, son, yeni}
  const uygulanan = [];
  const reddedilen = [];
  const hookGerekenler = new Map(); // gövde başlangıcı → girinti

  const dugumBul = (bas, son) => {
    let bulunan = null;
    const gez = (n) => {
      if (n.getStart(sf) === bas && n.getEnd() === son) bulunan = n;
      if (!bulunan) ts.forEachChild(n, gez);
    };
    gez(sf);
    return bulunan;
  };

  // Geri çağırma (onPress = () => …) bileşen İÇİNDEDİR: en yakın BÜYÜK harfli / use* işlevi aranır (hook oraya eklenir).
  const bilesenGovdesi = (n) => {
    let x = n.parent;
    while (x) {
      if (ts.isFunctionDeclaration(x) || ts.isFunctionExpression(x) || ts.isArrowFunction(x)) {
        let ad = "";
        if (x.name && ts.isIdentifier(x.name)) ad = x.name.text;
        else if (x.parent && ts.isVariableDeclaration(x.parent) && ts.isIdentifier(x.parent.name)) ad = x.parent.name.text;
        if (/^[A-Z]/.test(ad) || /^use[A-Z]/.test(ad)) return x.body && ts.isBlock(x.body) ? x.body : "blok-degil";
      }
      x = x.parent;
    }
    return null;
  };

  for (const is of islemler) {
    const a = adaylar.find((x) => x.satir === is.satir && x.sutun === is.sutun && x.metin === is.metin);
    const ret = (neden) => reddedilen.push({ ...is, neden });
    if (!a) {
      ret("aday bulunamadı (satır / sütun / metin kaynağın bugünkü hâliyle eşleşmiyor — cikar'ı yeniden koşun)");
      continue;
    }
    if (!ANAHTAR.test(is.anahtar || "")) {
      ret("anahtar biçimi geçersiz (ASCII camelCase, noktalı; ör. ayarlar.dil.baslik)");
      continue;
    }
    if (!IZINLI_TUR.has(a.tur)) {
      ret(`tür '${a.tur}' elle dönüştürülür`);
      continue;
    }
    if (a.modulDuzeyi) {
      ret("modül düzeyi sabit — anahtar saklanır, gösterimde çevrilir (elle; KURALLAR §Modül düzeyi sabit)");
      continue;
    }
    if (a.tGolge) {
      ret("kapsamda çeviri işlevini GÖLGELEYEN başka bir `t` var (geri çağırma parametresi / yerel değişken) — onu yeniden adlandırıp elle");
      continue;
    }
    const n = dugumBul(a.bas, a.son);
    if (!n) {
      ret("düğüm konumu bulunamadı");
      continue;
    }
    // Birleşik aday: yalnız şablon (`a ${x} b` → tek anahtar + yer tutucu) otomatik; `+` zinciri ve ifadeyle karışık JSX metni ELLE.
    if (a.birlesik && !ts.isTemplateExpression(n)) {
      ret(ts.isJsxText(n) ? "ifadeyle karışık JSX metni — elle tek anahtar + yer tutucu" : "`+` birleştirme — elle tek anahtar + yer tutucu");
      continue;
    }
    const govde = bilesenGovdesi(n);
    if (govde === null) {
      ret("bileşen / hook dışında (yardımcı işlev) — i18n.t gösterim anında, elle");
      continue;
    }
    if (govde === "blok-degil") {
      ret("bileşen gövdesi blok değil (=> (...)) — elle");
      continue;
    }
    let yeni = null;
    if (ts.isJsxText(n)) {
      const ham = n.text;
      const onBosluk = (ham.match(/^\s*/) || [""])[0];
      const sonBosluk = (ham.match(/\s*$/) || [""])[0];
      yeni = (onBosluk.includes("\n") ? onBosluk : "") + `{${tCagri(is.anahtar)}}` + (sonBosluk.includes("\n") ? sonBosluk : "");
    } else if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) {
      yeni = ts.isJsxAttribute(n.parent) ? `{${tCagri(is.anahtar)}}` : tCagri(is.anahtar);
    } else if (ts.isTemplateExpression(n)) {
      const parcalar = [];
      let ic = false;
      n.templateSpans.forEach((sp, i) => {
        if (ts.isTemplateExpression(sp.expression) || ts.isConditionalExpression(sp.expression)) ic = true;
        const ad = a.yertutucular[i];
        const ifade = sp.expression.getText(sf);
        parcalar.push(ad === ifade ? ad : `${ad}: ${ifade}`);
      });
      if (ic || a.yertutucular.length !== n.templateSpans.length) {
        ret("iç içe şablon / koşullu parça — elle (iki tam cümle anahtarı)");
        continue;
      }
      yeni = tCagri(is.anahtar, `, { ${parcalar.join(", ")} }`);
    } else {
      ret("desteklenmeyen düğüm");
      continue;
    }
    duzenler.push({ bas: a.bas, son: a.son, yeni });
    uygulanan.push({ ...is, tur: a.tur, ham: a.ham, yertutucular: a.yertutucular });
    if (!a.tVar) {
      const ilk = govde.statements[0];
      const girinti = ilk ? metin.slice(metin.lastIndexOf("\n", ilk.getStart(sf)) + 1, ilk.getStart(sf)) : "  ";
      hookGerekenler.set(govde.getStart(sf) + 1, /^\s*$/.test(girinti) ? girinti : "  ");
    }
  }
  for (const [konum, girinti] of hookGerekenler) duzenler.push({ bas: konum, son: konum, yeni: `\n${girinti}const { t } = useTranslation()${nv}` });
  if (hookGerekenler.size && !/import\s*\{[^}]*\buseTranslation\b[^}]*\}\s*from\s*["']react-i18next["']/.test(metin)) {
    const konum = sonIceAktarma ? sonIceAktarma.getEnd() : 0;
    const satir = `import { useTranslation } from ${q}react-i18next${q}${nv}`;
    duzenler.push({ bas: konum, son: konum, yeni: konum ? "\n" + satir : satir + "\n" });
  }
  duzenler.sort((x, y) => y.bas - x.bas || y.son - x.son);
  let cikti = metin;
  for (const d of duzenler) cikti = cikti.slice(0, d.bas) + d.yeni + cikti.slice(d.son);
  return { metin: cikti, uygulanan, reddedilen };
}

module.exports = { uygulaKaynak };

if (require.main === module) {
  let veri = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (p) => (veri += p));
  process.stdin.on("end", () => {
    const g = JSON.parse(veri);
    const ts = tsYukle();
    const r = uygulaKaynak(g.metin, g.dosya, g.islemler || [], { ts });
    process.stdout.write(JSON.stringify(r));
  });
}
