// Author: mertaygn, cglrgrkn
/* ============================================================
   PEMF Vet — Site içeriği & indirme yapılandırması
   Tek yerden düzenleyin. İndirme linkleri client yayınlanınca
   güncellenir (GitHub Releases / R2 / S3 önerilir — Vercel'e 52 MB
   koymayın; büyük dosya harici host'ta durmalı).
   ============================================================ */

export const BRAND = {
  name: 'PEMF Vet',
  tagline: 'Veteriner PEMF Terapisinde Yeni Kontrol Standardı',
  // Telif satırında TESCİLLİ ünvanın kısa hâli kullanılır; ürün markası 'PEMF Vet' ayrı kalır.
  company: 'İBİA Teknoloji Ltd. Şti.',
  year: 2026,
} as const

/* ------------------------------------------------------------------
   SATICI / ŞİRKET KİMLİĞİ — YASAL ZORUNLU
   (6563 sy. E-Ticaret Kanunu m.5 + Mesafeli Sözleşmeler Yönetmeliği +
   iyzico üye işyeri şartı). Footer ve TÜM yasal sayfalar buradan okur.
   ⚠️ PLACEHOLDER'LARI GERÇEK BİLGİLERLE DOLDURUN → tüm site güncellenir.
   ------------------------------------------------------------------ */
