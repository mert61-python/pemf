// I18N-0 — TS / TSX / JS aday metin çıkarımı (TypeScript derleyici API'si; YENİ BAĞIMLILIK YOK).
//
// NE YAPAR: kaynakta kullanıcıya GÖRÜNEBİLECEK dizgileri bulur ve her biri için konum + tür + bağlam + öneri anahtar döker.
// Kullanıcılar: `scripts/i18n/cikar.py` (CLI, bütün yüzeyler), `scripts/i18n/uygula_ts.cjs` (kod dönüşümü) ve K-2 kapısının
// jest / vitest tarafı (`apps/ui/src/i18n/__tests__/sabitMetinYasagi.test.ts`, `apps/web/src/i18n/__tests__/...`).
//
// İLKE (KURALLAR.md §Muaf): "kararsızsan ÇEVRİLİR say" — görünen bir metnin kaçması fazladan bir adaydan kötüdür. Bu yüzden
// dışlama YALNIZ kesin kod bağlamlarında yapılır (import, tür, nesne anahtarı, karşılaştırma, günlük, stil, testID …); geri
// kalan her doğal dil dizgisi adaydır ve gerekirse `i18n/kapsam.json` muaf listesine GEREKÇEYLE girer.
//
// Kullanım (CLI):  node scripts/i18n/cikar_ts.cjs [--olcum] <dosya>...   → stdout JSON {adaylar:[...], olcum:{...}}
// TypeScript yolu: I18N_TS_YOLU ortam değişkeni → yoksa depo kökünde apps/ui, apps/web, DEMA node_modules sırasıyla aranır.
"use strict";

const fs = require("fs");
const path = require("path");

const DEPO_KOKU = path.resolve(__dirname, "..", "..");

function tsYukle() {
  const adaylar = [];
  if (process.env.I18N_TS_YOLU) adaylar.push(process.env.I18N_TS_YOLU);
  for (const alt of ["apps/ui", "apps/web", "dema-terapi-simülatörü"]) {
    adaylar.push(path.join(DEPO_KOKU, alt, "node_modules", "typescript"));
  }
  for (const a of adaylar) {
    try {
      if (fs.existsSync(path.join(a, "package.json"))) return require(a);
    } catch (_e) {
      /* sıradaki aday */
    }
  }
  throw new Error(
    "typescript bulunamadı (I18N_TS_YOLU ya da apps/ui|apps/web node_modules/typescript gerekli): " + adaylar.join(" | "),
  );
}

// Kullanıcıya görünen JSX öznitelikleri. ⚠️ Liste ölçerek genişletilir (I18N-0 ölçümü: bkz. DUZELTME-I18N.md §Ön ölçüm).
const GORUNUR_OZNITELIK = new Set([
  "title", "label", "placeholder", "accessibilityLabel", "accessibilityHint", "aria-label", "aria-description", "alt",
  "message", "subtitle", "description", "hint", "tooltip", "text", "helperText", "errorText", "emptyText", "confirmText",
  "cancelText", "okText", "buttonText", "actionLabel", "baslik", "altBaslik", "aciklama", "etiket", "metin", "ipucu",
  "bosMetin", "onayMetni", "vazgecMetni", "dugmeMetni", "hata", "uyari", "bilgi", "not", "mesaj", "rozet", "kisaEtiket",
  "eylemEtiketi", "yukleniyorMetni", "value",
]);
// Kesin KOD öznitelikleri — dizgileri kullanıcıya görünmez.
const KOD_OZNITELIK = new Set([
  "testID", "nativeID", "key", "style", "className", "id", "href", "src", "uri", "source", "name", "icon", "color",
  "accessibilityRole", "role", "type", "variant", "tone", "size", "mode", "kind", "keyboardType", "autoCapitalize",
  "autoComplete", "textContentType", "returnKeyType", "resizeMode", "pointerEvents", "behavior", "animationType",
  "presentationStyle", "importantForAccessibility", "accessibilityLiveRegion", "dataSet", "target", "rel", "method",
  "action", "htmlFor", "lang", "dir", "inputMode", "enterKeyHint", "to", "path", "element", "loading", "decoding",
  "crossOrigin", "referrerPolicy", "sandbox", "allow", "fill", "stroke", "d", "viewBox", "xmlns", "fontFamily",
  "fontWeight", "ellipsizeMode", "textBreakStrategy", "dataDetectorType", "accessibilityState", "hitSlop",
]);
// Kullanıcıya ileti gösteren çağrılar (tür etiketi için; dışlama değil).
const ILETI_CAGRILARI = new Set([
  "Alert.alert", "Alert.prompt", "platformAlert", "platformConfirm", "emitToast", "showToast", "toast", "confirm",
  "alert", "window.alert", "window.confirm", "window.prompt",
]);
// Karşılaştırma / metin işleme yöntemleri — ilk argümanları KOD değeridir (ölçüm (i) için ayrıca sayılır).
const KARSILASTIRMA_YONTEMI = new Set([
  "includes", "startsWith", "endsWith", "indexOf", "lastIndexOf", "match", "matchAll", "test", "search", "split",
  "replace", "replaceAll", "localeCompare", "has", "get", "set", "delete", "getItem", "setItem", "removeItem",
  "getAttribute", "setAttribute", "querySelector", "querySelectorAll", "getElementById", "addEventListener",
  "removeEventListener", "emit", "on", "off", "once", "dispatchEvent", "postMessage", "invoke", "listen",
]);
const GUNLUK_NESNESI = /^(console|logger|log|_log|LOG|debugLog|gunluk|Sentry)$/;
const GUNLUK_YONTEMI = /^(log|info|warn|error|debug|trace|group|groupEnd|table|time|timeEnd|captureException|captureMessage)$/;

