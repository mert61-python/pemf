// Author: mertaygn, cglrgrkn
/* ============================================================
   PEMF Vet — Site içeriği & indirme yapılandırması
   Tek yerden düzenleyin. İndirme linkleri client yayınlanınca
   güncellenir (GitHub Releases / R2 / S3 önerilir — Vercel'e 52 MB
   koymayın; büyük dosya harici host'ta durmalı).
   ============================================================ */

import i18n from './i18n'

export const BRAND = {
  name: 'PEMF Vet',
  // I18N-0: başlık metni katalogda (ana.slogan) — modül düzeyi sabit ANAHTAR saklar, gösterimde çevrilir.
  sloganAnahtari: 'ana.slogan',
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
  // ⚠️ TEK KAYNAK — sitedeki HER destek bağlantısı buradan okur. Elle adres yazmayın;
  // `tests/test_destek_adresi_tek_kaynak.py` bunu kilitliyor.
  // 2026-08-22: `destek@v-pemf.com` idi; o alan adı KAYITLI DEĞİL (A ve MX için NXDOMAIN
  // ölçüldü) → sitedeki tüm iletişim yolları ve yasal zorunlu iletişim bilgisi ÖLÜYDÜ.
  email: 'ibiatechnology@gmail.com',
  kvkkEmail: 'ibiatechnology@gmail.com',   // ayrı KVKK adresi açılınca burayı değiştirin
  taxOffice: 'Eskişehir Vergi Dairesi Başkanlığı',
  taxNo: '4690841423',
  mersis: '0469084142300001',
  tradeRegistry: '45277',
  withdrawalDays: 14, // dijital hizmet/abonelikte cayma; istisnalar Ön Bilgilendirme'de
  get updated() { return i18n.t('icerik.sirket.guncelleme') },
} as const

/** Yasal belge sayfaları — App.tsx route'ları, Footer menüsü ve LegalPage içeriği buradan üretilir. */
export const LEGAL_DOCS = [
  { slug: 'mesafeli-satis', get title() { return i18n.t('icerik.yasal.mesafeliSatis') } },
  { slug: 'on-bilgilendirme', get title() { return i18n.t('icerik.yasal.onBilgilendirme') } },
  { slug: 'iptal-iade', get title() { return i18n.t('icerik.yasal.iptalIade') } },
  { slug: 'kvkk', get title() { return i18n.t('hesap.kayit.kvkk') } },
  { slug: 'gizlilik', get title() { return i18n.t('hesap.kayit.gizlilik') } },
  { slug: 'cerez-politikasi', get title() { return i18n.t('icerik.yasal.cerez') } },
  { slug: 'kullanim-sartlari', get title() { return i18n.t('hesap.kayit.kullanimSartlari') } },
] as const
export type LegalSlug = (typeof LEGAL_DOCS)[number]['slug']

/** Tıbbi/veteriner sorumluluk uyarısı — footer + ürün sayfalarında gösterilir. Etkin dilde OKUNUR (işlev; modül düzeyi sabit DEĞİL). */
export function tibbiUyari(): string {
  return i18n.t('icerik.uyari.tibbi')
}

/** TEST AŞAMASI: true → TÜM profiller (Araştırma dahil) ücretsiz/indirilebilir; ücret etiketleri
 *  gizlenir. Abonelik satışı canlıya geçince false yapın (iyzico hazır olunca). */
export const FREE_MODE = true

/**
 * JETON (token) ÜCRETLENDİRME MODELİ — TEK KAYNAK (sahip kararı 2026-08-20).
 *
 * NEDEN: planlar önce "işlem önceliği / kuyruk / gerçek zamanlı" ile ayrılıyordu; oysa yapay
 * zekâ analizleri KLİNİK BİLGİSAYARINDA çalışıyor — "sunucuda sıra beklersiniz" çerçevesi
 * yanlıştı ve vaat bugün karşılanmıyor.
 * ⚠️ OLGU DÜZELTMESİ (8. parti): "karşılığı hiç yoktu" diye yazmıştım; ölçüm bunu ÇÜRÜTTÜ —
 * servers/entitlement.py içinde gerçek bir eş-zamanlılık sınırlayıcısı VAR, ama
 * PEMF_TIER_ENFORCED kapalı olduğu için devrede değil. Kapalı mekanizma satılamayacağı için
 * vaadin kaldırılması yine de doğru. Jeton ölçülebilir ve dürüst bir birim:
 * 1 jeton = 1 yapay zekâ analizi.
 *
 * İKİ CEPLİ BAKİYE: plan hakkı her dönem yenilenir ve DEVRETMEZ; satın alınan jetonlar
 * SÜRESİZDİR. Tüketim önce plan hakkından düşer → kullanıcı parasıyla aldığını kaybetmez.
 *
 * ⚠️ TIBBİ GÜVENLİK: jeton TİCARİ kapıdır; süren seansı, acil durdurmayı, sensör okumayı ve
 * cihaz kontrolünü ASLA engellemez. Yalnız YENİ analiz isteğini kapılar. Analiz İNTERNET ister
 * (sahip kararı 2026-10-19, S-4B.5): jeton çevrimiçi düşülür, internetsiz analiz başlatılmaz; tam
 * düşüm anında kopan bağlantının ödemesi cihazda bekler, sonra uzlaşır (servers/jeton.py).
 *
 * Şema: database/supabase_jetonlar.sql · Uçlar: api/tokens.ts · Cihaz tarafı: servers/jeton.py
 */
