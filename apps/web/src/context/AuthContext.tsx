// Author: mertaygn, cglrgrkn
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase, supabaseReady } from '../lib/supabase'
// Metin denetimi 2026-08-20: Supabase'in HAM INGILIZCE mesajlari ('Invalid login credentials')
// dogrudan ekrana basiliyordu; hata mesajinin isi kullaniciya NE YAPACAGINI soylemektir.
import { authHatasiTurkce } from '../lib/authHatalari'

type AuthCtx = {
  session: Session | null
  loading: boolean
  ready: boolean
  email: string | null
  signIn: (email: string, password: string) => Promise<{ error?: string }>
  signUp: (
    email: string,
    password: string,
    meta?: Record<string, unknown>,
  ) => Promise<{ error?: string; needConfirm?: boolean }>
  resetPassword: (email: string) => Promise<{ error?: string }>
  signOut: () => Promise<void>
}

const Ctx = createContext<AuthCtx | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!supabaseReady) {
      setLoading(false)
      return
    }
    // .catch: getSession reddedilirse `loading` sonsuza dek true kalıyordu.
    supabase.auth
      .getSession()
      .then(({ data }) => setSession(data.session))
      .catch(() => setSession(null))
      .finally(() => setLoading(false))
    // TOKEN_REFRESHED dahil tüm oturum değişimlerinde session tazelenir.
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  const value: AuthCtx = {
    session,
    loading,
    ready: supabaseReady,
    email: session?.user?.email ?? null,
    signIn: async (email, password) => {
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      return { error: error ? authHatasiTurkce(error.message) : undefined }
    },
    signUp: async (email, password, meta) => {
      // Rol + profil bilgileri Supabase user_metadata'ya (raw_user_meta_data) yazılır.
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: meta ? { data: meta } : undefined,
      })
      return { error: error ? authHatasiTurkce(error.message) : undefined, needConfirm: !data.session }
    },
    resetPassword: async (email) => {
      // `redirectTo` ZORUNLU: verilmezse Supabase Site URL'ine (mobil uygulamanın GitHub Pages
      // sayfasına) yönlenir ve web kullanıcısı şifresini hiç belirleyemezdi.
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/sifre-sifirla`,
      })
      return { error: error ? authHatasiTurkce(error.message) : undefined }
    },
    signOut: async () => {
      // ⚠️ KAPSAM 'local' (denetim 2026-08-18): supabase-js v2'de `signOut()` varsayılanı
      // `scope: 'global'`dir ve kullanıcının TÜM yenileme jetonlarını iptal eder. Yani
      // pazarlama sitesindeki "Çıkış" düğmesi, aynı hesapla açık olan MOBİL uygulamanın ve
      // klinikteki masaüstü launcher'ın (1.9.9'dan beri Supabase girişi var) oturumlarını da
      // düşürüyordu — kullanıcı bunu istemiyor ve sebebini de göremiyor. Site oturumu yalnız
      // bu tarayıcıda kapanmalı.
      await supabase.auth.signOut({ scope: 'local' })
    },
  }

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth must be used within AuthProvider')
  return c
}
