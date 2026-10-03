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
import { isAuthRetryableFetchError } from "@supabase/supabase-js";
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
  /** Y58: bu oturumda GERÇEK hak hiç öğrenilemedi (ilk açılış internetsiz) — `entitlement` yalnız yer tutucudur. */
  dogrulanamadi: boolean;
};

/** Y58: hak bilinmiyorken yeniden deneme aralığı — internet gelince gerçek hak kendiliğinden görünür. */
export const HAK_YENIDEN_DENEME_MS = 30_000;

const EntitlementContext = createContext<Ctx | undefined>(undefined);

/** Ağ/altyapı hatasında entitlement'i SIFIRLAMA sinyali (bkz. fetchEntitlement dönüşü). */
const UNKNOWN: unique symbol = Symbol("entitlement-unknown");
type FetchResult = Entitlement | typeof UNKNOWN;

async function fetchEntitlement(): Promise<FetchResult> {
  try {
    // ⚠️ D1.63 (B-6.7): supabase-js `getUser()` ağ hatasında FIRLATMAZ — `{data:{user:null}, error: AuthRetryableFetchError}`
    // DÖNER. Eskiden `!user` dalı bunu "kullanıcı yok" sayıp `defaultEntitlement()` dönüyordu: aşağıdaki `catch` (UNKNOWN)
    // gerçek istemcide HİÇ koşmuyordu, internetsiz açılışta ücretli kullanıcı "Başlangıç/deneme"ye düşüyordu (kapı da
    // fırlatan sahte getUser kullandığı için kördü). Açık RET (oturum yok / 401) yine varsayılandır.
    const {
      data: { user },
      error: kullaniciHatasi,
    } = await supabaseAuth.auth.getUser();
    if (kullaniciHatasi && isAuthRetryableFetchError(kullaniciHatasi)) return UNKNOWN;
    if (!user) return defaultEntitlement();
    const { data, error, status: httpDurum } = await supabaseAuth
      .from("subscriptions")
      .select("tier,status,addons,trial_ends_at,current_period_end")
      .eq("user_id", user.id)
      .maybeSingle();
    // postgrest-js istek reddini (ağ) `status: 0` ile döndürür — o da "bilinmiyor"dur, abonelik satırı YOK değil.
    if (error && httpDurum === 0) return UNKNOWN;
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
  // ⚠️ Y58 (sahip, S-E5): ilk açılış internetsizse ve bilinen son hak YOKSA rozet "abonelik doğrulanamadı (internet yok)"
  // der; "Başlangıç"/deneme gösterilmez, `X-PEMF-Tier` gönderilmez, cihaza hiçbir şey YAZILMAZ (profil kalıcılığı geri
  // eklenmez — Ö.4). Bilinen hak varsa (D1.63) o korunur ve bu bayrak kalkmaz.
  const [dogrulanamadi, setDogrulanamadi] = useState(false);
  const bilinenRef = useRef(false);

  // NESİL SAYACI: uçuştaki bir refresh, kullanıcı ÇIKIŞ yaptıktan (veya hesap değiştirdikten) sonra
  // çözülürse önceki kullanıcının tier'ını ve X-PEMF-Tier header'ını GERİ YÜKLÜYORDU — yani B
  // kullanıcısı, A'nın abonelik hakkıyla istek atabiliyordu. Her etki bir nesil alır; nesil
  // değiştiyse sonuç YOK SAYILIR.
  const genRef = useRef(0);
  // D1.63 · D1.87 (A-70): çevrimdışı açılan oturumun (launcher devri, Supabase'e ulaşılamadı) hakkı SORGULANMAZ — supabase-js'te
  // oturum kurulamadığı için `getUser` "oturum yok" (açık ret gibi) döner ve hak varsayılana düşerdi. Bilinen SON hak korunur.
  const cevrimdisiRef = useRef(false);
  cevrimdisiRef.current = !!session?.cevrimdisi;

  const refresh = useCallback(async () => {
    const gen = ++genRef.current;
    setLoading(true);
    const e = cevrimdisiRef.current ? UNKNOWN : await fetchEntitlement();
    if (gen !== genRef.current) return; // bayat sonuç — oturum değişti
    const eff = e === UNKNOWN ? null : e;
    if (eff) {
      bilinenRef.current = true;
      setDogrulanamadi(false);
      setEntitlement(eff);
      setEntitlementHeaders(eff.tier, [...eff.addons]); // apiClient AI isteklerinde X-PEMF-Tier/Addons yollasın
    } else if (!bilinenRef.current) {
      setDogrulanamadi(true); // Y58: yer tutucu hak GÖSTERİLMEZ, başlık YOLLANMAZ
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
      bilinenRef.current = false;
      setDogrulanamadi(false);
      setEntitlement(defaultEntitlement());
      setEntitlementHeaders(null);
      setAuthBearer(null);
      setLoading(false);
    }
  }, [session, refresh]);

  // Y58: hak bilinmiyorken periyodik yeniden deneme (oturum nesnesi değişmeden internet geri gelebilir).
  useEffect(() => {
    if (!session || !dogrulanamadi) return undefined;
    const t = setInterval(() => {
      void refresh();
    }, HAK_YENIDEN_DENEME_MS);
    return () => clearInterval(t);
  }, [session, dogrulanamadi, refresh]);

  const value = useMemo(
    () => ({ entitlement, loading, refresh, dogrulanamadi }),
    [entitlement, loading, refresh, dogrulanamadi]
  );
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
    dogrulanamadi: ctx.dogrulanamadi,
    active: isActive(e, now),
    trialing: isTrialActive(e, now),
    trialDaysLeft: trialDaysLeft(e, now),
    realtime: hasRealtime(e, now),
    research: hasResearch(e, now),
    allowedProfiles: allowedProfiles(e, now),
  };
}
