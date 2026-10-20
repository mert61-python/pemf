/**
 * I18N-0 · `kaynakMetni.ts` (kaynak METNİ tarayan jest testlerinin yardımcısı) — ölçütü zayıflatmadığını kanıtlar: metin kataloğa taşınınca
 * görünür kalır; `t()` çağrısı kaynaktan kalkınca, TR değeri değişince ya da EN boşken GÖRÜNMEZ (kapı kırmızı olur).
 */
import { gorunenMetinler, kullanilanAnahtarlar, TR } from "./kaynakMetni";

const KAYNAK = 'export const K = () => <Text>{t("ayarlar.dil.baslik")}</Text>;';

it("gerçek katalog: kullanılan anahtarın TR değeri görünür metne eklenir", () => {
  expect(kullanilanAnahtarlar(KAYNAK)).toEqual(new Set(["ayarlar.dil.baslik"]));
  expect(gorunenMetinler(KAYNAK)).toContain(TR["ayarlar.dil.baslik"]);
  expect(TR["ayarlar.dil.baslik"]).toBe("Dil / Language");
});

it("t() kalkınca / TR değişince / EN boşken metin GÖRÜNMEZ (iki mutant + yarım çeviri)", () => {
  const tr = { "x.y": "Seans geçmişi" };
  expect(gorunenMetinler(KAYNAK.replace('t("ayarlar.dil.baslik")', "null"))).not.toContain("Dil / Language");
  expect(gorunenMetinler('t("x.y")', { "x.y": "Seans kaydı" }, { "x.y": "Session" })).not.toContain("Seans geçmişi");
  expect(gorunenMetinler('t("x.y")', tr, { "x.y": " " })).not.toContain("Seans geçmişi");
  expect(gorunenMetinler('t("x.y")', tr, { "x.y": "Session history" })).toContain("Seans geçmişi");
});

it("<Trans i18nKey> zengin metin anahtarı da KULLANIM sayılır (düz ve {\"…\"} biçimi)", () => {
  expect(kullanilanAnahtarlar('<Trans i18nKey="a.b" components={{}} /><Trans i18nKey={"c.d"} />')).toEqual(new Set(["a.b", "c.d"]));
  expect(gorunenMetinler('<Trans i18nKey="x.y" />', { "x.y": "Seans <b>geçmişi</b>" }, { "x.y": "Session" })).toContain("Seans <b>geçmişi</b>");
});

it("çoğul anahtar: _one / _other biçimleri eklenir", () => {
  const tr = { "s.adet_one": "{{count}} seans", "s.adet_other": "{{count}} seans" };
  const en = { "s.adet_one": "{{count}} session", "s.adet_other": "{{count}} sessions" };
  expect(gorunenMetinler('t("s.adet", { count })', tr, en)).toContain("{{count}} seans");
});
