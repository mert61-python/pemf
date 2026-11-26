/**
 * YS1d (Y320 4): AP-B1 Kontrol belleği yazımı bileşen dışına (`kontrolHafizasinaYaz`) taşındı — React derleyicisi (`react-hooks/immutability`)
 * kancadan gelen nesnenin bileşen içinde değiştirilmesini HATA sayıyordu. Davranış aynı: bellek varsa YALNIZ istenen alan yazılır (diğer
 * alan korunur), bellek yoksa (sağlayıcısız) hiçbir şey olmaz.
 */
import type { MutableRefObject } from "react";
import type { KontrolHafizasi } from "@/context/AppNavContext";
import { kontrolHafizasinaYaz } from "@/utils/kontrolHafizasi";

describe("YS1d kontrolHafizasinaYaz", () => {
  it("bellek varken YALNIZ istenen alanı yazar, diğer alanı korur (aynı ref nesnesi)", () => {
    const aiPro = { hedefModeli: "petri", kosulsuz: false, frek: 10, duration: "20", organId: 3 };
    const bellek: MutableRefObject<KontrolHafizasi> = { current: { aiPro } };
    const ilk = bellek.current;
    kontrolHafizasinaYaz(bellek, "sekme", "aipro");
    expect(bellek.current).toBe(ilk);
    expect(bellek.current).toEqual({ sekme: "aipro", aiPro });
    const yeni = { ...aiPro, frek: 50 };
    kontrolHafizasinaYaz(bellek, "aiPro", yeni);
    expect(bellek.current).toEqual({ sekme: "aipro", aiPro: yeni });
  });

  it("KARŞIT: bellek yoksa (sağlayıcısız çizim) sessizce hiçbir şey yapmaz", () => {
    expect(() => kontrolHafizasinaYaz(undefined, "sekme", "manual")).not.toThrow();
  });
});
