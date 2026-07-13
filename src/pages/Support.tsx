import { Link } from 'react-router-dom'
import { FAQ } from '../config'
import { ArrowRight } from '../components/Icons'

export default function Support() {
  return (
    <>
      <section className="bg-hero border-b border-border/60">
        <div className="mx-auto max-w-3xl px-5 py-16 text-center sm:px-6 sm:py-20">
          <span className="chip">Destek</span>
          <h1 className="mt-5 text-4xl font-extrabold sm:text-5xl">Sık sorulan sorular</h1>
          <p className="mx-auto mt-4 max-w-xl text-muted">
            Client, kurulum ve uygulama hakkında en çok merak edilenler.
          </p>
        </div>
      </section>

      <section className="border-b border-border/60">
        <div className="mx-auto max-w-3xl px-5 py-14 sm:px-6">
          <div className="space-y-3">
            {FAQ.map((f, i) => (
              <details key={i} className="card group p-0">
                <summary className="flex cursor-pointer items-center justify-between gap-4 px-6 py-4 font-semibold [&::-webkit-details-marker]:hidden">
                  {f.q}
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-border-strong text-muted transition-transform group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="px-6 pb-5 text-sm leading-relaxed text-muted">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-3xl px-5 py-16 sm:px-6">
          <div className="card p-8 text-center sm:p-10">
            <h2 className="text-2xl font-bold">Hâlâ yardıma mı ihtiyacınız var?</h2>
            <p className="mx-auto mt-3 max-w-md text-muted">
              Kurulum, lisans veya klinik entegrasyon için ekibimizle iletişime geçin.
            </p>
            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <a href="mailto:destek@v-pemf.com" className="btn-primary">destek@v-pemf.com</a>
              <Link to="/download" className="btn-ghost">
                İstemciyi İndir <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
