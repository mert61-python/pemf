/* ============================================================
   PEMF Vet — Site içeriği & indirme yapılandırması
   Tek yerden düzenleyin. İndirme linkleri client yayınlanınca
   güncellenir (GitHub Releases / R2 / S3 önerilir — Vercel'e 52 MB
   koymayın; büyük dosya harici host'ta durmalı).
   ============================================================ */

export const BRAND = {
  name: 'PEMF Vet',
  tagline: 'Veteriner PEMF Terapisinde Yeni Kontrol Standardı',
  company: 'V-PEMF Technologies',
  year: 2026,
} as const

/* ------------------------------------------------------------------
   SATICI / ŞİRKET KİMLİĞİ — YASAL ZORUNLU
   (6563 sy. E-Ticaret Kanunu m.5 + Mesafeli Sözleşmeler Yönetmeliği +
   iyzico üye işyeri şartı). Footer ve TÜM yasal sayfalar buradan okur.
   ⚠️ PLACEHOLDER'LARI GERÇEK BİLGİLERLE DOLDURUN → tüm site güncellenir.
   ------------------------------------------------------------------ */
export const COMPANY = {
  legalName: '[TİCARİ ÜNVAN — ör. V-PEMF Teknoloji Ltd. Şti. / Ad Soyad]',
  brandName: 'PEMF Vet',
  entityType: '[Şahıs İşletmesi / Limited Şirket / Anonim Şirket]',
  address: '[AÇIK ADRES — Mahalle, Cadde, No, İlçe]',
  city: '[İL]',
  country: 'Türkiye',
  phone: '[TELEFON — +90 (___) ___ __ __]',
  email: 'destek@v-pemf.com',
  kvkkEmail: '[KVKK BAŞVURU E-POSTASI]',
  taxOffice: '[VERGİ DAİRESİ]',
  taxNo: '[VERGİ NO / TCKN]',
  mersis: '[MERSIS NO — tüzel kişi ise]',
  tradeRegistry: '[TİCARET SİCİL NO — tüzel kişi ise]',
  withdrawalDays: 14, // dijital hizmet/abonelikte cayma; istisnalar Ön Bilgilendirme'de
  updated: '14 Temmuz 2026',
} as const

/** Yasal belge sayfaları — App.tsx route'ları, Footer menüsü ve LegalPage içeriği buradan üretilir. */
export const LEGAL_DOCS = [
  { slug: 'mesafeli-satis', title: 'Mesafeli Satış Sözleşmesi' },
  { slug: 'on-bilgilendirme', title: 'Ön Bilgilendirme Formu' },
  { slug: 'iptal-iade', title: 'İptal, İade ve Cayma Hakkı' },
  { slug: 'kvkk', title: 'KVKK Aydınlatma Metni' },
  { slug: 'gizlilik', title: 'Gizlilik Politikası' },
  { slug: 'cerez-politikasi', title: 'Çerez Politikası' },
  { slug: 'kullanim-sartlari', title: 'Kullanım Şartları' },
] as const
export type LegalSlug = (typeof LEGAL_DOCS)[number]['slug']

/** Tıbbi/veteriner sorumluluk uyarısı — footer + ürün sayfalarında gösterilir. */
export const MEDICAL_DISCLAIMER =
  'PEMF Vet, veteriner hekim gözetiminde kullanılmak üzere tasarlanmış klinik destek yazılımıdır. ' +
  'Akıllı teşhis ve AI analiz çıktıları bilgilendirme amaçlıdır; veteriner hekimin tıbbi teşhis, karar ve ' +
  'tedavisinin yerine geçmez. Otonom tedavi (AI Pro) özellikleri veteriner hekim sorumluluğunda kullanılır.'

/** TEST AŞAMASI: true → TÜM profiller (Araştırma dahil) ücretsiz/indirilebilir; ücret etiketleri
 *  gizlenir. Abonelik satışı canlıya geçince false yapın (iyzico hazır olunca). */
export const FREE_MODE = true

