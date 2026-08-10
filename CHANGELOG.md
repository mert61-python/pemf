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
