/**
 * TA T1 (Y292-1) · istemci hak katmanı: iptal / ödeme gecikmesi = ÖDENMİŞ DÖNEM SONUNA KADAR erişim.
 * Önce: `isActive` yalnız active / trialing kabul ediyordu → iptal eden ödeyen kullanıcı dönem ortasında Pro / Pro+ haklarını
 * (gerçek-zamanlı AI, araştırma eklentisi, profiller) kaybediyordu; `currentPeriodEnd` okunmuyordu.
 * Saf işlevler (SAHTE YOK); saat yalnız `now` ile. Karşıt kollar: dönem bitti → yok · aktif → var · NULL → yok.
 */
import { allowedProfiles, donemSuruyor, hasRealtime, hasResearch, isActive, type Entitlement } from "@/config/entitlement";

const SIMDI = new Date("2026-11-19T12:00:00Z");
const plan = (ek: Partial<Entitlement>): Entitlement => ({
  tier: "pro_plus", status: "canceled", addons: ["research"], trialEndsAt: null, currentPeriodEnd: null, ...ek,
});

it.each(["canceled", "past_due"] as const)("KRİTİK: %s + ödenmiş dönem sürüyor → Pro+ hakları (gerçek-zamanlı, araştırma) KORUNUR", (status) => {
  const e = plan({ status, currentPeriodEnd: "2026-11-30T00:00:00+00:00" });
  expect(isActive(e, SIMDI)).toBe(true);
  expect(hasRealtime(e, SIMDI)).toBe(true);
  expect(hasResearch(e, SIMDI)).toBe(true);
  expect(allowedProfiles(e, SIMDI).length).toBeGreaterThan(0);
});

it.each(["canceled", "past_due"] as const)("KARŞIT: %s + dönem BİTTİ / NULL / bozuk → hak YOK", (status) => {
  for (const son of ["2026-11-19T11:59:59Z", "2026-11-19T12:00:00Z", null, "", "yarın"]) {
    const e = plan({ status, currentPeriodEnd: son });
    expect([son, isActive(e, SIMDI), hasRealtime(e, SIMDI), hasResearch(e, SIMDI)]).toEqual([son, false, false, false]);
  }
});

it("KARŞIT: aktif abonelik dönem sonu geçmiş olsa da etkin (yenileme bildirimi gecikebilir) · Pro da aynı kural", () => {
  expect(isActive(plan({ status: "active", currentPeriodEnd: "2026-01-01T00:00:00Z" }), SIMDI)).toBe(true);
  expect(isActive(plan({ tier: "pro", status: "canceled", currentPeriodEnd: "2026-11-20T00:00:00Z" }), SIMDI)).toBe(true);
  expect(isActive(plan({ tier: "pro", status: "canceled", currentPeriodEnd: "2026-11-18T00:00:00Z" }), SIMDI)).toBe(false);
});

it("Başlangıç katmanında dönem sonu hak VERMEZ (yalnız deneme kuralı)", () => {
  expect(isActive(plan({ tier: "baslangic", status: "canceled", currentPeriodEnd: "2026-12-30T00:00:00Z" }), SIMDI)).toBe(false);
});

it("donemSuruyor: sınır ve biçimler; `now` verilmezse gerçek saat", () => {
  expect(donemSuruyor(plan({ currentPeriodEnd: "2026-11-19T12:00:00.001Z" }), SIMDI)).toBe(true);
  expect(donemSuruyor(plan({ currentPeriodEnd: "2026-11-19T15:00:01+03:00" }), SIMDI)).toBe(true);
  expect(donemSuruyor(plan({ currentPeriodEnd: "2026-11-19T12:00:00Z" }), SIMDI)).toBe(false);
  const yarin = new Date(Date.now() + 864e5).toISOString();
  const dun = new Date(Date.now() - 864e5).toISOString();
  expect(donemSuruyor(plan({ currentPeriodEnd: yarin }))).toBe(true);
  expect(donemSuruyor(plan({ currentPeriodEnd: dun }))).toBe(false);
  expect(isActive(plan({ currentPeriodEnd: yarin }))).toBe(true);
});