/** 52 MB'lık client'ın barındırıldığı yer.
 *  GitHub Releases (OTA ile aynı mantık): her zaman en yeni sürümü verir →
 *  https://github.com/<owner>/<repo>/releases/latest/download/<asset>
 *  Client yayınlanınca `ready: true` yapın; o zamana kadar butonlar "Yakında" gösterir.
 *  Farklı host (Cloudflare R2 / S3 / kendi sunucu) isterseniz windows/macos url'lerini
 *  doğrudan CLIENT.downloads içinde elle yazın. */
export const DOWNLOAD_HOST = {
  ready: true, // Windows launcher yayında (pemf-update/launcher-v1.8.0)
  githubOwner: 'mert61-python',
  githubRepo: 'pemf-update', // launcher, paketlerle aynı user-named repo'da
  launcherTag: 'launcher-v1.9.0', // SABİT etiket (latest değil — paket release'iyle çakışmaz); 3-platform 1.9.0, macOS notarize'li (2026-07-26)
  windowsAsset: 'PEMFVetClient-Setup.exe',
  macosAsset: 'PEMFVetClient.dmg',
  macosReady: true, // Mac native YAYINDA (base-mac.zip + imzalı .dmg 1.9.0, launcher-v1.8.0, 2026-07-26)
  linuxDebAsset: 'PEMFVetClient.deb', // Ubuntu / Debian (+ zip crate → 'unzip' sistem bağımlılığı YOK)
  linuxAppImageAsset: 'PEMFVetClient.AppImage', // universal (AYRI flag; .deb'den bağımsız yayınlanır)
  linuxRpmAsset: 'PEMFVetClient.rpm', // Fedora / RHEL (mosquitto Requires + %post config)
  linuxReady: true, // .deb native sürüm YAYINDA (launcher-v1.8.0/PEMFVetClient.deb, 2026-07-19)
  linuxAppImageReady: true, // taze AppImage YAYINDA (launcher-v1.8.0/PEMFVetClient.AppImage, fix'li, 2026-07-19)
  linuxRpmReady: true, // .rpm YAYINDA (launcher-v1.8.0/PEMFVetClient.rpm, 2026-07-19)
}

const REL = `https://github.com/${DOWNLOAD_HOST.githubOwner}/${DOWNLOAD_HOST.githubRepo}/releases/download/${DOWNLOAD_HOST.launcherTag}`

export const CLIENT = {
  version: '1.8.0',
  channel: 'Sürüm 2026.1',
  sizeMB: 3, // NSIS launcher setup ~2.9 MB (asıl uygulama+modeller client içinden iner)
  releaseDate: '14 Tem 2026',
  ready: DOWNLOAD_HOST.ready,
  downloads: {
    windows: {
      key: 'windows' as const,
      label: 'Windows',
      url: `${REL}/${DOWNLOAD_HOST.windowsAsset}`,
      os: 'Windows 10 / 11 (64-bit)',
      ready: true,
    },
    macos: {
      key: 'macos' as const,
      label: 'macOS',
      url: `${REL}/${DOWNLOAD_HOST.macosAsset}`,
      os: 'macOS 12 Monterey+',
      ready: DOWNLOAD_HOST.macosReady,
    },
    linux: {
      key: 'linux' as const,
      label: 'Linux',
      url: `${REL}/${DOWNLOAD_HOST.linuxDebAsset}`,
      appImageUrl: `${REL}/${DOWNLOAD_HOST.linuxAppImageAsset}`,
      appImageReady: DOWNLOAD_HOST.linuxAppImageReady, // AppImage butonu yalnız bu true iken (404 önle)
      rpmUrl: `${REL}/${DOWNLOAD_HOST.linuxRpmAsset}`,
      rpmReady: DOWNLOAD_HOST.linuxRpmReady, // rpm butonu yalnız bu true iken
      os: 'Ubuntu/Debian · Fedora/RHEL · universal (64-bit)',
      ready: DOWNLOAD_HOST.linuxReady,
    },
  },
}

export const NAV = [
  { label: 'Özellikler', to: '/features' },
  { label: 'Fiyatlandırma', to: '/pricing' },
  { label: 'İndir', to: '/download' },
  { label: 'Destek', to: '/support' },
] as const

/** Kurulum modülleri (kullanım profili). Kullanıcı çoklu seçer; client yalnız seçilenlerin
 *  AI modellerini indirir → ev kullanıcısı büyük araştırma modellerini boşuna indirmez. */
