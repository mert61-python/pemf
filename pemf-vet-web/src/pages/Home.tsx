// Author: mertaygn, cglrgrkn
import { Link } from 'react-router-dom'
import { BRAND, CLIENT, FEATURES, FREE_MODE, LAUNCHER_STEPS, MODULES, PLANS } from '../config'
import { planKisaFiyat } from '../lib/planFiyat'
import { ICONS } from '../components/Icons'
import { Sparkle, ArrowRight, Check, Bolt } from '../components/Icons'
import DownloadButtons from '../components/DownloadButtons'
import LauncherMock from '../components/LauncherMock'
import AppScreenshots from '../components/AppScreenshots'

export default function Home() {
  return (
    <>
      {/* ── HERO ─────────────────────────────────────────── */}
      <section className="bg-hero border-b border-border/60">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-20 sm:px-6 lg:grid-cols-2 lg:py-28">
          <div>
            {/* Metin denetimi 2026-08-20: burada `CLIENT.channel` ("Sürüm 2026.1") yazıyordu ve
                aynı ekranın altında "v1.9.32" görünüyordu — iki ayrı sürüm şeması yan yana,
                hangisinin ne olduğu belirsiz. Rozet artık sürüm SÖYLEMİYOR; tek sürüm bilgisi
                aşağıdaki satırda (ve İndir sayfasında) durur. */}
            <span className="chip">
              <Sparkle className="h-3.5 w-3.5" />
              Veteriner klinikleri için · Yayında
            </span>
            <h1 className="mt-5 text-4xl font-extrabold leading-[1.08] sm:text-5xl lg:text-[3.4rem]">
              <span className="text-gradient">{BRAND.tagline}</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
              Veteriner kliniğiniz için elektromanyetik alan terapisini tek ekrandan yönetin.
              {' '}
              <span className="text-fg/90 font-medium">PEMF Vet’i indirin</span>{' '}
              — uygulama, cihaz yazılımı ve yapay zekâ modelleri sizin için kurulur, güncellemeler kendiliğinden gelir.
            </p>

            <div className="mt-8">
              <DownloadButtons size="lg" />
            </div>
            <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
              {/* Adversaryal inceleme 2026-08-20: burada macOS ve Linux ONAY İŞARETİYLE
                  listeleniyordu ama ikisi de `ready:false` — İndir sayfasında "Yakında". Yani
                  ana sayfa, indirilemeyen iki platformu destekleniyor gibi gösteriyordu.
                  Rozetler artık gerçekten indirilebilen platformları söyler. */}
              <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> {CLIENT.downloads.windows.os}</span>
              <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> {CLIENT.downloads.android.os}</span>
              <span className="inline-flex items-center gap-1.5 text-muted/70">macOS · Linux yakında</span>
              <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> Sürüm {CLIENT.version} · {CLIENT.sizeMB} MB kurulum</span>
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
            <h2 className="mt-4 text-3xl font-bold sm:text-4xl">Tek indirme, gerisi otomatik</h2>
            <p className="mt-3 text-muted">
              Küçük bir kurulum dosyası indirirsiniz; uygulamayı, modelleri ve güncellemeleri o getirir.
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
              <p className="mt-3 text-muted">Cihaz bağlantısından yapay zekâ teşhisine kadar her şey tek uygulamada.</p>
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

      {/* ── UYGULAMA EKRANLARI ──────────────────────────────── */}
      <AppScreenshots />

      {/* ── PROFİLLER + PLAN TEASER ─────────────────────────── */}
      <section className="border-b border-border/60 bg-bg-soft/60">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 py-20 sm:px-6 lg:grid-cols-2 lg:items-center">
          <div>
            <span className="chip">Kurulum profilleri</span>
            <h2 className="mt-4 text-3xl font-bold sm:text-4xl">Herkes kendi ihtiyacını kurar</h2>
            <p className="mt-3 text-muted">
              Evcil Hayvan Sahibi, Veteriner ve Araştırma — kurulumda seçtiğiniz profile göre yalnız
              işinize yarayan yapay zekâ modelleri iner. Evcil hayvan sahibi, ağır araştırma
              modellerini indirmez.
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
            <h3 className="mt-4 text-2xl font-bold">İhtiyacınıza göre plan</h3>
            <p className="mt-2 text-sm text-muted">Planınız, ayda kaç yapay zekâ analizi yapabileceğinizi belirler. Her analiz 1 jeton harcar.</p>
            {/* FİYAT TEK KAYNAK + FREE_MODE (metin denetimi 2026-08-20): burada ₺990 / ₺1.990
                KODA GÖMÜLÜYDÜ. Fiyat sayfası "test aşaması: tüm planlar şu an ücretsiz" derken bu
                kutu fiyat gösteriyordu — iki sayfa birbirini yalanlıyordu. Sayılar artık
                `config.PLANS`ten gelir ve ücretsiz dönemde fiyat yerine durum yazılır. */}
            <div className="mt-5 space-y-3">
              {PLANS.filter((p) => p.paid).map((p) => (
                <div
                  key={p.tier}
                  className={
                    p.highlight
                      ? 'flex items-center gap-3 rounded-lg border border-primary/40 bg-primary/10 px-4 py-3'
                      : 'flex items-center gap-3 rounded-lg border border-border px-4 py-3'
                  }
                >
                  {p.highlight ? <Bolt className="h-4 w-4 text-primary" /> : <span className="h-2 w-2 rounded-full bg-muted" />}
                  <div className="flex-1">
                    <div className="font-semibold">{p.name}</div>
                    <div className="text-xs text-muted">{p.jetonHakki}</div>
                  </div>
                  <div className="text-sm font-bold">
                    {/* Fiyat metni TEK KAYNAKTAN (src/lib/planFiyat.ts) — burada ayrıca
                        hesaplanınca kullandıkça-öde planı "₺0/ay" görünüyordu. */}
                    <span className={p.priceLabel || FREE_MODE ? 'text-primary' : undefined}>
                      {planKisaFiyat(p)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <Link to="/pricing" className="btn-primary mt-6 w-full">
              Planları karşılaştır <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
