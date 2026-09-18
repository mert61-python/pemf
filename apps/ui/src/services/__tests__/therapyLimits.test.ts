/**
 * SAHİP KARARI (2026-09-08): frekans ve duty arayüzde SINIRLANMAZ — tezgâhta istenen değer
 * verilebilmeli; tek sınır cihaz firmware'i (NACK). Bu test kararı KORUR: freq/duty olduğu
 * gibi geçer ve "aralığına çekildi" uyarısı üretmez; faz/süre/yoğunluk klempi ise kalır.
 * (Mutasyon: freq'i yeniden THERAPY_LIMITS'e koyup klemplemek ilk testi düşürür.)
 */
import { clampParam, clampTherapyParams, SINIRSIZ_PARAMLAR, THERAPY_LIMITS } from "@/services/therapyLimits";

describe("therapyLimits — freq/duty sınırsız (sahip kararı 2026-09-08)", () => {
  it("KRİTİK: 500 Hz ve %80 duty OLDUĞU GİBİ geçer, uyarı yok", () => {
    const r = clampTherapyParams({ freq: 500, duty: 80, phase: 90, duration: 20 });
    expect(r.values.freq).toBe(500);
    expect(r.values.duty).toBe(80);
    expect(r.warnings).toEqual([]);
  });

  it("0.5 Hz ve %0.5 duty da arayüzde çekilmez (cihaz karar verir)", () => {
    const r = clampTherapyParams({ freq: 0.5, duty: 0.5 });
    expect(r.values).toEqual({ freq: 0.5, duty: 0.5 });
    expect(r.warnings).toEqual([]);
    expect(clampParam("freq", 5000)).toBe(5000);
    expect(clampParam("duty", 99)).toBe(99);
  });

  it("freq/duty THERAPY_LIMITS'te YOK, SINIRSIZ_PARAMLAR'da VAR (geri eklenirse kırmızı)", () => {
    expect(Object.keys(THERAPY_LIMITS)).not.toContain("freq");
    expect(Object.keys(THERAPY_LIMITS)).not.toContain("duty");
    expect([...SINIRSIZ_PARAMLAR]).toEqual(["freq", "duty"]);
  });

  it("KARŞIT-KANIT: faz/süre/yoğunluk klempi ve uyarısı korunur", () => {
    const r = clampTherapyParams({ phase: 400, duration: 500, intensity: 50 });
    expect(r.values.phase).toBe(360);
    expect(r.values.duration).toBe(120);
    expect(r.values.intensity).toBe(20);
    expect(r.warnings).toHaveLength(3);
    expect(r.warnings[0]).toMatch(/Faz 0–360 ° aralığına çekildi/);
    expect(clampParam("phase", NaN)).toBe(0);
  });
});