export type Module = {
  id: 'home' | 'vet' | 'research'
  name: string
  tagline: string
  sizeGB: number
  /** Seviyeye dahil mi? true → ek ücret yok. false → aylık eklenti (addonMonthly). */
  included: boolean
  addonMonthly: number
  includes: readonly string[]
  recommended?: boolean
}

/** Client'ın kendisi (küçük launcher) — modüllerden bağımsız, her zaman iner. */
export const CLIENT_BASE_MB = 52

export const MODULES: Module[] = [
  {
    id: 'home',
    name: 'Ev Sahibi',
    tagline: 'Kamera destekli akıllı teşhis + tek-tuş güvenli tedavi.',
    sizeGB: 0.6,
    included: true,
    addonMonthly: 0,
    includes: [
      'Kedi yüz-ağrısı (FGS)',
      'Segmentasyon',
      'Kedi organ 3B lokalizasyon',
      'Kedi sesi analizi',
      'Hastalık ön-değerlendirme',
    ],
  },
  {
    id: 'vet',
    name: 'Veteriner Hekim',
    tagline: 'Tam klinik kontrol: manuel frekans, sensör, hasta veritabanı.',
    sizeGB: 0.9,
    included: true,
    addonMonthly: 0,
    includes: [
      'Manuel frekans & bobin kontrolü',
      'Sensör monitörü (mT / °C)',
      'Şifreli hasta veritabanı + KPI',
      'AI Pro otonom kapalı-döngü tedavi',
      'Tüm klinik AI modelleri',
    ],
    recommended: true,
  },
  {
    id: 'research',
    name: 'Araştırma Modu',
    tagline: FREE_MODE
      ? 'Kanser-araştırma modelleri — test aşamasında ücretsiz.'
      : 'Kanser-araştırma modelleri — ağır indirme; ücretli eklenti.',
    sizeGB: 1.9,
    included: FREE_MODE,
    addonMonthly: FREE_MODE ? 0 : 390,
    includes: [
      'Fantom tümör + EM alan',
      'Petri kuyu (kanser)',
      'Böbrek RNA (KIRC)',
      'Böbrek CT',
      'Böbrek patoloji (histopatoloji)',
      'CKD hastalık tahmini',
    ],
  },
]

export type Plan = {
  name: string
  /** Abonelik tier kimliği — backend/mobil ile birebir aynı (Supabase subscriptions.tier). */
  tier: 'baslangic' | 'pro' | 'pro_plus'
  /** true → Stripe Checkout'a gider (ücretli); false → indirmeye gider (ücretsiz deneme). */
  paid: boolean
  monthly: number | null
  yearly: number | null
  priceLabel?: string
  period: string
  desc: string
  /** İşlem önceliği politikası. realtime=true → kuyruksuz anlık; false → paylaşımlı kuyruk. */
  realtime: boolean
  queue: string
  features: readonly string[]
  cta: string
  to: string
  highlight: boolean
  badge?: string
}

/** Araştırma eklentisi — Pro/Pro+ üzerine eklenebilir (Supabase addons:["research"]). */
export const RESEARCH_ADDON = { monthly: 390, label: 'Araştırma modülü' } as const

/** Üyelik katmanları — fiyat politikası İŞLEM ÖNCELİĞİNE bağlı:
 *  Pro paylaşımlı KUYRUKTA bekler, Pro+ GERÇEK-ZAMANLI (kuyruksuz) öncelik alır.
 *  Fiyatlar ₺ (KDV hariç). yearly = 12 ayın toplamı (2 ay bedava). */
