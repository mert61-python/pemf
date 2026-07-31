import { useEffect, useRef, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { PLANS, RESEARCH_ADDON } from '../config'
import { useAuth } from '../context/AuthContext'
import { useAuthModal } from '../context/AuthModal'
import { initCheckout, type CheckoutCustomer } from '../lib/checkout'
import { Sparkle, Bolt, Check } from '../components/Icons'

const tl = (n: number) => `₺${n.toLocaleString('tr-TR')}`
const EMPTY: CheckoutCustomer = { name: '', surname: '', identityNumber: '', gsmNumber: '', city: '', address: '', zipCode: '' }

export default function Odeme() {
  const [sp] = useSearchParams()
  const tier = sp.get('tier') === 'pro_plus' ? 'pro_plus' : 'pro'
  const yearly = sp.get('yearly') === '1'
  const research = sp.get('research') === '1'
  const plan = PLANS.find((p) => p.tier === tier)

  const { session, ready } = useAuth()
  const { requireAuth } = useAuthModal()
  const [form, setForm] = useState<CheckoutCustomer>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [paying, setPaying] = useState(false)
  const [checkoutContent, setCheckoutContent] = useState<string | null>(null)
  const [consent, setConsent] = useState(false)
  const scriptHost = useRef<HTMLDivElement>(null)

  // Giriş yoksa modal aç (ödeme hesaba tanımlanır).
  useEffect(() => {
    if (ready && !session) requireAuth()
  }, [ready, session, requireAuth])

  // FIX (#54): scriptHost div'i YALNIZ `paying` dalında render edilir → submit anında ref NULL'dı
  // ve iyzico formu HİÇ enjekte edilmiyordu (kalıcı deadlock). paying=true olup div render olduktan
  // SONRA burada (childElementCount guard'ıyla tek sefer) iyzico içeriğini + script'lerini gömeriz.
  useEffect(() => {
    const host = scriptHost.current
    if (paying && checkoutContent && host && host.childElementCount === 0) {
      // innerHTML script çalıştırmaz; createContextualFragment script'leri ÇALIŞTIRIR.
      host.appendChild(document.createRange().createContextualFragment(checkoutContent))
    }
  }, [paying, checkoutContent])

  const monthly = yearly ? Math.round((plan?.yearly ?? 0) / 12) : plan?.monthly ?? 0
  const total = monthly + (research ? RESEARCH_ADDON.monthly : 0)

  function set<K extends keyof CheckoutCustomer>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!session) return requireAuth()
    if (!consent) return setErr('Devam etmek için Ön Bilgilendirme Formu ve Mesafeli Satış Sözleşmesi’ni onaylayın.')
    setErr(null)
    setBusy(true)
    const { content, error, needAuth } = await initCheckout({ tier, yearly, research, customer: form })
    setBusy(false)
    if (needAuth) return requireAuth()
    if (error) return setErr(error)
    if (content) {
      // scriptHost.current'a burada DOKUNMA (henüz render olmadı → null). İçeriği sakla + paying'e
      // geç; enjeksiyonu yukarıdaki useEffect div render olunca yapar.
      setCheckoutContent(content)
      setPaying(true)
    } else {
      setErr('Ödeme başlatılamadı. Lütfen tekrar deneyin.')
    }
  }

  if (!plan) {
    return (
      <section className="mx-auto max-w-2xl px-5 py-24 text-center">
        <p className="text-muted">Geçersiz plan.</p>
        <Link to="/pricing" className="btn-primary mt-6">Fiyatlandırmaya dön</Link>
      </section>
    )
  }

  return (
    <section className="mx-auto max-w-3xl px-5 py-14 sm:px-6">
      <Link to="/pricing" className="text-sm text-muted hover:text-fg">← Planlar</Link>

      {/* Özet */}
      <div className="card mt-4 p-6">
        <span className="chip"><Sparkle className="h-3.5 w-3.5" /> Abonelik</span>
        <div className="mt-3 flex items-center gap-2">
          <h1 className="text-2xl font-bold">{plan.name}</h1>
          {plan.realtime && (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-xs font-bold text-primary">
              <Bolt className="h-3 w-3" /> Real-time
            </span>
          )}
        </div>
        <ul className="mt-3 space-y-1.5 text-sm text-muted">
          <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />{plan.queue}</li>
          <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />{yearly ? 'Yıllık ödeme (2 ay bedava)' : 'Aylık ödeme'}</li>
          {research && <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />Araştırma modülü eklendi</li>}
        </ul>
        <div className="mt-4 flex items-baseline justify-between border-t border-border pt-4">
          <span className="text-sm text-muted">Aylık toplam</span>
          <span className="text-2xl font-extrabold">{tl(total)}<span className="text-sm font-normal text-muted">/ay</span></span>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted">
          <strong className="text-fg/80">Otomatik yenilenen abonelik:</strong> {tl(total)} tutarında {yearly ? 'yıllık' : 'aylık'} ödeme,
          siz iptal edene kadar her dönem sonunda otomatik tahsil edilir. Fiyat ve vergi ayrıntıları için{' '}
          <a href="/on-bilgilendirme" target="_blank" rel="noreferrer" className="text-primary hover:underline">Ön Bilgilendirme Formu</a>'na bakınız.
        </p>
      </div>

      {!paying ? (
        <form onSubmit={submit} className="card mt-6 space-y-4 p-6">
          <h2 className="text-lg font-bold">Fatura bilgileri</h2>
          <p className="text-sm text-muted">iyzico güvenli ödeme için gereklidir. Kart bilgisi bir sonraki adımda iyzico formunda girilir.</p>

          <div className="grid gap-3 sm:grid-cols-2">
            <input required placeholder="Ad" value={form.name} onChange={(e) => set('name', e.target.value)} className="input" />
            <input required placeholder="Soyad" value={form.surname} onChange={(e) => set('surname', e.target.value)} className="input" />
          </div>
          <input required placeholder="TC Kimlik No" inputMode="numeric" maxLength={11} value={form.identityNumber} onChange={(e) => set('identityNumber', e.target.value.replace(/\D/g, ''))} className="input" />
          <input required placeholder="Telefon (+90...)" value={form.gsmNumber} onChange={(e) => set('gsmNumber', e.target.value)} className="input" />
          <input required placeholder="Şehir" value={form.city} onChange={(e) => set('city', e.target.value)} className="input" />
          <textarea required placeholder="Adres" value={form.address} onChange={(e) => set('address', e.target.value)} className="input min-h-20" />
          <input placeholder="Posta kodu (opsiyonel)" value={form.zipCode} onChange={(e) => set('zipCode', e.target.value)} className="input" />

          {err && <p className="text-sm text-red-500">{err}</p>}
          {!session && <p className="text-sm text-amber-600 dark:text-amber-400">Devam etmek için giriş yapın.</p>}

          <label className="flex items-start gap-2.5 text-xs leading-relaxed text-muted">
            <input type="checkbox" required checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              <a href="/on-bilgilendirme" target="_blank" rel="noreferrer" className="text-primary hover:underline">Ön Bilgilendirme Formu</a>'nu ve{' '}
              <a href="/mesafeli-satis" target="_blank" rel="noreferrer" className="text-primary hover:underline">Mesafeli Satış Sözleşmesi</a>'ni okudum, onaylıyorum.
            </span>
          </label>

          <button type="submit" disabled={busy || !consent} className="btn-primary w-full disabled:opacity-60">
            {busy ? 'Hazırlanıyor…' : 'Ödemeye geç'}
          </button>
          <p className="text-center text-xs text-muted">Aboneliğinizi istediğiniz zaman hesabınızdan iptal edebilirsiniz.</p>
        </form>
      ) : (
        <div className="card mt-6 p-6">
          <h2 className="text-lg font-bold">Güvenli ödeme</h2>
          <p className="mt-1 text-sm text-muted">iyzico ödeme formu aşağıda yüklenir.</p>
          {/* iyzico bu div'e render eder; script host ayrı (script'ler buraya eklenir + çalışır). */}
          <div id="iyzipay-checkout-form" className="responsive mt-4" />
          <div ref={scriptHost} />
        </div>
      )}
    </section>
  )
}