// 2026-08-07: gerçek şirket kimliği işlendi (kaşeden). Placeholder KALMADI → yasal kapı açık.
// NOT: boş bırakılan alanlar arayüzde GÖSTERİLMEZ (Footer/Legal koşullu render) — yer tutucu
// yayınlamaktansa alanı gizlemek doğrudur.
export const COMPANY = {
  legalName: 'İBİA Teknoloji Makina Arge Danışmanlık Sanayi ve Ticaret Limited Şirketi',
  brandName: 'PEMF Vet',
  entityType: 'Limited Şirket',
  address: 'Yeşiltepe Mah. İsmet İnönü 2 Cad. No: 2-57, Tepebaşı',
  city: 'Eskişehir',
  country: 'Türkiye',
  phone: '+90 531 388 04 13',
  email: 'destek@v-pemf.com',
  kvkkEmail: 'destek@v-pemf.com',   // ayrı KVKK adresi açılınca burayı değiştirin
  taxOffice: 'Eskişehir Vergi Dairesi Başkanlığı',
  taxNo: '4690841423',
  mersis: '0469084142300001',
  tradeRegistry: '45277',
  withdrawalDays: 14, // dijital hizmet/abonelikte cayma; istisnalar Ön Bilgilendirme'de
  updated: '7 Ağustos 2026',
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
  'tedavisinin yerine geçmez. Otonom seans (AI Pro) özellikleri veteriner hekim sorumluluğunda kullanılır.'

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
  ready: true, // Windows launcher yayında (pemf-update/launcher-v1.9.2)
  githubOwner: 'mert61-python',
  githubRepo: 'pemf-update', // launcher, paketlerle aynı user-named repo'da
  launcherTag: 'launcher-v1.9.2', // mac/linux/android ORTAK etiketi (1.9.2; macOS notarize'li 2026-07-26). Windows AYRI (windowsTag).
  windowsTag: 'launcher-v1.9.30', // 1.9.30 = BASLAT DUGMESI guncelleme kontrolu bitmeden cikmiyor (kontrol surerken 'Guncelleme kontrol ediliyor...' yazip bekliyor; tiklama bosa gitmiyor). Ekran DONMUYOR: kurulu cihazda Hazir! aninda cizilir, bekleyen yalniz dugme; internet yoksa dugme hemen acilir. 1.9.29 = GUNCELLEME GORUNURLUGU: arka plan indirmesinde yuzde+bar; SUREKLI ACIK cihazlar da guncelleme aliyor (6 saatte bir kontrol; onceden yalniz acilista bakiliyordu, gunlerce kapatilmayan klinik makinesi yeni surumu HIC gormuyordu -> zorunlu guvenlik guncellemesi de ulasamiyordu); indirme oncesi DISK kontrolu + eski paket temizligi; iki pencere ayni anda guncelleme yapamaz. Suren seans ASLA kesilmez: periyodik tur yalniz indirir+bildirir, kurulum kapat-ac aninda. 1.9.28 = KALDIR -> YENIDEN KUR temiz: Ayarlar > Uygulamalar'dan kaldirmada MQTT broker'i sahipsiz kalip 1883'u tutuyordu -> yeniden kurulumda broker baslamiyor, 6-8 numarali bobinler ULASILAMAZ oluyordu (1-5 seri porttan calistigi icin cihaz calisiyor gibi gorunuyordu). Kaldirma artik broker+tunel yardimcisini adlariyla durduruyor. 1.9.27 = KARARSIZ BAGLANTIDA yanlis "internet yok" (manifest cekimi tek denemeydi; anlik TCP sifirlamasi kurulumu 3'te 1 engelliyordu) -> 3 deneme + kalici hatalarda tekrar yok. 1.9.25 = DENETIM MASASI BOYUTU gercegi yansitiyor (NSIS kurulum aninda ~11 MB yaziyordu; runtime+profiller sonra iniyor). 1.9.24 = GUVENLIK DUVARI UYARISI yanlis alarm vermiyor: Windows'un KENDI izni de sayiliyor; 'kural yok' acilista SUSAR (yalniz Baslat'tan sonra uyarir), acik Block kuralinda her zaman uyarir. 1.9.23 = YARIM KALMIS KURULUM artik 'Hazir!' gorunmuyor (butunluk exe VARLIGI yerine YAPISAL kontrolle olculuyor). 1.9.22 = KESINTI/ESZAMANLILIK: guncelleme ortasinda kapanma artik 'kurulu degil' demiyor (yarim takas acilista kurtarilir); ayni anda iki client kurulum yapamaz; bozuk indirmede tek-seferlik temiz yeniden-deneme. 1.9.21 = SIYAH KONSOL PENCERESI duzeltildi: yardimci komutlar (guvenlik duvari denetimi + kurulum ACL) pencereli launcher'dan calisirken Windows onlara yeni konsol aciyordu; kapat-ac akisinda 2 pencere goruluyordu. 1.9.20 = SAHA ARIZASI: kurulum sonrasi cihaz acilmiyordu (at-rest anahtar uyusmazliginda karantina + veri-gocu sonsuz dongusu + launcher yanlis gunluk yolu + baglanti sizintisi). Ayrica URETICI KIMLIGI duzeltildi: UAC/Yayimci artik IBIA Teknoloji Ltd. Sti. 1.9.19 = PROFIL BAGIMLILIGI KAYNAGINDAN KALKTI: AI Pro organ lokalizasyonu modelleri (inference_cat_organ, ~209 MB) yalniz home.zip'te idi → cekirdege (base-deps) alindi; profiller arasi artik NE zorunlu NE islevsel bag var, home.zip 528→318 MB. 1.9.18 = PROFILLER BAGIMSIZ: 'Veteriner' secilince 'Ev Sahibi' artik ZORLA eklenmiyor (yalniz Vet+Arastirma kurulabilir). 1.9.17 = GIRIS EKRANI: parola goster/gizle + hatali giriste alan temizlenir + gorunmez karakter/bosluk uyarisi (dogru parola 'hatali' deniyordu, alan silinip tekrar yazilinca geciyordu). 1.9.16 = URETIME-HAZIRLIK DENETIMI (Tier 0-3): geri cagirma (min_supported_version), kurulum oncesi disk-alani kontrolu + olu onbellek temizligi, guvenlik-duvari kurali, filo envanteri (surum alanlari heartbeat'te), surum dosyasi app katmaninda (siradan yayinda artik tazelenir). 1.9.13 = KATMANLI GUNCELLEME: paket app(~71MB)+deps(~1,19GB) olarak ayrildi → siradan surum 1,3 GB yerine ~71 MB iner. 1.9.12 = UYGULAMA OTO-GUNCELLEME: client acilista base.zip + model paketlerini de manifest sha'siyla karsilastirip yeniler ("Onar" gerekmez; seans sirasinda ertelenir). 1.9.11 = arayuz metinlerinde "tedavi" -> "seans" (client + kurulum + guncelleme uyarilari). 1.9.9 = client GIRISI (Supabase + Beni hatirla) + oturum devri (uygulamada cift login yok) + cevrimdisi acilis kilidi fix + header tasmasi fix. 1.9.8 = yarım-kalan çoklu-kurulumda tamamlanan profil korunur (iptal→Hazır!) + 1.9.7 Başlat ayrı-pencere (client açık kalır) + 1.9.6 uninstall (os error 5) fix → kayıtlı NSIS uninstaller'ı başlatır. 1.9.5 = KRİTİK backend-deadlock fix (stdout→NUL) + 1.9.4 self-update/uninstaller-fix. Windows-only → mac/linux 1.9.2'de. // Windows'a AYRI etiket: 1.9.4 = self-update + uninstaller-fix (işaretsiz kaldırmada profiller korunur). Windows-only → mac/linux 1.9.2'de kalır (404 olmasın).
  // ⚠️ SÜRÜM DOSYA ADINDA (2026-08-10, sahip isteği). İndirilen dosya `PEMFVetClient-Setup.exe`
  // diye kaydediliyordu; İndirilenler klasöründe üç sürüm yan yana durunca hangisinin hangisi
  // olduğu anlaşılmıyordu ve destek çağrısında "hangi setup'ı kurdunuz?" sorusu cevapsız
  // kalıyordu. Ad artık sürümü taşır: PEMFVetClient-Setup-1.9.16.exe
  //
  // ⚠️ TEK KAYNAK: `windowsTag`. Adı elle yazmak, etiket yükseltilip ad unutulduğunda 404
  // üretirdi (indirme butonu sessizce ölürdü) — bu yüzden ad etiketten TÜRETİLİR, elle
  // yazılmaz. `scripts/check-legal-config.mjs` testi ikisinin tutarlılığını ayrıca kilitler.
  get windowsAsset(): string {
    return `PEMFVetClient-Setup-${this.windowsTag.replace(/^launcher-v/, '')}.exe`
  },
  macosAsset: 'PEMFVetClient.dmg',
  macosReady: false, // "Yakında": launcher Mac'te ÇALIŞIR ama DONANIM (STM seri + ESP MQTT + hotspot) Windows-ÖZEL → Mac'te cihaz sürülemez. Donanım desteği gelene kadar "Yakında" (kasıtlı; .dmg yayında ama gösterme).
  linuxDebAsset: 'PEMFVetClient.deb', // Ubuntu / Debian (+ zip crate → 'unzip' sistem bağımlılığı YOK)
  linuxAppImageAsset: 'PEMFVetClient.AppImage', // universal (AYRI flag; .deb'den bağımsız yayınlanır)
  linuxRpmAsset: 'PEMFVetClient.rpm', // Fedora / RHEL (mosquitto Requires + %post config)
  linuxReady: false, // "Yakında": donanım (STM/ESP/hotspot) Windows-özel → Linux'ta cihaz sürülemez (paketler yayında ama kasıtlı gizli, donanım desteği gelene kadar).
  linuxAppImageReady: false, // (aynı neden — Linux donanım desteği yok)
  linuxRpmReady: false, // (aynı neden)
  // Android: mobil app STANDALONE APK (Hermes gömülü, Metro gerekmez). GitHub'da launcher release'inde
  // barındırılır → Windows/Mac/Linux ile AYNI REL. Backend'e aynı WiFi'de mDNS/subnet ile oto-bağlanır.
  // 2026-08-06: Android AYRI etiket. Eskiden mac/linux ile ORTAK launcherTag'i (1.9.2) kullanıyordu
  // → APK güncellense bile site ESKİ sürümü (2.3.2) veriyordu. Mobil sürüm döngüsü masaüstünden
  // bağımsız olduğu için kendi etiketi olmalı.
  androidTag: 'launcher-v1.9.30',
  // ⚠️ SÜRÜM DOSYA ADINDA (2026-08-11) — Windows ile AYNI gerekçe: İndirilenler klasöründe üç
  // sürüm yan yana durunca hangisinin hangisi olduğu anlaşılmıyor ve destek çağrısında "hangi
  // APK'yı kurdunuz?" cevapsız kalıyordu. Windows `windowsTag`ten türetilebiliyor (etiket sürümü
  // taşır); Android'in etiketi `launcher-v*` olduğu için MOBİL sürümü ayrıca tutmak ZORUNLU.
  //
  // ⚠️ TEK KAYNAK guii/versions.json → mobile.name. Burası ELLE eşlenir; APK yayınlarken ikisini
  // birlikte güncelleyin (`scripts/check-legal-config.mjs` tutarlılığı ayrıca kilitler).
  androidVersion: '2.3.16',
  get androidAsset(): string {
    return `PEMF_Vet_Mobil-${this.androidVersion}.apk`
  },
  androidReady: true, // Android standalone APK yayinda (v2.3.16 / versionCode 23 = ACILIS KAPISI: uygulama once guncelleme kontrol edip sonra aciliyor; guncelleme ZORUNLU DEGIL, 'Simdilik devam et' her zaman var)
}

