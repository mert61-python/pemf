# Gerçek Arıza Listesi — çalışma takipçisi

> Kaynak denetim: [`DEPO-DENETIMI-2026-09-15.md`](DEPO-DENETIMI-2026-09-15.md)
> Klasör düzeni: [`KLASOR-YAPISI-PLANI.md`](KLASOR-YAPISI-PLANI.md) — **bu listeden SONRA**
> Her satır 2026-09-15'te yeniden ölçüldü. "Belgede öyle yazıyor" kanıt sayılmadı.

Ayrım şu: **A = bugün zarar verebilir ya da sessizce kırılır.** B = ticari olgunluk.
C = hijyen. Klasör taşıma hiçbirini çözmez, o yüzden en sonda.

---

## A — Gerçek arızalar

### A1 · Göç kodu beş yerde — bu zaten hasta geçmişi kaybettirdi ⛔
| | |
|---|---|
| **Kanıt** | `database/sqlcipher_util.py` · `database/treatment_history_db.py` · `utils/path_utils.py` · `servers/api_server.py` · `pemf_gui/config.py` |
| **Neden arıza** | 2026-09-13: ilk iki kopya düzeltildi, **ürün hâlâ kaybediyordu** — üçüncü yol (şablon kopyalayıcı) önce davranıyordu. Kopyalama teorik değil, **gerçekleşmiş** bir veri kaybı sebebi |
| **Bugünkü durum** | Arıza kapatıldı (10 mutasyon-kanıtlı test). Ama beş kopya duruyor → altıncı kopya aynı arızayı geri getirir |
| **İş** | Tek modül `database/goc.py`; diğerleri ince sarmalayıcı. Mevcut 10 kapı birleştirmeden sonra da yeşil kalmalı |
| **Kim** | Ben |

### A2 · MD5 birebir kopya CV kodu — biri düzeltilince diğeri sürükleniyor
| | |
|---|---|
| **Kanıt (ölçüldü)** | `51263a20…` → `ai_hub/inference_em_fantom/phantom_cv/coord_transform.py` **=** `ai_hub/inference_petri_dish/petri_cv/coord_transform.py` (326 satır)<br>`e3e8fb06…` → aynı ikilinin `mqtt_publish.py`'leri (144 satır)<br>`cabin_config.py`: 367 satırın **366'sı aynı**, tek fark `mqtt_client_id` varsayılanı |
| **Neden arıza** | `coord_transform` = bobin/hedef geometrisi. Bir taraftaki düzeltme diğerinde kalmaz. Depo bunu **biliyor** ve kaldırmak yerine teste bağlamış — kapı yalnız *unutulunca* kırılıyor, yani arızayı önlemiyor, haber veriyor |
| **İş** | `ai_hub/cv_ortak/` paketi; `client_id` çağıran tarafın parametresi olur |
| **Kim** | Ben |

### A3 · Bu oturumun 14 yeni testi CI'ı hiç görmedi
| | |
|---|---|
| **Kanıt (ölçüldü)** | `origin/production-hardening`'in **18 commit** önünde · **71 değiştirilmiş + 48 takipsiz** dosya · takipsizlerin **14'ü `tests/` altında** |
| **Neden arıza** | Bu testlerin içinde yarım-göç veri kaybı kapısı var — yani A1'i kapatan kapı. CI'da koşmuyorsa, biri regresyon yaptığında **kimse görmez**. Kapı var ama devrede değil |
| **İş** | Seçerek commit + push → ubuntu/windows matrisi + kapsam ratchet + gitleaks tam geçmiş taraması |
| **Dikkat** | `pre-commit` kurulu (`.git/hooks/pre-commit` var), önbellek dolu → indirme gerekmez. `skip-worktree`'li 4 sır dosyası commit'e **girmemeli** |
| **Kim** | Ben |

