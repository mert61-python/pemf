// Author: mertaygn, cglrgrkn
/**
 * I18N-P · KRİTİK (GÜVENLİK) ANAHTARLAR — `i18n/kritik-anahtarlar.json`'daki her arayüz anahtarı İKİ dilde sınanır:
 *   · TR ve EN katalogda DOLU; yer tutucu kümesi AYNI (çevirmen `{{ad}}`'ı düşürüp eylemi kaybettirmesin);
 *   · EN, TR'nin kopyası DEĞİL (çevrilmemiş kritik metin sessizce geçmesin);
 *   · kaynak dosya anahtarı GERÇEKTEN kullanıyor (metin ekrana ulaşıyor);
 *   · çalışma zamanında `i18n.t(anahtar, { lng })` iki dilde katalogdaki değeri verir.
 * ACİL DURDUR yedeği (`kritik.ts`) ve çoğul biçimleri kendi testlerinde (`GlobalEmergencyStop.I18N0.kritik.test.tsx`); burada çoğul
 * kökler `_one` / `_other` ile sayılır. Eylem davranışı (düğme ne yapar) her ekranın KENDİ testinde iki dilde sınanır.
 */
import { readFileSync } from "fs";
import { join } from "path";
import i18n from "i18next";
import { EN, TR, kullanilanAnahtarlar } from "@/i18n/__tests__/kaynakMetni";

const KOK = join(__dirname, "..", "..", "..", "..", "..");
type Kayit = { yuzey: string; anahtar: string; tur: string; kaynak: string };
const liste = (JSON.parse(readFileSync(join(KOK, "i18n", "kritik-anahtarlar.json"), "utf8")) as { anahtarlar: Kayit[] }).anahtarlar.filter(
  (k) => k.yuzey === "arayuz",
);

const yerTutucular = (s: string) => [...s.matchAll(/\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g)].map((m) => m[1]).sort().join(",");
const biçimler = (k: string) => [k, `${k}_one`, `${k}_other`].filter((a) => a in TR);
const tt = i18n.t.bind(i18n) as unknown as (k: string, o?: Record<string, unknown>) => string;

it("kritik liste boş değil (kör kapı olmasın)", () => {
  expect(liste.length).toBeGreaterThan(0);
});

describe.each(liste.map((k) => [k.anahtar, k] as const))("kritik anahtar %s", (anahtar, k) => {
  it("TR + EN dolu, yer tutucular aynı, EN çevrilmiş", () => {
    const b = biçimler(anahtar);
    expect(b.length).toBeGreaterThan(0);
    for (const a of b) {
      expect(String(TR[a] ?? "").trim()).not.toBe("");
      expect(String(EN[a] ?? "").trim()).not.toBe("");
      expect(yerTutucular(EN[a])).toBe(yerTutucular(TR[a]));
      expect(EN[a]).not.toBe(TR[a]);
    }
  });

  it("kaynak dosya anahtarı kullanıyor", () => {
    const src = readFileSync(join(KOK, k.kaynak), "utf8");
    expect(kullanilanAnahtarlar(src).has(anahtar) || src.includes(`"${anahtar}`)).toBe(true);
  });

  it("çalışma zamanı: iki dilde katalog değeri", () => {
    const a = biçimler(anahtar)[0];
    const sade = a.replace(/_(one|other)$/, "");
    const p = { count: 2, ad: "x", hesapSayisi: 2, surum: "1" } as Record<string, unknown>;
    const yer = (s: string) => s.replace(/\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g, (_m, g: string) => String(p[g] ?? `{{${g}}}`));
    const beklenenTr = yer(TR[a]);
    const beklenenEn = yer(EN[a]);
    const tr = tt(sade, { ...p, lng: "tr" });
    const en = tt(sade, { ...p, lng: "en" });
    if (a === sade) {
      expect(tr).toBe(beklenenTr);
      expect(en).toBe(beklenenEn);
    } else {
      // çoğul kök: count=2 → _other
      expect(tr).toBe(yer(TR[`${sade}_other`]));
      expect(en).toBe(yer(EN[`${sade}_other`]));
    }
  });
});