export const PLANS: Plan[] = [
  {
    name: 'Başlangıç',
    tier: 'baslangic',
    paid: false,
    monthly: 0,
    yearly: 0,
    priceLabel: 'Ücretsiz',
    period: '14 gün deneme',
    desc: 'Ev Sahibi profilinde sistemle tanışın.',
    realtime: false,
    queue: 'Paylaşımlı kuyruk · günlük sınırlı analiz',
    features: [
      'Ev Sahibi profili · 1 cihaz',
      'AI teşhis (kuyruklu, sınırlı)',
      'Şifreli hasta kaydı',
      '14 gün tam erişim',
    ],
    cta: 'Denemeyi Başlat',
    to: '/download',
    highlight: false,
  },
  {
    name: 'Pro',
    tier: 'pro',
    paid: true,
    monthly: 990,
    yearly: 9900,
    period: 'klinik / ay',
    desc: 'Aktif klinikler için tam sürüm — standart işlem önceliği.',
    realtime: false,
    queue: 'Standart kuyruk · yoğun saatlerde kısa bekleme',
    features: [
      'Veteriner profili · 5 cihaza kadar',
      'AI Hub + AI Pro (otonom tedavi)',
      'Standart işlem kuyruğu',
      'Hasta DB + KPI · otomatik güncelleme',
      'E-posta ve uzak destek',
    ],
    cta: 'Pro’yu Seç',
    to: '/download',
    highlight: false,
  },
  {
    name: 'Pro+',
    tier: 'pro_plus',
    paid: true,
    monthly: 1990,
    yearly: 19900,
    period: 'klinik / ay',
    desc: 'Gerçek-zamanlı öncelik ve eşzamanlı çoklu cihaz.',
    realtime: true,
    queue: 'Kuyruk yok · gerçek-zamanlı öncelik',
    features: [
      'Pro’daki her şey',
      'Gerçek-zamanlı AI Pro — kuyruksuz, anlık kapalı-döngü',
      'Eşzamanlı çoklu-cihaz real-time işlem',
      'Araştırma modülü eklenebilir (+₺390/ay)',
      'Öncelikli destek + SLA',
    ],
    cta: 'Pro+’ya Yükselt',
    to: '/download',
    highlight: true,
    badge: 'Real-time',
  },
]

/** İsteğe bağlı eklentiler (uygulama içi satın alma). Araştırma modülü ayrı profil eklentisidir. */
export const ADDONS = [
  { name: 'Ek Cihaz Yuvası', desc: 'Plana cihaz başına ek eşzamanlı bağlantı.', price: '₺149 / ay' },
  { name: 'Uzaktan Erişim', desc: 'Güvenli tünelle klinik dışından cihaz kontrolü ve izleme.', price: '₺249 / ay' },
  { name: 'Genişletilmiş Yedekleme', desc: 'Bulut şifreli hasta verisi yedekleme ve arşiv.', price: '₺190 / ay' },
] as const

/** Riot/Valorant akışı: website'den küçük client → client asıl uygulamayı indirir → Başlat. */
export const LAUNCHER_STEPS = [
  {
    step: '01',
    title: 'Client’ı indirin & kurun',
    desc: 'Website’den hafif PEMF Vet Client’ı indirin, kurulumu next-next tamamlayın. Masaüstüne client kısayolu eklenir.',
  },
  {
    step: '02',
    title: 'Uygulamayı client’tan indirin',
    desc: 'Client açılınca asıl PEMF Vet uygulamasını — AI modelleri ve donanım yazılımı gömülü — sizin için indirip kurar. Masaüstüne uygulama kısayolu da eklenir.',
  },
  {
    step: '03',
    title: '“Başlat”a basın',
    desc: 'İndirme bitince Başlat butonu gelir; tek tıkla uygulama açılır. Yeni sürüm ve güncellemeler yine client üzerinden gelir — manuel kurulum yok.',
  },
] as const

