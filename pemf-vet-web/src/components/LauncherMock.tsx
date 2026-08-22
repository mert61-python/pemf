// Author: mertaygn, cglrgrkn
import { BRAND, CLIENT } from '../config'
import { Check, Logo, Refresh } from './Icons'

/* PEMF Vet Client önizlemesi — saf CSS pencere mockup'ı (ekran görüntüsü DEĞİL).
 *
 * ⚠️ 2026-08-12 — GERÇEK CLIENT'A GÖRE YENİDEN ÇİZİLDİ. Önceki hâli client'ın ARTIK OLMAYAN
 * bir sürümünü gösteriyordu: macOS trafik-ışığı noktaları, "PEMF Vet Dashboard", "Cihaz Durumu"
 * satırı ve Frekans/Yoğunluk/Süre metrik kutuları. Client bunların hiçbirini göstermiyor;
 * kurulum sonrası ekranı "Hazır!" + profil rozetleri + Başlat'tır. Sitede ürünün yanlış bir
 * resmini göstermek, indirmeden önce beklenti oluşturur ve ilk açılışta kafa karıştırır.
 *
 * ⚠️ NEDEN EKRAN GÖRÜNTÜSÜ DEĞİL: gerçek client başlığında OTURUM AÇMIŞ KULLANICININ
 * E-POSTASI yazar. Halka açık pazarlama sayfasına konacak bir ekran görüntüsü o adresi de
 * yayınlar. Mockup'ta kimlik alanı hiç yok; ayrıca sürüm/ünvan tek kaynaktan gelir
 * (`CLIENT.version`, `BRAND.company`) — ekran görüntüsü ise her yayında bayatlar.
 *
 * "Yoğunluk 0 mT" metriği de bu vesileyle kalktı: girilen mT değeri cihaza HİÇ ulaşmıyor
 * (ne STM paketinde ne ESP komutunda alan var) ve bu iddia raporlardan zaten kaldırılmıştı.
 */
const chrome = { background: 'oklch(14% 0.015 260)' }
const bg = { background: 'oklch(17% 0.025 230)' }
const kutu = { background: 'oklch(22% 0.03 200)' }

/** Kurulu profil rozeti — client'ta olduğu gibi onay işaretli. */
function Profil({ ad }: { ad: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 px-3 py-1.5 text-[11px] font-semibold text-primary/90"
      style={kutu}
    >
      <Check className="h-3 w-3" /> {ad}
    </span>
  )
}

export default function LauncherMock() {
  return (
    <div className="glow-ring overflow-hidden rounded-xl border border-white/10" style={bg}>
      {/* Başlık çubuğu — logo + ürün adı solda, sürüm rozeti sağda (client ile aynı düzen) */}
      <div className="flex items-center gap-2.5 border-b border-white/8 px-4 py-3" style={chrome}>
        <span
          className="grid h-7 w-7 shrink-0 place-items-center rounded-lg"
          style={{ background: 'oklch(30% 0.07 190)' }}
        >
          <Logo className="h-4 w-4 text-primary" />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-xs font-bold text-white/90">PEMF Vet</span>
          <span className="block truncate text-[10px] text-white/40">
            Veteriner PEMF seans + yapay zekâ teşhis platformu
          </span>
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2">
          <span className="hidden items-center rounded-md border border-white/10 text-[10px] font-semibold sm:inline-flex">
            <span className="rounded-l-md bg-primary px-1.5 py-0.5 text-[oklch(17%_0.03_200)]">TR</span>
            <span className="px-1.5 py-0.5 text-white/40">EN</span>
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-white/55">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'oklch(72% 0.17 152)' }} />
            v{CLIENT.version}
          </span>
        </span>
      </div>

      {/* Gövde — client'ın kurulum-sonrası "Hazır!" ekranı */}
      <div className="px-5 py-8 text-center">
        <span
          className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-primary/20"
          style={kutu}
        >
          <Check className="h-7 w-7 text-primary" />
        </span>

        <div className="mt-4 text-xl font-bold text-white/95">Hazır!</div>
        <p className="mx-auto mt-1.5 max-w-xs text-[11px] leading-relaxed text-white/45">
          PEMF Vet kuruldu. Uygulamayı başlatın veya profillerinizi güncelleyin.
        </p>

        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          <Profil ad="Evcil Hayvan Sahibi" />
          <Profil ad="Araştırma Modu" />
          <Profil ad="Veteriner Hekim" />
        </div>

        <button
          type="button"
          tabIndex={-1}
          aria-hidden="true"
          className="mt-6 inline-flex items-center gap-2 rounded-full px-8 py-3 text-sm font-bold text-[oklch(17%_0.03_200)]"
          style={{ background: 'linear-gradient(180deg, oklch(76% 0.15 178), oklch(68% 0.14 182))' }}
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
            <path d="M8 5v14l11-7z" />
          </svg>
          Başlat
        </button>

        <div className="mt-5 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[11px] text-white/40">
          <span className="inline-flex items-center gap-1.5">
            <Refresh className="h-3 w-3" /> Profilleri değiştir
          </span>
          {/* Maket, uygulamanın GERÇEK düğme metnini göstermeli (launcher I18N `repair`). */}
          <span>Kurulumu onar</span>
          <span>Uygulamayı kaldır</span>
        </div>
      </div>

      {/* Alt bilgi — ünvan TEK KAYNAK (`BRAND.company`) */}
      <div className="border-t border-white/8 px-4 py-2.5 text-center text-[10px] text-white/30" style={chrome}>
        © {BRAND.company}
      </div>
    </div>
  )
}
