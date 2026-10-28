/**
 * I18N-P1 · site-12a-sayfa — ana sayfa, özellikler, destek, 404, ekran görüntüleri galerisi, başlatıcı maketi, kök hata ekranı ve
 * `index.html` başlığı/açıklaması. GERÇEK bileşenler (sunucu tarafı çizim), gerçek katalog.
 * Türkçe (bayrak kapalı) göç öncesiyle BAYT BAYT aynı metin (altın tablo = eski kaynak dizgileri); bayrak açık + İngilizce seçilince
 * her satırın İngilizcesi görünür ve Türkçesi KALMAZ. Her çift, ilgili çeviri kaldırılırsa / Türkçe değer bozulursa KIRMIZI olur.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import INDEX_HTML from '../../../index.html?raw'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true
const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
const meta = {
  content: '',
  setAttribute(ad: string, deger: string) {
    if (ad === 'content') this.content = deger
  },
}
const belge = {
  documentElement: { lang: '' },
  title: '',
  querySelector: (s: string) => (s === 'meta[name="description"]' ? meta : null),
}
vi.stubGlobal('document', belge)

const i18nMod = await import('../index')
const dilMod = await import('../dil')
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const Home = (await import('../../pages/Home')).default
const Features = (await import('../../pages/Features')).default
const Support = (await import('../../pages/Support')).default
const NotFound = (await import('../../pages/NotFound')).default
const AppScreenshots = (await import('../../components/AppScreenshots')).default
const LauncherMock = (await import('../../components/LauncherMock')).default
const { ErrorBoundary } = await import('../../components/ErrorBoundary')
const { AuthProvider } = await import('../../context/AuthContext')
const { AuthModalProvider } = await import('../../context/AuthModal')
const { CLIENT, COMPANY, PATCH } = await import('../../config')

const temizle = (h: string) => h.replace(/<!-- -->/g, '')
const ciz = (bilesen: unknown) =>
  renderToString(createElement(MemoryRouter, null, createElement(AuthProvider, null, createElement(AuthModalProvider, null, createElement(bilesen as never)))))
const cizHata = () => {
  const eb = new ErrorBoundary({ children: null })
  eb.state = { hasError: true }
  return renderToString(eb.render() as never)
}

/**
 * Çizilen HTML'in metin düğümleri (React'in `<!-- -->` ayracıyla ayrılmış HAM düğümleri) + öznitelik değerleri. Eşleşme TAM düğüm eşitliğidir: "Ekranlarla tanıyın!" (bozuk değer), alt metne
 * gömülü başlık ya da çıplak anahtar adı sızması YAKALANIR. `~` önekli dizgi (öznitelik içi parça) alt dizgi olarak aranır.
 */
const dugumler = (h: string): Set<string> => {
  const s = new Set<string>(h.split(/<[^>]*>/))
  for (const m of h.matchAll(/="([^"]*)"/g)) s.add(m[1])
  return s
}
const var_ = (h: string, d: Set<string>, s: string) => (s.startsWith('~') ? temizle(h).includes(s.slice(1)) : d.has(s))

