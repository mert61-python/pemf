// Author: mertaygn, cglrgrkn
/**
 * AuthContext — operatör oturumu (Supabase Auth: e-posta/şifre + doğrulama). Giriş yapılmadan
 * uygulamaya girilemez. Oturum supabase-js ile KALICI (her açılışta tekrar giriş YOK); profil seçimi
 * yine her açılış (bilinçli). `isResearch` = e-posta `.edu` → WelcomeScreen araştırma-modu kartı.
 * Giriş/çıkış/doğrulama-sonrası değişimleri `onAuthStateChange` ile otomatik yansır.
 *
 * 2026-08-06 — MASAÜSTÜ OTURUM DEVRİ: masaüstü client (Tauri) Supabase'e giriş yapıp oturumu
 * backend'e devrettiğinde uygulama açılışta onu devralır ve login ekranını ATLAR (çift giriş yok).
 * Devir yoksa/başarısızsa AKIŞ DEĞİŞMEZ — sessizce normal login gösterilir. Bkz. services/desktopSession.
 */
import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { AuthSession, isResearchEmail } from "@/services/authApi";
import { supabaseAuth, getCurrentSession, signOutUser } from "@/services/supabaseAuth";
import { isDesktopHost, hydrateFromDesktopSession, clearDesktopSession } from "@/services/desktopSession";

interface AuthContextValue {
  session: AuthSession | null;
  loading: boolean;       // saklı oturum kontrol edilirken VE masaüstü devri denenirken (ilk açılış)
  isResearch: boolean;    // e-posta .edu → araştırma modu görünür
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/**
 * Açılış splash'inin TAVANI (ms) — `hydrating` bu süreden uzun sürerse zorla kapatılır.
 *
 * NEDEN GEREKLİ (denetim 2026-08-06): `hydrating` yalnız aşağıdaki akışın SONUNDA sıfırlanıyordu,
 * o akışın son adımı ise `getCurrentSession()`. supabase-js tüm oturum işlemlerini TEK bir iç
 * kilitle sıraya alır ve devrin `setSession`'ı o kilidi tutarken Supabase'e ağ çağrısı yapar —
 * supabase-js'te bu çağrının ZAMAN AŞIMI YOKTUR. Yarı-açık tünel / captive portal / DNS asılması
 * durumunda `setSession` dakikalarca asılı kalır, `getCurrentSession()` kilidin arkasında bekler
 * ve `hydrating` HİÇ kapanmaz. `DESKTOP_SESSION_BUDGET_MS` yalnız BEKLENEN sonucu sınırlar, arka
 * planda süren çağrıyı değil → tek başına yetmiyordu.
 * Sonuç eskiden: masaüstünde açılış donmuş bir spinner'da kalıyor, operatör uygulamaya —
 * dolayısıyla içindeki ACİL DURDUR'a — hiç giremiyordu. Tavan dolunca splash'ten ÇIKILIR
 * (eski davranış: login ya da saklı oturumla uygulama). Geç gelen devir KAYBOLMAZ: `setSession`
 * tamamlanınca `onAuthStateChange` kullanıcıyı zaten içeri alır.
 *
 * Sabit BİLEREK burada tanımlı (desktopSession'dan import EDİLMEZ): o modül testlerde tümüyle
 * mock'lanıyor, oradan gelen bir süre `undefined` olur ve setTimeout'u sessizce 0 ms'ye düşürürdü.
 */
const HYDRATE_SPLASH_CEILING_MS = 6000;

function toAuthSession(s: Session | null): AuthSession | null {
  if (!s || !s.user?.email) return null;
  // Kayıtta girilen veteriner/klinik profili user_metadata'da → session'a taşı (uygulama her yerden okur).
  const m = (s.user.user_metadata || {}) as Record<string, string>;
  return {
    email: s.user.email,
    token: s.access_token || "",
    profile: {
      first_name: m.first_name || "",
      last_name: m.last_name || "",
      full_name: m.full_name || "",
      title: m.title || "",
      phone: m.phone || "",
      clinic_name: m.clinic_name || "",
      clinic_phone: m.clinic_phone || "",
      city: m.city || "",
      district: m.district || "",
      address: m.address || "",
    },
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);
  // MASAÜSTÜ OTURUM DEVRİ (2026-08-06): client Supabase ile giriş yapıp oturumu backend'e devreder;
  // burada devralınır ve login ekranı ATLANIR (çift giriş yok). Devir denenirken AuthGate SPLASH'te
  // kalmalı: `loading` tek başına yetmez, çünkü onAuthStateChange abone olur olmaz INITIAL_SESSION
  // yayınlar → loading false olur ve devir bitmeden AuthScreen bir an "yanıp" çift-giriş hissi verir.
  const [hydrating, setHydrating] = useState(() => isDesktopHost());

  useEffect(() => {
    let alive = true;
    // Splash TAVANI — bkz. HYDRATE_SPLASH_CEILING_MS: devir/oturum-okuma asılı kalsa da açılış
    // sonsuza dek spinner'da kilitlenmesin (ACİL DURDUR uygulamanın İÇİNDE yaşıyor).
    const tavan = setTimeout(() => { if (alive) setHydrating(false); }, HYDRATE_SPLASH_CEILING_MS);
    // ÖNCE abone ol: hidrasyonun tetikleyeceği setSession olayı KAÇMASIN.
    const { data: sub } = supabaseAuth.auth.onAuthStateChange((_event, s) => {
      setSession(toAuthSession(s));
      setLoading(false);
    });
    (async () => {
      // Masaüstü devri (yalnız client'ın açtığı loopback sayfada). Uç yoksa / boş dönerse /
      // hata verirse NORMALDİR → sessizce mevcut login akışına düşülür (kullanıcı hata görmez).
      if (isDesktopHost()) {
        try {
          await hydrateFromDesktopSession();
        } catch {
          /* sessiz — normal login */
        }
      }
      // Sonra saklı/devralınmış oturumu oku (ilk açılış).
      const s = await getCurrentSession();
      if (!alive) return;
      setSession(toAuthSession(s));
      setLoading(false);
      setHydrating(false);
    })();
    return () => {
      alive = false;
      clearTimeout(tavan);
      sub?.subscription?.unsubscribe();
    };
  }, []);

  const logout = useCallback(async () => {
    // ÖNCE backend'in bellekteki devir oturumunu sil: aksi halde sayfa yenilenince uygulama
    // kendini tekrar hydrate eder ve masaüstünde çıkış İŞLEMEZ. En-iyi-çaba (hata yutulur).
    await clearDesktopSession();
    await signOutUser(); // → onAuthStateChange oturumu null'lar
    setSession(null);
  }, []);

  const isResearch = !!session && isResearchEmail(session.email);

  // Devir sürerken de "yükleniyor" say → AuthGate splash'te kalır, login ekranı yanıp sönmez.
  const busy = loading || hydrating;

  const value = useMemo(
    () => ({ session, loading: busy, isResearch, logout }),
    [session, busy, isResearch, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
