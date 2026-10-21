// Author: mertaygn, cglrgrkn
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useAuthModal } from '../context/AuthModal'
import { cancelSubscription } from '../lib/checkout'
import { FREE_MODE } from '../config'
import { odemeHatasiTurkce } from '../lib/authHatalari'
import { jetonBakiyesiniOku, type JetonBakiyesi } from '../lib/jeton'
import { sayi } from '../lib/para'
import { useTranslation } from 'react-i18next'

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
export default function AccountButton({ onNavigate, inline }: { onNavigate?: () => void; inline?: boolean }) {
  const { t } = useTranslation()
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
        {t('hesap.girisYap')}
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
        ? t('hesap.abonelik.iptalEdildi')
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
        {t('hesap.hesabim')}
      </button>

      {acik && (
        /* [W adım 3 / site-15] Menü SABİT 288 px (w-72) + `absolute right-0` idi: 320 px
           telefonda görünüm alanının DIŞINA taşıyordu. Genişlik artık görünüm alanıyla sınırlı;
           mobil çekmecede (inline) AKIŞA girip kendi yerini açıyor — üst üste binen iki katman
           yerine tek sütun. */
        <div
          role="menu"
          className={`z-50 mt-2 rounded-xl border border-border bg-bg p-4 text-left shadow-xl ${
            inline ? 'static w-full' : 'absolute right-0 w-72 max-w-[calc(100vw-2.5rem)]'
          }`}
        >
          <div className="text-xs text-muted">{t('hesap.girisYapildi')}</div>
          <div className="mt-0.5 truncate text-sm font-medium" title={email ?? undefined}>{email}</div>

          {/* JETON BAKİYESİ (7. parti): kullanıcı kalan analiz hakkını buradan görür.
              Okunamazsa HİÇ gösterilmez — yanlış sayı göstermektense boş bırakmak (DownloadStats
              ile aynı ilke). Aylık hak devretmez, satın alınan süresizdir; ikisi ayrı yazılır ki
              kullanıcı hangisinin ay sonunda sıfırlanacağını bilsin. */}
          {jeton && (
            <div className="mt-3 rounded-lg border border-primary/30 bg-primary/10 px-3 py-2">
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-muted">{t('hesap.kalanJeton')}</span>
                <span className="text-lg font-bold text-primary">{sayi(jeton.kalan)}</span>
              </div>
              <div className="mt-1 text-[11px] leading-snug text-muted">
                {t('hesap.jeton.aylikHak', { sayi: sayi(jeton.aylikHak) })}{' '}
                {t('hesap.jeton.satinAlinan', { sayi: sayi(jeton.satinAlinan) })}
              </div>
            </div>
          )}

          <div className="mt-3 rounded-lg border border-border bg-bg-soft/60 px-3 py-2 text-xs leading-relaxed text-muted">
            {FREE_MODE
              ? t('hesap.abonelik.testAsamasi')
              : t('hesap.jetonNotu')}
          </div>

          {!FREE_MODE && !onay && !sonuc && (
            <button
              onClick={() => setOnay(true)}
              className="mt-3 w-full rounded-lg border border-border px-3 py-2 text-sm text-muted transition hover:border-red-500/40 hover:text-red-500"
            >
              {t('hesap.abonelik.iptalEt')}
            </button>
          )}

          {onay && (
            <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
              <p className="text-xs leading-relaxed text-warning">
                {t('hesap.abonelik.iptalSorusu')}
              </p>
              <div className="mt-3 flex gap-2">
                <button onClick={iptalEt} disabled={busy} className="btn-primary flex-1 py-1.5 text-xs disabled:opacity-60">
                  {busy ? t('hesap.abonelik.iptalEdiliyor') : t('hesap.abonelik.evetIptal')}
                </button>
                <button onClick={() => setOnay(false)} disabled={busy} className="btn-ghost flex-1 py-1.5 text-xs">
                  {t('hesap.abonelik.vazgec')}
                </button>
              </div>
            </div>
          )}

          {sonuc && (
            <p
              className={`mt-3 rounded-lg border px-3 py-2 text-xs leading-relaxed ${
                sonuc.ok
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-success'
                  : 'border-red-500/40 bg-red-500/10 text-danger'
              }`}
            >
              {sonuc.mesaj}
            </p>
          )}

          <button
            onClick={() => { setAcik(false); signOut() }}
            className="mt-3 w-full rounded-lg px-3 py-2 text-sm text-muted transition hover:bg-bg-soft hover:text-fg"
          >
            {t('hesap.cikisYap')}
          </button>
        </div>
      )}
    </div>
  )
}
