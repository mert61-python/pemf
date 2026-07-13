import type { FC } from 'react'
import { CLIENT, LAUNCHER_STEPS, MODULES } from '../config'
import { Windows, Apple, Check, Download } from '../components/Icons'

function PlatformCard({
  Icon,
  label,
  os,
  url,
  primary,
}: {
  Icon: FC<{ className?: string }>
  label: string
  os: string
  url: string
  primary?: boolean
}) {
  return (
    <div className="card flex flex-col p-7">
      <div className="flex items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-xl bg-primary/12 text-fg ring-1 ring-white/10">
          <Icon className="h-6 w-6" />
        </span>
        <div>
          <div className="text-lg font-semibold">{label}</div>
          <div className="text-xs text-muted">{os}</div>
        </div>
      </div>
      {CLIENT.ready ? (
        <a href={url} className={`mt-6 ${primary ? 'btn-primary' : 'btn-ghost'}`}>
          <Download className="h-4 w-4" />
          {label} için indir
        </a>
      ) : (
        <span className={`mt-6 ${primary ? 'btn-primary' : 'btn-ghost'} cursor-not-allowed opacity-60`} aria-disabled>
          <Download className="h-4 w-4" />
          Yakında
        </span>
      )}
      <div className="mt-4 space-y-1.5 text-xs text-muted">
        <div className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> Sürüm {CLIENT.version} · {CLIENT.releaseDate}</div>
        <div className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> İmzalı kurulum · SHA-256 doğrulanır</div>
      </div>
    </div>
  )
}

export default function DownloadPage() {
  return (
    <>
      <section className="bg-hero border-b border-border/60">
        <div className="mx-auto max-w-5xl px-5 py-16 text-center sm:px-6 sm:py-20">
          <span className="chip">İndir · v{CLIENT.version}</span>
          <h1 className="mt-5 text-4xl font-extrabold sm:text-5xl">PEMF Vet Client’ı indirin</h1>
          <p className="mx-auto mt-4 max-w-xl text-muted">
            Hafif client. Kurun; asıl uygulama client içinden inip “Başlat” ile açılır.
          </p>

          <div className="mx-auto mt-10 grid max-w-2xl gap-5 sm:grid-cols-2">
            <PlatformCard Icon={Windows} label="Windows" os={CLIENT.downloads.windows.os} url={CLIENT.downloads.windows.url} primary />
            <PlatformCard Icon={Apple} label="macOS" os={CLIENT.downloads.macos.os} url={CLIENT.downloads.macos.url} />
          </div>
        </div>
      </section>

      {/* Kurulumda profil seçimi (client içinde) */}
      <section className="border-b border-border/60">
        <div className="mx-auto max-w-5xl px-5 py-16 sm:px-6">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-bold sm:text-3xl">Kurulumda profilinizi seçin</h2>
            <p className="mt-3 text-muted">
              Client açılınca kullanım profil(ler)inizi seçersiniz; yalnız seçtiğiniz modeller iner.
              Çoklu seçim yapılabilir, dilediğiniz zaman değiştirebilirsiniz.
            </p>
          </div>
          <div className="mt-8 grid gap-5 sm:grid-cols-3">
            {MODULES.map((m) => (
              <div key={m.id} className="card p-6">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-semibold">{m.name}</h3>
                  <span className={`shrink-0 text-xs font-semibold ${m.included ? 'text-success' : 'text-primary'}`}>
                    {m.included ? 'Dahil' : `+₺${m.addonMonthly}/ay`}
                  </span>
                </div>
                <p className="mt-2 text-sm text-muted">{m.tagline}</p>
                <div className="mt-3 inline-flex items-center gap-1.5 text-xs text-muted">
                  <Download className="h-3.5 w-3.5" /> İndirme ≈ {m.sizeGB.toFixed(1)} GB
                </div>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-muted">
            Fiyatlandırma seviyeye (Pro / Pro+) bağlıdır; Araştırma modülü ücretli eklentidir. Bkz.{' '}
            <a href="/pricing" className="text-primary hover:underline">Fiyatlandırma</a>.
          </p>
        </div>
      </section>

      {/* Kurulumdan sonra ne olur */}
      <section className="border-b border-border/60">
        <div className="mx-auto max-w-5xl px-5 py-16 sm:px-6">
          <h2 className="text-2xl font-bold sm:text-3xl">Kurulumdan sonra</h2>
          <div className="mt-8 grid gap-6 md:grid-cols-3">
            {LAUNCHER_STEPS.map((s) => (
              <div key={s.step} className="flex gap-4">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary/12 text-sm font-bold text-primary ring-1 ring-primary/20">
                  {s.step}
                </span>
                <div>
                  <h3 className="font-semibold">{s.title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Sistem gereksinimleri */}
      <section>
        <div className="mx-auto max-w-5xl px-5 py-16 sm:px-6">
          <h2 className="text-2xl font-bold sm:text-3xl">Sistem gereksinimleri</h2>
          <div className="mt-8 grid gap-5 sm:grid-cols-2">
            <div className="card p-6">
              <div className="mb-3 inline-flex items-center gap-2 font-semibold"><Windows className="h-5 w-5" /> Windows</div>
              <ul className="space-y-2 text-sm text-muted">
                <li>• {CLIENT.downloads.windows.os}</li>
                <li>• 8 GB RAM (AI modelleri için 16 GB önerilir)</li>
                <li>• ~5 GB boş disk (uygulama + AI modelleri client’la iner)</li>
                <li>• İlk kurulum için internet bağlantısı</li>
              </ul>
            </div>
            <div className="card p-6">
              <div className="mb-3 inline-flex items-center gap-2 font-semibold"><Apple className="h-5 w-5" /> macOS</div>
              <ul className="space-y-2 text-sm text-muted">
                <li>• {CLIENT.downloads.macos.os}</li>
                <li>• Apple Silicon veya Intel</li>
                <li>• 8 GB RAM (16 GB önerilir)</li>
                <li>• İlk kurulum için internet bağlantısı</li>
              </ul>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