### A4 · `base-linux.zip` yok — Linux kullanıcısı için sessiz ölüm
| | |
|---|---|
| **Kanıt (ölçüldü)** | Tüm ağaçta `base-linux*` **sıfır dosya**. `scripts/make_manifest.py:45` bu adı bekliyor. `.github/workflows/linux-backend.yml` üretiyor (tag `backend-linux-v*`) |
| **Neden arıza** | `docs/LAUNCHER_SPEC.md:66` kendi uyarısı: *"Eksikse Linux client sessizce Windows base.zip indirir → backend hiç çalışmaz."* Hata mesajı yok, çökme yok — **ürün çalışmıyor** |
| **Acillik** | Sahada tek makine Windows → bugün kimseyi vurmuyor. Ama Linux satışı açılırsa ilk müşteride patlar |
| **İş** | Linux workflow'unu bir kez koştur, release asset'i doğrula; ya da manifestten Linux runtime'ını **açıkça kaldır** (sessiz yanlış indirme yerine dürüst "yok") |
| **Kim** | Ben (workflow) |

### A5 · Sır koruması taze klonda kurulmuyor
| | |
|---|---|
| **⚠️ DENETİM DÜZELTMESİ** | Denetim §1.3 *"Bayrağı kuran bir script/hook depoda yok"* diyordu — **yanlış**. `build_tools/secrets_backup.py:96-152` restore sonrası `skip-worktree`'yi **kendisi uyguluyor**, üstelik `git exit 128` (dubious ownership) deliği de kapatılmış |
| **Kalan gerçek delik** | Restore **koşmadan** `Secrets.h` elle doldurulursa bayrak yok. O senaryoda tek güvence gitleaks (pre-commit + CI) — çalışıyor ama tek kemer |
| **İş** | `bootstrap.ps1`'e skip-worktree adımı; restore'a bağlı olmasın |
| **Kim** | Ben · **küçük iş** |

### A6 · BLE eşleşme/şifreleme hâlâ yok
| | |
|---|---|
| **Bugünkü durum** | Uzaktan tetiklenen otomatik açılma **kaldırıldı** · yalan `PIN` log'u **kaldırıldı** · `PEMF_BLE_PROVISIONING_ENABLED` kill-switch **eklendi**. Yüzey daraldı |
| **Kalan** | Eşleşme/şifreleme yok, `DEFAULT_BLE_CMD_HMAC_KEY` hiçbir yerde tüketilmiyor (komut imzalama **hiç yazılmamış**) |
| **Neden bugün P0 değil** | ESP bobin sürmüyor (`ESP_COIL_IDS = {8}`, rezerve) |
| **Şartı** | ESP geri bobin sürmeye başlamadan **önce** açılmalı |
| **Kim** | Sahip (kart elimde yok, test edilmemiş kripto yakılmamalı) |

### A7 · Bulut MQTT kimlik bilgileri — **bilinçli atlandı**
Sahip 2026-09-15'te "boşver" dedi. Adres PUBLIC geçmişte duruyor. Karar kayıtlı, iş kapalı.

---

## B — Ticari olgunluk

| # | İş | Kanıt | Kim |
|---|---|---|---|
| **B1** | `pyproject.toml`'a `[project]` + `[build-system]`; `controllers/` `scripts/` `build_tools/`'a `__init__.py` | 97 satır, **sıfır** `[project]`/`[build-system]`. Somut maliyeti: `headless_core.py`+`event_bus.py` spec'e **elle** sabitlenmiş (`PEMF_Backend_onedir.spec:401`). IEC 62304 "yazılım öğesi" tanımı için de gerekli | Ben |
| **B2** | `THIRD_PARTY_LICENSES.md` yenile | 2026-08-10'da donmuş; sonrasında `shap` `grad-cam` `timm` `captum` `celldetection` eklendi. **AGPL'li `ultralytics`** taşıyan üründe eksik envanter = ticari satışta doğrudan risk | Ben |
| **B3** | `README.md:188` sürüm tablosunu `versions.json`'dan **türet** | Yazan: `1.9.5 / 1.9.9 / 2.3.3` — gerçek: **1.9.50 / 1.9.51 / 2.3.34**. Aynı README'nin 49. satırı "tablo donmuştu, kaldırıldı" diyor → **aynı tuzak üçüncü kez**. Elle yazıldığı sürece dördüncü kez bayatlar | Ben |
| **B4** | Dev dosyaları böl | `api_server.py` **5.139** · `ai_router.py` **4.023** · `treatment_history_db.py` **3.701** (tek sınıfta 95 metot: seans + coil-run + sensör + denetim izi + outbox + şema göçü + PII) | Ben · **en son** |

