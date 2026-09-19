# Gerçek Arıza Listesi — çalışma takipçisi

> Kaynak denetim: [`DEPO-DENETIMI-2026-09-15.md`](DEPO-DENETIMI-2026-09-15.md)
> Klasör düzeni: [`KLASOR-YAPISI-PLANI.md`](KLASOR-YAPISI-PLANI.md) — **bu listeden SONRA**
> Her satır 2026-09-15'te yeniden ölçüldü. "Belgede öyle yazıyor" kanıt sayılmadı.

Ayrım şu: **A = bugün zarar verebilir ya da sessizce kırılır.** B = ticari olgunluk.
C = hijyen. Klasör taşıma hiçbirini çözmez, o yüzden en sonda.

---

## A — Gerçek arızalar

### ✅ A1 · Göç kodu beş yerde — bu zaten hasta geçmişi kaybettirdi (2026-09-15 KAPANDI)
| | |
|---|---|
| **Kanıt (2026-09-15 AST ile ölçüldü)** | **935 satır göç kodu, 18 fonksiyon, 5 dosya:**<br>`sqlcipher_util.py` 285 · `treatment_history_db.py` 342 · `path_utils.py` 174 · `api_server.py` 75 · `pemf_gui/config.py` 59 |
| ⚠️ **Denetim düzeltmesi** | Denetim §2.3 *"göç kodu beş yerde"* diyordu — **bu ifade gevşek**. Ölçüldü: ortada **tek bir gerçek kopya** var, kalan dördü *farklı* göçler (anahtar göçü, veri-kökü göçü, AI JSONL, eski config dizini) — sadece dağınıklar. Gerçek kopya:<br>`sqlcipher_util.migrate_to_encrypted_if_needed` (129 anlamlı satır) ↔ `treatment_history_db._migrate_to_encrypted_if_needed` (139) → **%73 aynı, 98 satır birebir**. Fark tamamen mekanik: modül-fonksiyonu ↔ metot (`self.logger`/`self.db_path`) |
| **Neden arıza** | 2026-09-13: ilk iki yol düzeltildi, **ürün hâlâ kaybediyordu** — üçüncü yol (şablon kopyalayıcı) önce davranıyordu. Dağınıklık teorik değil, **gerçekleşmiş** bir veri kaybı sebebi |
| **Bugünkü durum** | Arıza kapatıldı (10 mutasyon-kanıtlı test, CI'da). Ama 98 satırlık kopya duruyor → bir tarafta düzeltilen sonraki hata diğerinde kalır |
| ⚠️ **TUZAK — düz delegasyon REGRESYON olur** | Normalize edilmiş karşılaştırma (%82 aynı) mekanik olmayan **tek bir fark** gösterdi: `treatment_history_db` fazladan bir **emanet (escrow) politikası** taşıyor — `PEMF_KEEP_PLAIN_BAK` bayrağı · `.plain.bak`'ı ACL ile kilitleyip saklama · kilit tutmazsa emanetten vazgeçip **güvenli silme** · silme de düşerse `KRİTİK: ELLE SİLİN` log'u. `sqlcipher_util`de bunların **hiçbiri yok**.<br>Yani "metodu util'e delege et" demek, **hasta DB'sinin at-rest PII politikasını sessizce düşürmek** demek — ya korumasız düz-metin yedek kalır ya da emanet kopya kaybolur. İkisi de zaten bir kez veri kaybettiren alanda yeni bir arıza olurdu. |
| **İş** | **(a)** Ortak 98 satırı tek fonksiyona al, **göç-sonrası yedek politikasını parametre/geri-çağrı yap** — iki çağıran da kendi politikasını AÇIKÇA belirtsin (`sqlcipher_util` = kenara al, `treatment_history_db` = emanet/güvenli-sil). **(b)** Kalan dört göçü tek giriş noktasından sıraya sok, "hangisi önce koşuyor" bir daha kaza olmasın.<br>✅ Escrow dalının kapısı **zaten var** (ölçüldü): `test_at_rest_encryption_rollout.py:188` davranışsal (`PEMF_KEEP_PLAIN_BAK=1` ile escrow geri gelir), `test_kalan_davranissal.py:250` bayrağın gerçekten okunduğunu regex'le çıpalıyor. Yani birleştirme bu kapıları **kırmadan** yapılmalı — kırılırlarsa politika düşmüş demektir. Mevcut 10 yarım-göç kapısı da yeşil kalmalı |
| **Kim** | Ben |

### ✅ A1b · Aynı politika, **iki farklı bayrak adı** — kopyalamanın canlı sonucu (KAPANDI)

Bu, A1'i araştırırken bulundu ve denetimin "kopya kod arıza doğurur" iddiasının **kanıtı**.
Düz-metin yedeğin emanete alınıp alınmayacağını belirleyen bayrak iki kopyada **farklı adla**
okunuyor:

| Dosya | Okuduğu bayrak | Kapsadığı veri |
|---|---|---|
| `apps/backend/database/sqlcipher_util.py:129` | **`PEMF_KEEP_PLAIN_BACKUP`** | hasta DB'si |
| `apps/backend/database/treatment_history_db.py:420` | **`PEMF_KEEP_PLAIN_BAK`** | tedavi + AI geçmişi DB'si |

**Sonuç:** emanet isteyen bir operatör bayrağı set eder, **iki veritabanından yalnız birinde**
işe yarar. Diğeri sessizce düz-metin yedeği güvenli-siler. Hangisi olduğunu hiçbir yerde
yazmıyor; ekranda ya da log'da da ayrım yok.

**Ölçüldü:**
- Testler **yalnız `PEMF_KEEP_PLAIN_BAK`'ı** tanıyor — `PEMF_KEEP_PLAIN_BACKUP` için **sıfır**
  test. Yani iki isimden biri tamamen kapısız.
- İkisi de `deploy/device.env`'de **yok** → **servis (NSSM) kurulumunda ulaşılamaz**, çünkü
  servis ortamı o dosyadan yazılır ve etkileşimli kullanıcının ortamını miras almaz.
  ⚠️ **Düzeltme:** ilk okumamda bunu "jeton bayrağıyla aynı sınıf (launcher geçirmiyor)" diye
  yazmıştım — **yanlış**. Ölçtüm: `launcher/core/src/backend.rs:484` haritayı `cmd.env(k, v)` ile
  uyguluyor ve **`env_clear()` yok**, yani launcher'ın doğurduğu backend ortamı **miras alıyor**.
  Eksik olan yalnız servis yolu; `install.rs`'e satır eklemek gerekmiyor.

**İş:** tek ada indir (eskisi geriye-uyum için okunmaya devam etsin, uyarı loglasın) ·
`device.env`'e kapı kaydı olarak yaz · her iki yolu da ölçen tek kapı. A1 ile **aynı turda**
yapılmalı — birleştirme zaten bu kod yolunu elden geçiriyor.

**Kim:** Ben

### ⛔ A2 · MD5 birebir kopya CV kodu — **ERTELENDİ, iddia tersine döndü** (2026-09-17)
| | |
|---|---|
| **Kanıt (ölçüldü)** | `51263a20…` → `ai_hub/inference_em_fantom/phantom_cv/coord_transform.py` **=** `ai_hub/inference_petri_dish/petri_cv/coord_transform.py` (326 satır)<br>`e3e8fb06…` → aynı ikilinin `mqtt_publish.py`'leri (144 satır)<br>`cabin_config.py`: 367 satırın **366'sı aynı**, tek fark `mqtt_client_id` varsayılanı |
| **Neden arıza** | `coord_transform` = bobin/hedef geometrisi. Bir taraftaki düzeltme diğerinde kalmaz. Depo bunu **biliyor** ve kaldırmak yerine teste bağlamış — kapı yalnız *unutulunca* kırılıyor, yani arızayı önlemiyor, haber veriyor |
| ⛔ **ÖLÇÜLDÜ — "güvenlik-ilgili" İDDİASI YANLIŞ** | `phantom_cv`/`petri_cv` **araştırma sağlayıcıları**, `PEMF_ARASTIRMA_AIPRO=0` ile kapalı; `_arastirma_aipro_kapisi` **409** döndürüyor: *"bobin sürülmez"*. Üstelik **bayrağın sebebi tam da bu dosya** — `ai_pro_hedef.py:202`: `coord_transform` marker→kabin rotasyonunu uygulamıyor, kedi hattıyla aynı çerçeveyi ürettiği **kanıtlanmadı**. Yani kopya kod **hiç bobin sürmüyor** |
| **Karar** | **ERTELENDİ.** Şimdi birleştirmek, yeniden yazılacak geometriyi birleştirmek olur. Doğru an: rotasyon düzeltmesi. ⚠️ Doğrulaması `ai_hub` PYZ dışında sevk edildiği için **backend build** ister |
| **Eski iş (askıda)** | `ai_hub/cv_ortak/` paketi; `client_id` çağıran tarafın parametresi olur |
| **Kim** | Ben |

### ✅ A3 · Bu oturumun 14 yeni testi CI'ı hiç görmedi (KAPANDI)
| | |
|---|---|
| **Kanıt (ölçüldü)** | `origin/production-hardening`'in **18 commit** önünde · **71 değiştirilmiş + 48 takipsiz** dosya · takipsizlerin **14'ü `tests/` altında** |
| **Neden arıza** | Bu testlerin içinde yarım-göç veri kaybı kapısı var — yani A1'i kapatan kapı. CI'da koşmuyorsa, biri regresyon yaptığında **kimse görmez**. Kapı var ama devrede değil |
| **İş** | Seçerek commit + push → ubuntu/windows matrisi + kapsam ratchet + gitleaks tam geçmiş taraması |
| **Dikkat** | `pre-commit` kurulu (`.git/hooks/pre-commit` var), önbellek dolu → indirme gerekmez. `skip-worktree`'li 4 sır dosyası commit'e **girmemeli** |
| **Kim** | Ben |

### ⛔ A4 · ~~`base-linux.zip` yok~~ — **BU MADDE YANLIŞTI** (2026-09-17)

`base-linux.zip`in yokluğu **arıza değil, KARARDIR.**

`launcher/core/src/manifest.rs` kayıtlı bir **sahip kararı** taşıyor (2026-08-09, Tier 1)
ve yokluğu **kapıyla kilitliyor**:

```rust
assert!(!m.runtimes.contains_key(platform::LINUX_X64),
    "linux-x64 manifest'e geri girdi — o platformda rollout freni ve self-update YOK");
```

Gerekçe (kararın kendi metninden): o platformlarda `layers` yoktu → rollout freni
çalışmıyordu, self-update Windows'a özeldi → kurulan cihaz eski sürümde **kalıcı
kilitleniyordu**. Client artık *"bu platform için paket yok"* deyip **durur**.

**Ölçüldü:** manifest `runtimes: []`, `layers` yalnız `win-x64`; `pemf-update` deposunun
altı release'inin hiçbirinde Linux varlığı yok (0/6).

⚠️ **Önerdiğim çözüm de yanlıştı.** "Workflow'u bir kez koştur" işe yaramaz:
`linux-backend.yml` `permissions: contents: read` + yalnız `upload-artifact` — **release'e
yazamaz**. Linux geri açılacaksa o adım ayrıca eklenmeli (ve bu bir **yayın**tır).

**Bulgu neden yanlış çıktı:** `LAUNCHER_SPEC.md`teki *"Linux client sessizce Windows
base.zip indirir"* uyarısını güncel sandım. O satır **v1 formatının** tarihsel tuzağı;
hemen altındaki **v2 hedefi** (sessiz fallback yok, sert hata) 08-09'da zaten uygulanmış.

Kapı: `tests/test_linux_runtime_YOKLUGU_karardir.py` · **Kim:** — (iş yok)

### ✅ A5 · Sır koruması taze klonda kurulmuyor (2026-09-16 KAPANDI)
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
| ✅ **B1** | `pyproject.toml`'a `[project]` + `[build-system]`; `apps/backend/controllers/` `scripts/` `build_tools/`'a `__init__.py` | 97 satır, **sıfır** `[project]`/`[build-system]`. Somut maliyeti: `headless_core.py`+`event_bus.py` spec'e **elle** sabitlenmiş (`PEMF_Backend_onedir.spec:401`). IEC 62304 "yazılım öğesi" tanımı için de gerekli | Ben |
| ✅ **B2** | `THIRD_PARTY_LICENSES.md` yenile — **YAPILDI** (26 → 113 bileşen) | 2026-08-10'da donmuş; sonrasında `shap` `grad-cam` `timm` `captum` `celldetection` eklendi. **AGPL'li `ultralytics`** taşıyan üründe eksik envanter = ticari satışta doğrudan risk | Ben |
| ✅ **B3** | `README.md:188` sürüm tablosu — **YAPILDI** (türetmek yerine KALDIRILDI + kapı) | Yazan: `1.9.5 / 1.9.9 / 2.3.3` — gerçek: **1.9.50 / 1.9.51 / 2.3.34**. Aynı README'nin 49. satırı "tablo donmuştu, kaldırıldı" diyor → **aynı tuzak üçüncü kez**. Elle yazıldığı sürece dördüncü kez bayatlar | Ben |
| ✅ **B4** | **KAPANDI (2026-09-18)** — `TreatmentHistoryDB` **93 → 17 metot**, dosya **3530 → 710 satır**, 8 karışım modülü | Ölçüt satır değil, tek nesnedeki **yedi sorumluluktu**. `apps/backend/database/thdb_{outbox,denetim,ai_gecmisi,telemetri,pii,sema,seans,bakim}.py` — kümeler metot **adından değil dokundukları tablodan** çıkarıldı. **Karışım (mixin)** seçildi, işbirlikçi nesne değil: `get_treatment_db(...)` her yerden alınıp metotları doğrudan çağrılıyor, işbirlikçiye çevirmek tüm çağrı yerlerini değiştirirdi. Gövdelere dokunulmadı (AST ile bayt bayt). **Yan çıktı:** taşıma, `_DB_ERROR` demetlerinin iki DB modülünde **zaten ayrışmış** olduğunu ortaya çıkardı → `apps/backend/database/db_hatalari.py` tek kaynak. Kapı: `tests/test_tedavi_db_bolunmus_KALIR.py` (tavan 22, 4 mutasyon). Doğrulama: süit 3109 · EXE 6/6 iç kapı · **48/48 ürün senaryosu** | Ben |

---

## C — Hijyen (ucuz, toplu yapılır)

| # | İş | Kanıt |
|---|---|---|
| ✅ **C1** | `firmware_cikti/` → `.gitignore` — **YAPILDI** | `.gitignore`'da **yok**, `git status`'ta `?? firmware_cikti/` |
| ⚠️ **C2** | `training_archive/` + `bin/` → **SAHİP KARARI BEKLİYOR** | `.git` **347 MB**; her klon indiriyor. `cloudflared.exe` 52 MB. ✅ `ecg_signals.npy` **ÖLÇÜLDÜ: KVKK riski YOK** — MIT-BIH (PhysioNet), PII içermiyor. Yerine **atıf** açığı çıktı ve kapatıldı |
| ⚠️ **C3** | Ölü dizinleri kaldır — **LİSTE YANLIŞTI, SİLME YAPILMADI** | `frontend/` 0 · `lattekurulum/` 0 · `website/` 3 · `web_static/` 3 · `dema-terapi-simülatörü/` 12 · `pemf_vet_landing/` 13 takipli. `ai/config.py` (349 satır) üretimde **sıfır** import — tek tüketicisi donmuş arşiv |
| ✅ **C4** | Bayat belgeler — **YAPILDI** (bayat olan belgeler değil, ETİKETLERİ) | `PEMF_SISTEM_RAPORU.md` (2026-03) · `RUNBOOK.md` (08-15, ESP sökülmesi sonrası güncellenmemiş) · `frontend_version.json` (2026-06-27) · `LAUNCHER_SPEC.md` (07-29, launcher o gün 1.9.9'du) |
| ⛔ **C5** | **YAPILAMAZ** — üçü zaten temiz; `launcher/target` taşımak `launcher.yml`i kırar (yayın, donmuş). Eski iş: derleme çıktılarını ağaç dışına | `PEMF_BUILD` · `launcher/target` · `pf/android/app/build` — birlikte 19,5 GB'dı |

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
| **9** | **Klasör düzeni** F1→F6 | 🟡 **F1a+F1b BİTTİ 2026-09-18**; kalan 5 alt faz bloke — aşağı bak |
| **10** | ~~**B4** dev dosya bölme~~ | ✅ **KAPANDI 2026-09-18** (sıradan önce yapıldı; ön şartı B1'di, o da bitmişti) |

> ### 🟡 Klasör düzeni — F1 BİTTİ, kalanların engelleri (2026-09-18)
>
> | Faz | Engel |
> |---|---|
> | ~~F1a `pemf-vet-web/`→`apps/web`~~ | ✅ **BİTTİ 2026-09-18** — sahip Vercel panosundaki `rootDirectory`yi güncelledi, taşıma yapıldı, `site-ci` + deploy yeşil |
> | ~~F1b `pf/`→`apps/ui`~~ | ✅ **BİTTİ 2026-09-18** — engel VS Code değil **Java** idi: `redhat.java` dil sunucusu + Gradle daemon'ları öldürülünce `git mv` geçti (editör kapatılmadı). ⚠️ Dizin adı **beş** ayrı biçimde geçiyordu; beşincisini (`build_mac.sh`teki yalın `cd pf`) hiçbir kapı görmedi → `tests/test_tasinmis_dizin_calisan_kodda_YOK.py` yazıldı |
> | F2 `launcher/` · F6 çıktılar | `launcher.yml` yolları sabit + yalnız `launcher-v*` etiketiyle koşar (**donmuş yayın**) → doğrulanamaz |
> | F3 `ai/hub` | **import kökü**: `ai_hub.` → `ai.hub.` 84 dosya + kod koruması (.pyd/PYZ) zinciri |
> | F3 `ai/service` | import kökü + `Dockerfile.ai` → doğrulaması **Docker imaj build'i** ister (metered kota) |
> | ~~F4 `apps/backend`~~ | ✅ **BİTTİ 2026-09-18.** Sahip kararı: **klasör taşındı, import kökü DEĞİŞMEDİ** (`from utils.x import y` aynen duruyor). Ölçülen gerekçe: tam paketleme (`pemf_backend.*`) 271 dosyada 1140 import ifadesi yeniden yazmayı ve PYZ/`hiddenimports`/kod-koruma zincirini yeniden ölçmeyi gerektirirdi; kazancı (üst-düzey `utils` adının global olmaması) ise **638 site-package arasında bugün HİÇBİR çarpışma olmadığı ölçüldüğü için** teorikti. Tesisat 4 yerde: `apps/backend/backend_service.py`, `tests/conftest.py`, iki spec `pathex`, + `pyproject` `package-dir`. ÖN ŞART (kök çıpası) da bitti 2026-09-18: 13 yerde depo kökü SABİT DERİNLİKLE (`parents[1]`) bulunuyordu; taşımada iki seviye kayar ve hepsi aday listesi olduğu için **sessizce** yanlış yola düşerdi (`bin/cloudflared`, 640 MB model, bulut sırrı, `VERSION`). Tek kaynak `kaynak_kokunu_bul(__file__)`; kapı `tests/test_kok_capasi_derinlikten_bagimsiz.py` (7 mutasyon) |
> | F5 `tools/` | 77 betiği amaca göre sınıflandırma; CI + bootstrap + pyproject |

> ### 🟡 BÜYÜK ÖLÇÜDE KAPANDI — ARALIKLI KIRMIZI: `test_anahtar_uyusmazligi_karantina`
>
> `test_KRITIK_TEDAVI_GECMISI_eski_anahtarda_backendi_OLDURMEZ` **tam süitte iki kez düştü**,
> ama tekrarlanmıyor. Ölçülenler:
>
> | Koşum | Sonuç |
> |---|---|
> | Tek başına (dosya) | ✅ 16/16 |
> | Alfabetik komşuluk (`test_ac*` + `test_ai_*` + `test_al*` + kendisi) | ✅ 386 passed |
> | Tam süit — 1. kez (F4 ÖNCESİ) | ❌ düştü |
> | Tam süit — 2. kez (F4 sonrası, ruff düzeltmesiyle) | ❌ düştü |
> | Tam süit — 3. kez (aynı ağaç, hemen ardından) | ✅ 3129 passed |
>
> ⚠️ **F4 taşımasının getirdiği bir şey DEĞİL** — ilk düşüş taşımadan önceydi ve bu turda
> dosyaya hiç dokunulmadı. `pytest-randomly` KURULU DEĞİL, yani sıra belirlenimci; dolayısıyla
> aralıklılık **sıradan değil, zamanlama/kaynak** kaynaklı (bu deponun bilinen daemon-bekçi
> sızıntısı sınıfı: `test_estop_bekci`, `test_ack_bekcisi` kayıtlarına bakın).
>
> ### 🔬 2026-09-19 AVI — ELENENLER (yarına devir; baştan kovalamayın)
>
> | Deney | Sonuç | Ne eledi |
> |---|---|---|
> | Tek başına | 16/16 ✅ | Testin kendisi bozuk değil |
> | 44 dosyalık **tam önek** (koşma sırası) | 395 ✅ | Önceki testlerin koşması TEK BAŞINA sebep değil |
> | **Tam toplama** + yalnız bu test (`-k`) | ✅ | Modül import yan etkileri TEK BAŞINA sebep değil |
> | `gc.collect` devre dışı + karantina | ✅ | ⚠️ "Tutamaç GC'ye kadar tutuluyor" hipotezi **YANLIŞ** |
>
> ⚠️ Kırılma için **hem tüm modüllerin import edilmesi hem önceki testlerin koşması** gerekiyor;
> `pytest-randomly` KURULU DEĞİL (sıra belirlenimci) → aralıklılık **zamanlama/kaynak** kaynaklı.
>
> ✅ **AV SIRASINDA BULUNAN GERÇEK ÜRÜN ARIZASI (kapandı, `d732b0f`)**: açık bir OKUYUCU
> karantinayı düşürüp cihazı tuğlalaştırıyordu (Windows). Bütçe 0,75 sn → 6 sn.
> Bu, aralıklı testi de sağlamlaştırmış **olabilir** ama KANITLANMADI — düzeltmeden sonra
> yalnız 2 yeşil tam koşum var, tarihsel oran 2/5 idi. **"Çözüldü" demek için kırmızının
> yeniden üretilip düzeldiğinin GÖRÜLMESİ gerekir.**
>
> ### 📊 2026-09-19 SONUÇ — 8 ARDIŞIK YEŞİL (kapatılmadı, ORAN daraltıldı)
>
> Düzeltmeden (`d732b0f`) sonra temiz ağaçla **6 tur** tam süit koşuldu; hepsi
> **3133 passed / 0 kırmızı** (12:06→12:44). Önceki 2 yeşille birlikte **8 ardışık**.
>
> | Dönem | Koşum | Kırmızı | Oran |
> |---|---|---|---|
> | Düzeltme ÖNCESİ | 5 | 2 | %40 |
> | Düzeltme SONRASI | 8 | 0 | 0 |
>
> ⚠️ **İSTATİSTİK DÜRÜST OKUNMALI.** Oran hâlâ %40 olsaydı 8 ardışık yeşilin olasılığı
> `0,6⁸ ≈ %1,7` — yani eski oran pratikte DIŞLANDI. Ama bu SIFIR demek DEĞİL: oran %10
> olsaydı 8 yeşil görme olasılığı %43'tür, veri bununla da tamamen uyumludur.
>
> ✅ **NEDENSEL ZİNCİR (yalnız korelasyon değil):** test tam da karantinanın OLUP
> OLMADIĞINA bakıyor → açık bir OKUYUCU'nun karantinayı düşürdüğü deterministik
> kanıtlandı → o dosyaya dokunan sızmış daemon'lar (`daily-maintenance` `shutil.copy2`,
> `sensor-persist`) conftest tarafından TEMİZLENMİYOR (yalnız `start-ack-*`/`estop-ack-*`
> temizleniyor) → bütçe genişletilince 8/8 yeşil.
>
> 📌 KALAN İŞ (düşük öncelik): conftest teardown'ı `_start_background_threads`'in açtığı
> daemon'ları da durdurmalı. Bu, nedensel zincirin SON halkasıdır; kapatmak için gerekli
> değil ama sınıfı tümden kaldırır. Kırmızı bir daha görülürse `--tb=long -rf` çıktısının
> TAMAMI saklanmalı (koşum sırasında depoya DOKUNMA — `inspect.getsource` satır kayması).

> ⚠️ **TEŞHİS EKSİK: yığın izi YOK.** İki düşüşte de çıktı `tail` ile kesilmişti. Bir sonraki
> tam süitte bu test düşerse **çıktının tamamı saklanmalı** (`--tb=long -rf > dosya`), yoksa
> aynı boşluğa yine düşülür. "Kararsız test" deyip geçmek bu depoda bir kez gerçek veri
> kaybına yol açtı (bkz. yarım göç kaydı).

> ### ✅ SINIF TARAMASI — "kurtarma yolunun KENDİSİ tuğlalaştırıyor" (2026-09-19, BİTTİ)
>
> Dünkü bulgu tek bir hata değil, bir SINIF işaret ediyordu. `apps/backend` altındaki
> kurtarma/yedek/göç adlı fonksiyonlarda **17 `raise` noktası** AST ile tarandı ve her biri
> çağrı yerinden ölçülerek sınıflandırıldı:
>
> | Desen | Yer | Karar |
> |---|---|---|
> | `karantinaya_al(...) is None` → `RuntimeError` | `treatment_history_db:538` · `patient_database:240` | 🔴 **TUĞLALAŞMA** — tek gerçek örnek, `d732b0f` ile kapandı (bütçe 0,75→6 sn) |
> | `_tasi_yeniden_dene` → `raise` | `sqlcipher_util:339` | ✅ **BİLEREK**: çağıran GERİ ALMA yapıyor (`:668-680` ölçüldü); düşerse orijinal yerine konur, o da düşerse operatöre "elle geri koyun" denir |
> | `get_sqlcipher_key` / `secrets_manager` fail-closed | 5 yer | ✅ **SAHİP KARARI** — sır çözülemeyince AÇILMAMAK kasıtlı (veri sağlam kalsın). DOKUNMA |
> | `ai_router._decode_image` vb. | 3 yer | ✅ İstek düzeyi hata, cihaz düzeyi değil |
>
> ⚠️ Bu sınıf depoda ÖNCE de görülmüş: `_tasi_yeniden_dene` docstring'i 2026-09-13'te
> `test_ikinci_acilis_yeniden_GOCMEZ`in aynı kilit/GC zamanlaması yüzünden aralıklarla
> düştüğünü kaydediyor. Yani "aralıklı test ← dosya kilidi" bu depoda tekrar eden bir desen.
>
> 📌 SONUÇ: başka tuğlalaşan kurtarma yolu YOK. Tarama tekrar edilmesin.

> ### 📌 LattePanda (saha makinesi) — UZAKTAN yapılabilir ölçümler · SONRAYA
>
> **Durum (sahip, 2026-09-18):** *"yayın öncesi firmware + main.c kodu var o cihazda,
> çalışır durumda"* → acil değil, sıraya alındı.
>
> ⚠️ **Ölçüldü (LattePanda'da koşturuldu):** CubeIDE 1.17.0 ile gelen **iki araç da yerinde** —
> `arm-none-eabi-gcc.exe` (gnu-tools-for-stm32 **12.3.rel1**) ve `STM32_Programmer_CLI.exe`
> (cubeprogrammer **win32_2.2.0**). Planın §2.1'i sahada doğrulandı.
> Klasör adları sürüm eki taşıyor → yol **sabit yazılamaz, glob ile aranır** (plan bunu söylüyordu).
>
> Sıra geldiğinde koşturulacaklar (hepsi tek komut, uzaktan analiz edilebilir):
>
> | # | Ne ölçer | Komut |
> |---|---|---|
> | 1 | **Sahadaki STM hangi firmware'i koşuyor** (kaç kanal) | `python scripts/stm_firmware_kimligi.py` |
> | 2 | Saha cihazının sağlık tablosu — sürüm · `stmUyumlu` · `atRestEncrypted` · `dbReady` · `tunnelUrl` | `curl http://127.0.0.1:8000/api/health` |
> | 3 | §4 Cloudflare NAMED tünel (hâlâ ⏳) | yukarıdaki `tunnelUrl` — ⚠️ backend **launcher'dan** açılmış olmalı, aksi hâlde ölçüm yanıltır |
> | 4 | ST-Link gerçekten görünüyor mu (yakma ön şartı) | `& $prog -l` (`$prog` = glob ile bulunan `STM32_Programmer_CLI.exe`) |
>
> ⚠️ **Uzaktan YAPILAMAZ:** §9 firmware `[FIX-1c]` duty geçişi tezgâh doğrulaması (osiloskop +
> akım probu) ve doz kalibrasyonu (manyetik alan ölçümü). Bunlar fiziksel.

**Sahip tarafı (bende yapılamaz):** A6 BLE eşleşme · S3 reflash · STM reflash + doz kalibrasyonu
(⚠️ tepe-tepe `pp_x = XP−XN`) · 164 senaryoluk saha listesi · Vault kurtarma setini makine dışına
alma · Cloudflare NAMED tünel · firmware satürasyon tezgâhı · 72 saatlik soak · iOS/EAS →
[`SAHA-ISLERI-REHBERI.md`](SAHA-ISLERI-REHBERI.md)

**Yayın:** ⛔ DONDURULDU — sahip "yayınla" demeden manifest/release koşturulmaz.

---

## ✅ Kapananlar — 2026-09-15 oturumu

| # | İş | Nasıl doğrulandı |
|---|---|---|
| **A3** | 12 commit push edildi, CI yeşil | `lint` · `security-audit` · `frontend-ci` · `critical-path-tests` dördü de yeşil. Yayın **yok** — release üreten üç workflow yalnız etiketle çalışıyor, ölçüldü |
| **A1b** | Bayrak adı ayrışması | Ortak `duz_metin_yedegi_emanete_al_mi()`; kanonik `PEMF_KEEP_PLAIN_BACKUP`, eski ad uyarıyla okunmaya devam. `device.env` + launcher `install.rs`. 6 mutasyon |
| **A1b-2** | ⛔ Hasta DB emanet yolu **fail-open**'dı + log yalan söylüyordu | `lock_down_file` dönüşü atılıyordu; ACL tutmasa bile korumasız `.plain.bak` diskte kalıyor, log "ACL-kilitli" diyordu. Davranışsal kapı + 4 mutasyon |
| **A1b-3** | Log seviyesi asimetrisi | Silme düşerse hasta DB `warning`+"önerilir" → `error`+"ELLE SİLİN" (tedavi DB ile eşitlendi) |
| **A1 (1/2)** | Yedek politikası kuyruğu tek fonksiyona | `goc_sonrasi_yedek_politikasi()`. 5 mutasyon |
| **A1 (2/2)** | Göç **gövdesi** tek uygulamaya | `treatment_history_db` artık delege ediyor. İki fonksiyon **357 → 161 satır**. 7 mutasyon |
| **C1** | `firmware_cikti/` yoksayıldı | `git check-ignore` + dosya-düzeyi istisnaların hâlâ sonda olduğu doğrulandı |
| **(yan)** | gitleaks Türkçe "API" yanlış alarmı | K-**API**-LANIYOR; muafiyet değer biçimine, 3 mutasyon |
| **(yan)** | jest 5 sn zaman aşımı soğuk CI'da yetmiyordu | `testTimeout: 20000` + üst sınır kapısı, 5 mutasyon |

**Ders:** denetim "göç kodu beş yerde" diyordu; ölçünce **tek gerçek kopya** çıktı ama o kopya
**üç ayrı yerden ayrışmıştı** ve üçü de denetimde görünmüyordu. Kopyalamanın maliyeti
"okuması zor" değil — **sessizce ayrışan davranış**.

**Bu oturumda kırılan 10 kapının hiçbiri silinmedi:** hepsinin niyeti korunup çıpası taşındı ve
taşınan çıpaların körleşmediği mutasyonla kanıtlandı.

### 2026-09-16 turu — A5 · B3 · B2

| # | İş | Ölçüm | Kapı |
|---|---|---|---|
| **A5** | `skip-worktree` koruması yalnız *restore* akışında uygulanıyordu; taze klon korumasızdı | Denetim §1.3'ün *"bayrağı kuran script yok"* iddiası **yanlıştı** — vardı, ama yalnız restore'da | `secrets_backup.py sir-korumasi` alt komutu + `bootstrap.ps1` 5c adımı · **6 mutasyon** |
| **B3** | README sürüm tablosu **üçüncü kez** bayatlamıştı (`1.9.5/1.9.9/2.3.3` ↔ gerçek `1.9.50/1.9.51/2.3.34`) | Aynı belgenin 47. satırı zaten *"bu belgeye sürüm yazılmaz"* diyordu. **Kural vardı, kapı yoktu** | `test_readme_surum_bayatlamaz.py` · **4 mutasyon** |
| **B2** | Atıf envanteri 50 sevk edilen bağımlılığın **36'sını** listelemiyordu (yalnız 26 satır) | Bayat değil **yapısal olarak eksik**: liste yalnız pakete bakıyordu, PyInstaller metadata'ları ayıklıyor | `scripts/lisans_envanteri_uret.py` üreteci + `test_notice_envanteri.py` · **4 mutasyon** |

**Yan bulgu (B2):** kopyleft kapısının ayrıştırıcısı `License-Expression`ı (PEP 639) okumuyordu —
sevk edilen pakette **100 paketin 30'unun** lisansı boş görünüyordu. ⚠️ Ölçüldü: bugün **hiçbir
kopyleft paketi gizlemiyor** (iki okuyucu da yalnız `ultralytics` buluyor), yani yaşanmış bir
ihlal değil, gelecek için açık bir delikti. Ayrıştırıcı tek yere alındı; kapı onu **import ediyor**.

**Yan bulgu (B2):** lisans kapılarının **tamamı** `base-deps.zip` yokken atlanıyor
(`pytestmark = skipif`) — yani temiz checkout'ta ve **CI'da hiç koşmuyorlar**. Yeni envanter
kapısı bilerek ayrı dosyada ve paketten bağımsız; kaynağı `requirements.txt`.

**Kapı yazarken kendi hatalarım (hepsi mutasyonla yakalandı):** A5'te çıpa iki kez metne
takıldı — `sir-korumasi` ve `--skip-worktree` sözcükleri *yardım metinlerinde* de geçtiği için
gerçek çağrı silinse bile kapı yeşil kalıyordu; ikisi de AST'ye/dize-soyulmuş koda pinlendi.
B3'te regex `127.0.0.1` IP'sini sürüm sandı ve sarılmış prozun ikinci satırı bağlamdan koptu.
B2'de yeni kapıyı yanlışlıkla `skipif`li dosyaya koymuştum — tam da CI'da atlanacaktı.

### 2026-09-17 turu — B1 · C4 · veri atfı · **üç denetim düzeltmesi**

Bu turun en önemli çıktısı yeni iş değil, **kendi denetimimdeki hataları ölçerek bulmak** oldu.

| # | İş | Sonuç |
|---|---|---|
| **B1** | Paket sınırları | `[project]` + `[build-system]` + 3 `__init__.py`. ⚠️ Sürüm **yazılmadı**, `VERSION`'dan türetildi (dördüncü kopya olurdu). `ai_hub` listeye **alınmadı** (84 MB + kod koruması kararı). Ürün doğrulaması: gerçek wheel üretildi — `pemf_backend-1.9.50-py3-none-any.whl`, 675 KB. **8 mutasyon** |
| **C4** | Bayat belgeler | Dört belgenin **üçünde iddia yanlıştı**: belgeler güncel, **etiketleri** bayattı. `frontend_version.json`'daki `date` alanı kaldırıldı — `sync_versions.ps1` onu hiç yazmıyordu, kalıcı yalandı. **5 mutasyon** |
| **veri atfı** | PhysioNet veri kümeleri | Dizin README'si + NOTICE'ta veri bölümü. Bölüm **üretecin önüne** konuldu; altına konsaydı bir sonraki koşuda sessizce silinirdi (üreteç gerçekten koşturulup doğrulandı). **4 mutasyon** |

**Düzeltilen üç denetim hatası (hepsi benim):**

1. **`ecg_signals.npy` KVKK riski** → **yanlış**. MIT-BIH (PhysioNet), PII yok. Gerçek açık **atıftı**: veriler kaynaksız yeniden dağıtılıyordu.
2. **"Silinecekler" listesi** → **altı dizinin beşi CANLI**. `frontend/` ürünün ana React arayüzü (`app.mount("/")`), `dema-terapi-simülatörü/` EXE'nin içinde. Tavsiyeye uyulsaydı ürün boş sayfa sunardı. **Silme yapılmadı**, kapı yazıldı, iki belge düzeltildi.
3. **"Bayat belgeler"** → üçünde iddia yanlış (yukarıda).

**Kök hata:** denetimde *"0 takipli dosya"* ve *"son commit eski"* ölçütlerini **ölü** ile eşitlemiştim. Üretilen çıktı dizinleri git'te görünmez ama ürün onları sunar; elle yazılan etiketler bayatlar ama belgenin kendisi güncel olabilir.

**Kapı yazarken kendi hatalarım (hepsi mutasyonla/CI ile yakalandı):** çıpa iki kez *yardım metnine* takıldı (A5) · regex `127.0.0.1`'i sürüm sandı, sarılmış proz bağlamdan koptu, "kapı hep boş dönsün" mutasyonu kaçtı (B3) · yeni kapıyı `skipif`li dosyaya koydum (B2) · `build-backend` silinmesi görünmedi (B1) · belge düzeltmesini "canlı" kelimesiyle aradım, bedavaya geçti (C3) · **üretilen çıktının varlığını şart koşup CI'ı kırdım** — öğrendiğim dersin tersi.