export const FEATURES = [
  {
    n: '01',
    title: 'Kesintisiz Senkronizasyon',
    desc: 'Bluetooth Low Energy üzerinden tüm PEMF ünitelerinize anında bağlanın ve frekansları milisaniye hassasiyetle yönetin.',
    icon: 'bluetooth',
  },
  {
    n: '02',
    title: 'Hasta Veritabanı',
    desc: 'Her hasta için özelleştirilmiş protokoller oluşturun; tedavi geçmişini şifreli olarak detaylı grafiklerle takip edin.',
    icon: 'database',
  },
  {
    n: '03',
    title: 'Otomatik Güncellemeler',
    desc: 'Launcher üzerinden donanım yazılımlarınızı ve AI modellerini tek tıkla güncelleyerek her zaman en yenisine sahip olun.',
    icon: 'refresh',
  },
  {
    n: '04',
    title: 'Yapay Zekâ Merkezi',
    desc: 'Kamera destekli akıllı teşhis: yüz-ağrısı skoru, organ 3B lokalizasyonu ve otonom kapalı-döngü tedavi (AI Pro).',
    icon: 'brain',
  },
  {
    n: '05',
    title: 'Klinik Güvenlik',
    desc: 'Acil durdurma, süre-watchdog ve güven-geçidi; tedavi yalnız hedef güvenle bulunduğunda uygulanır.',
    icon: 'shield',
  },
  {
    n: '06',
    title: 'Çoklu Platform',
    desc: 'Tek istemci Windows, macOS ve Linux’ta; klinik verisi cihazda şifreli (SQLCipher), uzaktan erişim güvenli tünelle.',
    icon: 'monitor',
  },
] as const

export const PATCH = {
  version: '1.2.4',
  date: '12 Haz 2026',
  notes: [
    'Bluetooth bağlantı stabilitesi artırıldı.',
    'Yeni “Hızlı Terapi” protokolleri eklendi.',
    'Arayüz performansı ve açılış süresi iyileştirildi.',
    'AI Analiz Geçmişi artık operatör bazlı filtrelenebiliyor.',
  ],
} as const

/** Seviye karşılaştırma tablosu — kolonlar: [Başlangıç, Pro, Pro+]. */
export const COMPARE: { label: string; values: [string, string, string] }[] = [
  { label: 'İşlem önceliği', values: ['Paylaşımlı kuyruk', 'Standart kuyruk', 'Real-time · kuyruksuz'] },
  { label: 'AI Pro canlı kapalı-döngü', values: ['—', 'Kuyruklu', 'Anlık'] },
  { label: 'Eşzamanlı cihaz', values: ['1', '5’e kadar', 'Çoklu (real-time)'] },
  { label: 'Kullanım profilleri', values: ['Ev Sahibi', 'Ev + Veteriner', 'Ev + Veteriner'] },
  { label: 'Araştırma modülü', values: ['—', '+₺390/ay', '+₺390/ay'] },
  { label: 'Hasta DB + KPI', values: ['Temel', '✓', '✓'] },
  { label: 'Otomatik güncelleme', values: ['✓', '✓', '✓'] },
  { label: 'Destek', values: ['Topluluk', 'E-posta & uzak', 'Öncelikli + SLA'] },
]

export const FAQ = [
  {
    q: 'PEMF Vet Client tam olarak nedir?',
    a: 'Website’den indirdiğiniz hafif bir kurulumdur (setup’ı next-next tamamlarsınız). Açtığınızda asıl PEMF Vet uygulamasını — AI modelleri ve donanım yazılımı gömülü — sizin için indirip kurar; bitince “Başlat” ile açarsınız. Masaüstüne hem client hem uygulama kısayolu eklenir — bir oyun istemcisinin oyunu kurup başlatması gibi.',
  },
  {
    q: 'Neden doğrudan uygulamayı indirmiyorum?',
    a: 'Uygulama + AI modelleri birkaç GB’tır ve sık güncellenir. Launcher yalnız gerekli parçaları indirir, farkları (delta) günceller ve kurulumu tek merkezden yönetir; böylece indirmeler küçük ve hızlı kalır.',
  },
  {
    q: 'Hangi işletim sistemleri destekleniyor?',
    a: 'Windows 10/11 (64-bit), macOS 12 Monterey+ ve Linux (Ubuntu/Debian). Klinik cihaz kurulumları Windows’ta yerel çalışır; macOS ve Linux de aynı şekilde yerel (native) çalışır.',
  },
  {
    q: 'İnternet olmadan çalışır mı?',
    a: 'İlk kurulum için internet gerekir. Kurulduktan sonra tüm AI modelleri cihazda gömülü ve çevrimdışı çalışır; klinik verisi cihazda şifreli tutulur.',
  },
  {
    q: 'Güncellemeler ücretli mi?',
    a: 'Hayır. Launcher üzerinden gelen sürüm, donanım yazılımı ve AI modeli güncellemeleri lisansınıza dahildir.',
  },
] as const