export const JETON = {
  /** Planın her dönem yenilenen hakkı (devretmez). */
  planHaklari: { baslangic: 50, pro: 500, pro_plus: 2000 },
  /** Bir işlemin kaç jeton yaktığı. Ağır araştırma modelleri daha çok kaynak tüketir. */
  // TD9 (Y148): `canli_dakika` = canlı kamera kipinde DAKİKA başına (kareler ve sonuçsuz dakika ücretsiz) — servers/jeton.py.
  maliyet: { goruntu: 1, ses: 1, sensor: 1, agir_arastirma: 3, ai_pro_seans: 5, canli_dakika: 1 },
  /** Ek jeton paketleri — satın alınan jeton süresizdir; adet arttıkça birim fiyat düşer. */
  paketler: [
    { ad: '100 jeton', adet: 100, fiyat: 249 },
    { ad: '500 jeton', adet: 500, fiyat: 990 },
    { ad: '2.000 jeton', adet: 2000, fiyat: 3490 },
  ],
  /**
   * KULLANDIKÇA ÖDE (sahip isteği 2026-08-20): önden ödeme ve aylık ücret YOK. Kart kaydedilir,
   * harcanan jeton birikir ve dönem sonunda (ya da eşik aşılınca) faturalanır. Hiç kullanılmazsa
   * ücret çıkmaz. Birim fiyat, paketli/planlı jetondan PAHALIDIR — taahhütsüzlüğün karşılığı.
   * ⚠️ borcTavani: faturalanmamış kullanım sınırı (cihaz tarafıyla TEK KAYNAK —
   * servers/jeton.py::BORC_TAVANI; ayrışması testle kilitli). Tavan TİCARİdir: aşılsa bile
   * seans/acil durdurma çalışır.
   */
  kullandikcaOde: { jetonFiyati: 2.9, borcTavani: 300, faturaEsigiTL: 500 },
  aylikHakDevreder: false,
  satinAlinanSuresiz: true,
} as const

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
  windowsTag: 'launcher-v1.9.52', // 1.9.52 (2026-11-03) = acilista pencere donmasi giderildi (guvenlik duvari / yedek / guncelleme denetimi arka planda); bosta kapanis 'ACIL DURDUR' uyarisi birakmiyor; 'Beni hatirla' gecici hatada silinmiyor; kurulum / kaldirma pencereleri TR + EN. 1.9.51 = PLATFORM KAPISI KATMANLARI DA SAYAR: tek-parca paket yayindan cikinca istemciler kurulabilir paket VARKEN 'Bu platform icin uygulama paketi henuz yayinlanmadi' deyip kilitleniyordu (kontrol yalniz tek-parcaya bakiyordu). Ayrica PEMF_ARASTIRMA_AIPRO bayragi artik launcher'dan backend'e geciriliyor (varsayilan 0, davranis degismedi).
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
  androidTag: 'client-app-v1.9.51',
  // ⚠️ SÜRÜM DOSYA ADINDA (2026-08-11) — Windows ile AYNI gerekçe: İndirilenler klasöründe üç
  // sürüm yan yana durunca hangisinin hangisi olduğu anlaşılmıyor ve destek çağrısında "hangi
  // APK'yı kurdunuz?" cevapsız kalıyordu. Windows `windowsTag`ten türetilebiliyor (etiket sürümü
  // taşır); Android'in etiketi `launcher-v*` olduğu için MOBİL sürümü ayrıca tutmak ZORUNLU.
  //
  // ⚠️ TEK KAYNAK guii/versions.json → mobile.name. Burası ELLE eşlenir; APK yayınlarken ikisini
  // birlikte güncelleyin (`scripts/check-legal-config.mjs` tutarlılığı ayrıca kilitler).
  // ⚠️ SÜRÜM FARKI KULLANICIYA AÇIKLANIR (metin denetimi 2026-08-20): İndir sayfasında bilgisayar
  // kartı "1.9.32", telefon kartı "2.3.18" gösteriyor ve sebebi hiçbir yerde yazmıyordu. Telefon
  // uygulaması AYRI sürüm döngüsüne sahiptir (ayrı yayın etiketi); numaraların eşleşmesi beklenmez.
  androidVersion: '2.3.35', // 2026-11-03 YAYINDA (client-app-v1.9.51): Ingilizce dil secenegi; Android guncelleme bildirimi Turkce karakterlerle
  // (yayin akisi: scripts/site_indirme_dogrula.py).
  /** İndir sayfasında telefon kartında gösterilir — uygulamanın ROLÜNÜ açıklar (tek başına
   *  terapi uygulamaz; masaüstündeki cihazın uzaktan kumandasıdır). */
  get androidRolNotu() { return i18n.t('icerik.indir.androidRol') },
  /** İndir sayfasında telefon kartının altında gösterilir — iki farklı numarayı açıklar. */
  get androidVersionNote() { return i18n.t('icerik.indir.androidSurumNotu') },
  get androidAsset(): string {
    return `PEMF_Vet_Mobil-${this.androidVersion}.apk`
  },
  androidReady: true, // Android standalone APK yayinda (v2.3.17 / versionCode 24 = GUNCELLEME DOGRUDAN KURULUYOR: indirme bitince paylasim sayfasi yerine kurulum ekrani aciliyor; inen paket bir daha indirilmiyor). Cikis artik yalniz o cihazi kapatiyor.
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
  version: '1.9.52',
  get channel() { return i18n.t('icerik.indir.kanal') },
  // D6.42 + D6.66: platformdan bağımsız `sizeMB: 3` ("NSIS launcher ~2.9 MB") KALDIRILDI — Windows kurulum dosyası 1.9.43'ten beri
  // WebView2 çevrimdışı kurucusunu gömer; boyut Windows'a özel alanda (`downloads.windows.sizeMB`), macOS / Linux boyutu ölçülmedi (Yakında).
  get releaseDate() { return i18n.t('icerik.indir.surumTarihi') },
  ready: DOWNLOAD_HOST.ready,
  downloads: {
    windows: {
      key: 'windows' as const,
      label: 'Windows',
      url: `${WIN_REL}/${DOWNLOAD_HOST.windowsAsset}`,
      os: 'Windows 10 / 11 (64-bit)',
      ready: true,
      // ⚠️ SÜRÜM HEDEF BAŞINA (denetim 2026-08-18): indirme kartı sürümü tek bir
      // `CLIENT.version`dan basıyordu, yani ANDROID kartı da Windows launcher sürümünü
      // ("Sürüm 1.9.30") yazarken 2.3.x APK indiriyordu. Aynı yanılgıyı `windowsTag`
      // için config yorumu zaten "kullanıcıyı yanıltır" diye tarif ediyor.
      version: `${DOWNLOAD_HOST.windowsTag.replace(/^launcher-v/, '')}`,
      // Kurulum dosyası boyutu (MB; Windows Gezgini'nin gösterdiği 1024 tabanı) — `pemf-app-packages/manifest.json` `launcher.size`
      // 220.956.183 B ≈ 211 MiB (launcher 1.9.52). Kapı: `tests/test_site_paket_boyutlari.py` (±%10, tek kaynak manifest).
      sizeMB: 211,
    },
    macos: {
      key: 'macos' as const,
      label: 'macOS',
      url: `${REL}/${DOWNLOAD_HOST.macosAsset}`,
      os: 'macOS 12 Monterey+',
      ready: DOWNLOAD_HOST.macosReady,
      version: `${DOWNLOAD_HOST.launcherTag.replace(/^launcher-v/, '')}`,
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
      version: `${DOWNLOAD_HOST.launcherTag.replace(/^launcher-v/, '')}`,
    },
    android: {
      key: 'android' as const,
      label: 'Android',
      url: `${AND_REL}/${DOWNLOAD_HOST.androidAsset}`,
      get os() { return i18n.t('icerik.indir.androidOs') },
      ready: DOWNLOAD_HOST.androidReady,
      version: DOWNLOAD_HOST.androidVersion,
    },
  },
}

