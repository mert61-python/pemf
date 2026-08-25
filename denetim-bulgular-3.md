# PEMF Vet — Hata Denetimi 3. Tur (2026-08-24)

Kapsam: yalnızca **kırık davranış**. Önceki üç denetim (`denetim-bulgular.md` 2026-08-17,
`denetim-bulgular-2.md` 2026-08-19/22, `denetim-guncelleme-altyapisi-2026-08-23.md`) kapattığı ~120
bulgu tekrar raporlanmadı; düzeltmelerin KENDİSİNDE bulunan yeni kusurlar raporlandı (birçoğu).
Çürütülen bulgular (C13, M6, M9, M10, Y3, Y4, O1) yeniden açılmadı.

**Yöntem:** tek başına oryantasyon (üç denetim kaydı + BUILD/CHANGELOG + `git log --since=2026-08-17`,
85 commit) → **5 katman tarayıcısı** (backend · pf · launcher · firmware · build; 27 benzersiz
şüpheli) → **her şüpheli ayrı bir adversaryal çürütme ajanına** ("bu neden bug DEĞİL?", 13 ajan) →
katman-aşan izler + koşturmalar elle. Çürütme turu **1 şüpheliyi eledi, 13'ünü daralttı, 1'ini
"kasıtlı", 1'ini "doğrulanamadı" olarak ayırdı; 12'si AYAKTA**. Ölçülebilen her iddia
gömülü Python / SQLite / pytest ile koşturuldu. **Kod DEĞİŞTİRİLMEDİ.**

**En verimli av alanı — denetim SONRASI değişen kod (2026-08-20→24):** `bfbcf78`(1.9.18)·`48be404`
(.gitignore lib/ yutması)·`1c33e28`(2.3.20)·`8d8b99d`(18. parti)·`005ab66`(p2)·`d63ac7f`(1.9.19)·
`6e66940`(1.9.20=08-23 denetiminin 22 düzeltmesi)·`fa85ac7`(1.9.36 C5)·`4df79cc`(1.9.21 "Beni
hatırla")·`b36aca8`(1.9.22+2.3.23 AI Pro). Son iki yayın (`4df79cc`,`b36aca8`) HİÇBİR denetimden
geçmemişti — bulguların ağırlığı orada.

Ciddiyet: **1** hasta güvenliği · **2** veri kaybı/sır · **3** cihaz kullanılamaz · **4** yanlış
klinik çıktı · **5** diğer işlevsel.

---

## DÜZELTME KAYDI (2026-08-24 — 1. parti: [C1] + [F1]+[C6])

Yöntem önceki denetimlerle aynı: **her düzeltme için ayrı test, düzeltmeden ÖNCE kırmızı olduğu
görüldü, sonra yeşile alındı, ardından iki yönlü mutasyonla doğrulandı.** Kod DEĞİŞTİRME dışında
başka dosyaya dokunulmadı (Tauri codegen build artefaktları geri alındı).

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [C1] | C2 geri-alma döngü kırıcısı üretimde ölü: `check_runtime_update` komut JSON'u `otomatik_durduruldu`'yu UI'ya taşımıyordu (flow hesaplar + UI okur ama orta halka kopuk) | `launcher/app/src/main.rs` (JSON serileştirme saf `plan_to_json` yardımcısına çıkarıldı + bayrak eklendi) | `main.rs` birim testi `plan_to_json_otomatik_durduruldu_tasir` (DAVRANIŞSAL: üretilen JSON değeri + karşıt-kanıt) · `test_runtime_geri_alma_dongusu_bagli.py::test_KRITIK_3b_KOMUT_bayragi_UIya_TASIR` (zincir köprüsü) | Rust: `left:None` kırmızı → ✓ · Python: kırmızı → 8/8 ✓ | 2/2 ✓ (satır sil = `None` · koşulsuz `true` = karşıt-kanıt "normal güncelleme de bloklanır") |
| [F1] | P0 Inno E-stop karşıt-kanıt testi yanlış dilim ölçüyor (`k.find` ilk geçişi bir yorum satırı → install-yolu E-stop'unu kapsar); hiçbir zaman kırmızıya dönemez tautoloji | `tests/test_inno_kurulum_bobin_guvenligi.py` (`_uninstall_yordami` gerçek `procedure`'e çıpalandı; `_ESTOP_CAGRI` aranır) | aynı test | gerçek procedure'de E-stop yok → kırmızı → C6 sonrası 11/11 ✓ | (F1'in kanıtı C6 mutasyonuyla ortak) |
| [C6] | Backend KALDIRMA zincirinde bobin E-stop yok — backend servis-dışı koşarken (`Stop-Process -Force` sinyalsiz) `_safe_stop_outputs` koşmadan ölür, ESP 6-8 enerjili kalır | `build_tools/PEMF_Backend_Setup.iss` (`usUninstall` dalının EN BAŞINA, `setup_services.ps1` çağrılmadan ÖNCE `PemfBobinleriGuveneAl();` — kurulum yolu `ssInstall` simetrisi) | `test_inno_kod_derlenir.py` (ISCC ile `[Code]` GERÇEKTEN derlendi — çağrı geçerli/tanımlı yordam) | 1/1 ✓ | 1/1 ✓ (uninstall çağrısını sil → karşıt-kanıt kırmızı) |

**Bilinçli kararlar:**
- **[C1]** `plan_to_json` AYRI fonksiyon: `check_runtime_update` dosya-sistemine bağlı olduğundan
  birim testte zor; saf dönüşüm plan→JSON kablolamasını davranışsal test edilebilir kılar (memory
  kuralı: "varlık değil UYGULAMA ölç"). Python kapısı zinciri (flow hesaplar → **KOMUT taşır** → UI
  okur) metin düzeyinde bütünler; asıl kanıt Rust birim testinde.
- **[C6]** Kurulum yolundaki `PemfBobinleriGuveneAl` yordamı YENİDEN kullanıldı (kod tekrarı yok);
  port dosyasından E-stop POST + ~1800 ms bekleme, servisli/servissiz her iki durumu kapsar. Yordam
  `CurUninstallStepChanged`'den ÖNCE tanımlı (forward-reference sorunu yok — ISCC derlemesi teyit
  etti). Sessiz başarısızlık kabul (backend kapalıysa POST düşer); kaldırma hiçbir koşulda bloklanmaz.
- **[F1]** Düzeltilmiş test gerçek procedure'de E-stop bulamayınca C6'yı ZORUNLU kıldı — ikisi tek
  parti. `_uninstall_yordami` `procedure` anahtar sözcüğüyle başlar; E-stop yordam TANIMLARI ondan
  önce olduğundan dilime sızmaz (çağrının görünmesi için gerçekten orada olması gerekir).

**Regresyon:** launcher WORKSPACE **210 app + core/entegrasyon tüm süit yeşil**; ilgili Python
testleri **49 passed** (`test_inno_kod_derlenir` + `test_inno_kurulum_bobin_guvenligi` 11 +
`test_runtime_geri_alma_dongusu_bagli` 8 + `test_installer_korumali_ai_hub` + `test_uretici_kimligi`).

## DÜZELTME KAYDI (2026-08-24 — 2. parti: [E2] + [E3-a])

AI Pro hazırlık akışının `catDetected`/`kedi_var` zincirinin iki eksik halkası (aynı özellik,
`b36aca8`). Aynı disiplin.

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [E2] | `ai_pro_frame` HTTP yanıtı `catDetected` taşımıyordu → mobil hazırlık ekranı "hayvan görünüyor, organ aranıyor" aşamasını hiç gösteremiyor (mobil bu alanı YALNIZ /frame'den okur) | `servers/ai_router.py` (frame yanıtı cache'ten `kedi_var` okuyup `catDetected` alanı ekler) | `test_ai_pro_asamali_akis.py::test_KRITIK_kare_yaniti_asamayi_TASIR` (GERÇEK `ai_pro_frame` gövdesine çıpalandı — eski test `find` ile ilk WS geçişini ölçüp yanlış-yeşildi) | kırmızı → 20/20 ✓ | ✓ frame `catDetected` sil → kırmızı |
| [E3-a] | `_ai_pro_loop` `lkedi`yi çözüp ATIYORDU — cache'i yalnız mobil /frame yolu güncelliyordu → web/sunucu-kameralı seansta ws `catDetected` + 409 ipucu bayat (yanlış yönlendirme) | `servers/ai_router.py` (loop `cache.update`'e `kedi_var` — frame yolu paritesi) | `test_ai_pro_asamali_akis.py::test_KRITIK_her_cache_update_kedi_var_PARITE` (iki transport parite kapısı: her `_ai_organ_cache.update` `kedi_var` taşımalı) | kırmızı → ✓ | ✓ loop `kedi_var` sil → kırmızı |

**Bilinçli kararlar / dürüstlük notu:**
- **[E2] test** ilk yazımda yorumdaki "catDetected" kelimesini görüp bir mutasyonu KAÇIRDI (deponun
  1 numaralı hata deseni, kendi testimde) → JSON anahtar deseni `"catDetected":` aramaya
  sıkılaştırıldı; `test_KRITIK_durum_ucu_asamayi_TASIR` de aynı desenle tutarlılık için sertleştirildi.
- **pf tarafı DEĞİŞMEDİ:** panel `mobileResult?.catDetected`'i zaten okuyordu (`AiProPanel.tsx:482`),
  eksik olan backend'in alanı GÖNDERMESİYDİ. pf 5/5 + `tsc --noEmit` temiz.
- **[E3-b] tek-yönlü mandal AÇIK BIRAKILDI (ayrı iş):** kedi kadrajdan çıkınca `cat_organ`
  `RuntimeError("segmentasyon: ...")` atar → `_extract_organ_target`'a ulaşılmaz → `kedi_var` bir kez
  True olduysa istisna dalında False'a dönemez (loop `:905`, frame 500 yolu). Doğru düzeltme
  `catorgan_predictor.py`'nin segmentasyon-hatası (=kedi yok, `kedi_var=False`) ile pose/PnP-hatası
  (=kedi var, organ yok, `kedi_var=True` KORUNMALI) ayrımına bağlı; mesaj-string'e bağımlı (kırılgan)
  ve GPU/CPU yol asimetrisi taşıyor. E3-a sonrası ana akış (başarılı lokalizasyon) doğru; kalan yalnız
  "hedef kadrajdan çıkınca bayat yönlendirme" derece kaybı → sahip/sonraki parti kararına bırakıldı.

**Regresyon:** backend AI Pro süiti **53 passed** (`test_ai_pro_asamali_akis` 20 +
`test_ai_pro_approval_gate` + `test_kalan_regression_gaps`); pf `AiProPanel` 5/5 + `tsc` temiz.

## DÜZELTME KAYDI (2026-08-24 — 3. parti: [C3] + L7 çift-thread guard'ı)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [C3] | "Beni hatırla" düzeltmesi ÇALIŞAN backend'i sahiplenme yolunda (`start_installed` → `detect_running_backend`) rotasyon senkronunu HİÇ başlatmıyordu (`on_backend_ready` çağrılamaz — child yok) → o oturumun jeton dönmeleri diske işlenmez, sonraki açılışta SessionRevoked → "Beni hatırla" silinir | `launcher/app/src/main.rs` (sahiplenme dalına `oturum_rotasyon_senkronu_baslat(...)` + `AtomicBool` guard) | `test_oturum_rotasyonu_bagli.py::test_KRITIK_4_SAHIPLENILEN_backend_de_senkronlar` (sahiplenme dalı gövdesi senkron çağırmalı) | kırmızı → 11/11 ✓ | ✓ çağrı sil → kırmızı (`test_KRITIK_3` on_backend_ready ayrı çağrı olduğu için yeşil KALIR) |
| L7-guard | Sahiplenme dalı her Başlat'ta koşabildiğinden (`state.proc`a KOYULMAZ) naif ekleme thread biriktirirdi (L7 çift-thread) | aynı (`senkron_baslamali` saf compare_exchange guard'ı; thread bitince bayrak serbest) | `main.rs` birim testi `senkron_baslamali_cift_thread_onler` (DAVRANIŞSAL: ilk true / aktifken false / bitince yeniden true) + `test_KARSIT_KANIT_senkron_CIFT_thread_baslatmaz` | yeşil | ✓ guard hep-true → ikinci-çağrı-false kırmızı · guard sil → çağrı kapısı kırmızı |

**Bilinçli kararlar:**
- Guard `AtomicBool` + `compare_exchange` (atomik bir-kez): senkron BİR backend için tek thread.
  Thread bitince (backend öldü / 5 ardışık None) bayrak `store(false)` — sonraki backend (farklı
  port) için yeniden açılabilir; aksi halde guard bir daha hiç açılmaz ve rotasyon kalıcı dururdu.
- `on_backend_ready` sahiplenme dalında çağrılamaz (child gerektiriyor; süreci biz başlatmadık,
  `state.proc`a koymuyoruz — öldürme hakkımız yok); yalnız senkron thread'i başlatılır.
- Yan kazanç: guard, mevcut `install→repair` çift-`on_backend_ready` yolundaki (L7) thread
  birikimini de kapatır.
- ⚠️ [L3]'ün ikinci yarısı ("açılışta refresh'ten ÖNCE backend'ten pull denenmiyor") ve [F5]
  (teardown öncesi son pull yok) bu partide kapsam dışı — ayrı, daha küçük pencereler.

**Regresyon:** launcher WORKSPACE **tüm süit yeşil**; main.rs'e dokunan Python testleri
**97 passed** (`test_oturum_rotasyonu_bagli` 11 + kurulum-kilidi/runtime-döngü/sağlık-db/self-update/
kaldırma/periyodik/iptal/arkaplan/güncelleme-kilidi kümesi).

