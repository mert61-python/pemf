/**
 * KP-8 · src/config/entitlement.ts kalan dallar — saf karar işlevleri (SAHTE YOK; saat yalnız `now` ile verilir ya da gerçek saat):
 *  - `now` verilmezse GERÇEK saat kullanılır: deneme bugünden 14 gün sonra biterse etkin + kalan gün 14; geçmişte bittiyse etkin DEĞİL.
 *  - Pro / Pro+ abonelik "deneme" (trialing) durumundayken de etkindir (ödeme sağlayıcısının deneme süresi); iptal / gecikmede değil.
 *  - Sert kapı (ENTITLEMENT_ENFORCED) KAPALIYKEN (sahada) bitmiş denemede bile her profil / özellik İZİNLİ. (Bayrak modül İÇİNDEN
 *    yerel sabit olarak okunur — testte açılamaz; açık kol Y279 etiketiyle ULAŞILAMAZ.)
 */
import {
  ENTITLEMENT_ENFORCED,
  allowedProfiles,
  canUseProfile,
  defaultEntitlement,
  gateFeature,
  gateProfile,
  hasRealtime,
  hasResearch,
  isActive,
  isTrialActive,
  trialDaysLeft,
  type Entitlement,
} from "@/config/entitlement";

const plan = (ek: Partial<Entitlement>): Entitlement => ({
  tier: "pro", status: "active", addons: [], trialEndsAt: null, currentPeriodEnd: null, ...ek,
});

it("`now` verilmezse gerçek saat: bugün açılan hesabın denemesi etkin, 14 gün; geçmişte biten deneme etkin değil", () => {
  const taze = defaultEntitlement(new Date().toISOString());
  expect(isTrialActive(taze)).toBe(true);
  expect(trialDaysLeft(taze)).toBe(14);
  expect(isActive(taze)).toBe(true);
  expect(allowedProfiles(taze)).toEqual(["pet_owner", "veterinarian"]);
  const eski = defaultEntitlement("2020-01-01T00:00:00Z");
  expect(isTrialActive(eski)).toBe(false);
  expect(isActive(eski)).toBe(false);
  expect(canUseProfile(eski, "veterinarian")).toBe(false);
  expect(allowedProfiles(eski)).toEqual([]);
});

it("Pro / Pro+ 'deneme' durumunda etkin; iptal / gecikmede değil · Pro+ gerçek zamanlı, araştırma eki araştırmacıyı açar", () => {
  expect(isActive(plan({ status: "trialing" }))).toBe(true);
  expect(isActive(plan({ tier: "pro_plus", status: "trialing" }))).toBe(true);
  expect(isActive(plan({ status: "canceled" }))).toBe(false);
  expect(isActive(plan({ status: "past_due" }))).toBe(false);
  expect(hasRealtime(plan({ tier: "pro_plus", status: "trialing" }))).toBe(true);
  expect(hasRealtime(plan({ tier: "pro" }))).toBe(false);
  expect(hasResearch(plan({ addons: ["research"] }))).toBe(true);
  expect(canUseProfile(plan({ addons: ["research"] }), "researcher")).toBe(true);
  expect(canUseProfile(plan({}), "researcher")).toBe(false);
});

it("sert kapı KAPALI (saha): bitmiş denemede bile her profil / özellik İZİNLİ", () => {
  const bitmis = defaultEntitlement("2020-01-01T00:00:00Z");
  expect(ENTITLEMENT_ENFORCED).toBe(false);
  for (const p of ["pet_owner", "veterinarian", "researcher"] as const) expect(gateProfile(bitmis, p)).toBe(true);
  expect(gateFeature(bitmis, "realtime")).toBe(true);
  expect(gateFeature(bitmis, "research")).toBe(true);
});
