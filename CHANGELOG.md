# Değişiklik Kaydı — PEMF Vet

> **Neden bu dosya var.** Cihaz yazılımı **sessizce ve otomatik** güncelleniyor: PEMF Vet Client
> açılışta manifest'e bakar, yeni paketi indirir, kurar. Klinik hiçbir şey yapmaz — ve değişikliğin
> ne olduğunu **hiçbir yerden okuyamıyordu.** Sessiz güncelleme ile değişiklik kaydı yokluğu tek
> başına değil, *birlikte* kötüdür: bir davranış değiştiğinde veteriner bunu arıza sanar, destek de
> hangi sürümün ne yaptığını bilemez. (2026-08-09 denetimi, Tier 3.)

## launcher 1.9.45 — 2026-09-04 (⏳ Guncelleme sirasinda ekran artik BOS KALMIYOR)

- **Saha bildirimi:** oto-guncellemede pencere kapaniyor, yeni surum acilana kadar ekranda HICBIR
  SEY yoktu; kullanici bu bosluk sirasinda uygulamayi yeniden acmaya calisiyordu. Olculen bosluk:
  sabit 3 sn bekleme + Windows Defender'in 265 MB kurulum dosyasini calistirmadan once bastan sona
  taramasi (yavas klinik makinesinde 10-30 sn) + sessiz kurulum + 2 sn bekleme.
