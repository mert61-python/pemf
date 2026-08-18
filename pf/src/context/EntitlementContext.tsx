// Author: mertaygn, cglrgrkn
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
  useRef,
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

/** Ağ/altyapı hatasında entitlement'i SIFIRLAMA sinyali (bkz. fetchEntitlement dönüşü). */
const UNKNOWN: unique symbol = Symbol("entitlement-unknown");
type FetchResult = Entitlement | typeof UNKNOWN;

async function fetchEntitlement(): Promise<FetchResult> {
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
    // Ağ/altyapı hatası → BİLİNMİYOR. Eskiden burada `defaultEntitlement()` dönülüyordu: internetsiz
    // klinikte (cihaz LAN'ında, Supabase erişilemezken) ücretli kullanıcının hakkı her açılışta
    // "Başlangıç · 14 gün deneme"ye düşüyor, üstelik deneme SIFIRDAN başladığı için rozet sürekli
    // "14 gün kaldı" gösteriyordu. Artık bilinen SON durum korunur.
    return UNKNOWN;
  }
}

export function EntitlementProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [entitlement, setEntitlement] = useState<Entitlement>(defaultEntitlement());
  const [loading, setLoading] = useState(true);

  // NESİL SAYACI: uçuştaki bir refresh, kullanıcı ÇIKIŞ yaptıktan (veya hesap değiştirdikten) sonra
  // çözülürse önceki kullanıcının tier'ını ve X-PEMF-Tier header'ını GERİ YÜKLÜYORDU — yani B
  // kullanıcısı, A'nın abonelik hakkıyla istek atabiliyordu. Her etki bir nesil alır; nesil
  // değiştiyse sonuç YOK SAYILIR.
  const genRef = useRef(0);

  const refresh = useCallback(async () => {
    const gen = ++genRef.current;
    setLoading(true);
    const e = await fetchEntitlement();
    if (gen !== genRef.current) return; // bayat sonuç — oturum değişti
    const eff = e === UNKNOWN ? null : e;
    if (eff) {
      setEntitlement(eff);
      setEntitlementHeaders(eff.tier, [...eff.addons]); // apiClient AI isteklerinde X-PEMF-Tier/Addons yollasın
    }
    // Backend Supabase-doğrulaması için erişim JWT'si (spoof-proof tier). Enforce kapalıyken zararsız.
    try {
      const { data } = await supabaseAuth.auth.getSession();
      if (gen !== genRef.current) return;
      setAuthBearer(data.session?.access_token ?? null);
    } catch {
      if (gen !== genRef.current) return;
      setAuthBearer(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (session) {
      refresh();
    } else {
      genRef.current++; // uçuştaki refresh'i geçersiz kıl (önceki kullanıcının hakkı geri gelmesin)
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