// I18N-0: menü etiketi katalogda (ortak.nav.*) — gösterimde t(n.anahtar).
export const NAV = [
  { anahtar: 'ortak.nav.ozellikler', to: '/features' },
  { anahtar: 'ortak.nav.fiyatlandirma', to: '/pricing' },
  { anahtar: 'ortak.nav.indir', to: '/download' },
  { anahtar: 'ortak.nav.destek', to: '/support' },
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

/** Profil seçiminden BAĞIMSIZ olarak her kurulumda inen ZORUNLU çalışma zamanı (MB).
 *
 *  ⚠️ DENETİM 2026-08-18: burada 52 yazıyordu ve bu sayı yalnızca client uygulamasının kendisiydi;
 *  oysa launcher kurulumdan sonra ZORUNLU olarak `app` + `deps` katmanlarını indiriyor
 *  (`pemf-app-packages/manifest.json` → layers.win-x64: app 0,07 GB + deps 1,36 GB = 1,43 GB).
 *  `PackageBuilder` "Tahmini indirme"yi bu sabit + profil boyutlarından hesapladığı için yalnız
 *  "Ev Sahibi" seçen bir kullanıcıya ≈0,7 GB gösteriliyordu; gerçek indirme ≈1,7 GB'dır (2,5 kat).
 *  Kırsal/kotalı bağlantıda bu, kullanıcıyı yanlış karara götüren bir sayıdır.
 *  ⚠️ TEK KAYNAK manifest'tir; `guii/tests/test_site_paket_boyutlari.py` bu üç sayıyı manifest'e
 *  karşı kilitler. Paketler yeniden üretilince buradaki değerler de güncellenmeli. */
export const CLIENT_BASE_MB = 1462

export const MODULES: Module[] = [
  {
    id: 'home',
    get name() { return i18n.t('baslatici.profil.ev') },
    get tagline() { return i18n.t('icerik.profil.ev.tagline') },
    // manifest profiles.home = 0,30 GB (eskiden 0.6 yazıyordu; `cat_organ` modelleri
    // çekirdeğe taşınınca home.zip 528 → 318 MB'a düştü, site güncellenmemişti).
    sizeGB: 0.3,
    included: true,
    addonMonthly: 0,
    get includes() {
      return [
        i18n.t('icerik.profil.ev.ic1'),
        i18n.t('icerik.profil.ev.ic2'),
        i18n.t('icerik.profil.ev.ic3'),
        i18n.t('icerik.profil.ev.ic4'),
        i18n.t('icerik.profil.ev.ic5'),
      ]
    },
  },
  {
    id: 'vet',
    get name() { return i18n.t('baslatici.profil.veteriner') },
    get tagline() { return i18n.t('icerik.profil.vet.tagline') },
    // manifest profiles.vet = 0,12 GB (eskiden 0.9 yazıyordu — 7 kat fazla).
    sizeGB: 0.1,
    included: true,
    addonMonthly: 0,
    get includes() {
      return [
        i18n.t('icerik.profil.vet.ic1'),
        i18n.t('icerik.profil.vet.ic2'),
        i18n.t('icerik.profil.vet.ic3'),
        i18n.t('icerik.profil.vet.ic4'),
        i18n.t('icerik.profil.vet.ic5'),
      ]
    },
    recommended: true,
  },
  {
    id: 'research',
    get name() { return i18n.t('icerik.profil.arastirma.ad') },
    get tagline() {
      return FREE_MODE ? i18n.t('icerik.profil.arastirma.taglineUcretsiz') : i18n.t('icerik.profil.arastirma.taglineEklenti')
    },
    // D6.66 (B-7.14): profil paketi (`profiles.research` 1,50 GiB) + AYRI model parçası (`model_parts.research` research-2.zip 1,69 GiB)
    // birlikte iner → 3,19 GiB (3,43 GB). Eskiden yalnız profil paketi yazılıyordu (1.5). Kapı: tests/test_site_paket_boyutlari.py.
    sizeGB: 3.2,
    included: FREE_MODE,
    addonMonthly: FREE_MODE ? 0 : 390,
    get includes() {
      return [
        i18n.t('icerik.profil.arastirma.ic1'),
        i18n.t('icerik.profil.arastirma.ic2'),
        i18n.t('icerik.profil.arastirma.ic3'),
        i18n.t('icerik.profil.arastirma.ic4'),
        i18n.t('icerik.profil.arastirma.ic5'),
        i18n.t('icerik.profil.arastirma.ic6'),
      ]
    },
  },
]

export type Plan = {
  name: string
  /** Abonelik tier kimliği — backend/mobil ile birebir aynı (Supabase subscriptions.tier). */
  tier: 'baslangic' | 'kullandikca' | 'pro' | 'pro_plus'
  /** true → Stripe Checkout'a gider (ücretli); false → indirmeye gider (ücretsiz deneme). */
  paid: boolean
  monthly: number | null
  yearly: number | null
  priceLabel?: string
  period: string
  desc: string
  /**
   * ⚠️ 8. parti — KÖK NEDEN TEMİZLİĞİ: burada `realtime: boolean` ve `queue: string` alanları
   * vardı; kaldırılan "işlem önceliği / kuyrukta bekleme" politikasının kalıntılarıydı. Alan
   * durdukça sayfalar onu yeniden vaade çeviriyordu (fiyat sayfası hero’su, ana sayfa plan
   * kutusu ve ödeme sayfasındaki "Anında analiz" rozeti — üçü de nüksetmişti). Alan SİLİNDİ;
   * görsel vurgu için `highlight`, plan hakkı için aşağıdaki `jetonHakki` kullanılır.
   */
  /** Planın jeton hakkını bir cümlede anlatır (kart üzerinde rozet olarak görünür). */
  jetonHakki: string
  features: readonly string[]
  cta: string
  to: string
  highlight: boolean
  badge?: string
}

/** Araştırma eklentisi — Pro/Pro+ üzerine eklenebilir (Supabase addons:["research"]). */
/** Araştırma eklentisi tarifesi.
 *
 *  ⚠️ `yearly` EKSİKTİ (denetim 2026-08-18) ve `Odeme.tsx` yıllık toplamı `monthly * 12` ile
 *  hesaplıyordu. Oysa yıllık politika "2 ay bedava"dır: `PLANS`ta yearly = monthly × 10
 *  (990→9.900, 1.990→19.900) ve `IYZICO_SETUP.md`deki plan tablosu eklentiyi de aynı kuralla
 *  katıyor (Pro + Araştırma yıllık **₺13.800** = 9.900 + 390×10). Ekranda ₺14.580 yazarken
 *  iyzico ₺13.800 tahsil edecekti — ₺780 fark. Yön "fazla gösterme" olduğu için müşteri fazla
 *  ödemez, ama Ön Bilgilendirme "tahsil edilecek KESİN tutarı" göstermeyi şart koşuyor
 *  (sayfanın kendi yorumu da aynı sebeple daha önce düzeltilmişti). */
export const RESEARCH_ADDON = { monthly: 390, yearly: 3900, get label() { return i18n.t('icerik.profil.arastirmaKucuk') } } as const

/** Üyelik katmanları — fiyat politikası JETON hakkına bağlı (bkz. JETON).
 *  Fiyatlar ₺ (KDV DÂHİL). yearly = 12 ayın toplamı (2 ay ücretsiz).
 *  'Kullandıkça Öde': önden ödeme/aylık ücret YOK; yalnız harcanan jeton faturalanır. */
export const PLANS: Plan[] = [
  {
    get name() { return i18n.t('icerik.plan.baslangic.ad') },
    tier: 'baslangic',
    paid: false,
    monthly: 0,
    yearly: 0,
    get priceLabel() { return i18n.t('indirme.profil.ucretsiz') },
    get period() { return i18n.t('icerik.plan.baslangic.donem') },
    get desc() { return i18n.t('icerik.plan.baslangic.aciklama') },
    get jetonHakki() { return i18n.t('icerik.plan.baslangic.jeton') },
    get features() {
      return [
        i18n.t('icerik.plan.baslangic.o1'),
        i18n.t('icerik.plan.baslangic.o2'),
        i18n.t('icerik.plan.baslangic.o3'),
        i18n.t('icerik.plan.baslangic.o4'),
      ]
    },
    get cta() { return i18n.t('icerik.plan.baslangic.cta') },
    to: '/download',
    highlight: false,
  },
  {
    get name() { return i18n.t('icerik.plan.kullandikca.ad') },
    tier: 'kullandikca',
    paid: true,
    monthly: null,
    yearly: null,
    get priceLabel() { return i18n.t('icerik.plan.kullandikca.fiyat') },
    get period() { return i18n.t('icerik.plan.kullandikca.donem') },
    get desc() { return i18n.t('icerik.plan.kullandikca.aciklama') },
    get jetonHakki() { return i18n.t('icerik.plan.kullandikca.jeton') },
    get features() {
      return [
        i18n.t('icerik.plan.kullandikca.o1'),
        i18n.t('icerik.plan.kullandikca.o2'),
        i18n.t('icerik.plan.kullandikca.o3'),
        i18n.t('icerik.plan.kullandikca.o4'),
        i18n.t('icerik.plan.destekBirGun'),
      ]
    },
    get cta() { return i18n.t('icerik.plan.kullandikca.cta') },
    to: '/download',
    highlight: false,
  },
  {
    name: 'Pro',
    tier: 'pro',
    paid: true,
    monthly: 990,
    yearly: 9900,
    get period() { return i18n.t('icerik.plan.klinikAy') },
    get desc() { return i18n.t('icerik.plan.pro.aciklama') },
    get jetonHakki() { return i18n.t('icerik.plan.pro.jeton') },
    get features() {
      return [
        i18n.t('icerik.plan.pro.o1'),
        i18n.t('icerik.plan.pro.o2'),
        i18n.t('icerik.plan.pro.o3'),
        i18n.t('icerik.profil.vet.ic3'),
        i18n.t('icerik.plan.destekBirGun'),
      ]
    },
    get cta() { return i18n.t('icerik.plan.pro.cta') },
    to: '/download',
    highlight: false,
  },
  {
    name: 'Pro+',
    tier: 'pro_plus',
    paid: true,
    monthly: 1990,
    yearly: 19900,
    get period() { return i18n.t('icerik.plan.klinikAy') },
    get desc() { return i18n.t('icerik.plan.proPlus.aciklama') },
    get jetonHakki() { return i18n.t('icerik.plan.proPlus.jeton') },
    get features() {
      return [
        i18n.t('icerik.plan.proPlus.o1'),
        i18n.t('icerik.plan.proPlus.o2'),
        i18n.t('icerik.plan.proPlus.o3'),
        i18n.t('icerik.plan.proPlus.o4'),
        i18n.t('icerik.plan.proPlus.o5'),
      ]
    },
    get cta() { return i18n.t('icerik.plan.proPlus.cta') },
    to: '/download',
    highlight: true,
    // D6.31 (B-7.1): "Anında analiz" rozeti KALDIRILDI — kaldırılan hız / kuyruk vaadinin (2026-08-20) fiyat kartındaki son kalıntısıydı
    // (ödeme sayfasındaki ikizi 8. partide silinmişti). Planlar jeton hakkıyla ayrışır; rozet yeni bir vaat taşımaz.
  },
]

/** İsteğe bağlı eklentiler (uygulama içi satın alma). Araştırma profili ayrı profil eklentisidir.
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
  { get name() { return i18n.t('icerik.eklenti.jeton.ad') }, get desc() { return i18n.t('icerik.eklenti.jeton.aciklama') }, get price() { return i18n.t('icerik.eklenti.jeton.fiyat') } },
  { get name() { return i18n.t('icerik.eklenti.cihaz.ad') }, get desc() { return i18n.t('icerik.eklenti.cihaz.aciklama') }, get price() { return i18n.t('icerik.eklenti.cihaz.fiyat') } },
  { get name() { return i18n.t('icerik.eklenti.uzak.ad') }, get desc() { return i18n.t('icerik.eklenti.uzak.aciklama') }, get price() { return i18n.t('icerik.eklenti.uzak.fiyat') } },
] as const

/* Akış: siteden küçük "başlatıcı" iner → başlatıcı asıl uygulamayı kurar → Başlat.
   Metin denetimi 2026-08-20: kullanıcıya MİMARİ anlatılmıyor; adımlar ne YAPACAĞINI söylüyor. */
export const LAUNCHER_STEPS = [
  {
    step: '01',
    get title() { return i18n.t('ana.hero.vurgu') },
    get desc() { return i18n.t('icerik.adim.a1.aciklama') },
  },
  {
    step: '02',
    get title() { return i18n.t('icerik.adim.a2.baslik') },
    get desc() { return i18n.t('icerik.adim.a2.aciklama') },
  },
  {
    step: '03',
    get title() { return i18n.t('icerik.adim.a3.baslik') },
    get desc() { return i18n.t('icerik.adim.a3.aciklama') },
  },
] as const

export const FEATURES = [
  {
    // DÜZELTİLDİ: burada "Bluetooth Low Energy" yazıyordu. Üründe BLE YOK — bağlantı yerel ağ
    // üzerinden (mDNS keşfi + HTTP/WebSocket), bobinler ise USB seri (STM32) ve MQTT (ESP32) ile
    // sürülüyor; uzaktan erişim güvenli tünelden. Yanlış yetenek beyanı satış vaadi doğurur.
    n: '01',
    get title() { return i18n.t('icerik.ozellik.f1.baslik') },
    get desc() { return i18n.t('icerik.ozellik.f1.aciklama') },
    icon: 'wifi',
  },
  {
    n: '02',
    get title() { return i18n.t('ekranlar.ekran.hastalar.baslik') },
    get desc() { return i18n.t('icerik.ozellik.f2.aciklama') },
    icon: 'database',
  },
  {
    n: '03',
    get title() { return i18n.t('icerik.ozellik.f3.baslik') },
    get desc() { return i18n.t('icerik.ozellik.f3.aciklama') },
    icon: 'refresh',
  },
  {
    n: '04',
    get title() { return i18n.t('ekranlar.ekran.modeller.baslik') },
    get desc() { return i18n.t('icerik.ozellik.f4.aciklama') },
    icon: 'brain',
  },
  {
    n: '05',
    get title() { return i18n.t('icerik.ozellik.f5.baslik') },
    get desc() { return i18n.t('icerik.ozellik.f5.aciklama') },
    icon: 'shield',
  },
  {
    // macOS derlemesi Apple notarizasyonu tamamlanana kadar YAYINDA DEĞİL (indirme butonu
    // `DOWNLOAD_HOST.macosReady` ile "Yakında" gösteriyor). Özellik metni "üçünde de çalışır"
    // diyerek indirme bölümüyle çelişiyordu; mevcut duruma hizala.
    n: '06',
    get title() { return i18n.t('icerik.ozellik.f6.baslik') },
    get desc() { return i18n.t('icerik.ozellik.f6.aciklama') },
    icon: 'monitor',
  },
] as const

// Sürüm notları CLIENT.version ile HİZALI olmalı: burası 1.2.4/12 Haz 2026'da donmuştu ve
// üründe olmayan "Bluetooth"tan bahsediyordu — site 1.9.8 dağıtırken eski sürüm notu gösteriyordu.
// D6.65 (B-7.31): notlar CHANGELOG.md'nin `## launcher <CLIENT.version>` bölümünden gelir — "Son güncelleme · v1.9.51" altında
// app 1.9.19 / mobil 2.3.20 notları duruyordu. Kapı: `src/__tests__/tanitim-dogrulugu.D6_65.test.ts`.
export const PATCH = {
  version: CLIENT.version,
  get date() { return CLIENT.releaseDate },
  get notes() {
    return [
      i18n.t('icerik.surum.n1'),
      i18n.t('icerik.surum.n2'),
    ]
  },
} as const

/**
 * Plan karşılaştırma tablosu.
 *
 * ⚠️ TIER-ANAHTARLI (8. parti): eskiden `[string, string, string]` konumlu üçlüydü ve tablo
 * başlıkları Pricing.tsx içinde AYRICA gömülüydü. `PLANS`e plan eklendiğinde tablo sessizce
 * eksik kalıyordu. Artık `Record<Plan['tier'], string>`: yeni bir tier eklenirse DERLEYİCİ her
 * satırda değer ister; sütunlar da PLANS'ten türetilir → tek kaynak.
 */
/**
 * PLAN KARŞILAŞTIRMASI — değer SÖZLÜĞÜ İKİ SÖZCÜKLÜDÜR (2026-09-05).
 *
 * ⚠️ ÖNCEDEN '—' glifi İKİ ZIT anlam taşıyordu: 'Jeton başına ücret: —' Pro'da "bu plandan
 * jeton başına ücret ALINMIYOR" (satış argümanı), 'Araştırma profili: —' Başlangıç'ta ise
 * "bu planda YOK" (eksiklik) demekti. Tabloda sütun başlığı bu farkı taşıyordu; mobil KART
 * görünümünde sütun yok, dolayısıyla glif tek başına ANLAMSIZ kalıyordu.
 *
 * SÖZLÜK: 'Alınmıyor' = ücret alınmıyor (AVANTAJ) · 'Yok' = bu planda yok (EKSİKLİK).
 * Kod valansı TAHMİN ETMEZ (etiketten /ücret/i sezgiseli YASAK) — veri söyler.
 * ⚠️ Yeni satır eklerken bu iki sözcükten birini seç; çıplak '—' KULLANMA.
 */
export const COMPARE: { label: string; values: Record<Plan['tier'], string> }[] = [
  { get label() { return i18n.t('icerik.karsilastir.aylikJeton') }, get values() { return { baslangic: '50', kullandikca: i18n.t('icerik.karsilastir.yokKullandikca'), pro: '500', pro_plus: i18n.t('icerik.karsilastir.sayi2000') } } },
  { get label() { return i18n.t('icerik.karsilastir.aylikUcret') }, get values() { return { baslangic: i18n.t('icerik.karsilastir.alinmiyor'), kullandikca: i18n.t('icerik.karsilastir.alinmiyor'), pro: '₺990', pro_plus: i18n.t('icerik.karsilastir.tl1990') } } },
  { get label() { return i18n.t('icerik.karsilastir.jetonUcreti') }, get values() { return { baslangic: i18n.t('icerik.karsilastir.alinmiyor'), kullandikca: i18n.t('icerik.karsilastir.tl290'), pro: i18n.t('icerik.karsilastir.alinmiyor'), pro_plus: i18n.t('icerik.karsilastir.alinmiyor') } } },
  { get label() { return i18n.t('icerik.karsilastir.ekPaket') }, values: { baslangic: '✓', kullandikca: '✓', pro: '✓', pro_plus: '✓' } },
  { get label() { return i18n.t('icerik.karsilastir.aiPro') }, get values() { return { baslangic: i18n.t('icerik.karsilastir.yok'), kullandikca: i18n.t('icerik.karsilastir.aiProSeans'), pro: i18n.t('icerik.karsilastir.aiProSeans'), pro_plus: i18n.t('icerik.karsilastir.aiProSeans') } } },
  { get label() { return i18n.t('icerik.karsilastir.cihaz') }, values: { baslangic: '1', kullandikca: '2', pro: '5', pro_plus: '15' } },
  { get label() { return i18n.t('ana.profiller.rozet') }, get values() { return { baslangic: i18n.t('baslatici.profil.ev'), kullandikca: i18n.t('icerik.karsilastir.evVet'), pro: i18n.t('icerik.karsilastir.evVet'), pro_plus: i18n.t('icerik.karsilastir.evVet') } } },
  { get label() { return i18n.t('icerik.profil.arastirmaKucuk') }, get values() { return { baslangic: i18n.t('icerik.karsilastir.yok'), kullandikca: i18n.t('icerik.karsilastir.arastirmaEk'), pro: i18n.t('icerik.karsilastir.arastirmaEk'), pro_plus: i18n.t('icerik.karsilastir.arastirmaEk') } } },
  { get label() { return i18n.t('icerik.karsilastir.kayitlar') }, get values() { return { baslangic: i18n.t('icerik.karsilastir.temel'), kullandikca: '✓', pro: '✓', pro_plus: '✓' } } },
  { get label() { return i18n.t('icerik.karsilastir.guncelleme') }, values: { baslangic: '✓', kullandikca: '✓', pro: '✓', pro_plus: '✓' } },
  { get label() { return i18n.t('icerik.karsilastir.destek') }, get values() { return { baslangic: i18n.t('icerik.karsilastir.ikiGun'), kullandikca: i18n.t('icerik.karsilastir.birGun'), pro: i18n.t('icerik.karsilastir.birGun'), pro_plus: i18n.t('icerik.karsilastir.ayniGun') } } },
]

/** Karşılaştırma değeri "bu planda yok" mu (eksiklik → soluk gösterim)? Sözlük etkin dilde katalogdan: 'Yok' (TR) / 'None' (EN) —
 *  etiketten valans TAHMİN EDİLMEZ (yukarıdaki kural aynen). */
export const karsilastirmaYokMu = (v: string): boolean => v.startsWith(i18n.t('icerik.karsilastir.yok'))

export const FAQ = [
  {
    get q() { return i18n.t('icerik.sss.program.q') },
    get a() { return i18n.t('icerik.sss.program.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.neden.q') },
    get a() { return i18n.t('icerik.sss.neden.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.isletim.q') },
    get a() { return i18n.t('icerik.sss.isletim.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.internet.q') },
    get a() { return i18n.t('icerik.sss.internet.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.jeton.q') },
    get a() { return i18n.t('icerik.sss.jeton.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.jetonBitince.q') },
    get a() { return i18n.t('icerik.sss.jetonBitince.a') },
  },
  {
    // 8. parti (sahip isteği): "hiç önden satın almadan kullandıkça öde gibi bir üyelik olmalı."
    // Bu maddede ÜÇ soru birden cevaplanmalı — testle kilitli: (1) hiç kullanmazsam ne olur,
    // (2) ne zaman faturalanır, (3) sürpriz fatura sınırı ne (borç tavanı).
    get q() { return i18n.t('icerik.sss.kullandikca.q') },
    get a() { return i18n.t('icerik.sss.kullandikca.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.proProPlus.q') },
    get a() { return i18n.t('icerik.sss.proProPlus.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.aiPro.q') },
    get a() { return i18n.t('icerik.sss.aiPro.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.deneme.q') },
    get a() { return i18n.t('icerik.sss.deneme.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.iptal.q') },
    get a() {
      return i18n.t('icerik.sss.iptal.a', { email: COMPANY.email })
    },
  },
  {
    get q() { return i18n.t('icerik.sss.arastirma.q') },
    get a() { return i18n.t('icerik.sss.arastirma.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.telefon.q') },
    get a() { return i18n.t('icerik.sss.telefon.a') },
  },
  {
    get q() { return i18n.t('icerik.sss.guncelleme.q') },
    get a() { return i18n.t('icerik.sss.guncelleme.a') },
  },
] as const
