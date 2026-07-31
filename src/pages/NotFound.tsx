import { Link } from 'react-router-dom'
import { NAV } from '../config'

export default function NotFound() {
  return (
    <section className="mx-auto grid min-h-[60vh] max-w-2xl place-items-center px-4 py-20 text-center">
      <div>
        <p className="text-sm font-semibold uppercase tracking-widest text-primary">404</p>
        <h1 className="mt-3 text-3xl font-bold sm:text-4xl">Sayfa bulunamadı</h1>
        <p className="mx-auto mt-3 max-w-md text-muted">
          Aradığınız sayfa taşınmış veya hiç var olmamış olabilir. Aşağıdaki bağlantılardan devam edebilirsiniz.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Link to="/" className="btn-primary">Ana sayfaya dön</Link>
          {NAV.map((n) => (
            <Link key={n.to} to={n.to} className="rounded-lg border border-border px-4 py-2 text-sm text-muted hover:border-primary/40 hover:text-fg">
              {n.label}
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}