---

## C — Hijyen (ucuz, toplu yapılır)

| # | İş | Kanıt |
|---|---|---|
| **C1** | `firmware_cikti/` → `.gitignore` | `.gitignore`'da **yok**, `git status`'ta `?? firmware_cikti/` |
| **C2** | `training_archive/` (299 MB / 434 takipli) + `bin/` (61 MB / 14 takipli ikili) → LFS ya da ayrı depo | `.git` **347 MB**; her klon indiriyor. `cloudflared.exe` 52 MB. ⚠️ `training_archive/ai_data/real_clinical_data/ecg_signals.npy` — PUBLIC depoda **"gerçek klinik veri"** adlandırması ayrıca doğrulanmalı |
| **C3** | Ölü dizinleri kaldır | `frontend/` 0 · `lattekurulum/` 0 · `website/` 3 · `web_static/` 3 · `dema-terapi-simülatörü/` 12 · `pemf_vet_landing/` 13 takipli. `ai/config.py` (349 satır) üretimde **sıfır** import — tek tüketicisi donmuş arşiv |
| **C4** | Bayat belgeler | `PEMF_SISTEM_RAPORU.md` (2026-03) · `RUNBOOK.md` (08-15, ESP sökülmesi sonrası güncellenmemiş) · `frontend_version.json` (2026-06-27) · `LAUNCHER_SPEC.md` (07-29, launcher o gün 1.9.9'du) |
| **C5** | Derleme çıktılarını ağaç dışına | `PEMF_BUILD` · `launcher/target` · `pf/android/app/build` — birlikte 19,5 GB'dı |

---

## Sıra — ve neden bu sıra

| # | Adım | Neden burada |
|---|---|---|
| **1** | **A3** commit + push, CI yeşil | Bundan sonraki her düzeltme bu kapılardan geçecek. Kapı devrede değilken yapılan düzeltme **doğrulanmamış** düzeltmedir |
| **2** | **A1** göç birleştirme | En yüksek gerçek risk; bir kez zaten zarar verdi |
| **3** | **A2** CV kopyaları | Aynı sınıf, geometri hesabı |
| **4** | **A5** + **C1** | İkisi de küçük; aynı commit'te gider |
| **5** | **B1** paket sınırları | Klasör taşımanın **ön şartı** |
| **6** | **B2** + **B3** | Ticari risk; ucuz |
| **7** | **A4** base-linux | Workflow koşturma gerektiriyor |
| **8** | **C2–C5** hijyen | Toplu |
| **9** | **Klasör düzeni** F1→F6 | Artık taşınacak şey sade |
| **10** | **B4** dev dosya bölme | Yeni sınırlar içinde doğal yerine düşer |

**Sahip tarafı (bende yapılamaz):** A6 BLE eşleşme · S3 reflash · STM reflash + doz kalibrasyonu
(⚠️ tepe-tepe `pp_x = XP−XN`) · 164 senaryoluk saha listesi · Vault kurtarma setini makine dışına
alma · Cloudflare NAMED tünel · firmware satürasyon tezgâhı · 72 saatlik soak · iOS/EAS →
[`SAHA-ISLERI-REHBERI.md`](SAHA-ISLERI-REHBERI.md)

**Yayın:** ⛔ DONDURULDU — sahip "yayınla" demeden manifest/release koşturulmaz.
