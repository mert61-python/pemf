import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PLANS, ADDONS, COMPARE, type Plan } from '../config'
import { Check, Sparkle, Bolt } from '../components/Icons'
import PackageBuilder from '../components/PackageBuilder'

const tl = (n: number) => `₺${n.toLocaleString('tr-TR')}`

function priceView(p: Plan, yearly: boolean) {
  if (p.priceLabel) return { big: p.priceLabel, sub: p.period }
  const perMonth = yearly ? Math.round((p.yearly ?? 0) / 12) : p.monthly ?? 0
  return {
    big: tl(perMonth),
    sub: yearly ? `${p.period} · yıllık ${tl(p.yearly ?? 0)}` : p.period,
  }
}

export default function Pricing() {
  const [yearly, setYearly] = useState(true)

  return (
    <>
      {/* Hero + billing toggle */}
      <section className="bg-hero border-b border-border/60">
        <div className="mx-auto max-w-6xl px-5 py-16 text-center sm:px-6 sm:py-20">
          <span className="chip"><Sparkle className="h-3.5 w-3.5" /> Fiyatlandırma</span>
          <h1 className="mt-5 text-4xl font-extrabold sm:text-5xl">İşlem önceliğine göre plan</h1>
          <p className="mx-auto mt-4 max-w-2xl text-muted">
            Seviye, AI’nın ne kadar hızlı çalışacağını belirler:{' '}
            <span className="text-fg/90 font-medium">Pro kuyrukta bekler, Pro+ gerçek-zamanlıdır</span>.
            Hangi modellerin ineceğini ise client içinde seçtiğiniz profiller belirler.
          </p>

          <div className="mt-8 inline-flex items-center gap-1 rounded-full border border-border-strong bg-bg-soft p-1 text-sm">
            <button onClick={() => setYearly(false)} className={`rounded-full px-4 py-1.5 font-medium transition-colors ${!yearly ? 'bg-primary text-primary-fg' : 'text-muted'}`}>Aylık</button>
            <button onClick={() => setYearly(true)} className={`rounded-full px-4 py-1.5 font-medium transition-colors ${yearly ? 'bg-primary text-primary-fg' : 'text-muted'}`}>
              Yıllık<span className={`ml-1.5 text-xs ${yearly ? 'text-primary-fg/80' : 'text-primary'}`}>2 ay bedava</span>
            </button>
          </div>
        </div>
      </section>

      {/* Seviyeler */}
      <section className="border-b border-border/60">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <div className="grid items-start gap-6 lg:grid-cols-3">
            {PLANS.map((p) => {
              const pv = priceView(p, yearly)
              return (
                <div key={p.name} className={`card relative flex flex-col p-7 ${p.highlight ? 'ring-2 ring-primary/50 glow-ring' : ''}`}>
                  {p.badge && (
                    <span className="absolute -top-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 rounded-full bg-primary px-3 py-1 text-xs font-bold text-primary-fg">
                      <Bolt className="h-3 w-3" /> {p.badge}
                    </span>
                  )}
                  <div className="text-lg font-bold">{p.name}</div>
                  <p className="mt-1 text-sm text-muted">{p.desc}</p>

                  <div className="mt-5 text-4xl font-extrabold tracking-tight">{pv.big}</div>
                  <div className="mt-1 text-xs text-muted">{pv.sub}</div>

                  {/* İşlem önceliği vurgusu */}
                  <div className={`mt-4 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium ${
                    p.realtime ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border text-muted'
                  }`}>
                    {p.realtime ? <Bolt className="h-4 w-4" /> : <span className="h-1.5 w-1.5 rounded-full bg-muted" />}
                    {p.queue}
                  </div>

                  <Link to={p.to} className={`mt-6 ${p.highlight ? 'btn-primary' : 'btn-ghost'}`}>{p.cta}</Link>

                  <ul className="mt-6 space-y-2.5 border-t border-border pt-6">
                    {p.features.map((f, i) => (
                      <li key={i} className="flex gap-2.5 text-sm text-muted">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* Karşılaştırma tablosu */}
      <section className="border-b border-border/60 bg-bg-soft/50">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <h2 className="text-2xl font-bold sm:text-3xl">Seviye karşılaştırması</h2>
          <div className="mt-8 overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="py-3 text-left font-medium text-muted"></th>
                  {['Başlangıç', 'Pro', 'Pro+'].map((c, i) => (
                    <th key={c} className={`px-3 py-3 text-center font-bold ${i === 2 ? 'text-primary' : ''}`}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARE.map((row) => (
                  <tr key={row.label} className="border-b border-border/60">
                    <td className="py-3 pr-3 font-medium">{row.label}</td>
                    {row.values.map((v, i) => (
                      <td key={i} className={`px-3 py-3 text-center ${i === 2 ? 'text-fg' : 'text-muted'}`}>{v}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Kullanım profilleri (kurulum) */}
      <section className="border-b border-border/60">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <div className="max-w-2xl">
            <span className="chip">Kurulum profilleri</span>
            <h2 className="mt-4 text-2xl font-bold sm:text-3xl">Ne kurulacağını siz seçin</h2>
            <p className="mt-3 text-muted">
              Client yalnız seçtiğiniz profillerin modellerini indirir — ev kullanıcısı ağır araştırma
              modellerini boşuna indirmez. Ev Sahibi ve Veteriner seviyenize dahildir.
            </p>
          </div>
          <div className="mt-10">
            <PackageBuilder />
          </div>
        </div>
      </section>

      {/* Eklentiler */}
      <section className="border-b border-border/60 bg-bg-soft/50">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <div className="max-w-xl">
            <span className="chip">Eklentiler</span>
            <h2 className="mt-4 text-2xl font-bold sm:text-3xl">Uygulama içi satın alma</h2>
            <p className="mt-3 text-muted">Client içinden tek tıkla etkinleştirin; aboneliğinize eklenir.</p>
          </div>
          <div className="mt-10 grid gap-5 sm:grid-cols-3">
            {ADDONS.map((a) => (
              <div key={a.name} className="card p-6">
                <div className="flex items-baseline justify-between">
                  <h3 className="font-semibold">{a.name}</h3>
                  <span className="text-sm font-bold text-primary">{a.price}</span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-muted">{a.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Kurumsal + trial */}
      <section>
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <div className="card flex flex-col items-center gap-6 p-8 text-center sm:flex-row sm:justify-between sm:p-10 sm:text-left">
            <div>
              <h2 className="text-2xl font-bold">Zincir klinik veya kurum musunuz?</h2>
              <p className="mt-2 max-w-lg text-muted">Sınırsız cihaz/lokasyon, özel entegrasyon, yerinde kurulum ve SLA için özel fiyat.</p>
            </div>
            <div className="flex shrink-0 flex-col gap-3 sm:flex-row">
              <Link to="/support" className="btn-ghost">İletişime Geçin</Link>
              <Link to="/download" className="btn-primary">14 gün ücretsiz dene</Link>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
