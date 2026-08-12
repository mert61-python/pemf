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
