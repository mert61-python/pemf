import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useAuthModal } from '../context/AuthModal'
import { cancelSubscription } from '../lib/checkout'

/* Header hesap kontrolü: giriş yoksa "Giriş yap" (AuthModal); varsa "Aboneliğim" (iptal — iyzico'da
   hosted portal yok) + "Çıkış". Supabase yapılandırılmadıysa hiç gösterilmez. */
export default function AccountButton({ onNavigate }: { onNavigate?: () => void }) {
  const { session, email, signOut, ready } = useAuth()
  const { requireAuth } = useAuthModal()
  const [busy, setBusy] = useState(false)

  if (!ready) return null

  if (!session) {
    return (
      <button onClick={() => { requireAuth(); onNavigate?.() }} className="btn-ghost text-sm">
        Giriş yap
      </button>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={async () => {
          if (!window.confirm('Aboneliğinizi iptal etmek istiyor musunuz?')) return
          setBusy(true)
          const { ok, error } = await cancelSubscription()
          setBusy(false)
          window.alert(ok ? 'Aboneliğiniz iptal edildi.' : error || 'İptal edilemedi.')
        }}
        disabled={busy}
        className="btn-ghost text-sm disabled:opacity-60"
        title={email ?? undefined}
      >
        {busy ? '…' : 'Aboneliğim'}
      </button>
      <button onClick={() => signOut()} className="text-sm text-muted hover:text-fg" title="Çıkış yap">
        Çıkış
      </button>
    </div>
  )
}
