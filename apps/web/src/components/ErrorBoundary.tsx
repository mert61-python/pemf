// Author: mertaygn, cglrgrkn
import { Component, type ReactNode } from 'react'
import { COMPANY } from '../config'
import i18n from 'i18next'

/* Kök hata sınırı. Sitede hiç ErrorBoundary yoktu: herhangi bir sayfadaki tek bir render hatası
   (ör. config'te eksik alan, beklenmedik veri şekli) TÜM siteyi beyaz ekrana düşürüyordu — üstelik
   ödeme akışının ortasında da olabilirdi. React Router `<Routes>` (data router değil) kullanıldığı
   için `errorElement` de devrede değil. Burada yakalayıp kurtarılabilir bir ekran gösteriyoruz. */
type State = { hasError: boolean }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: unknown) {
    // Ayrıntı yalnız konsola; kullanıcıya iç detay (stack, dosya yolu) gösterme.
    console.error('Uygulama hatası:', error)
  }

  render() {
    if (!this.state.hasError) return this.props.children
    // Tek çeviri anahtarı, e-posta bağlantısı yerinde kalsın diye işaretçiyle (\u0001) ikiye bölünür.
    const [govdeOnce, govdeSonra] = i18n.t('hata.govde', { eposta: '\u0001' }).split('\u0001')
    return (
      <section className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-4 px-5 text-center">
        <h1 className="text-2xl font-bold">{i18n.t('hata.baslik')}</h1>
        {/* Metin denetimi 2026-08-20: "bize yazın" tıklanabilir değildi ve adres yazmıyordu —
            hata anında kullanıcının iletişim yolu kapalıydı. */}
        <p className="text-muted">
          {govdeOnce}
          <a className="text-primary hover:underline" href={`mailto:${COMPANY.email}?subject=${encodeURIComponent(i18n.t('hata.konu'))}`}>
            {COMPANY.email}
          </a>
          {govdeSonra}
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button className="btn-primary" onClick={() => window.location.reload()}>
            {i18n.t('hata.yenile')}
          </button>
          <a className="btn-ghost" href="/">
            {i18n.t('ortak.anaSayfayaDon')}
          </a>
        </div>
      </section>
    )
  }
}
