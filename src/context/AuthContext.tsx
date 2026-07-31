import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase, supabaseReady } from '../lib/supabase'

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
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
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
      return { error: error?.message }
    },
    signUp: async (email, password, meta) => {
      // Rol + profil bilgileri Supabase user_metadata'ya (raw_user_meta_data) yazılır.
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: meta ? { data: meta } : undefined,
      })
      return { error: error?.message, needConfirm: !data.session }
    },
    resetPassword: async (email) => {
      const { error } = await supabase.auth.resetPasswordForEmail(email)
      return { error: error?.message }
    },
    signOut: async () => {
      await supabase.auth.signOut()
    },
  }

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth must be used within AuthProvider')
  return c
}