const REL = `https://github.com/${DOWNLOAD_HOST.githubOwner}/${DOWNLOAD_HOST.githubRepo}/releases/download/${DOWNLOAD_HOST.launcherTag}`
// Windows AYRI etiket (self-update = Windows-only → mac/linux/android REL'inden bağımsız).
const WIN_REL = `https://github.com/${DOWNLOAD_HOST.githubOwner}/${DOWNLOAD_HOST.githubRepo}/releases/download/${DOWNLOAD_HOST.windowsTag}`
// Android AYRI etiket (mobil sürüm döngüsü masaüstünden bağımsız — bkz. androidTag yorumu).
const AND_REL = `https://github.com/${DOWNLOAD_HOST.githubOwner}/${DOWNLOAD_HOST.githubRepo}/releases/download/${DOWNLOAD_HOST.androidTag}`

export const CLIENT = {
  // ⚠️ `windowsTag` ile AYNI sürüm olmalı — sayfada "1.9.18" okuyup adında 1.9.20 yazan dosya
  // indirmek kullanıcıyı yanıltır ve destek çağrısını çözümsüz bırakır. Etiket yükseltilirken
  // burası UNUTULDU (2026-08-10 → 1.9.19 yayınında); `downloadNames.test.ts` yakaladı.
  version: '1.9.30',
  channel: 'Sürüm 2026.1',
  sizeMB: 3, // NSIS launcher setup ~2.9 MB (asıl uygulama+modeller client içinden iner)
  releaseDate: '16 Ağu 2026',
  ready: DOWNLOAD_HOST.ready,
  downloads: {
    windows: {
      key: 'windows' as const,
      label: 'Windows',
      url: `${WIN_REL}/${DOWNLOAD_HOST.windowsAsset}`,
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
    android: {
      key: 'android' as const,
      label: 'Android',
      url: `${AND_REL}/${DOWNLOAD_HOST.androidAsset}`,
      os: 'Android 8.0+ · APK (bilinmeyen kaynağa izin verin)',
      ready: DOWNLOAD_HOST.androidReady,
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
    tagline: 'Kamera destekli akıllı teşhis + tek-tuş güvenli seans.',
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
      'AI Pro otonom kapalı-döngü seans',
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
      'AI Hub + AI Pro (otonom seans)',
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

/** İsteğe bağlı eklentiler (uygulama içi satın alma). Araştırma modülü ayrı profil eklentisidir.
 *
 * ⚠️ 2026-08-09 — SAHİP KARARI: "Genişletilmiş Yedekleme (Bulut şifreli hasta verisi yedekleme
 * ve arşiv, ₺190/ay)" KALDIRILDI ve GERİ EKLENMEYECEK. Unutulmuş değildir.
 *
 * İki gerekçe:
 *   1) Arkasında ÜRÜN YOKTU — kod tabanında bulut yedekleme diye bir şey hiç olmadı. Var olmayan
 *      bir hizmeti listelemek, veterinerin ona güvenip yedeksiz kalmasıyla sonuçlanır.
 *   2) Ürün, hasta kayıtlarını bilinçli olarak MAKİNEDE tutar (bulut senkronu yok — kişisel veri
 *      yurt dışına çıkmasın, kayıt kliniğin olsun); Supabase yalnız cihaz kaydı/eşleştirme için
 *      kullanılır. Bulut yedekleme bu mimari kararı tersine çevirirdi.
 * NOT: karar MALİYET sebebiyle değildi — sensör verisi dakika-ortalaması olarak yazıldığından
 * depolama klinik başına ayda ~₺1 mertebesinde kalırdı. Sorun ürünün olmaması ve veri ikametiydi.
 *
 * Yerine ZATEN VAR OLANLAR: yerel/harici-disk şifreli yedek + kurtarma zarfı
 * (utils/backup_recovery.py) ve şifreli cihaz taşıma (/api/data/export|import).
 *
 * Buraya yeni bir kalem eklerken kural: SATILAN ŞEYİN KODU OLMALI. Kalan ikisinin var:
 * uzaktan erişim → servers/tunnel_manager.py (cloudflared + eşleştirme), cihaz yuvası →
 * entitlement katmanı (henüz ENFORCED=false; ödeme başlayınca zorunlu kılınacak).
 */
export const ADDONS = [
  { name: 'Ek Cihaz Yuvası', desc: 'Plana cihaz başına ek eşzamanlı bağlantı.', price: '₺149 / ay' },
  { name: 'Uzaktan Erişim', desc: 'Güvenli tünelle klinik dışından cihaz kontrolü ve izleme.', price: '₺249 / ay' },
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
    // DÜZELTİLDİ: burada "Bluetooth Low Energy" yazıyordu. Üründe BLE YOK — bağlantı yerel ağ
    // üzerinden (mDNS keşfi + HTTP/WebSocket), bobinler ise USB seri (STM32) ve MQTT (ESP32) ile
    // sürülüyor; uzaktan erişim güvenli tünelden. Yanlış yetenek beyanı satış vaadi doğurur.
    n: '01',
    title: 'Kesintisiz Senkronizasyon',
    desc: 'Cihazı aynı Wi-Fi ağında otomatik bulur; frekans ve şiddet değişiklikleri anında uygulanır, sensör verisi canlı akar.',
    icon: 'bluetooth',
  },
  {
    n: '02',
    title: 'Hasta Veritabanı',
    desc: 'Her hasta için özelleştirilmiş protokoller oluşturun; seans geçmişini şifreli olarak detaylı grafiklerle takip edin.',
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
    desc: 'Kamera destekli akıllı teşhis: yüz-ağrısı skoru, organ 3B lokalizasyonu ve otonom kapalı-döngü seans (AI Pro).',
    icon: 'brain',
  },
  {
    n: '05',
    title: 'Klinik Güvenlik',
    desc: 'Acil durdurma, süre-watchdog ve güven-geçidi; seans yalnız hedef güvenle bulunduğunda uygulanır.',
    icon: 'shield',
  },
  {
    // macOS derlemesi Apple notarizasyonu tamamlanana kadar YAYINDA DEĞİL (indirme butonu
    // `DOWNLOAD_HOST.macosReady` ile "Yakında" gösteriyor). Özellik metni "üçünde de çalışır"
    // diyerek indirme bölümüyle çelişiyordu; mevcut duruma hizala.
    n: '06',
    title: 'Çoklu Platform',
    desc: 'Windows ve Linux’ta tek istemci (macOS yakında); klinik verisi cihazda şifreli (SQLCipher), uzaktan erişim güvenli tünelle.',
    icon: 'monitor',
  },
] as const

// Sürüm notları CLIENT.version ile HİZALI olmalı: burası 1.2.4/12 Haz 2026'da donmuştu ve
// üründe olmayan "Bluetooth"tan bahsediyordu — site 1.9.8 dağıtırken eski sürüm notu gösteriyordu.
export const PATCH = {
  version: CLIENT.version,
  date: CLIENT.releaseDate,
  notes: [
    'Sıcaklık ölçümü olmayan bobinler artık “ölçüm yok” diye açıkça belirtiliyor — boş bir alan “sorun yok” diye okunmasın.',
    'Seans kaydı tutulamıyorsa seans başlatılmıyor: uygulanan doz sonradan bilinemeyecek bir tedavi yapılmıyor.',
    'Hekim kimliği artık cihazda doğrulanıyor; kayıtlar doğru hekime yazılıyor.',
    'Geri dönüşsüz işlemler (toplu silme, veri aktarma) kalıcı bir denetim izine yazılıyor.',
    'Tek tuşla destek paketi: hasta adları maskelenmiş, tek dosyalık teşhis kaydı.',
    'Cihaz taşıma artık tüm klinik kayıtlarını eksiksiz taşıyor.',
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
