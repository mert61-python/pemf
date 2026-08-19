# Değişiklik Kaydı — PEMF Vet

> **Neden bu dosya var.** Cihaz yazılımı **sessizce ve otomatik** güncelleniyor: PEMF Vet Client
> açılışta manifest'e bakar, yeni paketi indirir, kurar. Klinik hiçbir şey yapmaz — ve değişikliğin
> ne olduğunu **hiçbir yerden okuyamıyordu.** Sessiz güncelleme ile değişiklik kaydı yokluğu tek
> başına değil, *birlikte* kötüdür: bir davranış değiştiğinde veteriner bunu arıza sanar, destek de
> hangi sürümün ne yaptığını bilemez. (2026-08-09 denetimi, Tier 3.)

## Kural

**Bir sürüm, buraya yazılmadan yayınlanmaz.** Kayıt en az şunları içerir:

- kanal (`app` paketi / `launcher` / `mobile`) ve sürüm,
- yayın etiketi ve **paket sha256'sının ilk 12 hanesi** — aynı sürüm numarası farklı ikili
  içerebilir; `buildId` (`/api/health`, `X-Build-Id`) tam bu değeri raporlar,
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

## app 1.9.17 — 2026-08-19 (donanım-uyum turu: hibrit bobin güvenliği uçtan uca)

**Etiket:** `client-app-v1.9.17` → `base-app.zip` + `base-deps.zip` (sha'lar yayında bu satıra işlenir).

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
Paket kimliği (`buildId`, `/api/health`): `42cbc0c11a0e`.

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
