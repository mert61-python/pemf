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
 * cihaz kontrolünü ASLA engellemez. Yalnız YENİ analiz isteğini kapılar. Çevrimdışı klinikte
 * yerel rezervden düşülür, bağlantı gelince uzlaşır (servers/jeton.py).
 *
 * Şema: database/supabase_jetonlar.sql · Uçlar: api/tokens.ts · Cihaz tarafı: servers/jeton.py
 */
export const JETON = {
  /** Planın her dönem yenilenen hakkı (devretmez). */
  planHaklari: { baslangic: 50, pro: 500, pro_plus: 2000 },
  /** Bir işlemin kaç jeton yaktığı. Ağır araştırma modelleri daha çok kaynak tüketir. */
  maliyet: { goruntu: 1, ses: 1, sensor: 1, agir_arastirma: 3, ai_pro_seans: 5 },
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
  windowsTag: 'launcher-v1.9.39', // 1.9.39 = COKLU-MODEL-ZIP: launcher bir profilin modellerini birden cok pakette kurabiliyor; boylece 2 GB uzeri buyuk AI agirliklari (bobrek histopatoloji + yara-kapanma modelleri) klinik makinelere inebiliyor. Ayrica indirme kartinda anlik hiza gore KALAN SURE gosterimi. 1.9.38 = BENI HATIRLA + GUNCELLEME SAGLAMLIGI (3. tur denetimi): uygulama kapanirken (guncelleme/pencere) en son oturum jetonu diske islenir ve oturum deposu yazimi ATOMIK yapildi (yarim yazim eski kaydi bozmaz) -> gereksiz "yeniden giris" istekleri elendi; bozuk bir yayinin her acilista yeniden kurulup geri alindigi dongu kiricisi uretimde etkin; calisan backend'i sahiplenen yolda oturum rotasyonu artik baslar; kaldirma/onarimda bobinler her zaman once guvene alinir. 1.9.37 = BENI HATIRLA DUZELTILDI: tedavi penceresi oturum anahtarini tazeledikce yeni oturum client'a geri bildirilir ve diske islenir; oncesinde diskteki kopya eskiyor ve sonraki acilista e-posta+sifre yeniden soruluyordu (ozellikle guncelleme sonrasi). 1.9.36 = BOZUK YAYIN SESSIZCE ONAYLANMIYOR: guncelleme onaylanmadan once tibbi kayit veritabaninin hazir oldugu ayrica dogrulanir; hazir degilse eski surume donulur (cihaz 'acildi' demek 'seans acabiliyor' demek degildi). 1.9.35 = GUNCELLEME ALTYAPISI DENETIMI: kesintiden sonra toparlanma (yarim kalan guncelleme diski kilitlemiyor, uygulama katmani kesintisi kurtariliyor), iki pencere birbirinin kurulumunu bozamiyor, tek disk hatasi GB'larca bosuna indirme baslatmiyor, geri alma artik 'donuldu' derken gercekten donuyor, cevrimdisi acilan makine de guncelleme kontrolu yapiyor, bozuk bir yayin sonsuz dongude yeniden denenmiyor. 1.9.32 = BAKIM/DOGRULAMA: guncelleme akisi uctan uca canli teste tabi tutuldu (istemci sessiz self-update + Android uygulama-ici guncelleme); islevsel degisiklik yok. 1.9.30 = BASLAT DUGMESI guncelleme kontrolu bitmeden cikmiyor (kontrol surerken 'Guncelleme kontrol ediliyor...' yazip bekliyor; tiklama bosa gitmiyor). Ekran DONMUYOR: kurulu cihazda Hazir! aninda cizilir, bekleyen yalniz dugme; internet yoksa dugme hemen acilir. 1.9.29 = GUNCELLEME GORUNURLUGU: arka plan indirmesinde yuzde+bar; SUREKLI ACIK cihazlar da guncelleme aliyor (6 saatte bir kontrol; onceden yalniz acilista bakiliyordu, gunlerce kapatilmayan klinik makinesi yeni surumu HIC gormuyordu -> zorunlu guvenlik guncellemesi de ulasamiyordu); indirme oncesi DISK kontrolu + eski paket temizligi; iki pencere ayni anda guncelleme yapamaz. Suren seans ASLA kesilmez: periyodik tur yalniz indirir+bildirir, kurulum kapat-ac aninda. 1.9.28 = KALDIR -> YENIDEN KUR temiz: Ayarlar > Uygulamalar'dan kaldirmada MQTT broker'i sahipsiz kalip 1883'u tutuyordu -> yeniden kurulumda broker baslamiyor, 6-8 numarali bobinler ULASILAMAZ oluyordu (1-5 seri porttan calistigi icin cihaz calisiyor gibi gorunuyordu). Kaldirma artik broker+tunel yardimcisini adlariyla durduruyor. 1.9.27 = KARARSIZ BAGLANTIDA yanlis "internet yok" (manifest cekimi tek denemeydi; anlik TCP sifirlamasi kurulumu 3'te 1 engelliyordu) -> 3 deneme + kalici hatalarda tekrar yok. 1.9.25 = DENETIM MASASI BOYUTU gercegi yansitiyor (NSIS kurulum aninda ~11 MB yaziyordu; runtime+profiller sonra iniyor). 1.9.24 = GUVENLIK DUVARI UYARISI yanlis alarm vermiyor: Windows'un KENDI izni de sayiliyor; 'kural yok' acilista SUSAR (yalniz Baslat'tan sonra uyarir), acik Block kuralinda her zaman uyarir. 1.9.23 = YARIM KALMIS KURULUM artik 'Hazir!' gorunmuyor (butunluk exe VARLIGI yerine YAPISAL kontrolle olculuyor). 1.9.22 = KESINTI/ESZAMANLILIK: guncelleme ortasinda kapanma artik 'kurulu degil' demiyor (yarim takas acilista kurtarilir); ayni anda iki client kurulum yapamaz; bozuk indirmede tek-seferlik temiz yeniden-deneme. 1.9.21 = SIYAH KONSOL PENCERESI duzeltildi: yardimci komutlar (guvenlik duvari denetimi + kurulum ACL) pencereli launcher'dan calisirken Windows onlara yeni konsol aciyordu; kapat-ac akisinda 2 pencere goruluyordu. 1.9.20 = SAHA ARIZASI: kurulum sonrasi cihaz acilmiyordu (at-rest anahtar uyusmazliginda karantina + veri-gocu sonsuz dongusu + launcher yanlis gunluk yolu + baglanti sizintisi). Ayrica URETICI KIMLIGI duzeltildi: UAC/Yayimci artik IBIA Teknoloji Ltd. Sti. 1.9.19 = PROFIL BAGIMLILIGI KAYNAGINDAN KALKTI: AI Pro organ lokalizasyonu modelleri (inference_cat_organ, ~209 MB) yalniz home.zip'te idi → cekirdege (base-deps) alindi; profiller arasi artik NE zorunlu NE islevsel bag var, home.zip 528→318 MB. 1.9.18 = PROFILLER BAGIMSIZ: 'Veteriner' secilince 'Ev Sahibi' artik ZORLA eklenmiyor (yalniz Vet+Arastirma kurulabilir). 1.9.17 = GIRIS EKRANI: parola goster/gizle + hatali giriste alan temizlenir + gorunmez karakter/bosluk uyarisi (dogru parola 'hatali' deniyordu, alan silinip tekrar yazilinca geciyordu). 1.9.16 = URETIME-HAZIRLIK DENETIMI (Tier 0-3): geri cagirma (min_supported_version), kurulum oncesi disk-alani kontrolu + olu onbellek temizligi, guvenlik-duvari kurali, filo envanteri (surum alanlari heartbeat'te), surum dosyasi app katmaninda (siradan yayinda artik tazelenir). 1.9.13 = KATMANLI GUNCELLEME: paket app(~71MB)+deps(~1,19GB) olarak ayrildi → siradan surum 1,3 GB yerine ~71 MB iner. 1.9.12 = UYGULAMA OTO-GUNCELLEME: client acilista base.zip + model paketlerini de manifest sha'siyla karsilastirip yeniler ("Onar" gerekmez; seans sirasinda ertelenir). 1.9.11 = arayuz metinlerinde "tedavi" -> "seans" (client + kurulum + guncelleme uyarilari). 1.9.9 = client GIRISI (Supabase + Beni hatirla) + oturum devri (uygulamada cift login yok) + cevrimdisi acilis kilidi fix + header tasmasi fix. 1.9.8 = yarım-kalan çoklu-kurulumda tamamlanan profil korunur (iptal→Hazır!) + 1.9.7 Başlat ayrı-pencere (client açık kalır) + 1.9.6 uninstall (os error 5) fix → kayıtlı NSIS uninstaller'ı başlatır. 1.9.5 = KRİTİK backend-deadlock fix (stdout→NUL) + 1.9.4 self-update/uninstaller-fix. Windows-only → mac/linux 1.9.2'de. // Windows'a AYRI etiket: 1.9.4 = self-update + uninstaller-fix (işaretsiz kaldırmada profiller korunur). Windows-only → mac/linux 1.9.2'de kalır (404 olmasın).
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
  androidTag: 'launcher-v1.9.39',
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
  androidVersion: '2.3.25',
  /** İndir sayfasında telefon kartında gösterilir — uygulamanın ROLÜNÜ açıklar (tek başına
   *  terapi uygulamaz; masaüstündeki cihazın uzaktan kumandasıdır). */
  androidRolNotu: 'Kliniğinizdeki cihaza bağlanır: seans başlatıp durdurabilir, bobin ayarlarını değiştirebilir, sensörleri izleyebilir ve hasta kayıtlarına bakabilirsiniz. Cihazın bağlı olduğu klinik bilgisayarı açık olmalıdır.',
  /** İndir sayfasında telefon kartının altında gösterilir — iki farklı numarayı açıklar. */
  androidVersionNote: 'Telefon uygulamasının sürüm numarası bilgisayar uygulamasından ayrıdır; ikisi bağımsız güncellenir.',
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
  version: '1.9.39',
  channel: 'Sürüm 2026.1',
  sizeMB: 3, // NSIS launcher setup ~2.9 MB (asıl uygulama+modeller client içinden iner)
  releaseDate: '27 Ağu 2026',
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
      os: 'Android 8.0 ve üzeri · telefona doğrudan kurulur',
      ready: DOWNLOAD_HOST.androidReady,
      version: DOWNLOAD_HOST.androidVersion,
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
    name: 'Evcil Hayvan Sahibi',
    tagline: 'Hekiminizin belirlediği protokolü evde uygulayın; kamera destekli ön-değerlendirme.',
    // manifest profiles.home = 0,30 GB (eskiden 0.6 yazıyordu; `cat_organ` modelleri
    // çekirdeğe taşınınca home.zip 528 → 318 MB'a düştü, site güncellenmemişti).
    sizeGB: 0.3,
    included: true,
    addonMonthly: 0,
    includes: [
      'Kedide yüz ifadesinden ağrı skoru (FGS)',
      'Görüntüde bölge ayırma',
      'Kedide organ konumu (üç boyutlu)',
      'Kedi sesi analizi',
      'Hastalık ön-değerlendirme (bilgilendirme amaçlı — teşhis değildir)',
    ],
  },
  {
    id: 'vet',
    name: 'Veteriner Hekim',
    tagline: 'Tam klinik kontrol: frekansı elle ayarlama, canlı sensör, hasta kayıtları.',
    // manifest profiles.vet = 0,12 GB (eskiden 0.9 yazıyordu — 7 kat fazla).
    sizeGB: 0.1,
    included: true,
    addonMonthly: 0,
    includes: [
      'Frekans ve bobinleri elle ayarlama',
      'Canlı sensör ekranı (alan şiddeti mT · sıcaklık °C)',
      'Şifreli hasta kayıtları + klinik istatistikleri',
      'AI Pro: ölçümlere göre kendini ayarlayan otomatik seans',
      'Tüm klinik AI modelleri',
    ],
    recommended: true,
  },
  {
    id: 'research',
    name: 'Araştırma Profili',
    tagline: FREE_MODE
      ? 'Kanser-araştırma modelleri — test aşamasında ücretsiz.'
      : 'Kanser-araştırma modelleri — ağır indirme; ücretli eklenti.',
    // manifest profiles.research = 1,46 GB.
    sizeGB: 1.5,
    included: FREE_MODE,
    addonMonthly: FREE_MODE ? 0 : 390,
    includes: [
      'Fantom tümör + elektromanyetik alan ölçümü',
      'Petri kuyucuğu (kanser hücre analizi)',
      'Böbrek RNA analizi (KIRC — berrak hücreli böbrek kanseri)',
      'Böbrek bilgisayarlı tomografi (BT)',
      'Böbrek patoloji (histopatoloji)',
      'Kronik böbrek hastalığı (CKD) tahmini',
    ],
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
export const RESEARCH_ADDON = { monthly: 390, yearly: 3900, label: 'Araştırma profili' } as const

/** Üyelik katmanları — fiyat politikası JETON hakkına bağlı (bkz. JETON).
 *  Fiyatlar ₺ (KDV DÂHİL). yearly = 12 ayın toplamı (2 ay ücretsiz).
 *  'Kullandıkça Öde': önden ödeme/aylık ücret YOK; yalnız harcanan jeton faturalanır. */
export const PLANS: Plan[] = [
  {
    name: 'Başlangıç',
    tier: 'baslangic',
    paid: false,
    monthly: 0,
    yearly: 0,
    priceLabel: 'Ücretsiz',
    period: '14 gün deneme',
    desc: 'Evcil Hayvan Sahibi profiliyle sistemi ücretsiz deneyin.',
    jetonHakki: 'Ayda 50 jeton (≈50 yapay zekâ analizi)',
    features: [
      'Evcil Hayvan Sahibi profili · 1 cihaz',
      'Yapay zekâ teşhis — jeton hakkınız kadar',
      'Şifreli hasta kaydı',
      '14 gün tam erişim',
    ],
    cta: 'Denemeyi Başlat',
    to: '/download',
    highlight: false,
  },
  {
    name: 'Kullandıkça Öde',
    tier: 'kullandikca',
    paid: true,
    monthly: null,
    yearly: null,
    priceLabel: '₺2,90 / jeton',
    period: 'aylık ücret yok',
    desc: 'Önden ödeme yok: yalnız yaptığınız analizler kadar ödersiniz.',
    jetonHakki: 'Aylık jeton hakkı yok — harcadığınız kadar faturalanır',
    features: [
      'Aylık ücret ve önden jeton alımı YOK',
      'Kullanmadığınız ay ücret çıkmaz',
      'Veteriner profili · 2 cihaza kadar',
      'Harcanan jetonlar dönem sonunda faturalanır',
      'E-posta ve uzak destek — 1 iş günü içinde yanıt',
    ],
    cta: 'Kullandıkça Öde ile Başla',
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
    desc: 'Aktif klinikler için tam sürüm — ayda 500 jeton.',
    jetonHakki: 'Ayda 500 jeton (≈500 yapay zekâ analizi)',
    features: [
      'Veteriner profili · 5 cihaza kadar',
      'Yapay Zekâ Merkezi + AI Pro (sensöre göre otomatik seans)',
      'Biten jetonu ek paketle tamamlarsınız',
      'Şifreli hasta kayıtları + klinik istatistikleri',
      'E-posta ve uzak destek — 1 iş günü içinde yanıt',
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
    desc: 'Yoğun klinikler için — ayda 2.000 jeton ve 15 cihaz.',
    jetonHakki: 'Ayda 2.000 jeton (≈2.000 yapay zekâ analizi)',
    features: [
      'Pro’daki her şey',
      'AI Pro otomatik seans (seans başına 5 jeton)',
      '15 cihaza kadar aynı anda bağlantı',
      'Araştırma profili eklenebilir (+₺390/ay)',
      'Öncelikli destek — aynı iş günü içinde yanıt',
    ],
    cta: 'Pro+’ya Yükselt',
    to: '/download',
    highlight: true,
    badge: 'Anında analiz',
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
  { name: 'Ek Jeton Paketi', desc: 'Jetonunuz bittiğinde tamamlayın — satın alınan jetonların süresi dolmaz.', price: '₺249’dan başlayan' },
  { name: 'Ek Cihaz Hakkı', desc: 'Aynı anda bağlanabilecek cihaz sayısını bir artırır.', price: '₺149 / ay' },
  { name: 'Uzaktan Erişim', desc: 'Klinik dışındayken cihazı şifreli bağlantıyla izleyip yönetin.', price: '₺249 / ay' },
] as const

/* Akış: siteden küçük "başlatıcı" iner → başlatıcı asıl uygulamayı kurar → Başlat.
   Metin denetimi 2026-08-20: kullanıcıya MİMARİ anlatılmıyor; adımlar ne YAPACAĞINI söylüyor. */
export const LAUNCHER_STEPS = [
  {
    step: '01',
    title: 'PEMF Vet’i indirin',
    desc: 'Sitemizden küçük kurulum dosyasını (yaklaşık 3 MB) indirip birkaç tıkla kurun. Masaüstünüze PEMF Vet kısayolu eklenir.',
  },
  {
    step: '02',
    title: 'Başlatıcı gerisini halleder',
    desc: 'Kurduğunuz başlatıcı, asıl PEMF Vet uygulamasını — yapay zekâ modelleri ve cihaz yazılımı dahil — sizin için indirip kurar. Beklemeniz yeterli.',
  },
  {
    step: '03',
    title: '“Başlat”a basın',
    desc: 'İndirme bitince “Başlat” düğmesi çıkar; tek tıkla uygulama açılır. Yeni sürümler de kendiliğinden gelir — elle kurulum yapmanız gerekmez.',
  },
] as const

export const FEATURES = [
  {
    // DÜZELTİLDİ: burada "Bluetooth Low Energy" yazıyordu. Üründe BLE YOK — bağlantı yerel ağ
    // üzerinden (mDNS keşfi + HTTP/WebSocket), bobinler ise USB seri (STM32) ve MQTT (ESP32) ile
    // sürülüyor; uzaktan erişim güvenli tünelden. Yanlış yetenek beyanı satış vaadi doğurur.
    n: '01',
    title: 'Otomatik Cihaz Bağlantısı',
    desc: 'Cihazı aynı Wi-Fi ağında otomatik bulur; frekans ve şiddet değişiklikleri anında uygulanır, sensör verisi canlı akar.',
    icon: 'wifi',
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
    desc: 'Cihaz yazılımınız ve yapay zekâ modelleriniz tek tıkla güncellenir; her zaman en yeni sürümle çalışırsınız.',
    icon: 'refresh',
  },
  {
    n: '04',
    title: 'Yapay Zekâ Merkezi',
    desc: 'Kamerayla desteklenen teşhis: yüz ifadesinden ağrı skoru, organların üç boyutlu konumu ve AI Pro — sensörden gelen ölçümlere göre seansı kendi kendine ayarlayan otomatik mod.',
    icon: 'brain',
  },
  {
    n: '05',
    title: 'Klinik Güvenlik',
    desc: 'Acil durdurma düğmesi, otomatik süre sınırı ve hedef kontrolü: seans, uygulanacak bölge güvenle tespit edilmeden başlamaz.',
    icon: 'shield',
  },
  {
    // macOS derlemesi Apple notarizasyonu tamamlanana kadar YAYINDA DEĞİL (indirme butonu
    // `DOWNLOAD_HOST.macosReady` ile "Yakında" gösteriyor). Özellik metni "üçünde de çalışır"
    // diyerek indirme bölümüyle çelişiyordu; mevcut duruma hizala.
    n: '06',
    title: 'Çoklu Platform',
    desc: 'Windows bilgisayarlarda ve Android telefonlarda tek uygulama (macOS ve Linux hazırlanıyor); klinik verileri cihazda şifreli tutulur, klinik dışından erişim şifreli bağlantıyla yapılır.',
    icon: 'monitor',
  },
] as const

// Sürüm notları CLIENT.version ile HİZALI olmalı: burası 1.2.4/12 Haz 2026'da donmuştu ve
// üründe olmayan "Bluetooth"tan bahsediyordu — site 1.9.8 dağıtırken eski sürüm notu gösteriyordu.
export const PATCH = {
  version: CLIENT.version,
  date: CLIENT.releaseDate,
  notes: [
    'Güvenlik ve kayıt doğruluğu sürümü: bobin bir komutu reddederse artık ekranda sebebiyle görünür ve tedavi geçmişine hiç çalışmamış bobin yazılmaz.',
    'Acil durdurmanın bulut yedeği ve kapanan seans kayıtları arka planda sağlamlaştırıldı; telefon ile bilgisayar sürümü farklıysa uygulama bunu artık açıkça söyler.',
  ],
} as const

/**
 * Plan karşılaştırma tablosu.
 *
 * ⚠️ TIER-ANAHTARLI (8. parti): eskiden `[string, string, string]` konumlu üçlüydü ve tablo
 * başlıkları Pricing.tsx içinde AYRICA gömülüydü. `PLANS`e plan eklendiğinde tablo sessizce
 * eksik kalıyordu. Artık `Record<Plan['tier'], string>`: yeni bir tier eklenirse DERLEYİCİ her
 * satırda değer ister; sütunlar da PLANS'ten türetilir → tek kaynak.
 */
export const COMPARE: { label: string; values: Record<Plan['tier'], string> }[] = [
  { label: 'Aylık jeton hakkı', values: { baslangic: '50', kullandikca: 'Yok — kullandıkça', pro: '500', pro_plus: '2.000' } },
  { label: 'Aylık ücret', values: { baslangic: 'Yok', kullandikca: 'Yok', pro: '₺990', pro_plus: '₺1.990' } },
  { label: 'Jeton başına ücret', values: { baslangic: '—', kullandikca: '₺2,90', pro: '—', pro_plus: '—' } },
  { label: 'Ek jeton paketi', values: { baslangic: '✓', kullandikca: '✓', pro: '✓', pro_plus: '✓' } },
  { label: 'AI Pro otomatik seans', values: { baslangic: 'Yok', kullandikca: '✓ (5 jeton/seans)', pro: '✓ (5 jeton/seans)', pro_plus: '✓ (5 jeton/seans)' } },
  { label: 'Aynı anda bağlanan cihaz', values: { baslangic: '1', kullandikca: '2', pro: '5', pro_plus: '15' } },
  { label: 'Kurulum profilleri', values: { baslangic: 'Evcil Hayvan Sahibi', kullandikca: 'Evcil Hayvan Sahibi + Veteriner', pro: 'Evcil Hayvan Sahibi + Veteriner', pro_plus: 'Evcil Hayvan Sahibi + Veteriner' } },
  { label: 'Araştırma profili', values: { baslangic: '—', kullandikca: '+₺390/ay', pro: '+₺390/ay', pro_plus: '+₺390/ay' } },
  { label: 'Hasta kayıtları + istatistikler', values: { baslangic: 'Temel', kullandikca: '✓', pro: '✓', pro_plus: '✓' } },
  { label: 'Otomatik güncelleme', values: { baslangic: '✓', kullandikca: '✓', pro: '✓', pro_plus: '✓' } },
  { label: 'Destek yanıt süresi', values: { baslangic: '2 iş günü', kullandikca: '1 iş günü', pro: '1 iş günü', pro_plus: 'Aynı iş günü' } },
]

export const FAQ = [
  {
    q: 'İndirdiğim program tam olarak nedir?',
    a: 'Siteden indirdiğiniz küçük kurulum dosyasına “başlatıcı” diyoruz (indirilen dosyanın adı PEMFVetClient-Setup-…exe’dir). Kurulumu birkaç tıkla tamamlarsınız; program açıldığında asıl PEMF Vet uygulamasını — yapay zekâ modelleri ve cihaz yazılımı dahil — sizin için indirip kurar, bitince “Başlat” ile açarsınız. Sonraki güncellemeleri de o getirir; siz bir daha dosya indirmezsiniz.',
  },
  {
    q: 'Neden doğrudan uygulamayı indirmiyorum?',
    a: 'Uygulama ve yapay zekâ modelleri birkaç gigabayt tutuyor ve sık güncelleniyor. Başlatıcı yalnız değişen parçaları indirir; böylece ilk kurulumdan sonraki güncellemeler küçük ve hızlı olur, siz de her seferinde büyük bir dosya indirmezsiniz.',
  },
  {
    q: 'Hangi işletim sistemleri destekleniyor?',
    a: 'Şu an Windows 10/11 (64-bit) bilgisayarlar ve Android 8.0+ telefonlar. macOS ile Linux sürümleri hazırlanıyor; hazır olduklarında İndir sayfasında görünecekler.',
  },
  {
    q: 'İnternet olmadan çalışır mı?',
    a: 'İlk kurulum ve güncellemeler için internet gerekir. Kurulumdan sonra yapay zekâ modelleri cihazınızda çalışır ve klinik verileriniz cihazda şifreli tutulur — seans yapmak için internet şart değildir. İnternet yalnız güncelleme, hesap doğrulama ve (açtıysanız) klinik dışından erişim için kullanılır. Planınız ise ayda kaç yapay zekâ analizi yapabileceğinizi belirler (bkz. “Pro ile Pro+ arasındaki fark ne?”).',
  },
  {
    q: 'Jeton nedir, neye harcanır?',
    a: 'Jeton, yapay zekâ analizlerinin birimidir: bir görüntü, ses veya sensör analizi 1 jeton; ağır araştırma modelleri (patoloji, RNA, tomografi) 3 jeton; AI Pro’nun otomatik seansı seans başına 5 jeton harcar. Planınız her ay belirli bir jeton hakkıyla yenilenir; hakkınız biterse ek paket alabilirsiniz. ⚠️ Jeton yalnız YAPAY ZEKÂ ANALİZİ içindir: seans başlatma, süren seansı sürdürme, acil durdurma, sensör izleme ve cihaz kontrolü jetondan BAĞIMSIZDIR — jeton bitse bile seans ve acil durdurma engellenmez.',
  },
  {
    q: 'Jetonum biterse ne olur? Kullanmadığım jetonlar ne oluyor?',
    a: 'Jetonunuz bittiğinde yeni yapay zekâ analizi başlatamazsınız; tedavi tarafı etkilenmez (seans, acil durdurma ve sensör izleme çalışmaya devam eder). Ek paket alarak hemen devam edebilirsiniz. Planınızın aylık hakkı her dönem yenilenir ve bir sonraki aya devretmez; buna karşılık satın aldığınız jetonların süresi yoktur — kullanana kadar hesabınızda durur. İnternetiniz yokken de analiz yapabilirsiniz: tüketim cihazınızda tutulur ve bağlantı gelince hesabınıza işlenir.',
  },
  {
    // 8. parti (sahip isteği): "hiç önden satın almadan kullandıkça öde gibi bir üyelik olmalı."
    // Bu maddede ÜÇ soru birden cevaplanmalı — testle kilitli: (1) hiç kullanmazsam ne olur,
    // (2) ne zaman faturalanır, (3) sürpriz fatura sınırı ne (borç tavanı).
    q: 'Kullandıkça Öde nasıl çalışıyor?',
    a: 'Aylık ücret ödemez, önden jeton satın almazsınız. Kartınızı bir kez tanımlarsınız; yalnız yaptığınız analizler kadar, jeton başına ₺2,90 üzerinden ücretlendirilirsiniz. O ay hiç analiz yapmazsanız hiç ücret çıkmaz. Harcamanız ay sonunda toplu olarak faturalanır. Faturalanmamış kullanım 300 jetona ulaşırsa, ödeme alınana kadar yeni analiz başlatılamaz — böylece beklemediğiniz büyüklükte bir fatura oluşmaz. ⚠️ Bu sınır yalnız yapay zekâ analizleri içindir: seans başlatma, süren seansı sürdürme, acil durdurma ve sensör izleme her koşulda çalışır. Düzenli olarak ayda 340’tan fazla analiz yapıyorsanız Pro planı daha ucuza gelir.',
  },
  {
    q: 'Pro ile Pro+ arasındaki fark ne?',
    a: 'İkisinde de aynı uygulama ve aynı yapay zekâ modelleri vardır; fark aylık jeton hakkı, cihaz sayısı ve destek hızıdır. Pro: ayda 500 jeton, 5 cihaza kadar bağlantı, 1 iş günü içinde destek. Pro+: ayda 2.000 jeton, 15 cihaza kadar bağlantı, aynı iş günü içinde öncelikli destek. Kliniğinizde tek cihaz varsa ve ayda birkaç yüz analiz yetiyorsa Pro çoğu durumda yeterlidir; jeton biterse her iki planda da ek paket alabilirsiniz.',
  },
  {
    q: 'AI Pro nedir? Hayvana kendi başına terapi mi uygular?',
    a: 'AI Pro, seans sırasında sensörlerden gelen ölçümlere (sıcaklık, alan şiddeti, kamera görüntüsü) bakarak seans ayarlarını otomatik güncelleyen moddur. Seansı HER ZAMAN siz başlatır, siz durdurursunuz; acil durdurma, süre sınırı ve sıcaklık kesmesi her koşulda önceliklidir. Cihaz kendi kendine seans başlatmaz ve hekim denetimi olmadan tedavi uygulamaz — nihai karar ve sorumluluk hekimindir.',
  },
  {
    q: '14 günlük deneme sonunda ne oluyor?',
    a: 'Deneme süresi bittiğinde hiçbir ücret çekilmez; kart bilgisi zaten istemiyoruz. Hesabınız ücretsiz Başlangıç düzeyinde çalışmaya devam eder: ayda 50 jeton ve 1 cihaz. Uygulama, hasta kayıtlarınız ve cihaz kontrolü aynen kalır. Daha çok analiz gerekiyorsa hesabınızdan bir plan seçersiniz. (Test aşamasında tüm planlar ücretsiz olduğu için şu an bir kısıtlama uygulanmıyor.)',
  },
  {
    q: 'Aboneliğimi nasıl iptal ederim? Param iade edilir mi?',
    a: `“Hesabım” menüsündeki “Aboneliği iptal et” ile iptal edersiniz; kısa bir onay adımından sonra otomatik yenileme durur ve bir daha ücret alınmaz. İade koşulları Mesafeli Satış Sözleşmesi ve Ön Bilgilendirme Formu’nda yazılıdır; sorunuz olursa ${COMPANY.email} adresine yazın.`,
  },
  {
    q: 'Araştırma profili kime gerekli?',
    a: 'Üniversite, laboratuvar ve Ar-Ge ekipleri için: fantom tümör ve elektromanyetik alan ölçümü, petri kuyucuğu analizi, böbrek RNA, bilgisayarlı tomografi ve patoloji modelleri gibi araştırma araçlarını içerir. Günlük klinik pratiği için gerekli değildir — Veteriner profili yeterlidir.',
  },
  {
    q: 'Telefon uygulaması ne işe yarıyor?',
    a: 'Telefon uygulaması kliniğinizdeki cihaza bağlanan tam bir kumandadır: seans başlatıp durdurabilir, bobin ayarlarını değiştirebilir, sensör ölçümlerini canlı izleyebilir, acil durdurma yapabilir ve hasta kayıtlarına bakabilirsiniz. Cihaz klinikteki bilgisayara bağlı olduğu için o bilgisayarın açık olması gerekir; aynı ağdayken doğrudan, dışarıdayken güvenli bağlantıyla erişirsiniz. Giriş için masaüstüyle aynı hesabı kullanırsınız.',
  },
  {
    q: 'Güncellemeler ücretli mi?',
    a: 'Hayır. Uygulama, cihaz yazılımı ve yapay zekâ modeli güncellemelerinin tamamı planınıza dahildir.',
  },
] as const