type Cift = [tr: string, en: string]
const SHOTS: Cift[] = [
  ['Profil Seçimi', 'Profile Selection'],
  ['Evcil Hayvan Sahibi · Veteriner · Araştırma', 'Pet Owner · Veterinarian · Research'],
  ['Akıllı Teşhis', 'Smart Diagnosis'],
  ['Kameradan anlık ağrı analizi', 'Instant pain analysis from the camera'],
  ['Yapay Zekâ Merkezi', 'AI Hub'],
  ['Görüntü, ses ve sinyal modelleri', 'Image, audio and signal models'],
  ['AI Pro · Otomatik Seans', 'AI Pro · Automatic Session'],
  ['Ölçümlere göre kendini ayarlayan seans', 'A session that adjusts itself to the measurements'],
  ['Cihaz Kontrolü', 'Device Control'],
  ['7 bobin, frekans ve süre ayarı', '7 coils, frequency and duration settings'], // D6.65: STM 7 bobin (ESP kapalı, Y37) — TR DEĞİŞTİ
  ['Canlı İzleme Paneli', 'Live Monitoring Panel'],
  ['Seans ve sensör ölçümleri', 'Session and sensor measurements'],
  ['Hasta Veritabanı', 'Patient Database'],
  ['Klinik içi hasta ve seans kaydı', 'In-clinic patient and session records'],
  ['Yapay zekâ analiz geçmişi', 'AI analysis history'],
  ['Şifreli, aranabilir analiz arşivi', 'Encrypted, searchable analysis archive'],
]
const GALERI: Cift[] = [
  ['Ekranlarla tanıyın', 'See it in screens'],
  ['Profil seçiminden yapay zekâ teşhisine, otomatik seanstan hasta arşivine — telefon uygulamasından ekran görüntüleri.', 'From profile selection to AI diagnosis, from automatic sessions to the patient archive — screenshots from the mobile app.'],
  ['Önceki', 'Previous'],
  ['Sonraki', 'Next'],
  ['PEMF Vet — Profil Seçimi', 'PEMF Vet — Profile Selection'],
  ['← kaydırın →', '← swipe →'],
  ...SHOTS,
]
const MAKET: Cift[] = [
  ['Veteriner PEMF seans + yapay zekâ teşhis platformu', 'Veterinary PEMF session + AI diagnostics platform'],
  ['Hazır!', 'Ready!'],
  ['PEMF Vet kuruldu. Uygulamayı başlatın veya profillerinizi güncelleyin.', 'PEMF Vet is installed. Start the app or update your profiles.'],
  ['Evcil Hayvan Sahibi', 'Pet Owner'],
  ['Araştırma', 'Research'],
  ['Veteriner Hekim', 'Veterinarian'],
  ['Başlat', 'Start'],
  [' Profilleri değiştir', ' Change profiles'],
  ['Kurulumu onar', 'Repair installation'],
  ['Uygulamayı kaldır', 'Uninstall'],
]
const HOME: Cift[] = [
  ['Veteriner kliniğiniz için elektromanyetik alan terapisini tek ekrandan yönetin.', 'Manage electromagnetic field therapy for your veterinary clinic from a single screen.'],
  ['PEMF Vet’i indirin', 'Download PEMF Vet'],
  ['— uygulama, cihaz yazılımı ve yapay zekâ modelleri sizin için kurulur, güncellemeler kendiliğinden gelir.', '— the app, device software and AI models are installed for you, and updates arrive on their own.'],
  ['macOS · Linux yakında', 'macOS · Linux coming soon'],
  [`Sürüm ${CLIENT.version} · ${CLIENT.downloads.windows.sizeMB} MB kurulum`, `Version ${CLIENT.version} · ${CLIENT.downloads.windows.sizeMB} MB installer`],
  ['Nasıl çalışır', 'How it works'],
  ['Tek indirme, gerisi otomatik', 'One download, the rest is automatic'],
  ['Küçük bir kurulum dosyası indirirsiniz; uygulamayı, modelleri ve güncellemeleri o getirir.', 'You download a small installer; it fetches the app, the models and the updates.'],
  ['Klinik için tasarlandı', 'Built for the clinic'],
  ['Cihaz bağlantısından yapay zekâ teşhisine kadar her şey tek uygulamada.', 'From device connection to AI diagnosis, everything in one app.'],
  ['Kurulum profilleri', 'Installation profiles'],
  ['Herkes kendi ihtiyacını kurar', 'Everyone installs what they need'],
  ['Evcil Hayvan Sahibi, Veteriner ve Araştırma — kurulumda seçtiğiniz profile göre yalnız işinize yarayan yapay zekâ modelleri iner. Evcil hayvan sahibi, ağır araştırma modellerini indirmez.', 'Pet Owner, Veterinarian and Research — depending on the profile you choose during installation, only the AI models you need are downloaded. A pet owner does not download the heavy research models.'],
  ['İhtiyacınıza göre plan', 'A plan that fits your needs'],
  ['Planınız, ayda kaç yapay zekâ analizi yapabileceğinizi belirler. Her analiz 1 jeton harcar.', 'Your plan sets how many AI analyses you can run each month. Each analysis uses 1 credit.'],
]
const OZELLIKLER: Cift[] = [
  ['Uçtan uca terapi kontrolü', 'End-to-end therapy control'],
  ['Cihaz bağlantısından yapay zekâya, hasta yönetiminden güvenliğe — hepsi tek uygulamada.', 'From device connection to AI, from patient management to security — all in one app.'],
  ['Masaüstü uygulaması', 'Desktop app'],
  ['Tek pencereden yönetim', 'Manage everything from a single window'],
  [`Son güncelleme · v${PATCH.version}`, `Latest update · v${PATCH.version}`],
  ['Başlamaya hazır mısınız?', 'Ready to get started?'],
  ['PEMF Vet’i indirin; kurulum ve güncellemeler otomatik.', 'Download PEMF Vet; installation and updates are automatic.'],
  ['PEMF Vet’i İndir', 'Download PEMF Vet'],
]
const DESTEK: Cift[] = [
  ['Sık sorulan sorular', 'Frequently asked questions'],
  ['Kurulum, kullanım ve abonelik hakkında en çok merak edilenler.', 'The most common questions about installation, usage and subscription.'],
  ['Hâlâ yardıma mı ihtiyacınız var?', 'Still need help?'],
  // D6.31 (B-7.15): yanıt süresi plan karşılaştırmasının en uzun süresine (Başlangıç "2 iş günü") indirildi — TR DEĞİŞTİ
  ['Kurulum, abonelik ya da kliniğinize özel çözümler için bize yazın; en geç iki iş günü içinde dönüş yapıyoruz.', 'Write to us for installation, subscription or clinic-specific solutions; we reply within two business days at the latest.'],
  ['PEMF Vet’i İndir', 'Download PEMF Vet'],
  ['Hafta içi 09:00–18:00 arası ulaşabilirsiniz; e-postalara en geç iki iş günü içinde dönüyoruz.', 'You can reach us on weekdays between 09:00 and 18:00; we reply to emails within two business days at the latest.'],
]
const BULUNAMADI: Cift[] = [
  ['Sayfa yok', 'No such page'],
  ['Sayfa bulunamadı', 'Page not found'],
  ['Aradığınız sayfa taşınmış veya hiç var olmamış olabilir. Aşağıdaki bağlantılardan devam edebilirsiniz.', 'The page you are looking for may have been moved or may never have existed. You can continue from the links below.'],
  ['Ana sayfaya dön', 'Back to the home page'],
]
const HATA: Cift[] = [
  ['Bir şeyler ters gitti', 'Something went wrong'],
  ['Sayfa yüklenirken beklenmeyen bir hata oluştu. Sayfayı yenilemeyi deneyin; sorun sürerse ', 'An unexpected error occurred while loading the page. Try reloading the page; if the problem continues, write to '],
  ['~</a> adresine yazın.', '~</a>.'],
  ['~subject=Site%20hatas%C4%B1', '~subject=Site%20error'],
  ['Sayfayı yenile', 'Reload the page'],
  ['Ana sayfaya dön', 'Back to the home page'],
]
/** Aynı Türkçe dizgi, başka (henüz göçmemiş) kaynaktan da çizilir: config.ts LAUNCHER_STEPS başlığı (site-12c-config göçünde bu satır SİLİNİR). */
const BASKA_KAYNAK_12C = new Set<string>(['PEMF Vet’i indirin'])
const SAYFALAR: [ad: string, ciz: () => string, ciftler: Cift[]][] = [
  ['AppScreenshots', () => ciz(AppScreenshots), GALERI],
  ['LauncherMock', () => ciz(LauncherMock), MAKET],
  ['Home', () => ciz(Home), HOME],
  ['Features', () => ciz(Features), OZELLIKLER],
  ['Support', () => ciz(Support), DESTEK],
  ['NotFound', () => ciz(NotFound), BULUNAMADI],
  ['ErrorBoundary', () => cizHata(), HATA],
]

