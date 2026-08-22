// Author: mertaygn, cglrgrkn
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useAuthModal } from '../context/AuthModal'
import { cancelSubscription } from '../lib/checkout'
import { FREE_MODE } from '../config'
import { odemeHatasiTurkce } from '../lib/authHatalari'
import { jetonBakiyesiniOku, type JetonBakiyesi } from '../lib/jeton'

/* Header hesap kontrolü: giriş yoksa "Giriş yap" (AuthModal); varsa hesap menüsü.
   Supabase yapılandırılmadıysa hiç gösterilmez.

   METİN DENETİMİ 2026-08-20 — bu bileşende iki sorun ölçülmüştü:
     1. Abonelik iptali TARAYICI `window.confirm`/`window.alert` kutularıyla yürütülüyordu:
        para/abonelik gibi kritik bir adımda sitenin görsel dili ve tonu tamamen kayboluyor,
        üstelik hata metni (iyzico'nun ham mesajı) da aynı kutuda çıkıyordu.
     2. Giriş yapan kullanıcı hesabıyla ilgili HİÇBİR ŞEY göremiyordu — hangi e-postayla
        girdiği bile yalnız `title` ipucundaydı (dokunmatik cihazda görünmez).

   ⚠️ BİLEREK YOK: plan adı / yenileme tarihi / fatura. `subscriptions.current_period_end`
   alanına bu depoda HİÇBİR yol değer yazmıyor (bkz. api/cancel.ts içindeki ölçüm notu) →
   tarih göstermek uydurma veri olurdu. Satış açılınca gerçek "Hesabım" sayfası ayrı iş. */
export default function AccountButton({ onNavigate }: { onNavigate?: () => void }) {
  const { session, email, signOut, ready } = useAuth()
  const { requireAuth } = useAuthModal()
  const [acik, setAcik] = useState(false)
  const [onay, setOnay] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sonuc, setSonuc] = useState<{ ok: boolean; mesaj: string } | null>(null)
  const [jeton, setJeton] = useState<JetonBakiyesi | null>(null)
  const kutu = useRef<HTMLDivElement>(null)

  // Dışarı tıklayınca / Esc ile kapan (menü açıkken sayfada gezinmeyi engellemesin).
  // Menü AÇILDIĞINDA bakiyeyi çek (her sayfa yüklemesinde değil — gereksiz istek olmasın).
  useEffect(() => {
    if (!acik) return
    void jetonBakiyesiniOku().then(setJeton)
  }, [acik])

  useEffect(() => {
    if (!acik) return
    const tikla = (e: MouseEvent) => {
      if (kutu.current && !kutu.current.contains(e.target as Node)) setAcik(false)
    }
    const tus = (e: KeyboardEvent) => { if (e.key === 'Escape') setAcik(false) }
    document.addEventListener('mousedown', tikla)
    document.addEventListener('keydown', tus)
    return () => {
      document.removeEventListener('mousedown', tikla)
      document.removeEventListener('keydown', tus)
    }
  }, [acik])

  if (!ready) return null

  if (!session) {
    return (
      <button onClick={() => { requireAuth(); onNavigate?.() }} className="btn-ghost text-sm">
        Giriş yap
      </button>
    )
  }

  async function iptalEt() {
    setBusy(true)
    const { ok, error } = await cancelSubscription()
    setBusy(false)
    setOnay(false)
    setSonuc({
      ok: !!ok,
      mesaj: ok
        ? 'Aboneliğiniz iptal edildi; otomatik yenileme durduruldu.'
        : odemeHatasiTurkce(error),
    })
  }

  return (
    <div className="relative" ref={kutu}>
      <button
        onClick={() => { setAcik((v) => !v); setSonuc(null) }}
        className="btn-ghost text-sm"
        aria-haspopup="menu"
        aria-expanded={acik}
      >
        Hesabım
      </button>

      {acik && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-72 rounded-xl border border-border bg-bg p-4 text-left shadow-xl"
        >
          <div className="text-xs text-muted">Giriş yapıldı</div>
          <div className="mt-0.5 truncate text-sm font-medium" title={email ?? undefined}>{email}</div>

          {/* JETON BAKİYESİ (7. parti): kullanıcı kalan analiz hakkını buradan görür.
              Okunamazsa HİÇ gösterilmez — yanlış sayı göstermektense boş bırakmak (DownloadStats
              ile aynı ilke). Aylık hak devretmez, satın alınan süresizdir; ikisi ayrı yazılır ki
              kullanıcı hangisinin ay sonunda sıfırlanacağını bilsin. */}
          {jeton && (
            <div className="mt-3 rounded-lg border border-primary/30 bg-primary/10 px-3 py-2">
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-muted">Kalan jeton</span>
                <span className="text-lg font-bold text-primary">{jeton.kalan.toLocaleString('tr-TR')}</span>
              </div>
              <div className="mt-1 text-[11px] leading-snug text-muted">
                {jeton.aylikHak.toLocaleString('tr-TR')} aylık hak (dönem sonunda yenilenir) ·{' '}
                {jeton.satinAlinan.toLocaleString('tr-TR')} satın alınan (süresi dolmaz)
              </div>
            </div>
          )}

          <div className="mt-3 rounded-lg border border-border bg-bg-soft/60 px-3 py-2 text-xs leading-relaxed text-muted">
            {FREE_MODE
              ? 'Test aşamasındayız: tüm planlar şu an ücretsiz, sizden ödeme alınmıyor.'
              : 'Jetonunuz yalnız yapay zekâ analizlerinde harcanır; seans ve acil durdurma jetondan bağımsızdır.'}
          </div>

          {!FREE_MODE && !onay && !sonuc && (
            <button
              onClick={() => setOnay(true)}
              className="mt-3 w-full rounded-lg border border-border px-3 py-2 text-sm text-muted transition hover:border-red-500/40 hover:text-red-500"
            >
              Aboneliği iptal et
            </button>
          )}

          {onay && (
            <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
              <p className="text-xs leading-relaxed text-amber-700 dark:text-amber-300">
                Aboneliğiniz iptal edilsin mi? Otomatik yenileme durur ve bir daha ücret alınmaz.
              </p>
              <div className="mt-3 flex gap-2">
                <button onClick={iptalEt} disabled={busy} className="btn-primary flex-1 py-1.5 text-xs disabled:opacity-60">
                  {busy ? 'İptal ediliyor…' : 'Evet, iptal et'}
                </button>
                <button onClick={() => setOnay(false)} disabled={busy} className="btn-ghost flex-1 py-1.5 text-xs">
                  Vazgeç
                </button>
              </div>
            </div>
          )}

          {sonuc && (
            <p
              className={`mt-3 rounded-lg border px-3 py-2 text-xs leading-relaxed ${
                sonuc.ok
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                  : 'border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400'
              }`}
            >
              {sonuc.mesaj}
            </p>
          )}

          <button
            onClick={() => { setAcik(false); signOut() }}
            className="mt-3 w-full rounded-lg px-3 py-2 text-sm text-muted transition hover:bg-bg-soft hover:text-fg"
          >
            Çıkış yap
          </button>
        </div>
      )}
    </div>
  )
}