## DÜZELTME KAYDI (2026-08-24 — 4. parti: [E1] NACK yarısı)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [E1] | `/api/session/start` ESP dalı 18. parti ack-mimarisine BAĞLANMAMIŞTI (tekil+batch bağlıydı) → termal-kilitli 8266 seans-start'ı NACK'lerse (`command_error`) hayalet koşu kaydı seans boyu açık kalır, kapanışta TAM SÜRELİ mühürlenir (hiç koşmamış bobin tedavi geçmişine "koştu" yazılır) | `servers/api_server.py` (seans ESP döngüsüne `_register_ack` + `_start_ack_izle_arka_planda` — YALNIZ broker canlıyken) | `test_nack_gorunurlugu.py::test_KRITIK_SEANS_start_NACK_inde_de_kayit_kapanir` (davranışsal: NACK → koşu kaydı kapanır + operatör bildirimi) | kırmızı → 9/9 ✓ | ✓ bekçi bağlamayı sil → kırmızı |
| [E1]-karşıt | 8. parti bilinçli kararı (broker-ölü yarısı snappy-start + `esp_unreachable`) DEĞİŞMEMELİ | aynı (`_esp_broker_ok` guard'ı) | `test_KARSIT_KANIT_SEANS_broker_OLU_iken_bekci_baglanmaz` (broker ölü → `esp_unreachable` korunur, bekçi bağlanmaz) | yeşil | ✓ broker guard sil → `esp_unreachable` + çift-uyarı kırmızı |

**Bilinçli kararlar:**
- **8. parti kararı korundu** (çürütme turu doğruladı: broker-ölü yarısı bilinçli): publish
  fire-and-forget (snappy start) + koşulsuz `_begin_coil_run`. Bekçi YALNIZ broker canlıyken bağlanır
  — broker ölüyken NACK gelemez (publish gitmedi) ve `esp_unreachable` zaten uyarır; bekçi timeout'u
  çift-uyarı (alarm yorgunluğu) üretmesin.
- Ack TIMEOUT'unda kayıt KORUNUR (tekil yolla aynı: ack QoS-0, kayıp ack gerçek koşunun dozunu
  silmemeli); yalnız NACK (kesin red) koşu kaydını kapatır. `_broker_reachable()` tekilleştirildi
  (döngü + `esp_unreachable` tek ölçüm).
- **Test izolasyonu (dürüstlük notu):** yeni seans testleri `_active_session`'ı (modül-genel) açık
  bırakıp sonraki seans testlerine "Zaten aktif seans" (409) sızdırıyordu → `istemci` fixture'ına
  teardown eklendi (her testten sonra seans temizlenir).

**Regresyon:** `test_nack_gorunurlugu` 9 + `test_hayalet_kosu_kaydi` + `test_session_stop_dogrulama`
+ `test_esp_freq_clamp` + `test_estop_ack_benzersizligi` + `test_termal_olay_gorunurlugu` = **48 passed**;
`PEMF_SIMULATE=1 tools/e2e_smoke.py` **35/35** (gerçek seans başlatma akışı).

## DÜZELTME KAYDI (2026-08-24 — 5. parti: [C4] + [D1])

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [C4] | `app_katmanini_degistir` açılım hatasında iç geri-almanın sonucunu `let _ =` ile YUTUYORDU — geri koyma da düşerse (kilit/AV) UI "iptal edildi" derken cihaz DOĞRULANMAMIŞ/yarım app ağacıyla kalır ([3.1]'in dış yolda kapattığı desen, iç yolda açık) | `launcher/core/src/flow.rs` (geri-alma hatası açık "GERI ALINAMADI… 'Onar' calistirin"e YÜKSELTİLİR — dış yol simetrisi) | `flow.rs` birim testi `C4_app_ic_yol_geri_alma_DUSERSE_hata_yutulmaz` (`#[cfg(windows)]`, TATBİKAT 5 tekniği: yedekteki dosyaya açık handle → geri-alma `rename` düşer) | kırmızı (Cancelled maskesi) → 211/211 ✓ | ✓ yükseltme bloğunu kaldır (yut) → kırmızı |
| [D1] | Kapanmış seans buluta HİÇ gitmiyor: (a) `end_session` `sync_status`'u 0'a çekmiyordu → aktifken push edilmiş (worker 60 sn → sync_status=1) seansın kapanışını sonraki PUSH ('WHERE sync_status=0') hiç görmez; (b) PULL koşulsuz `sync_status=1` korunan kapanışın PUSH bayrağını siliyordu | `database/treatment_history_db.py` (`end_session` → `sync_status=0`) · `servers/sync_worker.py` (PULL: korunan kapanışta `sync_status` CASE-korumalı) | `test_sync_pull_bayat_active.py::test_KRITIK_D1_kapanis_sync_status_SIFIRLAR` + `test_KRITIK_D1_bayat_active_PULL_PUSH_bayragini_SILMEZ` (PUSH-başarısız senaryosu) | 2 kırmızı → 4/4 ✓ | 2/2 ✓ (a: `sync_status=0` sil · b: CASE→koşulsuz 1) |

**Bilinçli kararlar:**
- **[C4]** İç yol dış yolla (`profilleri_yenile`, [3.1]) BİREBİR simetrik yükseltilir; `runtime.old`
  fail-safe'i etkilenmez (bu dalda tüketilmez). Test `#[cfg(windows)]` (açık-handle semantiği; CI
  launcher windows-latest, üretim platformu Windows).
