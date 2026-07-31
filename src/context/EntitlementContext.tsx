/**
 * EntitlementContext — kullanıcının abonelik hakkını (tier/eklenti/deneme) Supabase'den okur
 * ve uygulamaya sağlar (A1: mobil satmaz, yalnız okur). `subscriptions` tablosu/satırı yoksa
 * → 14 günlük deneme varsayılanı (graceful; tablo canlı olmadan da app çalışır).
 */
import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  ReactNode,
} from "react";
import { supabaseAuth } from "@/services/supabaseAuth";
import { setEntitlementHeaders, setAuthBearer } from "@/services/apiClient";
import { useAuth } from "@/context/AuthContext";
import {
  Entitlement,
  defaultEntitlement,
  Tier,
  SubStatus,
  Addon,
  isActive,
  isTrialActive,
  trialDaysLeft,
  hasRealtime,
  hasResearch,
  allowedProfiles,
} from "@/config/entitlement";

type Ctx = {
  entitlement: Entitlement;
  loading: boolean;
  refresh: () => Promise<void>;
};

const EntitlementContext = createContext<Ctx | undefined>(undefined);

async function fetchEntitlement(): Promise<Entitlement> {
  try {
    const {
      data: { user },
    } = await supabaseAuth.auth.getUser();
    if (!user) return defaultEntitlement();
    const { data, error } = await supabaseAuth
      .from("subscriptions")
      .select("tier,status,addons,trial_ends_at,current_period_end")
      .eq("user_id", user.id)
      .maybeSingle();
    if (error || !data) return defaultEntitlement(user.created_at);
    // Şekil doğrula (backend gibi savunmacı): bilinmeyen tier/status → güvenli varsayılan;
    // addons dizi değilse [] (aksi halde [...e.addons] / includes çökerdi).
    const validTiers: Tier[] = ["baslangic", "pro", "pro_plus"];
    const validStatus: SubStatus[] = ["trialing", "active", "past_due", "canceled"];
    const tier: Tier = validTiers.includes(data.tier as Tier) ? (data.tier as Tier) : "baslangic";
    const status: SubStatus = validStatus.includes(data.status as SubStatus)
      ? (data.status as SubStatus)
      : "trialing";
    const addons: Addon[] = Array.isArray(data.addons)
      ? data.addons.filter((a: unknown): a is Addon => a === "research")
      : [];
    return {
      tier,
      status,
      addons,
      trialEndsAt: data.trial_ends_at ?? defaultEntitlement(user.created_at).trialEndsAt,
      currentPeriodEnd: data.current_period_end ?? null,
    };
  } catch {
    // Tablo yok / ağ hatası → deneme varsayılanı (app'i bloke etme).
    return defaultEntitlement();
  }
}

export function EntitlementProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [entitlement, setEntitlement] = useState<Entitlement>(defaultEntitlement());
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    const e = await fetchEntitlement();
    setEntitlement(e);
    setEntitlementHeaders(e.tier, [...e.addons]); // apiClient AI isteklerinde X-PEMF-Tier/Addons yollasın
    // Backend Supabase-doğrulaması için erişim JWT'si (spoof-proof tier). Enforce kapalıyken zararsız.
    try {
      const { data } = await supabaseAuth.auth.getSession();
      setAuthBearer(data.session?.access_token ?? null);
    } catch {
      setAuthBearer(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (session) {
      refresh();
    } else {
      setEntitlement(defaultEntitlement());
      setEntitlementHeaders(null);
      setAuthBearer(null);
      setLoading(false);
    }
  }, [session, refresh]);

  const value = useMemo(() => ({ entitlement, loading, refresh }), [entitlement, loading, refresh]);
  return <EntitlementContext.Provider value={value}>{children}</EntitlementContext.Provider>;
}

/** Entitlement + türetilmiş kolaylıklar (aktif/deneme/real-time/research/izinli-profiller). */
export function useEntitlement() {
  const ctx = useContext(EntitlementContext);
  if (!ctx) throw new Error("useEntitlement must be used within EntitlementProvider");
  const now = new Date();
  const e = ctx.entitlement;
  return {
    ...ctx,
    tier: e.tier,
    active: isActive(e, now),
    trialing: isTrialActive(e, now),
    trialDaysLeft: trialDaysLeft(e, now),
    realtime: hasRealtime(e, now),
    research: hasResearch(e, now),
    allowedProfiles: allowedProfiles(e, now),
  };
}
