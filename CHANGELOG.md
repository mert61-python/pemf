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

| Sürüm | Etiket | Tarih | base.zip sha (12) | app / deps sha (12) |
|---|---|---|---|---|
| 1.8.0 | `client-app-v1.8.0` | 2026-07-13 | `90cf004f9fa1` | `42b88557fe00` / `69cf344d0fc6` |

### launcher (PEMF Vet Client)

| Sürüm | Etiket | Tarih | Installer sha (12) |
|---|---|---|---|
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
| 2.3.7 | 14 | `launcher-v1.9.15` | `7078cf6b36a3` |

### backend (`VERSION`)

| Sürüm | Not |
|---|---|
| 1.9.5 | app paketi içinde dağıtılır; ayrı bir yayın etiketi yoktur |
