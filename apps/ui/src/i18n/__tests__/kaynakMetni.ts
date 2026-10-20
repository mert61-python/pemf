/**
 * I18N — KAYNAK METNİ TARAYAN jest testleri için yardımcı (pytest `tests/i18n_yardimci.py` ile AYNI ölçüt; ZAYIFLATMAZ).
 *
 * Göç metni kaynaktan kataloğa taşır; `readFileSync(...tsx)` + `toMatch(/Klinik \/ Muayenehane/)` gibi bir test yanlış kırmızı verir.
 * Ölçüt yer değiştirir: `gorunenMetinler(src)` = kaynak + kaynağın KULLANDIĞI anahtarların TR değerleri. Böylece "bu metin bu
 * dosyadan kullanıcıya ulaşıyor" iddiası korunur; metin kataloğa taşınınca da, anahtar kaynaktan kalkınca ya da TR değeri değişince kırmızı.
 * Yapısal iddialar (ör. `isExpert && (` koşulu) kaynakta aranmaya DEVAM eder — yalnız metin parçası kataloğa bakar.
 */
import { enKaynak, trKaynak } from "@/i18n/kaynaklar";

type Agac = { [k: string]: string | Agac };

function duzlestir(o: Agac, onek = "", c: Record<string, string> = {}): Record<string, string> {
  for (const [k, v] of Object.entries(o)) {
    const tam = onek ? `${onek}.${k}` : k;
    if (typeof v === "string") c[tam] = v;
    else duzlestir(v, tam, c);
  }
  return c;
}

export const TR = duzlestir(trKaynak as unknown as Agac);
export const EN = duzlestir(enKaynak as unknown as Agac);
const KULLANIM = /(?:(?:\b(?:t|kritikMetin)|\bi18n\.t)\(\s*|\bi18nKey=\{?\s*)["']([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)["']/g;

export function kullanilanAnahtarlar(src: string): Set<string> {
  const s = new Set<string>();
  for (const m of src.matchAll(KULLANIM)) s.add(m[1]);
  return s;
}

/** Kaynak + kullandığı anahtarların TR değerleri (çoğul biçimler dahil). EN'i boş olan anahtar EKLENMEZ (yarım çeviri geçemez). */
export function gorunenMetinler(src: string, tr: Record<string, string> = TR, en: Record<string, string> = EN): string {
  const ekler: string[] = [];
  for (const k of kullanilanAnahtarlar(src)) {
    for (const aday of [k, `${k}_one`, `${k}_other`]) {
      if (aday in tr && String(en[aday] ?? "").trim()) ekler.push(tr[aday]);
    }
  }
  return `${src}\n${ekler.join("\n")}`;
}
