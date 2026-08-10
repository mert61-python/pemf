// Author: mertaygn, cglrgrkn
import { Component, type ReactNode } from 'react'

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
    return (
      <section className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-4 px-5 text-center">
        <h1 className="text-2xl font-bold">Bir şeyler ters gitti</h1>
        <p className="text-muted">
          Sayfa yüklenirken beklenmeyen bir hata oluştu. Sayfayı yenilemeyi deneyin; sorun sürerse
          bize yazın.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button className="btn-primary" onClick={() => window.location.reload()}>
            Sayfayı yenile
          </button>
          <a className="btn-ghost" href="/">
            Ana sayfaya dön
          </a>
        </div>
      </section>
    )
  }
}