- **[D1]** Latent (`PEMF_CLOUD_PATIENT_SYNC` varsayılan KAPALI); çürütme turu (a)'yı asıl kök,
  (b)'yi "ölçülmüş savunma açığı ama bugün kurgusal" saymıştı. (a) çekirdeği kapatır; (b) PUSH
  **başarısız** olduğunda (ağ hatası — sık) kapanışın yeniden-PUSH'unu korur (CASE simetrisi). D1-b
  testi bu gerçekçi senaryoyu (`_PushHatali` upsert RPC hatası) kurar. Monotonik-kapanış koruması
  (mevcut CASE'ler) bozulmadı — karşıt-kanıt testleri yeşil.

**Regresyon:** launcher WORKSPACE **core lib 211 + tüm süit yeşil**; backend seans-kapanış/kurtarma/
audit/backup **30 passed** + sync/migration **13 passed**; `PEMF_SIMULATE=1 tools/e2e_smoke.py` **35/35**.

## DÜZELTME KAYDI (2026-08-24 — 6. parti: [C2] + [D3])

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [C2] | `update_installed` İÇİNDEKİ deterministik hatalar (kilitli model/AV/eksik-exe/bozuk manifest) deneme sayacını yazmıyordu → o sınıf döngü kırıcısına ([C1]/`otomatik_durduruldu`) hiç takılmadan her açılışta backend'i öldürüp ~1,19 GB açıp geri alıyordu | `launcher/core/src/flow.rs` (`hata_deterministik_mi` saf sınıflandırıcı) · `launcher/app/src/main.rs` (Err dalı: deterministikse `geri_almayi_kaydet`) | `flow.rs` birim testi `hata_deterministik_mi_dogru_siniflar` (DAVRANIŞSAL: varyant sınıflandırma) · `test_runtime_geri_alma_dongusu_bagli.py::test_KRITIK_1b_IC_YOL` (Err dalına çıpalı bağlanma kapısı) | kırmızı → 9/9 + 212/212 ✓ | ✓ Err-dalı sayacı sil → kırmızı · geçici-ağ'ı say → karşıt-kanıt kırmızı |
| [D3] | `secrets_backup._git_sir_korumasi` git-128 (dubious ownership — taze klonda yaygın) ile returncode 1 (gerçek untracked) ayırt etmiyordu; 128'i "izlenmiyor" sayıp SESSİZCE geçiyordu → safe.directory düzeltilip `git add -A` yapılınca gerçek sırlar PUBLIC repoya stage'lenir + "git düşerse yüksek sesle uyar" sözleşmesi ihlali | `build_tools/secrets_backup.py` (repo-var kapısı + `returncode != 1` = git düştü → YÜKSEK SESLE uyar) | `test_secrets_backup_git_korumasi.py::test_KRITIK_D3_git_128...` + `test_KARSIT_KANIT_D3_gercek_untracked_SESSIZ` | 1 kırmızı → 7/7 + 1 skip ✓ | 2/2 ✓ (128 ayrımı sil · `!=1`→`!=0` kör sayım) |

**Bilinçli kararlar:**
- **[C2]** Cancel/Pause (`apply_runtime_update` zaten önce ayırır) ve GEÇİCİ ağ hataları
  (`is_retriable` — yeniden denenir) SAYILMAZ: kör sayım kullanıcı iptalini döngü-kırıcıya saydırır
  ya da tek ağ hatası düzeltme yayınını kalıcı bloklardı. Sağlık-kapısı geri alması (main.rs:884/906)
  ayrı yol (Ok → sağlıksız) — çift-sayma yok. Kapı test **Err(e) dalına çıpalı** (geniş pencere
  sağlık-kapısı çağrılarını kapsayıp mutasyonu kaçırırdı — dürüstlük notu).
- **[D3]** `returncode 1` = git çalıştı, gerçekten untracked → risk yok, sessiz (karşıt-kanıt);
  `128` vb. = git düştü → uyar. Repo-var kapısı (`.git` yok → sessiz) mevcut "repo değilse sessiz"
  karşıt-kanıtını korur. Gitleaks özel kuralları (2. kemer) etkilenmedi (17 passed).

**Regresyon:** launcher WORKSPACE **core lib 212 + tüm süit yeşil**; backend `secrets_backup`
kümesi **17 passed** (+1 skip: gitleaks binarisi yok).

## DÜZELTME KAYDI (2026-08-24 — 7. parti: [D2] + [C7])

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [D2] | NACK bekçisi `_finish_coil_run(coil_id)` ile o an açık HANGİ run varsa kapatıyordu (command/run eşlemesi YOK) → aynı bobine hızlı çift-start'ta start#1'in GECİKEN NACK'i, araya giren KABUL edilmiş start#2'nin ÇALIŞAN koşusunu düşürüyor + "bobin çalışmıyor" yanlış bildirim | `servers/coil_run_tracker.py` (`_finish_coil_run(only_run_id=None)`) · `servers/api_server.py` (`_start_ack_watch`/`_start_ack_izle_arka_planda` run_id taşır; tekil/batch/seans ESP çağrıları `_begin_coil_run` sonrası run'ı yakalar) | `test_nack_gorunurlugu.py::test_KRITIK_D2_geciken_NACK_araya_giren_kosuyu_KAPATMAZ` (davranışsal: çift-start + geciken NACK → araya giren run KORUNUR) | kırmızı → 10/10 ✓ | 2/2 ✓ (only_run_id koruması sil · run_id yakalamayı None yap) |
| [C7] | Yayın runbook'u §6 launcher `gh release create` satırı sürümsüz `PEMFVetClient-Setup.exe`'yi DEPO KÖKÜNDEN alıyordu (APK ise `release_assets\` önekli — asimetri); kökte bayat kopya (gitignore'lu, hiçbir build tazelemiyor) → harfiyen izlenirse aynı etikete bayat launcher, manifest sha taze kopyadan → saha self-update fail-closed 404 | `BUILD.md` §6 (sürümsüz Setup.exe de `release_assets\`'ten — APK ile simetrik + gerekçe yorumu) | `test_yayin_runbook_etiketi.py::test_KRITIK_C7_runbook_surumsuz_EXE_release_assets_ten_alinir` | kırmızı → 5/5 ✓ | ✓ kök EXE'ye geri döndür → kırmızı |

**Bilinçli kararlar:**
- **run_id eşleşmesi** (command_id değil): bekçi başlatıldığı andaki `_active_coil_runs.get(coil_id)`'yi
  taşır; NACK yalnız o run hâlâ açıksa kapatır. `_begin_coil_run` imzası DEĞİŞMEDİ (en az invaziv);
  `only_run_id=None` (stop/begin-içi-kapatma/seans-finalize) mevcut koşulsuz davranışı korur.
- **Kapsam D2'nin (b) kısmı:** "geciken/bayat NACK yanlış run'ı kapatır" — BE-S4'ün ana ifadesi.
  Çürütme turunun işaret ettiği (a) [optimistic `_begin_coil_run`, start#2 NACK'lenince koşu#1 geri
  açılmaz] AYRI/daha derin bir mimari konu; seans-düzeyi doz dakika-akümülatöründe korunuyor (çürütme
  turu doğruladı), zarar koşu-düzeyi atıf. Tekil-start NACK karşıt-kanıtları (kendi run'ını kapatır)
  bozulmadı — 10/10.

**[C7] dürüstlük notu:** test ilk yazımda `cat >> heredoc` ile eklendi ve `[\\/]` regex'i heredoc
ters-bölü çökmesiyle `[\/]`e bozuldu (yalnız slash eşleşir, backslash değil) → düzeltme sonrası bile
yanlış-kırmızı verdi. Memory'deki bilinen tuzak ([[bash-heredoc-ters-bolu-cokmesi]]); Edit ile
düzeltildi. Kök bayat EXE (gitignore'lu, referanssız) SİLİNMEDİ — runbook düzeltmesi tuzağı zaten
kaldırır (satır artık release_assets kullanır); dosya silmenin riski > kazanım.

**Regresyon:** `test_nack_gorunurlugu`+`test_hayalet_kosu_kaydi`+`test_coil_run_tracker`+
`test_session_stop_dogrulama`+`test_estop_ack_benzersizligi` = **37 passed**; `e2e_smoke` **35/35**;
`test_yayin_runbook_etiketi`+`test_site_indirme_varligi_URETILDI` = **13 passed**.

## DÜZELTME KAYDI (2026-08-24 — 8. parti: [F7])

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [F7] | pre-commit `check_changelog_surum.py` ham `s not in metin` (substring); CI (`test_version_visibility`) 2026-08-23'te kanal-başlıklı regex'e sertleşti — betiğin kendi docstring'i "birebir aynı tutulur" der ama ayrışmıştı → cross-kanal sürüm (backend, mevcut launcher numarasına çekilince) pre-commit yanlış-yeşil, hata push'tan sonra CI'da ("Run failed e-postasından önce yakala" kaybı) | `scripts/check_changelog_surum.py` (saf `_eksik_kanallar` — CI ile BİREBİR kanal-başlıklı regex; `backend`→`app` eşlemesi) | `test_version_visibility.py::test_KRITIK_F7_pre_commit_kancasi_CI_ile_BIREBIR_kanal_basligi` (cross-kanal reddedilir + kendi-başlık karşıt-kanıtı) | kırmızı → 13/13 ✓ · gerçek CHANGELOG exit=0 | ✓ regex→ham substring → cross-kanal geçer → kırmızı |

**Bilinçli kararlar:** mantık CI kapısıyla **birebir** (deponun kendi "mantık test ile birebir tutulur"
değişmezi — `test_lint_muafiyet_tutarliligi` hikâyesi); saf `_eksik_kanallar` hem betik hem test
tarafından çağrılabilir. CI yedek kapısı bozulmadı (13 passed). ⚠️ Mutasyonu inline `python -c` ile
uygularken yine ters-bölü escape sorunu — geçici script dosyasıyla yapıldı ([[bash-heredoc-ters-bolu-cokmesi]]).

## DÜZELTME KAYDI (2026-08-24 — 9. parti: [F6] + [F4] + [E3-b] + [F2], tasarım-workflow destekli)

Kalan bulgular için önce paralel bir Workflow düzeltme-tasarımı çıkarıldı (fizibilite + en-temiz-
düzeltme + kırmızı-önce test + mutasyon planı), sonra TAM doğrulanabilir 4'ü seri uygulandı.

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [F6] | `secret_store::save` düz `fs::write` (atomik değil); rotasyonla yazma saatte ~1'e çıktı → yazım anında elektrik/kill SAĞLAM blob'u bozar → açılışta `None` → parola | `launcher/core/src/secret_store.rs` (tmp aynı dizinde + `fs::rename`; `gecici_blob_path` helper) | `yarim_yazim_ESKI_oturumu_BOZMAZ` + `gecici_yol_install_root_icinde` + `basarili_save_sonrasi_tmp_kalmaz` (davranışsal: tmp-yolu DİZİN yaparak yazımı bloke) | 1 kırmızı → 6/6 ✓ | 2/2 ✓ (atomik→düz write · tmp→temp_dir cross-volume) |
| [F4] | Rotasyon thread "backend meşgul (5 sn timeout)" ile "kesin ölü (refused)"yu ayırmıyordu → uzun AI yükünde 5 meşgul-yoklama thread'i öldürür, o oturumun rotasyonları kaçar ("Beni hatırla" aralıklı) | `launcher/app/src/main.rs` (`rotasyon_ardisik` saf karar + döngü None dalında `backend_is_definitely_gone`) | `rotasyon_ardisik_mesgulu_oldurmez` (DAVRANIŞSAL: meşgul→sıfırla/asla-çık, kesin-ölü→eşikte-çık) | yeşil | ✓ kesin_olu ayrımını sil (her None say) → kırmızı |
| [E3-b] | AI Pro tek-yönlü mandal: kedi çıkınca `cat_organ` `RuntimeError("segmentasyon:")` → `_extract_organ_target`'a ulaşılmaz → `kedi_var` False'a dönemez → bayat yönlendirme | `servers/ai_router.py` (`_is_cat_absent_error` + `_localize_organ_cpu` segmentasyon-hatasında temiz `(localized=False, kedi_var=False)` tuple; pose/PnP YUKARI fırlar) | `test_ai_pro_kedi_yok_mandal.py` (kedi-yok→temiz False + karşıt-kanıt: PnP→raise, kedi_var korunur) | 1 kırmızı → 2/2 ✓ | 2/2 ✓ (kedi-yok yakalamayı sil→raise · hepsini yut→karşıt-kanıt) |
| [F2] | AI Pro "ARDISIK_ONAY=2 (iki tutarlı ölçüm)" YAPISAL BOŞ: lokalizasyon 10 sn'de bir, kareler 1,5 sn → aynı ölçümün ekosu; sayaç tek ölçümle 2'ye ulaşıp öneriyi tetikliyor ("tek şanslı kare" koruması boş) | `servers/ai_router.py` (`/frame` yanıtına lokalizasyon damgası `localizedAt`=cache `at`, eko-kararlı) · `pf/.../AiProPanel.tsx` (`sonDamgaRef`; ardisik yalnız YENİ damgada artar; 4 reset noktası) | backend `test_ai_pro_lokalize_damgasi.py` (damga + eko-kararlılık) · pf `AiProPanelSahiplik.test.tsx` (+2: eko→propose YOK, yeni damga→propose VAR) | backend kırmızı → 1/1 ✓ · pf 7/7 ✓ | backend 2/2 (localizedAt sil · at→now) · pf ✓ (damga kapısı sök→eko sayılır) |

**Bilinçli kararlar:**
- **[E3-b]** iki varyant vardı; ai_hub'a (korumalı katman) dokunmamak için **string-prefix**
  (`"segmentasyon:"`, 1 dosya) seçildi — typed-exception (`catorgan_predictor.py`'ye `CatNotDetected`)
  daha temiz ama +1 dosya. GPU-only asimetrisi (ai_service `_err500` mesajı maskeler) ayrı YAPISAL iş
  (Docker/CI); CPU-fallback dağıtımlarını fix kapsıyor. pose/PnP → raise (kedi_var korunur, doğru).
- **[F2]** damga = cache `at` (bir ÖLÇÜMÜN kimliği), istek-başı `now` değil → eko-kareler aynı damga.
  Geriye-uyum: eski backend damga göndermezse pf kare-başı sayıma düşer (kilitlenme yok). UX: iki onay
  ~10 sn (HAZIRLIK_TAVAN 120 sn içinde). Web etkilenmez (ardisik mobil-only). Sahip-kararı çelişkisi
  yok (panel yorumları zaten bu sertleştirmeyi vaat ediyordu).

**Regresyon:** launcher WORKSPACE **core lib 215 + app 18 + tüm süit yeşil**; backend AI Pro
**55 passed** + `test_ai_pro_lokalize_damgasi` + `test_ai_pro_kedi_yok_mandal`; pf **AiProPanel 5/5 +
AiProPanelSahiplik 7/7** + `tsc --noEmit` temiz.

## DÜZELTME KAYDI (2026-08-25 — 10. parti: firmware [E4] + [B2] + [B3] + [D4], YAPISAL_MODEL disiplini)

Dört firmware bulgusu **denetim-bulgular-2 §14 disipliniyle** uygulandı: her biri (a) davranışsal
Python durum-makinesi/adres modeli (kırmızı-önce + `bug` toggle bug'ı ÜRETİYOR), (b) yorum-soyulmuş
(`c_soy`) yapısal kapı, (c) iki-yönlü mutasyon ve (d) **adversaryal C-inceleme Workflow'u** (bu makinede
C derleyicisi yok → 3 bağımsız lens: eşzamanlılık/değişmez/syntax). ⚠️ **Gerçek C davranışı hâlâ tezgah
+ REFLASH + skopla doğrulanmalı** — model/kapı yalnız algoritmayı ve kaynağın onu taşıdığını kanıtlar.

| # | Bulgu | Dosya(lar) | Test (model + yapısal kapı) | Önce → Sonra | Mutasyon · C-inceleme |
|---|---|---|---|---|---|
| [E4] | S3 faz-kilidi START'ta hiçbir ortak-epoch'a hizalanmıyor (`s_tick` yalnız iki ISR'da yazılır); aynı frekanslı ama SABİT faz-ofsetli STM/ESP çifti tolerans penceresine hiç giremez → darbe hep 'ignored' → çok-bobin faz deseni yanlış | `firmware/esps3_pemf_coil/CoilController.cpp` (`s_awaiting_acquire`: seans başı/freq değişimi → İLK PB1 darbesi `s_tick=0` ile faz kilidini EDİNİR; kapılardan SONRA → HG-3/[4.3] korunur) | `tests/test_s3_sync_dc_yapisma.py` (`_SyncModel`+edinim; sabit-ofset→ilk darbede kilit; ayrıştırıcı) | 4 kırmızı → 16/16 ✓ | 3/3 (model arm sil · C arm sil · sıra boz) · C-inceleme **3/3 sound** |
| [B2] | 8266 çalışırken-kopuşta kayıtlı ağları DENEMEDEN ilk retry'de portal açıyor (STA ölür) + portal timeout kaldırılmış → hotspot dönse de SONSUZA AP-only | `firmware/esp8266_pemf_coil/NetworkManager.cpp`+`.h` (`_hasSavedCredentials`; ilk-retry kredi-kapılı; tükenmede portal; kredi-kapılı portal-timeout; FSM hardening) | `test_esp8266_portal_ozilesme_model.py` (FSM: buggy sonsuz offline / fixed toparlar) + `test_esp8266_portal_ozilesme.py` (yapısal) | 4+2 kırmızı → 12/12 ✓ | 3/3 (kredi-kapı sil · portal-timeout sil · PLAN-A stopPWM enjekte) · C-inceleme **3/3 sound** |
| [B3] | 8266 buluta göçünce yerele DÖNMÜYOR: `_reconnectMQTT` cloud-başarı + çift-başarısızlık sayaç reset yok (MAX'ta takılır) + geri-dönüş probe'u yok | `firmware/esp8266_pemf_coil/NetworkManager.cpp` (BROKER_CLOUD iken 15 sn'de bir yerel plain probe + 2 sayaç reset) | `test_8266_broker_geri_donus.py` (MQTT FSM: buggy sonsuz cloud/None / fixed LOCAL'e döner + yapısal) | 2 kırmızı → 9/9 ✓ | 2/2 (cloud-reset sil · probe sil) · C-inceleme **1 BLOCKER** (aşağıda) → düzeltildi → yeniden-inceleme **sound** |
| [D4] | 8266 EEPROM non-WiFi adresleri (PWM 256/BROKER 300/CONFIG_VER 304) WiFi bölgesi [0,495) İÇİNDE → 30 sn savePWMState kayıtlı WiFi'yi bozar, portal yazımı CONFIG_VER'i örtüp wipe döngüsü tetikler | `SharedDefs.h` (blok ≥512'ye taşındı + `EEPROM_WIFI_REGION_END`) · `.ino` (wipe tüm WiFi bölgesi) · `NetworkManager.cpp` (clearAll WiFi bölgesiyle sınırlı) · `Secrets.h` (CONFIG_VERSION 1→2) | `test_esp8266_eeprom_harita_cakismasi.py` (adres modeli + `c_soy` yapısal + ayrıştırıcı) | 6 kırmızı → 10/10 ✓ | 4/4 (adres geri-al · CONFIG_VER≥1024 · wipe→256 · clearAll→EEPROM_SIZE) · C-inceleme **3/3 sound** |

**⚠️ [B3] adversaryal C-inceleme BLOCKER'ı (bulundu → düzeltildi):** probe `probeClient.connect()` VARSAYILAN
5000 ms timeout'la kooperatif loop'u ~5 sn bloklayabiliyordu (yerel sessiz-drop) → o sürede `_mqttClient.loop()`
servis edilmez → **bulut E-stop aynası ~5 sn geciker (hasta-güvenliği-bitişik)**. Üç lens de bağımsız işaretledi.
Düzeltme: `probeClient.setTimeout(400)` (worst-case blok ~0,4 sn); yapısal kapı `setTimeout < connect` ile kilitlendi.
**Residual (MINOR, tezgah-izle):** yerel port TCP kabul edip MQTT reddederse (broker açılış penceresi) 15 sn'lik
churn olabilir (S3 paritesiyle aynı, kendini iyileştirir) — brick/güvenlik değil.

**⚠️ Hepsi için tezgah ZORUNLU:** [E4] 2 bobin aynı freq + faz farkı → skop; [B2] reflash→gateway reboot→AP-only'de
takılmıyor + portalsız toparlıyor; [B3] failover→failback + BearSSL heap headroom; [D4] reflash sonrası tek-seferlik
WiFi wipe + savePWMState artık WiFi bozmuyor + yeni adreste PWM-resume çalışıyor. [D4] en riskli (mevcut kurulumların
layout'u değişir; portal-kurulu cihazlar WiFi'yi BİR KEZ yeniden girer — sahip-yüzlü, kabul edilen migrasyon).

### ⚠️ Test-çıpa bakımı (bu partinin refaktörlerinden düşen 2 yapısal kapı — davranış regresyonu DEĞİL)
Tam süit taraması iki yapısal testin çıpasının kaydığını buldu (değişmez korunuyor, yalnız metin-çıpa kaymış):
`test_mt_dose_honesty::test_KRITIK_ESP_komutu_mT_TASIMIYOR` ([E1] `command_id`'yi değişkene çıkardı →
çıpa `mqtt_payload` dict'ine yeniden pinlendi) ve `test_oturum_rotasyonu_bagli::test_KRITIK_3_launcher_diske_ISLER`
([F4] doc-comment adı metinde daha önce anıyor → çıpa `pull_desktop_session(port)` gerçek çağrısına pinlendi).
İkisi de düzeltildi; korudukları değişmezler (ESP komutu mT taşımaz · okunan oturum diske işlenir) sürüyor.
**Tam backend süiti: 1743 passed + 2 skipped, 0 fail.**

## DÜZELTME KAYDI (2026-08-25 — 11. parti: [F5] + [B1], tasarım-vetting + adversaryal-inceleme destekli)

Kullanıcı reflash/derleme doğrulamasını ÜSTLENDİ (makinede ESP derleyicisi var) → firmware tezgah-kuyruğu
kullanıcıya geçti. Bu partide iki TAM-doğrulanabilir bulgu uygulandı: [F5] (launcher/Rust, cargo) ve [B1]
(backend + pf/mobil). [B1] güvenlik-değişmezi/sahip-kararı içerdiğinden ÖNCE 4-lensli adversaryal tasarım-
vetting Workflow'u koşuldu (`decision_consistent: true`, 2 MAJOR iyileştirme benimsendi).

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon · İnceleme |
|---|---|---|---|---|---|
| [F5] | Hiçbir teardown yolunda kapanış-öncesi son pull yok → ≤60 sn rotasyon penceresi diske bayat kalır (SessionRevoked → parola) | `core/src/backend.rs` (`pull_desktop_session_kisa` + `PULL_TEARDOWN_TIMEOUT_S=2`) · `app/src/main.rs` (`son_oturumu_yakala` + 2 çağrı: teardown tracked + Destroyed job; E-stop SONRASI/kill ÖNCESİ; orphan HARİÇ) | core `pull_teardown_kisa...` (STALL'da ≈1sn) + app `f5_kapanis_sirasi...` (yorum-soyulmuş sıra kapısı) | core 1✓ · app 1✓ | 3/3 (sıra swap · timeout hardcode · orphan'a ekle) |
| [B1] | AI Pro kare/istek sahipliği: izleyici istemci kendi kamerasından bobin sürüyor + cache kirletiyor + onaylanmamış organa geçebiliyor + "Already running"→ownedRef drift | `servers/ai_router.py` (`_ai_kare_yabanci` deny-only; frame localize+drive+overlay kapısı; /organ + /calibrate 403; start ownerClientId) · `pf/.../AiProPanel.tsx` (client_id → /frame /organ /calibrate; ownedRef=ownerClientId===benim) | backend `test_ai_pro_sahiplik_kare.py` (10) · pf `AiProPanelB1.test.tsx` (4) | 6🔴/5🔴 → 10✓/4✓ | backend 4/4 · pf 1/1 |

**Bilinçli tasarım kararları (kayıtlı sahip-kararına UYGUN):** YABANCI = `bool(_ai_owner_client) and
client!=owner` (deny-only). ⚠️ Vetting **Hole 1**: `bool(frame_client)` şartı KASITEN YOK — kimliksiz kare
de yabancı sayılır (yoksa alan atlayan izleyici bastırmayı baypaslardı; modern sahip kendi karesinde hep
id taşır → yanlış-bastırma yok). ⚠️ Vetting **Hole 2**: /organ + /calibrate de gate'lendi (izleyici mid-
seans onaylanmamış organa geçemez). Sahip boşsa (eski/anonim) hiç bastırma yok (geriye-uyum). `/ai/pro/stop`
GÖVDESİZ + AÇIK kaldı, mühür (D/P/organ/süre) değişmedi → **yeni yetki verilmedi**. Test-boşluğu kapatıldı:
sahip ÖNCEDEN localize etmiş cache'ten yabancı kare sürüşü ayrı test (`..._ONCEDEN_lokalize_cache...`) —
`need_localize` gate'i TEK BAŞINA yetmez, drive-gate `not is_foreign` şart.

**Adversaryal KOD-inceleme (3 lens, uygulama sonrası) — 1 MAJOR bulundu → düzeltildi:**
- ⚠️ **MAJOR (düzeltildi):** `_ai_owner_client` YALNIZ /ai/pro/stop tarafından sıfırlanıyordu; süre-dolumu /
  acil-durdur / dış /session/stop ile biten seansta STALE kalıp BAŞKA modern istemciyi AI Pro'dan KALICI
  kilitliyordu (yabancı→localize yok→propose 409→owner'ı ezecek /start'a ulaşamaz). **Fix:** `_ai_kare_yabanci`
  bastırmayı YALNIZ aktif sahipli seansta (`_active_session.is_active` + mode AI) uygular → seans bitince
  owner stale kalsa da bastırma yok. Kilit: `test_..._seans_BITINCE_stale_owner_KILITLEMEZ` (kırmızı→yeşil).
- **minor (düzeltildi):** start ownedRef formülü boş ownerClientId'yi status-poll ile AYNI ele almalı
  (`!!owner`) — ıraksama sahibin unmount /stop'unu atlayabilirdi. · **minor (düzeltildi, F5):** `son_oturumu_yakala`
  + 60 sn rotasyon thread'i aynı pid-tmp'ye eşzamanlı yazabiliyordu (F6 atomikliği tek-yazar varsayar) →
  `secret_store::save`'e `SAVE_KILIDI` mutex'i eklendi (yol deterministik kaldı, F6 testleri yeşil).
- **KABUL EDİLEN sınırlar (belge):** (a) depo-erişimi bozulmuş yeniden-yüklemede `getClientInstanceId` yeni
  rastgele id üretir → meşru sahip kendi seansında /organ /calibrate 403 (nadir + güvenli-bozunum: /stop
  açık); (b) yabancı-istemci 403'te çift-uyarı + mobil start calibrate-403'ü yok sayıp hazırlığa girer
  (yalnız YABANCI, sahibi/güvenliği etkilemez).

**MAJOR-fix yeniden-inceleme (tek ajan): `resolved: true`** — üç bitiş yolu (süre/acil/dış-stop) lockout'u
kapandı, aktif-seans koruması + yarış-yokluğu teyit edildi. **Kalan dar boşluk (aynı sınıf, REGRESYON DEĞİL —
eski kod kesinlikle daha kötüydü):** `_ai_pro_loop` başlarken çökerse (kamera açılamaz / model yüklenemez)
erken-dönüş `is_active`'i STALE-TRUE bırakır → gate hâlâ başkalarını bastırır (WEB seansında, mobil-kare yokken).
⚠️ İnceleyenin önerisi (loop erken-dönüşünde is_active=False) MOBİLİ BOZAR: kamerasız klinik backend'inde loop'un
çökmesi NORMAL'dir ve telefon /frame yolu meşru olarak is_active üzerinden sürer → is_active'i öldürmek mobil AI
Pro'yu tümden kapatır, owner'ı temizlemek mobil B1 korumasını deler. Bu yüzden loop'ta güvenle kapatılamaz;
Hole 4 ile AYNI mimari-pass'i (backend-loop vs mobil-/frame ayrımı) gerektirir. Etki dar + kendini onarır (tek
/stop / acil-durdur owner'ı temizler; aksi halde ≤120 dk süre-watchdog). Ertelendi.

**Açık (B1 kapsamı DIŞI, ayrı bulgu — vetting Hole 4, kod-inceleme teyit):** `ai_pro_start` KOŞULSUZ `_ai_pro_loop`
(backend `cv2.VideoCapture`) başlatır; kamerası olan klinik cihazında mobil-sürüşlü seansta backend-kamera
loop'u + telefon /frame AYNI ANDA sürebilir (sahibin İKİ kaynağı — yabancı-client değil). Yukarıdaki kalan-boşluk
bununla aynı kökü paylaşır (loop yaşam-döngüsü ↔ mobil-seans is_active çakışması) → tek bir ayrı denetim işi.

### ⚠️ Test-çıpa bakımı (refaktörlerden düşen 4 yapısal kapı — davranış regresyonu DEĞİL)
Tam süit taraması, ilgisiz refaktörlerin kaydırdığı 4 yapısal çıpayı buldu (değişmez korunuyor, yalnız
metin-çıpa kaymış → hepsi gerçek koda yeniden pinlendi): `test_mt_dose_honesty` ([E1] command_id değişkene →
`mqtt_payload` dict'i), `test_oturum_rotasyonu_bagli::_3_diske_ISLER` ([F4] doc-comment → `pull_desktop_session(port)`
çağrısı), `test_ai_pro_asamali_akis` (2 test; [B1] drive-gate `... and not is_foreign` + response `bool(localized)...`
→ iki-koşul ön-eki + JSON-anahtarı), `test_oturum_rotasyonu_bagli::_2_backendten_OKUR` ([F5] loopback kontrolü
`pull_desktop_session_kisa`e taşındı → o gövdeye pin). **Ders:** [[pemf-yapisal-capa-kirilganligi]] — refaktör
sonrası TAM süit koştur, çıpayı gerçek çağrıya pinle. **Tam süit: backend 1772 passed + pf 581 passed, 0 fail.**

### ⚠️ Doğrulama engeli — [C5] bu partide YAPILMADI (kullanıcı kararı)
[C5] (kurulum kilidi Unix'te no-op) düzeltmesi `libc::flock` gerektiriyor ve bu **Windows makinede
ne davranışsal ne de derleme doğrulanabilir**: linux/apple cross-compile target'ı kurulu değil,
`#[cfg(unix)]` bloğu Windows derlemesinde atlanır (olası FFI/syntax hatası ancak CI ubuntu'da
görünür). "Koşturarak doğrula" disiplini uygulanamadığından kullanıcı **doğrulanabilir bir bulguya
geçilmesini** seçti; C5 açık kaldı (Unix ortamı / CI-ubuntu gerektiren ayrı iş).

---

## CİDDİYET 1-2 — hasta güvenliği / güvenlik ağı

### [B1] AI Pro hazırlık akışı: İKİNCİ istemci, birinci hekimin onaylı seansını kendi kamerasıyla sürüyor ve habersiz durdurabiliyor — DARALDI (ciddiyet 1→2)
**Yer:** `servers/ai_router.py:1370` (`ai_pro_frame` imzasında istemci kimliği YOK) + `:1440`
(`if localized and session_active:` — sürüş kapısı yalnız GLOBAL seans) + `:1242-1243` (start
"Already running"→`status:success`) ↔ `pf/src/components/domain/AiProPanel.tsx:206` (`start()`
aktif-seans/sahiplik kontrolü yapmadan hazırlığa girer) + `:413` (kare akışı `running||hazirlik`).
**Tetikleyici:** Vet A telefondan AI Pro seansını onaylayıp başlatır (`session_active=true`). Vet B
kendi telefonunda paneli açıp "Başlat"a basar (A başlamadan hemen önce, hazırlıktayken) — ya da
sadece kamera-izinli paneli açık tutar: B'nin kareleri 1,5 sn'de bir `/frame`'e akar.
**Sonuç:** B'nin karesinde organ lokalize olursa `if localized and session_active` geçer;
`_predict_and_drive`+`_drive_coils_ai_pro` bobinleri **B'nin kamerasından hesaplanan hedefe** sürer.
İki kare kaynağı paylaşılan `_ai_organ_cache`'i çift yönlü kirletir. Ayrıca B "Başlat"→"Already
running" success alır → `ownedRef=true` olur → B panelini kapatınca unmount-cleanup A'nın onaylı
seansına `/ai/pro/stop` gönderir. Commit'in "hazırlık karesi HİÇBİR BOBİNİ SÜRMEZ" değişmezi yalnız
"hiç seans yokken" doğru; global `session_active` başka istemcinin seansını ayırt etmiyor.
**Zarf (çürütme ile daraldı):** organ+süre A'nın onay mührüyle kilitli, duty/frekans kaplı,
süre-watchdog sürüyor → zarar "yanlış hedefe kaplı enerji + yabancı seansı durdurma", onaysız/
sınırsız tedavi DEĞİL. Backend sahipliği çalınmaz (ölçüldü: "Already running" sonrası owner A kaldı);
`ownedRef` sapması ≤3 sn'lik status-poll'da düzelir.
**Nasıl doğrulandı:** Çürütme ajanı TestClient ile koşturdu: A onaylı+sahipli start → kimliksiz
`/frame` POST → `PREDICT:1 DRIVE:1` (B onaysız sürdü); B start → `{status:success, Already running}`,
owner A kaldı. `git log -S "Already running"` → tek commit `1dc33d9` (2026-06-27, b36aca8 ile
ilgisiz). 21b düzeltmesi (`b30d7bd`) yalnız "unmount'ta yabancı seansı durdurma"yı kapattı;
kare-sürüş sahipliği hakkında kayıtlı karar yok.

### [B2] 8266 (bobin 6-8) tek bir WiFi kopuşunda kalıcı AP-only portala düşüyor — hotspot dönse de asla bağlanmıyor — DARALDI (ciddiyet 1→2)
**Yer:** `firmware/esp8266_pemf_coil/NetworkManager.cpp:476-487` (kopuşta `_wifiRetryCount==1` →
kayıtlı ağlar HİÇ denenmeden `_startWiFiPortal()`) + `:609-612` (`WiFi.mode(WIFI_AP)` STA'yı kapatır)
+ `:460` (kontrol döngüsü portal aktifken `_reconnectWiFi`'yi hiç çağırmaz) + `:136-137` (portal
timeout bilerek kaldırılmış). S3 kardeşi kendini iyileştiriyor (`esps3.../NetworkManager.cpp:443-460`:
10 sn'de bir yeniden dener, STA'yı kapatmaz).
**Tetikleyici:** Klinik PC yeniden başlar (PEMF-Gateway hotspot ~30 sn+ kesilir) — 30 sn'lik kontrol
örneklemesine denk gelen tek kopuş yeter. Bobin çalışırken de olabilir.
**Sonuç:** Bobin kalıcı çevrimdışı: MQTT yok → normal STOP yok, E-stop bulut aynası da ulaşamaz
(WiFi yok). Kurtarma yalnız güç çevrimi (boot'ta kayıtlı ağ denenir) ya da elle Android provizyonu.
**Zarf (çürütme ile daraldı):** "ağ koparsa PWM durmaz" sahip kararının (Plan A, deadman REDDEDİLDİ)
kabul ettiği pencere; bulgunun gerçek katkısı bu pencereyi **hotspot dönüşünün ötesine** uzatması.
Enerjili bobin cihaz-yerel katmanlarla durur (sonlu süre + 7200 sn kümülatif tavan + 48°C termal);
arıza SESSİZ değil (`_esp_telemetry_watchdog api_server.py:581` panelde 30 sn'de "koptu" gösterir).
**Nasıl doğrulandı:** İki firmware NetworkManager satır satır okundu; portal mantığı `git show
3f1e171` ile sahibin masaüstü kopyasından import edilmiş ("geçici kesinti→kalıcı AP" SONUCU hiçbir
denetim/karar kaydında yok). S3 ile parite farkı öz-iyileşme niyetini gösteriyor.

### [B3] 8266 broker failover'da yerele geri dönüş yok — Mosquitto kısa süre kapanınca bobin buluta göçüp geri dönmüyor — DARALDI (ciddiyet 1→3)
**Yer:** `firmware/esp8266_pemf_coil/NetworkManager.cpp:722-755` (`_reconnectMQTT`): `_localRetryCount`
yalnız WiFi-kopukken (`:728`) ve yerel başarıda (`:739`) sıfırlanıyor. S3'ün bulut-başarısı (`:545`),
çifte-başarısızlık (`:592`) sıfırlamaları ve 15 sn'lik cloud→local probe'u (`:289-303`) 8266'da YOK.
**Tetikleyici:** WiFi ayakta kalırken Mosquitto ≥~6 sn kapanır (backend/launcher güncellemesi, servis
restart'ı; hotspot aynı makinede açık kalır). İlk yerel başarısızlıkta (~2 sn) bobin buluta göçer.
**Sonuç:** Bulut bağlantısı sürdükçe bobin **yerele asla dönmez**; backend normal start/stop'u yalnız
`127.0.0.1`'e basar (köprü kaldırıldı, `mosquitto.conf:6`) → bobin komutlara sağır, yalnız E-stop
bulut aynası ulaşır. En keskin alt-durum: çifte-kesinti sayacı 3'e sabitlerse Mosquitto dönse bile
WiFi düşene/reboot'a dek **hiçbir** broker'a bağlanamaz.
**Zarf (çürütme ile daraldı):** "normal start/stop sağır, yalnız E-stop aynası ulaşır" hali sahibin
KAYITLI Plan A kararıyla (HG-5, bulut aynası seçildi) örtüşür; kalıcı-sağır yalnız çifte-kesinti
alt-durumunda. Kalan çekirdek güvenlik açığı değil, S3-parite/erişilebilirlik boşluğu.
**Nasıl doğrulandı:** İki firmware `_reconnectMQTT` Python durum-makinesine çevrilip koşturuldu
(`scratchpad/mqtt_model.py`): 8266 Mosquitto 6 sn kapanınca sonsuza dek cloud; S3 probe ile döner;
8266 çifte-kesinti → `count=3`, Mosquitto dönse de `None` (sonsuza dek broker'sız). İlk göç 3
başarısızlıkla değil İLK başarısızlıkla oluyor (`MQTT_RETRY_DELAY=2000`).

---

## CİDDİYET 2 — veri kaybı / bozulması / sır

### [D1] Kapanmış seans buluta HİÇ gitmiyor + bayat-active PULL bekleyen PUSH bayrağını siliyor — DARALDI/kök değişti (ciddiyet 2, latent)
**Yer:** İki ayrı kusur. (a) `database/treatment_history_db.py:2047-2071` (`end_session` UPDATE'i
`sync_status`'a HİÇ dokunmuyor; `update_session_notes:2358`, güç-kesintisi kurtarma `:1441`, PII
redaksiyon `:1639` de dokunmuyor). (b) `servers/sync_worker.py:405` (`ON CONFLICT DO UPDATE ...
sync_status=1` KOŞULSUZ — kapanış üçlüsü CASE-korumalı ama bayrak değil).
**Tetikleyici:** `PEMF_CLOUD_PATIENT_SYNC` açıkken (bugün varsayılan KAPALI — latent). Seans aktifken
worker onu buluta push eder (60 sn interval → 1 dk'dan uzun her seansta) ve yerel `sync_status`'u 1
yapar; sonra seans kapanır ama hiçbir kapanış yolu `sync_status`'u 0'a çekmez.
**Sonuç:** Kapanmış seansı `WHERE sync_status=0` seçen bir sonraki PUSH hiç görmez → bulut kopyası
**sonsuza dek "active"** kalır (diğer cihazlarda/raporlarda seans hep açık, `end_time`/`duration`
bulutta hiç oluşmaz). Ayrıca (b): korunan yerel kapanış PULL'da yeniden `sync_status=1` yazılarak
bayat-active'in yakınsamasını da bozar. Yerel doz belgesi korunur; çok-cihaz görünümü kalıcı yanlış.
**Nasıl doğrulandı:** İn-memory SQLite'ta upsert birebir kuruldu (`scratchpad/s6_upsert_test.py`):
kapanış üçlüsü korunuyor ama `sync_status` 0→1 siliniyor. `end_session` UPDATE'i satır satır okundu —
`sync_status`'a dokunmuyor; repo-genel grep `sync_status` yalnız 3 dosyada, seans kapanış yolları
hiçbirinde bayrağı kirli işaretlemiyor. `test_sync_pull_bayat_active.py` `sync_status`'u hiç ölçmüyor
(test kör noktası). **Orijinal iddia (yalnız PULL) daraldı; asıl kök: kapanış yolları.**

### [D2] Manuel start NACK bekçisi koşuyu `command_id` yerine `coil_id` ile kapatıyor — çift-start örtüşmesinde ÇALIŞAN bobinin koşu kaydı düşüyor — DARALDI (ciddiyet 2→1)
**Yer:** `servers/api_server.py:1545` (`_start_ack_watch` NACK dalı → `_finish_coil_run(coil_id)`,
`command_id`→run eşlemesi YOK) ↔ `servers/coil_run_tracker.py:112` (run'ı yalnız `coil_id` ile pop'lar).
**Tetikleyici:** Aynı bobine hızlı çift start: #1 kabul (koşu#1 açılır, bobin çalışır), #2 NACK'lenir
(8266 rate-limiter 10 sn'de 6+, ya da doğrudan API'den firmware-geçersiz duty>99). `_begin_coil_run(#2)`
önce koşu#1'i kapatır ve koşu#2'yi açar; NACK bekçisi o an açık olan HANGİ run varsa kapatır.
**Sonuç:** Bobin #1 parametreleriyle **fiziksel olarak çalışmaya devam ederken** koşu-düzeyi açık
kayıt kalmaz + operatöre "bobin ÇALIŞMIYOR" YANLIŞ bildirimi. Aynı boşluk, 2 sn'lik geciken NACK'in
sonraki kabul edilmiş start'ın run'ını kapatmasına da izin verir.
**Zarf (çürütme ile daraldı):** Seans-düzeyi doz SİLİNMEZ — dakika-ortalama telemetri
(`_emit_minute_averages:3017` `coil_run_id=None` ile) koşu kaydından bağımsız yazmaya devam eder;
kaybolan yalnız koşu-düzeyi atıf/run-özeti. Yanlış bildirim telafili (`command_error` eventi gerçek
sebeple ayrı bildirim basar). Tetikleyici UI'dan üretilemez (start butonu `isActive||loading`'de
disabled), yalnız doğrudan API / rate-limit yolu.
**Nasıl doğrulandı:** `_start_ack_watch`, `coil_run_tracker`, 8266 rate-limiter
(`esp8266_pemf_coil.ino:454-461`, reddedilen start mevcut PWM'i durdurmaz) okundu; `git log -S
_start_ack_watch` → tek commit `8d8b99d`, çift-start örtüşmesi 18. parti kararlarında hiç ele
alınmamış; `test_nack_gorunurlugu.py` çift-start içermiyor.

### [D3] `secrets_backup.py` git-koruması dubious-ownership'te (git exit 128) SESSİZCE geçiyor — skip-worktree uygulanmadan restore biter — DARALDI (ciddiyet 2)
**Yer:** `build_tools/secrets_backup.py:109-135` (`_git_sir_korumasi`): `git ls-files --error-unmatch`
her dosyada nonzero dönerse izlenenler boş kalır ve fonksiyon `:119` UYARISIZ `return` eder;
"git düşerse YÜKSEK SESLE uyar" sözleşmesi ([2.2] düzeltmesi, `denetim-bulgular-2.md:121`) yalnız
`FileNotFoundError` + update-index-düşmesi dalına bağlı.
**Tetikleyici:** Yeni build makinesinde repo farklı kullanıcı/yükseltilmiş oturumla klonlanır
(safe.directory uyuşmazlığı → git ≥2.35.2 tüm komutlara 128 döner); `secrets_backup.py restore`
koşulur (sessiz geçer, skip-worktree UYGULANMAZ); kullanıcı safe.directory'yi düzeltir, `git add -A`.
**Sonuç:** Gerçek `Secrets.h`/`config.json` sırları izlenen dosyalar olduğu için PUBLIC repoya
stage'lenebilir. Uyarı sözleşmesi de sessizce ihlal.
**Zarf (çürütme ile daraldı):** Doğrudan sızıntı DEĞİL — `.gitleaks.toml` 4. parti özel kuralları
(düşük-entropili gerçek değerler) hem pre-commit kancasında (bootstrap §5b otomatik kurar) hem CI'da
yakalıyor (koşturuldu: 9 passed). Tetikleyici dar (git 128 iken `git add -A` de düşer; kullanıcının
restore'u tekrarlamaması + kanca kurulu olmaması + push gerekir).
**Nasıl doğrulandı:** Çürütme ajanı geçici repoda repro etti (gerçek depoya dokunmadan): `GIT_DIR`
bozuk iken `_git_sir_korumasi` stdout BOŞ (uyarı yok), `ls-files -v` hepsi 'H' (skip-worktree yok),
`git add -A` 4 sır dosyasını staged. Sağlıklı git'te aynı çağrı "skip-worktree uygulandı" basıyor.

### [D4] 8266 EEPROM adres haritası çakışıyor — WiFi kimlik yazımı CONFIG_VERSION ve PWM-resume kaydını bozuyor — DARALDI (ciddiyet 2)
**Yer:** `firmware/esp8266_pemf_coil/NetworkManager.h:25-27` (5 slot × 99 bayt = 0-494) ↔
`SharedDefs.h:155-157` (`EEPROM_PWM_STATE_ADDR=256`, `EEPROM_CONFIG_VER_ADDR=304`; "0-255 WiFi için"
yorumu YANLIŞ). Slot2 parolası 232-296 → PWM kaydını (256-279) örter; slot3 SSID'si 298-330 →
CONFIG_VER'i (304) örter. `_saveWiFiCredentials:837-852` 5 slotu KOŞULSUZ yazar.
**Tetikleyici:** Portal ile yapılandırılan bir kurulum bir kimlik kaydeder → EEPROM[304] slot3 SSID'nin
6. baytıyla (çöp/NUL) ezilir → izleyen açılışta `CONFIG_VERSION` uyuşmazlığı 0-255'i siler.
**Sonuç:** Portal kurulumlarında kayıtlı ağlar kaybolur (her yeniden-yapılandırma 304'ü tekrar bozar
→ her güç çevriminde portal + elle kurulum). PWM-resume magic'i de bozulur (fail-safe: resume atlanır,
bobin kapalı kalır). Ters yönde: 30 sn'lik `savePWMState` slot2 parolasını bozar (≥3 ağ + ≥25 karakter).
**Zarf (çürütme ile daraldı):** GERÇEK KLİNİK AKIŞI ETKİLENMEZ — bobin 6-8 `Secrets.h` gömülü
kimlikle bağlanır, mutlu yolda `_setupWiFi` hiç kayıt YAPMAZ, EEPROM kimlik bölgesi yazılmaz. Etki
portal-tabanlı kurulumlara sınırlı; güvenlik tarafı fail-safe.
**Nasıl doğrulandı:** Adres aritmetiği (`+1/+33/+65`, `sizeof(struct)` değil) gömülü Python ile
modellendi (`scratchpad/eeprom_model.py`): slot2 parola 232-296 ⊇ PWM 256-279; portal kaydı → EEPROM[304]≠1
→ Boot-2 wipe (slot0 gitti, PWM 0xAB korundu) → Boot-3 (kayıtsız) wipe DURDU. `denetim-bulgular-2.md:93`
"adres çakışması yok" hükmü yalnız CoilController restore-save kapsamındaydı, WiFi bölgesini incelememişti.

---

## CİDDİYET 3 — cihaz kullanılamaz / güncelleme kırılması

### [C1] C2 geri-alma döngü kırıcısı ÜRETİMDE ÖLÜ — bozuk yayın her açılışta yeniden kurulup geri alınıyor — AYAKTA (ciddiyet 3)
**Yer:** `launcher/app/src/main.rs:740-754` (`check_runtime_update` komut JSON'una `otomatik_durduruldu`
KONMUYOR — 9 anahtar: needed/base/deps/app/profiles/bytes/cached/rolloutPending/recall) ↔
`launcher/app/ui/index.html:1645` (`if (plan.otomatik_durduruldu)` — tek tüketici). Alan
`flow.rs:917`'de var, `:1064`'te hesaplanıyor ama serileştirilmiyor (`UpdatePlan` `Serialize`
türetmiyor → başka yol yapısal olarak imkânsız).
**Tetikleyici:** Sağlık kapısını (start_backend / dbReady) 2 kez düşüren bozuk bir yayın sahada:
sayaç `runtime_attempt.json`'a 2 yazılır, `runtime_otomatik_izinli=false` olur — ama `bootNetwork`
her çevrimiçi açılışta `tryRuntimeUpdate` çağırıyor (`index.html:2071`) ve `plan.cached=true` iken
doğrudan `apply_runtime_update`'e gidiyor.
**Sonuç:** C2'nin çözdüğü iddia edilen arıza AYNEN sürer: her açılışta backend öldürülür, ~1,19 GB
deps açılır, ~180 sn sağlık beklenir, geri alınır — klinik her açılışta dakikalarca bloklanır;
`rtBlocked` bildirimi hiç görünmez. Tek fren yine yayıncının `rollout:0` yazması.
**Nasıl doğrulandı:** Komut JSON'u satır satır okundu (`otomatik_durduruldu` yok); `git show 6e66940 --
launcher/app/src/main.rs | grep -c otomatik_durduruldu` → 0 (aynı commit index.html'e `if
(plan.otomatik_durduruldu)` ekledi). Kilit test (`test_runtime_geri_alma_dongusu_bagli.py`) yalnız
isim-varlığı ölçüyor: `main.rs` serileştirme köprüsünü hiçbir test görmüyor → 7 passed (ölü kablolamaya
rağmen yeşil). Bu, 08-23 denetiminin "düzeltildi" dediği C2'nin düzeltmesindeki YENİ kusur.

### [C2] `update_installed` içindeki geri almalar deneme sayacı yazmıyor — profil/app hata sınıfı döngüye SAYAÇSIZ girer — AYAKTA (ciddiyet 3)
**Yer:** `launcher/app/src/main.rs:884,906` (`geri_almayi_kaydet` yalnız dbReady + sağlık-kapısı geri
almalarında) ↔ `flow.rs:1206-1219` (app yapısal-geçersiz/açılım hatası) ve `:1262-1282`
(`profilleri_yenile` hatası) — bu iç geri almalar sayaç YAZMADAN `Err` döner, `main.rs:859` sayaçsız
dışarı taşır.
**Tetikleyici:** `plan.cached` bir güncellemede profil (model) zip açılımı deterministik düşer (AV bir
model dosyasını karantinada tutar / dosya kilitli): takas yapılır → `profilleri_yenile` Err → geri
alınır → sayaç yazılmaz. C12 invalidasyonu (`record_model_sha(name,"")` extract'ten ÖNCE) başarısız
profili planda TUTAR → ikinci açılışta `plan.needed()=true`, `plan.cached=true`.
**Sonuç:** L1 düzeltilse bile bu hata sınıfında döngü kırıcı devreye girmez: her açılışta backend
öldürülür, deps/app yeniden açılır, profil adımında düşülür, geri alınır — süresiz tekrar (yeni sha
yayınlanana kadar). Deterministik tetikleyiciler kodun kendi yorumunda sayılıyor (`flow.rs:1257`:
"kilitli model dosyası, AV karantinası").
**Nasıl doğrulandı:** `geri_almayi_kaydet` çağrı yerleri grep'le çıkarıldı (yalnız main.rs:884/906);
iç geri alma blokları okundu; kayıtlar yalnız `guncellemeyi_onayla`'da yazılıyor (`flow.rs:778`,
kasıtlı fail-safe). ⚠️ Düzeltme Cancel/Pause'u SAYMAMALI (o hatalar da :1262'den geçer). Bugün L1
yüzünden kapı zaten ölü — kusur L1 kapatılınca görünür hale gelir.

### [C3] "Beni hatırla" düzeltmesi ÇALIŞAN backend'i sahiplenme yolunda hiç başlamıyor — o oturumun rotasyonu diske işlenmiyor — AYAKTA (ciddiyet 2-3)
**Yer:** `launcher/app/src/main.rs:601-608` (`detect_running_backend` sahiplenme dalı: `hand_off_session`
+`open_app_window` yapıp döner) — `oturum_rotasyon_senkronu_baslat` YALNIZ `on_backend_ready:226`'dan
çağrılıyor (çağrı yerleri 551/624/696/921), sahiplenme dalı listede yok.
**Tetikleyici:** Launcher çöker/Görev Yöneticisi'nden kapatılır (backend yetim ve sağlıklı kalır) →
kullanıcı launcher'ı yeniden açıp Başlat'a basar → backend sahiplenilir → pencere saatte bir jetonu
döndürüp backend'e geri yazar ama launcher HİÇ çekmez → makine kapatılıp açıldığında launcher diskteki
bayat refresh jetonuyla yenileme dener.
**Sonuç:** GoTrue bayat jetonu reddeder → `SessionRevoked` → `secret_store::clear` (`main.rs:1095`) →
"Beni hatırla" kaydı SİLİNİR, e-posta+parola yeniden sorulur — `4df79cc`'nin sahada ölçtüğü arızanın
ta kendisi, sahiplenme yolunda açık.
**Nasıl doğrulandı:** Çağrı yerleri ölçüldü; dalın kendi yorumu (`:596`) "çökmüş bir önceki oturum"
senaryosunu gerçek diye kaydediyor; `open_app_window` açık pencereyi yeniden yüklemez → pencere
aileyi yalnız sayfa yüklenirken alır. `4df79cc` mesajı/testleri sahiplenme dalını dışlama kararı
KAYDETMİYOR. İki-instance alt-senaryosunda backend'i başlatan instance telafi eder; crash-sonrası
tek-instance sahiplenmede hiçbir katman yok.

### [C4] App-katmanı iç geri-alma hatası yutuluyor — cihaz yarım ağaçla kalırken UI "iptal edildi" diyor — AYAKTA (ciddiyet 3)
**Yer:** `launcher/core/src/flow.rs:614-617` (`app_katmanini_degistir` açılım hatasında `let _ =
guncellemeyi_geri_al(...)` — sonuç yutulur) → orijinal `Cancelled` `?` ile yukarı taşınır →
`main.rs:856-858` `{"status":"cancelled"}` yapar. Aynı fonksiyonun DIŞ yolu (`:1271-1279`) ve
yapısal-kontrol yolu (`:1209-1218`) tam bu durumda hatayı açıkça yükseltir — iç yol çevrilmemiş
([3.1]'in 7. partide dış yolda kaldırdığı desen).
**Tetikleyici:** Yalnız-app güncellemesi sırasında kullanıcı açılım aşamasında İptal'e basar (ya da
G/Ç hatası) VE geri koyma `fs::rename`'i (`:854`) AV/kilitli-dosya yüzünden düşer.
**Sonuç:** Cihaz yarım app ağacıyla "Hazır!" ekranında; Başlat anlaşılmaz hatayla düşer; UI "iptal
edildi" der (yalan). Kurtarma ancak sonraki açılışta `yarim_takasi_kurtar` (C11) ile.
**Zarf:** `runtime.old` tüketilmez ([3.1]'in felaket kolu yok); sha kaydı hiç yazılmadığı için sonraki
tur app'i önbellekten yeniden açar. Zarar tipik olarak tek oturum + yanıltıcı mesaj.
**Nasıl doğrulandı:** `extract.rs:145` iptalde `Err(Cancelled)` döner → Err dalından geçer; iç
`let _ =` ile dış yolun açık yükseltmesi karşılaştırıldı; deponun kendi tatbikatı (`upgrade_drill.rs`
TATBIKAT 5) aynı üretim analojisini kullanıyor. `denetim-bulgular-2.md` 7. parti "iptal maskesi
takılmaz" hedefiyle çelişiyor.

### [C5] Kurulum kilidi Unix'te sessiz no-op — Linux/macOS'ta iki eşzamanlı yıkıcı akış çakışabilir — AYAKTA (ciddiyet 3)
**Yer:** `launcher/core/src/install.rs:352-369` (`kurulum_kilidi_al`): dışlama YALNIZ
`#[cfg(windows)]` `share_mode(0)`'dan gelir; Unix'te `OpenOptions create+write` her zaman başarılı,
flock/fs2/fd-lock kullanımı yok → kilit sessiz no-op. Tauri single-instance plugin de yok (`main.rs:824`
yorumu "Tek-instance koruması da yok" diyor).
**Tetikleyici:** macOS/Linux'ta iki launcher penceresi aynı anda kurulum/onarım/`apply_runtime_update`
başlatır — dosya kilidi 6 yıkıcı akışın (`main.rs:499,642,776,828,972,1325`) TEK bekçisi.
**Sonuç:** Yarışan iki akış runtime ağacını karışık/yarım bırakabilir (C6'nın Windows'ta kapattığı
bozulma sınıfı); kilit mesajı hiç görülmez.
**Zarf:** Pratik zarar hasta güvenliği değil kurulum bütünlüğü — macOS notarization'da bloklu, Linux
konuşlanmaları daha çok demo/sunucu profili.
**Nasıl doğrulandı:** grep single-instance/fs2/fd-lock/flock (boş); `git log -S share_mode` +
`git show b2d8a69` (kilit doğuşundan beri `cfg(windows)`, tasarım yorumu tamamen Windows semantiği);
`launcher.yml` matrisi 3 platform üretiyor (macos-14/windows-latest/ubuntu-22.04); C6 kaydı kilidin
çalıştığı varsayımıyla kalıcı kapı testi yazmış. Unix no-op'u hiçbir denetimde geçmiyor.

### [C6] Backend KALDIRMA zincirinde bobin E-stop yok — backend servis-dışı koşarken sinyalsiz öldürülür — DARALDI (ciddiyet 1→3)
**Yer:** `scripts/setup_services.ps1:104-110` + `scripts/pemf_teardown.ps1:99` (`Get-Process
PEMF_Backend | Stop-Process -Force` — ad-eşleşmeli, sinyalsiz, E-stop'suz; her ikisinde `emergency_stop`
0 kez) ↔ `build_tools/PEMF_Backend_Setup.iss:390` (`CurUninstallStepChanged`).
**Tetikleyici:** Backend SERVİS DIŞINDA koşarken (servis durdurulmuş/silinmiş/kurulum-fail + launcher
ya da elle backend — `.iss:368` bu durumu bizzat tanıyor) seans sürerken kaldırıcı çalıştırılır.
**Sonuç:** `_safe_stop_outputs` koşmadan süreç ölür: STM kuyruk-flush + ESP MQTT STOP yayınlanmaz →
08-23 raporu satır 79'un "aynı sıra kaldırma yolunda da uygulanmalı" önerisi kodda uygulanmamış.
**Zarf (çürütme ile daraldı):** Birincil dağıtımda telafi VAR — kaldırma zincirinin ilk adımı graceful
servis-durdurmadır (`setup_services.ps1:94` `nssm stop PemfBackend` + `AppStopMethodConsole 15000` →
`backend_service.py:722` SIGINT/SIGTERM yakalar → `_safe_stop_outputs`). Bu E-stop POST'unun işlevsel
ikizi. Salt-launcher makinede Inno kaldırıcı zaten yok (NSIS `hooks.nsi` E-stop'u POST ediyor, testli).
Boşluk yalnız çok-koşullu bozuk-konfigürasyonda (servis-dışı backend).
**Nasıl doğrulandı:** `grep -c emergency_stop` setup_services/pemf_teardown/pemf_uninstall_all = 0/0/0;
`setup_services.ps1:94-110` graceful yolu + `backend_service.py:722-744` sinyal işleyicisi okundu;
`.iss:368` "backend servis DIŞINDA başlatılmış olabilir" durumunu tanıyor ama teardown ailesi bobin-STOP
için "koşan backend = servis" varsayımına asılı.

### [C7] Site yayın runbook'u kök dizindeki BAYAT `PEMFVetClient-Setup.exe`'yi yükletiyor — aynı etikette iki farklı ikili tuzağı — AYAKTA (ciddiyet 3)
**Yer:** `BUILD.md:379` (`gh release create ... PEMFVetClient-Setup.exe release_assets\PEMF_Vet_Mobil.apk`
— EXE öneksiz=kök, APK `release_assets\` önekli) + kök `PEMFVetClient-Setup.exe` (2026-08-08 tarihli,
2.926.195 B; taze ikili `release_assets/`'te 2.964.583 B).
**Tetikleyici:** Bir sonraki launcher yayınında yayıncı §6'yı harfiyen kökten çalıştırır → yeni etikete
sürümsüz ad olarak Aug-08 bayat launcher yüklenir; sürümlü ad `release_assets`'ten doğru yüklenir.
**Sonuç:** Aynı etikette İKİ FARKLI ikili ("her varlık iki adla, ikisi aynı ikili olmalı" değişmezi
kırılır): `manifest.launcher.sha256` taze dosyadan alınırsa sahadaki tüm self-update'ler sha
doğrulamasında fail-closed düşer (launcher güncellenemez); bayat dosyadan alınırsa saha eski launcher
alır. Son yayınlarda kaza olmaması yayıncının runbook'u izlememesine bağlı.
**Nasıl doğrulandı:** `ls -la`: kök EXE Aug 8/2.926.195 B, release_assets Aug 24/2.964.583 B (=1.9.37
boyutu); kök kopya gitignore'lu, hiçbir betik tüketmiyor, hiçbir build tazelemiyor. `gh release view
launcher-v1.9.37` → iki ad da 2.964.583 B (runbook izlenmemiş, tuzak silahlı). Y1 düzeltmesi
(`6e66940`) satırı bu haliyle bırakmış. Hiçbir kapı sürümsüz yüklemenin tazeliğini ölçmüyor.

---

## CİDDİYET 4 — yanlış klinik çıktı / kayıt

### [E1] Seans yolu ESP dalı NACK'lenen bobin için hayalet koşu kaydı yazıyor — DARALDI (ciddiyet 4)
**Yer:** `servers/api_server.py:2524-2540` (`/api/session/start` ESP döngüsü: publish fire-and-forget
daemon-thread + KOŞULSUZ `_begin_coil_run`; `_register_ack`/`_start_ack_izle_arka_planda` YOK).
Tekil (`:2145`) ve batch (`:2254`) yolları ack-bekçisine bağlı — seans yolu üçüncü, bağlanmamış yol.
**Tetikleyici:** Seans başlatılırken bir ESP bobini start'ı reddeder (en gerçekçisi: önceki seanstan
sıcak kalan bobinin `g_thermalLock` reddi → 8266 termal kilidi NACK+`command_error` basar).
**Sonuç:** Hiç çalışmamış bobin seans süresi boyunca "koştu" kalır ve seans sonunda `_stop_session_coils`
onu TAM SÜRELİ koşu olarak mühürler → tedavi geçmişine/doz belgesine hayalet bobin koşusu yazılır.
**Zarf (çürütme ile daraldı — iki yarı):** (1) **Broker-ölü/fire-and-forget yarısı bug DEĞİL** — 8.
parti bilinçli kararı (`denetim-bulgular-2.md:197`) "Seans yolunun ESP koşu kayıtları DEĞİŞMEDİ:
publish bilerek arka planda; `esp_unreachable` uyarısı taşıyor" birebir kapsıyor (`api_server.py:2596`
doğrulandı). (2) **NACK yarısı AYAKTA** — 8. parti bu yarıyı "AÇIK kaldı" diye kaydetti, 18. parti
(`8d8b99d`) bekçiyi yalnız "Manuel ESP start (tekil VE batch)" yoluna bağladı; seans yolu 18. partiden
sonra ack-mimarisiz kalan TEK start yolu ve bu kayıtlı karar DEĞİL. Operatör kör değil (thermal_lock +
command_error bildirimleri yol-bağımsız); zarar tıbbi doz kaydının bütünlüğü. `esp_unreachable` yalnız
broker ölüyken tetiklenir, termal-NACK vakasını KAPSAMAZ.
**Nasıl doğrulandı:** `git show 8d8b99d` ("Manuel ESP start (tekil VE batch)" — seans yolu geçmiyor);
`_register_ack` çağrı yerleri grep'lendi (:2145/:2254/:3985 — seans döngüsünde yok); `_begin_coil_run`
koşulsuzluğu ve kapanış mühürleme zinciri okundu. **NOT:** STM ikizi (BE-S7 — seans STM dalı update_coil
dönüşünü okumuyor) ÇÜRÜTÜLDÜ: start yolunda `update_coil` False pratikte üretilemiyor (aşağıya bakınız).

### [E2] Mobil AI Pro hazırlık ekranının "hayvan görünüyor, organ aranıyor" aşaması ölü kod — yanlış operatör yönlendirmesi — AYAKTA (ciddiyet 3-4)
**Yer:** `servers/ai_router.py:1472-1486` (`ai_pro_frame` JSONResponse'u `catDetected` alanını
TAŞIMIYOR) ↔ `pf/src/components/domain/AiProPanel.tsx:482,498-500` (mobil dal yalnız
`mobileResult?.catDetected` okur; `/status` poll'u var ama `AiProStatus` tipi `:86-93` `catDetected`
içermiyor → telafi yok).
**Tetikleyici:** Telefonda hazırlık: hayvan kadrajda ve `cat_organ` organ döndürüyor ama seçili organ
güven eşiğini geçemiyor (`detected=false, kedi_var=true`).
**Sonuç:** Aşama şeridi asla "🔎 Hayvan görünüyor, {organ} aranıyor… (kamerayı biraz çevirin)" demez;
hayvan tam kadrajdayken bile "🐾 Hayvan aranıyor… kamerayı hastaya doğrultun" + 45 sn sonra "ışığı
artırın, 1-2 metreye gelin" gösterir — sürümün DÜZELTMEYİ İDDİA ETTİĞİ tam davranışın (kamerayı mı
çevir açıyı mı değiştir ayrımı) tersi. `b36aca8` commit mesajı "`/frame` ve `/status` catDetected taşır"
diyor — YENİ backend de göndermiyor. (409 propose ipucu cache'ten okuduğu için doğru çalışır → iki mesaj
çelişir.)
**Nasıl doğrulandı:** `../python.exe -m pytest tests/test_ai_pro_asamali_akis.py` → 19 passed (yanlış
yeşil); koruyucu test `router.find('"detected": localized')` İLK geçişi (satır 999, ws bloğu —
catDetected VAR) ölçüyor, `/frame` yanıtını (satır 1476, catDetected YOK) hiç görmüyor —
`scratchpad` scriptiyle ölçtüm.

### [E3] `_ai_pro_loop` cache'e `kedi_var` yazmıyor + kedi-yok tek-yönlü mandal — web/status/409 ipucu bayat — AYAKTA (ciddiyet 3-4)
**Yer:** `servers/ai_router.py:891-904` (loop relocalize: `lkedi` `:891`'de açılıp ATILIYOR;
`cache.update`'te `kedi_var` anahtarı YOK — frame yolu `:1411` yazıyor, asimetri) + `:905-911` (hata
dalı yalnız `localized=False`) + `_localize_organ_cpu:644` (kedi yokken cat_organ RuntimeError atar →
`_extract_organ_target`'a hiç ulaşılmaz → `kedi_var=False` HİÇ yazılamaz).
**Tetikleyici:** Web/sunucu-kameralı AI Pro seansı; loop her lokalizasyonda `lkedi` çözer ama cache'e
yazmaz. Kedi kadrajdan çıkınca `cat_organ` istisna atar, hem loop hata dalı hem `/frame` 500 yolu
`kedi_var`'a dokunmaz → bir kez True olan değer bir daha False olamaz.
**Sonuç:** Hedef kaybolduğunda web paneli `catDetected`'e göre yönlendirme seçer: bayat False ise hayvan
kabindeyken "kamerayı hastaya doğrultun", bayat True ise hayvan kabinden çıkmışken "açıyı değiştirin" —
yanlış klinik yönlendirme; `/status` ve propose-409 ipucu da aynı bayat değeri kullanır.
**Nasıl doğrulandı:** grep `kedi_var` yazarları → yalnız `:1411` (frame yolu); `ai_hub/inference_cat_organ`
ve `ai_service/app.py:591` (GPU 500 → `ai_client.py:74` raise) okundu — CPU fallback yine fırlatıyor →
`_extract_organ_target` ölü dal. start/stop yalnız `localized` sıfırlıyor (`:1273`).

### [E4] S3 faz kilidinin EDİNİM yolu yok — çok-bobinli faz senkronu çoğu seansta saatlerce kurulamaz/hiç kurulmaz — AYAKTA (ciddiyet 3-4)
**Yer:** `firmware/esps3_pemf_coil/CoilController.cpp:83-129` (`syncPulseISR` yalnız darbe periyot
sınırının ±%2'sine denk gelirse kilitler) + `:134-143` (pasifken `s_tick` ilerlemez) + `_beginOutput`/
`_updatePWM` hiçbir yerde `s_tick`'i START'ta sıfırlamaz/hizalamaz (grep: `s_tick` yalnız iki ISR'de
yazılıyor). STM PB1 epoch-hizalı (`main.c:1083`).
**Tetikleyici:** AI Pro çok-bobinli seans (1 Hz, faz desenli, bobin 6-7): CMD_START uygulanır, `s_tick`
donmuş değerinden akar. STM ve ESP nominal aynı frekansta (`tpp=50000` her ikisi) → PB1 darbesi ESP
periyodunda RASTGELE sabit ofsete düşer; toleranslı ISR onu sürekli "ignored" sayar.
**Sonuç:** Kilit ancak kristal kayması (±20 ppm) ofseti ±%2 pencereye SÜRÜKLERSE oluşur — 1 Hz'de
saatler. Çok-bobinli faz deseni (cihazın temel işlevi) çoğu seansta hiç kurulamayabilir; bobin 6-7
fazları STM'e göre rastgele kayık sürülür. Sessizdir: status yalnız `sync_ignored`/`sync_disabled`
yayınlar, hiçbir tüketici (servers/, pf/) okumaz.
**Zarf:** Yön fail-safe (bipolar, DC yok); STM 1-5 kendi içinde faz-tutarlı; kayıp yalnız bobin 6'nın
STM'e göre fazı (bobin 7 zaten sahip kararıyla tek-faz). REFLASH öncesi ZORUNLU tezgâh doğrulaması
(README madde 3: "STM bağlı + aynı frekans → sync_ignored SABİT") bu bulguyu görünür kılar.
**Nasıl doğrulandı:** Gömülü Python ISR modeli: kilit penceresi periyodun %4,01'i; rel-drift 0 →
orta-periyot ofseti HİÇ kilitlenmez; 40 ppm → 3,19 saat, 10 ppm → 6,39 saat (1 Hz). `_AI_PRO_FREQ_HZ=1.0`
(`ai_router.py:528`); STM `tpp=(uint32_t)(50000.0f/1.0)=50000` (`main.c:1028`), ESP `50000/1=50000`.
grep: `sync_ignored`/`sync_disabled` tüketicisi yok. [4.3] erken-kilit guard'ı edinimi bozmuyor ama
edinim zaten drift'e mahkûm.

---

## CİDDİYET 5 — diğer işlevsel / test-kalitesi

### [F1] P0 (Inno E-stop) karşıt-kanıt testi YANLIŞ dilim ölçüyor — hiçbir zaman kırmızıya dönemez, hasta-güvenliği boşluğunu maskeliyor — AYAKTA (ciddiyet 2, güvenlik-görünürlüğü)
**Yer:** `tests/test_inno_kurulum_bobin_guvenligi.py:227` (`k.find("CurUninstallStepChanged")` İLK
geçişi indeks 7408=satır 122'deki YORUM satırında buluyor; gerçek `procedure` indeks 21816=satır 390).
**Tetikleyici:** Her pytest koşusu.
**Sonuç:** `k.find`'ın aldığı dilim INSTALL yolunun `taskkill`'ini VE E-stop yordamlarını (satır
244-312) kapsıyor → "taskkill var + emergency_stop var" → skip'e düşmeden PASSED. Gerçek kaldırma
yordamı ikisini de içermiyor. Test "KALDIRMA yolunda E-stop VAR" diye YANLIŞ güvence veriyor ve 08-23
kapanış raporu bu testi P0 kapanış kanıtlarından biri sayıyor; [C6]'yı görünmez kılıyor. Install yolu
E-stop'u korunduğu sürece kapı HİÇBİR ZAMAN kırmızıya dönemez (tautoloji).
**Nasıl doğrulandı:** Ölçüldü — ilk geçiş 7408/satır 122 (yorum), procedure 21816/satır 390; dilimde
`taskkill=True`+`emergency_stop=True`; gerçek procedure gövdesinde ikisi de `False`. `pytest ...` →
11 passed (KALDIRMA testi PASSED, skip DEĞİL). Mutasyon simülasyonu: gerçek procedure'e E-stop'suz
taskkill enjekte edilse mevcut mantık PASS verir (regresyonu KAÇIRIR). Deponun kendi "yorum-satırı
tuzağı" dersinin ihlali (aynı dosyanın ssInstall fixture'ı yorumları özellikle ayıklıyor).

### [F2] AI Pro "üst üste iki tutarlı ölçüm" sertleştirmesi YAPISAL OLARAK BOŞ — AYAKTA (ciddiyet 3-5)
**Yer:** `servers/ai_router.py:548` (`_ORGAN_LOCALIZE_INTERVAL_S=10.0`) + `:1387-1391` (frame `detected`'ı
CACHE'ten servis eder) ↔ `pf/src/components/domain/AiProPanel.tsx:43` (`KARE_ARALIK_HAZIRLIK_MS=1500`) +
`:262-300` (`ARDISIK_ONAY=2` sayaç efekti).
**Tetikleyici:** Telefonda hazırlık akışı; her hazırlık başlatması.
**Sonuç:** Lokalizasyon en fazla 10 sn'de bir koşuyor, hazırlık kareleri 1,5 sn'de bir → aynı 10 sn
penceresindeki TÜM yanıtlar tek ölçümün ekosu; sayaç o pencerenin 1. ve 2. yanıtında (~1,5 sn arayla)
2'ye ulaşır. İki onayın iki AYRI lokalizasyona denk gelmesi erişilebilir hiçbir sıralamada olmuyor →
"tek şanslı kare tedavi parametresi tetikleyemez" vaadi yapısal olarak boş.
**Zarf:** Telafi katmanları duruyor (hekim onayı, `_MIN_RELIABILITY`, güven % gösterimi, süre-watchdog)
→ durum eskisinden KÖTÜ değil; zarar "sertleştirme var sanılması". Ciddiyet düşük.
**Nasıl doğrulandı:** Sabitler okundu; `need_localize` koşulu (`:1387`) ve efekt sayacı izlendi. Commit
mesajı + panel yorumu (`:47-53`) "üst üste iki tutarlı ölçüm şart" diyor; cache-eko hiçbir yerde
anılmıyor; test yalnız sayaç mekaniğini zorluyor.

### [F3] Web'de AI Pro soğuk başlangıçta propose hep 409 — yeni 409 metni web'de yanıltıcı — AYAKTA (ciddiyet 5)
**Yer:** `servers/ai_router.py:815` (tek `VideoCapture(0)` `_ai_pro_loop` içinde, yalnız aktif seansta
koşar) + `:1093-1097` (propose taze-cache kapısı) + `:1114-1115` (yeni 409 metni "Kamera görüntüsü
akarken konumlandırma kendiliğinden tamamlanır"). Panel yorumu (`AiProPanel.tsx:233`) "Web'de sunucu
kamerası zaten sürekli kare üretir" — kodla çelişiyor.
**Tetikleyici:** Web panelinde ilk kez AI Pro başlatma (cache boş, <120 sn taze lokalizasyon yok).
**Sonuç:** Seans öncesi web'de hiçbir kare kaynağı yok → propose hep 409; yeni 409 metni web'de
GERÇEKLEŞEMEZ (kamera yalnız aktif seans loop'unda açılıyor).
**Zarf:** Bilinçli karar değil (denetim notu yalnız AiHubScreen otonom akışını kapsıyor). Zayıf telafi:
önceki seanstan <120 sn taze cache veya aynı backend'e telefonla hazırlık koşturmak propose'u geçirir —
tasarlanmış web yolu değil. Kilit bu commit'te doğmadı (`0e2b1ed`'de propose taze kapısıyla eklendi),
ama SÜRÜYOR.
**Nasıl doğrulandı:** grep `VideoCapture` (repo geneli): AI Pro cache'ine bağlanan tek kullanım
`:815`; pf'te web tarafı için başka üretici yok (`getUserMedia` yok); `git show 0e2b1ed` doğrulandı.

### [F4] Rotasyon senkron thread'i "meşgul" ile "ölü"yü ayırmıyor — 5 meşgul yoklamada kalıcı ölür — DARALDI (ciddiyet 2→5)
**Yer:** `launcher/app/src/main.rs:247-252` (5 ardışık `None` → thread KALICI çıkar) +
`backend.rs:382` (pull timeout 5 sn). `backend.rs:263`'teki `backend_is_definitely_gone` (refused/timeout)
ayrımı bu döngüde kullanılmıyor.
**Tetikleyici:** Uzun AI çıkarım yükü altında backend loopback isteklere 5 sn içinde yanıt veremez
(repo bunu belgeliyor: `backend.rs:224` session_active timeout tam bu yüzden 10 sn) → 5 meşgul yoklama
~5 dk'da thread'i öldürür.
**Sonuç:** O oturumun sonraki rotasyonları diske işlenmez → sonraki yeniden başlatmada bayat jetonla
SessionRevoked ("Beni hatırla" aralıklı geri gelir).
**Zarf (çürütme ile daraldı):** "Oturum yok {}" ile çıkılan senaryolarda pencere blob-ailesini tutmuyor
(ıraksama doğmaz); backend-ölü çıkışı zararsız. Kalan çekirdek yalnız "backend meşgul 5 sn timeout"
kovası.
**Nasıl doğrulandı:** `main.rs:247-252` döngüsü + `backend.rs:376-404` pull None koşulları okundu;
`auth_router.py:155` (GET boşken {}+200).

### [F5] Hiçbir teardown yolunda kapanış öncesi son pull yok — ≤60 sn rotasyon penceresi diske bayat kalır — AYAKTA (ciddiyet 2→5)
**Yer:** `launcher/app/src/main.rs:242` (`pull_desktop_session` TEK çağrı yeri, 60 sn döngüsü içinde);
teardown yolları (Destroyed job `:1694`, `apply_runtime_update:833`, self-update, uninstall `:977`)
hiçbirinde son pull YOK. Yorum (`:234`) "60 sn ... kapatmadan önce yakala için fazlasıyla sık" diyor —
kapanış anını hiç kapsamıyor.
**Tetikleyici:** supabase-js jetonu döndürür (push edilir), kullanıcı 60 sn dolmadan pencereyi/launcher'ı
kapatır ya da o aralıkta güncelleme backend'i öldürür.
**Sonuç:** Diskte tüketilmiş refresh jetonu kalır → sonraki açılışta SessionRevoked → parola yeniden
istenir. `4df79cc`'nin tetikleyicisi (rotasyon + hemen yeniden başlatma) dar bir pencereye sıkışmış
ama kapanmamış.
**Zarf:** Olasılık ~60/3600 ≈ %1,7/oturum-saat; sonuç tek seferlik yeniden-giriş.
**Nasıl doğrulandı:** grep `pull_desktop_session` (tek satır 242); teardown yolları satır satır;
`app` kapanınca pencere JS'i ölür ama backend ayakta — kill'den önce tek pull yarışı kapatırdı.

### [F6] `secret_store::save` atomik değil (tmp+rename yok) — DARALDI (ciddiyet 1→5, sağlamlaştırma)
**Yer:** `launcher/core/src/secret_store.rs:40-41` (`fs::write`, geçici-dosya+rename yok); rotasyonla
yazma "yalnız girişte"den saatte ~1'e çıktı; ardışık `on_backend_ready`'ler iki senkron thread'i
kurabilir.
**Sonuç:** Yazım anında elektrik kesintisi blob'u bozar (sessiz `None` → parola yeniden istenir).
**Zarf (çürütme ile daraldı):** Bozulmanın sonucu modülün BELGELİ best-effort geri-düşüşü (bir kez
parola); veri/güvenlik etkisi yok. Aynı-jeton kapısı (`rotasyonu_isle:80`) yazma sıklığını ~saatte 1
kısa yazıma tutuyor, çift-thread yazımlarını da bastırıyor. Atomik-yazma bir sağlamlaştırma iyileştirmesi.
**Nasıl doğrulandı:** `secret_store.rs` + testleri okundu (bozuk blob sessiz `None` testli); dört kapı +
`KARSIT_KANIT_ayni_jeton` testi; thread ömrü `main.rs:236-257`'den türetildi.

### [F7] pre-commit CHANGELOG kapısı ham substring, CI kanal-başlıklı regex — ayrışma erken uyarıyı öldürüyor — DARALDI (ciddiyet 5)
**Yer:** `scripts/check_changelog_surum.py:31-38` (ham `s not in metin`) ↔
`tests/test_version_visibility.py:172` (kanal-başlıklı regex, 2026-08-23'te sertleştirildi). Betiğin
docstring'i (`:11`) "mantık test ile BİREBİR aynı tutulur" diyor — ayrışmış.
**Tetikleyici:** `versions.json`'da bir kanal sayısı, CHANGELOG'da BAŞKA bir kanalın girdisi olarak zaten
geçen bir numaraya yükseltilir (ör. backend 1.9.37 — launcher 1.9.37 girdisi mevcut) ve yeni kaydın
bölümü yazılmaz.
**Sonuç:** Pre-commit yanlış-yeşil verir; eksik CHANGELOG push'tan SONRA CI'da kırmızı döner —
kancanın var oluş sebebi olan "Run failed e-postasından önce yakala" (2026-08-14 vakası) kaybolur.
**Zarf:** CI yedek kapı zaten yakalıyor; tek kayıp erken uyarı, saha/ürün zararı yok.
**Nasıl doğrulandı:** Koşturuldu — cross-kanal '1.9.37' substring=True/regex=False; HEAD'de üç kanal da
True/True. `git log -- scripts/check_changelog_surum.py` → tek commit; `git show 6e66940 --stat` →
yalnız CHANGELOG + test değişti (betik değişmemiş).

---

## ÇÜRÜTÜLDÜ — rapor edilmiyor

- **[BE-S7] Seans yolu STM dalı `update_coil` dönüşünü okumuyor → STM hayalet koşu.** Tetikleyici bu
  uçtan ERİŞİLEMEZ: `update_coil(start=True)` yalnız (a) `coil_id∉1..5` (seans yolu STM'i `STM_COIL_IDS`
  ile önden filtreler) ya da (b) normalize istisnası döndürebilir. `SessionStartPayload` Pydantic
  tipleri sayısal-olmayan girdiyi 422'de eler; sayısal girdilerde normalize yardımcıları **istisna
  atmaz** (koşturuldu: nan/inf/-inf/1e308/negatif hepsi istisnasız — `clamp_float` isfinite ile
  default'a düşer). Kalan her durumda dönüş KASITLI koşulsuz True (`hardware_controller.py:215`: "START
  yolunda dönüş BİLEREK değişmedi: keep-alive her turda tam durumu tazeler"). Reddedilen STM bobini bu
  yolda var OLAMAZ → zarar zinciri ilk halkada kopuyor.

---

## ŞÜPHELİ — DOĞRULANAMADI

- **[FW-6] S3 Network görevinin WDT bütçesi (10 sn panic=true) bulut TLS handshake / OTA `httpUpdate`
  bloklarıyla tutarlı mı?** Doğrulanan: WDT yorumları BAYAT (`.ino:270` "3 Saniye", `NetworkManager.cpp:111`
  "WDT=5sn" — gerçek `SharedDefs.h:80` = 10 sn; salt dokümantasyon kusuru); OTA `httpUpdate.update`
  (`:884`) zincirinde WDT reset yok ve 1,38 MB imaj 10 sn'yi aşar AMA `UPDATE_FIRMWARE`'in depoda hiç
  üreticisi yok (latent, elle MQTT gerekir; OTA öncesi PWM durduruluyor). Merkezi iddia (kötü ağda
  periyodik panic-reset) `PubSubClient`/`WiFiClientSecure`/`HTTPUpdate` kaynakları depoda OLMADIĞI için
  ne ispatlanabildi ne çürütülebildi. Panic olsa bile PWM ağ-bağımsız tasarım gereği NVS'ten resume
  eder → zarar saniyelik çıkış boşluğu + telemetri kesintisi.

---

## KASITLI GÖRÜNÜYOR — TEYİT İSTER

- **[BLD-6] `.iss` MyAppVersion bayat (1.9.20; ağaç 1.9.22) — çıplak-ISCC koridoru yanlış etiketli
  kurulum üretir.** Mekanizmanın çekirdeği KAYITLI sahip kararıyla örtüşüyor (`denetim-bulgular-2.md:226`:
  ".iss MyAppVersion üretimi build_installer'da KALDI"). Üretim yolu kendini iyileştiriyor:
  `build_installer.ps1` önce `sync_versions`'i koşar sonra `Sync-ReleaseVersion` MyAppVersion'ı VERSION'dan
  yeniden yazar → her kurulum doğru etiketlenir. Ayakta kalan dar boşluk: `.iss` başlığının kendi KULLANIM
  adımı 2 çıplak `iscc.exe`/Inno-IDE yolunu belgeliyor ve o yol `Sync-ReleaseVersion`'ı atlar → 1.9.22 kodu
  1.9.20 etiketiyle derlenir; `MyAppVersion==VERSION` kıyas kapısı yok. Canlı dağıtım launcher-OTA'dan
  olduğu için saha maruziyeti minimal. **Sahibe:** çıplak-ISCC koridorunun bu sonucu kabul mü, yoksa `.iss`
  başlığına uyarı satırı / `MyAppVersion==VERSION` kapısı mı isteniyor?

---

## Özet

**12 AYAKTA + 13 DARALDI = 25 kesin bulgu** (kalan çekirdekleri gerçek), **1 çürütüldü** (BE-S7),
**1 doğrulanamadı** (FW-6, kütüphane kaynağı yok), **1 kasıtlı-teyit-ister** (BLD-6). Çoğu 2026-08-20
sonrası yazılan kodda; birçoğu önceki düzeltmelerin KENDİSİNDE (C2 döngü kırıcısının serileştirme
kopukluğu, P0 karşıt-kanıt testinin yanlış dilimi, "Beni hatırla" düzeltmesinin sahiplenme boşluğu,
AI Pro hazırlık akışının catDetected/kedi_var/ARDISIK eksikleri, seans yolu NACK bekçisizliği).

**En kritik iki:** [C1] C2 döngü kırıcısı üretimde ölü (`otomatik_durduruldu` komut JSON'una hiç
konmuyor — bozuk yayın her açılışta yeniden kurulur) ve [F1] P0 Inno E-stop karşıt-kanıt testi hiçbir
zaman kırmızıya dönemez (hasta-güvenliği boşluğunu [C6] maskeliyor). İkisi de koşturularak kanıtlandı.

**Hiç bakılamayanlar:** gerçek donanım/tezgâh ölçümleri (tüm firmware bulguları kod düzeyinde — S3+8266
REFLASH zaten bekliyor), Arduino kütüphane kaynakları (FW-6), canlı HiveMQ bulut ucu + Supabase RLS/RPC,
iOS/EAS, iki-istemci AI Pro'nun gerçek cat_organ modeliyle uçtan-uca reprosu (kimliksiz-sürüş çekirdeği
TestClient ile ölçüldü), `pemf-vet-web` ödeme/webhook akışı (5. turda denetlenmişti).
