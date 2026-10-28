/**
 * I18N-P1 · site-12b-indirme-hesap — indirme düğmeleri / kapı notu / istatistik / paket hesaplayıcı / indirme sayfası, hesap menüsü /
 * giriş-kayıt penceresi / iniş sayfası / şifre sıfırlama ve giriş-ödeme hata iletileri. GERÇEK bileşenler (sunucu tarafı çizim), gerçek katalog;
 * yalnız oturum bağlamları (AuthContext / AuthModal) sahtelenir (oturum yok / var).
 *  · ALTIN: göç ÖNCESİ kaynaktan alınan Türkçe değerler (141 anahtar; her biri HEAD kaynağında birebir doğrulandı) — katalog bunlardan sapmaz.
 *  · Çizim: Türkçe (bayrak kapalı) eski dizgilerle TAM metin düğümü eşitliği; bayrak AÇIK + İngilizce → her satırın İngilizcesi, Türkçesi KALMAZ.
 *  · İşlevler: Supabase / ödeme hata iletileri iki dilde (eşleşme sırası değişmez), şifre kuralı etkin dile göre okunur.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EN, TR, kullanilanAnahtarlar } from '../../__tests__/_kaynakMetni'
import ACCOUNT_SRC from '../../components/AccountButton.tsx?raw'
import BUTTONS_SRC from '../../components/DownloadButtons.tsx?raw'
import GATE_SRC from '../../components/DownloadGate.tsx?raw'
import STATS_SRC from '../../components/DownloadStats.tsx?raw'
import PACKAGE_SRC from '../../components/PackageBuilder.tsx?raw'
import MODAL_SRC from '../../context/AuthModal.tsx?raw'
import HATALAR_SRC from '../../lib/authHatalari.ts?raw'
import AUTHROUTE_SRC from '../../pages/AuthRoute.tsx?raw'
import DOWNLOAD_SRC from '../../pages/Download.tsx?raw'
import RESET_SRC from '../../pages/ResetPassword.tsx?raw'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true
const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })

const oturum = vi.hoisted(() => ({ session: null as unknown, email: null as string | null }))
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    session: oturum.session,
    email: oturum.email,
    ready: true,
    loading: false,
    signOut: () => {},
    signIn: async () => ({}),
    signUp: async () => ({}),
    resetPassword: async () => ({}),
  }),
  AuthProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../../context/AuthModal', () => ({
  useAuthModal: () => ({ requireAuth: () => {} }),
  AuthModalProvider: ({ children }: { children: unknown }) => children,
}))

const i18nMod = await import('../index')
const dilMod = await import('../dil')
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const AccountButton = (await import('../../components/AccountButton')).default
const DownloadButtons = (await import('../../components/DownloadButtons')).default
const PackageBuilder = (await import('../../components/PackageBuilder')).default
const DownloadPage = (await import('../../pages/Download')).default
const AuthRoute = (await import('../../pages/AuthRoute')).default
const ResetPassword = (await import('../../pages/ResetPassword')).default
const { authHatasiTurkce, odemeHatasiTurkce, SIFRE_KURALI, sifreGecerliMi } = await import('../../lib/authHatalari')
const { CLIENT, COMPANY, FREE_MODE, MODULES } = await import('../../config')

/** Altın tablo: anahtar → göç ÖNCESİ Türkçe değer. */
const ALTIN: Record<string, string> = {
  "hesap.abonelik.evetIptal": "Evet, iptal et",
  "hesap.abonelik.iptalEdildi": "Aboneliğiniz iptal edildi; otomatik yenileme durduruldu.",
  "hesap.abonelik.iptalEdiliyor": "İptal ediliyor…",
  "hesap.abonelik.iptalEt": "Aboneliği iptal et",
  "hesap.abonelik.iptalSorusu": "Aboneliğiniz iptal edilsin mi? Otomatik yenileme durur ve bir daha ücret alınmaz.",
  "hesap.abonelik.testAsamasi": "Test aşamasındayız: tüm planlar şu an ücretsiz, sizden ödeme alınmıyor.",
  "hesap.abonelik.vazgec": "Vazgeç",
  "hesap.alan.adSoyad": "Ad Soyad",
  "hesap.alan.bolum": "Bölüm / anabilim dalı",
  "hesap.alan.eposta": "E-posta",
  "hesap.alan.epostaKurumsal": "E-posta (kurumsal olması gerekmez)",
  "hesap.alan.klinikAdi": "Klinik / hastane adı",
  "hesap.alan.klinikBilgileri": "Klinik bilgileri",
  "hesap.alan.kurumAdi": "Üniversite / kurum / enstitü",
  "hesap.alan.kurumBilgileri": "Kurum bilgileri",
  "hesap.alan.sehir": "Şehir",
  "hesap.alan.sifre": "Şifre",
  "hesap.alan.sifreKurala": "Şifre ({{kural}})",
  "hesap.alan.telefon": "Telefon",
  "hesap.alan.unvan": "Akademik unvan (isteğe bağlı)",
  "hesap.alan.veterinerOda": "Veteriner oda / diploma no (isteğe bağlı)",
  "hesap.bekleyin": "Lütfen bekleyin…",
  "hesap.bilgi.dogrulama": "Doğrulama e-postası gönderildi. Onayladıktan sonra giriş yapın.",
  "hesap.bilgi.dogrulamaIndirme": "Doğrulama e-postası gönderildi. Onaylayıp buradan giriş yapın — indirme kaldığı yerden devam eder.",
  "hesap.bilgi.sifirlamaGonderildi": "Şifre sıfırlama bağlantısı e-postanıza gönderildi. E-postanızı kontrol edin.",
  "hesap.cikisYap": "Çıkış yap",
  "hesap.girisYap": "Giriş yap",
  "hesap.girisYapildi": "Giriş yapıldı",
  "hesap.girisYapin": "Giriş yapın",
  "hesap.hata.beklenmeyen": "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.",
  "hesap.hata.cokFazlaDeneme": "Çok fazla deneme yapıldı. Lütfen birkaç dakika sonra tekrar deneyin.",
  "hesap.hata.cokSikDenendi": "Çok sık denendi. Güvenlik gereği kısa bir süre beklemeniz gerekiyor; birkaç saniye sonra tekrar deneyin.",
  "hesap.hata.epostaDogrulanmadi": "E-posta adresiniz henüz doğrulanmadı. Size gönderdiğimiz doğrulama bağlantısına tıklayın, sonra tekrar giriş yapın.",
  "hesap.hata.epostaGecersiz": "E-posta adresi geçerli görünmüyor. Adresi kontrol edip tekrar deneyin.",
  "hesap.hata.epostaGirin": "Önce e-posta adresinizi girin.",
  "hesap.hata.epostaKabulEdilmedi": "Bu e-posta adresi kabul edilmedi. Farklı bir adres deneyin.",
  "hesap.hata.epostaSifreHatali": "E-posta veya şifre hatalı. Şifrenizi hatırlamıyorsanız \"Şifremi unuttum\" bağlantısını kullanın.",
  "hesap.hata.hesapZatenVar": "Bu e-posta adresiyle zaten kayıtlı bir hesap var. Giriş yapmayı ya da \"Şifremi unuttum\" ile şifrenizi yenilemeyi deneyin.",
  "hesap.hata.islemTamamlanamadi": "İşlem tamamlanamadı. Lütfen tekrar deneyin; sorun sürerse {{email}} adresine yazın.",
  "hesap.hata.sifreAyni": "Yeni şifre eskisiyle aynı olamaz. Farklı bir şifre belirleyin.",
  "hesap.hata.sifreZayif": "Şifre yeterince güçlü değil. {{aciklama}}",
  "hesap.hata.sifrelerEslesmiyor": "Şifreler eşleşmiyor.",
  "hesap.hata.sunucuyaUlasilamadi": "Sunucuya ulaşılamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.",
  "hesap.hesabim": "Hesabım",
  "hesap.hesabinizVar": "Zaten hesabınız var mı? ",
  "hesap.hesabinizYok": "Hesabınız yok mu? ",
  "hesap.hesapOlustur": "Hesap oluştur",
  "hesap.jeton.aylikHak": "{{sayi}} aylık hak (dönem sonunda yenilenir) ·",
  "hesap.jeton.satinAlinan": "{{sayi}} satın alınan (süresi dolmaz)",
  "hesap.jetonNotu": "Jetonunuz yalnız yapay zekâ analizlerinde harcanır; seans ve acil durdurma jetondan bağımsızdır.",
  "hesap.kalanJeton": "Kalan jeton",
  "hesap.kapat": "Kapat",
  "hesap.kayit.gizlilik": "Gizlilik Politikası",
  "hesap.kayit.kullanimSartlari": "Kullanım Şartları",
  "hesap.kayit.kvkk": "KVKK Aydınlatma Metni",
  "hesap.kayit.once": "Kayıt olarak",
  "hesap.kayit.sonrasi": "'nı kabul edersiniz.",
  "hesap.kayit.ve": " ve",
  "hesap.kayitOl": "Kayıt ol",
  "hesap.kayitOlun": "Kayıt olun",
  "hesap.odeme.abonelikYok": "Hesabınızda aktif bir abonelik görünmüyor. Sorun sürerse {{email}} adresine yazın.",
  "hesap.odeme.bankaDogrulamadi": "Bankanız işlemi doğrulayamadı. Kart bilgilerinizi kontrol edip tekrar deneyin.",
  "hesap.odeme.tahsilEdilemedi": "Ödeme kartınızdan tahsil edilemedi (limit/bakiye). Farklı bir kartla tekrar deneyebilirsiniz.",
  "hesap.pencere.abonelikAciklama": "Aboneliğiniz bu hesaba tanımlanır (mobil ve masaüstü ile aynı).",
  "hesap.pencere.formdaKal": "Vazgeç, formda kal",
  "hesap.pencere.hesapTuru": "Hesap türü",
  "hesap.pencere.indirmeAciklama": "İndirme için ücretsiz hesap yeterli — kart bilgisi istenmez. Giriş yapınca indirme kendiliğinden başlar.",
  "hesap.pencere.kapatmaSorusu": "Girdiğiniz bilgiler kaybolacak. Pencere kapatılsın mı?",
  "hesap.pencere.servisYok": "Giriş servisine şu anda ulaşılamıyor. Kısa süre sonra tekrar deneyin; sürerse{{eposta}} adresine yazın.",
  "hesap.rota.giris.aciklama": "Hesabınızla giriş yapın. Pencere kapandıysa aşağıdaki düğmeyle yeniden açabilirsiniz.",
  "hesap.rota.giris.dugme": "Giriş penceresini aç",
  "hesap.rota.kayit.aciklama": "Ücretsiz hesap masaüstü uygulaması, telefon uygulaması ve bu site için ortaktır; kart bilgisi istenmez. Kayıt penceresi kapandıysa aşağıdaki düğmeyle yeniden açabilirsiniz.",
  "hesap.rota.kayit.dugme": "Kayıt penceresini aç",
  "hesap.rota.rozet": "Hesap",
  "hesap.rota.sifre.aciklama": "Giriş penceresinde e-postanızı yazıp \"Şifremi unuttum\" bağlantısına basın; size yeni şifre belirleme bağlantısı göndeririz. Pencere kapandıysa aşağıdaki düğmeyle yeniden açabilirsiniz.",
  "hesap.sifirla.anaSayfaBaglanti": "ana sayfadan giriş penceresini açıp",
  "hesap.sifirla.baslik": "Yeni şifre belirle",
  "hesap.sifirla.dogrulaniyor": "Sıfırlama bağlantısı doğrulanıyor… Bu mesaj kalıcıysa bağlantının süresi dolmuş olabilir. Yeni bir bağlantı almak için",
  "hesap.sifirla.girisYapabilirsiniz": "Yeni şifrenizle giriş yapabilirsiniz.",
  "hesap.sifirla.guncelle": "Şifreyi güncelle",
  "hesap.sifirla.guncellendi": "Şifreniz güncellendi",
  "hesap.sifirla.guncelleniyor": "Güncelleniyor…",
  "hesap.sifirla.tekrarlayin": "“Şifremi unuttum” adımını tekrarlayın.",
  "hesap.sifirla.yeniSifre": "Yeni şifre",
  "hesap.sifirla.yeniSifreTekrar": "Yeni şifre (tekrar)",
  "hesap.sifreKurali": "En az 8 karakter; büyük harf, küçük harf ve rakam içermeli.",
  "hesap.sifremiUnuttum": "Şifremi unuttum",
  "hesap.tur.arastirmaci": "Araştırmacı / Kurum",
  "hesap.tur.bireyselAlt": "Bireysel kullanım",
  "hesap.tur.klinikAlt": "Klinik bilgileriyle",
  "hesap.tur.kurumAlt": "Üniversite · enstitü",
  "hesap.tur.veteriner": "Veteriner Hekim / Klinik",
  "indirme.abonelikBasladi": "✓ Aboneliğiniz başladı. Aşağıdan PEMF Vet’i indirip aynı hesapla giriş yapın; planınız otomatik tanınır, ayrıca kod girmeniz gerekmez.",
  "indirme.appImage": ".AppImage (tüm dağıtımlar)",
  "indirme.baslaticiAciklama": "İndirdiğiniz başlatıcıyı kurun; asıl uygulamayı o indirip kurar ve “Başlat” ile açılır.",
  "indirme.butunluk": " İnen dosyaların bütünlüğü kurulumda otomatik doğrulanır",
  "indirme.gereksinim.baslik": "Sistem gereksinimleri",
  "indirme.gereksinim.disk": "• 4–12 GB boş disk — kesin boyut seçtiğiniz profil sayısına göre değişir", // D6.66: başlatıcının disk kuralı (2 × indirme + %10) — TR DEĞİŞTİ
  "indirme.gereksinim.internet": "• İlk kurulum için internet bağlantısı",
  "indirme.gereksinim.ram": "• 8 GB RAM (yapay zekâ modelleri için 16 GB önerilir)",
  "indirme.girisYapVeIndir": "Giriş yap ve indir",
  "indirme.girisYapipIndir": "{{label}} için giriş yapıp indir",
  "indirme.haberBaglanti": "bize yazın",
  "indirme.haberOnce": "Çıkınca haber vermemiz için",
  "indirme.haberVer": "Çıkınca haber ver",
  "indirme.icinIndir": "{{label}} için indir",
  "indirme.istatistik.aciklama": "E-posta adresi doğrulanmış hesap sayısı ile son 30 günde bağlanan cihaz sayısıdır.",
  "indirme.istatistik.aktifCihaz": "Aktif cihaz (30 gün)",
  "indirme.istatistik.kayitliKullanici": "Kayıtlı kullanıcı",
  "indirme.kapiNotu": "İndirmek için ücretsiz hesap oluşturun veya giriş yapın — aynı hesapla uygulamaya ve destek taleplerinize giriş yaparsınız. Kart bilgisi istenmez.",
  "indirme.kurulumDosyasi": "İndirilen kurulum dosyası ≈ {{sizeMB}} MB · uygulama kurulum sırasında iner",
  "indirme.kurulumSonrasi": "Kurulumdan sonra",
  "indirme.paket.ayArti": "+{{tutar}}/ay",
  "indirme.paket.aylikEklenti": "Aylık eklenti",
  "indirme.paket.aylikEklentiEk": "+{{tutar}}/ay eklenti",
  "indirme.paket.onerilen": "Önerilen",
  "indirme.paket.planaDahil": "Planınıza dahil",
  "indirme.paket.planaDahilNotu": "Evcil Hayvan Sahibi ve Veteriner profilleri planınıza dahildir; Araştırma ücretli eklentidir.",
  "indirme.paket.seciliProfil": "Seçili profil",
  "indirme.paket.secimOnce": "Profil seçimini ",
  "indirme.paket.secimSonra": " yaparsınız — yalnız seçtiğiniz modeller iner.",
  "indirme.paket.secimVurgu": "kurulum sırasında",
  "indirme.paket.tahminiIndirme": "Tahmini indirme",
  "indirme.paket.testUcretsiz": "Test aşamasında tüm profiller (Araştırma dahil) ücretsizdir.",
  "indirme.paket.yokDahil": "Yok — dahil",
  "indirme.platformYakinda": "{{label}} · Yakında",
  "indirme.profil.aciklama": "Kurulum sırasında kullanım profilinizi seçersiniz; yalnız seçtiğiniz yapay zekâ modelleri iner. Birden fazla profil seçebilir, dilediğiniz zaman değiştirebilirsiniz.",
  "indirme.profil.baslik": "Kurulumda profilinizi seçin",
  "indirme.profil.indirmeBoyutu": "İndirme ≈ {{gb}} GB",
  "indirme.profil.planOnce": "Evcil Hayvan Sahibi ve Veteriner profilleri planınıza dahildir; Araştırma profili ücretli eklentidir. Ayrıntılar",
  "indirme.profil.planSonra": " sayfasında.",
  "indirme.profil.testOnce": "Test aşamasında ",
  "indirme.profil.testSonra": " — dilediğinizi indirin.",
  "indirme.profil.testVurgu": "tüm profiller (Araştırma dahil) ücretsizdir",
  "indirme.profil.ucretsiz": "Ücretsiz",
  "indirme.rozetSurum": "İndir · v{{surum}}",
  "indirme.surumTarih": "Sürüm {{surum}} · {{tarih}}",
  "indirme.telefonaTekDosya": "Telefona tek dosya olarak iner",
  "indirme.yakinda": "Yakında",
  "indirme.yakindaSurum": "Yakında · v{{surum}}",
  "ortak.anaSayfa": "Ana sayfa",
}

