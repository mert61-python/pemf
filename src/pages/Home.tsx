import { Link } from 'react-router-dom'
import { BRAND, CLIENT, FEATURES, LAUNCHER_STEPS, MODULES } from '../config'
import { ICONS } from '../components/Icons'
import { Sparkle, ArrowRight, Check, Download, Bolt } from '../components/Icons'
import DownloadButtons from '../components/DownloadButtons'
import LauncherMock from '../components/LauncherMock'

export default function Home() {
  return (
    <>
      {/* ── HERO ─────────────────────────────────────────── */}
      <section className="bg-hero border-b border-border/60">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-20 sm:px-6 lg:grid-cols-2 lg:py-28">
          <div>
            <span className="chip">
              <Sparkle className="h-3.5 w-3.5" />
              {CLIENT.channel} · Yayında
            </span>
            <h1 className="mt-5 text-4xl font-extrabold leading-[1.08] sm:text-5xl lg:text-[3.4rem]">
              <span className="text-gradient">{BRAND.tagline}</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
              Klinik hassasiyetinde elektromanyetik alan terapisi artık masaüstünüzde.
              {' '}
              <span className="text-fg/90 font-medium">Hafif PEMF Vet Client’ı</span>{' '}
              indirin; uygulamayı, donanım yazılımını ve AI modellerini client içinden kurun ve tek merkezden güncelleyin.
            </p>

            <div className="mt-8">
              <DownloadButtons size="lg" />
            </div>
            <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
              <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> {CLIENT.downloads.windows.os}</span>
              <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> {CLIENT.downloads.macos.os}</span>
              <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> v{CLIENT.version} · hafif client</span>
            </p>
          </div>

          <div className="lg:pl-6">
            <LauncherMock />
          </div>
        </div>
      </section>

      {/* ── LAUNCHER AKIŞI (Riot-benzeri) ───────────────────── */}
      <section className="border-b border-border/60">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-6">
          <div className="mx-auto max-w-2xl text-center">
            <span className="chip">Nasıl çalışır</span>
            <h2 className="mt-4 text-3xl font-bold sm:text-4xl">Tek client, tüm kurulum</h2>
            <p className="mt-3 text-muted">
              Bir oyun istemcisinin oyunu kurup güncellemesi gibi — küçük client’ı indirir, gerisini o halleder.
            </p>
          </div>

          <div className="relative mt-14 grid gap-6 md:grid-cols-3">
            {/* bağlayıcı çizgi */}
            <div className="pointer-events-none absolute inset-x-[16%] top-9 hidden h-px bg-gradient-to-r from-transparent via-border-strong to-transparent md:block" />
            {LAUNCHER_STEPS.map((s) => (
              <div key={s.step} className="card relative p-6">
                <div className="mb-4 grid h-12 w-12 place-items-center rounded-xl bg-primary/12 text-lg font-bold text-primary ring-1 ring-primary/25">
                  {s.step}
                </div>
                <h3 className="text-lg font-semibold">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── ÖZELLİKLER ──────────────────────────────────────── */}
      <section className="border-b border-border/60 bg-bg-soft/60">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-6">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
            <div className="max-w-xl">
              <span className="chip">Özellikler</span>
              <h2 className="mt-4 text-3xl font-bold sm:text-4xl">Klinik için tasarlandı</h2>
              <p className="mt-3 text-muted">Bağlantıdan yapay zekâya, tek istemciden yönetilen uçtan uca terapi kontrolü.</p>
            </div>
            <Link to="/features" className="btn-ghost self-start text-sm md:self-auto">
              Tümünü gör <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => {
              const Icon = ICONS[f.icon as keyof typeof ICONS]
              return (
                <div key={f.n} className="card p-6 transition-transform hover:-translate-y-0.5">
                  <div className="flex items-center justify-between">
                    <span className="grid h-11 w-11 place-items-center rounded-xl bg-primary/12 text-primary ring-1 ring-primary/20">
                      {Icon && <Icon className="h-5.5 w-5.5" />}
                    </span>
                    <span className="text-xs font-semibold text-muted/60">{f.n}</span>
                  </div>
                  <h3 className="mt-4 text-lg font-semibold">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted">{f.desc}</p>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ── PROFİLLER + PLAN TEASER ─────────────────────────── */}
      <section className="border-b border-border/60 bg-bg-soft/60">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 py-20 sm:px-6 lg:grid-cols-2 lg:items-center">
          <div>
            <span className="chip">Kullanım profilleri</span>
            <h2 className="mt-4 text-3xl font-bold sm:text-4xl">Herkese göre tek uygulama</h2>
            <p className="mt-3 text-muted">
              Ev Sahibi, Veteriner ve Araştırma — client içinde seçtiğiniz profile göre uyarlanır ve
              yalnız seçtiğiniz modeller iner. Ev kullanıcısı ağır araştırma modellerini indirmez.
            </p>
            <div className="mt-6 space-y-3">
              {MODULES.map((m) => (
                <div key={m.id} className="flex items-center justify-between rounded-lg border border-border bg-bg/40 px-4 py-3">
                  <div>
                    <div className="font-semibold">{m.name}</div>
                    <div className="text-xs text-muted">{m.tagline}</div>
                  </div>
                  <div className="shrink-0 pl-3 text-right">
                    <div className="text-xs text-muted">≈ {m.sizeGB.toFixed(1)} GB</div>
                    <div className={`text-xs font-semibold ${m.included ? 'text-success' : 'text-primary'}`}>
                      {m.included ? 'Dahil' : `+₺${m.addonMonthly}/ay`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-8">
            <span className="chip">Üyelik</span>
            <h3 className="mt-4 text-2xl font-bold">İşlem önceliğinize göre plan</h3>
            <p className="mt-2 text-sm text-muted">AI’nın ne kadar hızlı çalışacağını seviye belirler.</p>
            <div className="mt-5 space-y-3">
              <div className="flex items-center gap-3 rounded-lg border border-border px-4 py-3">
                <span className="h-2 w-2 rounded-full bg-muted" />
                <div className="flex-1">
                  <div className="font-semibold">Pro</div>
                  <div className="text-xs text-muted">Standart kuyruk · yoğunlukta kısa bekleme</div>
                </div>
                <div className="text-sm font-bold">₺990<span className="text-xs font-medium text-muted">/ay</span></div>
              </div>
              <div className="flex items-center gap-3 rounded-lg border border-primary/40 bg-primary/10 px-4 py-3">
                <Bolt className="h-4 w-4 text-primary" />
                <div className="flex-1">
                  <div className="font-semibold">Pro+ <span className="text-xs font-bold text-primary">Real-time</span></div>
                  <div className="text-xs text-muted">Kuyruk yok · anlık AI Pro kapalı-döngü</div>
                </div>
                <div className="text-sm font-bold">₺1.990<span className="text-xs font-medium text-muted">/ay</span></div>
              </div>
            </div>
            <Link to="/pricing" className="btn-primary mt-6 w-full">
              Planları karşılaştır <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* ── İNDİR CTA ───────────────────────────────────────── */}
      <section>
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-6">
          <div className="card glow-ring relative overflow-hidden p-10 text-center sm:p-14">
            <div className="bg-hero pointer-events-none absolute inset-0 opacity-40" />
            <div className="relative">
              <span className="grid mx-auto h-14 w-14 place-items-center rounded-2xl bg-primary/15 text-primary ring-1 ring-primary/25">
                <Download className="h-7 w-7" />
              </span>
              <h2 className="mt-6 text-3xl font-bold sm:text-4xl">PEMF Vet Client’ı indirin</h2>
              <p className="mx-auto mt-3 max-w-lg text-muted">
                Hafif client · v{CLIENT.version}. İndirin, kurun ve uygulamayı client içinden başlatın.
              </p>
              <div className="mt-8 flex justify-center">
                <DownloadButtons size="lg" />
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
