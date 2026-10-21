// Author: mertaygn, cglrgrkn
import { useEffect, useRef, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { PLANS, RESEARCH_ADDON, FREE_MODE } from '../config'
import { odemeHatasiTurkce } from '../lib/authHatalari'
import { useAuth } from '../context/AuthContext'
import { useAuthModal } from '../context/AuthModal'
import { initCheckout, type CheckoutCustomer } from '../lib/checkout'
import { Sparkle, Check } from '../components/Icons'
import { tl } from '../lib/para'
import { baglantiliMetin } from '../lib/metin'
import { useTranslation } from 'react-i18next'

const EMPTY: CheckoutCustomer = { name: '', surname: '', identityNumber: '', gsmNumber: '', city: '', address: '', zipCode: '' }

export default function Odeme() {
  const { t } = useTranslation()
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

  // Aylık-EŞDEĞER (yalnız bilgilendirme) ile O AN TAHSİL EDİLECEK tutarı ayır. Eskiden yalnız
  // aylık-eşdeğer hesaplanıyor ve aşağıdaki cümlede "{tutar} tutarında YILLIK ödeme" diye
  // sunuluyordu → yıllık Pro'da ekranda ₺825 yazarken karttan ₺9.900 çekiliyordu (12 kat fark).
  // Gerçek dönem tutarı sayfanın hiçbir yerinde görünmüyordu; bu bir ön bilgilendirme ihlalidir.
  const monthly = yearly ? Math.round((plan?.yearly ?? 0) / 12) : plan?.monthly ?? 0
  const total = monthly + (research ? RESEARCH_ADDON.monthly : 0)
  /** Bu siparişte HEMEN tahsil edilecek tutar (dönem bedeli).
   *
   *  ⚠️ EKLENTİYE DE "2 AY BEDAVA" UYGULANIR (denetim 2026-08-18): burada `monthly * 12` vardı ve
   *  yıllık+Araştırma seçiminde ekranda ₺14.580 yazarken iyzico planı ₺13.800 tahsil edecekti
   *  (₺780 fark). Yıllık tarife tek kuraldır: `PLANS`ta yearly = monthly × 10 ve
   *  `IYZICO_SETUP.md` plan tablosu eklentiyi de öyle katıyor. Sayı artık `RESEARCH_ADDON.yearly`
   *  tek kaynağından gelir; `download.test.ts` üçünü birden kilitliyor. */
  const chargeNow = yearly ? (plan?.yearly ?? 0) + (research ? RESEARCH_ADDON.yearly : 0) : total

  function set<K extends keyof CheckoutCustomer>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!session) return requireAuth()
    if (!consent) return setErr(t('odeme.onayGerekli'))
    setErr(null)
    setBusy(true)
    const { content, error, needAuth } = await initCheckout({ tier, yearly, research, customer: form })
    setBusy(false)
    if (needAuth) return requireAuth()
    // Ham iyzico metni ekrana basılmaz (auth tarafındaki kuralın aynısı) — sağlayıcı mesajı
    // günlüğe gider, kullanıcıya Türkçe ve eylem söyleyen karşılık döner.
    if (error) return setErr(odemeHatasiTurkce(error))
    if (content) {
      // scriptHost.current'a burada DOKUNMA (henüz render olmadı → null). İçeriği sakla + paying'e
      // geç; enjeksiyonu yukarıdaki useEffect div render olunca yapar.
      setCheckoutContent(content)
      setPaying(true)
    } else {
      setErr(t('odeme.baslatilamadi'))
    }
  }

  // FREE_MODE yalnız İSTEMCİ butonlarını gizliyordu; /odeme rotası App.tsx'te koşulsuz kayıtlı
  // olduğundan adres çubuğuna doğrudan yazan (ya da eski bir link açan) kullanıcıda GERÇEK iyzico
  // tahsilatı başlıyordu — site "Ücretsiz" derken. Kapıyı sayfanın kendisine koy.
  if (FREE_MODE) {
    return (
      <section className="mx-auto max-w-2xl px-5 py-24 text-center">
        <h1 className="text-2xl font-bold">{t('odeme.ucretsizBaslik')}</h1>
        <p className="mt-2 text-muted">
          {t('odeme.ucretsizAciklama')}
        </p>
        <Link to="/download" className="btn-primary mt-6">{t('odeme.indir')}</Link>
      </section>
    )
  }

  if (!plan) {
    return (
      <section className="mx-auto max-w-2xl px-5 py-24 text-center">
        <p className="text-muted">{t('odeme.planYok')}</p>
        <Link to="/pricing" className="btn-primary mt-6">{t('odeme.fiyatlandirmayaDon')}</Link>
      </section>
    )
  }

  return (
    <section className="mx-auto max-w-3xl px-5 py-14 sm:px-6">
      <Link to="/pricing" className="text-sm text-muted hover:text-fg">{t('odeme.planlar')}</Link>

      {/* Özet */}
      <div className="card mt-4 p-6">
        <span className="chip"><Sparkle className="h-3.5 w-3.5" />{t('odeme.abonelik')}</span>
        <div className="mt-3 flex items-center gap-2">
          <h1 className="text-2xl font-bold">{plan.name}</h1>
          {/* ⚠️ "Anında analiz" rozeti KALDIRILDI (8. parti): 7. partide kaldırılan hız
              vaadinin ödeme sayfasındaki kalıntısıydı — üstelik ödeme anında gösteriliyordu. */}
        </div>
        <ul className="mt-3 space-y-1.5 text-sm text-muted">
          <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />{plan.jetonHakki}</li>
          <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />{yearly ? t('odeme.yillikOdeme') : t('odeme.aylikOdeme')}</li>
          {research && <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />{t('odeme.arastirmaEklendi')}</li>}
        </ul>
        {/* ÖNCE gerçekte çekilecek tutar; aylık-eşdeğer yalnızca ikincil bilgi olarak. */}
        <div className="mt-4 flex items-baseline justify-between border-t border-border pt-4">
          <span className="text-sm text-muted">{t('odeme.bugunTahsil')}</span>
          <span className="text-2xl font-extrabold">
            {tl(chargeNow)}
            <span className="text-sm font-normal text-muted">/{yearly ? t('odeme.yil') : t('odeme.ay')}</span>
          </span>
        </div>
        {yearly && (
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-xs text-muted">{t('odeme.aylikEsdeger')}</span>
            <span className="text-xs text-muted">{t('fiyat.tlAy', { tutar: tl(total) })}</span>
          </div>
        )}
        {/* KDV BEYANI (metin denetimi 2026-08-20): burada "Fiyatlara KDV dâhil değildir" yazıyordu.
            Bu cümle İKİ ŞEYLE birden çelişiyordu: (1) Mesafeli Satış Sözleşmesi md.4 ve Ön
            Bilgilendirme Formu "tüm vergiler (KDV) dâhil toplam bedel sipariş özetinde gösterilen
            tutardır" diyor; (2) `api/checkout.ts` listedeki tutarı OLDUĞU GİBİ iyzico'ya geçiyor —
            hiçbir yerde vergi eklenmiyor, yani tahsil edilen tutar zaten TOPLAM bedel. Metin artık
            sistemin gerçek davranışını söylüyor. ⚠️ SAHİP KARARI: fiyatların KDV HARİÇ olması
            isteniyorsa değişmesi gereken şey bu cümle değil, tahsilat tarafıdır (checkout'un KDV
            eklemesi ve özetin ayrı satırda göstermesi gerekir). */}
        <p className="mt-3 text-xs leading-relaxed text-muted">
          <strong className="text-fg/80">{t('odeme.otoYenileme')}</strong>{' '}
          {t('odeme.otoYenilemeGovde', { tutar: tl(chargeNow), donem: yearly ? t('odeme.yillik') : t('odeme.aylik') })}{' '}
          <a href="/on-bilgilendirme" target="_blank" rel="noreferrer" className="text-primary hover:underline">{t('icerik.yasal.onBilgilendirme')}</a>{t('odeme.formunaBakin')}
        </p>
      </div>

      {!paying ? (
        <form onSubmit={submit} className="card mt-6 space-y-4 p-6">
          <h2 className="text-lg font-bold">{t('odeme.faturaBilgileri')}</h2>
          {/* Metin denetimi 2026-08-20: TC Kimlik No'nun neden istendiği "iyzico için gereklidir"
              diye geçiştiriliyordu; bir yazılım aboneliği için kimlik numarası vermek kullanıcıya
              tuhaf gelir ve sebebi söylenmezse form terk edilir. */}
          <p className="text-sm text-muted">
            {t('odeme.faturaAciklama')}
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            <input required placeholder={t('odeme.ad')} value={form.name} onChange={(e) => set('name', e.target.value)} className="input" />
            <input required placeholder={t('odeme.soyad')} value={form.surname} onChange={(e) => set('surname', e.target.value)} className="input" />
          </div>
          <input required placeholder={t('odeme.tc')} inputMode="numeric" maxLength={11} value={form.identityNumber} onChange={(e) => set('identityNumber', e.target.value.replace(/\D/g, ''))} className="input" />
          <input required placeholder={t('odeme.telefon')} value={form.gsmNumber} onChange={(e) => set('gsmNumber', e.target.value)} className="input" />
          <input required placeholder={t('hesap.alan.sehir')} value={form.city} onChange={(e) => set('city', e.target.value)} className="input" />
          <textarea required placeholder={t('odeme.adres')} value={form.address} onChange={(e) => set('address', e.target.value)} className="input min-h-20" />
          <input placeholder={t('odeme.posta')} value={form.zipCode} onChange={(e) => set('zipCode', e.target.value)} className="input" />

          {err && <p className="text-sm text-red-500">{err}</p>}
          {!session && <p className="text-sm text-warning">{t('odeme.girisYapin')}</p>}

          <label className="flex items-start gap-2.5 text-xs leading-relaxed text-muted">
            <input type="checkbox" required checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              {baglantiliMetin(t('odeme.onay', { skipInterpolation: true }), {
                onBilgi: <a href="/on-bilgilendirme" target="_blank" rel="noreferrer" className="text-primary hover:underline">{t('icerik.yasal.onBilgilendirme')}</a>,
                satis: <a href="/mesafeli-satis" target="_blank" rel="noreferrer" className="text-primary hover:underline">{t('icerik.yasal.mesafeliSatis')}</a>,
              })}
            </span>
          </label>

          <button type="submit" disabled={busy || !consent} className="btn-primary w-full disabled:opacity-60">
            {busy ? t('odeme.hazirlaniyor') : t('odeme.odemeyeGec')}
          </button>
          <p className="text-center text-xs text-muted">{t('odeme.istediginizZaman')}</p>
        </form>
      ) : (
        <div className="card mt-6 p-6">
          <h2 className="text-lg font-bold">{t('odeme.guvenliOdeme')}</h2>
          <p className="mt-1 text-sm text-muted">{t('odeme.formAciliyor')}</p>
          {/* iyzico bu div'e render eder; script host ayrı (script'ler buraya eklenir + çalışır). */}
          <div id="iyzipay-checkout-form" className="responsive mt-4" />
          <div ref={scriptHost} />
        </div>
      )}
    </section>
  )
}