- **Bilgilendirme penceresi:** launcher cikmadan hemen once kendi kopyasini (`%TEMP%`, FARKLI ADLA —
  NSIS'in "uygulama calisiyor" denetimi `PEMFVetClient.exe` adina bakar) `--guncelleme-ekrani` kipinde
  acar: "Baslatici guncelleniyor… PEMF Vet birazdan kendiliginden acilacak; bu pencereyi kapatmaniz ya
  da uygulamayi yeniden acmaniz gerekmez." + hareketli bar; 90 sn gecerse "uzun surdu" ipucu. Pencere
  yeni surum acilinca (isaret dosyasi silinince) ya da en gec 3 dk sonra kendini kapatir; backend'e,
  oturuma, kuruluma dokunmaz. Kip acilamazsa guncelleme eski davranisla yine surer.
- **Boslukta yeniden tiklama korumasi:** `selfupdate_inprogress.json` isareti (kurulum koku). Taze
  isaret (<=2 dk) + calisan surum = eski surum ise exe SESSIZCE cikar (pencere zaten ekranda, NSIS'in
  dosya kilidine carpilmaz). Yeni surum acilinca isaret temizlenir; bayat isaret ya da hedef == kaynak
  ASLA kilitlemez (basarisiz kurulumda uygulama yine acilir).
- **Yeniden-baslatici daha hizli ve guvenli:** sabit 3 sn yerine launcher'in cikisini PID ile bekler
  (~1 sn adim, en cok 30 sn); kurulumdan sonra uygulama zaten calisiyorsa (kullanici kendisi acti)
  ikinci pencere ACMAZ; pencere kopyasini siler; `tasklist`/`find` tam yolla cagrilir (PATH'te Git'in
  `find`i one cikabiliyordu). Calisan-uygulama kontrolu CSV biciminde (tablo ciktisi adi 25 karakterde
  kirpiyordu; uzun ad eslesmeyince ikinci pencere aciliyordu — gercek cmd.exe'de olculdu).
- Kaldirma temizlik listesi + profil paketi yasakli kok dosyalari: `selfupdate_inprogress.json` eklendi.
- Kilitler: `relaunch_script_gomer_ve_enjeksiyon_reddeder` (PID bekleme, start korumasi, kopya silme,
  tam yollar), `guncelleme_ekrani_sirasi_ve_acilis_bekcisi` (isaret → pencere → batch → cik sirasi;
  bekci Builder'dan once), `guncelleme_isareti_testleri` (taze/bayat/from==to/bozuk JSON).
- Gecis notu: 1.9.44 → 1.9.45 guncellemesi ESKI kodla uygulanir (bu tek seferde bosluk yine gorulur);
  1.9.45'ten sonraki guncellemelerde pencere gosterilir.

## app 1.9.40 — 2026-09-03 (🔑 Guncelleme sonrasi giris istenmesi — ASIL neden duzeltildi)

- **Guncelleme sonrasi (ya da uygulamayi acmadan yapilan birkac launcher acilisindan sonra) e-posta+sifre
  yeniden isteniyordu.** Kok neden (bu makinede dosya-sistemi gunlugu ve Supabase kaynagiyla OLCULDU):
  uygulama penceresi, launcher ile AYNI oturum jeton ailesinin KENDI kalici kopyasini tarayici deposunda
  tutuyor ve her acilista launcher'in devrinden ONCE o ESKI kopyayla yenilemeye kalkiyordu. Launcher ise
  uygulama acilmadan yapilan acilislarda (guncelleme gunu: oto-guncelleme, uzun indirme, kapat-ac) jetonu
  kendi basina yeniliyor ama pencerenin kopyasini guncellemiyordu. Kopya 2+ nesil geride kalinca Supabase
  guvenlik kurali (yeniden-kullanim tespiti) TUM aileyi iptal ediyor -> launcher'daki taze jeton da
  gecersizlesiyor -> sonraki acilista giris ekrani.
- **Cozum:** launcher'in actigi pencerede (masaustu) oturum artik KALICI TUTULMAZ (pencere omru boyunca
  bellekte); eski kalici kopya bir kez temizlenir. Pencere daima launcher'in devrettigi taze oturumla
  baslar. Telefon/LAN tarayici davranisi DEGISMEDI. Kilit: `supabaseAuthDesktopStorage.test.ts`.
- ⚠️ Gecis: bu surumu alan makinede bir kez daha giris istenebilir (eski aile zaten iptal olmus
  olabilir); sonrasinda oturum guncellemeler boyunca korunur.

Paket kimliği (`buildId`): `f7369b58eee1`. Monolit `base.zip` sha: `8b3ae5c14c04`.

## launcher 1.9.44 — 2026-09-03 (🔑 Guncelleme sonrasi "Beni hatirla" — ikincil kemerler)

- **Baglam:** "guncelleme sonrasi e-posta+sifre yeniden" belirtisinin ASIL nedeni uygulama
  penceresindedir ve **app 1.9.40**'ta duzeltildi (yukaridaki giris). Bu launcher surumu, ayni
  belirtiyi ikincil yollardan uretebilecek uc bosluğu kapatan **guvenlik kemerleridir**; tek
  baslarina belirtiyi uretmezler (Supabase bir nesil geriyi tolere eder) ama birikince uretirler.
- **[F5] Oto-guncelleme cikisinda son oturum yakalama:** self-update yolu `app.exit(0)` ile cikiyor,
  normal kapanistaki "kapanis-oncesi son oturum yakalama" bu yolda yoktu. Artik yeniden-baslatici
  calismadan ONCE, yalniz bu oturumun izlenen backend'inden son oturum diske islenir.
  Parite testi: `f5_selfupdate_son_yakalama_var`.
- **[S4] Bellekteki oturum rotasyonla senkron:** rotasyonla gelen taze oturum yalniz DISKE
  yaziliyor, bellekteki kopya guncellenmiyordu; uygulama guncellemesi backend'i yeniden baslatinca,
  ikinci "Baslat"ta ya da calisan backend sahiplenilince BAYAT bellek oturumu devrediliyordu.
  Artik rotasyon senkronu ve kapanis yakalamasi bellegi de tazeler; calisan backend sahiplenilirken
  devirden ONCE ondaki (daha taze olabilecek) oturum cekilir. Testler: `s4_bellek_rotasyonu_kurali`,
  `s4_rotasyon_bellegi_de_tazeler_ve_sahiplenme_once_ceker`.
- **[S4-yon] Geriye yazma korumasi:** posta kutusundan/devirden gelen jeton diskteki/bellekteki
  kayittan daha ESKIYSE (bayat devir ekosu) artik yazilmaz (`expires_at` karsilastirmasi; eski
  backend'de bilinmiyorsa kapi devre disi).
- ⚠️ Gecis notu: 1.9.43 -> 1.9.44 guncellemesi ESKI (1.9.43) kodla uygulanir; o tek seferde bir
  kez daha giris istenebilir. 1.9.44'ten sonraki guncellemelerde oturum korunur.

## app 1.9.39 · mobile 2.3.31 — 2026-09-03 (🧠 AI Hub 5 duzeltme + STM uyumluluk)

- **AI Hub: organ analizinden canli kameraya gecince eski sonuc kalmiyor.** Galeriden secilen
  fotografin organ isaretleri/rozeti canli goruntunun ustunde kaliyordu; canliya gecis artik
  onceki analizi temizler, gec gelen sonuclar yanlis moda dusmez.
- **Isi haritasi dogru yerde ve boyutta.** Tum AI modullerinde isi haritasi ince bir serit gibi
  cikip alttaki karta tasiyordu; artik analiz gorseliyle ayni boyut/hizada gosteriliyor.
- **AI Pro siyah ekran ve "Hazirlaniyor..." takilmasi giderildi.** Sunucu kamerasi hazirlik
  onizlemesi artik ekrana gelir; kamera acilamaz veya model yuklenemezse NEDENI ekranda gosterilir
  (120 saniye kor bekleyis yok). Onizleme sirasinda "bobin surulmuyor" acikca belirtilir.
- **Yara Kapanma isi haritasi hemen gorunur.** Isi haritasi istenmisse sonuc dogrudan XAI
  sekmesiyle acilir; istenip gelmediyse uyari verilir.
- **CKD (bobrek) analizi duzeltildi.** Secilmemis bulgular yanlislikla "anormal" sayiliyor,
  saglikli hasta %60 CKD aliyordu — artik dogru sekilde tamamlaniyor (%6). Yetersiz girdide
  ne yapilacagi soylenir: en az 6 alan ve Kreatinin/Ure/Idrar oz.ag./Albumin/Hemoglobin'den biri.
- **STM uyumluluk (bobin 1-5):** frekans tabani 1 Hz'e hizalandi (0,5 girilince cihaz sessizce
  1,0 suruyordu); firmware termal kesme bildirimi (STM_EVT) artik backend'de islenir; aktif seans
  kartinda yogunluk (mT) "kayit" olarak etiketlendi (cihaza gonderilmez); donanim surumu tek kaynak.

Paket kimliği (`buildId`): `2f8741aecf22`. Monolit `base.zip` sha: `8d3f7cdc6d34`.

## launcher 1.9.43 — 2026-09-03 (🔌 Bos/offline cihazda WebView2 kurulumu artik takilmiyor)

- **Bos cihazda kurulum "Installing WebView2..." adiminda takiliyordu.** Bos (fresh) bir Latte
  Panda / Windows cihaza client kurarken kurulum WebView2 adiminda SONSUZA KADAR asili kaliyordu.
  Kok neden: `webviewInstallMode` tanimsizdi -> Tauri v2 varsayilani `downloadBootstrapper` idi.
  Bootstrapper (~2 MB) iniyor ("downloaded successfully"), sonra Microsoft CDN'den WebView2
  Runtime'i (~150 MB) `/silent` indirmeye calisiyor; klinik cihazinda internet yok/kisitli (PEMF
  gateway ortami) -> sessiz modda TIMEOUT OLMADAN sonsuza kadar takiliyor.

- **Cozum: `offlineInstaller`.** WebView2 Runtime'in tam offline kurulumu artik client
  installer'ina gomulu; internet gerektirmez, bos cihazda da kurar. Sistem WebView2'si zaten
  varsa atlar; evergreen kalir (guvenlik yamasi alir). Yan etki: Windows installer boyutu
  ~3 MB'tan ~130 MB'a cikar (tek seferlik indirme; sonrasi ayni).

## app 1.9.38 · mobile 2.3.30 — 2026-08-30 (🖼️ AI analizinde buyuk gorsel + anlasilir hata)

- **AI analizinde "1024KB" hatasi giderildi.** Yara Kapanma (Scratch) basta olmak uzere gorsel
  yukleyen AI analizlerinde, biraz buyuk bir gorsel (~1 MB uzeri) secildiginde "Part exceeded
  maximum size of 1024KB" hatasi cikip analiz BASLAMIYORDU. Sinir gereksiz yere dusuktu; artik
  32 MB'a kadar gorsel kabul ediliyor (asiri buyuk dosyalar yine reddedilir — bellek korumasi).

- **AI hata mesajlari artik ANLASILIR.** Bir analiz basarisiz oldugunda kullaniciya bazen ham
  teknik metin (yukaridaki gibi Ingilizce cerceve mesaji) gosteriliyordu; kullanici ne yapacagini
  anlamiyordu. Artik teknik mesajlar eyleme cevriliyor ("Gorsel cok buyuk, daha kucuk cozunurlukte
  bir gorsel secin" gibi); sistemin kendi anlasilir Turkce uyarilari oldugu gibi korunuyor. Bu 10+
  AI modulunun tamaminda gecerli.

Paket kimliği (`buildId`): `4985be7e3160`. Monolit `base.zip` sha: `3f897aa17cb9`.

## app 1.9.37 · mobile 2.3.29 — 2026-08-30 (🔒 Hasta duzenleme cakismasi + seans suresi kaydi)

- **Ayni hastayi iki cihazdan duzenlerken degisiklik KAYBOLMASI onlendi.** Iki kullanici (ornegin
  masaustu + telefon) ayni hastayi ayni anda acip FARKLI alanlari degistirirse, birinin kaydettigi
  degisiklik sessizce kayboluyordu: kaydetme ekrandaki TUM formu gonderiyor, boylece bir cihazin
  eski (bayat) degeri digerinin yeni degerinin uzerine yaziliyordu. Artik yalnizca GERCEKTEN
  degistirdiginiz alanlar gonderilir; dokunmadiginiz alanlar oldugu gibi korunur. (Hem masaustu
  hem mobil.)

- **Seans suresi kaydi saat degisiminden etkilenmiyor.** Kayitli seans suresi bilgisayarin duvar
  saatine gore hesaplaniyordu; yaz/kis saati gecisi, otomatik saat duzeltmesi (NTP) ya da elle
  saat degisimi olursa RAPORLANAN sure yanlis cikabiliyordu (ornegin saat 1 saat ileri atlarsa
  30 dakikalik seans 90 dakika gorunebiliyordu). Artik sure, saatten bagimsiz bir olcumle
  hesaplanir.
  ⚠️ Onemli: uygulanan GERCEK tedavi suresi bu sorundan zaten ETKILENMIYORDU (ayri bir guvenlik
  sayaci onu koruyordu); bu duzeltme yalnizca KAYDI/raporu dogru gosterir.

Paket kimliği (`buildId`): `80bdb402db56`. Monolit `base.zip` sha: `adeef8dd66f7`.

## app 1.9.36 — 2026-08-30 (🔤 Turkce arama + dogru doz: I/i ve ondalik virgul duzeltmeleri)

- **Turkce adli hastalar artik araninca BULUNUYOR.** Hasta arama "İ"/"I" harflerini yanlis
  isliyordu (Python/JS'in bilinen Turkce hatasi): "İhsan" kaydedip "ihsan" arayan hekim hastayi
  BULAMIYORDU -> erisilemeyen kayit ya da mukerrer hasta. Arama artik Turkce-dogru; aksan ve
  i/i(noktasiz) ayrimi KORUNUR ("Sirin" ile "Sirin" karismaz -> yanlis hastaya bakma riski yok).
  Mevcut hastalarin arama dizini acilista kendiliginden yenilenir. Ayni duzeltme PDF hasta
  raporu filtresine de uygulandi. Masaustu ve mobil arama artik BIREBIR ayni davranir.

- **⚠️ DOGRU DOZ: ondalik VIRGUL artik dogru okunuyor (hasta guvenligi).** Hasta kilosu/yasi
  virgulle girilmisse (3,5 kg) sistem bunu okuyamayip SESSIZCE varsayilana (15 kg) dusuyor ve
  kucuk bir hayvana ORTA-BOY doz suresi onerebiliyordu. Artik "3,5" dogru okunuyor -> dogru
  kilo kategorisi -> dogru doz. (Cihazin uyguladigi gercek sure zaten ayri bir saatle
  guvencedeydi; bu duzeltme ONERI/kayit tarafini duzeltir.)

- **Filo envanteri + coklu klinik saglamlastirmalari** (denetim turu): gelistirme kosumlari
  bulut listesinde '-dev' ile isaretlenir; ayni klinikte iki cihaz ayni seansi cakismadan
  kaydeder. Ayrica bobin sure-kapaginin monotonik saat kullanmasi ve hasta kaydinin kismi
  guncelleme (gonderilmeyen alani koruma) davranislari otomatik kontrollerle kilitlendi
  (regresyon korumasi).

Paket kimliği (`buildId`): `b8e324b5f1fd`. Monolit `base.zip` sha: `84f4aa5eb685`.

## app 1.9.35 — 2026-08-30 (🧭 Filo envanteri okunabilir: gelistirme kosumlari isaretleniyor)

- **Cihaz listesi artik gercek klinikleri gosteriyor.** Bulut cihaz kaydinda 26 satir birikmisti
  ve bunlarin yalnizca BIRI gercek bir cihazdi; gerisi ayni gelistirme makinesinin farkli
  ortamlariydi (derleme klasorleri, gecici kopyalar, Docker). Cihaz kimligi ag donanimindan
  turedigi icin her ortam kendi kimligini uretip ayni listeye yaziyordu. Bu, listenin TEK var
  olus sebebini — "hangi klinik hangi surumde calisiyor" sorusunu, yani gerektiginde geri
  cagirma yapabilmeyi — islevsiz birakiyordu.
- **Cozum: engelleme degil isaretleme.** Uygulamayi normal yoldan (PEMF Vet Client uzerinden)
  baslatmayan kosumlar listede adlarinin sonunda `-dev` ile gorunur. Kayit HER KOSULDA
  yazilmaya devam eder; yalnizca adi degisir.
  ⚠️ "Kurulu degilse hic yazma" secenegi bilerek REDDEDILDI (sahip karari): kurulum yolu
  beklenenden farkli bir klinikte cihaz kaydini hic olusturmaz ve uzaktan erisim KIMSE FARK
  ETMEDEN olurdu. Isaretleme o riski tasimaz — yanlis tarafa dusen bir cihaz islevini tam
  surdurur, bedeli listedeki etiketten ibarettir.
- 6 yeni otomatik kontrol; en kritigi bu kararin kendisini kilitliyor (isaretleme ileride
  engellemeye cevrilirse kontrol KIRMIZI yanar). Uc mutasyonun ucu de dogrulandi.
- Not: eski kalinti kayitlar ayrica temizlendi (25 → 1).

Paket kimliği (`buildId`): `8d4f8e8f18f8`. Monolit `base.zip` sha: `990a69a90a0f`.
Bagimlilik katmani DEGISMEDI (`06622c47209b`) → sahaya yalnizca ~81 MB iner.

## app 1.9.34 — 2026-08-29 (📶 Ayni WiFi'de otomatik baglanma + uzaktan erisim kilidi)

- **"Ayni WiFi'de oldugu halde telefon otomatik baglanmiyor" duzeltildi** (saha bildirimi).
  Cihaz acilirken kendi PEMF-Gateway hotspot'unu baslatiyor; Windows o ag arayuzunu yaklasik
  yarim dakika sonra olusturuyor. Sistem bunu gorunce ag duyurusunu (mDNS) KAPATIP yeniden
  kuruyordu ve duyuru birkac saniye ortadan kalkiyordu. Telefonun arama penceresi de tam o
  kadar — yani cihaz tam kullanicinin denedigi anda gorunmez oluyordu. Hotspot bosta kalinca
  Windows onu uyutup uyandirdigi icin ayni kesinti gun icinde tekrar tekrar yasaniyordu
  (bir gunde 21 kez olculdu).
  ⚠️ Telefonun hotspot'a bagli olmasi GEREKMIYORDU: hotspot yalnizca VAR OLMAKLA ev
  WiFi'sindeki keşfi kesiyordu.
  Iki yerden duzeltildi: (a) bir ag arayuzu KAYBOLDUGUNDA duyuru artik yeniden kurulmuyor —
  kalan aglar zaten calisiyor; (b) acilistan sonraki ilk dakikada arayuzler siklikla
  kontrol ediliyor, boylece hotspot belirir belirmez is bitiyor ve kullanici telefonu
  denemeden once sistem kararli hale geliyor.

- **Yeniden kurulum sonrasi UZAKTAN ERISIM kalici olarak bozulabiliyordu.** Cihazin bulut
  kimlik anahtari iki ayri yerde tutulabiliyordu; kaldirma birini siliyor, digeri kaliyordu.
  Ikisi ayrisinca cihaz buluta kaldirma ONCESI ve SONRASI farkli anahtar gonderiyor, bulut
  ilk anahtara muhurlendigi icin sonrakini KALICI olarak reddediyordu — uzaktan erisim bir
  daha acilmiyordu (bu makinede 269 kez olculdu). Artik kaldirmada KORUNAN kaynak tek
  yetkilidir; ayrisma tespit edilirse gunluge yazilir.
  Not: 1.9.33 anahtari kalici hale getirmisti; bu surum "hangi kopya gecerli" sorusunu da
  kapatiyor. Zaten bozulmus bir cihazin bulut kaydinin bir kez sifirlanmasi gerekir.

- 10 yeni otomatik kontrol (4'u davranissal); bes mutasyonun besi de KIRMIZI dogrulandi.

Paket kimliği (`buildId`): `d7021de55a8c`. Monolit `base.zip` sha: `dc072a4c92d9`.
Bagimlilik katmani DEGISMEDI (`06622c47209b`) → sahaya yalnizca ~81 MB iner.

## launcher 1.9.42 — 2026-08-29 (🌐 Anlasilir ag hatasi + temiz kaldirma)

- **Ag hatalari artik ne yapmaniz gerektigini soyluyor.** Kurulum sirasinda internet ya da DNS
  duserse ekranda ham teknik metin cikiyordu ("indirme aktarimi basarisiz: ... Dns Failed:
  resolve dns name ... os error 11001"). Bu cumle iki bakimdan kotuydu: kullaniciya hicbir
  eylem onermiyordu ve sorunu SUNUCUDA sandiriyordu — oysa o hata neredeyse her zaman yerel
  bir ag kesintisidir. Artik "Wi-Fi baglantinizi kontrol edip tekrar deneyin" gibi net bir
  cumle gosteriliyor; teknik ayrinti destek icin ikinci satirda KORUNUYOR.
- **DNS hatasi gecici sayilip yeniden deneniyor** — anlik bir cozumleme hatasi artik kurulumu
  tamamen dusurmuyor.
- **Kaldirma daha temiz:** program kaldirildiginda kendi guvenlik duvari kurallari ve yerel
  uygulama verisi de siliniyor (kullanicinin kendi onayladigi Windows kurallarina dokunulmaz).
- 21 yeni otomatik kontrol eklendi; her biri, yakalamasi gereken hatayi bilerek geri koyarak
  KIRMIZI yandigi dogrulandi.

## mobile 2.3.28 — 2026-08-29 (🔴 "Guncelle"ye basinca uygulama kapaniyordu)

- **Guncelleme baslatirken uygulamanin kapanmasi duzeltildi** (saha bildirimi, Galaxy S23 /
  Android 16). Kullanici "Guncelle"ye basiyor, uygulama aninda kapaniyordu — indirme hic
  baslamadan. Bu, guncellemeyi TAMAMEN engelliyordu: her deneme ayni yerde kapanmayla
  bitiyordu.
- **Sebep bir SIRA hatasiydi, izin sorunu degil.** Indirme boyunca sureci canli tutan on-plan
  servisi baslatiliyor, ancak indirme cok hizli bittiginde (ornegin paket daha once tam
  inmisse) servis kendini on plana almaya firsat bulamadan durduruluyordu. Android bunu
  olumcul sayip uygulamayi kapatiyor. Olculen aralik 23 milisaniye.
- **Uc yerde birden saglamlastirildi**, biri kacsa da digerleri tutsun diye: servis artik
  kendini her kosulda once on plana aliyor; durdurma istegi servise dogrudan iletiliyor; ve
  durdurma, baslatmanin tamamlanmasi beklenmeden gonderilmiyor.
- Not: paketi daha once tam indirmis cihazlar bu hataya HER denemede giriyordu — bu yuzden
  ariza "bir kere oldu" degil, kalici gorunuyordu.

## app 1.9.33 — 2026-08-28 (📡 Uzaktan erisim ariza SEBEBI ortadan kalkti)

- **Yeniden kurulum artik uzaktan erisimi BOZMUYOR.** 1.9.32 arizayi GORUNUR yapmisti; bu surum
  SEBEBINI ortadan kaldiriyor. Kok neden bir kalicilik asimetrisiydi: cihazin bulut kimligi
  yeniden kurulumda AYNI geliyordu (ag donanimindan turetiliyor), ona esilik eden guvenlik
  anahtari ise yalnizca silinen veri klasorunde durdugu icin DEGISIYORDU. Bulut, kimlik ayni
  anahtar farkli olunca yazmayi kalici olarak reddediyordu — cihaz acik ve internete bagliyken
  bile uzaktan erisim guncellenmiyordu. Anahtar artik veri klasorunun DISINDA, makineye bagli
  bir yerde saklaniyor; klasor yenilense de ayni kaliyor.
- **Mevcut cihazlar da korunuyor:** ilk acilista anahtar sessizce yeni yerine tasiniyor. Yalniz
  yeni kurulumlari korusaydi sahadaki cihazlar ilk kaldir-kur dongusunde yine bozulacakti.
- **KVKK dengesi korundu:** siradan kaldir-kur anahtari BIRAKIR (ariza olmasin diye), ama
  "hasta verisini de sil" secildiginde bulut yazma yetkisi de MAKINEDEN SILINIR. Kaldirma
  betigine bunun icin ayri bir kalem eklendi.
- Bu makinedeki 31 gunluk ariza giderildi: bulut kaydi silinip cihaz kendini yeniden muhurledi
  (dogrulandi — kayit 31 gun sonra ilk kez guncellendi, yerel IP ve surum bilgisi dogru yazildi).
- Kalici koruma: iki yeni test dosyasi + test izolasyonuna bir kalem. ⚠️ Yol boyunca test
  suitinin GERCEK cihaz anahtarina yazdigi bulundu ve kapatildi; kapatilmasaydi bir sonraki
  kaldir-kur'da ariza test suiti yuzunden geri gelecekti.
Paket kimliği (`buildId`): `1e09964006ad`. Monolit `base.zip` sha: `4ecbc61df2e2`.
Deps katmanı DEĞİŞMEDİ (`06622c47209b`) — klinikler yalnız ~77 MB uygulama katmanını indirir.

## app 1.9.32 — 2026-08-28 (🔒 Kod korumasi gercekten etkin + uzaktan erisim teshisi + CKD aciklamasi)

> Bu surum, 28 Agustos "sessiz olum" taramasinda bulunan **10 arizanin tamamini** kapatir.
> 1.9.31'de dordu kapanmisti; kalan alti burada. Hicbiri sahaya YAYINLANMADAN once bu surumde
> birlestirildi (1.9.31 paketleri hazirlandi ama manifest yayinlanmadi).

- **🔒 KOD KORUMASI ARTIK GERCEKTEN ETKIN.** AI modul kaynaklari Cython ile `.pyd`'ye
  derleniyordu ama **hicbiri yuklenmiyordu**: paketleyici ayni modullerin okunabilir
  bytecode'unu da EXE'nin ic arsivine gomuyor ve calisma aninda o kopya onceligi aliyordu.
  Olculdu: 65 derlenmis modulden **yalniz 1'i** kullaniliyordu; sevk edilen EXE'den okunabilir
  kaynak cikarilabiliyordu. Dort koruma kapisi da yesil yaniyordu, cunku dordu de yalniz
  "diskte duz kaynak kaldi mi" diye soruyordu. Arsiv artik temizleniyor; iki YENI kapi eklendi
  (arsivde AI kodu var mi + moduller gercekte nereden yukleniyor) ve build bunlar kirmiziysa
  DURUYOR.
- **⚠️ Ayni duzeltme bir sessiz olumu onledi:** paketleme filtresi, adinda "torch" gectigi icin
  `ig_torch` modulunu pakete hic almiyordu; bugune kadar yalnizca arsiv kopyasi sayesinde
  calisiyordu. Arsiv temizligi tek basina yapilsaydi **bobrek RNA gen-katki aciklamasi sahada
  sessizce olecekti**. Filtre yola gore duzeltildi + kaynak/paket butunlugu kapisi eklendi.
- **📡 Uzaktan erisim arizasi artik EKRANDA GORUNUYOR.** Cihazin bulut kaydi bozulmussa
  (genellikle yeniden kurulum sonrasi) Ayarlar ekraninda net bir uyari cikiyor ve eslestirme
  kodunun yaninda "(uzaktan gecersiz)" etiketi beliriyor — eskiden kod kosulsuz gecerli gibi
  sunuluyordu. Uzaktan baglanmaya calisan operatore de artik dogru sey soyleniyor: eski mesaj
  *"uzaktan erisimi acin; kod dogru"* diyordu (ikisi de yanlis yone kilitliyordu); yenisi
  bulut kaydinin **kac gundur guncellenmedigini** soyluyor. Ayrica bir tur basarisiz olunca
  durum artik "saglikli" kalmiyor (bayat teshis, teshissizlikten kotudur).
- **🧪 Bobrek hastaligi (CKD) aciklamasi duzeltildi — klinik dogruluk.** Uc kusur ust uste
  binmisti: (1) aciklama **yakinsamamisti** — ayni hastada, ayni girdiyle en etkili bes ozellik
  her calistirmada degisiyordu; (2) kullanilan seyreklestirme 24 ozellikten 14'unu sifira
  zorluyordu ve **bunlarin arasinda KREATININ vardi** (bobrek aciklamasinda katkisi "0,0"
  yaziyordu); (3) karsilastirma referansi modelce zaten hasta sayiliyordu, aciklanacak sinyal
  gurultuye gomuluyordu. Olculen yeni durum: ilk-5 dort farkli kosuda **birebir ayni**,
  kreatinin katkisi 0,0 → 0,026, aciklanabilir sinyal ~100 kat guclu. Gecikme 0,18 sn.
- **🛠 Launcher "Onar" dugmesi calisiyor.** Model paketi bozulan klinikte "Onar" **indirme
  baslamadan** "'ai_hub' profili manifest'te yok" hatasiyla dusuyordu: kurulum dizinindeki
  klasor adi profil sanilıyordu. 4 Agustos'ta yazilan duzeltme fiilen calismiyordu ve kapisi da
  gercekte hic olusmayan bir dizin duzeni kurdugu icin yesil kaliyordu.
- **📶 Ayni agda iki cihaz artik birbirini engellemiyor.** mDNS servis adi sabit oldugu icin
  ikinci cihazin kaydi reddediliyor ve o oturum boyunca **hic toparlanamiyordu**; ustelik hata
  gunluge bos satir olarak yaziliyordu (destek hangi hatayi aldigini goremiyordu). Ad artik
  cihaza ozel ve kararli; kayit reddedilse bile arayuz degisiminde yeniden deneniyor.
- **🐳 GPU/Docker profilindeki uc olu uc onarildi** (bu profil henuz sevk edilmiyor): termal ve
  retikulosit sonuclari arayuzun bekledigi bicimde donmuyordu (panel sessizce bos kaliyordu) ve
  uc AI modulu, yaninda duran yardimci model dosyalarini bulamadigi icin hata veriyordu.
- Kalici korumalar: alti yeni test dosyasi + iki yeni build kapisi. Her kapi, yakalamasi gereken
  hatayi **bilerek geri koyularak** kirmizi oldugu dogrulandi (20 mutasyon). Bu turda kendi
  kapilarimizin **besi ilk halinde bos calisti** ve ancak bu yontemle yakalandi.
Paket kimliği (`buildId`): `d8f4fc7ca6dc`. Monolit `base.zip` sha: `5efa035ef3d6`.

- ⚠️ **Bu yayinda BAGIMLILIK KATMANI da degisti** (`3b39061b2286` -> `06622c47209b`): eksik
  surum bilgileri (`.dist-info`) pakete eklendigi icin klinikler bu sefer yalniz ~77 MB
  uygulama katmanini degil, ~1,4 GB bagimlilik katmanini da indirecek. Son dort yayinda
  degismemisti; duzeltmenin kacinilmaz bedeli, bir defalik.

## app 1.9.31 — 2026-08-28 (🎯 Hedefe ozel doz + yedek sayaci + kor kalan kapilar)

> ⚠️ Bu surum SAHAYA CIKMADI: paketleri hazirlandi ama manifest yayinlanmadan once kalan alti
> ariza da duzeltildi ve hepsi 1.9.32'de birlestirildi. Asagidaki degisiklikler 1.9.32'de canli.

- **Otomatik modda UC HEDEF YANLIS DOZ aliyordu — duzeltildi (klinik dogruluk).** Arayuzdeki
  8 seans hedefinden ucu literatur protokolune baglanamiyordu: *Enflamasyon Azaltma* ve
  *Sinir Rejenerasyonu* sessizce **genel (wellness) dozuna** dusuyordu; *Bag Dokusu Tamiri*
  ise yumusak-doku dozunu (105 Hz / %50 / 30 dk) aliyordu — bag/tendon dozu (75 Hz / %40 /
  37 dk) yerine. Ucunde de ekranda hicbir fark yoktu, veteriner hedefe ozel doz aldigini
  saniyordu ve seans kaydina o hedef yaziliyordu. Olculen yeni durum: 8 hedefin 8'i dogru
  protokolu aliyor.
- **Doz kaynagi artik ekranda gorunuyor.** Secilen hedefin literatur karsiligi yoksa
  "genel (wellness) dozu uygulaniyor" uyarisi cikar; varsa "Literatur protokolu uygulandi"
  yazar. Doz yine doner — seans engellenmez, yalnizca sessizlik kaldirildi.
- **Yedekleme ozeti "0 hasta" demeyi birakti.** 300 hastalik yedek alan klinik
  "Yedek olusturuldu: **0 hasta**" goruyordu; veriler dogru tasiniyordu, **sayi yalan
  soyluyordu** — arayuzun okudugu sayac backend yanitinda hic yoktu. Geri yuklemede de
  yanlis sayac okunuyordu. Ayrica geri yuklemenin uc sonucu (**eklendi / zaten vardi /
  AKTARILAMADI**) artik ekrana ulasiyor; aktarilamayan kayit varsa bildirim hata rengine doner.
- **AI hazirlik teshis ucu artik gercekten olcuyor.** Sahada "model calismiyor" arizasinda
  destegin baktigi uc, 13 modulun 12'sinde **hicbir dosyaya bakmadan** "hazir" diyordu ve
  aciklanabilir-AI zincirini hic gormuyordu; iki AI ucu ise listede yoktu. Uc artik 15 modulu
  gercek agirlik dosyasi uzerinden dogruluyor, XAI kutuphanelerini ve EM referans
  istatistiklerini ayrica raporluyor. Build kapisi bunlarin hepsini kontrol ediyor — bir
  eksiklik varsa o EXE yayina cikmiyor.
- **Urun artik calisirken kendine paket kurmaya kalkmiyor.** Her AI modeli yuklenirken
  `pip install` alt-sureci deneniyordu (basarisiz, model basina ~2,9 saniye ve destegi
  yaniltan kirmizi kayit). Iki bagimsiz onlem: paketleme tarafinda eksik surum bilgileri
  eklendi, calisma tarafinda otomatik kurulum tumden kapatildi.
- **Paketleme kapisindaki sessiz atlama giderildi.** Surum bilgisi toplama adimi, agactaki
  tek bir eksik bagimlilik yuzunden UC PAKETI birden sessizce atliyordu (27 Agustos
  arizasinin kendi paketi dahil) ve build yine yesil kaliyordu. Artik once genis, sonra dar
  toplama denenir; kurulu bir paketin bilgisi yine alinamazsa **build durur**.
- Kalici korumalar: dort yeni test dosyasi (hedef-doz sozlesmesi, yedek sayaclari, pip yasagi,
  hazirlik envanteri). Her kapi, yakalamasi gereken hatayi **bilerek geri koyularak** kirmizi
  oldugu dogrulandi — bu turda iki kapinin ilk halinin bos calistigi boylece bulundu ve duzeltildi.
Paket kimliği (`buildId`): `38fa24480204`. Monolit `base.zip` sha: `86c96c5aa207`.

- ⚠️ **Bu yayinda BAGIMLILIK KATMANI da degisti** (`3b39061b2286` -> `8c7beec846bb`): eksik surum
  bilgileri (`.dist-info`) pakete eklendigi icin klinikler bu sefer yalniz ~78 MB uygulama
  katmanini degil, ~1,4 GB bagimlilik katmanini da indirecek. Son dort yayinda degismemisti;
  duzeltmenin kacinilmaz bedeli, bir defalik.

## app 1.9.30 — 2026-08-27 (🔍 Hastalik analizinde aciklama artik gercekten uretiliyor)

- **Kedi Hastalik modulunde "Aciklama uretilemedi" arizasi giderildi.** Analiz calisiyordu
  ama "karari surukleyen ozellikler" dokumu URETIMDE SESSIZCE olusmuyordu: kullanilan SHAP
  kutuphanesi, model kutuphanesinin yeni surumuyle uyumsuzdu. Artik model kutuphanesinin
  KENDI yerlesik hesaplayicisi kullaniliyor — ayni matematik, daha hizli, surum-bagimsiz.
  Ornek cikti (gercek modelle dogrulandi): Gastroenteritis icin "sikayet suresi +3,29",
  "ishal -1,60", "kilo -0,87" — isaretli ve tekrarlanabilir.
- **Tum aciklanabilir-AI yuzeyleri gercek girdilerle bastan sona dogrulandi (13 yuzey):**
  termal / retikulosit / bobrek CT / kedi sesi / yara kapanma isi haritalari, histopatolojide
  konsensus + model-kararsizligi haritalari, RNA gen katkilari (isaretli), EM duyarlilik
  metasi, CKD ozellik katkilari, yuz-agrisi populasyon bantlari, organ guven dokumu.
  12'si sorunsuz; yalniz yukaridaki ariza bulundu ve duzeltildi.
Paket kimliği (`buildId`): `5b5b89b74f97`. Monolit `base.zip` sha: `8894aa98945b`.
Deps katmanı DEĞİŞMEDİ (`3b39061b2286`) — klinikler yalnız ~81 MB uygulama katmanını indirir.

- Test tarafinda kalici koruma: hastalik aciklamasi artik GERCEK model agirligiyla sinaniyor
  (onceki kilitler CI kolayligi icin vekil bir model kullaniyordu ve bu yuzden gercek surum
  uyumsuzlugunu goremiyordu).

## mobile 2.3.27 — 2026-08-27 (🔇 AI Pro: kare yakalama sessiz)

- **AI Pro seansinda her karede calan DEKLANSOR SESI kaldirildi** (saha bildirimi). Otonom
  seans ~3 saniyede bir olcum karesi alir; sistem her karede fotograf-cekim sesi caliyordu —
  klinikte hem operatoru rahatsiz ediyor hem hayvani urkutuyordu. Yakalanan sey bir fotograf
  degil OLCUM karesidir; artik sessiz alinir. Ayni duzeltme canli kamera modlarinda da
  gecerli (yuz agrisi canli takibi ve kedi organ canli takibi).
- Not: Windows istemcisinde bu ses zaten yoktu (orada kareler klinik sunucu kamerasindan
  alinir, telefon kamerasi kullanilmaz) — dogrulandi.

## app 1.9.29 — 2026-08-27 (⚡ Yara Kapanma: ilk analiz artik beklemiyor)

- **Yara Kapanma modelinin ilk analizi belirgin hizlandi.** Model (872 MB) artik uygulama
  acilirken ARKA PLANDA hazirlaniyor; onceden ilk "Analiz Et" anina birakiliyordu.
  Olculen fark (ayni makine, bosta): ilk analiz **32,8 sn → ~22 sn**; aradaki sure saf
  model yuklemesiydi ve o pencerede ikinci bir analiz istegi "baska analiz suruyor"
  uyarisi aliyordu. Sahadan bildirilen "ilk basista bos dondu, ikincide cikti" davranisinin
  sebebi buydu.
Paket kimliği (`buildId`): `2e49b39e3d9a`. Monolit `base.zip` sha: `b806d908bea4`.
Deps katmanı DEĞİŞMEDİ (`3b39061b2286`) — klinikler yalnız ~81 MB uygulama katmanını indirir.

- Hazirlama seansi/E-stop yolunu ETKILEMEZ (ayri is parcaciginda calisir) ve arastirma
  profili kurulu olmayan makinelerde  ile kapatilabilir.

## app 1.9.28 — 2026-08-27 (🩹 Yara Kapanma modulu sahada CALISMIYORDU — duzeltildi)

- **SAHA ARIZASI:** Guncel kurulumda "Yara kapanma modeli bu kurulumda hazir degil —
  GPU AI servisi ya da model paketi gerekli." cikiyordu. **Model paketi kuruluydu**
  (872 MB agirlik diskte, launcher paket kaydi dogru); gosterilen sebep YANLISTI.
  Gercek neden: uygulama paketinde (frozen EXE) bir kutuphanenin **paket kimlik
  bilgisi (metadata)** eksikti; hucre-segmentasyon zinciri acilirken
  `No package metadata was found for imageio` ile olu doguyordu. Duzeltildi —
  modul artik referans degerleri birebir uretiyor (12a: 1495 hucre, kapanma %4.29,
  ort. gap 1053,5 um; sahip referansi 1494 / %4.3 / 1053 um).
- **AYNI SINIF HATA BIR DAHA SESSIZ KALMASIN diye ucu kapatan iki kapi:**
  - **`GET /api/ai/hazirlik`** (destek/tanilama ucu): her AI modulu icin **kod** ve
    **model** durumu AYRI raporlanir; `?derin=1` gercek yuklemeyi dener. "Kod bozuk"
    ile "model inmemis" bir daha karismaz. (Yol/sistem detayi donmez.)
  - **Yayin oncesi otomatik kapi:** uretilen uygulama paketi derlendikten sonra tum
    AI modulleri gercekten yuklenerek sinanir; biri olu ise **yayin uretimi durur**.
    Bu arizanin sahaya inebilmesinin sebebi tam olarak boyle bir kapinin olmamasiydi
    (tum testler paketlenmemis ortamda kosuyor, orada bagimlilik hep var).
  - Kurulum-eksigi hatasi artik **kok nedeniyle loglanir** (kullaniciya gosterilen
    metin sade kalir) — destek sahadaki nedeni ilk bakista gorebilir.
Paket kimliği (`buildId`): `8a3ed351dc97`. Monolit `base.zip` sha: `e4acbdb0e3f1`.
Deps katmanı: `3b39061b2286` (paket metadata dosyaları bu katmana girdi).

- Kullanici etkisi: guncelleme sonrasi Arastirma profilinde **Yara Kapanma (Scratch)**
  modulu calisir. Diger 12 AI modulu bu arizadan etkilenmemisti (dogrulandi: 13/13).

## mobile 2.3.26 — 2026-08-27 (indirme kesinti-dayanikliligi + kalan sure)

- **Guncelleme indirmesi artik ekran kilidi / arka plana alma ile SUREKLI KESILMIYOR**
  (saha bildirimi): (1) indirme boyunca ekran uyanik tutulur (otomatik kilit devreye
  girmez); (2) indirme, dataSync ON-PLAN SERVISI ile korunur — bildirim cubugunda
  "guncelleme indiriliyor" gorunur, Android arka planda agi kesmez; (3) yine de kesilirse
  KENDILIGINDEN kaldigi bayttan surer (40 denemeye kadar; arka plandaysa on-plana donus
  beklenir, on-plandayken 90 sn ilerlemeyen indirme dusurulup diskteki kismi dosyadan
  yeniden acilir). Duraklatma YOK — yalniz istemsiz kesintinin onarimi.
- **Indirme kartinda anlik hiza gore KALAN SURE** ("~3 dk 20 sn kaldi") — masaustu
  istemcideki gostergenin mobil esi; hem acilis kapisinda hem uygulama ici bantta.
- Not: bu iki iyilestirme 2.3.26'yi INDIRIRKEN henuz aktif degildir (eski surum indirir);
  ilk faydasi bir SONRAKI guncellemede gorulur.

## app 1.9.27 · launcher 1.9.39 · mobile 2.3.25 — 2026-08-27 (🧫 Yara Kapanma/Scratch + coklu-model-zip)

- **YENI MODUL — Yara Kapanma (Scratch), Arastirma profili:** CPN hucre segmentasyonu +
  TScratch kapanma metrikleri (PEMF calismasinin primary endpoint'i). TEK goruntuden coklu
  gorsel cikti: Kapanma/Analiz/Segmentasyon/Overlay/Orijinal (+istege bagli EigenCAM XAI ve
  3'lu panel) — butonlu galeri; yara-yonu (dikey/yatay) ve objektif (4x-40x) secimi;
  Karsilastir modu (0H↔24H delta-kapanma karti). GERCEK-MODEL dogrulamasi sahip
  referanslariyla neredeyse birebir (24H: 2083 hucre %29.36, gap 428.0um BIREBIR); GPU
  smoke cuda:0 9.8sn. Uc: /api/ai/vision/scratch (3 jeton sinifi; FREE_MODE'da etkisiz).
- **Klinik EXE'ye celldetection eklendi** (sahip karari 0.1): scratch CPU'da da calisir
  (~18 sn/goruntu; 872MB model ilk kullanimda yuklenir). deps katmani bu yuzden DEGISTI
  (6. degisim, bilincli).
- **mobile 2.3.25:** ayni Yara Kapanma modulu mobil arayuzde (dosya secici + galeri +
  Karsilastir); arastirma profili modul sayisi 7.
- **XAI §KALAN kapanisi (A+B+C, cat_llm haric):** (A) Bobrek CT + Histopatoloji'de
  "Isi haritasi uret" anahtari (histopat CIFT harita: konsensus + model-kararsizligi),
  RNA hasta satirinda "Surukleyen genler" (yon oklu), retikulosit isi-haritasi; Kedi Organ
  ayna/anatomik-tutarlilik rozetleri; Petri kanser kuyusunda "gerekce: N mavi piksel
  (esik >=30)" satiri; Yuz Agrisi'nda "Olcumler · populasyon bandi (p5-p95)" paneli
  (bant-disi isaretli); termal/ses uclarinda CAM yontemi secilebilir (allowlist, gecersiz
  422); EM fantom/petri yanitlarinda canli xaiSensitivity meta (router + :8100 paritesi).
  (B) `scripts/xai_batch_rapor.py` — tek CLI ile toplu XAI: goruntu/ses CAM, RNA IG
  isaretli-CSV, EM sensitivity+SHAP paketi; summary.csv + index.html + istege bagli PDF
  (yeni `generate_xai_report`). (C) test-girdileri: 03 termal + 04 retikulosit + 11b
  gercek-format RNA + 12 scratch TIF'leri + 90_Batch_XAI ornekleri; calibrate_camera.py
  araci; segmentation help-metni duzeltmesi.
- Launcher 1.9.39 ayrintilari icin asagidaki kendi girdisine bakin (coklu-model-zip —
  renal + scratch PT'leri research-2.zip parcasiyla sahaya iner).
- Dusman-dogrulama turu (yayin oncesi, 25 ham -> 17 dogrulanmis bulgu, TAMAMI kapatildi):
  en kritigi `.npz` spec eksigi — EM canli XAI referanslari frozen EXE'ye hic girmiyordu
  (1.9.25'ten beri uretimde sessiz oluydu); ayrica GPU-mikroservis paritesi (landmark/
  cat_organ/termal/ses), FGS band-paneli anahtar eslemesi, batch ses sessizlik-kapisi,
  XAI baz-noktasi cfg ikamesi. Ayrinti: docs/xai-entegrasyon-plani.md KAPANIS notu.
- Rollout: %100. Etiket: client-app-v1.9.27.

Paket kimliği (`buildId`): `1bb79548612e`. Monolit `base.zip` sha: `4c3d5b6b621f`.
Deps katmanı: `ce9f9dfcca50` (celldetection nedeniyle 6. değişim — bilinçli).

## launcher 1.9.41 — 2026-08-29 (🚑 1.9.40 ACILIS ARIZASI GIDERILDI)

- **1.9.40 kurulan cihazlar "Ortam algılanıyor…" ekraninda kaliyordu — duzeltildi.** Uygulama
  aciliyor ama hicbir dugme cikmiyordu; baslikta surum yerine `v—` yaziyordu. Sebep, 1.9.40 ile
  eklenen bir uyari metnindeki bicimlendirme hatasiydi: metin ic ic e gecen satirlar yuzunden
  arayuz kodunun TAMAMI calisamaz hale geliyordu. Metin duzeltildi.
- ⚠️ **1.9.40 kurulu cihazlar KENDILIGINDEN duzelemez**: arayuz calismadigi icin guncelleme
  kontrolu de yapilamiyor. O cihazlarda kurulum dosyasi ELLE indirilip calistirilmalidir
  (site > Windows icin indir). Kurulu veriler, hasta kayitlari ve profiller ETKILENMEZ.
- **Kalici koruma:** arayuz kodunun ayristirilabilir oldugunu dogrulayan bir kapi eklendi
  (`tests/test_launcher_ui_sozdizimi.py`). Bu ariza sinifi daha once HIC olculmuyordu: mevcut
  kapilarin hepsi arayuzun tek tek PARCALARINA bakiyordu, butununun calisip calismadigina
  bakan yoktu. Kapi, arizanin birebir hali geri konularak kirmizi oldugu dogrulandi.
- 1.9.40'in getirdigi Duraklat/Iptal ozelligi aynen gecerli (asagidaki nota bakin).

## launcher 1.9.40 — 2026-08-28 (⏸ Arka plan indirmesi artik DURDURULABILIYOR)

- **"Duraklat" ve "Iptal" dugmeleri eklendi.** Yeni surum arka planda inerken (ornekte 1,39 GB
  `deps` paketi) ekranda yalnizca ilerleme cubugu vardi; indirmeyi durdurmanin HICBIR yolu
  yoktu. Klinik hattini mesgul eden bir indirmeyi ancak uygulamayi kapatarak kesebiliyordunuz.
- **Duraklat**: indirme durur, **inen kisim KORUNUR**. "Devam et"e bastiginizda kaldigi yerden
  surer — bastan inmez. Karar oturum boyunca gecerlidir: 6 saatte bir kosan otomatik kontrol,
  duraklattiginiz indirmeyi kendiliginden yeniden BASLATMAZ (yoksa "Duraklat" birkac saat sonra
  sessizce geri alinirdi). Bir sonraki acilista normal sekilde yeniden denenir.
- **Iptal**: inen kisim SILINIR ve guncelleme bir sonraki acilista bastan indirilir. Bu kayip
  onemli oldugu icin once ONAY sorulur ve onay metni daha ucuz secenegi ("Duraklat") acikca
  onerir.
- **Kendi bastiginiz dugme artik "hata" gibi gosterilmiyor.** Eskiden tum sonuclar tek bir
  "indirme tamamlanamadi" mesajina dusuyordu; duraklatan kullanici bunu ariza saniyordu. Artik
  "duraklatildi — inen kisim korundu" ve "iptal edildi — sonraki acilista yeniden denenecek"
  ayri ayri yazilir.
- ⚠️ Teknik not (ileride geri alinmasin): durdurma yetenegi (`net::Control::Pause/Cancel`) ve
  `pause_install`/`cancel_install` komutlari ZATEN vardi ve kurulum ekraninda calisiyordu; arka
  plan indirmesi tek bir satirda sabit "devam et" ile cagrildigi icin kullaniciya ulasmiyordu.
  Ayrica `resume_install` komutu HIC YOKTU. Kapilar: `launcher/core/tests/
  arka_plan_indirme_denetimi.rs` (cekirdek) + `tests/test_launcher_indirme_denetimi.py` (kablo).

## launcher 1.9.39 — 2026-08-27 (coklu-model-zip: buyuk PT'ler sahaya inebiliyor)

- **Ne degisti:** Launcher artik bir profilin modellerini BIRDEN COK zip'ten kurabiliyor
  (manifest `model_parts` alani). Ilk kullanim: `research-2.zip` — GitHub'in 2 GiB tek-dosya
  siniri (OLCULDU: HTTP 422) yuzunden ana research.zip'e sigmayan iki buyuk agirlik
  (renal histopatoloji PT ~858 MB + yara-kapanma/scratch CPN PT ~872 MB) artik ayri
  parcayla klinik makinelere inebilecek.
- **Geriye uyum:** eski launcher'lar yeni alani YOK SAYAR (canli manifestte kanitli desen);
  davranislari bit degismeden surer. Parcasiz profillerde 1.9.39 da birebir eski davranistir.
- **Ayrintilar:** parca indirme ayni dogrulama/kaldigi-yerden-devam borusundan gecer;
  onbellek etiketleri benzersiz (`research-p2`); kurulum kaydi birlesik kimlikle tutulur
  (tek parcada eski kayitlarla birebir — sahte 'guncelleme var' uretmez). Uretim tarafinda
  `make_model_zip.py` 2 GiB'i asan paketi YAYINA CIKMADAN durdurur.
- **Geri donus maliyeti (bilincli):** parcali kurulumdan 1.9.38'e donulurse eski launcher
  research'u bir kez bayat sayip ana zip'i (~1,6 GB) yeniden indirir ve stabilize olur (veri
  kaybi yok; PT'ler diskte kalir). Eski surumun onbellek-koruma listesi research-2.zip'i
  tanimadigindan olu-onbellek temizligi parca kopyasini silebilir — 1.9.39'a geri gelis parca
  indirmesini tekrarlar.
- Testler: cargo 223 (7 yeni manifest/etiket/adopt kilidi) + manifest URL-koruma suiti parca
  vakalariyla 9; BUILD.md runbook'u AYNI commit'te guncellendi (parcalar da once-asset kurali).

## Kural

**Bir sürüm, buraya yazılmadan yayınlanmaz.** Kayıt en az şunları içerir:

- kanal (`app` paketi / `launcher` / `mobile`) ve sürüm,
- yayın etiketi ve **paket sha256'sının ilk 12 hanesi** — aynı sürüm numarası farklı ikili
  içerebilir; `buildId` (`/api/health`, `X-Build-Id`) tam bu değeri raporlar
  *(katmanlı kurulumda "paket" = **app katmanı** — cihaz `layers.app` sha'sını raporlar;
  `base.zip` sha'sı yalnız eski ≤1.9.12 tek-parça istemcilerde görülür)*,
- hasta güvenliğini veya veriyi etkileyen değişiklikler **ayrı ve önce**.

`tests/test_changelog_gate.py` bunu kilitler: `versions.json`daki güncel sürümler burada
geçmiyorsa test kırılır.

## Kanallar

| Kanal | Sürüm kaynağı | Nasıl dağıtılır |
|---|---|---|
| **app** (backend + frontend paketi) | `VERSION` | `manifest.json` → `layers` (base-app/base-deps); launcher kurar |
| **launcher** (PEMF Vet Client) | `versions.json → launcher` | kendi kendini günceller (`manifest.json → launcher`) |
| **mobile** (Android APK) | `versions.json → mobile` | `manifest.json → mobile.android`; uygulama içi bildirim |
| ~~frontendOta~~ | `frontend_version.json` | **KULLANIM DIŞI** — eski ayrı OTA kanalı |
| ~~exe / Inno~~ | `pemf-update@exe/latest.json` | **KAPALI** — bkz. 2026-08-09 girdisi |

---

## app 1.9.26 — 2026-08-26 (🔬 Histopatoloji XAI: ensemble ısı haritası + model-kararsızlık haritası)

Yayın etiketi: app → `client-app-v1.9.26`. Launcher (1.9.38) ve mobil (2.3.24) DEĞİŞMEDİ;
**deps katmanı da DEĞİŞMEDİ** (1.9.25'teki sha aynen — yeni bağımlılık yok).
Paket kimliği (`buildId`): `d4ad28a47dc9`. Monolit `base.zip` sha: `4757e30f35f8`.
`research.zip` İÇERİK OLARAK DEĞİŞMEDİ (sha aynı; yalnız v1.9.26 etiketine de kondu).
⚠️ Renal PT ikizi (~858MB) pakete GİREMEDİ — ÖLÇÜLDÜ: GitHub release asset sınırı 2 GiB,
PT'li research.zip (2,51GB) HTTP 422 ile reddedildi. Renal ısı haritası GPU mikroservis
kurulumunda (/models mount) ÇALIŞIR; klinik tek-EXE'de PT bulunamazsa zarif "Açıklama
üretilemedi" düşer. Saha inişi launcher çoklu-model-zip işine bağlı (plan notu).

**Ne değişti (XAI Faz 4 — 1.9.25'in tamamlayıcısı):**
- **Böbrek Patoloji:** `explain=true` → 3-backbone ensemble'ın (VGG19-BN + WideResNet50-2 +
  DenseNet-201) kesitin NERESİNE dayandığı (ensemble HiRes-CAM ortalaması) **ve üç modelin
  nerede AYRIŞTIĞI** (std **disagreement haritası** — tek skalar güvenin gösteremediği
  model-kararsızlığı göstergesi) görselde döner. XAI hatası analizi düşürmez; PT yüklemesi
  `weights_only=True`; tek-iş kilidi.
- Test: 6 yeni (gerçek 858MB PT ile deterministik) + mutasyon; tam süit 1843.

## app 1.9.25 — 2026-08-26 (🔍 Açıklanabilir AI: analizler artık NEDENİNİ gösteriyor)

Yayın etiketi: app → `client-app-v1.9.25`. Launcher (1.9.38) ve mobil (2.3.24) DEĞİŞMEDİ.
Paket kimliği (`buildId`, ≥1.9.13 istemcilerin `/api/health`te raporladığı **app katmanı** sha): `db30473e34d0`.
Monolit `base.zip` sha (≤1.9.12): `6bb3f21ca2ca`.
⚠️ Bu yayında **deps katmanı DEĞİŞTİ** (5. değişim; yeni XAI kütüphaneleri: shap/grad-cam/timm/captum)
ve **model paketleri yenilendi** (home/vet/research — XAI PT ikizleri eklendi; içerik listeleri artık
`build_tools/make_model_zip.py`te KODDA, elle-üretim dönemi bitti).

**Ne değişti (Açıklanabilir AI — Faz 1+2, `docs/xai-entegrasyon-plani.md`):**
- **AI Pro:** "Güven %62" artık NEDENİYLE görünür (poz × derinlik × maske × belirsizlik + kalibrasyonsuz
  tavan uyarısı); hekim onay ekranında **"Dozu en çok belirleyen: güç bütçesi · hedef alan"** satırı
  (7+1 hızlı duyarlılık — kapalı döngüye ağır hesap SOKULMADI).
- **Kedi Hastalık / CKD:** sonuç altında "🔍 Kararı sürükleyenler: Öksürük ↑ · Süre ↑ · Nabız ↓"
  (SHAP; CKD'de 'ortalama-hasta' referansı — tek-hasta ~0 dejenerasyonu çözüldü).
- **Termal / Ses:** opt-in **"🔍 Isı haritası üret"** anahtarı — modelin baktığı bölgeler / dinlediği
  frekans-zaman bandı görselde (Grad-CAM; sessizlik kapısının ARKASINDA — sessiz kayda duygu ısı
  haritası ÜRETİLMEZ; canlı kamera döngüsüne asla eklenmez).
- **Retikülosit / Böbrek-CT:** `explain=true` ile EigenCAM ısı haritası; **RNA:** hasta başına en
  etkili genler (IG; ≤25 hasta sınırı).
- Güvenlik değişmezleri: XAI hatası analizi/öneriyi ASLA düşürmez (zarif düşüş); tüm PT yüklemeleri
  `weights_only=True`; kapı sıraları korunud; iki taşımada (tek-EXE + :8100) parite; jeton şemasında
  açıklama analizin PARÇASI (ek jeton yok — sahip kararı #6).
- Test: ~75 yeni test (RED→GREEN), 18+ iki-yönlü mutasyon; tam süit 1837 + frontend 578/578.

## app 1.9.24 — 2026-08-26 (🔴 Web/masaüstünde AI Pro "organ konumlandırılmadı" ile açılmıyordu)

Yayın etiketi: app → `client-app-v1.9.24`. Launcher (1.9.38) ve mobil (2.3.24) DEĞİŞMEDİ.
Paket kimliği (`buildId`, ≥1.9.13 istemcilerin `/api/health`te raporladığı **app katmanı** sha): `9125d636a9c4`.
Monolit `base.zip` sha (≤1.9.12): `6e57f412d3d7`.

**Saha bildirimi:** *"Daha kamera bile açılmadan hata veriyor."* — masaüstü panelinde "AI Pro Başlat"a
basınca kamera hiç açılmadan **"Karaciğer henüz konumlandırılmadı"** (Sunucu Hatası) çıkıyordu.

**Neydi.** Masaüstü/web yolu "Başlat"ta DOĞRUDAN öneri hesaplatıyordu; öneri ise organın önceden
konumlandırılmış olmasını şart koşuyor. Ama sunucu kamerası ancak **seans sürerken** konumlandırma
yapıyordu — seans başlamadan önce hiçbir şey konumlanmadığı için istek hemen hata veriyordu. (Telefonda
1.9.22'de çözülen "kapalı döngü"nün masaüstü hâli; o düzeltme web yoluna uygulanmamıştı.)

**Yeni akış.** Masaüstü de artık telefondaki gibi **önce hazırlık** yapıyor: "Başlat" sunucu kamerasını
bir **ön-izlemede ısıtır** (kamera açılır, seçili organ konumlandırılır, **hiçbir bobin SÜRÜLMEZ, seans
BAŞLAMAZ**); organ konumlanınca öneri **kendiliğinden** hazırlanıp onay ekranına gelir. Hekim onaylayınca
gerçek seans başlar ve kamerayı devralır (tek kamera → çakışma yok). ⚠️ Masaüstünde AI Pro için sunucu
bilgisayarına **kamera bağlı olması** gerekir. Onay kapısı, doz/organ/süre mührü ve süre-watchdog aynen korunur.

---

## app 1.9.23 · launcher 1.9.38 · mobile 2.3.24 — 2026-08-25 (3. tur hata denetimi)

Yayın etiketleri: app → `client-app-v1.9.23`, launcher → `launcher-v1.9.38`, mobil → `launcher-v1.9.38`.
Paket kimliği (`buildId`, ≥1.9.13 istemcilerin `/api/health`te raporladığı **app katmanı** sha): `8e5ad639da10`.
Monolit `base.zip` sha (≤1.9.12 tek-parça istemciler): `bd71bb25a8d4`. Launcher setup sha: `7acb5c058161`.

**🔴 Hasta güvenliği / tedavi bütünlüğü (önce):**
- **AI Pro seans sahipliği.** İki cihazlı klinikte (klinik PC + telefon, ya da iki veteriner) yalnızca
  seansı **başlatan** operatörün kamerası tedaviyi sürebilir. İkinci bir cihaz AI Pro panelini açıp kare
  aksa bile artık **bobinleri kendi kamerasından hesaplanan hedefe süremez**, seans ortasında **organı
  değiştiremez** ve paneli kapatınca **birincinin onaylı seansını durduramaz**. Herkesin "Durdur"/acil-durdur
  düğmesi eskisi gibi açık kalır (her operatör tedaviyi durdurabilmeli); onaylanan doz/organ/süre mührü değişmez.
- **Seans-durdurma teyidi ve kayıt bütünlüğü.** Kapanmış seanslar buluta güvenilir gidiyor; onay (NACK)
  gelmeyen bobin komutları hayalet koşu kaydı bırakmıyor.

**Güvenilirlik / veri:**
- **"Beni hatırla" artık kapanışta bayatlamıyor.** Uygulama kapanırken (güncelleme/pencere kapanışı) en son
  oturum jetonu diske işleniyor; oturum deposu yazımı atomik yapıldı (yarıda kesilen yazım eski kaydı bozmaz).
  Sonuç: gereksiz "yeniden giriş" istekleri elendi.
- **Güncelleme sağlamlığı.** Bozuk bir yayının her açılışta yeniden kurulup geri alındığı döngü kırıcısı
  üretimde etkin; çalışan backend'i sahiplenen yolda oturum rotasyonu artık başlıyor; kaldırma/onarımda
  bobinler her zaman önce güvene alınıyor.

**Firmware (bu commit'te KAYNAK olarak var; OTA ile GİTMEZ — bobinlere ayrıca flash'lanır, tezgah doğrulaması
sürüyor):** S3 çok-bobin faz-kilidi ilk-darbe edinimi; ESP8266 WiFi portal öz-iyileşmesi (tek bir kopuşta
kalıcı çevrimdışı kalma giderildi); ESP8266 yerel MQTT broker'a geri dönüş; ESP8266 EEPROM bellek-harita düzeni.

Ayrıntı (25 bulgu, kırmızı-önce test + mutasyon + adversaryal inceleme): `docs/denetim-bulgular-3.md`.

---

## app 1.9.22 · mobile 2.3.23 — 2026-08-24 (🔴 AI Pro telefonda hiç başlamıyordu)

**Saha bildirimi:** *"Bu hatayı verip çalışmıyor AI Pro."* — ekranda "Organ henüz lokalize
edilmedi. Kamerayı hedefe doğrultup 'Yeniden konumla' ile lokalizasyonu tamamlayın" yazıyordu.

**Neydi.** Kapalı bir döngü vardı ve **telefonda AI Pro hiç başlatılamıyordu.** Öneri
hesaplanması için organın konumlandırılmış olması gerekiyor; konumlandırma ancak kamera karesi
işlenince oluşuyor; kareler ise yalnız seans **başladıktan sonra** gönderiliyordu — seans da öneri
olmadan başlamıyordu. Üstelik hata metni tam olarak "Yeniden konumla"ya basmayı söylüyordu, ama o
düğme yalnızca sunucuya bir işaret bırakıyor ve işleyecek kare gelmediği için hiçbir şey
olmuyordu. Kullanıcı aynı hataya kilitleniyordu; yanlış kullanım değildi.

**Yeni akış — istenen sırayla.** "Başlat"a basınca önce hazırlık çalışıyor ve ne olduğu ekranda
yazıyor: *hayvan aranıyor → hayvan görünüyor, organ aranıyor → organ konumlandı*. Bunun için
"hayvan var mı" bilgisi organ tespitinden ayrıldı; önceden ikisi tek bir "bulunamadı" altında
birleşiyordu ve operatöre kamerayı mı çevirmesi yoksa açıyı mı değiştirmesi gerektiği
söylenemiyordu. Organ konumlanınca seçilen organın konumuna göre faz ve duty **kendiliğinden**
hesaplanıp onay ekranına geliyor.

**Tıbbi güvenlik sertleştirmeleri:**
- Konumlandırma artık **üst üste iki tutarlı ölçüm** istiyor — tek bir şanslı kare tedavi
  parametrelerini tetikleyemez.
- Ekranda **güven yüzdesi** görünüyor ve düşükse ayrıca işaretleniyor. (Eşik değiştirilmedi;
  yükseltmek gerçek hastaları reddederdi. Amaç kararı engellemek değil, bilgilendirmek.)
- Hayvan bulunamazsa 45 saniyede somut yönlendirme (ışık, mesafe, kadraj), iki dakikada kamera
  otomatik duruyor (pil koruması). Her aşamada "Vazgeç" var.

Paket kimliği (`buildId`, `/api/health`): `acca5ded1547` — katmanlı kurulumda cihaz **app
katmanının** sha'sını raporlar. Eski ≤1.9.12 tek-parça istemciler `base.zip` sha'sı `296161f2f4a1`
raporlar. Mobil APK: `2.3.23` (versionCode `30`).

⚠️ **Bağımlılık katmanı DEĞIŞMEDI** (`2189cdd4970e`, dördüncü ardışık yayın): kliniklere
yalnız ~71 MB'lık uygulama katmanı iner, 1,53 GB'lık bağımlılık paketi yeniden indirilmez.
Launcher `1.9.37`'de kaldı — bu turda değişmedi.

⚠️ **Değişmeyenler:** hekim onayı olmadan tedavi başlamıyor ve hazırlık karesi **hiçbir bobini
sürmüyor** — sürüş yalnız onaylanmış, süre denetimli seansta yapılıyor.

## app 1.9.21 · launcher 1.9.37 — 2026-08-24 (🔴 "Beni hatırla" düzeltildi)

**Etiketler:** `client-app-v1.9.21` → `base-app.zip` (sha `58167771f6d5`) · `launcher-v1.9.37`.
Paket kimliği (`buildId`, `/api/health`): `58167771f6d5`. Eski ≤1.9.12 tek-parça istemciler
`base.zip` sha'sı `655859570f86` raporlar.

⚠️ **Bağımlılık katmanı DEĞİŞMEDİ** (`2189cdd4970e`): kliniklere yalnız ~71 MB'lık uygulama
katmanı iner.

**Saha bildirimi:** *"Client'taki beni hatırla düzgün çalışmıyor; güncelleme geldi, tekrar mail
ve şifre istedi."*

**Neydi.** Oturum iki yerde birden yaşıyordu. Bilgisayar uygulaması girişi yapıp oturumu güvenli
biçimde diske yazıyor, aynı oturumu tedavi penceresine de devrediyordu. Pencere ise oturumu
arka planda kendi başına tazeliyor — ve tazelemede sunucu **yeni bir anahtar verip eskisini
geçersiz kılıyor**. Yeni anahtar yalnız pencerede kalıyor, diskteki kopya eskiyordu. Bir sonraki
açılışta uygulama o eski anahtarla giriş yapmayı deniyor, sunucu haklı olarak reddediyor ve
uygulama kayıtlı oturumu **siliyordu** → e-posta ve şifre yeniden soruluyordu.

Güncelleme bunu güvenilir biçimde tetikliyordu: pencere bir süre açık kalıp anahtarı tazeliyor,
hemen ardından güncelleme uygulamayı yeniden başlatıyordu. Bu yüzden "her güncellemede tekrar
soruyor" gibi görünüyordu.

**Ne yapıldı.** Pencere anahtarı her tazelediğinde yeni oturum bilgisayar uygulamasına geri
bildiriliyor ve diske işleniyor. Böylece tek bir oturum iki yerde ayrışmıyor.

⚠️ Kalıcılık **yalnız** "Beni hatırla" işaretliyse sürer; işaretlenmediyse hiçbir şey diske
yazılmaz. Farklı bir hesapla giriş yapılırsa önceki kayıt değiştirilmez, ve eksik/boş bir oturum
sağlam kaydın üzerine yazılamaz.

## launcher 1.9.36 — 2026-08-23 (bozuk bir yayın artık sessizce onaylanmıyor)

**Etiket:** `launcher-v1.9.36`.

**Cihaz "açıldı" demek "kullanılabilir" demek değildi.** Güncelleme sonrası sağlık kontrolü yalnız
"yazılım ayakta mı" diye bakıyordu. Tıbbi kayıt veritabanını bozan bir yayında cihaz açılıyor,
sağlıklı sayılıyor, güncelleme **onaylanıyor** ve geri dönülecek eski sürüm **siliniyordu** —
ama klinik hiçbir seans başlatamıyordu (kayıt yazılamadığı için seans reddedilir). Otomatik geri
dönüş yolu da kalmadığı için tek çare elle "Onar"dı, o da aynı bozuk paketi yeniden kuruyordu.

Artık güncelleme onaylanmadan önce "kayıt veritabanı hazır mı" ayrıca soruluyor; hazır değilse
yayın başarısız sayılıp eski sürüme dönülüyor ve sebebi yazılıyor.

⚠️ Bu kontrol sağlık ölçümünün kendisine **eklenmedi**: veritabanı bozuk olsa bile acil durdurma
çalışmalıdır ve cihazı "sağlıksız" saymak o yolu da düşürürdü. Ayrıca eski sürümler bu bilgiyi
bildirmediği için, bilgi **yoksa** güncelleme normal onaylanır — bilinmeyeni "bozuk" saymak
sahadaki eski kurulumları güncellenemez hâle getirirdi.

## app 1.9.20 — 2026-08-23 (güncelleme uçlarına yetki kapısı)

**Etiket:** `client-app-v1.9.20` → `base-app.zip` (sha `7e63ec096932`).
Paket kimliği (`buildId`, `/api/health`): `7e63ec096932` — katmanlı kurulumda cihaz **app
katmanının** sha'sını raporlar. Eski ≤1.9.12 tek-parça istemciler `base.zip` sha'sı `20aac12fa705`
raporlar.

⚠️ **Bağımlılık katmanı DEĞİŞMEDİ** (`base-deps.zip` sha `2189cdd4970e`, 1.9.19'daki ile birebir):
kliniklere yalnız ~71 MB'lık app katmanı iner, 1,4 GB'lık bağımlılık paketi yeniden indirilmez.
Manifest o katmanın URL'sini eski etiketinde korur.

- **Kurulum ve geri-alma uçları artık yetki istiyor.** Eski (PEMF Vet Client'sız) kurulum kanalı
  açıkken klinik ağındaki herhangi bir cihaz kimlik doğrulamadan cihazda kurulum başlatabiliyor
  ya da yayınlanmış bir düzeltmeyi geri alabiliyordu. Yerel ağ kimlik denetiminden muaf sayıldığı
  için hotspot'a bağlanan bir telefon bile yeterliydi. Durum sorgusu (salt-okunur) kasten açık
  kaldı — arayüzün güncelleme rozeti kimliksiz cihazlarda da çalışmalı.

⚠️ Bu sürümde uygulamanın kendisinde başka değişiklik yok; bağımlılık katmanı **değişmedi**
(kliniklere yalnız ~71 MB'lık uygulama katmanı iner).

## offline kurulum (Inno) — 2026-08-23 (🔴 hasta güvenliği)

**Kurulum artık bobinleri durdurmadan cihaz yazılımını kapatmıyor.**

Offline kurulum dosyası, çalışan arka servisi kapatırken bobinlere durdurma komutu gönderiyordu —
ama yalnız cihaz **servis olarak** kurulmuşsa. PEMF Vet Client ile kurulmuş bir cihazda servis
yoktur; o durumda durdurma adımı tamamen atlanıyor ve süreç doğrudan sonlandırılıyordu. Sonlandırma
sinyalsizdir: yazılımın kendi güvenli kapanışı çalışmaz, **bobin 6-8'e durdurma yayını gitmez** ve
bu bobinlerin firmware'inde bağlantı-kesildi koruması YOKTUR → seans süresi boyunca (20-120 dk)
hastanın üzerinde enerjili kalabilirdi.

Kurulum artık **her koşulda** önce donanım acil durdurmasını gönderiyor, bobinlerin gerçekten
durması için bekliyor, ancak sonra süreci kapatıyor. Kaldırma yolu bu değişmezi zaten uyguluyordu;
kurulum yolu geride kalmıştı.

⚠️ **Sahadaki cihazlar için:** bu düzeltme yalnız **yeni** offline kurulum dosyasında vardır.
Elinizdeki eski kurulum dosyasını çalışan bir cihazda çalıştırmayın; önce seansı bitirin.

## launcher 1.9.35 — 2026-08-23 (güncelleme altyapısı denetimi: kesinti kurtarma, kilit, boşuna indirme)

**Etiket:** `launcher-v1.9.35`.

Güncelleme altyapısının uçtan uca denetiminde bulunan ve doğrulanan arızalar. Hiçbiri günlük
kullanımda görünür değildi; hepsi **kesinti, çakışma ya da hata anında** ortaya çıkıyordu.

### Kesintiden sonra kurtarma

- **Uygulama katmanı güncellemesi yarıda kesilirse cihaz artık kendini toparlıyor.** Elektrik
  kesintisi / pencerenin kapatılması gibi bir durumda cihaz "kurulu değil" görünüyor ve kullanıcı
  ~1,46 GB'ı yeniden indirmek zorunda kalıyordu — oysa çalışan sürüm diskte duruyordu.
- **Yarım kalan güncelleme artık diski kilitlemiyor.** Kesintiden kalan geçici klasör (GB'lara
  varabilir) siliniyordu ama bu, disk kontrolünden **sonra** oluyordu: kontrol o alanı dolu
  görüp güncellemeyi "Yetersiz disk alanı" ile reddediyordu — ve artığı silecek olan şey tam da
  reddedilen güncellemenin kendisiydi. Kilitlenme kalıcı olabiliyordu.
  ⚠️ Geri dönüş kopyası (`runtime.old`) temizlikte **korunuyor**; sağlam bir kuruluma dokunulmuyor.

### Çakışma ve boşuna indirme

- **İki pencere artık birbirinin kurulumunu bozamıyor.** Başlatıcının kendi kendini güncellemesi,
  diğer akışların aldığı kurulum kilidini almıyordu; ikinci bir pencere kurulum/onarım yaparken
  bu akış onun arka servisini kapatabiliyordu. (Aynı sınıf 2026-08-16'da bir kez düzeltilmişti;
  geride kalan tek akış buydu — artık beş akışın hepsi testle denetleniyor.)
- **Tek bir disk hatası 7 GB'lık boşuna indirme başlatmıyor.** Yerel dosya hataları (antivirüs
  kilidi, dolu disk, izin) "geçici ağ hatası" sayılıyordu: indirme **tamamlandıktan sonra** dosya
  taşınamazsa 6 kez tam yeniden indirme tetikleniyordu. Gerçek ağ kopmalarında yeniden deneme
  aynen sürüyor.

### Bozuk bir yayın artık cihazı kilitlemiyor

- **Başlayamayan bir sürüm sonsuza kadar yeniden denenmiyor.** Yeni sürüm kurulup cihazda
  başlayamazsa güvenlik için eskisine dönülüyordu — ama bu her açılışta baştan tekrarlanıyordu:
  arka servis kapatılıyor, paket yeniden açılıyor, üç dakika bekleniyor, yine geri alınıyordu.
  Klinik her açılışta dakikalarca bekliyordu ve durumdan çıkmanın tek yolu yeni bir yayın
  beklemekti. Artık iki başarısız denemeden sonra **otomatik** kurulum duruyor; ekranda sebebi ve
  ne yapılacağı yazıyor ("Onar" ile elle denenebilir), yeni bir sürüm çıkınca da normal akış
  kendiliğinden geri geliyor. Elle "Onar" hiçbir koşulda engellenmiyor.
- **Model paketleri artık kurulumun kritik dosyalarını ezemiyor.** Profil paketleri kurulum
  klasörüne açılıyor ve korunan girdi listesi güncel değildi: paket kaydı, kademeli-yayın kimliği,
  yedek hedefi ve geri dönüş kopyası açıktaydı. Paket kaydının ezilmesi en ağırıydı — cihaz
  sonsuza dek "güncel" görünür ve **zorunlu geri çağırma dahil** hiçbir yama ulaşmazdı. Liste
  artık kaynaktan türetiliyor; yeni bir durum dosyası eklenip listeye işlenmezse testler kırılıyor.

### Geri alma artık doğruyu söylüyor

- **"Eski sürüme dönüldü" mesajı gerçeği yansıtıyor.** Sınır dosyası kayıp/bozuk olan bir
  kurulumda yedek hiç alınamıyordu ama sistem yedek varmış gibi davranıyordu: sağlık kapısı
  düştüğünde geri alma hiçbir şey yapmadan "başarılı" diyordu ve cihaz doğrulanmamış sürümde
  kalıyordu. Artık ya gerçekten geri alınıyor ya da alınamadığı **söyleniyor**.
- **Yarıda kesilen "Onar" bozuk model bırakmıyor.** Model paketi açılırken kesinti olursa kayıt
  hâlâ "güncel" görünüyordu; o profil bir daha yenilenmiyor ve AI analizi anlaşılmaz bir hatayla
  düşüyordu. Kayıt artık açılımdan önce geçersiz kılınıyor.

### Yönetimsel uçlar

- Kurulum ve geri-alma uçları artık yetki istiyor. Eski (launcher'sız) kurulum kanalı açıkken
  klinik ağındaki herhangi bir cihaz kimlik doğrulamadan kurulum başlatabiliyor ya da yayınlanmış
  bir düzeltmeyi geri alabiliyordu. Durum sorgusu (salt-okunur) kasten açık kaldı.

### Kaldırma

- Kaldırmada geride kalan kurulum artıkları (üç durum dosyası + kesintiden kalan GB'lık geçici
  klasörler) artık siliniyor; "Uygulama verisini sil" işaretliyken kurulum kökü gerçekten gidiyor.

## mobile 2.3.22 — 2026-08-23 (sürüm uyarısı yanlış alarm veriyordu)

**Etiket:** `launcher-v1.9.34` → `PEMF_Vet_Mobil.apk` · versionCode **29**.

**Düzeltilen (sahadan bildirildi).** Telefon tam güncelken bile "Sürümler farklı" uyarısı
çıkıyordu. Sebep: bant telefonun sürümünü (2.3.x) **cihazın** sürümüyle (1.9.x) karşılaştırıyordu —
bunlar ayrı numaralandırma şemalarıdır, hiçbir zaman eşit olamazlar. Sürekli yanlış alarm, gerçek
uyarının değerini sıfırlar.

Uyarı artık güncelleme altyapısıyla **aynı ölçüyü** kullanıyor (yayınlanmış en son mobil sürüm):

- telefon güncelse bant **hiç çıkmaz**;
- telefon gerçekten eskiyse ve güncelleme açılışta ertelendiyse hatırlatır (`2.3.21 → 2.3.22`);
- erteleme yoksa susar — indirme düğmeli güncelleme bandı zaten sahnededir (çift bant yok).

Korunanlar: seans sürerken gösterilmez; ağ/manifest yokken sahte uyarı üretmez; bağlantı ve acil
durdurma sürüm farkından **hiçbir koşulda** etkilenmez. Kaldırılan yanlış yönlendirme: "Ayarlar'dan
güncelleyebilirsiniz" (uygulamada öyle bir giriş yok).

Kilit: `pf/src/components/domain/__tests__/SurumFarkiBanner.test.tsx` (6 test; ilk test tam da
sahadaki durumu — güncel telefonda bant çıkmamasını — ölçer).

### Hasta güvenliği (önce bunlar)

- **Güncelleme bantları artık ÇALIŞAN BOBİNİ görüyor.** İki bandın da gizlenme kapısı yalnız
  "seans kaydı açık mı"ya bakıyordu; oysa bobinler seanssız da sürülebilir (AI Pro, bobin paneli,
  başka istemci). O durumda bobin hastanın üzerinde **enerjiliyken** güncelleme bandı ve "Güncelle"
  düğmesi çiziliyordu. Ölçü, uygulamanın geri kalanıyla (acil durdurma düğmesi, kaldırma koruması)
  aynı tek kaynağa bağlandı: `useDonanimCalisiyor()`.

### Güncelleme güvenliği

- **İndirilen paket artık kurulumdan önce doğrulanıyor (SHA256).** Bugüne kadar tek kontrol dosya
  BOYUTUYDU; yayın bilgisi "doğrulanır" dediği hâlde kod bunu yapmıyordu. Aynı boyutta bozuk ya da
  karışık inen bir paket kurulmaya çalışılabiliyordu. Hesaplama telefonu yormaz (paket parça parça
  okunur); hesaplanamadığı durumda güncelleme yine de sürer.
- **APK indirme adresi artık pinli.** Manifest'ten gelen adres doğrulanmadan indiriliyordu; şema
  ve host denetimi yoktu, uygulamada düz HTTP açık olduğu için `http://` bir adres de gerçekten
  inerdi. Masaüstü istemcide 2026-08-04'te konan koruma (yalnız yayın deposunun kendi yolu ya da
  GitHub nesne depoları) mobil tarafa da geldi. Şüpheli adres "güncelleme yok" sayılır.
- **Sunucu hatası artık doğru anlatılıyor.** Paket adresi bozuksa telefon hata sayfasını APK
  sanıp indiriyordu ve kullanıcıya "bağlantınızı kontrol edip tekrar deneyin" diyordu — oysa
  tekrar denemek durumu değiştirmiyordu. Artık ayrı ve doğru mesaj gösteriliyor.
- **Eski paketler siliniyor.** Kurulan APK telefonun önbelleğinde kalıyordu (her yayında ~128 MB);
  yeterince biriktiğinde bir sonraki güncellemenin inmesini engelleyebilirdi.
- **Güncelleme mesajları kırpılmıyor.** Bantta üç satırdan uzun metin kesiliyordu ve kesilen kısım
  tam da ne yapılacağını söyleyen cümleydi.

## app 1.9.19 — 2026-08-22 (eksik-taraması düzeltmeleri: NACK görünürlüğü, jeton kapısı, rebinding koruması)

**Etiket:** `client-app-v1.9.19` → `base-app.zip` (sha `9506287592a7`) + `base-deps.zip` (sha `2189cdd4970e`).
Paket kimliği (`buildId`, `/api/health`): `9506287592a7` — katmanlı kurulumda cihaz **app
katmanının** sha'sını raporlar. Eski ≤1.9.12 tek-parça istemciler `base.zip` sha'sı `cb0b825e64f6` raporlar.

⚠️ **Bağımlılık katmanı bir kez daha iniyor (~1,4 GB, bir kereliğine).** Bağımlılıklar değişmedi;
dağıtım profilleri (`deploy/*.env`) yanlış katmandaydı ve sınır düzeltildi — profiller artık
app katmanında, yani bundan sonraki profil değişiklikleri kliniklere yalnız ~71 MB indirtecek.

12-ajanlı eksik-taramasının P1/P2 kod kapanışları (docs/denetim-bulgular-2.md 18. parti + p2 turu).

### Hasta kaydı ve güvenlik (önce bunlar)

- **Bobinin açık reddi (NACK) artık görünür ve kayda işlenir.** Bobin bir komutu reddederse
  (hız sınırı / geçersiz parametre) operatör bunu SEBEBİYLE görür; reddedilen start, tedavi
  geçmişine "koştu" olarak giremez — koşu kaydı otomatik düzeltilir. Onay zaman aşımında kayıt
  bilerek KORUNUR (kayıp onay, gerçek koşunun dozunu silmemeli). [4.5]'in kalan yarısı.
- **Acil durdurmanın bulut yedeği sağlamlaştırıldı:** çifte tetikte iki ayna oturumu artık
  birbirini düşürmüyor; kimlik her koşulda broker sınırına sığıyor. [3.3]
- **Kapanan seans kaydı buluttan bozulamaz:** bulut kopyası bayat-"açık" ise kapanış saati ve
  süre artık ezilmiyor (doz belgesi korunur); başka cihazda kapatılan seans yerelde de kapanır.
- **KVKK:** eski hastaların anonimleştirilmesi yaş ve kiloyu da kapsıyor; anonim bir kayda
  gerçek bilgi geri yazılırsa kayıt saklama düzenine yeniden girer.

### Ücretlendirme altyapısı (satış hâlâ KAPALI)

- **Jeton kapısı AI uçlarına bağlandı** ve ödeme geri-çağrıları jeton yüklüyor — ancak bayrak
  kapalı: bugün hiçbir analiz ücretlendirilmiyor, hiçbir davranış değişmedi. ⚠️ Seans durdurma,
  acil durdurma ve tedavi uçları jeton kapısının ARKASINDA DEĞİL (yapısal testle kilitli).

### Ağ güvenliği

- **DNS-rebinding koruması fiilen devrede** (`PEMF_ALLOWED_HOSTS=auto`): telefon/tarayıcının
  IP, localhost, *.local, makine adı ve tünel erişimleri aynen çalışır; yabancı alan adıyla
  gelen istekler reddedilir. Kurumsal ağ adı gereken klinik `auto,ad` ile ekleyebilir.

### Doğrulama

Backend 1625 · mobil 532 · site 171 · launcher 222 test; 35 mutasyon doğrulaması.

---

## launcher 1.9.34 — 2026-08-22 (Host koruması launcher kurulumlarında da açık)

**Etiket:** `launcher-v1.9.34` → `PEMFVetClient-Setup-1.9.34.exe` (sha `9bce6a7dcf32`).

- Launcher artık backend'e `PEMF_ALLOWED_HOSTS=auto` geçiriyor — DNS-rebinding koruması siteden
  kurulan kliniklerde de devrede (deploy profilleriyle aynı davranış; ortamda tanımlıysa dokunmaz).
- Başka işlevsel değişiklik yok.

---

## mobile 2.3.21 — 2026-08-22 (jeton bildirimi altyapısı)

**Etiket:** `launcher-v1.9.32` → `PEMF_Vet_Mobil-2.3.21.apk` (versionCode 28).

- Jeton sistemi ileride açıldığında telefon, "jeton bitti" durumunu genel sunucu hatasıyla
  karıştırmadan ayrı ve anlaşılır gösterecek (bugün görünür bir değişiklik yok — satış kapalı).
- 2.3.20'deki tüm düzeltmeler geçerli.

---

## app 1.9.18 — 2026-08-21 (2. tur denetimi + ücretlendirme altyapısı + bulut sertleştirme)

**Etiket:** `client-app-v1.9.18` → `base-app.zip` (sha `c780ef1130bf`) + `base-deps.zip` (sha `69dc57a16dab`).
Paket kimliği (`buildId`, `/api/health`): `c780ef1130bf` — katmanlı kurulumda cihaz **app katmanının**
sha'sını raporlar. Eski ≤1.9.12 tek-parça istemciler `base.zip` sha'sı `f4113b3ef753` raporlar.

⚠️ **Bu sürümde bağımlılık katmanı da yenileniyor (~1,4 GB, bir kereliğine).** Hiçbir bağımlılık
değişmedi; paketin baytları bir **derleme belirlenimciliği hatası** yüzünden ayrışıyordu ve bu
sürümde kaynağında düzeltildi (aşağıya bakın). Sonraki sürümler yine ~71 MB olacak.

İkinci tur çok-ajanlı denetimin (23 bulgu, `docs/denetim-bulgular-2.md`) tamamı ile bu turda alınan
sahip kararları. Beraberinde: site metni elden geçti, jeton ücretlendirme **altyapısı** kuruldu
(satış **kapalı**) ve canlı Supabase şeması sertleştirildi.

### Hasta kaydı ve güvenlik (önce bunlar)

- **Gözlem notu artık hasta KİMLİĞİNE bağlı.** Sıfırlama anahtarı yalnız hasta *adıydı*; aynı
  isimli iki hastada A'nın notu B'nin tıbbi kaydına yazılabiliyordu. [4.1]
- **Broker erişilemezken "durduruldu" onayı verilmiyor.** Durdurma turu `mqtt_unavailable`'ı
  başarı sayıyordu — operatör bobin durmadığı hâlde "durduruldu" görüyordu. [1.1]
- **Acil durdurmada sahte alarm giderildi.** Onay takibindeki `command_id` çakışması, E-stop
  anında "ESP onayı gelmedi" kırmızı uyarısı üretiyordu. [3.2]
- **ESP'nin yerel termal kesmesi backend'de işleniyor** — operatör bobinin *neden* durduğunu
  görüyor (eskiden olay hiç işlenmiyordu). [4.2]
- **Frekans tavanı seans yolunu da kapsıyor**; doğrudan API'de karma-dizi doz tutarsızlığı bitti. [4.4]
- **Doz geçmişine hiç koşmamış bobin koşuları yazılmıyor** (teslim/kabul ayrımı). [4.5]
- **Süreli seans <30 sn crash-loop'u kapandı**: NVS resume, kümülatif süresiz-tavan sayacını
  geri yüklemeden sıfırlıyordu; 120 dk tavan böylece delinebiliyordu. [1.3]

### ⚠️ Firmware — S3 ve 8266 yeniden flash'lanmalıdır

Bu sürümdeki bobin düzeltmeleri **cihaz yazılımındadır**; paket güncellemesi onları taşımaz.

- Süreli seans devralma tabanı (yukarıdaki [1.3]) — her iki firmware.
- HG-3 DC-yapışma latch'i PWM pasifken birikmiyor; faz senkronu sessizce kapanmıyor. [4.3]
- Ölü komut yüzeyleri kaldırıldı (`SET_PARAMS`, `start_at`, `SYNC_ALL`) — kusurlu kümülatif-tavan
  makinesi de yüzeyle birlikte gitti. [4.6]
- Son-vasiyet (LWT) mesajları artık `retain=false` — bayat kopuş bildirimi canlı sanılmıyor.

### Kurulum, güncelleme ve yayın

- **"Onar" ile önbellek çelişkisi giderildi:** onarım, cihazın kurulu paketlerini disk kapısında
  koruyor; gereksiz 1,4 GB yeniden indirme olmuyor.
- **İptal edilen kurulum yarım dosya bırakmıyor.**
- **Takas sonrası geri-alma hatası yutulmuyor** — doğrulanmamış sürüm "iptal edildi" mesajıyla
  canlıda kalamaz. [3.1]
- **Yayın runbook'u düzeltildi**: paketler artık kendi etiketlerine yükleniyor; harfiyen izlenen
  eski yol saha geneli 404 üretebilirdi. [3.4]
- `restore_assets.ps1` "klon = çalışan sistem" vaadini tutuyor (`cat_organ` çekirdek modeli). [3.5]

### Mobil (2.3.19)

- **Güncelleme kapısı seansı olmayan çalışan bobinleri de görüyor**; yükleyici bobin çalışırken
  ekranı almıyor. [2.1]

### Site, ücretlendirme ve hesap

- **Site metni baştan sona elden geçti**: anlaşılmayan/karşılığı olmayan ifadeler ayıklandı,
  kısaltmalar açıklandı, indirme ve hesap akışları sadeleşti (`pemf-vet-web/METIN-KILAVUZU.md`).
- **"İşlem önceliği / kuyrukta bekleme / anında analiz" vaadi kaldırıldı.** Mekanizma var ama
  kapalı (`PEMF_TIER_ENFORCED=0`) ve kliniğin kendi makinesinde — kapalı bir mekanizma satılamaz.
- **Jeton ücretlendirme altyapısı kuruldu — SATIŞ KAPALI.** 1 jeton = 1 yapay zekâ analizi;
  şema, uç ve cihaz kapısı hazır ve testli, ancak `FREE_MODE` açık ve `PEMF_JETON_ENFORCED`
  kapalı: **bugün hiçbir analiz ücretlendirilmiyor.** ⚠️ Jeton bir *ticari* kapıdır; seans
  başlatma/durdurma, **acil durdurma** ve sensör izleme hiçbir koşulda engellenmez.
- **"Kullandıkça Öde" üyeliği eklendi** (aylık ücret ve önden alım yok; jeton başına ücret,
  faturalanmamış kullanım tavanı ile). Yine satış kapalı olduğu için tahsilat yolu uyumaya devam ediyor.

### Bulut (Supabase) sertleştirme

- **Tablolarda `anon`/`authenticated` rollerine bırakılmış doğrudan yetkiler kaldırıldı** (bunlar
  Supabase'in varsayılanıydı; RLS onları zaten reddediyordu, ama tek bir yanlış politika ekiyle
  yazma yetkisine dönüşebilirlerdi). Kullanıcı okumaları SECURITY DEFINER RPC'lere taşındı.
- **Kurulum sırasında bulunan iki açık kapatıldı:** jeton dönem-yenileme fonksiyonu `anon`a
  açıktı (sınırsız jeton yazma) ve cihaz sırrı doğrulayıcısı bir *orakül* olarak çağrılabiliyordu.
- Canlı şema artık `scripts/supabase_sql.py --denetim` ile denetleniyor.

### Paket belirlenimciliği (bu sürümde bulundu ve düzeltildi)

- **Her yayın, hiçbir bağımlılık değişmese bile her kliniğe 1,4 GB indiriyordu.** Bağımlılık
  paketinin sha'sı her derlemede değişiyordu; boyut baytı baytına aynı olduğu için de fark
  edilmiyordu. Yayındaki paketle karşılaştırıldı: 6154 dosyanın 6153'ü birebir aynı, tek fark
  `base_library.zip`; onun da içinde tek bir dosya (`_collections_abc.pyc`) — aynı boyut,
  farklı bayt. Kök neden: `marshal`, `frozenset` sabitlerini kümenin yineleme sırasına göre
  yazar; o sıra `PYTHONHASHSEED`e bağlıdır. Build artık tohumu sabitliyor.
  *(Ölçüm: rastgele tohumla 5 derleme → 5 farklı çıktı; sabit tohumla 3/3 birebir aynı.)*

### Güvenlik ve araçlar

- `secrets_backup.py restore` sonrası `git add -A` gerçek sırları public depoya taşıyabiliyordu;
  koruma eklendi ve gitleaks bu sır sınıfını görüyor. [2.2]

### Doğrulama

Backend 1568 · mobil 525 · launcher 267 · site 164 test yeşil; denetim düzeltmeleri mutasyonla
doğrulandı.

---

## app 1.9.17 — 2026-08-19 (donanım-uyum turu: hibrit bobin güvenliği uçtan uca)

**Etiket:** `client-app-v1.9.17` → `base-app.zip` (sha `7a0de0cdcf38`) + `base-deps.zip` (sha `d22c35a91d05` — **1.9.16 ile BAYT-BAYT AYNI**, paket-belirlenimciliği çalıştı: kurulu istemciler yalnız ~71 MB app katmanını indirir).
Paket kimliği (`buildId`, `/api/health`): `7a0de0cdcf38` — katmanlı kurulumda cihaz **app
katmanının** sha'sını raporlar (launcher `PEMF_BASE_SHA`e onu geçirir). Eski ≤1.9.12 tek-parça
istemciler `base.zip` sha'sı `5cdb86380a55` raporlardı. *(2. tur denetimi [5.5]: bu satır
eskiden base sha'sını "buildId" diye etiketliyordu — sahadan gelen kimlikle eşleşmiyordu.)*

Bugünkü çok-ajanlı donanım-uyum denetiminin (12 gerçek uyumsuzluk, `docs/DONANIM-UYUM-ANALIZI-2026-08-19.md`)
backend ayağı. Firmware ayağı cihazlara ayrıca flash'landı; bu paket backend/sunucu düzeltmelerini taşır.

### Acil durdurma artık uçtan uca doğrulanıyor
- **ESP komut onayı (ack round-trip):** E-stop'un bobine GERÇEKTEN ulaştığı `command_id` ile doğrulanır;
  onay 2 sn'de gelmezse operatöre açık uyarı (eskiden broker'ın "aldım"ı bobin "durdu" sanılıyordu).
- **E-stop bulut aynası:** yerel broker çöküp ESP buluta göçtüyse acil durdurma HiveMQ üzerinden de
  yayınlanır. Kimlik bilgileri pakete gömülü provizyonla gelir (sahip kararı: indir-kur yeterli);
  ilk çalışmada makineye-bağlı şifreyle `pemf_secrets.json`'a taşınır.
- **Hedefli reconcile:** yeniden bağlanan bir bobin "çalışıyorum" derse ama backend'in niyeti/aktif
  seans bunu kapsamıyorsa (reboot-sonrası hayalet), o bobine otomatik hedefli STOP gider.

### Komut tutarlılığı (3 bobin ailesi tek dil)
- selftest/reset artık ESP'lerin gerçekten dinlediği kanala gider (eski ölü kanal kaldırıldı);
  bobin self-test sonuçları (geçti/kaldı/atlandı) operatöre bildirim olarak düşer.
- ESP frekans komutları 1000 Hz donanım tavanına önden sabitlenir (8266 reddi/S3 sessiz kırpması yerine).
- STM referans bobini boştayken anlamsız senkron darbesi basmaz; ≥50× frekans ayrışmasında yanıt
  `sync_warning` taşır (reddetmez, uyarır).
- Bobin 8 (8266) ani kopuşu saniyeler içinde görünür (last-will); bayat/retained MQTT mesajları
  artık canlı durum sanılmaz.

### Sağlamlaştırma
- Süresiz moda cihaz+sunucu uyumlu 120 dk mutlak tavan (kümülatif — cihaz çök-diril döngüsüyle uzatılamaz).
- Acil-durdurma bulut aynasına 8 sn toplam süre bütçesi; tekrar eden hayalet-bobin bildirimleri 5 dk'da bire katlanır.
- E2E süiti donanım-uyum bölümüyle genişledi (canlı 119/119); pytest 1436.

---

## app 1.9.16 — 2026-08-18 (denetim turu: hasta kaydı, doz saklama, bağlanma)

**Etiket:** `client-app-v1.9.16` → `base-app.zip` (sha `00de04c75ac9`) + `base-deps.zip` (sha `d22c35a91d05`).
Paket kimliği (`buildId`, `/api/health`): `00de04c75ac9` — katmanlı kurulumda app-katmanı
sha'sı raporlanır; `42cbc0c11a0e` bu yayının `base.zip` (tek-parça) sha'sıydı. *(2. tur [5.5]
düzeltmesi — yanlış etiket 1.9.16'dan beri sistematikti.)*

⚠️ **Bu sürümde bağımlılık katmanı da yenileniyor (~1,4 GB, bir kereliğine).** Paketlerin baytları
artık her derlemede birebir aynı üretiliyor; bu düzeltme 1.9.15'ten sonra girdiği için bir kez daha
inmesi gerekiyor. Sonraki sürümler yine ~71 MB olacak.

### Hasta kaydı ve doz (önce bunlar)

- **Seans devri, önceki seansın telemetrisini yeni seansa yazıyordu.** Manuel seans sürerken AI Pro
  başlatıldığında (devralma), önceki seanstan kalan **kısmi dakikanın** sıcaklık/akım örnekleri yeni
  seansın kaydına düşüyordu. Artık eski seans kendi satırına düzgün kapatılıyor (son dakikası dahil)
  ve yeni seans temiz başlıyor.
- **Uygulanan doz kaydı artık 90 günde silinmiyor.** "Hangi bobin, hangi frekans/duty ile kaç saniye"
  bilgisi sensör telemetrisiyle aynı saklama süresine bağlanmıştı; 90 gün sonra seans başlığı kalıp
  doz cevabı yok oluyordu. Doz kaydı ayrıldı (varsayılan 10 yıl) ve silinmesi denetim izine yazılıyor.
- **Kayıt tutulamıyorsa seans başlamıyor** kuralı korunuyor; buna ek olarak yapılandırma dosyası
  okunamadığında artık **varsayılanlarla ezilmiyor** — eskiden MQTT broker adresi gibi ayarlarınız
  ilk kayıtta sessizce sıfırlanabiliyordu.

### Bağlanma ve keşif

- **Telefon cihazı daha hızlı buluyor.** Keşif kanalları portu sabit 8000 duyuruyordu; gerçek port
  farklıysa (8000 meşgulse launcher başka port seçer) telefon yanlış porta gidip alt-ağ taramasına
  düşüyordu — ilk bağlanma saniyelerden ~70 saniyeye çıkıyordu.
- **mDNS kendi kendini toparlıyor.** Açılışta ağ hazır değilse yayın kurulumu bir kez patlayıp
  tamamen susuyordu; artık 30 saniyede bir yeniden deneniyor. (Aynı hata `pemf-gateway.local`
  yayınını da öldürüyordu.)
- **Sessizleşen ESP bobinine gerçek STOP gönderiliyor.** Telemetrisi kesilen bobin arayüzde "durdu"
  gösterilirken kendi süresi dolana kadar enerjili kalabiliyordu.

### Diğer

- Ayarlar ekranından kayıt yapıldığında **gönderilmeyen alanlar artık silinmiyor** (klinik adı her
  kayıtta kayboluyordu).
- Destek paketi, sır dosyalarının **türevlerini** de (geçici/bozuk kopyalar, anahtar dosyaları) dışarı
  çıkarmıyor.
- AI mikroservis profili kullanılıyorsa: boş/eksik formda **"%78 böbrek hastalığı" gibi uydurma sonuç
  üretilmiyor** — asgari klinik girdi kapısı iki taşımada da aynı.

---

## mobile 2.3.20 — 2026-08-22 (sürüm farkı artık sessiz değil)

**Etiket:** `launcher-v1.9.32` → `PEMF_Vet_Mobil-2.3.20.apk` (versionCode 27).

### Durdurma uyarısı artık ESKİ telefonlara da ulaşıyor (önce bu)

Telefon uygulaması cihazdan farklı bir sürümde kalabilir ve bu **kasıtlıdır**: Android'de
kurulumu işletim sistemi sorar, güncelleme zorunlu kılınamaz — bir tıbbi cihazın uzaktan acil
durdurmasını sürüm eşleşmesine bağlamak kabul edilemez.

Ama ölçüldü ki bu, güvenlik uyarılarının **sessizce kaybolmasına** yol açıyordu: 1.9.18'de
eklenen "donanım STOP'u doğrulanamadı" uyarısı yanıtta yeni bir **alan** olarak taşınıyordu ve
eski telefon o alanı tanımadığı için yutuyordu — bobinler hâlâ çalışırken ekranda düz "seans
durduruldu" yazıyordu. Yani düzeltme, en çok ihtiyacı olan kullanıcıya hiç ulaşmıyordu.

- **Uyarı artık yutulamayacak kanaldan gider.** Doğrulanamayan bobin varsa cihaz `409` döner;
  eski telefon 2xx dışı bir yanıtı yok sayamaz ve "donanım hâlâ çalışıyor olabilir — ACİL
  DURDUR'a basın" uyarısını gösterir. Yeni telefon ayrıca hangi bobinlerin teyitsiz kaldığını
  listeler. Mutlu yolda hiçbir şey değişmedi (yanlış alarm üretilmez).
- **Uyarı kaybolmayacak bir yere de düşer:** klinik bilgisayarının bildirim akışına ve günlüğe.
  Telefon eskiyse ya da ekranı kimse görmüyorsa bile uyarı birine ulaşır.

### Sürüm farkı görünür oldu

- Telefon ile cihaz sürümü farklıysa kapatılabilir bir bilgi bandı çıkar: *"Telefon 2.3.20 ·
  cihaz 1.9.18 — bağlantı ve acil durdurma normal çalışır; bazı düzeltmeler eksik olabilir."*
  **Bloklamaz**, girişi engellemez, seans sürerken gösterilmez.

### Diğer

- Şirket künyesindeki destek adresi güncellendi (eski adresin alan adı kayıtlı değildi).

---

## launcher 1.9.33 — 2026-08-21 (onarım artık 1,4 GB'ı yeniden indirmiyor)

**Etiket:** `launcher-v1.9.33` → `PEMFVetClient-Setup-1.9.33.exe` (sha `09728768a9f8`).

- **"Onarım" ile önbellek çelişkisi giderildi.** Kurulumu onarırken disk kapısı, cihazın
  **kurulu** paketlerini de korunacaklar listesine alıyor; onarım artık bağımlılık katmanını
  gereksiz yere silip 1,4 GB'ı yeniden indirtmiyor.
- **İptal edilen kurulum yarım dosya bırakmıyor** — iptalde o kurulumun parça dosyaları temizlenir.
- **Sade dil.** Arayüzdeki "client / launcher / core" gibi teknik adlar kaldırıldı; TR ve EN
  metinleri aynı anlamı veriyor ("Kurulumu onar", "Uygulama dosyaları", "Başlatıcı güncelleniyor…").

---

## mobile 2.3.19 — 2026-08-21 (yükleyici çalışan bobini görüyor)

**Etiket:** `mobil-v2.3.19` → `PEMF_Vet_Mobil-2.3.19.apk` (versionCode 26).

- **Güncelleme kapısı yalnız "açık seans" varlığına bakıyordu.** Seansı olmayan ama **çalışan**
  bobinlerde yükleyici ekranı alabiliyordu; artık bobin durumu da kapsanıyor.
- Gözlem notu düzeltmesi (hasta kimliğine bağlama) telefon arayüzünde de geçerli.

---

## launcher 1.9.32 — 2026-08-18 (bakım: güncelleme akışı uçtan uca doğrulama)

**Etiket:** `launcher-v1.9.32` → `PEMFVetClient-Setup-1.9.32.exe` (sha `64fd12eb2e8c`).

- **İşlevsel değişiklik yok.** Bu sürüm, web sitesinden yapılan temiz kurulum sonrası otomatik
  güncelleme zincirinin (manifest → sessiz self-update → yeniden başlatmada yeni sürüm) sahada
  kırılmadan çalıştığını uçtan uca doğrulamak için yayınlandı. 1.9.31'deki tüm düzeltmeler
  aynen geçerli.

---

## mobile 2.3.18 — 2026-08-18 (bakım: uygulama içi güncelleme doğrulama)

**Etiket:** `launcher-v1.9.32` → `PEMF_Vet_Mobil-2.3.18.apk` (sha `9593a194e135`, versionCode 25).

- **İşlevsel değişiklik yok.** Kurulu 2.3.17'nin uygulama içi güncelleme akışını (manifest
  `versionCode` karşılaştırması → indirme → boyut/sha doğrulaması → kurulum ekranı) canlı
  doğrulamak için yayınlandı. Güncelleme zorunlu değildir; "Atla" davranışı korunur.

---

## launcher 1.9.31 — 2026-08-18 (çıkış artık telefonunuzu düşürmüyor)

**Etiket:** `launcher-v1.9.31` → `PEMFVetClient-Setup-1.9.31.exe` (sha `58fc57034f33`).

- **"Çıkış" yalnız bu bilgisayarı kapatıyor.** Aynı hesabın telefondaki uygulaması ve varsa diğer
  bilgisayarlardaki oturumları da düşüyordu; klinikte çıkış yapmak hekimin telefonunu giriş ekranına
  atıyordu. (Aynı düzeltme telefon uygulamasına 2.3.17 ile geliyor.)
- **Yarıda kesilen güncelleme artık doğru geri alınıyor.** Dosya takasından sonra iptal/hata olursa
  eski sürüme dönülmüyordu — doğrulanmamış bir sürüm sağlık kapısı atlanarak yerinde kalabiliyordu.
- **Kurulum iptali, arka planda inen güncellemenin dosyasını silmiyor.** İptal, o an inmekte olan
  yabancı `.part` dosyasını da siliyordu; indirme baştan başlıyordu.
- **"Başlat" etiketi ve "Devam Et" düzeldi.** Kapı kapalıyken etiket pencere odağı/dil değişiminde
  eziliyordu; duraklatılmış güncellemede "Devam Et" ekranı geri getirmiyor ve her basış yeni bir
  indirme başlatıyordu.

---

## mobile 2.3.15 — 2026-08-14 ("cihaz bulunamadı" artık sebebini söylüyor)

**Etiket:** `launcher-v1.9.27` → `PEMF_Vet_Mobil-2.3.15.apk` (sha `f7951bd6978d`, versionCode 22).

Telefon ve cihaz aynı Wi-Fi'deyken, cihaz çalışırken, hiçbir ayar bozuk değilken uygulama
bağlanamıyordu. Sebep **modemde açık olan istemci izolasyonu** (AP Isolation) idi: bu ayar
cihazların internete çıkmasına izin verir ama **birbirlerini görmelerini engeller**. Ekranda
yalnızca "cihaz bulunamadı" yazıyordu; kullanıcının bunu ayarlardan bulmasının hiçbir yolu yoktu.

Artık uygulama **sebebi araştırıyor ve söylüyor.** Cihaza internet üzerinden ulaşılıyor, cihazın
bildirdiği yerel adres telefonla aynı ağda, ama o adrese doğrudan ulaşılamıyorsa — başka açıklaması
yoktur: paketler modemde durduruluyordur. Bu durumda rehber ne yapılacağını yazar (ayarı kapatın,
telefonu ana ağa alın ya da eşleştirme koduyla internet üzerinden bağlanın).

Aynı yöntemle ayırt edilen diğer durumlar: telefon **gerçekten başka bir ağda** (eşleştirme kodu
zaten doğru cevap) ve **cihaz çevrimdışı** (cihazın kendisine bakılmalı).

**Emin olunamıyorsa hiçbir şey söylenmez.** Üç kanıttan biri eksikse ekran susar. Yanlış teşhis
teşhissizlikten kötüdür: kullanıcıyı düzeltecek bir şeyi olmayan modem ayarlarında dolaştırır.

**Hasta güvenliği ve veri:** etkilenmez. Değişiklik yalnız bağlanamama durumundaki bilgilendirme
ekranını kapsar; bağlanma ve kimlik doğrulama yolları değişmedi.

---

## mobile 2.3.14 — 2026-08-14 (güncelleme indirmesi kaldığı yerden devam eder)

**Etiket:** `launcher-v1.9.27` → `PEMF_Vet_Mobil-2.3.14.apk` (sha `fee5e8817441`, versionCode 21).

Güncelleme indirmesi **%10'dayken uygulamayı kapatıp açınca sıfırdan başlıyordu** ve **başka bir
uygulamaya geçildiğinde ya da ekran kilitlendiğinde tamamlanıp tamamlanmadığı belirsizdi**. 128
MB'lık paketi mobil veriyle baştan indirmek hem zaman hem kota kaybıdır.

**Artık kaldığı yerden devam ediyor.** Devam noktası, diskteki yarım dosyanın kendi boyutundan
türetilir ve indirme `Range` başlığıyla oradan sürer. Bu, kaydedilmiş bir "devam jetonuna"
bağlanmaktan daha sağlamdır: uygulama çökerse ya da işletim sistemi onu öldürürse — devam etmenin
asıl gerekli olduğu an — jetonu diske yazma fırsatı zaten olmaz, ama dosya oradadır.

**Arka planda durmuyor.** İndirme arayüzden ayrı bir iş parçacığında yürür ve Android'de siz
başka bir uygulamaya geçtiğinizde ya da ekran kilitlendiğinde koşmaya devam eder; indirme
kendiliğinden tamamlanır. (Bu sürümün ilk denemesinde arka plana geçişte indirme
*duraklatılıyordu* — tamamlanacak bir işi durdurmak olduğu için kaldırıldı.) Sistem, belleğe
ihtiyaç duyup uygulamayı yine de kapatırsa indirme durur; o durumda yukarıdaki devam mekanizması
devreye girer ve sonraki açılışta kaldığı yerden sürer.

Kenar durumlar da kapatıldı: paket tam inmiş ama kurulum onayı verilmeden çıkılmışsa yeniden
indirilmez; başka bir sürümün yarım dosyası çöp sayılıp silinir; sunucunun devam isteğini yok
sayması hâlinde bozulan dosya boyut denetiminde yakalanır ve sonraki deneme temiz başlar; ağ
koparsa yarım dosya **bilerek korunur** ki tekrar denendiğinde baştan inmesin.

**Hasta güvenliği ve veri:** etkilenmez. Değişiklik yalnız güncelleme paketinin indirilmesini
kapsar; kurulumun güven çıpası değişmedi (Android, kurulu uygulamayla aynı anahtarla
imzalanmamış bir APK'yı kabul etmez).

---

## mobile 2.3.13 — 2026-08-13 (rehber artık gerçekten açılıyor)

**Etiket:** `launcher-v1.9.27` → `PEMF_Vet_Mobil-2.3.13.apk` (sha `9d9463e64fdf`, versionCode 20).

2.3.12'de eklenen eşleştirme rehberi **sahada hiç açılmadı**. Şerit "daha önce eşleşilmiş mi"
diye kayıtlı cihaz kimliğine bakıyor, yalnız kimlik **yoksa** rehberi açıyordu. Ama
`checkHealth` **her başarılı bağlantıda** kimliği saklar — LAN keşfi dahil. Yani aynı ağda bir
kez bağlanmış her kullanıcıda kimlik vardır ve koşul hiçbir zaman sağlanmaz. "Hiç eşleşilmemiş"
sanılan sinyal aslında "hiç bağlanmamış"tı.

Artık **tahmin yok**: çevrimdışıyken şerit her zaman tek bir eylemli kapı açar ve rehber iki
yolu da sunar — *"Yeniden Dene"* (aynı ağdaki geçici kopma, kod gerekmez) ve *kod girişi*
(farklı ağ). Hangisinin geçerli olduğunu kullanıcı bilir.

---

## mobile 2.3.12 — 2026-08-13 (farklı ağdaki ilk açılış için eşleştirme rehberi)

**Etiket:** `launcher-v1.9.27` → `PEMF_Vet_Mobil-2.3.12.apk` (sha `0cd353b58632`, versionCode 19).

Telefon ile cihaz **aynı ağda değilken** ilk açılışta bağlantı kurulamıyordu — bu beklenen bir
durum — ama kullanıcı ne olduğunu ve **ne yapacağını** öğrenemiyordu. Ekranda tek bir şerit
vardı ("Cihaza bağlanılamıyor — dokunup yeniden bağlan") ve dokunmak **her zaman** aynı keşfi
tekrarlıyordu. Oysa keşif merdiveninin uzaktan adımı **kayıtlı bir cihaz kimliği** ister ve ilk
açılışta o kimlik yoktur: o düğme sonsuza kadar başarısız olacak bir işi tekrarlıyordu.
Eşleştirme alanı vardı ama Ayarlar'ın içine gömülüydü.

Artık şerit iki durumu ayırır:

- **Hiç eşleşilmemişse** → *"Bağlanmak için DOKUNUN"* → rehber açılır: neden bağlanılamadığı,
  kodun cihazda **tam olarak nerede** yazdığı (Daha Fazla → Uzaktan Erişim Bağlantısı) ve giriş
  alanı aynı ekranda. Ayrıca "aynı Wi-Fi'ye bağlanırsanız kod **gerekmez**" ve "bir kez eşleşince
  bu ekran bir daha çıkmaz" bilgileri.
- **Daha önce eşleşilmişse** → eski davranış (yeniden dene); geçici kopmada kod istemek gereksiz.

Bağlanma kararı `services/pairing`e çıkarıldı ve **Ayarlar ekranı da onu kullanıyor** — güvenlik
değişmezleri (health + kimlik doğrulama, token takası) tek yerde. Web arayüzü **muaf**: onu
cihazın kendisi sunar, orada eşleştirme anlamsızdır.

---

## mobil 2.3.17 — 2026-08-17 (güncelleme artık doğrudan kuruluyor)

**Etiket:** `launcher-v1.9.31` → `PEMF_Vet_Mobil-2.3.17.apk` (sürüm kodu 24, sha `da65615f19d7`).

2.3.16'da indirme bittiğinde **paylaşım sayfası** açılıyordu — WhatsApp, Telegram, Drive… Oysa
kullanıcının APK'yı paylaşmaya değil kurmaya ihtiyacı var. Bu ekran hiçbir zaman kurulum
sunamazdı: Android'in paket yükleyicisi paylaşım listesinde yer almaz.

Artık **doğrudan kurulum ekranı** açılıyor. "Bilinmeyen kaynak" izni verilmemişse uygulama sizi
tek dokunuşla doğru ayar ekranına götürüyor ve ne yapmanız gerektiğini yazıyor.

**İndirilen paket bir daha indirilmiyor.** Kurulumu onaylamadan geri çıkarsanız, "Güncelle"ye
tekrar dokunduğunuzda 128 MB sıfırdan inmiyordu artık — dosya diskte hazırsa kurulum ekranı
anında açılıyor. (Önceki sürümde indirme bitince devam kaydı silindiği için hazır dosya
tanınmıyor ve paket baştan iniyordu.)

**Aynı paket iki kez indirilmiyor.** Açılış ekranında indirmeye başlayıp "Şimdilik devam et"
derseniz, uygulama içindeki bant aynı indirmeyi kaldığı yerden gösteriyor; ikinci bir indirme
başlatmıyor.

Ayrıca indirme ekranı artık yüzdenin yanında **kaç MB indiğini** de yazıyor ve kurulum
başlatıldığında ne beklendiğini söylüyor.

---

## mobil 2.3.16 — 2026-08-16 (uygulama güncelleme kontrolü bitmeden açılmıyor)

**Etiket:** `launcher-v1.9.30` → `PEMF_Vet_Mobil-2.3.16.apk` (sürüm kodu 23, sha `f99cc9966589`).

Masaüstü client'ta "Başlat" düğmesi artık güncelleme kontrolü bitmeden çıkmıyor (1.9.30).
Telefonda karşılığı yoktu: uygulama anında açılıyor, yeni sürüm ancak içerideki bant fark
edilirse görülüyordu.

Artık uygulama açılırken **önce güncelleme kontrol ediliyor**, sonra açılıyor. Yeni sürüm varsa
karşınıza güncelleme ekranı geliyor; indirme ve kurulum orada tek dokunuşla yapılıyor.

**Bekleme kısa ve her zaman kaçış yolu var.** Kontrol en fazla 7 saniye sürer; 2,5 saniye sonra
"Atla" çıkar. İnternet yoksa ya da kontrol yapılamıyorsa uygulama hemen açılır — cihaz
internetsiz de çalışır.

**Güncelleme zorunlu değil.** Android'de kurulumu telefonun kendisi sorar ve
reddedebilirsiniz; bu yüzden güncelleme ekranında her zaman "Şimdilik devam et" var — indirme
sürerken bile. Ertelerseniz uygulamayı bir dahaki açışınızda yeniden sorulur.

---

## launcher 1.9.30 — 2026-08-16 ("Başlat" güncelleme kontrolü bitmeden çıkmıyor)

**Etiket:** `launcher-v1.9.30` → `PEMFVetClient-Setup-1.9.30.exe` (sha `07daf9f51f5a`).

Uygulamayı açtığınızda "Başlat" düğmesi hemen çıkıyordu, ama güncelleme kontrolü arka planda
hâlâ sürüyordu. Tam "Başlat"a basacakken ekran güncellemeye geçebiliyordu — tıklamanız boşa
gidiyor, ne olduğu anlaşılmıyordu.

Artık "Başlat" kontrol bitene kadar **beklemede** kalıyor ve üstünde *"Güncelleme kontrol
ediliyor…"* yazıyor. Kontrol bitince açılıyor; güncelleme varsa kurulum yapılıp "Hazır!"a
dönüldüğünde açılıyor.

**Ekran donmuyor.** Kurulu cihazda "Hazır!" ekranı eskisi gibi anında çiziliyor; bekleyen
yalnızca düğme. İnternet yoksa ya da kontrol yapılamıyorsa düğme hemen açılıyor — cihaz
internetsiz de çalışır, bunun için beklemeye gerek yok.

---

## launcher 1.9.29 — 2026-08-16 (güncelleme: yüzde göstergesi + üç denetim düzeltmesi)

**Etiket:** `launcher-v1.9.29` → `PEMFVetClient-Setup-1.9.29.exe` (sha `eac5685204a3`).

**1. Arka planda inen güncellemenin yüzdesi artık görünüyor.** Yeni sürüm indirilirken yalnız
"arka planda indiriliyor" yazıyordu; ne kadar kaldığı hiçbir yerde yoktu. Artık bilgi notunun
içinde yüzde, ince bir ilerleme çubuğu, inen/toplam boyut ve hız akıyor. Kurulum ekranı
**açılmıyor** — uygulamayı kullanmaya devam edebilirsiniz.

**2. Sürekli açık kalan cihazlar da güncelleme alıyor.** Güncelleme kontrolü yalnız uygulama
açılırken yapılıyordu. Launcher penceresi siz çalışırken açık kaldığı için, günlerce kapatılmayan
bir klinik bilgisayarı yeni sürümü **hiç görmüyordu**. Artık altı saatte bir kontrol ediliyor.

⚠️ Bunun en önemli sonucu: **önemli bir güvenlik güncellemesi** yayınlandığında (üretici
tarafından zorunlu işaretlenen sürüm) sürekli açık cihazlara ulaşamıyordu. Artık ulaşıyor ve
ekranda ayrıca uyarı çıkıyor.

🔴 **Süren seans ASLA kesilmez.** Periyodik kontrol yalnız indirir ve bildirir; kurulum, siz
uygulamayı kapatıp açtığınızda yapılır. Seans sürüyorsa hiçbir şey yapılmaz.

**3. Disk dolmadan uyarı.** Güncelleme indirmeleri, yer yetmeyeceğini önceden söylemeden
başlıyordu; disk dolunca anlaşılmayan bir hatayla duruyordu. Artık indirmeden önce yer kontrol
ediliyor ve eski sürümlerden kalan kullanılmayan paketler temizleniyor.

**4. İki pencere aynı anda güncelleme yapamaz.** Uygulamanın ikinci bir penceresi açıksa ya da
siz "Onar" derken otomatik güncelleme başlarsa, ikisi aynı dosyalara yazabiliyordu. Artık
yalnızca biri çalışır; diğeri bekler.

---

## launcher 1.9.28 — 2026-08-15 (kaldır → yeniden kur artık temiz)

**Etiket:** `launcher-v1.9.28` → `PEMFVetClient-Setup-1.9.28.exe` (sha `78209912de66`).

**Hasta güvenliğini etkileyen sonuç — önce bu.** Client'ı **Windows Ayarlar ▸ Uygulamalar**'dan
kaldırıp aynı makineye yeniden kurmak, MQTT broker'ını sessizce çalışamaz hale getirebiliyordu.
Broker olmadan **6, 7 ve 8 numaralı bobinler ulaşılamaz** (onlar komutu MQTT ile alır); 1-5
numaralı bobinler seri porttan çalışmaya devam ettiği için cihaz **çalışıyor gibi görünür**.
Arızanın en kötü yanı buydu: yarısı çalışan bir cihaz, sebebi ekranda yazmayan bir sorun.

Sebep: kaldırma sırasında yalnızca ana servis süreci durduruluyordu. O süreç daha önce
beklenmedik şekilde kapanmışsa broker **sahipsiz** kalıyor ve durdurulamıyordu. Sahipsiz broker
1883 numaralı portu tuttuğu için yeni kurulum kendi broker'ını başlatamıyor, ayrıca kendi
dosyasını kilitlediği için kurulum dosyaları da tam silinemiyordu.

Kaldırma artık broker'ı ve tünel yardımcısını **adlarıyla** durduruyor — sahipsiz kalmış olsalar
bile. Sıra korunuyor: önce servis, sonra broker (ters sırada servis broker'ı yeniden başlatır).
Bobinlere acil durdurma komutu, eskisi gibi her şeyden **önce** gönderiliyor.

Uygulama içindeki "Kaldır" düğmesi bu temizliği zaten yapıyordu; sorun yalnızca Windows'un
kendi kaldırma yolundaydı. İki yol artık aynı.

---

## launcher 1.9.27 — 2026-08-12 (kararsız bağlantıda yanlış "internet yok")

**Etiket:** `launcher-v1.9.27` → `PEMFVetClient-Setup-1.9.27.exe` (sha `d46914fe85c5`).

Makinede internet **varken** client *"İnternet bağlantısı yok; kurulum için bağlantı gerekli"*
diyordu. Sebep: manifest çekimi **tek denemeydi**; anlık bir TCP kopması tüm açılışı
"internetsiz" ilan ediyordu.

Aynı makinede aynı anda ölçüldü (6 istek): `200 · 200 · KOPTU · KOPTU · 200 · 200` → **~%33**
anlık kopma. Kopmalar 0,5 sn'de oluyordu — zaman aşımı değil, **TCP sıfırlaması**; zayıf WiFi,
hotspot ya da ISP dalgalanmasında olağan, tam da klinik ortamı. Çalışan bir hatta kurulum
3'te 1 ihtimalle engelleniyordu.

Manifest çekimi artık geçici kopmada **3 kez** deneniyor (250 ms / 750 ms bekleme). **Kalıcı**
hatalar (HTTP 404, host pini reddi, politika sınırı) tekrarlanmaz — tekrarda aynı sonucu
verirler ve yalnızca kullanıcıyı bekletirlerdi. Duvar-saati tavanı 10 → 20 sn (çevrimdışı
makineyi geciktirmez: rota/DNS yokken bağlantı <1 sn'de düşer).

---

## launcher 1.9.26 · mobile 2.3.11 — 2026-08-12 (uzaktan erişim artık çalışıyor)

**Etiket:** `launcher-v1.9.26` → `PEMFVetClient-Setup-1.9.26.exe` (sha `dfc96f8b1ac9`) ·
`PEMF_Vet_Mobil-2.3.11.apk` (versionCode 18).

### Farklı ağdan uzaktan bağlanma hiç çalışmıyordu

**Siteden indirip kuran hiçbir klinikte** uzaktan erişim açılmıyordu. Backend'de Cloudflare
tüneli varsayılan kapalıdır (`PEMF_ENABLE_TUNNEL`) ve **launcher onu geçirmiyordu**; servis
kurulumu (`deploy/device.env`) geçiriyordu. Bu, hasta verisi şifrelemesinde (2026-08-08,
`PEMF_ENCRYPT_AT_REST`) yaşanan hatanın **birebir aynısı**: bayrak servis yolunda var,
launcher yolunda yok.

Sonuç zinciri: tünel hiç başlamıyor → cihazın `tunnel_url`i boş → cihaz buluta yine de
kaydoluyor (eşleştirme kodu görünüyor) → mobil, adresi olmayan kaydı eleyip
**"Bu kod/kimlikle eşleşen kayıtlı cihaz bulunamadı. Kodu kontrol edin."** diyor. Kullanıcı
doğru kodu defalarca giriyor ve sebebi anlayamıyor. Sahada ölçüldü: `/api/health` →
`pairingCode: MVPDDN`, `cloudRegistry: ok`, `tunnelUrl: None`.

Oysa mobil arayüz bunu açıkça vaat ediyordu: *"Farklı ağ → bir kez eşleştikten sonra cihazın
buluttaki güncel adresinden otomatik bağlanır."*

**Güvenlik:** tünel cihazı internete açar; backend tüneli açarken `PEMF_REQUIRE_AUTH`u
**zorla** etkinleştirir (fail-closed) → kimliksiz donanım/hasta erişimi mümkün değildir.
`cloudflared` pakete zaten bundle'lı. Kapatmak için `PEMF_ENABLE_TUNNEL=0` yeter (kod
değişikliği gerekmez).

### Hata mesajları artık ne yapılacağını söylüyor (mobil)

Çözümleme "kayıt yok" ile "kayıt var ama adresi yok"u aynı `null`a indiriyordu. Dört durum
ayrıldı: *kod yanlış* · *cihazda uzaktan erişim kapalı (kod doğru)* · *cihaz çevrimdışı* ·
*buluta ulaşılamadı*. Ayrıca iki paralel çözümleme yolundan biri kaldırıldı — keşif ile
elle-bağlanmanın farklı karar vermesi mümkündü.

---

## app 1.9.15 — 2026-08-15 (ses analizi: boş kayıt artık sonuç uydurmuyor)

**Etiket:** `client-app-v1.9.15` (base-app `782014a7ca14`, base `d7a392d99c4e`,
base-deps `2b29c7f806f9`).

**Ev sahibi modunda bildirilen iki sorun.**

**1. Sessiz/boş kayıt artık analiz edilmiyor.** Mikrofon ses almamışken bile ekranda bir ruh
hali sonucu çıkıyordu. Sebep şu: ses modelinin tanıdığı **on sınıfın hepsi bir kedi duygusu** —
"kedi sesi yok" diye bir cevabı yok. Bu yüzden sessizliğe bile mutlaka bir duygu atıyordu.
Ölçüldü: tam sessizlikte model %16,7 güven veriyor (rastgele tahmin %10), yani aslında hiçbir
şey söylemiyor; ekran bunu kesin bir bulgu gibi gösteriyordu. Artık kayıt seviyesi ölçülüyor ve
sessizse analiz yapılmıyor — "mikrofonu yaklaştırıp tekrar kaydedin" deniyor.

**2. Zayıf kayıtlarda sonucun güvenilmez olduğu yazıyor.** Kayıtta net bir kedi sesi
ayırt edilemediğinde sonuç yine gösteriliyor ama üstünde uyarı çıkıyor.

⚠️ **Neden "kedi sesi yok" denip tamamen reddedilmiyor:** eşik gerçek kayıtlarla ölçüldü ve
**gerçek bir ağrı kaydı da düşük güvendeydi** (%56), oda gürültüsü ise %60. Yani düz bir güven
eşiği gerçek ağrıyı eler, gürültüyü geçirirdi — ev sahibi kedisi gerçekten ağrıdayken "ses
algılanamadı" görürdü. Bu, düzeltilen sorundan daha kötü olurdu. Sessizlik kapısı sinyal
seviyesine bakar; gerçek kayıtların en sessizi bile eşiğin 19 dB üstündedir.

**3. Bilgisayarda ses kaydı çökmesi.** Tarayıcıda kayıt yapıp "Analiz Et" denince
"expo-file-system web'de yok" hatası veriyordu — masaüstünde canlı kayıt hiç analiz
edilemiyordu. Kayıt dosyası artık tarayıcıda da doğru okunuyor.

---

## app 1.9.14 — 2026-08-15 (cihaz artık açılıyor; kayıp doz kaydı; gözetimsiz bobin)

**Etiket:** `client-app-v1.9.14` (base-app `61389a6ac434`, base `a2becde42f04`,
base-deps `eee622a23be9`).

⚠️ **Bağımlılık güncellemesi YOK.** `base-deps` arşivi yeniden üretildiği için karması değişti
(boyut baytı baytına aynı: 1 462 119 667), ama içerdiği kütüphane kümesi aynıdır. Yine de
yayınlandı: "içerik herhalde aynıdır" varsayımıyla eski paketi göstermek yerine, sürümün
her katmanı TEK bir yapımdan gelsin diye. Alan kurulumu olmadığı için kimseye ek indirme
maliyeti çıkarmaz.

Katmanlı kurulumda cihazın bildirdiği `buildId` **base-app** karmasıdır; tek parça kurulumda
**base**. İkisi de yukarıda yazılıdır — sahadan gelen kimlik bu kayıtla eşleşebilsin.

Bu sürüm, 26 ajanlı bir senaryo kampanyasının bulduğu ve bağımsız doğrulamadan geçen
kusurları kapatır. Hepsi tıbbi kayıt ya da cihaz kullanılabilirliğiyle ilgilidir.

**⚠️ CİHAZ AÇILMAMA (en ağır).** At-rest anahtarı veritabanına uymadığında cihaz **hiç
açılmıyordu**. Üç ayrı halka birlikte kilitleniyordu: (1) bozuk dosyayı kenara alan kurtarma,
dosya kilidi yüzünden başarısız oluyor ve "kurtarılamadı" deyip açılışı durduruyordu;
(2) kurtarma dosyayı kenara alsa bile veri göçü onu geri kopyalıyordu; (3) göç, bu makinede
çözülemeyen bir anahtarı hedefe yazarak çalışan bir kurulumu açılamaz hâle getirebiliyordu.
Üçü de kapatıldı; cihaz artık temiz bir veritabanıyla açılır ve okunamayan dosya
**silinmeden** kenarda durur.

**⚠️ UYGULANAN DOZ KAYDI KAYBOLUYORDU.** Seans sürerken elektrik kesilir ya da servis
kapanırsa, yeniden açılışta kayıt "tedavi sürüyor" hâlinde kalıyor; bitiş, süre ve hangi
bobinin ne kadar çalıştığı **hiç yazılmıyordu**. Artık açılışta kapatılıyor ve süre "şimdi"den
değil son telemetri kanıtından türetiliyor — cihaz üç gün kapalı kaldıysa kayıt "üç günlük
tedavi" demez.

**⚠️ SÜRE VERİLMEYEN BOBİN GÜNLERCE SÜRÜYORDU.** Kontrol panelinden süre belirtmeden
başlatılan bir bobinin yazılım sınırı ~6,9 güne düşüyordu (ölçüldü). Artık klinik sınıra
(120 dk) düşer — AI Pro'nun zaten kullandığı sınırın aynısı. Negatif süre de sessizce kabul
ediliyordu; artık reddediliyor.

**Acil durdurma geçmişte görünüyor.** Acil durdurmayla biten seans, normal tamamlanan bir
seanstan ayırt edilemiyordu (üçü de "tamamlandı" yazıyordu) ve gösterge tablosu bunları
saymıyordu. Artık ayrı işaretleniyor ve KPI'da görünüyor — "bu hastada acil durdurma yaşandı
mı?" sorusu cevaplanabilir.

**PDF raporda hasta adı kayboluyordu.** Aynı seans CSV ve JSON'da doğru adı verirken PDF
"Bilinmiyor" yazıyordu; hasta raporunda ise başlıkta ad varken tabloda "Belirtilmemiş" —
belge kendi içinde çelişiyordu. İkisi de düzeltildi.

**Hasta kayıtları göçte taşınmıyordu.** Eski kullanıcı klasöründen makine geneline geçişte
seans geçmişi taşınıyor, hasta kayıtları taşınmıyordu (yanlış dosya adı aranıyordu). Ayrıca
felaket kurtarma yönergesi, yedeği uygulamanın hiç açmadığı bir adla geri yüklemeyi
söylüyordu — yönergeyi izleyen klinik "geri yükledim" sanıp boş liste görürdü.

**Denetim izi seansa bağlanabiliyor.** Seans mührü aynı saniyede başlayan iki seansta
çakışabiliyordu ve denetim kaydı hangi seansa ait belli olmuyordu.

**Hasta güvenliği ve veri:** bu sürümde bobin sürme, frekans/doluluk sınırları ve acil
durdurmanın çalışma biçimi DEĞİŞMEDİ. Değişenler kayıt bütünlüğü, kurtarma ve gözetimsiz
çalışma süresidir.

---

## app 1.9.13 · mobile 2.3.10 — 2026-08-12 (ses analizi anında; çoklu modül)

**Etiketler:** `client-app-v1.9.13` (base-app `d300d38e008b`, base `ad4fc3d69cce`,
**base-deps `d43942b3e78b` — bu sürümde DEĞİŞTİ**, frozen backend yeniden derlendi) ·
APK `launcher-v1.9.25` → `PEMF_Vet_Mobil-2.3.10.apk` (`519dabb298ec`, versionCode 17).

### Ses analizi artık anında sonuç veriyor

Kedi-sesi modeli, diğerlerinden belirgin şekilde geç sonuç veriyordu. Ölçüldü: maliyet
**modelde değil**, ses hattının numba-JIT ön-işlemesinde (`librosa`). Ses, JIT kullanan tek
model; diğerleri saf ONNX.

    librosa.load (ilk)   36,7 sn   ← baskın maliyet
    trim (ilk)            6,5 sn
    ONNX yükle+çalıştır   0,17 sn

Kıyas (aynı koşullar): böbrek CT **0,6 sn** — modeli 3 kat BÜYÜK (42,7 MB) olduğu hâlde.

Maliyet artık **açılışta, arka planda** ödeniyor (`PEMF_AI_WARMUP=0` ile kapatılabilir).
Kullanıcının gördüğü ilk analiz süresi:

| | önce | sonra |
|---|---|---|
| yeni kurulum | 38,2 sn | **0,28 sn** |
| sonraki açılışlar | 4,7 sn | **0,27 sn** |

Model çıktısına etkisi yoktur — yalnız aynı kod yolu bir kez ısıtılır. Teşhis için
`AI ısıtma tamam (ses ön-işleme): X sn` loglanır.

### AI Hub'da birden fazla modül aynı anda açık

Veteriner ve Araştırma modlarında ikinci bir modüle dokunulduğunda **birincinin ayrıntısı
kapanıyordu**, geriye yalnız başlığı kalıyordu. Akış karşılaştırmalı olduğu için bu, hekimi
sürekli ileri-geri dokunmaya zorluyordu. Artık istenen kadar modül açık kalır ve sayfa aşağı
doğru uzar; açık bir modüle dokunmak yalnız onu kapatır. Hasta/profil değişince hepsi kapanır.

---

## app 1.9.12 · mobile 2.3.9 — 2026-08-12 (AI analizinde zaman aşımı düzeltmesi)

**Etiketler:** `client-app-v1.9.12` (base-app sha `564d8e9c4cd1`, base sha `729234cef212`) ·
APK `launcher-v1.9.25` → `PEMF_Vet_Mobil-2.3.9.apk` (sha `0e22d81b1133`, versionCode 16).
`base-deps.zip` **değişmedi** (sha `dea13abcc80b`) → manifest onu 1.9.11 sürümünden kullanmaya
devam eder; sıradan güncellemede yalnız 71 MB'lık uygulama katmanı iner.

### Düzeltilen

- **Peş peşe başlatılan analizlerde ses analizi düşüyordu.** Saha bildirimi: ev kullanıcısı
  profilinde fps + hastalık + ses analizleri arka arkaya başlatıldı; ilk ikisi sonuç döndürdü,
  ses analizi `AbortError: signal is aborted without reason` verdi — üstelik bu ham tarayıcı
  metni kullanıcıya olduğu gibi gösterildi. Hemen ardından ses analizi **tek başına** denendiğinde
  anında sonuçlandı.

  Sebep: kedi-sesi modeli ilk çağrıda numba/librosa JIT derlemesi yapıyor (ölçüm: tek başına
  **28,0 sn**, sonraki çağrı **0,06 sn**). Üç analiz aynı anda koşunca CPU çekişmesi bu süreyi,
  arayüzde **çağrı yerine elle yazılmış** 60 saniyelik sınırın üstüne çıkarıyordu. Sunucu kuyruğu
  suçlu değildi: `ai_queue_gate` yalnız `PEMF_TIER_ENFORCED` açıkken çalışır, varsayılan kapalıdır.

  ⚠️ Aynı arıza 2026-08-06'da `/ai/disease` için bildirilmiş ve düzeltilmişti — ama yalnız
  `apiPost` yolunda; ham `fetch` kullanan 10 modül atlanmıştı. Bu yüzden hata ses modülünde
  aynen tekrarladı. **Kısmi düzeltme, düzeltilmemiş demektir**: sınır artık tüm AI çağrılarında
  tek kaynaktan (120 sn) geliyor ve yapısal bir test elle yazılmış sınırı yasaklıyor.

- **İptal mesajı anlaşılır oldu.** Zaman aşımı ile ağ hatası ayrı şeylerdir: ilkinde tekrar
  denemek işe yarar (model artık bellekte), ikincisinde yaramaz. Kullanıcı artık ne olduğunu ve
  ne yapacağını okuyor. `landmark` ve `RNA` modüllerindeki satır-içi kontroller de tek kaynağa
  devredildi — eski metinleri "bağlantıyı kontrol edin" diyordu, oysa zaman aşımında bağlantı
  sağlamdır.

- **Canlı kamera döngülerine dokunulmadı** (15/25 sn). Oraya uzun bir sınır koymak görüntü
  akışını kilitlerdi; istisna artık kodda açıkça işaretli ve test onu da sınırlıyor.

### Not

Sürüm numarası 2.3.8 değil **2.3.9**: 2.3.8 zaten yayındaydı, aynı numarayla farklı içerik
dağıtmamak için yükseltildi (Android aynı `versionCode` ile güncellemeyi kabul etmez).

---

## app 1.9.6 · launcher 1.9.16 · mobile 2.3.8 — 2026-08-10

2026-08-09 üretime-hazırlık denetiminin **Tier 0-3** düzeltmeleri. Tek bir sürümde toplandı;
öncesindeki her şey `1.9.5 / 1.9.15 / 2.3.7`tir.

### Hasta güvenliği ve tıbbi kayıt

- **Bobin 1-5'te sıcaklık ölçümü olmadığı arayüzde AÇIKÇA yazıyor** ("ölçüm yok" + ekran okuyucu
  "termal durdurma uygulanmaz"). `firmware/README`nin "termal koruma sensör/ESP tarafındadır"
  iddiası kaldırıldı — o iddia 8 bobinin 5'i için doğru değildi. ⚠️ Koruma **eklenmedi**; gerçek
  çözüm donanımdadır (sensör + STM telemetrisi + firmware kesmesi).
- **Uygulanmayan mT dozu hasta raporundan kaldırıldı.** Operatörün girdiği yoğunluk hiçbir
  taşımaya girmiyor (ne STM paketi ne ESP komutu); yine de hasta sahibine giden PDF'te
  "Yoğunluk: X mT" basılıyordu. Klinik-içi tablolarda etiket "Ayarlanan (mT)" oldu. Veri silinmedi.
- **Bobinler her `kill` öncesi durdurulur** değişmezi korundu ve testle kilitlendi.
- **Kayıtsız seans reddedilir**: tıbbi kayıt DB'si açılamıyorsa `/api/session/start` 503 döner
  (`/api/health → dbReady` aynı kaynaktan).

### Kimlik ve veri

- **Operatör kimliği sunucu tarafında**: PIN doğrulaması artık jeton üretir; kayıtlar jetondan
  yazılır. Kanıtsız beyan **kayıtlı** bir hekimi taklit edemez (kayıt sahipsiz yazılır, tedavi
  ENGELLENMEZ). Cihazdan çıkarılan operatörün jetonu anında ölür.
- **Geri dönüşsüz PII maskelemesi operatör onayına bağlandı**; süre arayüzden yönetilir ve ortam
  değişkenini ezer. Onaysız hiçbir kayıt maskelenmez.
- **Cihaz taşıma gerçekten tüm veriyi taşır** (11 tablonun 2'si değil, 8 tablo) ve `patient_id`
  yeniden eşlenir — aksi hâlde sonuç *sessizce* yanlış olabiliyordu.

### Güncelleme ve dağıtım

- **Tek güncelleme kanalı.** Eski Inno/`exe` OTA kanalı **varsayılan kapalı**
  (`PEMF_LEGACY_EXE_UPDATE=1` ile açılır). O kanalın `latest.json`ı yayında değil (404) ve
  `previousStable` hiç dolmadığı için `/api/update/rollback` zaten çalışmıyordu; asıl risk ise
  kanalın yeniden yayına girmesi hâlinde launcher'ın yönettiği kurulumun yanına **ikinci bir
  backend + ikinci veri kökü** kurulması — yani **ikiye bölünmüş hasta veritabanı**. Mobil
  arayüzdeki "cihaz yazılımını güncelle" düğmesi de kaldırıldı.
- **Geri çağırma**: `manifest.json → min_supported_version`. `rollout: 0` yalnız *yeni* dağıtımı
  durdurur; geri çağırma **sahadaki** kurulumları güncellemeye zorlar. Sürümünü söyleyemeyen
  kurulum fail-safe olarak kapsama girer.
- **Filo envanteri**: cihaz heartbeat'i artık `app_version` / `launcher_version` / `base_sha` /
  `at_rest_encrypted` taşır (`supabase/upsert_device_envanter.sql`). RPC geriye uyumlu.
- **Disk alanı kontrolü + ölü önbellek temizliği** — kurulum 1,2 GB indirdikten sonra `os error 112`
  ile ölmüyor.
- **RUNBOOK'un "kötü güncelleme" satırı düzeltildi** — var olmayan `DEPLOYMENT.md`ye ve hiçbir şey
  yapmayan bir komuta yönlendiriyordu.

### Sürüm görünürlüğü

- **`X-API-Version` artık doğru sürümü söylüyor.** `1.4.1` raporluyordu; o `frontendOta`
  kanalının numarasıydı, backend ise `1.9.5`. Sıra düzeltildi: `VERSION` → `frontend_version.json`.
- **`X-Build-Id` + `/api/health → buildId`**: kurulu paketin sha256'sının ilk 12 hanesi. Aynı sürüm
  numarası farklı paket içeriği çalıştırabilir; olay kaydında "hangi ikili" sorusunu bu cevaplar.
- **`/api/health` sürümü bildiriyor** — teşhisin ilk durağı sürümü hiç söylemiyordu.

### Kalite kapıları

- **AI altın-değer testleri** (CKD / em_fantom / em_petri / em_kedi / RNA): üretim ön-işleyicileri
  sklearn **1.8.0** ile serileştirilmiş, runtime **1.7.2** sabitli; sklearn her yüklemede *"may
  lead to invalid results"* diyordu ve süit yeşil kalıyordu. Artık sabit girdi → beklenen çıktı
  kilitli; %1'lik bir ölçek kayması testi kırıyor (mutasyonla doğrulandı).
- **Model eseri sürüm ratchet'i**: yeni bir sürüm uyuşmazlığı sessizce giremez.
- **Üçüncü taraf lisans yüzeyi kapısı**: yeni bir kopyleft bağımlılık sessizce giremez
  (bkz. `docs/AGPL-KARARI.md`).

---

## Yayınlanmış sürümler

> Bu dosya **2026-08-10**'da başlatıldı. Aşağıdaki liste yayın etiketlerinden ve
> `pemf-app-packages/manifest.json`dan doğrulanmıştır; sürüm başına ayrıntılı değişiklik dökümü
> için o tarihten öncesi **git geçmişindedir** (`git log --oneline`). Geriye dönük ayrıntı
> uydurulmamıştır.

### app paketi

| Sürüm | Etiket | Tarih | base.zip sha (12) | app / deps sha (12) | rollout |
|---|---|---|---|---|---|
| 1.9.11 | `client-app-v1.9.11` | 2026-08-11 | `809756decce4` | `c58ae59968dd` / `dea13abcc80b` | 100 |
| 1.9.10 | `client-app-v1.9.10` | 2026-08-11 | `0756286b6ce7` | `db362caeb65a` / `fc25abb00531` | ⚠️ ÖZYİNELEME — KULLANMAYIN |
| 1.9.9 | `client-app-v1.9.9` | 2026-08-11 | `81e977ccad9d` | `048d4aabb6bb` / `b789896c2aa4` | ⚠️ ÖZYİNELEME — KULLANMAYIN |
| 1.9.8 | `client-app-v1.9.8` | 2026-08-10 | `3fd701051e7c` | `38446e281313` / `82986dfd7215` | 100 |
| 1.9.7 | `client-app-v1.9.7` | 2026-08-10 | `4c580cfc0489` | — | 100 |
| 1.9.6 | `client-app-v1.9.6` | 2026-08-10 | `194a3a07fd54` | `0a9f209a704b` / `fdc0b02b73aa` | 100 |
| 1.8.0 | `client-app-v1.8.0` | 2026-07-13 | `90cf004f9fa1` | `42b88557fe00` / `69cf344d0fc6` | 100 |

> ⚠️ **1.9.8'de bağımlılık katmanı DEĞİŞTİ** (`inference_cat_organ` çekirdeğe girdi) → bu sürüme
> **güncelleyen** kurulum ~1,46 GB indirir. Katman ayrımının amacı sıradan sürümlerde ~71 MB'da
> kalmaktı; burada bilerek ödenen tek seferlik bedeldir ve karşılığında `home.zip` 209 MB küçüldü.

> ⚠️ **1.9.6'da bağımlılık katmanı da değişti.** `_internal/VERSION` app katmanına taşındığı için
> `base-deps.zip` yenilendi → bu sürümü **güncelleyen** bir kurulum ~1,19 GB indirir. Sonraki
> sıradan yayınlar yine ~71 MB olacaktır. (Sahada henüz kurulum olmadığı için bu sürümde kimse
> bu bedeli ödemedi; yeni kurulumlar zaten tüm paketi indirir.)
>
> ⚠️ **`rollout` BİR SONRAKİ YAYINA TAŞINIR.** `make_manifest.py`'ye `--rollout` verilmezse
> manifest'teki mevcut değer korunur. Yani düşürülmüş bir rollout unutulursa, sonraki sürüm de
> sessizce o oranda dağıtılır. Kademeyi düşürdükten sonra **açmayı unutmayın** — ya da her
> yayında `--rollout`'u AÇIKÇA verin.
>
> ⚠️ **Manifest'in adresi sabittir:** istemciler onu daima
> `releases/download/client-app-v1.8.0/manifest.json` adresinden okur (launcher'da derlenmiş
> sabit). Yeni paketler yeni bir etikete yüklenir; **manifest her zaman o eski etikete**
> `--clobber` ile yazılır. Yeni etikete koymak yayını görünmez kılar.
>
> Kademeli açma (**sahada kurulum varken** anlamlıdır): `--rollout 10` → izle → `--rollout 50` →
> `--rollout 100`, her adımda manifest'i aynı adrese yeniden yükleyerek. `rollout` yalnız
> **mevcut** kurulumların güncellenmesini kısar; **yeni kurulum** her hâlükârda en son paketi alır
> (`install_profiles` rollout'a bakmaz). Dolayısıyla henüz dağıtım yapılmamışken kademelendirmenin
> koruduğu kimse yoktur.

### launcher (PEMF Vet Client)

| Sürüm | Etiket | Tarih | Installer sha (12) |
|---|---|---|---|
| 1.9.25 | `launcher-v1.9.25` | 2026-08-11 | `92467b5483ee` |
| 1.9.24 | `launcher-v1.9.24` | 2026-08-11 | `d1b3ca26efa4` |
| 1.9.23 | `launcher-v1.9.23` | 2026-08-11 | `f0fa6ef4f81b` |
| 1.9.22 | `launcher-v1.9.22` | 2026-08-11 | `57d20065fe0a` (yayinda; manifest 1.9.23'e isaret eder) |
| 1.9.21 | `launcher-v1.9.21` | 2026-08-11 | `07a89b8ab57a` |
| 1.9.20 | `launcher-v1.9.20` | 2026-08-11 | `625d896fad51` |
| 1.9.19 | `launcher-v1.9.19` | 2026-08-10 | `65093583277a` |
| 1.9.18 | `launcher-v1.9.18` | 2026-08-10 | `8bdc6252b235` |
| 1.9.17 | `launcher-v1.9.17` | 2026-08-10 | `8070971e5180` |
| 1.9.16 | `launcher-v1.9.16` | 2026-08-10 | `04a39ee87701` |
| 1.9.15 | `launcher-v1.9.15` | 2026-08-08 | `cca09c179fa0` |
| 1.9.14 | `launcher-v1.9.14` | 2026-08-08 | — |
| 1.9.13 | `launcher-v1.9.13` | 2026-08-08 | — |
| 1.9.12 | `launcher-v1.9.12` | 2026-08-08 | — |
| 1.9.11 | `launcher-v1.9.11` | 2026-08-08 | — |
| 1.9.10 | `launcher-v1.9.10` | 2026-08-07 | — |
| 1.9.9 | `launcher-v1.9.9` | 2026-08-06 | — |
| 1.9.8 | `launcher-v1.9.8` | 2026-08-03 | — |
| 1.9.7 | `launcher-v1.9.7` | 2026-08-01 | — |
| 1.9.6 | `launcher-v1.9.6` | 2026-08-01 | — |
| 1.9.5 | `launcher-v1.9.5` | 2026-07-29 | — |
| 1.9.4 | `launcher-v1.9.4` | 2026-07-29 | — |
| 1.9.3 | `launcher-v1.9.3` | 2026-07-29 | — |
| 1.9.2 | `launcher-v1.9.2` | 2026-07-26 | — |
| 1.9.1 | `launcher-v1.9.1` | 2026-07-26 | — |
| 1.9.0 | `launcher-v1.9.0` | 2026-07-26 | — |
| 1.8.0 | `launcher-v1.8.0` | 2026-07-13 | — |

### mobile (Android)

| Sürüm | versionCode | Yayın | APK sha (12) |
|---|---|---|---|
| 2.3.8 | 15 | `launcher-v1.9.16` | `d6be2a3166fc` |
| 2.3.7 | 14 | `launcher-v1.9.15` | `7078cf6b36a3` |

### backend (`VERSION`)

| Sürüm | Not |
|---|---|
| 1.9.6 | app paketi içinde dağıtılır; ayrı bir yayın etiketi yoktur |
| 1.9.5 | app paketi içinde dağıtılır; ayrı bir yayın etiketi yoktur |

---

## launcher 1.9.25 — 2026-08-11 (Denetim Masası boyutu gerçeği yansıtıyor)

**Sahip bildirimi:** *"Denetim Masası'nda uygulamanın boyutu hep 11 MB görünüyor, profil
kurulumlarından sonra bile."*

**Sebep.** NSIS `EstimatedSize`i **kurulum anında** `$INSTDIR`den hesaplar. O anda dizinde yalnız
launcher vardır (~11 MB); çalışma zamanı (~2 GB) ve profil modelleri (0,3-1,6 GB) **sonradan**
client tarafından indirilir ve kayıt bir daha güncellenmez. Kullanıcı diskte yer ararken
gigabaytlık bir uygulamayı 11 MB sanıyor — yanlış karar verdiren bir sayı.

**Düzeltme.** Kurulum / onarım / güncelleme bitince gerçek boyut yazılır. Kayıt per-user
kurulumda HKCU'dadır → **yönetici gerekmez**. Önbellek de sayılır: indirilen paketler gerçekten
yer kaplar ve kaldırma onları da siler, yani "kaldırırsam ne kadar yer açılır"ın doğru cevabı budur.

⚠️ Boş/okunamayan kökte kayda **DOKUNULMAZ** — "0 MB" yazmak, eski 11 MB'ı bırakmaktan daha
kötü olurdu.

**Doğrulama:** 7 test; gerçek kayıt üzerinde uçtan uca ölçüldü (11 MB → 500 MB). Mutasyon:
boyut toplamayı kaldırma ve boş kökte yazma yakalandı.
⚠️ Kapsam notu: "junction izlenmesin" mutasyonu yakalanmadı — sebebi test zayıflığı DEĞİL,
Rust'ta `is_dir()` ile `is_symlink()`in birbirini dışlaması (mutasyon davranışı değiştirmiyor).
Koruma savunma amaçlı bırakıldı.
---

## launcher 1.9.24 — 2026-08-11 (güvenlik duvarı uyarısı: yanlış alarm bitti)

**Sahip bildirimi:** *"eskiden buna gerek olmadan buluyordu, şart mı bu?"*

Şart değildi. Uyarı **yanlış alarmdı** ve kullanıcıyı gereksiz yönetici istemine itiyordu.
İki ayrı kusur vardı:

1. **Windows'un KENDİ izni sayılmıyordu.** Bir program ilk kez dinlemeye başlayınca Windows
   "erişime izin ver" penceresi gösterir; kullanıcı onaylarsa **program kapsamlı bir Allow
   kuralı** oluşur ve bağlantı onunla çalışır. Denetim yalnız kendi adlandırılmış kurallarımıza
   baktığı için, izin zaten varken "engelli" diyordu. (Sahibin makinesinde ölçüldü: Windows'un
   kuralı vardı ve doğru kurulum yolunu gösteriyordu.)
2. **"Kural yok" ile "açıkça engellenmiş" AYNI sayılıyordu** ve kontrol HER AÇILIŞTA, backend
   daha bir kez bile dinlemeden koşuyordu. Yeni kurulumda kural olmaması NORMALDİR — Windows
   henüz penceresini göstermemiştir. Kullanıcı, işletim sisteminin on saniye sonra zaten
   halledeceği bir şey için UAC istemine itiliyordu.

**Yeni davranış — önce Windows'a şans ver:**

| Durum | Uyarı |
|---|---|
| Açıkça engellenmiş (etkin **Block** kuralı) | Her zaman — engel kalıcıdır, yükseltilmiş düzeltme tek çözüm |
| Kural yok | Açılışta **susar**; yalnız **Başlat'tan sonra** uyarır (Windows fırsatını kullandı) |
| İzin var (bizimki **veya Windows'unki**) | Hiç uyarmaz |

Mesaj da duruma göre ayrışır ("Windows engelliyor" ↔ "izin yok").

⚠️ Tam sessiz otomatik YAPILAMAZ: kural eklemek yönetici ister; launcher bilerek yükseltilmemiş
çalışır (sessiz oto-güncelleme UAC'siz olsun diye) ve kurulum `currentUser` kipindedir. Açılışta
otomatik UAC çıkarmak daha kötü olurdu — çoğu kullanıcıda hiç gerekmiyor.

**Doğrulama:** 3 mutasyon yakalandı (Windows iznini yok sayma, iki durumu birleştirme, Block
tespitini kaldırma); cargo 234 ✓.
---

## app 1.9.11 — 2026-08-11 (⚠️ ACİL: veri göçünde SONSUZ ÖZYİNELEME)

**1.9.9 ve 1.9.10 bu kusuru TAŞIYOR. Bu sürüme geçin.**

### Kusur

Veri göçü (`%APPDATA%` → makine-geneli kök) `get_app_data_directory()` İÇİNDEN çağrılır.
1.9.9'da eklenen "hedefin anahtarıyla açılıyor mu?" kontrolü oradan sır katmanına gidiyordu:

```
get_app_data_directory → _kullanicidan_makineye_gocur → (kontrol)
  → get_sqlcipher_key → secrets_manager.get_secret → _load → _data_dir
  → get_app_data_directory → …
```

Eski `%APPDATA%\PEMF_GUI` verisi olan bir kurulumda backend **açılışta sonsuz özyinelemeye**
girip belleği tüketiyordu. Geliştirme makinesinde bu, commit limitini doldurup Windows'u
**BSOD**'a (`0x10E`) götürdü; klinikte karşılığı cihazın hiç açılmamasıdır. Yığın izi
`faulthandler` ile kanıtlandı.

**Düzeltme:** göç yolu artık sır/kripto katmanına **hiç dokunmuyor**. Karar saf dosya
okumasıyla verilir: düz-metin SQLite mi, değilse kaynak ile hedefin **ham** (DPAPI-sarılı)
anahtar değerleri eşit mi. Çözme/türetme yok. `tests/test_anahtar_uyusmazligi_karantina.py`
bu değişmezi kilitler — göç yolu sır katmanına dokunursa test patlar.

### At-rest anahtarı artık tıbbi kayıtla BİRLİKTE taşınıyor

Şifreli kurulumlarda göç hiç çalışmıyordu: anahtar `pemf_secrets.json`da durur, o dosya ise
`device_id`/`pairing_code` taşıdığı için bütün olarak göçemez. Sonuç, vardiyalı klinikte
ikinci hesapla açan veterinerin hâlâ **"boş klinik"** görmesiydi.

Artık **yalnız `auto.sqlcipher_key`** taşınıyor; cihaz kimliğine dokunulmuyor. Değer DPAPI
`LOCAL_MACHINE` kapsamında sarılı olduğu için ham hâliyle kopyalanır (aynı makinede geçerli).

⚠️ **Hedefte anahtar VARSA asla ezilmez** — hedefin kendi verisi onunla şifreli olabilir;
üzerine yazmak çalışan bir kurulumu okunamaz hâle getirirdi. Mutasyonla doğrulandı.

**Doğrulama:** pytest 926 ✓; 3 mutasyon (anahtarı ezme / cihaz kimliğini taşıma / şifreli
DB'yi koşulsuz taşıma) yakalandı. **Gerçek frozen build** üzerinde uçtan uca: eski kökte
DPAPI-sarılı anahtar + gerçek şifreli DB → anahtar taşındı, DB kopyalandı ve hedefte
**çözülebildi** (backend şema göçüne kadar ilerledi).

---

## app 1.9.10 · launcher 1.9.22 — 2026-08-11 (kesinti/eşzamanlılık denetimi)

Sahip isteğiyle **kullanıcı gözünden** yaşam-döngüsü denetimi: "kurulum esnasında kapanma,
güncelleme esnasında kapanma — hepsi olabilir". Üç gerçek kusur çıktı. Kesintiler süreç
öldürülerek değil, **öldürülmüş olsaydı diskte ne kalırdı** durumu birebir kurulup bir sonraki
AÇILIŞIN toparlayıp toparlamadığı ölçülerek test edildi.

### 1. Güncellemenin ortasında kapanma → cihaz "kurulu değil" oluyordu

Takas iki `rename` yapar (`runtime`→`runtime.old`, `runtime.new`→`runtime`). **İkisinin
arasında** kapanma olursa diskte `runtime` HİÇ YOKTUR; çalışan sürüm `runtime.old`da sağlamdır.
Ama `detect_environment` kurulumu `runtime/PEMF_Backend/…` ile anlar → client "kurulu değil"
der, kullanıcı sıfırdan kurulum ekranı görür ve sağlam yedek sessizce yetim kalır.

Açılışta `flow::yarim_takasi_kurtar` eklendi. **Sıra: önce `runtime.old`** — o, sağlık kapısını
geçmiş, çalıştığı KANITLANMIŞ sürümdür; `runtime.new` hiç doğrulanmadı. Yarıda kalanı
"tamamlamak" doğrulanmamış bir sürümü sessizce canlıya almak olurdu. Güncelleme sonraki
açılışta yeniden denenir (paketler önbellekte).

### 2. İki client aynı anda kurulum yapabiliyordu

Tek-örnek koruması yok; kullanıcı simgeye iki kez tıklayabilir. İki client aynı `runtime.new`e
açar, birbirinin dosyalarını ezer, takası yarış hâlinde yapar ve kurulum öncesi `taskkill` ile
**diğerinin backend'ini — muhtemelen SÜREN BİR SEANSI** öldürür.

Kilit, işletim sisteminin dosya kilidine dayanır (süreç ölürse Windows tutamağı kendi kapatır →
**bayat kilit imkânsız**; PID+canlılık sorgusu, çöken kurulumdan sonra kliniği kalıcı kilitli
bırakabilirdi). Kurulum/onarım/kaldırmaya bağlandı.
⚠️ Kilit dosyası kurulum kökünün **DIŞINDA** (geçici dizin): kökün içinde olsaydı `remove_install`
açık tutamak yüzünden kökü silemez, kaldırma yarım kalırdı.

### 3. Bozuk indirmede kendini toparlamıyordu

`ensure_package`'in 6-denemeli retry'ı yalnız AĞ hatalarını kapsıyordu; "indi ama sha tutmadı"
hâli döngünün dışındaydı → kullanıcı elle tekrar denemek zorundaydı ve mesaj ("değiştirilmiş")
gereksiz yere güvenlik olayı ima ediyordu. Artık sha uyuşmazlığında **sıfırdan bir kez daha**
inilir (`.part` de silinir); ikinci kez de tutmazsa hata gerçektir ve yükselir — doğrulama
ZAYIFLATILMADI.
⚠️ `.part` adı artık TEK KAYNAK (`net::part_path`): `flow` kendi kopyasını tutuyordu ve kısa-sha
kolunda FARKLI ad üretiyordu → temiz deneme yanlış dosyayı siler, düzeltme hiçbir şey yapmazdı.

### Konsol penceresi (backend tarafı)

1.9.21 launcher yardımcı komutlarını kapatmıştı; backend tarafında da bayraksız spawn'lar vardı
(güncelleme sırasında çalışan imza denetimi + kurulum başlatma + ffmpeg). Ortak yardımcı
`utils/gizli_surec.py` + `tests/test_konsol_penceresi.py` yapısal kapısı eklendi.

### Yarım kalmış kurulum "Hazır!" görünüyordu (launcher 1.9.23)

`install_profiles` ATOMİK DEĞİLDİR — canlı `runtime`ı silip yerine açar; `runtime.new` + takas
yalnız GÜNCELLEME yolunda var. Açma sırasında kapanma olursa exe yazılmış ama
`_internal/frontend` yarım kalmış olabilir. `detect_environment` kurulumu YALNIZ exe'nin
varlığıyla anlıyordu → client "Hazır!" der, kullanıcı Başlat'a basar, backend anlaşılmaz bir
hatayla düşerdi.

Artık yapısal kontrol (`flow::kurulum_saglam_mi`: exe + `_internal` + web arayüzü). "Kurulu
değil" demek "kurulu ama açılmıyor"dan İYİDİR: kurulum ekranı çıkar, kullanıcı tek tıkla
toparlar (paketler önbellekte). Karşı-kanıt testi de var: kontrol fazla katı olup çalışan
kurulumu "kurulu değil" göstermemeli.
**Doğrulama:** 14+ yeni test; mutasyonlar 6/6 + 3/3 + 3/3 yakalandı (kurtarmayı devre dışı
bırakma, doğrulanmamış sürümü öne alma, yapısal kapıyı kaldırma, kilidi kaldırma, kilidi kökün
içine koyma, `.part` adını ayrıştırma).

---

## launcher 1.9.21 — 2026-08-11 (siyah konsol penceresi)

**Saha şikâyeti.** "Client güncellemesi için uygulamayı kapatıp geri açtığımda **2 kez siyah
konsol penceresi** çıktı."

**Kök neden.** Launcher pencereli (konsolsuz) çalışır. Konsol-altsistem bir program
(`powershell`, `icacls`, `taskkill`…) böyle bir süreçten başlatılınca Windows ona **yeni bir
konsol açar** ve kullanıcı ekranda siyah pencerenin yanıp söndüğünü görür. Backend spawn'ında
`CREATE_NO_WINDOW` zaten vardı; **yardımcı komutlarda unutulmuştu** — güvenlik-duvarı denetimi
(açılışta) ve kurulum dizinine ACL (güncellemede). Tam olarak iki pencere.

- Ortak yardımcı: `platform::gizli_komut` — Windows'ta süreç başlatan **tek** yol.
- Dört çağrı yeri buna çevrildi (güvenlik duvarı denetimi, ACL, yükseltme kabuğu, klasör seçici);
  backend spawn'ı ve tarayıcı açma da aynı yola alındı (bayrak iki kez verilmesin: `creation_flags`
  değeri **ezer**, OR'lamaz — ikinci çağrı ilkini sessizce iptal ederdi).
- **Yapısal kapı** (`core/tests/konsol_penceresi.rs`): kaynakta konsol açabilecek çıplak
  `Command::new` kalmadığını denetler. Tek tek düzeltmek yetmezdi; bir sonraki yardımcı komut
  yine unutulurdu. Mutasyonla doğrulandı (3/3).
---

## app 1.9.9 · launcher 1.9.20 — 2026-08-11 (SAHA ARIZASI: kurulum sonrası cihaz açılmıyordu)

**Hasta güvenliği / kullanılabilirlik — ACİL.** Kaldırıp yeniden kuran bir kurulumda backend
açılışta ölüyor, cihaz **bir daha hiç açılmıyordu**. Operatörün yapabileceği hiçbir şey yoktu:
yeniden kurmak da çözmez, çünkü tıbbi veri (doğru olarak) korunur. Tek bir arızanın altından
**dört ayrı kusur** çıktı; dördü de düzeltildi.

### 1. At-rest anahtarı uymayınca backend TUĞLALAŞIYORDU

Yeniden kurulumda `pemf_secrets.json` yenilenince SQLCipher anahtarı değişir; korunan DB
çözülemez (`file is not a database`) ve `_init_database` hatayı yukarı fırlatıp süreci **çıkış
kodu 1** ile öldürürdü. Artık dosya **kenara alınır** (yeniden adlandırılır, `*.acilamadi-<ts>`;
**asla silinmez**) ve temiz bir DB açılır — anahtar gittiyse veri zaten kalıcı okunamaz, cihazı
çalışmaz tutmak veriyi kurtarmaz.

⚠️ Karantina **yalnız** "anahtar okunabildi ama uymuyor" hâlinde yapılır. Anahtar hiç
çözülemediyse (geçici DPAPI/keyring arızası) hata yukarı fırlar — orada dosyayı kenara almak
KURTARILABİLİR hasta verisini yetim bırakırdı. Bu sınır testle kilitlidir.

### 2. Veri göçü, açılamayacak DB'yi kopyalayıp SONSUZ DÖNGÜ yaratıyordu

`%APPDATA%` → makine-geneli kök göçü (1.9.6, vardiyalı klinikte "boş klinik" düzeltmesi) şifreli
DB'leri kopyalıyor ama onları açan anahtarı **taşımıyordu** — `pemf_secrets.json` cihaz kimliği
içerdiği için haklı olarak göç etmez. Kodun kendi yorumu "tıbbi kayıt + onu açan anahtar" diyordu;
liste bunu yapmıyordu. En kötüsü: dosya kenara alınsa bile hedefte "yok" sayılır ve **aynı bozuk
dosya tekrar kopyalanırdı** — karantina hiçbir şey çözmez, elle müdahale bile kurtarmazdı.
Şifreli DB artık ancak hedefin anahtarıyla **gerçekten açılabiliyorsa** kopyalanır; açılmıyorsa
kaynak eski konumunda durur ve durum loglanır.

### 3. Launcher YANLIŞ günlüğü okuyordu — arıza teşhis edilemiyordu

Backend `PEMF_DATA_DIR` ile `C:\ProgramData\PEMF_System`e yazar; bu değişkeni çocuğa **yalnız
launcher** verir, kendi ortamında yoktur. `read_tail` yolu kendi ortamından çözdüğü için
`%APPDATA%\PEMF_GUI\logs`a bakıyordu → kullanıcıya **günler öncesine ait** bayat günlük
gösterildi. Gerçek sebep doğru dosyaya yazılmıştı ama kimse oraya bakmıyordu. Günlük yolu artık
çocuğun gördüğü ortamla çözülür.

### 4. Başarısız SQLCipher açışı bağlantı sızdırıyordu

`open_encrypted_conn` yanlış anahtarda bağlantıyı kapatmadan fırlatıyordu. Windows'ta o tutamak
dosyayı **kilitler** → karantina `shutil.move`'u PermissionError'a düşerdi, yani (1)'deki koruma
tam ihtiyaç duyulan anda çalışmazdı. (Bu kusuru, karantina testinin geçici dizini temizlenemeyince
fark ettik.)

**Doğrulama:** 10 yeni test; **7 mutasyonun 7'si** yakalandı (karantina kapatma, silmeye çevirme,
`-wal/-shm` bırakma, bağlantı sızdırma, göç kapısını kaldırma, göç doğrulamasını sahte-True yapma).
Ayrıca **gerçek frozen build** üzerinde uçtan uca: başka anahtarla şifreli DB → karantinaya alındı,
temiz DB oluştu, `/api/health` 200.

### Üretici kimliği düzeltildi

Kurulumdaki Windows UAC penceresi yayıncıyı **"PEMF Medical Technologies"** gösteriyordu; tescilli
ünvan **İBİA Teknoloji Ltd. Şti.**dir. Ünvan sitede ve client arayüzünde güncellenmişti ama Windows
sürüm-kaynaklarında eski ad kalmıştı — yani kullanıcıya gösterilen tek yerde yanlış duruyordu.
Kaynak `LegalCopyright` alanıydı (`CompanyName` boştu, Tauri NSIS şablonu onu hiç yazmıyor).

- `tauri.conf.json`: `publisher` alanı **eklendi** + `copyright` düzeltildi. Artık Programlar
  listesindeki **Yayımcı** da doğru ad.
- Backend sürüm kaynağı (`docs/version_info.txt` + onu üreten `build_installer.ps1`) ve Inno
  yayıncısı düzeltildi.
- ⚠️ **Uygulama kimliği (`com.pemfmedical.vetclient`) BİLEREK DEĞİŞMEDİ** — o ünvan değil kurulum
  kimliğidir; değiştirmek kurulum yollarını, kaldırma kaydını ve oto-güncellemenin mevcut kurulumu
  tanımasını bozar. Testle kilitli.
- ⚠️ Client'ın üretici registry yolu (`Software\<üretici>`) `pemfmedical`den yeni ünvana kaydı.
  Kaldırma kaydı **ürün adına** bağlı olduğu için yerinde güncelleme bozulmaz; ama eski anahtar
  yetim kalır → kaldırma aracı artık **ikisini de** tarar.

### Android indirmesi de sürüm taşıyor

Windows kurulum dosyası sürüm taşıyordu (`PEMFVetClient-Setup-1.9.19.exe`), APK taşımıyordu.
Artık `PEMF_Vet_Mobil-2.3.8.apk`. Eski ad **korundu** (manifest'teki uygulama-içi güncelleme ve
eski bağlantılar kırılmasın); ikisi de yayında ve 200 dönüyor. Windows sürümü etiketten türetilir,
Android'in etiketi `launcher-v*` olduğu için mobil sürüm site yapılandırmasında ayrıca tutulur.

---

## app 1.9.8 · launcher 1.9.19 — 2026-08-10 (profil bağımlılığı KALKTI)

Bir önceki sürüm profilleri bağımsız *seçilebilir* yapmıştı ama altta yatan gerçek bağ
duruyordu: **AI Pro'nun organ lokalizasyonunu çalıştıran modeller yalnız `home.zip` içindeydi.**
Yalnız Veteriner kuran kullanıcıda özellik **sessizce** çalışmıyordu; arayüz de bunu bir uyarı
notuyla telafi etmeye çalışıyordu. Bu sürümde bağ **kaynağından** kaldırıldı.

- **`inference_cat_organ` (3 ONNX, ~209 MB) ÇEKİRDEĞE alındı** — `base-deps.zip` katmanına,
  yani her kurulumda var. Uygulama katmanı (`base-app.zip`, ~71 MB) büyümedi: sıradan sürüm
  güncellemeleri eskisi kadar küçük iner. Modeller `deps` katmanında olduğu için ancak
  gerçekten değiştiklerinde yeniden indirilir.
- **Profiller arasında artık HİÇBİR bağ yok** — ne zorunlu ne işlevsel. Bir önceki sürümdeki
  bilgi notu kalktı (mekanizma, ileride yeni bir ortak model çıkarsa kullanmak üzere duruyor).
- **`home.zip` 528 MB → 318 MB.** Aynı modeller hem çekirdekte hem profil paketinde olsaydı ev
  sahibi kullanıcı ~209 MB'ı **iki kez** indirecekti.
- **Profil paketlerinin içeriği artık KODDA** (`build_tools/make_model_zip.py`). Bu paketler
  elle üretiliyordu; ne içerdikleri hiçbir yerde yazılı değildi — bu hatanın kaynağı da tam
  olarak buydu. Betik, çekirdek modeli bir profil paketine koymayı **reddeder**.

⚠️ Sahada işe yaradığı ölçüldü, varsayılmadı: launcher kuruluma `PEMF_AI_MODELS_DIR` verir ve o
dizin vet-only kurulumda **vardır** (ama çekirdek modeli içermez). Model çözücü kök-başına değil
**dosya-başına** düştüğü için bundle'daki kopya bulunur; `tests/test_cekirdek_model_cozumu.py`
bunu kilitler (çözücü kök-başına seçime dönerse testler kırmızıya döner).

### İndirme sayacı — macOS/Linux sayılmıyor

Site o platformları **"Yakında"** gösteriyor (donanım yolu Windows'a özel), yani kullanıcı
oradan indiremiyor. Paketler yayında olduğu için sayaç yine de onları topluyordu; indirilemeyen
bir platformun indirmeleri çoğunlukla bizim kendi doğrulamalarımızdı ve "kaç kişi kullanıyor"
izlenimini bozuyordu. Toplam artık **yalnız Windows + Android**.

---

## app 1.9.7 · launcher 1.9.18 — 2026-08-10 (hotspot + profiller)

### PEMF-Gateway hotspot'u artık KENDİLİĞİNDEN açılıyor

**Saha hatası.** Siteden indirip kuran kullanıcıda `PEMF-Gateway` WiFi'si hiç oluşmuyordu →
**8 bobinin 3'ü (ESP 6-8) bağlanamıyordu** ve arayüzde bunun hiçbir göstergesi yoktu.

**Kök neden (ölçüldü).** Hotspot'u kuran tek yol `setup_services.ps1 -Mode device`in kaydettiği
logon-task'tı. Ama PEMF Vet Client — yani siteden indirip kuran yol — `setup_services.ps1`i
**hiç çalıştırmıyor** (launcher kaynağında ne `setup_services` ne `schtasks` geçiyor). Backend de
hotspot'u yalnız *okuyordu*, hiç başlatmıyordu.

- **Backend açılışta hotspot'u kendisi başlatır.** Windows Mobile Hotspot API'si kullanıcı oturumu
  ister; launcher backend'i kendi oturumunda çocuk süreç olarak başlattığı için bu mümkündür.
  Servis kurulumunda (session 0) yol kendini devre dışı bırakır — logon-task orada zaten işi
  yapıyor, iki başlatıcı çakışmasın.
- **SSID/parola tek kaynak**: `start_hotspot.ps1` (PEMF-Gateway / pemf1234). Backend parametre
  geçmez — ESP firmware'i değerleri kendi içinde taşır, ikinci bir gerçek üretilemez.
- Açılışı **bloklamaz** (ayrı thread) ve hata hâlinde servisi **düşürmez**: hotspot yoksa STM
  bobinleri (1-5) ve tüm arayüz çalışmaya devam eder. Kapatmak için `PEMF_HOTSPOT=0`.
- Arayüzde **"Kablosuz Bağlantı"** durum satırı. `hotspotActive` zaten çekiliyordu ama **hiç
  gösterilmiyordu** — arıza görünmezdi.

### Profiller bağımsız seçilir (client 1.9.18)

"Veteriner Hekim" seçilince "Ev Sahibi" **zorla** ekleniyordu; yalnız Veteriner + Araştırma
kurulamıyor, gereksiz ~503 MB iniyordu. Zorunlu olan tek şey **çekirdek**.

⚠️ Bağımlılık uydurma değildi (paket içerikleri doğrulandı): `home.zip` →
`inference_cat_organ/models/*.onnx`, AI Pro'nun organ lokalizasyonu bunları kullanır. Zorlama
yerine **engellemeyen** bir bilgi notu + tek tıkla ekleme kondu. Kalıcı çözüm ortak modeli
çekirdeğe almaktır.

### Giriş ekranı (client 1.9.17)

Doğru parola "hatalı" deniyordu; alan silinip aynı şey yazılınca giriş yapılıyordu → parolayı
göster/gizle, hatalı girişte alan temizleme, görünmez karakter uyarısı.

### İndirme sayacı

Sitedeki sayaç sabit dosya adına bakıyordu; kurulum dosyası sürüm taşımaya başlayınca yeni
sürümlerin indirmeleri **hiç sayılmayacaktı**. Desenli eşleşmeye geçildi — geçmiş sayı korunur
(gerçek veriyle ölçüldü: 46 -> 51).

---

## launcher 1.9.17 — 2026-08-10 (giriş ekranı düzeltmesi)

**Saha hatası.** Doğru parola yazıldığında *"E-posta veya parola hatalı"* deniyor; parola alanı
**silinip aynı şey tekrar yazılınca** giriş yapılıyordu.

**Kök neden.** İlk istekte gönderilen parola, kullanıcının yazdığı şey değildi. Alan `type="password"`
olduğu için içinde ne olduğunu **ne kullanıcı ne uygulama** görebiliyordu (otomatik doldurma
kalıntısı, kopyala-yapıştırdan gelen görünmez karakter, yutulan ilk tuş…). Üstelik alan **yalnız
başarıda** temizleniyordu — hatalı denemeden sonra kalıntı duruyor, kullanıcı üstüne yazdıkça hata
birikiyordu.

- **Parolayı göster/gizle** düğmesi — bu hata sınıfını kendi kendine teşhis edilir kılar. Her giriş
  denemesinden sonra otomatik gizlenir (ekranda unutulmaz).
- **Hatalı girişte alan temizlenir** ve odak ona döner → her deneme temiz başlar.
- Parolada **baştaki/sondaki boşluk** ya da **görünmez karakter** (ZWSP, yön işaretleyici) varsa
  açıkça söylenir. ⚠️ Sessizce kırpılmaz: bir parola gerçekten boşluk içerebilir.
- **Boş girdi artık `MissingInput`** — eskiden `BadCredentials` dönüyordu, yani arayüz tarafındaki
  bir hata kullanıcıya "parolanız yanlış" diye görünüyor ve hiçbir kayıtta ayırt edilemiyordu.

| Sürüm | Etiket | Tarih | Installer sha (12) |
|---|---|---|---|
| 1.9.17 | `launcher-v1.9.17` | 2026-08-10 | `8070971e5180` |

> ⚠️ **İndirilen dosya adı artık sürüm taşır** (`PEMFVetClient-Setup-1.9.17.exe`). Ad site
> tarafında `windowsTag`ten **türetilir**, elle yazılmaz — etiket yükseltilip ad unutulduğunda
> indirme butonu sessizce 404 verirdi.
