// Author: mertaygn, cglrgrkn
import type { FC } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CLIENT, DOWNLOAD_HOST, LAUNCHER_STEPS, MODULES, FREE_MODE } from '../config'
import { Windows, Apple, Linux, Android, Check, Download } from '../components/Icons'
import { useDownloadGate, DownloadGateNote } from '../components/DownloadGate'
import { DownloadStats } from '../components/DownloadStats'
import type { DownloadTarget } from '../lib/download'

function PlatformCard({
  Icon,
  label,
  os,
  target,
  ready,
  altTarget,
  altLabel,
  alt2Target,
  alt2Label,
  primary,
  version,
}: {
  Icon: FC<{ className?: string }>
  label: string
  os: string
  /** URL yerine HEDEF anahtarı: adres çözümü tek yerde (lib/download.ts) kalsın. */
  target: DownloadTarget
  ready: boolean
  altTarget?: DownloadTarget
  altLabel?: string
  alt2Target?: DownloadTarget
  alt2Label?: string
  primary?: boolean
  /** Bu HEDEFİN sürümü — `CLIENT.version` DEĞİL (Android kartı 1.9.x yazıp 2.3.x APK veriyordu). */
  version: string
}) {
  const { loading, gated, download } = useDownloadGate()
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
      {ready ? (
        // Kapı: giriş yoksa modal açılır, giriş bitince indirme KENDİLİĞİNDEN başlar (ikinci tık yok).
        <button
          type="button"
          onClick={() => download(target)}
          disabled={loading}
          aria-busy={loading}
          aria-label={gated ? `${label} için giriş yapıp indir` : `${label} için indir`}
          className={`mt-6 ${primary ? 'btn-primary' : 'btn-ghost'} cursor-pointer disabled:cursor-wait disabled:opacity-60`}
        >
          <Download className="h-4 w-4" />
          {gated ? 'Giriş yap ve indir' : `${label} için indir`}
        </button>
      ) : (
        /* Metin denetimi 2026-08-20: devre dışı buton hiçbir ÇIKIŞ sunmuyordu (tarih yok, haber
           verme yok) — oysa ana sayfadaki aynı durum e-posta bağlantısı veriyor. İki yüzey artık
           aynı davranıyor. */
        <>
          <span className={`mt-6 ${primary ? 'btn-primary' : 'btn-ghost'} cursor-not-allowed opacity-60`} aria-disabled>
            <Download className="h-4 w-4" />
            Yakında
          </span>
          {/* ⚠️ href STATİK: `download-gate-wiring.test.ts` bu dosyada dinamik `href={...}`
              YASAKLAR — indirme kapısını atlayan bir bağlantı böyle sızabilir. Platform adını
              konuya gömmek yerine sabit konu kullanıyoruz (kapı korunur, kullanıcı yine yazar). */}
          <a
            href="mailto:ibiatechnology@gmail.com?subject=Yeni%20platform%20s%C3%BCr%C3%BCm%C3%BC%20haber%20ver"
            className="mt-2 text-center text-xs text-primary hover:underline"
          >
            Çıkınca haber ver
          </a>
        </>
      )}
      {altTarget && altLabel && (
        /* #20-followup: alt-link (AppImage) kendi appImageReady kapısına sahip → ana `ready` (.deb)
           koşuluna BAĞLAMA (aksi halde AppImage yalnız .deb de hazırsa görünür = bağımsız-yayın bozulur).
           Bu alt paketler de AYRI birer indirmedir → kapının DIŞINDA bırakılırsa arka kapı olurdu. */
        <button
          type="button"
          onClick={() => download(altTarget)}
          disabled={loading}
          className="mt-2 cursor-pointer text-center text-xs text-primary hover:underline disabled:opacity-60"
        >
          {altLabel}
        </button>
      )}
      {alt2Target && alt2Label && (
        <button
          type="button"
          onClick={() => download(alt2Target)}
          disabled={loading}
          className="mt-1 cursor-pointer text-center text-xs text-primary hover:underline disabled:opacity-60"
        >
          {alt2Label}
        </button>
      )}
      <div className="mt-4 space-y-1.5 text-xs text-muted">
        <div className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> Sürüm {version} · {CLIENT.releaseDate}</div>
        {/* İNDİRME BOYUTU (metin denetimi 2026-08-20): dört kartın hiçbirinde boyut yoktu;
            kullanıcı ne indireceğini bilmiyordu. Masaüstünde inen dosya KÜÇÜKTÜR (kurulum
            dosyası); asıl uygulama sonra iner — ikisi ayrı ayrı söylenir ki ne 3 MB'lık dosya
            "her şey bu" sanılsın ne de kullanıcı gereksiz yere ~5 GB'tan korksun. */}
        <div className="inline-flex items-center gap-1.5">
          <Check className="h-3.5 w-3.5 text-primary" />
          {target === 'android'
            ? 'Telefona tek dosya olarak iner'
            : `İndirilen kurulum dosyası ≈ ${CLIENT.sizeMB} MB · uygulama kurulum sırasında iner`}
        </div>
        {/* İki kart iki farklı sürüm gösteriyordu (1.9.32 ↔ 2.3.18) ve sebebi yazmıyordu;
            ayrıca telefon uygulamasının masaüstünün yanında mı çalıştığı hiç yazmıyordu. */}
        {target === 'android' && (
          <>
            <div className="text-[11px] leading-snug text-muted">{DOWNLOAD_HOST.androidRolNotu}</div>
            <div className="text-[11px] leading-snug text-muted">{DOWNLOAD_HOST.androidVersionNote}</div>
          </>
        )}
        {/* Eskiden düz "SHA-256 doğrulanır" yazıyordu; sitede yayımlanan bir hash yok, bu yüzden
            ziyaretçi indirdiği kurulum dosyasını KENDİSİ doğrulayamıyordu. İfadeyi gerçekte olan
            şeye bağla: bütünlük doğrulaması client'ın indirdiği uygulama paketi için yapılıyor. */}
        <div className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-primary" /> İnen dosyaların bütünlüğü kurulumda otomatik doğrulanır</div>
      </div>
    </div>
  )
}

