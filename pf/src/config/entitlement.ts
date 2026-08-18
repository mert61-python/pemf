// Author: mertaygn, cglrgrkn
/**
 * Entitlement (abonelik hakkı) — A1 modeli: abonelik WEB'de satılır (Stripe), mobil yalnız
 * hakkı OKUR ve özellik açar (reader model, IAP YOK). Tek-kaynak Supabase `subscriptions`.
 *
 * Katmanlar:
 *  - tier: baslangic (14g deneme) | pro (kuyruk) | pro_plus (real-time)
 *  - addons: ör. 'research' (Araştırma modeli — ücretli eklenti; Pro/Pro+ üstüne)
 *  - status/trial: aktiflik + deneme bitişi
 *
 * ⚠️ ENTITLEMENT_ENFORCED (şu an FALSE — açık-erişim KASITLI, ödeme öncesi): dikkat, bu bayrağı
 *    TRUE yapmak TEK BAŞINA hiçbir şeyi KİLİTLEMEZ. gateProfile/gateFeature şu an HİÇBİR yerde
 *    tüketilmiyor (WelcomeScreen profilleri installedModes ile filtreler, entitlement ile DEĞİL) →
 *    bayrak inert. GERÇEK enforcement BACKEND-otoriter (Supabase `subscriptions` + tier-header
 *    doğrulaması, spoof-proof). İstemci-kilidi istenirse ÖNCE gateProfile'ı WelcomeScreen profil
 *    onPress'ine + gateFeature'ı AiHub modül-açma/autoAdjust'a BAĞLANMALI, sonra bayrak açılmalı.
 */
import type { UserMode } from "@/context/UserModeContext";

export const ENTITLEMENT_ENFORCED = false;

export type Tier = "baslangic" | "pro" | "pro_plus";
export type SubStatus = "trialing" | "active" | "past_due" | "canceled";
export type Addon = "research";
export type Profile = Exclude<UserMode, null>;

export type Entitlement = {
  tier: Tier;
  status: SubStatus;
  addons: Addon[];
  trialEndsAt: string | null; // ISO — baslangic denemesi için
  currentPeriodEnd: string | null;
};

export const TRIAL_DAYS = 14;
export const TIER_LABEL: Record<Tier, string> = {
  baslangic: "Başlangıç",
  pro: "Pro",
  pro_plus: "Pro+",
};

/** Abonelik satırı yoksa varsayılan: 14 günlük deneme (hesap oluşturma anından). */
export function defaultEntitlement(accountCreatedAt?: string | null): Entitlement {
  let start = accountCreatedAt ? new Date(accountCreatedAt) : new Date();
  if (Number.isNaN(start.getTime())) start = new Date(); // bozuk tarih → şimdi (toISOString çökmesin)
  const end = new Date(start.getTime() + TRIAL_DAYS * 864e5);
  return {
    tier: "baslangic",
    status: "trialing",
    addons: [],
    trialEndsAt: end.toISOString(),
    currentPeriodEnd: null,
  };
}

export function isTrialActive(e: Entitlement, now: Date = new Date()): boolean {
  return (
    e.tier === "baslangic" &&
    e.status === "trialing" &&
    !!e.trialEndsAt &&
    now < new Date(e.trialEndsAt)
  );
}

export function trialDaysLeft(e: Entitlement, now: Date = new Date()): number {
  if (!e.trialEndsAt) return 0;
  const end = new Date(e.trialEndsAt).getTime();
  if (Number.isNaN(end)) return 0; // bozuk tarih → "NaN gün" gösterme
  return Math.max(0, Math.ceil((end - now.getTime()) / 864e5));
}

/** Aktif mi (ücretli-aktif veya deneme-içi)? Değilse hak kapalı (yükseltme gerekir). */
export function isActive(e: Entitlement, now: Date = new Date()): boolean {
  if (e.tier === "pro" || e.tier === "pro_plus") {
    return e.status === "active" || e.status === "trialing";
  }
  return isTrialActive(e, now); // baslangic
}

/** Pro+ → gerçek-zamanlı AI (kuyruksuz). Pro/Başlangıç → kuyruklu. */
export function hasRealtime(e: Entitlement, now: Date = new Date()): boolean {
  return e.tier === "pro_plus" && isActive(e, now);
}

/** Araştırma modelleri: 'research' eklentisi gerekir (deneme DAHİL DEĞİL — backend require_research
 *  ile hizalı; aksi halde denemede kilitsiz görünüp her çağrı 402 alırdı). */
export function hasResearch(e: Entitlement, now: Date = new Date()): boolean {
  return isActive(e, now) && e.addons.includes("research");
}

/** Profil bu entitlement ile kullanılabilir mi (mantık — sert-gating ENTITLEMENT_ENFORCED'e bağlı). */
export function canUseProfile(e: Entitlement, profile: Profile, now: Date = new Date()): boolean {
  if (!isActive(e, now)) return false;
  if (profile === "researcher") return hasResearch(e, now);
  return true; // pet_owner / veterinarian → aktif abonelik/deneme yeter
}

export function allowedProfiles(e: Entitlement, now: Date = new Date()): Profile[] {
  return (["pet_owner", "veterinarian", "researcher"] as Profile[]).filter((p) =>
    canUseProfile(e, p, now),
  );
}

/** Sert-gating kararı: enforced kapalıyken HER ZAMAN izinli (UI yalnız rozet gösterir). */
export function gateProfile(e: Entitlement, profile: Profile, now: Date = new Date()): boolean {
  return ENTITLEMENT_ENFORCED ? canUseProfile(e, profile, now) : true;
}
export function gateFeature(
  e: Entitlement,
  feature: "realtime" | "research",
  now: Date = new Date(),
): boolean {
  const has = feature === "realtime" ? hasRealtime(e, now) : hasResearch(e, now);
  return ENTITLEMENT_ENFORCED ? has : true;
}