const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/
const yerTutucu = (s: string) => [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort()

/** Çizilen HTML'in React `<!-- -->` ayracıyla ayrılmış HAM metin düğümleri + öznitelik değerleri (TAM eşleşme; `~` önek = alt dizgi). */
const temizle = (h: string) => h.replace(/<!-- -->/g, '')
const dugumler = (h: string): Set<string> => {
  const s = new Set<string>(h.split(/<[^>]*>/))
  for (const m of h.matchAll(/="([^"]*)"/g)) s.add(m[1])
  return s
}
const var_ = (h: string, d: Set<string>, s: string) => (s.startsWith('~') ? temizle(h).includes(s.slice(1)) : d.has(s))
const ciz = (bilesen: unknown, props: Record<string, unknown> = {}) =>
  renderToString(createElement(MemoryRouter, null, createElement(bilesen as never, props)))

type Cift = [tr: string, en: string]
/** Türkçe dizgi başka (henüz göçmemiş) kaynaktan da çizilir: config.ts (site-12c-config göçünde bu küme SİLİNİR). */
const BASKA_KAYNAK_12C = new Set<string>(['PEMF Vet’i indirin', 'Windows', 'Android', 'Linux', 'macOS'])

const oturumsuz = () => {
  oturum.session = null
  oturum.email = null
}
const oturumlu = () => {
  oturum.session = { user: { id: 'u1' } }
  oturum.email = 'klinik@ornek.com'
}

afterEach(async () => {
  oturumsuz()
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

const platformlar = [CLIENT.downloads.windows, CLIENT.downloads.macos, CLIENT.downloads.linux, CLIENT.downloads.android]

const SAYFALAR: [ad: string, oturumlu: boolean, cizici: () => string, ciftler: () => Cift[]][] = [
  [
    'DownloadButtons (oturum yok)', false, () => ciz(DownloadButtons),
    () => [
      ['İndirmek için ücretsiz hesap oluşturun veya giriş yapın — aynı hesapla uygulamaya ve destek taleplerinize giriş yaparsınız. Kart bilgisi istenmez.',
       'Create a free account or sign in to download — the same account signs you in to the app and to your support requests. No card details are required.'],
      ['Giriş yap ve indir', 'Sign in and download'],
      ...platformlar.filter((d) => d.ready).map((d): Cift => [`${d.label} için giriş yapıp indir`, `Sign in and download for ${d.label}`]),
      ...platformlar.filter((d) => !d.ready).map((d): Cift => [`${d.label} · Yakında`, `${d.label} · Coming soon`]),
    ],
  ],
  [
    'DownloadButtons (oturum var)', true, () => ciz(DownloadButtons),
    () => [
      ...platformlar.filter((d) => d.ready).map((d): Cift => [`${d.label} için indir`, `Download for ${d.label}`]),
      ...platformlar.filter((d) => !d.ready).map((d): Cift => [`${d.label} · Yakında`, `${d.label} · Coming soon`]),
    ],
  ],
  [
    'AccountButton (oturum yok)', false, () => ciz(AccountButton),
    () => [['Giriş yap', 'Sign in']],
  ],
  [
    'AccountButton (oturum var)', true, () => ciz(AccountButton),
    () => [['Hesabım', 'My account']],
  ],
  [
    'PackageBuilder', false, () => ciz(PackageBuilder),
    () => [
      ['Önerilen', 'Recommended'],
      ['Planınıza dahil', 'Included in your plan'],
      ['Seçili profil', 'Selected profiles'],
      ['Tahmini indirme', 'Estimated download'],
      ['Aylık eklenti', 'Monthly add-on'],
      ['Yok — dahil', 'None — included'],
      ['PEMF Vet’i İndir', 'Download PEMF Vet'],
      ['Profil seçimini ', 'You choose your profile '],
      ['kurulum sırasında', 'during installation'],
      [' yaparsınız — yalnız seçtiğiniz modeller iner.', ' — only the models you select are downloaded.'],
      FREE_MODE
        ? ['Test aşamasında tüm profiller (Araştırma dahil) ücretsizdir.', 'During the test phase all profiles (including Research) are free.']
        : ['Evcil Hayvan Sahibi ve Veteriner profilleri planınıza dahildir; Araştırma ücretli eklentidir.', 'The Pet Owner and Veterinarian profiles are included in your plan; Research is a paid add-on.'],
    ],
  ],
  [
    'Download (indirme sayfası)', false, () => ciz(DownloadPage),
    () => [
      [`İndir · v${CLIENT.version}`, `Download · v${CLIENT.version}`],
      ['İndirdiğiniz başlatıcıyı kurun; asıl uygulamayı o indirip kurar ve “Başlat” ile açılır.', 'Install the launcher you downloaded; it downloads and installs the main app, and the app opens with “Start”.'],
      ['PEMF Vet’i indirin', 'Download PEMF Vet'],
      [` Sürüm ${CLIENT.downloads.windows.version} · ${CLIENT.releaseDate}`.trim(), `Version ${CLIENT.downloads.windows.version} · ${CLIENT.releaseDate}`],
      [' İnen dosyaların bütünlüğü kurulumda otomatik doğrulanır', ' The integrity of the downloaded files is verified automatically during installation'],
      [`İndirilen kurulum dosyası ≈ ${CLIENT.downloads.windows.sizeMB} MB · uygulama kurulum sırasında iner`, `The installer you download is ≈ ${CLIENT.downloads.windows.sizeMB} MB · the app is downloaded during installation`],
      ['Telefona tek dosya olarak iner', 'Downloads to your phone as a single file'],
      ['Giriş yap ve indir', 'Sign in and download'],
      ['Kurulumda profilinizi seçin', 'Choose your profile during installation'],
      ['Kurulum sırasında kullanım profilinizi seçersiniz; yalnız seçtiğiniz yapay zekâ modelleri iner. Birden fazla profil seçebilir, dilediğiniz zaman değiştirebilirsiniz.',
       'You choose your usage profile during installation; only the AI models you select are downloaded. You can select more than one profile and change it at any time.'],
      [`İndirme ≈ ${MODULES[0].sizeGB.toFixed(1)} GB`, `Download ≈ ${MODULES[0].sizeGB.toFixed(1)} GB`],
      ...(FREE_MODE
        ? ([
            ['Ücretsiz', 'Free'],
            ['Test aşamasında ', 'During the test phase '],
            ['tüm profiller (Araştırma dahil) ücretsizdir', 'all profiles (including Research) are free'],
            [' — dilediğinizi indirin.', ' — download whichever you like.'],
          ] as Cift[])
        : []),
      ['Kurulumdan sonra', 'After installation'],
      ['Sistem gereksinimleri', 'System requirements'],
      ['• 8 GB RAM (yapay zekâ modelleri için 16 GB önerilir)', '• 8 GB RAM (16 GB recommended for AI models)'],
      ['• 4–12 GB boş disk — kesin boyut seçtiğiniz profil sayısına göre değişir', '• 4–12 GB free disk space — the exact size depends on the number of profiles you select'],
      ['• İlk kurulum için internet bağlantısı', '• Internet connection for the first installation'],
      ...(CLIENT.downloads.linux.appImageReady ? ([['.AppImage (tüm dağıtımlar)', '.AppImage (all distributions)']] as Cift[]) : []),
      ...(platformlar.some((d) => !d.ready)
        ? ([['Yakında', 'Coming soon'], ['Çıkınca haber ver', 'Notify me when available']] as Cift[])
        : []),
    ],
  ],
  [
    'Download (oturum var)', true, () => ciz(DownloadPage),
    () => platformlar.filter((d) => d.ready).map((d): Cift => [`${d.label} için indir`, `Download for ${d.label}`]),
  ],
  [
    'AuthRoute · kayıt', false, () => ciz(AuthRoute, { kind: 'register' }),
    () => [
      ['Hesap', 'Account'],
      ['Hesap oluştur', 'Create account'],
      ['Ücretsiz hesap masaüstü uygulaması, telefon uygulaması ve bu site için ortaktır; kart bilgisi istenmez. Kayıt penceresi kapandıysa aşağıdaki düğmeyle yeniden açabilirsiniz.',
       'A free account is shared by the desktop app, the phone app and this site; no card details are required. If the sign-up window closed, you can reopen it with the button below.'],
      ['Kayıt penceresini aç', 'Open the sign-up window'],
      ['Ana sayfa', 'Home page'],
    ],
  ],
  [
    'AuthRoute · giriş', false, () => ciz(AuthRoute, { kind: 'login' }),
    () => [
      ['Giriş yap', 'Sign in'],
      ['Hesabınızla giriş yapın. Pencere kapandıysa aşağıdaki düğmeyle yeniden açabilirsiniz.', 'Sign in with your account. If the window closed, you can reopen it with the button below.'],
      ['Giriş penceresini aç', 'Open the sign-in window'],
    ],
  ],
  [
    'AuthRoute · şifremi unuttum', false, () => ciz(AuthRoute, { kind: 'forgot' }),
    () => [
      ['Şifremi unuttum', 'Forgot password'],
      ['Giriş penceresinde e-postanızı yazıp "Şifremi unuttum" bağlantısına basın; size yeni şifre belirleme bağlantısı göndeririz. Pencere kapandıysa aşağıdaki düğmeyle yeniden açabilirsiniz.'.replace(/"/g, '&quot;'),
       'In the sign-in window, enter your email and press the &quot;Forgot password&quot; link; we will send you a link to set a new password. If the window closed, you can reopen it with the button below.'],
      ['Giriş penceresini aç', 'Open the sign-in window'],
    ],
  ],
  [
    'ResetPassword', false, () => ciz(ResetPassword),
    () => [
      ['Yeni şifre belirle', 'Set a new password'],
      ['Sıfırlama bağlantısı doğrulanıyor… Bu mesaj kalıcıysa bağlantının süresi dolmuş olabilir. Yeni bir bağlantı almak için', 'Verifying the reset link… If this message stays, the link may have expired. To get a new link,'],
      ['ana sayfadan giriş penceresini açıp', 'open the sign-in window from the home page and'],
      ['“Şifremi unuttum” adımını tekrarlayın.', 'repeat the “Forgot password” step.'],
      ['Yeni şifre', 'New password'],
      ['Yeni şifre (tekrar)', 'New password (again)'],
      ['En az 8 karakter; büyük harf, küçük harf ve rakam içermeli.', 'At least 8 characters; must include an uppercase letter, a lowercase letter and a number.'],
      ['Şifreyi güncelle', 'Update password'],
    ],
  ],
]

describe('site-12b-indirme-hesap · altın tablo', () => {
  const anahtarlar = Object.keys(ALTIN).sort()

  it('141 anahtar (kapı küçülmesin)', () => {
    expect(anahtarlar.length).toBe(141)
  })

  for (const k of anahtarlar) {
    it(`${k} · TR değer göç öncesiyle BAYT BAYT aynı · EN dolu, Türkçe harfsiz, aynı yer tutucular`, () => {
      expect(TR[k], `TR değer eskisinden FARKLI: ${k}`).toBe(ALTIN[k])
      expect(String(EN[k] ?? '').trim(), `EN boş: ${k}`).not.toBe('')
      expect(TR_HARF.test(EN[k]), `EN'de Türkçe harf: ${k}: ${EN[k]}`).toBe(false)
      expect(yerTutucu(EN[k]), `yer tutucu kümesi ayrışmış: ${k}`).toEqual(yerTutucu(TR[k]))
    })
  }

  it('her altın anahtar bu gruptaki kaynaklardan en az birinde KULLANILIYOR (t() kaldırılırsa kırmızı)', () => {
    const kaynaklar = [ACCOUNT_SRC, BUTTONS_SRC, GATE_SRC, STATS_SRC, PACKAGE_SRC, MODAL_SRC, HATALAR_SRC, AUTHROUTE_SRC, DOWNLOAD_SRC, RESET_SRC].join('\n')
    const kullanilan = kullanilanAnahtarlar(kaynaklar)
    const dizgiler = new Set([...kaynaklar.matchAll(/'((?:hesap|indirme|ortak|baslatici|ana)\.[A-Za-z0-9.]+)'/g)].map((m) => m[1]))
    const kullanilmayan = anahtarlar.filter((k) => !kullanilan.has(k) && !dizgiler.has(k))
    expect(kullanilmayan, `katalogda var, kaynakta kullanılmıyor: ${kullanilmayan.join(', ')}`).toEqual([])
  })
})

describe('site-12b-indirme-hesap · çizim', () => {
  for (const [ad, girisli, cizici, ciftler] of SAYFALAR) {
    it(`${ad} · Türkçe (bayrak kapalı): göç öncesiyle aynı metin`, () => {
      girisli ? oturumlu() : oturumsuz()
      const h = cizici()
      const d = dugumler(h)
      for (const [tr] of ciftler()) expect(var_(h, d, tr), `${ad}: ${tr}`).toBe(true)
    })

    it(`${ad} · bayrak AÇIK + İngilizce: her satır İngilizce, Türkçe kalmaz`, async () => {
      girisli ? oturumlu() : oturumsuz()
      dilMod.__bayrakTestiAyarla(true)
      await i18nMod.dilSec('en')
      const h = cizici()
      const d = dugumler(h)
      for (const [tr, en] of ciftler()) {
        expect(var_(h, d, en), `${ad} EN: ${en}`).toBe(true)
        if (BASKA_KAYNAK_12C.has(tr)) continue
        expect(var_(h, d, tr), `${ad} TR kaldı: ${tr}`).toBe(false)
      }
    })
  }
})

describe('site-12b-indirme-hesap · hata iletileri ve şifre kuralı', () => {
  const sifreKurali = (dil: 'tr' | 'en') => (dil === 'tr' ? TR : EN)['hesap.sifreKurali']
  const doldur = (s: string, dil: 'tr' | 'en') => s.replace('{{aciklama}}', sifreKurali(dil)).replace('{{email}}', COMPANY.email)
  const AUTH: [ham: string | null | undefined, anahtar: string][] = [
    ['Invalid login credentials', 'hesap.hata.epostaSifreHatali'],
    ['Email not confirmed', 'hesap.hata.epostaDogrulanmadi'],
    ['User already registered', 'hesap.hata.hesapZatenVar'],
    ['Password should be at least 6 characters', 'hesap.hata.sifreZayif'],
    ['For security purposes, you can only request this after 60 seconds', 'hesap.hata.cokSikDenendi'],
    ['Rate limit exceeded', 'hesap.hata.cokFazlaDeneme'],
    ['Unable to validate email address: invalid format', 'hesap.hata.epostaGecersiz'],
    ['Failed to fetch', 'hesap.hata.sunucuyaUlasilamadi'],
    ['email_address_invalid', 'hesap.hata.epostaKabulEdilmedi'],
    ['New password should be different from the old password.', 'hesap.hata.sifreAyni'],
    ['', 'hesap.hata.beklenmeyen'],
    [undefined, 'hesap.hata.beklenmeyen'],
    ['some brand new supabase failure xyz', 'hesap.hata.islemTamamlanamadi'],
  ]
  const ODEME: [ham: string, anahtar: string][] = [
    ['Insufficient funds', 'hesap.odeme.tahsilEdilemedi'],
    ['3D secure failed', 'hesap.odeme.bankaDogrulamadi'],
    ['subscription not found', 'hesap.odeme.abonelikYok'],
    ['', 'hesap.hata.islemTamamlanamadi'],
  ]

  for (const dil of ['tr', 'en'] as const) {
    it(`authHatasiTurkce · ${dil}: her Supabase iletisi kendi karşılığına çevrilir (eşleşme sırası değişmez)`, async () => {
      dilMod.__bayrakTestiAyarla(dil === 'en')
      await i18nMod.dilSec(dil)
      const kat = dil === 'tr' ? TR : EN
      for (const [ham, anahtar] of AUTH) {
        expect(authHatasiTurkce(ham), `${dil}: ${String(ham)}`).toBe(doldur(kat[anahtar], dil))
      }
      if (dil === 'en') for (const [ham] of AUTH) expect(TR_HARF.test(authHatasiTurkce(ham)), String(ham)).toBe(false)
    })

    it(`odemeHatasiTurkce · ${dil}: ödeme iletileri kendi karşılığına çevrilir`, async () => {
      dilMod.__bayrakTestiAyarla(dil === 'en')
      await i18nMod.dilSec(dil)
      const kat = dil === 'tr' ? TR : EN
      const hata = vi.spyOn(console, 'error').mockImplementation(() => {})
      for (const [ham, anahtar] of ODEME) expect(odemeHatasiTurkce(ham), `${dil}: ${ham}`).toBe(doldur(kat[anahtar], dil))
      hata.mockRestore()
      if (dil === 'en') for (const [ham] of ODEME) expect(TR_HARF.test(odemeHatasiTurkce(ham))).toBe(false)
    })

    it(`SIFRE_KURALI.aciklama · ${dil}: etkin dilde okunur; kural (8 karakter, büyük / küçük harf, rakam) iki dilde aynı`, async () => {
      dilMod.__bayrakTestiAyarla(dil === 'en')
      await i18nMod.dilSec(dil)
      expect(SIFRE_KURALI.aciklama).toBe(sifreKurali(dil))
      expect(SIFRE_KURALI.minUzunluk).toBe(8)
      expect(sifreGecerliMi('Abcdef12')).toBe(true)
      expect(sifreGecerliMi('abc123')).toBe(false)
    })
  }

  it('Türkçe: kalıcı iletiler eski kaynakla aynı (örnekler)', () => {
    expect(authHatasiTurkce('Invalid login credentials')).toBe('E-posta veya şifre hatalı. Şifrenizi hatırlamıyorsanız "Şifremi unuttum" bağlantısını kullanın.')
    expect(authHatasiTurkce('zzz')).toBe(`İşlem tamamlanamadı. Lütfen tekrar deneyin; sorun sürerse ${COMPANY.email} adresine yazın.`)
    expect(SIFRE_KURALI.aciklama).toBe('En az 8 karakter; büyük harf, küçük harf ve rakam içermeli.')
  })

  it('K-3 dinamik izin tablosundaki anahtarlar katalogda iki dilde dolu', () => {
    for (const k of ['baslatici.profil.ev', 'hesap.tur.veteriner', 'hesap.tur.arastirmaci', 'hesap.tur.bireyselAlt', 'hesap.tur.klinikAlt', 'hesap.tur.kurumAlt']) {
      expect(String(TR[k] ?? '').trim(), k).not.toBe('')
      expect(String(EN[k] ?? '').trim(), k).not.toBe('')
    }
  })

  it('giriş servisi yok iletisi: TR bayt bayt eski (e-posta arasında boşluk YOK), EN düzgün cümle', () => {
    expect(TR['hesap.pencere.servisYok']).toBe('Giriş servisine şu anda ulaşılamıyor. Kısa süre sonra tekrar deneyin; sürerse{{eposta}} adresine yazın.')
    expect(EN['hesap.pencere.servisYok']).toBe('The sign-in service is unavailable right now. Try again shortly; if the problem continues, write to {{eposta}}.')
  })
})