const TR_HARF = /[çğıöşüÇĞİÖŞÜâîûÂÎÛ]/;

/** Dizgi doğal dil mi (kullanıcıya görünebilir mi)? Kod / yol / renk / tanımlayıcı → false. Kararsız durumda true. */
function dogalMi(ham) {
  const s0 = String(ham).trim();
  if (s0.length < 2) return false;
  if (!/\p{L}/u.test(s0)) return false;
  // Başta / sonda süs (emoji, ok, madde imi, ✓) varsa metin GÖSTERİM içindir (kod değerleri süs taşımaz).
  const sus = /^[^\p{L}\p{N}\s"'`(\[{<\/\\#@$_.-]/u.test(s0) || /[✓✔✗✕…!?]$/u.test(s0);
  const s = s0.replace(/^[^\p{L}\p{N}]+/u, "").replace(/[^\p{L}\p{N}]+$/u, "") || s0;
  if (sus && /\p{L}{2,}/u.test(s)) return true;
  if (TR_HARF.test(s)) {
    // Türkçe harf taşıyan ama açıkça kod olanlar: yol / dosya adı / kimlik
    if (/^[\w.\-\/\\:çğıöşüÇĞİÖŞÜ]+\.(tsx?|jsx?|json|py|rs|md|png|jpe?g|pdf|csv|zip|exe|log|db)$/i.test(s)) return false;
    return true;
  }
  if (/^[a-z][a-z0-9+.\-]*:\/\//i.test(s) || /^(mailto|tel|data|blob):/i.test(s)) return false; // URL
  if (/^\/[\w\-./:{}?=&%]*$/.test(s)) return false; // yol (/api/x)
  if (/^[\w\-]+\/[\w\-+.]+(;.*)?$/.test(s) && !/\s/.test(s)) return false; // mime (application/json)
  if (/^#[0-9a-f]{3,8}$/i.test(s) || /^(rgba?|hsla?)\(/i.test(s)) return false; // renk
  if (/^[\w.\-]+@[\w.\-]+$/.test(s)) return false; // e-posta
  if (/^[A-ZÇĞİÖŞÜ]{3,}[.!?…:]$/.test(s0)) return true; // "UYARI:", "DURDURULUYOR…" (sabit adı değil, noktalamalı vurgu)
  if (/^[A-Z0-9_]+$/.test(s)) return false; // SABIT_ADI / kısaltma (OK, API, PEMF …)
  if (/^[a-z][A-Za-z0-9_]*$/.test(s)) return false; // camelCase / küçük harf tanımlayıcı
  if (/^[a-z0-9]+([_\-.:][a-z0-9]+)+$/i.test(s) && !/\s/.test(s)) return false; // snake / kebab / nokta / iki nokta
  if (/^[\d\s.,:;%+\-*/()=<>xX°]+[a-zA-Zµ°%]{0,3}$/.test(s)) return false; // sayı + birim (12 mT, 5 Hz)
  if (/^(mT|Hz|kHz|MHz|ms|sn|dk|sa|°C|µT|uT|V\/m|mA|A|V|W|kg|g|mm|cm|m|px|dp|pt|em|rem|vh|vw|fr|%)$/.test(s)) return false;
  if (/\s/.test(s)) {
    const sozcuk = s.split(/\s+/).filter((w) => /\p{L}{2,}/u.test(w));
    return sozcuk.length >= 2 || /^[A-ZÇĞİÖŞÜ]/.test(s);
  }
  // tek sözcük: Büyük harfle başlayan doğal sözcük (Kaydet, Hastalar) → aday; KarışıkDurum (PascalCase) → kod
  if (/^[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}[.!?…:]?$/.test(s)) return true;
  return false;
}

const KATLA = { ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u", Ç: "C", Ğ: "G", İ: "I", Ö: "O", Ş: "S", Ü: "U", â: "a", î: "i", û: "u" };
function asciiKatla(s) {
  return s.replace(/[çğıöşüÇĞİÖŞÜâîû]/g, (c) => KATLA[c] || c);
}
/** Öneri anahtar parçası: ASCII camelCase, ilk 4 sözcük. */
/** Şablon / birleşik metin doğal dil mi: yer tutucular atıldıktan sonra yol / tanımlayıcı DEĞİLSE ve en az bir sözcük
 *  (≥ 2 harf) taşıyorsa evet — "({{n}} bobin)" gibi küçük harfli Türkçe parçalar da yakalanır. */
function sablonDogalMi(sablon) {
  const sade = String(sablon).replace(/\{\{[^}]*\}\}/g, "\u0000");
  const govde = sade.replace(/\u0000/g, " ").trim();
  if (!govde || !/\p{L}{2,}/u.test(govde)) return false;
  if (dogalMi(govde)) return true;
  const tek = sade.replace(/\u0000/g, "X");
  if (/^[a-z][a-z0-9+.\-]*:\/\//i.test(tek) || /^\/?[\w\-.]*(\/[\w\-.:]*)+[?#]?.*$/.test(tek)) return false; // URL / yol
  if (!/\s/.test(tek) && /^[\w\-.:#@\/=&?%]+$/.test(tek)) return false; // kimlik_X, pemf.X, #X
  return /(^|[\s(\[])\p{L}{2,}/u.test(govde.replace(/[()\[\]]/g, " "));
}

function anahtarParcasi(metin) {
  const sozcukler = asciiKatla(metin)
    .replace(/\{\{[^}]*\}\}/g, " ")
    .replace(/[^A-Za-z0-9 ]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 4);
  if (!sozcukler.length) return "metin";
  return sozcukler
    .map((w, i) => (i === 0 ? w.charAt(0).toLowerCase() + w.slice(1).toLowerCase() : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()))
    .join("");
}
/** Dosyadan ad alanı önerisi: ekran → "Screen" eki atılmış kök; diğerleri dosya kökü (küçük harfle başlar). */
function adAlaniOnerisi(dosya) {
  const kok = path.basename(dosya).replace(/\.(web|native|ios|android)?\.?(tsx?|jsx?|cjs|mjs)$/, "").replace(/\.$/, "");
  const sade = kok.replace(/Screen$/, "") || kok;
  return sade.charAt(0).toLowerCase() + sade.slice(1);
}

function ifadeAdi(ts, e) {
  if (!e) return "";
  if (ts.isIdentifier(e)) return e.text;
  if (ts.isPropertyAccessExpression(e)) {
    const sol = ifadeAdi(ts, e.expression);
    return sol ? sol + "." + e.name.text : e.name.text;
  }
  if (ts.isCallExpression(e)) return ifadeAdi(ts, e.expression);
  if (ts.isElementAccessExpression(e)) return ifadeAdi(ts, e.expression);
  return "";
}

/** Şablon / birleştirme içindeki ifade için yer tutucu adı. */
function yerTutucuAdi(ts, e, sira) {
  let x = e;
  while (x && (ts.isParenthesizedExpression(x) || ts.isAsExpression(x) || ts.isNonNullExpression(x))) x = x.expression;
  if (x && ts.isIdentifier(x)) return x.text;
  if (x && ts.isPropertyAccessExpression(x)) return x.name.text;
  return "deger" + sira;
}

function tekSatir(s) {
  return String(s).replace(/\s+/g, " ").trim();
}

/** JSX metin düğümünün EKRANA çıkan biçimi (Babel `cleanJSXElementLiteralChild` ile aynı kural): yeni satır içeren
 *  boşluk silinir, tek satırdaki boşluk korunur. Türkçe birebir karşılaştırma (`ham`) bunu kullanır. */
function jsxMetni(text) {
  const satirlar = String(text).split(/\r\n|\n|\r/);
  let sonDolu = 0;
  for (let i = 0; i < satirlar.length; i++) if (/[^ \t]/.test(satirlar[i])) sonDolu = i;
  let s = "";
  for (let i = 0; i < satirlar.length; i++) {
    let x = satirlar[i].replace(/\t/g, " ");
    if (i !== 0) x = x.replace(/^[ ]+/, "");
    if (i !== satirlar.length - 1) x = x.replace(/[ ]+$/, "");
    if (x) {
      if (i !== sonDolu) x += " ";
      s += x;
    }
  }
  return s;
}

/**
 * JSX metni / öznitelik dizgisindeki HTML varlıkları React'in ÇİZDİĞİ gibi çözülür (`&quot;` → `"`; önce boşluk kuralı, sonra varlık —
 * dönüştürücünün sırası). TypeScript düğüm metnini HAM tutar; çözülmezse katalog TR değeri `&quot;` taşır ve t() düz dizgi döndüğü için
 * ekranda AYNEN `&quot;` görünürdü (ölçüldü: AuthScreen hesap ekleme bandı). Tablo dışı adlı varlık olduğu gibi kalır (depoda yok).
 */
const VARLIK = {
  quot: '"', apos: "'", amp: "&", lt: "<", gt: ">", nbsp: " ", copy: "©", reg: "®", trade: "™", hellip: "…",
  mdash: "—", ndash: "–", laquo: "«", raquo: "»", middot: "·", bull: "•", rarr: "→", larr: "←", deg: "°", times: "×",
};
function jsxVarlikCoz(s) {
  return String(s).replace(/&(#[xX][0-9a-fA-F]+|#[0-9]+|[A-Za-z]+);/g, (m, v) => {
    if (v[0] === "#") return String.fromCodePoint(v[1] === "x" || v[1] === "X" ? parseInt(v.slice(2), 16) : parseInt(v.slice(1), 10));
    return Object.prototype.hasOwnProperty.call(VARLIK, v) ? VARLIK[v] : m;
  });
}

/** Kaynak metinden aday + ölçüm çıkarır. `dosya` yalnız rapor ve ad alanı önerisi içindir. */
function cikarKaynak(metin, dosya, secenek) {
  const ts = (secenek && secenek.ts) || tsYukle();
  const tur = /\.tsx$/i.test(dosya) || /\.jsx$/i.test(dosya) ? ts.ScriptKind.TSX : /\.(js|cjs|mjs)$/i.test(dosya) ? ts.ScriptKind.JSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(dosya, metin, ts.ScriptTarget.Latest, true, tur);
  const satirOtele = (secenek && secenek.satirOtele) || 0;
  const adAlani = (secenek && secenek.adAlani) || adAlaniOnerisi(dosya);
  const adaylar = [];
  const olcum = { karsilastirma: [], buyukKucuk: [], yerelAyar: [], sayiAyristirma: [], iletiCagrisi: [], hata: [] };

  const konum = (n) => {
    const p = sf.getLineAndCharacterOfPosition(n.getStart(sf));
    return { satir: p.line + 1 + satirOtele, sutun: p.character + 1 };
  };
  const satirMetni = (n) => {
    const p = sf.getLineAndCharacterOfPosition(n.getStart(sf));
    const satirlar = sf.getLineStarts();
    const bas = satirlar[p.line];
    const son = p.line + 1 < satirlar.length ? satirlar[p.line + 1] : metin.length;
    return tekSatir(metin.slice(bas, son)).slice(0, 200);
  };

  // `t` bağlaması. ÇEVİRİ işlevi yalnız `const { t } = useTranslation(…)` (ya da `TFunction` türlü parametre). Düğümden yukarı yolda
  // EN İÇTEKİ `t` bağlaması kazanır; o başka bir şeyse (geri çağırma parametresi `.map((t) => …)`, yerel değişken, döngü / catch
  // değişkeni, modül düzeyi içe aktarma) çeviri işlevini GÖLGELER → `tGolge` (uygula reddeder: eklenen `t("…")` yanlış işlevi çağırırdı).
  const tBaglar = (ad) =>
    !!ad &&
    ((ts.isIdentifier(ad) && ad.text === "t") ||
      ((ts.isObjectBindingPattern(ad) || ts.isArrayBindingPattern(ad)) &&
        ad.elements.some((el) => !ts.isOmittedExpression(el) && tBaglar(el.name))));
  const useTranslationCagrisi = (e) => {
    while (e && (ts.isAwaitExpression(e) || ts.isParenthesizedExpression(e) || ts.isAsExpression(e))) e = e.expression;
    return !!e && ts.isCallExpression(e) && ts.isIdentifier(e.expression) && e.expression.text === "useTranslation";
  };
  const bildirimTuru = (d) => (ts.isObjectBindingPattern(d.name) && useTranslationCagrisi(d.initializer) ? "ceviri" : "golge");
  function blokBaglamasi(ifadeler) {
    for (const st of ifadeler) {
      if (ts.isVariableStatement(st)) {
        for (const d of st.declarationList.declarations) if (tBaglar(d.name)) return bildirimTuru(d);
      } else if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st)) && st.name && st.name.text === "t") {
        return "golge";
      } else if (ts.isImportDeclaration(st) && st.importClause) {
        const ic = st.importClause;
        if (ic.name && ic.name.text === "t") return "golge";
        if (ic.namedBindings && ts.isNamedImports(ic.namedBindings) && ic.namedBindings.elements.some((el) => el.name.text === "t")) return "golge";
      }
    }
    return null;
  }

  /** Düğümün içinde bulunduğu bileşen / işlev ve `t` bağlaması (`tVar`: çeviri işlevi kapsamda · `tGolge`: başka bir `t` gölgeliyor). */
  function kapsam(n) {
    let x = n.parent;
    let islev = null;
    let bilesen = null;
    let tDurum = null;
    while (x) {
      if (ts.isFunctionDeclaration(x) || ts.isFunctionExpression(x) || ts.isArrowFunction(x) || ts.isMethodDeclaration(x)) {
        let ad = "";
        if (x.name && ts.isIdentifier(x.name)) ad = x.name.text;
        else if (x.parent && ts.isVariableDeclaration(x.parent) && ts.isIdentifier(x.parent.name)) ad = x.parent.name.text;
        else if (x.parent && ts.isPropertyAssignment(x.parent) && ts.isIdentifier(x.parent.name)) ad = x.parent.name.text;
        if (!islev) islev = ad || "(adsız)";
        if (!bilesen && /^[A-Z]/.test(ad)) bilesen = ad;
        if (tDurum === null && x.body && ts.isBlock(x.body)) tDurum = blokBaglamasi(x.body.statements);
        if (tDurum === null && x.parameters) {
          for (const p of x.parameters) {
            if (!tBaglar(p.name)) continue;
            tDurum = ts.isIdentifier(p.name) && p.type && /\bTFunction\b/.test(p.type.getText(sf)) ? "ceviri" : "golge";
            break;
          }
        }
      } else if (tDurum === null && (ts.isBlock(x) || ts.isSourceFile(x) || ts.isModuleBlock(x) || ts.isCaseClause(x) || ts.isDefaultClause(x))) {
        tDurum = blokBaglamasi(x.statements);
      } else if (tDurum === null && (ts.isForOfStatement(x) || ts.isForInStatement(x) || ts.isForStatement(x))) {
        const b = x.initializer;
        if (b && ts.isVariableDeclarationList(b) && b.declarations.some((d) => tBaglar(d.name))) tDurum = "golge";
      } else if (tDurum === null && ts.isCatchClause(x)) {
        if (x.variableDeclaration && tBaglar(x.variableDeclaration.name)) tDurum = "golge";
      }
      x = x.parent;
    }
    return { islev, bilesen, tVar: tDurum === "ceviri", tGolge: tDurum === "golge", modulDuzeyi: !islev };
  }

  function ekle(n, metinDegeri, turAdi, baglam, ek) {
    const k = konum(n);
    const kp = kapsam(n);
    const m = tekSatir(metinDegeri);
    adaylar.push(
      Object.assign(
        {
          dosya,
          satir: k.satir,
          sutun: k.sutun,
          bas: n.getStart(sf),
          son: n.getEnd(),
          metin: m,
          // ham: ekrana çıkan BİREBİR metin (boşluklar korunur; JSX'te React boşluk kuralı) — tr katalog değeri buna eşit olmalı
          ham: ek && ek.ham !== undefined ? ek.ham : String(metinDegeri),
          tur: turAdi,
          baglam: baglam || "",
          oneri: adAlani + "." + anahtarParcasi(m),
          yertutucular: [],
          birlesik: false,
          bilesen: kp.bilesen,
          islev: kp.islev,
          tVar: kp.tVar,
          tGolge: kp.tGolge,
          modulDuzeyi: kp.modulDuzeyi,
          kaynakSatiri: satirMetni(n),
        },
        ek || {},
      ),
    );
  }

  /** Şablon dizgiyi {{ad}} yer tutuculu metne çevirir. */
  function sablonMetni(n) {
    let s = n.head.text;
    const yt = [];
    n.templateSpans.forEach((sp, i) => {
      let ad = yerTutucuAdi(ts, sp.expression, i + 1);
      while (yt.includes(ad)) ad = ad + (i + 1);
      yt.push(ad);
      s += "{{" + ad + "}}" + sp.literal.text;
    });
    return { s, yt };
  }

  /** `a + "x" + b` zincirini düzleştirir; içinde en az bir doğal dil dizgisi varsa birleşik aday. */
  function birlesimMetni(n) {
    const parcalar = [];
    const topla = (e) => {
      if (ts.isBinaryExpression(e) && e.operatorToken.kind === ts.SyntaxKind.PlusToken) {
        topla(e.left);
        topla(e.right);
      } else parcalar.push(e);
    };
    topla(n);
    let s = "";
    const yt = [];
    let dogal = false;
    let sira = 0;
    for (const p of parcalar) {
      if (ts.isStringLiteral(p) || ts.isNoSubstitutionTemplateLiteral(p)) {
        s += p.text;
        if (dogalMi(p.text)) dogal = true;
      } else if (ts.isTemplateExpression(p)) {
        const r = sablonMetni(p);
        s += r.s;
        yt.push(...r.yt);
        if (sablonDogalMi(r.s)) dogal = true;
      } else {
        sira += 1;
        let ad = yerTutucuAdi(ts, p, sira);
        while (yt.includes(ad)) ad = ad + sira;
        yt.push(ad);
        s += "{{" + ad + "}}";
      }
    }
    return { s, yt, dogal };
  }

  /** Dizgi düğümünün bağlamını sınıflar: null = kesin KOD (aday değil) | {tur, baglam}. */
  function baglamSinifi(n) {
    let p = n.parent;
    let cocuk = n;
    // parantez / as / koşullu / || ?? zincirinde yukarı çık (ifade bağlamı aynı kalır)
    while (
      p &&
      (ts.isParenthesizedExpression(p) ||
        ts.isAsExpression(p) ||
        ts.isSatisfiesExpression?.(p) ||
        ts.isNonNullExpression(p) ||
        (ts.isConditionalExpression(p) && cocuk !== p.condition) ||
        (ts.isBinaryExpression(p) &&
          (p.operatorToken.kind === ts.SyntaxKind.BarBarToken ||
            p.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken ||
            p.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) &&
          cocuk === p.right))
    ) {
      cocuk = p;
      p = p.parent;
    }
    if (!p) return { tur: "dizgi", baglam: "" };
    if (ts.isImportDeclaration(p) || ts.isExportDeclaration(p) || ts.isExternalModuleReference(p) || ts.isImportTypeNode?.(p)) return null;
    if (ts.isLiteralTypeNode(p)) return null;
    if (ts.isPropertyAssignment(p) && p.name === cocuk) return null;
    if (ts.isPropertyAssignment(p) && ts.isComputedPropertyName(p.name)) return null;
    if (ts.isComputedPropertyName(p)) return null;
    if (ts.isElementAccessExpression(p) && p.argumentExpression === cocuk) return null;
    if (ts.isCaseClause(p)) return { tur: "karsilastirma", baglam: "case" };
    if (ts.isEnumMember(p)) return null;
    if (ts.isPropertyDeclaration(p) && p.name === cocuk) return null;
    if (ts.isExpressionStatement(p)) return null; // "use strict" vb.
    if (ts.isBinaryExpression(p)) {
      const k = p.operatorToken.kind;
      if (
        k === ts.SyntaxKind.EqualsEqualsEqualsToken ||
        k === ts.SyntaxKind.ExclamationEqualsEqualsToken ||
        k === ts.SyntaxKind.EqualsEqualsToken ||
        k === ts.SyntaxKind.ExclamationEqualsToken ||
        k === ts.SyntaxKind.InKeyword ||
        k === ts.SyntaxKind.InstanceOfKeyword
      )
        return { tur: "karsilastirma", baglam: ts.tokenToString(k) || "" };
    }
    if (ts.isCallExpression(p) || ts.isNewExpression(p)) {
      const ad = ifadeAdi(ts, p.expression);
      const yontem = ad.split(".").pop() || "";
      const nesne = ad.split(".")[0] || "";
      if (ts.isCallExpression(p) && p.expression.kind === ts.SyntaxKind.ImportKeyword) return null;
      if (ad === "require" || ad === "jest.mock" || ad === "jest.requireActual" || ad === "jest.unmock" || ad === "jest.doMock") return null;
      if (ad === "describe" || ad === "it" || ad === "test" || ad.startsWith("describe.") || ad.startsWith("it.") || ad.startsWith("test.")) return null;
      if (GUNLUK_NESNESI.test(nesne) && GUNLUK_YONTEMI.test(yontem)) return { tur: "gunluk", baglam: ad };
      if (ad.split(".").length > 1 && KARSILASTIRMA_YONTEMI.has(yontem)) return { tur: "karsilastirma", baglam: ad };
      if (ad === "StyleSheet.create") return null;
      if (ts.isNewExpression(p) && /Error$/.test(ad)) return { tur: "hata", baglam: "new " + ad };
      if (ILETI_CAGRILARI.has(ad)) return { tur: "ileti", baglam: ad };
      if (/^(t|i18n\.t|i18next\.t|kritikMetin|ceviri)$/.test(ad)) return null; // zaten çeviri çağrısı (ilk argüman ANAHTAR)
      return { tur: "cagri", baglam: ad };
    }
    if (ts.isJsxAttribute(p) || (ts.isJsxExpression(p) && p.parent && ts.isJsxAttribute(p.parent))) {
      const at = ts.isJsxAttribute(p) ? p : p.parent;
      const ad = at.name.getText(sf);
      if (KOD_OZNITELIK.has(ad)) return null;
      if (GORUNUR_OZNITELIK.has(ad)) return { tur: "oznitelik", baglam: ad };
      return { tur: "oznitelik?", baglam: ad };
    }
    if (ts.isJsxExpression(p)) return { tur: "jsx-ifade", baglam: "" };
    if (ts.isPropertyAssignment(p)) {
      const ad = p.name.getText(sf).replace(/^["']|["']$/g, "");
      // stil nesnesi değerleri (fontFamily: "Inter") ve bilinen kod anahtarları
      if (KOD_OZNITELIK.has(ad) || /^(fontFamily|fontWeight|backgroundColor|borderColor|textAlign|position|display|flexDirection|alignItems|justifyContent|overflow|cursor|transform)$/.test(ad))
        return null;
      return { tur: "nesne", baglam: ad };
    }
    if (ts.isVariableDeclaration(p)) {
      const ad = p.name.getText(sf);
      return { tur: "sabit", baglam: ad };
    }
    if (ts.isReturnStatement(p)) return { tur: "donus", baglam: "" };
    if (ts.isArrayLiteralExpression(p)) return { tur: "dizi", baglam: "" };
    // İç içe şablon / koşullu parça: dıştaki şablon onu {{degerN}} yer tutucusuyla gösterir → parça AYRICA adaydır.
    if (ts.isTemplateSpan(p)) return { tur: "sablon-parcasi", baglam: "" };
    if (ts.isBinaryExpression(p) && p.operatorToken.kind === ts.SyntaxKind.EqualsToken) return { tur: "atama", baglam: p.left.getText(sf).slice(0, 60) };
    if (ts.isParameter(p) || ts.isBindingElement(p)) return { tur: "varsayilan", baglam: p.name.getText(sf) };
    if (ts.isThrowStatement(p)) return { tur: "hata", baglam: "throw" };
    return { tur: "dizgi", baglam: ts.SyntaxKind[p.kind] };
  }

  const islenenBirlesim = new Set();

  function ziyaret(n) {
    // --- ölçüm: büyük / küçük harf, yerel ayar, sayı ayrıştırma, ileti çağrıları ---
    if (ts.isCallExpression(n)) {
      const ad = ifadeAdi(ts, n.expression);
      const yontem = ad.split(".").pop();
      const k = konum(n);
      if (/^(toUpperCase|toLowerCase|toLocaleUpperCase|toLocaleLowerCase)$/.test(yontem))
        olcum.buyukKucuk.push({ dosya, satir: k.satir, ifade: tekSatir(n.getText(sf)).slice(0, 120) });
      if (/^(toLocaleString|toLocaleDateString|toLocaleTimeString)$/.test(yontem) || /Intl\.(DateTimeFormat|NumberFormat|Collator|PluralRules|RelativeTimeFormat)/.test(ad) || (yontem === "localeCompare"))
        olcum.yerelAyar.push({ dosya, satir: k.satir, ifade: tekSatir(n.getText(sf)).slice(0, 120) });
      if (/^(parseFloat|parseInt|Number|Number\.parseFloat|Number\.parseInt|sayiyaCevir|sayiAyristir|parseNumber)$/.test(ad))
        olcum.sayiAyristirma.push({ dosya, satir: k.satir, ifade: tekSatir(n.getText(sf)).slice(0, 120) });
      if (ILETI_CAGRILARI.has(ad)) olcum.iletiCagrisi.push({ dosya, satir: k.satir, cagri: ad });
      if (ad.split(".").length > 1 && /^(includes|startsWith|endsWith|indexOf|match|test|search|replace)$/.test(yontem)) {
        const a0 = n.arguments[0];
        if (a0 && (ts.isStringLiteral(a0) || ts.isNoSubstitutionTemplateLiteral(a0) || ts.isRegularExpressionLiteral(a0)) && TR_HARF.test(a0.text || a0.getText(sf)))
          olcum.karsilastirma.push({ dosya, satir: k.satir, ifade: tekSatir(n.getText(sf)).slice(0, 140) });
      }
      // /Sıfırla/.test(eylem) · /bulunamadı/i.exec(m): Türkçe metne göre DALLANMA (dil değişince sessizce bozulur)
      if (ts.isPropertyAccessExpression(n.expression) && ts.isRegularExpressionLiteral(n.expression.expression) && /^(test|exec)$/.test(n.expression.name.text)) {
        const rx = n.expression.expression.getText(sf);
        if (TR_HARF.test(rx) || /[a-zçğıöşü]{4,}\|[a-zçğıöşü]{4,}/i.test(rx))
          olcum.karsilastirma.push({ dosya, satir: k.satir, ifade: tekSatir(n.getText(sf)).slice(0, 140) });
      }
    }
    if (ts.isBinaryExpression(n)) {
      const k = n.operatorToken.kind;
      if (k === ts.SyntaxKind.EqualsEqualsEqualsToken || k === ts.SyntaxKind.ExclamationEqualsEqualsToken || k === ts.SyntaxKind.EqualsEqualsToken) {
        for (const yan of [n.left, n.right]) {
          if ((ts.isStringLiteral(yan) || ts.isNoSubstitutionTemplateLiteral(yan)) && TR_HARF.test(yan.text))
            olcum.karsilastirma.push({ dosya, satir: konum(n).satir, ifade: tekSatir(n.getText(sf)).slice(0, 140) });
        }
      }
    }

    // --- adaylar ---
    if (ts.isJsxText(n)) {
      const m = tekSatir(jsxVarlikCoz(n.text));
      if (m && /\p{L}/u.test(m)) {
        const kardes = n.parent && n.parent.children ? n.parent.children : [];
        const karisik = kardes.some((c) => c !== n && ts.isJsxExpression(c) && c.expression);
        ekle(n, m, "jsx-metin", n.parent && n.parent.openingElement ? n.parent.openingElement.tagName.getText(sf) : "", {
          birlesik: karisik,
          ham: jsxVarlikCoz(jsxMetni(n.text)),
        });
      }
    } else if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) {
      if (n.parent && ts.isTemplateSpan(n.parent)) return; // olamaz ama güvenlik
      const sinif = baglamSinifi(n);
      if (sinif && sinif.tur !== "gunluk" && sinif.tur !== "karsilastirma") {
        // birleştirme zincirinin parçasıysa zincir bir kez işlenir
        let ust = n.parent;
        while (ust && ts.isParenthesizedExpression(ust)) ust = ust.parent;
        if (ust && ts.isBinaryExpression(ust) && ust.operatorToken.kind === ts.SyntaxKind.PlusToken) {
          let kok = ust;
          while (kok.parent && ts.isBinaryExpression(kok.parent) && kok.parent.operatorToken.kind === ts.SyntaxKind.PlusToken) kok = kok.parent;
          if (!islenenBirlesim.has(kok)) {
            islenenBirlesim.add(kok);
            const r = birlesimMetni(kok);
            const ks = baglamSinifi(kok);
            if (r.dogal && ks && ks.tur !== "gunluk" && ks.tur !== "karsilastirma")
              ekle(kok, r.s, ks.tur, ks.baglam, { yertutucular: r.yt, birlesik: true });
          }
        } else if (
          dogalMi(n.text) ||
          (sinif.tur === "oznitelik" && /\p{L}/u.test(n.text)) ||
          // JSX alt ifadesi (`{ok ? "CANLI" : "OFFLINE"}`) EKRANA yazılır: tek sözcüklü harf dizisi sabit adı sanılmamalı
          // ("kararsızsan ÇEVRİLİR say" — I18N-P1 ekran taramasında yakalanan boşluk)
          (sinif.tur === "jsx-ifade" && /^\p{L}{2,}$/u.test(n.text.trim())) ||
          // şablon içi koşullu parça ("yok", "lar") çoğu zaman görünen metin / Türkçe ektir → kararsızsa aday
          (sinif.tur === "sablon-parcasi" && /\p{L}{2,}/u.test(n.text) && !/[\/_.=#@:]/.test(n.text))
        ) {
          // JSX öznitelik dizgisi de varlık çözülerek çizilir (`title="a &amp; b"` → "a & b"); JS dizgisi çözülmez.
          ekle(n, n.parent && ts.isJsxAttribute(n.parent) ? jsxVarlikCoz(n.text) : n.text, sinif.tur, sinif.baglam);
        }
      }
    } else if (ts.isTemplateExpression(n)) {
      const sinif = baglamSinifi(n);
      const r = sablonMetni(n);
      let ust = n.parent;
      while (ust && ts.isParenthesizedExpression(ust)) ust = ust.parent;
      const zincirde = ust && ts.isBinaryExpression(ust) && ust.operatorToken.kind === ts.SyntaxKind.PlusToken;
      if (!zincirde && sinif && sinif.tur !== "gunluk" && sinif.tur !== "karsilastirma" && sablonDogalMi(r.s))
        ekle(n, r.s, sinif.tur === "dizgi" ? "sablon" : sinif.tur, sinif.baglam, { yertutucular: r.yt, birlesik: true });
      if (zincirde && !islenenBirlesim.has(ust)) {
        let kok = ust;
        while (kok.parent && ts.isBinaryExpression(kok.parent) && kok.parent.operatorToken.kind === ts.SyntaxKind.PlusToken) kok = kok.parent;
        if (!islenenBirlesim.has(kok)) {
          islenenBirlesim.add(kok);
          const rb = birlesimMetni(kok);
          const ks = baglamSinifi(kok);
          if (rb.dogal && ks && ks.tur !== "gunluk" && ks.tur !== "karsilastirma") ekle(kok, rb.s, ks.tur, ks.baglam, { yertutucular: rb.yt, birlesik: true });
        }
      }
      // şablonun içindeki ifadelerde de aday olabilir (ör. koşullu metin)
    }
    ts.forEachChild(n, ziyaret);
  }
  ziyaret(sf);
  adaylar.sort((a, b) => a.bas - b.bas);
  for (const a of adaylar) if (a.tur === "hata") olcum.hata.push({ dosya, satir: a.satir, metin: a.metin.slice(0, 120) });
  return { adaylar, olcum };
}

function cikarDosya(yol, secenek) {
  const metin = fs.readFileSync(yol, "utf8");
  const goreli = path.relative(DEPO_KOKU, path.resolve(yol)).split(path.sep).join("/");
  return cikarKaynak(metin, (secenek && secenek.goreliAd) || goreli, secenek);
}

module.exports = { cikarKaynak, cikarDosya, dogalMi, sablonDogalMi, jsxMetni, jsxVarlikCoz, anahtarParcasi, adAlaniOnerisi, asciiKatla, tsYukle, DEPO_KOKU };

if (require.main === module) {
  // Kipler: `node cikar_ts.cjs [--olcum] <dosya>...`  ya da  `node cikar_ts.cjs --stdin [--olcum]` (stdin: JSON liste
  // [{"yol": <dosya>} | {"ad": <depo-göreli ad>, "metin": <kaynak>, "satirOtele": n, "uzanti": ".js"}] — HTML içi <script>).
  const argv = process.argv.slice(2);
  const olcumIste = argv.includes("--olcum");
  const ts = tsYukle();
  const tum = { adaylar: [], olcum: { karsilastirma: [], buyukKucuk: [], yerelAyar: [], sayiAyristirma: [], iletiCagrisi: [], hata: [] }, hatalar: [] };
  const isle = (girdi) => {
    try {
      let r;
      if (girdi.metin !== undefined) {
        const ad = girdi.ad + (girdi.uzanti && !girdi.ad.endsWith(girdi.uzanti) ? "#" + girdi.uzanti : "");
        r = cikarKaynak(girdi.metin, ad, { ts, satirOtele: girdi.satirOtele || 0, adAlani: girdi.adAlani });
        for (const a of r.adaylar) a.dosya = girdi.ad;
        for (const k of Object.keys(r.olcum)) for (const x of r.olcum[k]) x.dosya = girdi.ad;
      } else r = cikarDosya(girdi.yol, { ts });
      tum.adaylar.push(...r.adaylar);
      for (const k of Object.keys(tum.olcum)) tum.olcum[k].push(...r.olcum[k]);
    } catch (e) {
      tum.hatalar.push({ dosya: girdi.yol || girdi.ad, hata: String(e && e.message ? e.message : e) });
    }
  };
  const bitir = () => {
    if (!olcumIste) delete tum.olcum;
    process.stdout.write(JSON.stringify(tum));
  };
  if (argv.includes("--stdin")) {
    let veri = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (p) => (veri += p));
    process.stdin.on("end", () => {
      for (const g of JSON.parse(veri || "[]")) isle(g);
      bitir();
    });
  } else {
    for (const d of argv.filter((a) => !a.startsWith("--"))) isle({ yol: d });
    bitir();
  }
}
