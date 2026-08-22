// Author: mertaygn, cglrgrkn
import { Link } from 'react-router-dom'
import { FEATURES, PATCH } from '../config'
import { ICONS, ArrowRight, Check } from '../components/Icons'
import LauncherMock from '../components/LauncherMock'

export default function Features() {
  return (
    <>
      <section className="bg-hero border-b border-border/60">
        <div className="mx-auto max-w-6xl px-5 py-16 text-center sm:px-6 sm:py-20">
          <span className="chip">Özellikler</span>
          <h1 className="mt-5 text-4xl font-extrabold sm:text-5xl">Uçtan uca terapi kontrolü</h1>
          <p className="mx-auto mt-4 max-w-2xl text-muted">
            Cihaz bağlantısından yapay zekâya, hasta yönetiminden güvenliğe — hepsi tek uygulamada.
          </p>
        </div>
      </section>

      <section className="border-b border-border/60">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => {
              const Icon = ICONS[f.icon as keyof typeof ICONS]
              return (
                <div key={f.n} className="card p-6">
                  <span className="grid h-11 w-11 place-items-center rounded-xl bg-primary/12 text-primary ring-1 ring-primary/20">
                    {Icon && <Icon className="h-5.5 w-5.5" />}
                  </span>
                  <h3 className="mt-4 text-lg font-semibold">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted">{f.desc}</p>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* Launcher önizleme + yama notları */}
      <section className="border-b border-border/60 bg-bg-soft/60">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-16 sm:px-6 lg:grid-cols-2">
          <div>
            <span className="chip">Masaüstü uygulaması</span>
            <h2 className="mt-4 text-3xl font-bold">Tek pencereden yönetim</h2>
            <p className="mt-3 text-muted">
              Cihaz durumu, anlık ölçümler, seans başlatma ve güncellemeler tek ekranda. Uygulama ve yapay zekâ modelleri kendiliğinden güncel kalır.
            </p>
            <div className="mt-6 rounded-lg border border-border p-5">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold">Son güncelleme · v{PATCH.version}</span>
                <span className="text-xs text-muted">{PATCH.date}</span>
              </div>
              <ul className="space-y-2">
                {PATCH.notes.map((n, i) => (
                  <li key={i} className="flex gap-2 text-sm text-muted">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    {n}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="lg:pl-6">
            <LauncherMock />
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-6xl px-5 py-16 text-center sm:px-6">
          <h2 className="text-2xl font-bold sm:text-3xl">Başlamaya hazır mısınız?</h2>
          <p className="mt-3 text-muted">PEMF Vet’i indirin; kurulum ve güncellemeler otomatik.</p>
          <Link to="/download" className="btn-primary mt-6 !px-6 !py-3.5">
            PEMF Vet’i İndir <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
    </>
  )
}
