/**
 * AuthContext — operatör oturumu (Supabase Auth: e-posta/şifre + doğrulama). Giriş yapılmadan
 * uygulamaya girilemez. Oturum supabase-js ile KALICI (her açılışta tekrar giriş YOK); profil seçimi
 * yine her açılış (bilinçli). `isResearch` = e-posta `.edu` → WelcomeScreen araştırma-modu kartı.
 * Giriş/çıkış/doğrulama-sonrası değişimleri `onAuthStateChange` ile otomatik yansır.
 */
import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { AuthSession, isResearchEmail } from "@/services/authApi";
import { supabaseAuth, getCurrentSession, signOutUser } from "@/services/supabaseAuth";

interface AuthContextValue {
  session: AuthSession | null;
  loading: boolean;       // saklı oturum kontrol edilirken (ilk açılış)
  isResearch: boolean;    // e-posta .edu → araştırma modu görünür
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

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

  useEffect(() => {
    let alive = true;
    // İlk açılış: saklı oturumu yükle.
    getCurrentSession().then((s) => {
      if (!alive) return;
      setSession(toAuthSession(s));
      setLoading(false);
    });
    // Oturum değişimlerini dinle: giriş / çıkış / token-yenileme / doğrulama-sonrası.
    const { data: sub } = supabaseAuth.auth.onAuthStateChange((_event, s) => {
      setSession(toAuthSession(s));
      setLoading(false);
    });
    return () => {
      alive = false;
      sub?.subscription?.unsubscribe();
    };
  }, []);

  const logout = useCallback(async () => {
    await signOutUser(); // → onAuthStateChange oturumu null'lar
    setSession(null);
  }, []);

  const isResearch = !!session && isResearchEmail(session.email);

  const value = useMemo(
    () => ({ session, loading, isResearch, logout }),
    [session, loading, isResearch, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
