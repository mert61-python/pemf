/**
 * K-2 (jest tarafı) · SABİT METİN YASAĞI — arayüzde kapsam defterinde (`i18n/kapsam.json`) `tamam` işaretli her TS / TSX dosyasında
 * kullanıcıya görünebilecek SABİT metin kalmaz (gerekçeli muaflar hariç). Çıkarıcı pytest tarafıyla AYNI: `scripts/i18n/cikar_ts.cjs`
 * (TypeScript derleyici API'si). jest her koşuda TypeScript'e sahip olduğu için bu kapı ATLANMAZ (pytest tarafı node_modules yoksa
 * TS dosyalarını atlar — bkz. tests/test_i18n_sabit_metin_K2.py). Muaf kuralı `scripts/i18n/kapsam.py::muaf_mi` ile AYNI: dosyanın
 * `muaf` listesi · `genelMuaf` (birebir) · `genelMuafDesen` (tam eşleşen düzenli ifade) · `durum: muaf` dosya.
 *
 * Aynı dosya çıkarıcının KENDİSİNİ de sınar (kör kapı olmasın): bilinen bir sabit metinli kaynak aday VERMELİ.
 */
import { readFileSync } from "fs";
import { join } from "path";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { cikarKaynak } = require("../../../../../scripts/i18n/cikar_ts.cjs");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const ts = require("typescript");

const KOK = join(__dirname, "..", "..", "..", "..", "..");
type Kayit = { yuzey: string; durum: string; muaf?: { metin: string }[] };
type Defter = {
  genelMuaf: { metin: string }[];
  genelMuafDesen?: { desen: string }[];
  dosyalar: Record<string, Kayit>;
};
const defter = JSON.parse(readFileSync(join(KOK, "i18n", "kapsam.json"), "utf8")) as Defter;
const genelMuaf = new Set(defter.genelMuaf.map((m) => m.metin));
const desenler = (defter.genelMuafDesen ?? []).map((d) => new RegExp(`^(?:${d.desen})$`));

function muafMi(kayit: Kayit, metin: string): boolean {
  if (kayit.durum === "muaf") return true;
  if ((kayit.muaf ?? []).some((m) => m.metin === metin)) return true;
  return genelMuaf.has(metin) || desenler.some((d) => d.test(metin));
}

function ihlaller(dosya: string, kayit: Kayit): string[] {
  const metin = readFileSync(join(KOK, dosya), "utf8");
  const { adaylar } = cikarKaynak(metin, dosya, { ts });
  return (adaylar as { metin: string; satir: number; tur: string }[])
    .filter((a) => !muafMi(kayit, a.metin))
    .map((a) => `${dosya}:${a.satir} [${a.tur}] ${JSON.stringify(a.metin)}`);
}

const tamamTs = Object.entries(defter.dosyalar).filter(
  ([d, k]) => k.yuzey === "arayuz" && k.durum === "tamam" && /\.(ts|tsx)$/.test(d),
);

it("çıkarıcı kör değil: sabit metinli kaynakta aday verir (karşıt kanıt)", () => {
  const { adaylar } = cikarKaynak('export function A() { return <Text title="Kaydet">Seans geçmişi</Text>; }', "x/A.tsx", { ts });
  expect((adaylar as { metin: string }[]).map((a) => a.metin)).toEqual(expect.arrayContaining(["Kaydet", "Seans geçmişi"]));
});

it("muaf kuralı Türkçe metni yutmaz, CSS sınıfını / ürün adını geçirir (pytest tarafıyla aynı)", () => {
  const k: Kayit = { yuzey: "arayuz", durum: "tamam" };
  expect(["e-posta", "Kaydet", "Bobin"].filter((m) => muafMi(k, m))).toEqual([]);
  expect(["PEMF Vet", "btn-primary", "text-muted hover:text-fg"].every((m) => muafMi(k, m))).toBe(true);
});

it("defterde en az bir arayüz dosyası tamam (kapı boş küme üzerinde koşmuyor)", () => {
  expect(tamamTs.length).toBeGreaterThan(0);
});

it("K-2: tamam işaretli arayüz dosyalarında kullanıcıya görünen sabit metin YOK", () => {
  const hepsi = tamamTs.flatMap(([d, k]) => ihlaller(d, k));
  expect(hepsi).toEqual([]);
});

/**
 * KANCA BAĞIMLILIĞI (I18N-0): `useCallback` / `useMemo` / `useEffect` / `useLayoutEffect` geri çağırması `t(` çağırıyorsa bağımlılık
 * dizisinde `t` OLMALI — yoksa dil değişince kapalı (closure) eski `t` kalır ve o ileti eski dilde çıkar. `uygula_ts` ekler; bu kapı elle
 * yapılan / sonradan bozulan durumu yakalar. Kapsam: `useTranslation` kullanan her arayüz dosyası.
 */
const KANCA = new Set(["useCallback", "useMemo", "useEffect", "useLayoutEffect"]);
function kancaIhlalleri(metin: string, dosya: string): string[] {
  const sf = ts.createSourceFile(dosya, metin, ts.ScriptTarget.Latest, true, /\.tsx$/.test(dosya) ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const sorun: string[] = [];
  const tCagiriyor = (n: any): boolean => {
    let var_ = false;
    const gez = (x: any) => {
      if (var_) return;
      if (ts.isCallExpression(x) && ts.isIdentifier(x.expression) && x.expression.text === "t") var_ = true;
      else ts.forEachChild(x, gez);
    };
    gez(n);
    return var_;
  };
  const gez = (n: any) => {
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && KANCA.has(n.expression.text)) {
      const [geri, dizi] = n.arguments;
      if (geri && dizi && ts.isArrayLiteralExpression(dizi) && tCagiriyor(geri)) {
        if (!dizi.elements.some((e: any) => ts.isIdentifier(e) && e.text === "t")) {
          const s = sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
          sorun.push(`${dosya}:${s} ${n.expression.text} t() çağırıyor ama bağımlılığında t YOK`);
        }
      }
    }
    ts.forEachChild(n, gez);
  };
  gez(sf);
  return sorun;
}

it("kanca bağımlılığı: t() çağıran useCallback / useMemo / useEffect dizisinde t var (dil değişince eski dilde kalmaz)", () => {
  const ornek = 'const f = useCallback(() => goster(t("a.b")), [x]);';
  expect(kancaIhlalleri(ornek, "x.tsx")).toHaveLength(1); // karşıt kanıt: kapı kör değil
  expect(kancaIhlalleri(ornek.replace("[x]", "[x, t]"), "x.tsx")).toEqual([]);
  const hepsi = Object.entries(defter.dosyalar)
    .filter(([d, k]) => k.yuzey === "arayuz" && /\.(ts|tsx)$/.test(d))
    .flatMap(([d]) => {
      const metin = readFileSync(join(KOK, d), "utf8");
      return metin.includes("useTranslation") ? kancaIhlalleri(metin, d) : [];
    });
  expect(hepsi).toEqual([]);
});