export default function DownloadPage() {
  const [sp] = useSearchParams()
  const success = sp.get('checkout') === 'success'
  return (
    <>
      {success && (
        <div className="mx-auto max-w-5xl px-5 pt-6 sm:px-6">
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-sm text-success">
            ✓ Aboneliğiniz başladı. Aşağıdan PEMF Vet’i indirip aynı hesapla giriş yapın; planınız otomatik tanınır, ayrıca kod girmeniz gerekmez.
          </div>
        </div>
      )}
      <section className="bg-hero border-b border-border/60">
        <div className="mx-auto max-w-5xl px-5 py-16 text-center sm:px-6 sm:py-20">
          <span className="chip">İndir · v{CLIENT.version}</span>
          <h1 className="mt-5 text-4xl font-extrabold sm:text-5xl">PEMF Vet’i indirin</h1>
          <p className="mx-auto mt-4 max-w-xl text-muted">
            İndirdiğiniz küçük başlatıcıyı kurun; asıl uygulamayı o indirip kurar ve “Başlat” ile açılır.
          </p>
          {/* Kapı yalnız İNDİRME DÜĞMELERİNE uygulanır; sayfanın kalanı (gereksinimler, kurulum
              adımları, profiller) herkese açık kalır — aksi halde arama motoru boş sayfa görür. */}
          <DownloadGateNote />

          {/* İndirme sayacı (2026-08-06): veri çekilemezse KENDİNİ GİZLER — yanlış sayı
              göstermektense hiç göstermemek. "Kullanıcı" değil "indirme" der; oto-güncelleme
              aynı dosyayı yeniden indirdiği için benzersiz kişi sayısı DEĞİLDİR. */}
          <DownloadStats />

          <div className="mx-auto mt-10 grid max-w-5xl gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <PlatformCard Icon={Windows} label="Windows" os={CLIENT.downloads.windows.os} target="windows" ready={CLIENT.downloads.windows.ready} version={CLIENT.downloads.windows.version} primary />
            <PlatformCard Icon={Android} label="Android" os={CLIENT.downloads.android.os} target="android" ready={CLIENT.downloads.android.ready} version={CLIENT.downloads.android.version} />
            <PlatformCard Icon={Linux} label="Linux" os={CLIENT.downloads.linux.os} target="linux" ready={CLIENT.downloads.linux.ready} altTarget={CLIENT.downloads.linux.appImageReady ? 'linux-appimage' : undefined} altLabel=".AppImage (tüm dağıtımlar)" alt2Target={CLIENT.downloads.linux.rpmReady ? 'linux-rpm' : undefined} alt2Label=".rpm (Fedora / RHEL)" version={CLIENT.downloads.linux.version} />
            <PlatformCard Icon={Apple} label="macOS" os={CLIENT.downloads.macos.os} target="macos" ready={CLIENT.downloads.macos.ready} version={CLIENT.downloads.macos.version} />
          </div>
        </div>
      </section>

      {/* Kurulumda profil seçimi (client içinde) */}
      <section className="border-b border-border/60">
        <div className="mx-auto max-w-5xl px-5 py-16 sm:px-6">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-bold sm:text-3xl">Kurulumda profilinizi seçin</h2>
            <p className="mt-3 text-muted">
              Kurulum sırasında kullanım profilinizi seçersiniz; yalnız seçtiğiniz yapay zekâ modelleri iner.
              Birden fazla profil seçebilir, dilediğiniz zaman değiştirebilirsiniz.
            </p>
          </div>
          <div className="mt-8 grid gap-5 sm:grid-cols-3">
            {MODULES.map((m) => (
              <div key={m.id} className="card p-6">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-semibold">{m.name}</h3>
                  <span className={`shrink-0 text-xs font-semibold ${m.included ? 'text-success' : 'text-primary'}`}>
                    {FREE_MODE ? 'Ücretsiz' : m.included ? 'Dahil' : `+₺${m.addonMonthly}/ay`}
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
            {FREE_MODE ? (
              <>Test aşamasında <span className="font-medium text-fg/80">tüm profiller (Araştırma dahil) ücretsizdir</span> — dilediğinizi indirin.</>
            ) : (
              <>Evcil Hayvan Sahibi ve Veteriner profilleri planınıza dahildir; Araştırma profili ücretli
              eklentidir. Ayrıntılar{' '}
              <a href="/pricing" className="text-primary hover:underline">Fiyatlandırma</a> sayfasında.</>
            )}
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
          <div className="mt-8 grid gap-5 sm:grid-cols-3">
            <div className="card p-6">
              <div className="mb-3 inline-flex items-center gap-2 font-semibold"><Windows className="h-5 w-5" /> Windows</div>
              <ul className="space-y-2 text-sm text-muted">
                <li>• {CLIENT.downloads.windows.os}</li>
                <li>• 8 GB RAM (yapay zekâ modelleri için 16 GB önerilir)</li>
                <li>• 3–5 GB boş disk — kesin boyut seçtiğiniz profil sayısına göre değişir</li>
                <li>• İlk kurulum için internet bağlantısı</li>
              </ul>
            </div>
            <div className="card p-6">
              <div className="mb-3 inline-flex items-center gap-2 font-semibold"><Linux className="h-5 w-5" /> Linux</div>
              <ul className="space-y-2 text-sm text-muted">
                <li>• {CLIENT.downloads.linux.os}</li>
                <li>• 8 GB RAM (yapay zekâ modelleri için 16 GB önerilir)</li>
                <li>• 3–5 GB boş disk — kesin boyut seçtiğiniz profil sayısına göre değişir</li>
                <li>• İlk kurulum için internet bağlantısı</li>
              </ul>
            </div>
            <div className="card p-6">
              <div className="mb-3 inline-flex items-center gap-2 font-semibold"><Apple className="h-5 w-5" /> macOS</div>
              <ul className="space-y-2 text-sm text-muted">
                <li>• {CLIENT.downloads.macos.os} · Apple Silicon / Intel</li>
                <li>• 8 GB RAM (yapay zekâ modelleri için 16 GB önerilir)</li>
                <li>• 3–5 GB boş disk — kesin boyut seçtiğiniz profil sayısına göre değişir</li>
                <li>• İlk kurulum için internet bağlantısı</li>
              </ul>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