const indexBaslik = /<title>([^<]*)<\/title>/.exec(INDEX_HTML)![1]
const indexAciklama = /name="description"\s+content="([^"]*)"/.exec(INDEX_HTML)![1]

afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

describe('site-12a-sayfa', () => {
  for (const [ad, cizici, ciftler] of SAYFALAR) {
    it(`${ad} · Türkçe (bayrak kapalı): göç öncesiyle aynı metin`, () => {
      const h = cizici()
      const d = dugumler(h)
      for (const [tr] of ciftler) expect(var_(h, d, tr), `${ad}: ${tr}`).toBe(true)
    })

    it(`${ad} · bayrak AÇIK + İngilizce: her satır İngilizce, Türkçe kalmaz`, async () => {
      dilMod.__bayrakTestiAyarla(true)
      await i18nMod.dilSec('en')
      const h = cizici()
      const d = dugumler(h)
      for (const [tr, en] of ciftler) {
        expect(var_(h, d, en), `${ad} EN: ${en}`).toBe(true)
        // Aynı satırın Türkçesi KALMAMALI (başka kaynaktan çizilenler hariç)
        if (BASKA_KAYNAK_12C.has(tr)) continue
        expect(var_(h, d, tr), `${ad} TR kaldı: ${tr}`).toBe(false)
      }
    })
  }

  it('ErrorBoundary · e-posta bağlantısı iki dilde de yerinde ve adresi gösterir', async () => {
    for (const dil of ['tr', 'en'] as const) {
      dilMod.__bayrakTestiAyarla(dil === 'en')
      await i18nMod.dilSec(dil)
      const h = cizHata()
      expect(h).toContain(`href="mailto:${COMPANY.email}?subject=`)
      expect(h).toContain(`>${COMPANY.email}</a>`)
    }
  })

  it('index.html başlığı ve açıklaması: Türkçe değer statik dosyayla BAYT BAYT aynı; İngilizce seçilince çalışma anında değişir', async () => {
    // modül yüklenirken (bayrak kapalı, tr) yazıldı
    expect(belge.title).toBe(indexBaslik)
    expect(meta.content).toBe(indexAciklama)
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    expect(belge.title).toBe('PEMF Vet — Veterinary PEMF Therapy Software')
    expect(belge.title).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/)
    expect(meta.content).toMatch(/^PEMF Vet: desktop software/)
    expect(meta.content).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/)
    await i18nMod.dilSec('tr')
    expect(belge.title).toBe(indexBaslik)
    expect(meta.content).toBe(indexAciklama)
  })
})
