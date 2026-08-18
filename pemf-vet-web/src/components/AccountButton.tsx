// Author: mertaygn, cglrgrkn
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
      {/* Buton eskiden "Aboneliğim" yazıyordu — kullanıcı abonelik bilgilerini GÖRECEĞİNİ sanıp
          tıklıyor, karşısına doğrudan iptal onayı çıkıyordu. Yıkıcı eylemin adı, yaptığı iş olmalı.
          Onay metni de sonucu net söylüyor (yenileme durur, dönem sonuna kadar erişim sürer). */}
      <button
        onClick={async () => {
          if (
            !window.confirm(
              'Aboneliğinizi iptal etmek istiyor musunuz?\n\n' +
                'Otomatik yenileme durdurulur. Bedeli tahsil edilmiş dönemin sonuna kadar erişiminiz devam eder.'
            )
          )
            return
          setBusy(true)
          const { ok, error } = await cancelSubscription()
          setBusy(false)
          window.alert(ok ? 'Aboneliğiniz iptal edildi. Dönem sonuna kadar erişiminiz sürüyor.' : error || 'İptal edilemedi.')
        }}
        disabled={busy}
        className="btn-ghost text-sm disabled:opacity-60"
        title={email ?? undefined}
      >
        {busy ? '…' : 'Aboneliği iptal et'}
      </button>
      <button onClick={() => signOut()} className="text-sm text-muted hover:text-fg" title="Çıkış yap">
        Çıkış
      </button>
    </div>
  )
}
