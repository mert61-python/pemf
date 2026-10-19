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
