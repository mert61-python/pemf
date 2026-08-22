# PEMF Vet — Hata Denetimi 2. Tur (2026-08-19/20)

Kapsam: yalnızca **kırık davranış**; 2026-08-17 denetiminin kapattığı ~45 bulgu tekrar
raporlanmadı (düzeltmelerin KENDİSİNDE bulunan yeni kusurlar raporlandı — birkaç tane var).
Yöntem: tek başına oryantasyon (denetim-bulgular.md + BUILD.md + CHANGELOG + donanım-uyum
raporu + `git log --since=2026-08-17`, 66 commit) → 5 katman tarayıcısı (36 benzersiz şüpheli)
→ **her şüpheli ayrı bir çürütme ajanına** ("bu neden bug DEĞİL?") → katman-aşan izler elle
kovalandı. Çürütme turu 3 şüpheliyi eledi, 18'ini daralttı; ölçülebilen her iddia
koşturularak/ölçülerek doğrulandı. **Kod DEĞİŞTİRİLMEDİ.**

Ciddiyet: **1** hasta güvenliği · **2** veri kaybı/sır · **3** cihaz kullanılamaz ·
**4** yanlış klinik çıktı · **5** diğer işlevsel.

## DÜZELTME KAYDI (2026-08-20 — 1. parti: [1.1] + [1.2])

Yöntem önceki denetimle aynı: **her düzeltme için ayrı test, düzeltmeden ÖNCE kırmızı olduğu
görüldü, sonra yeşile alındı, ardından mutasyonla doğrulandı** (kusuru geri getiren VE
aşırı-düzelten yöndeki mutasyonların ikisi de yakalanıyor).

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [1.2] | Firmware↔backend status sözleşmesi (connected/duty/current-ambient) | `servers/api_server.py` (status dalı) | `tests/test_esp_status_sozlesmesi.py` (8: 5 kusur + 2 karşıt-kanıt + 1 parite kapısı) | 5 kırmızı → 8/8 ✓ | 4/4 ✓ (connected=False geri · pwm_duty sil · pwm_duty_cycle sil · dize-işleme sil = aşırı-düzeltme) |
| [1.1a] | Durdurma turu `mqtt_unavailable`'ı teyit sayıyor + batch satırları okunmuyor | `pf/src/screens/ControlScreen.tsx` | `durdurmaTuruParalel.test.tsx` (+3) | 2 kırmızı → 8/8 ✓ | 2/2 ✓ (eski yüklem · satır kontrolünü atla) |
| [1.1b] | Aşırı-ısınma interlock'u teyitsiz "durduruldu" diyor | `pf/src/components/domain/CoilParameterPanel.tsx` | `coilDurdurmaOnayi.test.tsx` (3, yeni) | 1 kırmızı → 3/3 ✓ | 1/1 ✓ |
| [1.1c] | `/session/stop` koşulsuz success → hook uyarısı ölü | `servers/api_server.py` (`_stop_session_coils` dönüşü + yanıt alanı) · `pf/src/hooks/useSessionControl.ts` | `tests/test_session_stop_dogrulama.py` (5, yeni) · `useSessionControl.test.ts` (+2) | 3+1 kırmızı → 5/5 + 16/16 ✓ | 3/3 ✓ (ESP sonucu yok say · alanı koşulsuz ekle=alarm-yorgunluğu · hook uyarısını düşür) |

### Düzeltmelerde verilen bilinçli kararlar

- **[1.2] `connected` varsayılanı:** canlı (retain=0) status mesajının KENDİSİ canlılık kanıtı
  sayıldı; ama eski firmware'in AÇIK `status` dizesi varsa o KAZANIR ("offline" diyen cihaza
  inat canlı denmez) — karşıt-kanıt testi bu yönü ayrıca kilitliyor. Retained filtre aynen
  korunuyor (D-4/HG-4). Duty üç anahtarın İLK bulunanından okunur (`duty_cycle` → eski filo,
  `pwm_duty_cycle` → 8266, `pwm_duty` → S3); firmware anahtar adları parite kapısıyla KAYNAKTA
  kilitli — firmware anahtar değiştirirse test kırmızıya döner, sentetik payload bayatlayamaz.
  **Firmware'e dokunulmadı** (backend düzeltmesi eski VE yeni firmware'le doğru; reflash
  beklemez). Kardeş anahtarların firmware'de birleştirilmesi ayrı bir iş olarak sahibe kaldı.
- **[1.1] teyit tanımı:** teyit = YALNIZ açık `"success"`. `/coil/batch`'in üst-seviye
  status'u bilerek DEĞİŞTİRİLMEDİ (mevcut tüketici sözleşmesi); pf artık satır-başı
  `results[]`i sayıyor. `/session/stop`'un üst-seviye status'u da `"success"` KALDI (seans
  kaydı gerçekten kapanıyor; eski çağıranlar kırılmasın) — teyitsizlik AYRI alanda
  (`hardware_stop_unconfirmed`, yalnız doluysa) taşınıyor. Hook, bu alanı görünce uyarır ama
  seansı UI'da KAPATIR (kayıt kapandı; `null`/`error` yolundan farkı bilinçli — o yolda seans
  açık kalmaya devam eder). ControlScreen'in kendi bobin-turu uyarısı İKİNCİ katman olarak
  duruyor (bu deponun yerleşik çift-katman deseni; broker-ölü durdurmada iki uyarı kabul edildi).
- **[1.1] STM tarafı:** `state.hardware` yokken STM bobinlerine STOP hiç denenemez — bu
  "sessiz atlama" da artık teyitsiz sayılıyor; `update_coil` istisnası yutulmaz, WARN + teyitsiz.

### 2. parti — düzeltmelerin ADVERSARYAL gözden geçirmesi ve tamamlamaları

1. parti bittikten sonra diff bağımsız bir çürütme ajanına verildi ("bu düzeltme neyi bozuyor /
neyi kaçırıyor?"). İki GERÇEK boşluk + test kör noktaları buldu; hepsi aynı yöntemle
(kırmızı-önce + mutasyon) kapatıldı:

| # | Boşluk | Dosya(lar) | Test | Mutasyon |
|---|---|---|---|---|
| R1 | STM "teyidi" fiilen koşulsuzdu: `update_coil` STOP paketi kuyruğa HİÇ girmemişken True dönüyordu (dönüşü yalnız E-stop yolu `stop_all_coils` okuyordu) → `hardware_stop_unconfirmed` STM için yalnız "donanım hiç yok"ta çalışıyordu | `controllers/hardware_controller.py` (STOP dönüşü artık `stop_all_coils` ile AYNI sözleşme: "kuyruğa VERİLDİ") | `test_session_stop_dogrulama.py` (+2: kuyruk-dolu→False + START-semantiği-değişmedi karşıt-kanıtı) | 1/1 ✓ |
| R2 | Süre-watchdog / AI Pro stop / sahipsiz-bobin yolları teyitsiz listeyi YUTUYORDU — broker ölüyken seans "süre doldu" ile bitince operatöre hiçbir uyarı gitmiyordu | `servers/api_server.py` (`_bildir_teyitsiz_stop` yardımcısı + 3 site) · `servers/ai_router.py` (2 site) | `test_session_stop_dogrulama.py` (+3: watchdog davranışsal + AI Pro stop ucu + teyitli-yolda-uyarı-yok) | 2/2 ✓ |
| R3 | S3 sensör arızasında (NaN→null) `float(None)` TypeError'ı status işlemeyi YARIDA kesiyordu — yeni eklenen current/ambient okumaları + WS + reconcile atlanıyordu (5 Hz WARN spam) | `servers/api_server.py` (alan-başına toleranslı dönüşüm; 0-nöbetçisi yazılmaz) | `test_esp_status_sozlesmesi.py` (+1) | 1/1 ✓ |
| R4 | Duty öncelik sırası gizil tuzak: ileride bir firmware komutlanan `duty_cycle` + efektif `pwm_duty` birlikte yayınlarsa komutlanan efektifi gölgelerdi | `servers/api_server.py` (öncelik: efektif `pwm_*` → eski `duty_cycle`) | `test_esp_status_sozlesmesi.py` (+1) | 1/1 ✓ |
| R5 | Test kör noktaları: parite kapısı `pwm_active`'i ve 8266'nın ayrı `sensors` yayınını kilitlemiyordu | `test_esp_status_sozlesmesi.py` parite kapısı genişletildi | — | — |

Gözden geçirmenin "RİSKLİ AMA KABUL EDİLEBİLİR" bulguları (bilinçli bırakıldı, kayda geçiyor):
- **S3 artık seans ortasında bayat-telemetri STOP'u alabilir** — [1.2] öncesi watchdog S3'ü hiç
  göremiyordu; şimdi 30 sn'lik gerçek telemetri boşluğu STOP üretir. Bu, 8266 için zaten geçerli
  TASARLANMIŞ fail-safe; kadans marjı geniş (S3 status 5 Hz / 8266 sensors ~3 sn ↔ eşik 30 sn) ve
  `pemf/coil/{1-5}/status`a yayın yapan hiçbir şey yok (yanlış-pozitif üreticisi bulunamadı).
- **Broker-ölü manuel durdurmada çifte uyarı** (hook + bobin-turu) — bu deponun yerleşik
  çift-katman deseni; bilinçli kabul.
- `/api/hardware/command stop_coil` artık kuyruk-dolu geçici durumda dürüstçe `error` döner
  (eskiden koşulsuz success) — `stop_all_coils` dalıyla tutarlı.

### 3. parti — [1.3] firmware düzeltmesi (S3 + 8266)

⚠️ **Bu parti C kodu değiştirir; bu makinede ESP derleyicisi YOK.** Doğrulama: yorum-soyulmuş
kaynakta yapısal sıra/taban kapıları + ayrıştırıcı Python modeli + mutasyon; **tezgâh prosedürü
`docs/VERIFICATION.md` §11'de ve REFLASH öncesi ZORUNLU** (repo pratiği [FIX-1c] ile aynı).

| # | Değişiklik | Dosya(lar) | Test | Mutasyon |
|---|---|---|---|---|
| F1 | S3: devralınan birikim `_beginOutput`a PARAMETRE girer (`devralinanSuresizMs=0` varsayılanı = taze START pencereyi sıfırlamaya devam eder); sayaç ataması `forceSaveState`'ten ÖNCE → içerideki kayıt NVS'e ≈0 değil DOĞRU kümülatifi yazar. Eski "çağrıdan sonra RAM'e geri yükle" deseni kaynaktan çıktı. | `esps3_pemf_coil/CoilController.{h,cpp}` | `test_plan_a_deadman.py` "A-1 TAMAMLAMASI" (4 yeni: sıra kapısı + taban kapısı + ayrıştırıcı model + taze-start/süreli karşıt-kanıtı); 3'ü kırmızı-önce | sıra-bozma + YORUM-KANDIRMACASI birlikte ✓ (soyucu yorumdaki "doğru" satırı görmüyor) |
| F2 | RESUME TABANI (iki cihaz): her resume `NVS_KAYIT_ARALIGI_MS` (30 sn, periyodik kayıt aralığıyla TEK KAYNAK — SharedDefs.h) taban sayılır ve HEMEN kalıcılaştırılır (S3: `_beginOutput` içi kayıt; 8266: `restorePWMState` sonunda `savePWMState`). Gerekçe: <30 sn periyotlu çök-diril döngüsünde HİÇBİR periyodik kayıt koşamaz → taban olmadan kümülatif hiç büyümez, 7200 sn tavan sıfırdan başlayan hızlı döngüde HİÇ dolmazdı (bulgunun "<30 sn crash-loop" iddiasının tam kapanışı). Yön FAIL-SAFE: resume başına ≤30 sn ERKEN durma; süreli resume'a taban UYGULANMAZ. | `esps3_pemf_coil/CoilController.cpp` · `esp8266_pemf_coil/CoilController.cpp` · iki `SharedDefs.h` | aynı bölüm | S3-taban-sil ✓ · 8266-taban/kalıcılaştırma-sil ✓ · 8266 kayıt-sırası-boz ✓ · model-eşitle ✓ |

**Bilinçli kararlar (3. parti):**
- Taban SÜRESİZ moda özgü; **süreli (duration>0) resume'un kalan-süre hesabına dokunulmadı**
  (karşıt-kanıt kapısı kilitli). 8266 restore'unun artık EEPROM'a yazması süreli resume'da kalan
  süreyi resume'lar arası KORUR (S3 pariteli davranış) — kısaltmaz/uzatmaz.
- `test_plan_a_deadman.py`'nin eski şekil-kapıları (satır 103/104/106) yeni biçime güncellendi —
  niyetleri (devralma + taze-start sıfırlaması) aynen korunuyor, artık sıra/taban da kilitli.

**3. partinin adversaryal C-incelemesi (bağımsız ajan):** düzeltmede gerçek kusur BULUNAMADI;
el-derleme denetimi temiz (default-arg yalnız bildirimde; dört `_beginOutput` çağrı yeri yeni
imzayla geçerli; ternary tipleri daraltmasız; meşru değerlerde taşma yok; S3 timed-resume bit-bit
aynı; 8266 restore-save çift-düşürme yapmıyor; `EEPROM.begin` restore'dan önce, adres çakışması
yok). Kayda geçen risk notları: (1) bozuk-NVS'te teorik `elapsedMs` sarması (tek-bayt XOR checksum
penceresi ~7×10⁻⁶×1/256; zarf "taze start = 2 saat" ile aynı → kabul); (2) tavan-dolu resume'da
cap-denetimi ilk process tick'inde koştuğu için ≤200 ms'lik tek-boot çıkış blip'i (cap-stop
`active=false` kalıcılaştırdığı için tekrarlamaz — iyileştirme fırsatı, kusur değil); (3) test
kapılarının latent kırılganlıkları: `_c_soy` string-içi `//`yi (bugün iki CoilController'da yok;
`NetworkManager.cpp:916`'da var — kapılar o dosyayı SOYMUYOR) ve `_c_govde`nin sınır listesi
(`\nPWMState ` vb. yok) — bugün dördü de doğru sınırda ölçüldü, kayda geçti.

### ✅ BU TURDA BULUNAN YENİ AÇIK BULGU — 12. partide KAPANDI (sahip onayı 2026-08-20)

**SÜRELİ seans, <30 sn periyotlu çök-diril döngüsünde iki cihazda da HİÇ bitmiyor.** Süreli
resume'da `elapsed` yalnız periyodik kayıtla (30 sn) büyür; <30 sn döngüde hiçbir kayıt koşamaz →
`remaining` her resume'da aynı kalır ve 20 dk'lık seans patolojik brown-out döngüsünde süresiz
sürer (bobin çevrim başına ~20-30 sn enerjili; ESP'de termal kesme son sınır, STM etkilenmez —
kalıcılık yok; çevrimiçiyse backend A-3 reconcile ikinci katman). Süresiz-mod için eklenen taban
mekanizması buraya da uygulanabilir (resume başına kalan süreden bir aralık düşmek, fail-safe yön:
seans en fazla resume başına 30 sn KISALIR) — ama bu, süreli seansın klinik semantiğini değiştirir;
**sahip onayı olmadan yapılmadı**, kayda geçti. İnceleme notu: bu döngüde 8266'nın boot-anı
`EEPROM.commit`i sınırsız tekrarlanır (~100k çevrimde sektör aşınması) — arıza yönü yine fail-safe
(magic/checksum bozulur → resume durur, döngü fiilen biter), ama timed-ikizi kapatılırsa bu aşınma
yolu da kendiliğinden sınırlanır.

### 4. parti — [2.1] + [2.2] (2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [2.1] | APK kapısı seanssız çalışan bobinlere kör | `servers/session_router.py` (`/api/session/active`e canlı-durumdan `hardware_running` + `running_coil_ids`; GET SALT-OKUNUR kuralı korunuyor — karşıt-kanıt testli) · `pf/src/hooks/useApkGuncelleme.ts` (yüklem `is_active \|\| hardware_running`; POZİTİF-kanıt/fail-open aynen) | `tests/test_session_active_donanim.py` (4, yeni) · `useApkGuncelleme.seansKapisi.test.ts` (+3) | 3+1 kırmızı → 4/4 + 10/10 ✓ | 3/3 ✓ — aşırı-düzeltme yönü (`!== false` fail-closed) ÜÇ karşıt-kanıt testine birden takıldı ("güncelleme ZORUNLU KILINAMAZ" sahip kararı test-kilitli) |
| [2.2] | restore sonrası `git add -A` sızıntı yolu + gitleaks körlüğü | `build_tools/secrets_backup.py` (`_git_sir_korumasi`: skip-worktree'yi ARAÇ uygular; git yoksa/düşerse YÜKSEK SESLİ uyarı + tek satırlık kabuk-bağımsız komut; repo-olmayan kökte sessiz) · `.gitleaks.toml` (2 özel kural: Secrets.h sabitleri `[^"<]+` + path-kapsamlı config.json — izlenen placeholder'lar YEŞİL) | `tests/test_secrets_backup_git_korumasi.py` (6, yeni; gitleaks binarisi varsa davranışsal, yoksa skip) | 4 kırmızı → 5/5+1s ✓ | 3/3 ✓ — kural-genişletme mutasyonu (placeholder'ı da yakalar) yanlış-alarm karşıt-kanıtına takıldı |

**Bilinçli kararlar (4. parti):**
- **[2.1]** Eski backend ↔ yeni APK her kombinasyonda geriye uyumlu: alan yoksa `undefined` →
  fail-open (bilinçli; kalıcı güncellenemezlik yasak). Uç SALT-OKUNUR kaldı (watchdog STOP'u
  bastırılamaz — dosyanın kendi kuralı). ⚠️ `_live_state["coils"]` LİSTE DEĞİL 0-7 anahtarlı
  SÖZLÜK — ilk denemede enumerate tuzağına düştü, test yakaladı, indeksli erişimle düzeltildi.
- **[2.2]** gitleaks kuralları BİLEREK dar: yalnız bu beş sabit adı + path-kapsamlı config.json —
  depo tarihçesi ve `sb_publishable_*` muafiyet düzeni etkilenmez (CI main tarihçesini tarar;
  izlenen içerikler placeholder olarak girmişti, kural onlarda yeşil — gerçek izlenen içerik
  üzerinde testle kilitli). `esp` dalı CI taramasının dışında ve İÇİNDE CANLI SIR OLDUĞU BİLİNİYOR
  (2026-08-04 açık P0, rotasyon sahip tarafından reddedilmişti) — bu düzeltme onu ÇÖZMEZ, yalnız
  yeni sızıntı yolunu kapatır. Testteki `git show` çıktısı BAYT okunur (cp1254 tuzağı — C1 sınıfı).

### 5. parti — [3.2] + [3.4] (2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [3.2] | E-stop ack `command_id` yalnız ms çözünürlüklü — aynı ms'de iki tetik (manuel+alarm) aynı id'yi üretip `_register_ack` üzerine-yazma / `_wait_ack` pop yarışıyla acil-durdurma anında SAHTE "ONAYI GELMEDİ" alarmı basıyordu; NACK (success=false) de yanlış "(2s) GELMEDİ" metniyle bildiriliyordu | `servers/api_server.py` (`_estop_sira` süreç-ömürlü sayaç → id `estop_{coil}_{ms}_{sıra}`; `_estop_ack_watch`e ayrı NACK dalı) | `tests/test_estop_ack_benzersizligi.py` (5, yeni: dondurulmuş-saat benzersizlik + S3 35-karakter kırpma sınırı karşıt-kanıtı + NACK metni + timeout/başarı yolları değişmedi) | 2 kırmızı → 5/5 ✓ | 2/2 ✓ (sıra-eki sil · NACK dalını kapat) |
| [3.4] | Yayın runbook'u paketleri SABİT `client-app-v1.8.0`a yükletiyordu (0e2b1ed'den beri bayat; 1.9.16'dan beri URL'ler sürüm-başına etikette) → harfiyen izlense saha-geneli 404 | `BUILD.md` §6 (adım 0: make_manifest sürüm-etiketiyle; adım 1: paketler `client-app-v<sürüm>`e + "URL KORUNDU" kuralı + asset doğrulaması; manifest SABİT v1.8.0'da KALIR) · `pemf-app-packages/README.md` (ikinci bayat kopya) | `tests/test_yayin_runbook_etiketi.py` (4, yeni: paket-satırı-v1.8.0-yasak + sürüm-etiketi-örneği-var + manifest-sabit-adres karşıt-kanıtı + canlı manifest gerçeklik çıpası) | 2 kırmızı → 4/4 ✓ | 1/1 ✓ (bayat v1.8.0 satırı geri) |

**Bilinçli kararlar (5. parti):**
- **[3.2]** Sıra sayacı YALNIZ E-stop id'lerine eklendi (ack kaydı yalnız orada); broadcast/
  reconcile/stale id'leri kayıt açmadığı için çakışmaları zararsız — dokunulmadı. id biçimi S3
  firmware'inin 35-karakter kırpma sınırının altında ve bu sınır karşıt-kanıt testiyle kilitli.
  ESP alarm dalındaki debounce'suzluk (aynı arızada N tam E-stop turu) AYRI kayıtlı yan bulgudur —
  STOP idempotent olduğundan güvenlik riski değil, bu partide kapsam dışı bırakıldı.
- **[3.4]** "v1.8.0 yasak" kuralı SATIR-kapsamlı (yalnız paket yükleme satırları): manifest.json'ın
  SABİT v1.8.0 adresi ve GERİ ÇEKME bölümü bilerek etkilenmez — karşıt-kanıt testi manifest
  satırının v1.8.0'da KALMASINI ayrıca kilitler. Gerçeklik çıpası depodaki manifest'e bağlı:
  tek-etiket düzenine bilinçli dönüş olursa önce çıpa kırmızıya döner, kural körlemesine dayatmaz.

### 6. parti — [4.2] + [4.4] (2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [4.2] | İki firmware de yerel termal korumada event yayınlıyor (S3: thermal_stop; 8266: stop+lock+unlock) ama backend events dalı bunları İŞLEMİYORDU — cihazın en önemli yerel güvenlik eylemi operatöre görünmezdi, termal kilitteki start redleri açıklamasız kalırdı | `servers/api_server.py` (events dalına termal üçlüsü: stop=error+🔥, lock=warning, unlock=success; firmware'in ölçtüğü sıcaklık metni bildirime taşınır; WS `thermal_event`; RETAINED filtresi aynen) | `tests/test_termal_olay_gorunurlugu.py` (4, yeni: üç olay + retained karşıt-kanıtı + firmware ad-parite kapısı) | 2 kırmızı → 4/4 ✓ | 2/2 ✓ (dal kapat · lock/unlock'u düşür) |
| [4.4] | D-3 clamp'i üç ham siteden yalnız ikisini kapatmıştı — `/api/session/start` ESP'ye HAM freq gönderiyordu (>1000 Hz'lik seansta STM istenen frekansta, ESP sessizce 1000'de → karma dizide tutarsız doz) | `servers/api_server.py` (seans ESP yayını + run-log `normalize_esp_frequency_hz` — tek-bobin/batch kuralıyla birebir) | `tests/test_esp_freq_clamp.py` (+2 DAVRANIŞSAL: gerçek endpoint koşar, ESP'ye giden MQTT payload ölçülür — eski kapı yalnız kaynak-substring'iydi ve bu boşluğu göremezdi) | 1 kırmızı → 14/14 ✓ | 1/1 ✓ |

**Bilinçli kararlar (6. parti):** [4.2] canlı-durum MUTATE EDİLMEDİ (running/duty'ye dokunulmadı —
cihaz kendini durdurdu, 5 Hz status zaten ~200 ms'de yansıtır; olayın işi GÖRÜNÜRLÜK). pf,
`thermal_event` WS tipini tanımaz ama bilinmeyen tip sessizce düşer (ölçülmüştü) ve operatör
bildirimi `notification` kanalından zaten ulaşır — pf gösterimi ayrı/opsiyonel iş. [4.4] STM
seans dalı ve `SessionStartPayload` sınırsız KALDI (freq güvenlik-limiti DEĞİL — sahip kararı;
yalnız transport-tavanı normalize edilir, tek-bobin/batch ile aynı ilke).

### 7. parti — [3.1] + [3.5] (2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [3.1] | Takas-sonrası geri-alma hatası `let _ =` ile yutuluyordu: geri alma düşerse UI "iptal edildi" derken cihaz DOĞRULANMAMIŞ sürümde kalıyor, `runtime.old` sonraki turda tüketiliyordu. Alt-durum: tam_takas geri almasında `rt→runtime.bozuk` başarılı + `eski→rt` düşerse kurulum o oturum boyunca HİÇ runtime dizinsiz kalıyordu | `launcher/core/src/flow.rs` (çağrı yeri: geri-alma hatası açık "GERI ALINAMADI … 'Onar' calistirin" hatasına YÜKSELTİLİR — iptal maskesi takılmaz; `guncellemeyi_geri_al`: `eski→rt` düşerse doğrulanmamış-yeni `runtime.bozuk`tan geri konur — çalışan-bilinmeyen > hiç yok) | `upgrade_drill.rs` TATBİKAT 5 (2 yeni; geri almayı DETERMİNİSTİK düşürme: runtime.old içinde açık dosya tutamacı — Windows içinde açık handle olan dizini taşımayı reddeder, üretim karşılığı AV/kilitli model) | 2 kırmızı → 13/13 ✓ (launcher tam: 249/249) | 2/2 ✓ (yutmayı geri getir · bozuk-restore'u kapat) |
| [3.5] | `restore_assets.ps1` çekirdek modeli (inference_cat_organ — YALNIZ base-deps katmanında) hiç getirmiyordu → temiz makinede ~1 saatlik akış son kapıda ölüyordu | `scripts/restore_assets.ps1` (deps katmanından YALNIZ `_internal/ai_models/` altı sha-doğrulamalı açılır; mevcutsa atlanır `-Force` yeniler; deps'te çekirdek yoksa SESSİZ "0 dosya" başarısı YASAK → açık hata; test kancaları `-DepsZipYolu/-YalnizCekirdek/-KokOverride` — PEMF_PKG_OUT emsali) | `tests/test_restore_assets_cekirdek.py` (3, yeni: filtreli açılım + boş-deps açık-hata + ters-bölülü girdi) | 2 kırmızı → 3/3 ✓ | 2/2 ✓ (filtre boz · sıfır-sayı hatasını kapat) |

**Bilinçli kararlar (7. parti):**
- **[3.1]** İptal + başarılı geri alma yolunun davranışı DEĞİŞMEDİ (tatbikat-4 aynen yeşil);
  yükseltme yalnız "geri alma DÜŞTÜ" dalında. Kayıt-yazmama fail-safe'i aynen korunuyor.
  İki yeni tatbikat `#[cfg(windows)]` — kilit numarası Windows semantiğine dayanır (CI launcher
  işi windows-latest; üretim platformu da o).
- **[3.5]** Çekirdek indirme deps katmanının TAMAMINI (~1,4 GB) çeker — cat_organ'ın (~200 MB)
  daha küçük yayın kaynağı yok (make_model_zip yalnız "home" üretir); mesaj bunu açıkça söyler,
  sha doğrulaması profil zip'leriyle aynı gerekçeyle zorunlu. Filtre `_internal/ai_models/`
  ALTININ tamamı: deps katmanına ileride eklenecek yeni çekirdek modeller de kendiliğinden gelir
  (CORE_MODELS tek-kaynağına dolaylı uyum). Betiğin bayat "51/40" sayımı da düzeltildi.

### 8. parti — [4.1] + [4.5] (2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [4.1] | Gözlem-modalı sıfırlama anahtarı yalnız hasta ADI'ydı — modal `running` yüzünden gizliyken (obsSession null'a düşmeden) AYNI İSİMLİ B'nin seansı bitince A'nın kaydedilmemiş notu B'nin modalında kalıyor, B'nin tıbbi kaydına gidebiliyordu | `pf/src/components/domain/ObservationNotesModal.tsx` (sıfırlama dep'i: `obsKey` + isim) · `pf/src/screens/ControlScreen.tsx` (her seansın YÜKSELEN kenarında artan `obsKey` sayacı; aynı seansın treatment tick'leri anahtarı değiştirmez) | `gozlemNotuKorunmasi.test.tsx` (+2: aynı-isim-farklı-seans sıfırlanır + aynı-seans-gizle/göster korunur) · `gozlemAnahtariKimligi.test.tsx` (1, yeni — KABLOLAMA: gerçek ControlScreen iki seans döngüsünde modal'a FARKLI obsKey taşır) | 2 kırmızı → 7/7 ✓ | 2/2 ✓ (dep'ten obsKey'i düşür · sayaç artmasın) |
| [4.5] | `_begin_coil_run` teslim/kabul sonucundan bağımsız koşu kaydı açıyordu: ESP publish False (komut KESİN gitmedi) ya da STM `update_coil` False (parametre reddi) olsa da tedavi geçmişine "koştu" yazılıyordu; STM tekil/batch reddi üstüne "success" dönüyordu | `servers/api_server.py` (4 site: tekil+batch × STM+ESP — koşu kaydı yalnız doğrulanmış publish / kabul edilen update_coil'de; STM tekil yanıtı `error`, batch satırı `invalid`) | `tests/test_hayalet_kosu_kaydi.py` (6, yeni: 3 kusur + 3 karşıt-kanıt — STOP'ta finish publish düşse de ÇALIŞIR: açık kaydı kapatmak güvenli taraf) | 3 kırmızı → 6/6 ✓ | 3/3 ✓ (ESP koşulsuz · STM kabul zorla · batch kabul zorla) |

**Bilinçli kararlar (8. parti):**
- **[4.1]** Kimlik SEANS-başına istemci sayacı (`obsKey`) — backend'e yeni yüzey açılmadı
  (db_session_id'yi taşımak `/session/notes` sözleşmesini değiştirirdi; çok-istemcili yarış YAN
  bulgu olarak kayıtlı duruyor, bu düzeltme tek-istemci bulaşmasını kapatır). Bulgu-20 koruması
  (gizle→göster'de not korunur) karşıt-kanıtla aynen kilitli.
- **[4.5]** Seans yolunun ESP koşu kayıtları DEĞİŞMEDİ: publish bilerek arka planda (snappy
  start) → sonuç bilinemez; seans zaten broker-erişilemezse `esp_unreachable` uyarısı taşıyor.
  STOP'ta `_finish_coil_run` publish sonucundan bağımsız ÇALIŞMAYA devam eder (açık kaydı
  kapatmak güvenli taraftır; fiziksel-durmama uyarısı [1.1]'in işi) — testle kilitli. Bulgunun
  "8266 NACK'i görünmez" yarısı AÇIK kaldı: manuel yolda ack-bekleme yok (yalnız E-stop bekler);
  ack-mimarisinin manuel yola genişletilmesi ayrı iş.

### 9. parti — [4.3] S3 firmware (2026-08-20)

⚠️ **C kodu değişir; bu makinede ESP derleyicisi yok** — doğrulama 3. partiyle aynı disiplin
(model + yorum-soyulmuş yapısal kapı + mutasyon); **tezgâh prosedürü `docs/VERIFICATION.md`
§12'de, S3 REFLASH oturumunda zorunlu.**

| # | Değişiklik | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [4.3] | `syncPulseISR` PWM PASİFKEN darbeyi tamamen YOK SAYAR (ne sayar ne latch'ler). Eskiden seans bitince donan `s_tick` kilit penceresindeyse boşta gelen 8 PB1 darbesi sync'i kapatıyor, AYNI frekanslı sonraki seans (AI Pro hep 1 Hz → `freqChanged=false` → latch bilinçli korunur) faz senkronsuz koşuyordu; boşta darbeler `sync_locked/ignored` tezgâh sayaçlarını da kirletiyordu | `esps3_pemf_coil/CoilController.cpp` (ISR başına `!s_active` erken dönüşü) | `test_s3_sync_dc_yapisma.py` (+4: modele AKTİFLİK semantiği eklendi — pasif-darbe-latch'lemez + sayaç-kirletmez + ESKİ-semantik ayrıştırıcısı + yorum-soyulmuş yapısal sıra kapısı) | 1 kırmızı → 11/11 ✓ | 3/3 ✓ (kapı-sil + YORUM-KANDIRMACASI birlikte ✓ · model-eşitle ✓) |

**Bilinçli kararlar (9. parti):** seans İÇİ latch birikimi ve `freqChanged`-korumalı latch
kalıcılığı (HG-3'ün asıl koruması) DEĞİŞMEDİ — mevcut 6 model testi aynen yeşil; VERIFICATION
§12 adım 4 bunu tezgâhta da karşıt-kanıt olarak doğrulatıyor. `_stopPWM`/`_beginOutput`'ta
streak/wrap sıfırlaması BİLEREK eklenmedi (seanslar-arası gerçek-uyuşmazlık hafızası korunur).

### 10. parti — [5.4] + [5.5] (2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [5.4] | EXE dosya-özellikleri sürümü 1.9.14'te DONMUŞTU: `docs/version_info.txt`'i yalnız KAPALI Inno kanalı yeniliyordu; canlı yayın yolu hiç dokunmuyordu ve hiçbir kapı görmüyordu (3 yayın sessiz kayma) | `build_tools/sync_versions.ps1` (version_info artık backend kanal HEDEFİ — filevers/prodvers/FileVersion/ProductVersion; otorite `versions.json._kanallar` iddiasıyla hizalandı) · `scripts/build_backend_exe.ps1` (sync çağrısı — build_installer/build_apk deseni) · `docs/version_info.txt` (sync koşularak 1.9.17'ye çekildi) | `tests/test_version_info_senkronu.py` (3, yeni: eşitlik kapısı + çağrı kapısı + `-Check` davranışsal karşıt-kanıtı) | 3 kırmızı → 3/3 ✓ | 3/3 ✓ — M1'de dosya bozuldu→kapı kırmızı→**sync mekanizmasının kendisi onardı**→yeşil (uçtan uca kanıt); M2 mutasyonu İLK kapımın zaafını yakaladı (Warn-dizesindeki geçiş kandırıyordu) → kapı iki-iddialı sertleştirildi (yol-kurulumu + `& $SyncScript` çağrısı, yorum-satırsız) |
| [5.5] | CHANGELOG 1.9.16/1.9.17 "Paket kimliği (buildId)" satırları base.zip sha'sını etiketliyordu — katmanlı sahadaki cihazlar app-katmanı sha'sını raporlar; destek eşleştirmesi iki yönde de kırıktı | `CHANGELOG.md` (iki girdi düzeltildi + Kural bölümüne katmanlı-kurulum notu; base sha bilgi olarak korunuyor, "buildId" diye ETİKETLENMİYOR) | `tests/test_changelog_buildid_etiketi.py` (1, yeni: en üst girdinin buildId'si = manifest `layers.app` sha[:12] — gelecek yayınlarda da CI kapısı) | 1 kırmızı → 1/1 ✓ | 1/1 ✓ |

**Bilinçli kararlar (10. parti):** `.iss` (MyAppVersion) üretimi build_installer'da KALDI (Inno'ya
özgü); build_installer'ın kendi `Sync-ReleaseVersion`ı idempotent çift-yazım olarak duruyor —
kaldırmak Inno kanalını sync'e bağımlı kılardı. buildId kapısı yalnız EN ÜST girdiyi kilitler
(manifest yalnız güncel yayını taşır); eski girdiler editoryal düzeltildi.

### 11. parti — [5.1] + [5.2] + [5.3] firmware kardeş-birim üçlüsü (2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [5.1] | `pwm_remaining_time` AYNI JSON anahtarı iki kardeşte FARKLI BİRİM taşıyordu: 8266 ham milisaniye, S3 saniye — alanı okuyacak İLK tüketici bobin 8 için 1000× yanlış kalan-süre görecekti (depo 1 no'lu deseni: aynı kural, iki transport) | `firmware/esp8266_pemf_coil/CoilController.cpp` (`populateStatus`: `(_pwmDuration - elapsed) / 1000UL` — S3 `getState` paritesi) | `tests/test_esp_kardes_birim_paritesi.py` T1 (S3 `/ 1000UL` referans-çapası + 8266 atama-içi `/ 1000` kapısı, yorum-soyulmuş) | kırmızı → ✓ | ✓ M1: `/ 1000UL` kaldırıldı → T1 kırmızı → geri |
| [5.2] | 8266 `restorePWMState` `_pwmDurationSec`'i geri kurmuyordu (ctor'daki 0'da kalıyordu) → resume sonrası SÜRELİ seans status'ta `pwm_duration=0` = SÜRESİZ nöbetçisi raporluyor, `pwm_remaining_time` ile çelişiyordu (S3 `loadState` kalan süreden kurar) | aynı dosya (`restorePWMState`: `_pwmDurationSec = (state.duration > 0) ? (int)(remaining / 1000UL) : 0;` + süreli dalda min-1 kelepçesi — kalan <1 sn'nin 0'a yuvarlanıp süresiz nöbetçisine dönmemesi için) | T2 (atama `remaining`'den türer) + KARŞIT_5_2 (süresiz resume'da 0 KALIR — süresiz sözleşmesi) | kırmızı → ✓ | ✓ M2: atama satırı silindi → T2+KARŞIT kırmızı → geri |
| [5.3] | S3 `CMD_UPDATE_PARAMS` fazı KOŞULSUZ uyguluyordu; parse `phase` anahtarı YOKKEN 0 dolduruyordu → fazsız bir set_params çok-bobinli faz desenini SESSİZCE sıfırlardı (freq/duty ">0 ise" korumalıyken faz korumasızdı; 0 meşru faz olduğundan ">0" çözüm olamazdı) | `firmware/esps3_pemf_coil/SharedDefs.h` (`PHASE_BELIRTILMEDI (-1)` nöbetçisi) · `NetworkManager.cpp` (UPDATE + SET_PARAMS dalları: yoklukta nöbetçi; açık değerler parse'ta 0..359'a sarılır — açık negatifler artık controller'a `-1` sanılmadan ulaşır) · `CoilController.cpp` (`if (cmd.phase != PHASE_BELIRTILMEDI)` koruması, freq/duty ile aynı kural) | T3 (iki parse dalı + SharedDefs tanımı) + T4 (controller'da nöbetçi kontrolü atamadan ÖNCE) + KARŞIT_5_3 (START `: 0` KALIR, SYNC_ALL nöbetçisiz) | kırmızı → ✓ | ✓ M3 çifti: UPDATE dalı `: 0`'a döndürüldü → T3 kırmızı; controller koruması söküldü → T4 kırmızı → ikisi de geri |

Toplam mutasyon: **4/4 yakalandı**. Test geliştirme dürüstlük notları: (a) T5 sınır dizesi ilk denemede
8266'ya ait `isCommandProcessed` idi (S3 NetworkManager'da yok → ValueError) — sınır `doc["command_id"]`'ye
düzeltildi; (b) `_govde` yardımcısı `restorePWMState` 8266 dosyasının SON fonksiyonu olduğu için
dosya-sonu düşüşü kazandı (bitiş bulunamazsa EOF'a kadar).

**Bilinçli kararlar (11. parti):** START ve SYNC_ALL dallarında faz varsayılanı **0 KALIR** (taze
seansın doğal başlangıcı; KARŞIT_5_3 kilitler) — nöbetçi yalnız "mevcut koşuyu DEĞİŞTİR" anlamı
taşıyan UPDATE/SET_PARAMS'ta. [5.2]'de `_pwmStartTimestamp` BİLEREK geri kurulmadı: zamanlama
otoritesi millis-tabanlı `_pwmStartTime` (resume'da taze kurulur); epoch alanı bilgilendirmedir ve
boot'ta NTP henüz hazır değilken bayat epoch'u geri basmak resume koşusunun başlangıcını yanlış
gösterirdi — kalan-süre matematiği bundan bağımsız doğru. Controller'daki `% 360` sarması parse
sarmalamasına rağmen savunma-derinliği olarak KALDI. ⚠️ Üçü de REFLASH kapsamında — tezgâh
doğrulaması VERIFICATION oturumuna dahil (C bu makinede derlenmiyor; kapılar yorum-soyulmuş yapısal).

### 12. parti — SÜRELİ seans crash-loop İKİZİ (sahip onayı 2026-08-20; S3+8266)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| ikiz | SÜRELİ seans <30 sn periyotlu çök-diril döngüsünde iki cihazda da HİÇ bitmiyordu: elapsed yalnız periyodik kayıtla (30 sn) büyür, <30 sn döngüde hiçbir kayıt koşamaz → remaining her resume'da aynı kalır, 20 dk'lık seans süresiz sürer (bobin çevrim başına ~20-30 sn enerjili) | `esps3_pemf_coil/CoilController.cpp` (loadState: kalanMs hesabına devralınan elapsed + BİR KAYIT ARALIĞI; taban dahil dolmuşsa resume YOK) · `esp8266_pemf_coil/CoilController.cpp` (restorePWMState: aynı sözleşme). Kalıcılaştırma zaten var: resume-anı kaydı `duration=KALAN, elapsed≈0` yazar (iki kardeşte ölçüldü) → taban çevrim başına birikir, döngü ≥30 sn/çevrim kısalır | `tests/test_sureli_crashloop_ikizi.py` (7, yeni: davranış modeli — tabansız model HİÇ bitmez / tabanlı ≤süre÷aralık çevrimde biter + kayıt-kontratı ayrıştırıcısı + tek-resume kaybı TAM BİR ARALIK zarfı + 2 yapısal kapı + süresiz-taban-dokunulmadı karşıt-kanıtı) | 2 kırmızı → 7/7 ✓ | 3/3 ✓ (S3 taban-sil · 8266 taban-sil · süresiz-taban-boz → karşıt-kanıt yakaladı) |

**Bilinçli kararlar (12. parti):** Yön FAIL-SAFE: seans resume başına EN FAZLA bir aralık ERKEN
biter (test zarfı tam-bir-aralık kaybını kilitler), UZAMASI artık imkânsız — klinik semantik
değişikliği sahip onaylı. Yan kazanç: 8266 boot-anı EEPROM.commit tekrarı artık süre/30 sn
çevrimiyle SINIRLI (denetimin aşınma notu kendiliğinden kapandı). ⚠️ REFLASH kapsamında (§14).

### 13. parti — [5.8] + [5.9] + [5.7] (backend + pf ciddiyet-5 kümesi, 2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [5.8] | Watchdog bildirimi publish SONUCUNU okumuyordu: broker çökükken de "STOP gönderildi" diyordu (1. turun sahte-"durduruldu" sınıfı); "log'a düşülür" vaadi de boştu (probe False döner, istisna atmaz → except hiç koşmaz) | `servers/api_server.py` (`stop_gitti` okunur; False/istisna → "STOP GÖNDERİLEMEDİ … HÂLÂ ENERJİLİ olabilir" (error) + uyarı logu; True → mevcut metin AYNEN) | `tests/test_watchdog_bildirim_durustlugu.py` (3, yeni; watchdog tek-tur sürme deseni test_kalan_davranissal'dan) | 2 kırmızı → 3/3 ✓ | 2/2 ✓ (hep-True · dal-tersle → karşıt-kanıt "başarılı yol warning KALIR"ı da yakaladı) |
| [5.9] | `checkHealth` başarılı her yanıtta deviceId'yi DİSKE yazıyordu; pairing onu token takasından ÖNCE çağırdığı için takas düşse de kayıtlı kimlik B'ye dönüyordu (F3 "token yoksa kalıcı yazım yok" delinmesi); birim testleri checkHealth'i mock'ladığından görünmezdi | `pf/src/services/discovery.ts` (`kimligiKaydet:false` seçeneği — varsayılan DEĞİŞMEZ, keşif merdiveni kimlik yazmaya devam eder) · `pf/src/services/pairing.ts` (ön-prob bayrakla; kalıcı yazım yalnız takas sonrası) | `discoveryKimlikYanEtkisi.test.ts` (3, yeni — checkHealth'in KENDİSİ fetch mock'uyla koşturulur) · `pairing.test.ts` (+1 bayrak kapısı) | 4 kırmızı → 19/19 ✓ | 3/3 ✓ (bayrak-yoksay · hiç-yazma → merdiven karşıt-kanıtı · pairing-bayrak-düşür) |
| [5.7] | Mobil erteleme kümesi: (a) kapı kapatıldıktan sonra UÇUŞTAKİ guncelle() ertelemeden habersiz — indirme bitince yükleyici o anki işin ÜSTÜNE sormadan açılıyordu; (c) `oran===null` yordamı "hiç başlamadı"yı "tamamlandı"dan ayıramıyor, tam inmiş paketten sonra erteleme bandı da susturuyordu | `pf/src/services/mobileUpdate.ts` (İKİNCİ bellek-içi bayrak `kurulumunuErtele` — atlandiMi'den AYRI: bandı susturmaz, yalnız oto-açılışı keser; guncelle() girişte TEMİZLER = açık niyet, kalıcı kilit yasak) · `useApkGuncelleme.ts` (erteleme kapısı seans kapısından SONRA + `paketHazir` alanı) · `MobileUpdateGate.tsx` (üç-yollu kural: hiç başlamadı→sustur; uçuşta/hazır→kurulum-ertele) | `useApkGuncelleme.ertelemeKapisi.test.ts` (5, yeni) · `MobileUpdateGate.test.tsx` (+2, 1 güncelleme) | kırmızı → 51/51 ✓ | 4/4 ✓ (kapı-sil · giriş-temizliği-sil · hep-ertele → atlandiMi karşıt-kanıtı · paketHazir-yoksay) |

**Bilinçli kararlar (13. parti):** [5.7b] (erteleme sonrası kancanın mesajları görünmüyor) ayrı UI
işi olarak KAPANMADI ama (a) düzeltmesi zarar yolunu kesti: sürpriz yükleyici artık imkânsız,
görünmeyen mesajlar yalnız kapının ölü örneğinde kalıyor (bant kendi örneğini üretir). [5.9]'da
`provisionToken` yan etkisine DOKUNULMADI (bulgu kapsamı device_id; uzak probda 403 no-op).
Erteleme bayrakları KASITEN bellek-içi (sahip kuralı: güncelleme kalıcı susturulamazın aynası).

### 14. parti — Onar/önbellek çelişkisi + [5.6] + [5.10] (launcher üçlüsü, sahip onayı 2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| Onar/önbellek | Temizlik yalnız O İŞLEMİN paket kümesini koruyordu: app-only oto-güncelleme geçerli deps.zip'i, seçimli kurulum kurulu-ama-seçilmemiş profil zip'ini "ölü" diye siliyordu → "Onar" eMMC'de 20+ dk indirmeye dönüyor, "indirilenler önbellekten gelir, yeniden İNMEZ" vaadi (ProfileRecordUnreadable metni dahil) boşa çıkıyordu; BAŞARISIZ güncelleme turu bile önbelleği silmiş oluyordu | `launcher/core/src/flow.rs` (`cihazin_guncel_paket_adlari`: katmanlar/base + KURULU profil modelleri; `disk_kapisi` `ayrica_koru` parametresi; 3 çağrı yeri) — üretim URL'leri paket başına SABİT olduğundan (--clobber aynı etikete) bu adlar eski+yeni sürümün AYNI önbellek adı; temizlik yalnız GERÇEKTEN ölü girdileri siler, eMMC disk-kazanımı DURUYOR | flow.rs tests (+2, yeni: kurulu-profil-zip korunur + ölü girdi YİNE silinir karşıt-kanıtı; güncel-katman korunur) | 2 kırmızı → 206/206 lib ✓ | 2/2 ✓ (extend-sil · temizliği-tümden-kapat → karşıt-kanıt + mevcut olu_onbellek testi yakaladı) |
| [5.6] | Duraklat→İptal ölüydü: komut {status:"paused"} ile çoktan dönmüş, CTL_CANCEL'ı okuyacak görev yok; her komut girişi bayrağı CTL_RUN'la eziyor → İptal grileşir, ekran süresiz "Duraklatıldı"da (tek çıkış pencereyi kapatmak) | `launcher/app/ui/index.html` (`pausedOp` bayrağı + `iptalTiklandi`: duraklatılmışken temizlik GÖREVSİZ — açılıştaki "yarım kaldı → İptal et" yolundaki `discard_pending` aynısı, plan .part'ları korunur; ekran hazır/seçim'e döner; koşan görev varken bayrak yolu AYNEN) | `tests/test_iptal_duraklatilmisken.py` (Node-harness, 3 senaryo; desen test_devam_et'ten) | ✓ (mutasyonla kanıt) | 2/2 ✓ (eski-davranış-dirilt · hep-görevsiz-yol → koşarken karşıt-kanıtı) |
| [5.10] | Kurulum İptal'i `clear_partials(&root,&[])` ile eşzamanlı arka plan ön-indirmesinin YABANCI ≤1,4 GB .part'ını da siliyordu (yorumdaki "o sorun discard_pending yolundaydı" gerekçesi eşzamanlılıkta yanlış: ön-indirme kilidi yalnız yoklayıp bırakır) | `launcher/app/src/main.rs` (iptal dalı `plan_part_paths` korumasıyla — discard_pending'le AYNI desen; kurulu-olmayan cihazda plan boş → tümü silinir, ilk-kurulum sözleşmesi korunur) | aynı dosyada yapısal kapı + karşıt (discard_pending koruması aynen); çekirdek sözleşme `iptal_temizligi.rs` yeşil | kırmızı → ✓ | 1/1 ✓ (`&[]`e geri döndür) |

**Bilinçli kararlar (14. parti):** [5.6] duraklatılmış-iptal .part'ları SİLMEZ (plan koruması) —
"İptal"in beklentisi indirilenin atılması olabilir ama repo emsali (açılış diyaloğu İptal'i) plan
.part'larını korur; disk maliyeti bir paketlik, sonraki tur kaldığı yerden sürer. mosquitto ACL'
lerindeki kullanılmayan broadcast izinlerine (credential_manager) DOKUNULMADI — provizyon
regresyon riski > kazanım. `pausedOp` eklemesi eski Node-harness'i kırdı → o teste tek satır
bildirim eklendi (kayıt). [5.10] testi ilk koşuda İLK `InstallOutcome::Cancelled` oluşumuna
(closure içi) takıldı → `rindex` ile SON oluşum (dürüstlük notu).

### 15. parti — ÖLÜ KOMUT YÜZEYLERİ KALDIRILDI: SET_PARAMS / start_at / SYNC_ALL → [4.6] KAPANDI (sahip kararı 2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| yüzeyler | 5-ajanlı envanter (2026-08-20): depoda HİÇBİR üretici yok (servers/+pf/ grep boş; backend ESP'lere yalnız "start"/"stop" yayınlar; STM'de eşdeğer yok — ikili UART paketi + PB1 donanım darbesi AYRI ve CANLI). Üç yüzey silinmiş PyQt GUI kalıntısıydı ve [4.6]'nın latent kusurlarını taşıyordu. Kardeş broadcast konuları üstelik AYRIŞIKTI (S3 `pemf/coil/all/control` ↔ 8266 `pemf/control/all` — tek konudan ikisine ulaşmak zaten imkânsızdı) | 8266: .ino set_params+sync_all dalları ve start_at ayrıştırması; CoilController PWMStartState/checkSyncWait/isWaiting/setParams/_targetTimestampMs/_syncFallbackEvent; SharedDefs CMD_UPDATE_PARAMS+CMD_SYNC_ALL (8266'da "update" dalı hiç olmadı → ikisi de üreticisizdi); NetworkManager `_globalControlTopic` · S3: NetworkManager SET_PARAMS+SYNC_ALL dalları, START start_at bloğu, `_topicBroadcast`; CoilController process() bekleme bloğu, `_waitingForSync`/`_syncTargetTime`/fallback-event zinciri; SharedDefs CMD_SYNC_ALL (enum değerleri AÇIK, boşluk yeniden kullanılmaz) | `tests/test_olu_komut_yuzeyleri_kaldirildi.py` (5, yeni: yokluk kapıları + canlı-yüzey/aşırı-silme karşıt-kanıtları + STM PB1 koruması) · parite testi kaldırma-sonrası biçime güncellendi | 3 kırmızı → 66/66 firmware-komşu ✓ | 2/2 ✓ (8266 sync_all dirilt · S3 SET_PARAMS dirilt) |

**Bilinçli kararlar (15. parti):** S3 `UPDATE` dalı KALIR — sahip listesinde yok; bugün üreticisiz
ama [5.3]-korumalı gelecek param-güncelleme yüzeyi. `CMD_SYNC_TIME` girdileri KALIR (kapsam dışı).
`ControlCommand.timestamp` alanı struct uyumu için durur (hiçbir yol doldurmaz/okumaz — yorumlu).
`SystemStatusMsg.syncFallbackEvent` + `sync_fallback_event` JSON anahtarı tel-uyumu için durur
(hep false). mosquitto ACL broadcast izinleri: 14. parti notuyla aynı — dokunulmadı, kayıtlı.
[4.6] tetikleyicisiz kaldı → KAPANDI (kusurlu makine tümden silindi). ⚠️ REFLASH kapsamında (§14).

### 16. parti — Retained LWT + [5.12] + [5.11] (firmware kalanları, sahip onayı 2026-08-20)

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| LWT | `willRetain=true` hiçbir tüketiciye fayda sağlamıyordu: tek MQTT abonesi backend ve HER retained girdiyi eler/kapılar (5-ajanlı tarama: events→drop, status/sensors→gate, alarm→ignore, ack→id-kapılı); yerel broker `persistence false`; bulut broker'da abone YOK — retain yalnız bayat-offline riski üretiyordu (HiveMQ'da süresiz kalan offline + D-4'ün bilinen churn'ü) | 8266 `NetworkManager.cpp` (2 connect) + S3 `NetworkManager.cpp` (3 connect): `willRetain=false` — canlı LWT teslimi MQTT-3.3.1-9 gereği bayraktan BAĞIMSIZ, kopma tespiti değişmez | `tests/test_esp_lwt.py` güncellendi (+1 S3 kapısı; davranış testleri bayraktan bağımsız — değişmeden yeşil, düzeltmenin kanıtı) | 2 kırmızı → ✓ | 1/1 ✓ (bir connect'i true'ya döndür) |
| [5.12] | Tek-atımlık olaylar (termal-kesme, self-test, ACK) tüketilip 0-timeout `xQueueSend`le veriliyordu; kuyruk dolu penceresinde (mdns 2000 ms bloğu) olay SONSUZA DEK kayboluyordu — termal kesme operatöre hiç ulaşmayabilir, E-stop ACK kaybı sahte "onay gelmedi" alarmı; "overwrite deneriz" yorumu hiç gerçeklenmemişti | `esps3_pemf_coil.ino` (durum gönderimi düşerse `restore*` ile olaylar GERİ KURULUR — sonraki 200 ms turu yeniden dener; ACK `pdMS_TO_TICKS(50)` sınırlı bekleme — tüketici 10 ms'de bir boşaltır) · `CoilController.h/.cpp` (`restoreThermalStopEvent`/`restoreSelfTestEvent`) | `tests/test_s3_oneshot_kaybi.py` (4, yeni: 2 kapı + restore-yalnız-başarısızlıkta + boş-gövde-kandıramaz karşıt-kanıtları) | 4 kırmızı → 4/4 ✓ | 3/3 ✓ (restore-sil · ACK-0'a-döndür · boş-gövde) |
| [5.11] | Secrets.h yorumu "BLE provizyonla NVS'ten değişir" diyordu — YANLIŞ: kod koşulsuz FACTORY_COIL_ID, BLE coil_id yazamaz, PREF_KEY_COIL_ID ölü; iki kart aynı Secrets.h ile flash'lanırsa ikisi de bobin 6 olur (üretim tuzağı) | S3 `NetworkManager.cpp` (İZLENEN dosyada üretim-süreci uyarısı — otoriter kopya) + yerel `Secrets.h` yorumu düzeltildi | — (yorum düzeltmesi) | ✓ | — |

**Bilinçli kararlar (16. parti):** 8266 status/ack ve S3 ack `retain=true` yayınları DEĞİŞMEDİ —
kayıtlı bulgu yalnız LWT; tüketici retained status/ack'i zaten doğru ele alıyor (drop/id-kapısı),
ayrı karar istenirse ucuz. [5.11] Secrets.h düzeltmesi YEREL kopyada — dosya skip-worktree'li
(gerçek sırlar taşır); izlenen placeholder sürümüne dokunmak sır sızdırma riski taşırdığından
otoriter açıklama İZLENEN NetworkManager.cpp'ye kondu. `esps3/data/config.json` (ölü/yanıltıcı)
SİLİNMEDİ: skip-worktree'li gerçek-sır dosyası + `secrets_backup._SW_DOSYALAR` referansı —
silmek sır-yedeği aracını kırardı; kayıt burada. ⚠️ LWT+[5.12] REFLASH kapsamında (§14).

### 17. parti — Adversaryal inceleme kapanışları (5-mercekli iş akışı, 2026-08-20)

12-16. partilerin TAMAMI 5 paralel adversaryal merceğe (C el-derleme · güvenlik değişmezleri ·
launcher · pf · test-gaming) verildi. **Üretim kodu 4 mercekte TEMİZ** (a-i değişmezlerinin hepsi
doğrulandı; STM 0 değişiklik teyitli); test-gaming merceği **6 test boşluğu** buldu — 5'i
uygula-koştur-geri-al ile AMPİRİK kanıtlıydı. pf merceği 2 gerçek RISK verdi. Hepsi kapatıldı:

| # | Bulgu (incelemeden) | Düzeltme | Doğrulama |
|---|---|---|---|
| G-soyucu | `_c_soy` string literal içindeki `//`yi yorum sanıyordu — `String("s://")` hilesiyle CANLI bir SYNC_ALL dispatch'i kapılardan kaçırıldı (ampirik) | `tests/c_soyucu.py` (yeni, ORTAK): durum-makineli string-bilinçli soyucu; 5 test dosyası ona geçirildi | G6 mutasyonu (string-literal dirilişi) artık KIRMIZI ✓ |
| G1/G2 | Crash-loop kapıları token VARLIĞINA bakıyordu: `+`→`-` işaret-çevirme (süre UZAR — kusurun beteri) ve token-LOG-string'e-taşıma YEŞİL kalıyordu (ampirik) | `test_sureli_crashloop_ikizi.py`: iki kapı TAM İFADE regex'ine sertleştirildi | işaret-çevirme ✓ · string-taşıma ✓ KIRMIZI |
| G3 | [5.12] 500-karakter penceresi kontrol akışına kördü: restore'lar ölü dala taşınınca yeşil (ampirik) | küme-ayrıştırmalı `_basarisizlik_blogu` — restore'lar TAM başarısızlık bloğunda aranır; `restoreSelfTestEvent` sayımı eklendi | ölü-dal mutasyonu ✓ KIRMIZI |
| G4 | `test_esp_lwt` HAM metin arıyordu: LWT'li connect YORUMA alınıp will'siz connect yazılınca yeşil (ampirik; deponun kendi dersinin ihlali) | 8266+S3 iddiaları yorum-soyulmuş kaynağa taşındı; S3 sayacı connect'e çapalandı | yorum-satırı mutasyonu ✓ KIRMIZI |
| G5 | ACK kapısı makro ADI arıyordu: `pdMS_TO_TICKS(0)` = özgün 0-timeout kusuru birebir, yeşil (ampirik) | pozitif-tick regex'i (`[1-9][0-9]*`) | 0-tick mutasyonu ✓ KIRMIZI |
| G-prefetch | Onar/önbellek düzeltmesinin ÜÇ çağrı yerinden yalnız ikisi pinliydi — prefetch'teki `&koru`→`&[]` hiçbir testi kırmızıya düşürmüyordu | flow.rs `KRITIK_onar_celiskisi_on_indirme_yolunda_da_KORUR` (yeni) | `&[]` mutasyonu ✓ KIRMIZI; lib 207/207 |
| G-[5.10] | Kapı yalnız `plan_part_paths` alt-dizisini arıyordu (boş-manifest/aynı-adlı-değişken hileleri) | argüman `&manifest_raw_iptal` ile pinlendi | ✓ |
| RISK-1 (pf) | YENİ-ERİŞİLİR çift-yükleyici yarışı: kapı indirmesi uçuşta + ertele + banttan "Güncelle" → İKİ kanca örneği İKİ ACTION_VIEW niyeti açabiliyordu | `mobileUpdate.kurulumuBaslat`: aynı URI için UÇUŞTAKİ açılış sözü paylaşılır (tek yükleyici niyeti); çözülünce yeni çağrı yine açar ("Kurulumu tekrar aç" bozulmaz — karşıt-kanıt testli) | 1 kırmızı → 39/39 ✓; dedupe-kapat mutasyonu ✓ |
| RISK-2 (pf) | `kimligiKaydet:false` yalnız kimliği bastırıyordu; `provisionToken` ön-probda hâlâ koşuyordu (F3 deliğinin TOKEN kardeşi — registry LAN adresi döndürürse) | ön-prob TAMAMEN yan-etkisiz: token yazımı da bayrağın arkasında; merdiven-biçimli karşıt-kanıt çağrısı eklendi (`!requireDeviceId` mutasyonu artık yakalanır) | 1 kırmızı → 37/37 ✓; koşul-mutasyonu ✓ |
| NOT | api_server [3.2] yorumu S3'ü yanlış anlatıyordu ("35'te kırpar" — gerçek: ≥36'yı TÜMDEN REDDEDER, ACK hiç gitmez) | yorum düzeltildi (davranış değişikliği yok) | — |

**Kayda geçen inceleme notları (düzeltme İSTEMEYEN):** launcher RISK — keep-listesi genişlemesi
çok dolu eMMC'de eskiden önbelleği feda ederek geçen bir güncellemeyi açık "Yetersiz disk alanı"
hatasına çevirebilir (fail-safe, sahip-onaylı tradeoff; sessiz zarar yok). Önceden-var C notları:
S3 OTA-içi stopCmd memset'siz (cop command_id ACK'i olası — bu turun kapsamı dışı, kayıtlı);
NVS tek-bayt XOR checksum yüksek-bayt bozulmasını geçirir (meşru yazım yollarında erişilmez);
8266 `getStatus()` set_params kalkınca ölü kod (zararsız, bırakıldı). pf sınır notu: `paketHazir`
açılışlar-arası geçmez (önceki açılışta inen paket yeni açılışta "hiç başlamadı" sayılır — eski
'atla' semantiğiyle aynı, kusur değil). Model testleri üretim kodunu bağlamaz (bilinçli — tezgâh
§14 telafi eder); kapılar artık tam-ifade pinli olduğundan model+kapı ikilisi bütünleşik.

**Regresyon (son ölçüm, 17. parti sonrası):** backend TAM süit **1521 passed / 2 skipped / 0
failed** (16. partide de 1521 — 17. parti test SERTLEŞTİRMESİ sayı eklemeden mevcutları
güçlendirdi; 11. parti 1497, 10. parti 1491, 9. parti 1487, 8. parti 1483, 7. parti 1477,
6. parti 1474, 5. parti 1468, 4. parti 1459, 3. parti 1450, 2. parti 1446, 1. parti 1439) ·
launcher WORKSPACE **267/267** (lib 207; 16. partide 266, 11. partide 249) · pf TAM süit
**54 süit / 525 test / 0 failed** + `tsc --noEmit` temiz (16. partide 521, 13. partide +11).
Ara ölçümler: hedefli 77+62+91+20+81+12+31+21+8+32+23+40+49+34+55+51+46+19+63+66+30+64 ✓.
17. parti oyunlama-mutasyonları: **G1-G6 + G-prefetch + dedupe-kapat + merdiven-koşulu = 9/9
artık KIRMIZI** (öncesinde 6'sı yeşil kalıyordu — ampirik).

⚠️ **REFLASH DURUMU (2026-08-20):** §9-13 tezgâhı sahip tarafından koşuldu — SORUNSUZ (sahip
beyanı). AYNI GÜN 12/15/16. partiler firmware'e yeniden dokundu → **S3+8266 için İKİNCİ REFLASH
gerekir** (STM değişmedi) — tezgâh adımları VERIFICATION §14.

⚠️ **Firmware bulguları için bağlam:** üç firmware kaynağı depoya 2026-08-18'de girdi ve
S3+8266+STM **REFLASH bekliyor** (donanım-uyum kararı). Aşağıdaki firmware↔backend sözleşme
bulguları, tam o zorunlu reflash yapıldığı anda sahaya gidecek kusurlardır — reflash öncesi
düzeltilmeleri en ucuz andır.

---

## CİDDİYET 1 — hasta güvenliği

### [1.1] Durdurma turu `mqtt_unavailable`'ı başarı sayıyor — broker ölüyken "Durdurma onaylanamadı" uyarısı HİÇ çıkmıyor — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI)
**Yer:** `pf/src/screens/ControlScreen.tsx:317` (`r.status !== "error"`) ↔ `servers/api_server.py:1800`
(ESP tek-bobin STOP: HTTP 200 + `{status:"mqtt_unavailable"}`) ve `:1898` (batch: KOŞULSUZ üst-seviye
`success`, satır-başı sonuçlar `results[]` içinde — pf hiç okumuyor).
**Tetikleyici:** Mosquitto ölü/yetim (bilinen arıza sınıfı) iken operatör "⏹ Durdur"a basar.
**Sonuç:** STOP hiçbir bobine ulaşmamışken tur sessizce "başarılı" biter; tam bu durum için yazılmış
*"bobinler HÂLÂ ÇALIŞIYOR olabilir, ACİL DURDUR'a basın"* uyarısı çıkmaz. Aynı predikat kusuru
`CoilParameterPanel.tsx:107`'de: aşırı-ısınma interlock'u komut broker'a ulaşmamışken "bobin otomatik
durduruldu" der. Ayrıca `/api/session/stop` (api_server.py:2984) publish'ler tamamen düşse bile koşulsuz
`success` döner → `useSessionControl.ts:243` alerti de ölü.
**Nasıl doğrulandı:** Predikat node ile ölçüldü (iki başarısızlık yanıtı da `allOk=true`); backend yanıt
şekilleri satır satır okundu; `durdurmaTuruParalel.test.tsx` yalnız `success`/null mock'luyor —
`mqtt_unavailable` hiçbir teste girmemiş. (E-stop yolu aynı statüyü DOĞRU şekilde arıza sayıyor —
tutarsızlık kasıt olmadığının kanıtı.)

### [1.2] KÜME: Yeni firmware'lerin MQTT status sözleşmesi backend'le uyuşmuyor — bayat-telemetri STOP güvenlik ağı S3'te ölü, panel kontrolleri kilitleniyor, doz kaydına duty=0 yazılıyor — ✅ DÜZELTİLDİ (2026-08-20, backend tarafında; firmware'e dokunulmadı — bkz. DÜZELTME KAYDI)
**Yer:** `servers/api_server.py:584-590` ↔ `firmware/esps3_pemf_coil/NetworkManager.cpp:604-672` ↔
`firmware/esp8266_pemf_coil/NetworkManager.cpp:210-235` ↔ `firmware/esps3_pemf_coil/esps3_pemf_coil.ino:83`.
Üç kopukluk: (a) backend `payload["status"]` dizesinden `connected` türetiyor — **hiçbir firmware status
JSON'ında `status` alanı yok** → her canlı status mesajı `connected=False` yazar (S3 5 Hz'de);
(b) backend duty'yi yalnız `duty_cycle` anahtarından okuyor — S3 `pwm_duty`, 8266 `pwm_duty_cycle`
yayınlıyor → ESP duty'si live-state'e HİÇ ulaşmıyor; (c) S3 `sensors` yayınını tümden kaldırmış
("UYUMSUZ-6") — backend'de `connected=True` yazan tek periyodik dal `sensors`; S3'ün `wifi_connected`
event'i de normal açılışta yayınlanAMAZ (`NetworkManager.cpp:233-236` MQTT'den önce WiFi bağlanır;
backend `mqtt_connected` event'ini işlemez).
**Sonuç (reflash sonrası):** (i) `_esp_telemetry_watchdog` (api_server.py:495) yalnız `connected=True`
bobini bayat-STOP'lar → S3 (bobin 6-7) için bu güvenlik ağı **hiç çalışmaz**, 8266 için son mesajın
sensors/status olmasına göre yazı-tura — 1.9.16'nın "sessizleşen ESP'ye gerçek STOP" düzeltmesi
işlevsizleşir (cid 1); (ii) S3 panelleri kalıcı "Offline" — `CoilParameterPanel.tsx:146` BAŞLAT/DURDUR
dahil tüm kontrolleri kilitler (cid 3); (iii) dakika-akümülatörü duty'yi live-state'ten aldığı için
(api_server.py:2715/2737 → 2606 `pwm_duty_percent`) ESP doz satırları **duty=0**, S3'te current/ambient
da 0 — D-2'nin "dürüst efektif duty" düzeltmesi backend'e hiç ulaşmıyor (cid 4).
**Nasıl doğrulandı:** Üç anahtar üç dosyada birebir okundu; `tests/test_esp_ack_roundtrip.py:113`
backend'in beklediği ama firmware'in ÜRETMEDİĞİ `{"status":"online"}` biçimini enjekte ediyor
(yanlış-yeşil); PEMF_SIMULATE yolu `_live_state`'i doğrudan yazıp MQTT ayrıştırmasını hiç sınamıyor
(api_server.py:2503-2570) → hiçbir test bu sözleşmeyi tutmuyor. Bağımsız çürütme ajanı da aynı sonuca ulaştı.

### [1.3] S3 NVS resume, kümülatif süresiz-tavan sayacını RAM'e geri yüklemeden ÖNCE NVS'e ≈0 yazıyor — <30 sn periyotlu crash-loop 7200 sn tavanı yine deliyor — ✅ DÜZELTİLDİ (2026-08-20, iki firmware; ⚠️ S3+8266 REFLASH + tezgâh doğrulaması gerekir — bkz. DÜZELTME KAYDI 3. parti + VERIFICATION §11)
**Yer:** `firmware/esps3_pemf_coil/CoilController.cpp:581` (`loadState` → `_beginOutput`) →
`:413` (`_suresizGecenMs = 0`) + `:416` (`forceSaveState()` → NVS `elapsedMs≈0`) → `:585`
(birikim yalnız RAM'e geri konur; sonraki NVS kaydı +30 sn).
**Tetikleyici:** duration=0 (süresiz) seans + cihaz resume'dan sonraki 30 sn içinde tekrar çöker.
**Sonuç:** Birikmiş süre NVS'te silinir → <30 sn periyotlu çök-diril döngüsünde kümülatif tavan HİÇ
dolmaz — `b7b842c`'nin kapattığını iddia ettiği deliğin ta kendisi (kalan sınır: yerel termal 48/45).
**8266 kardeşi ETKİLENMEZ:** `restorePWMState` (:502-564) EEPROM'a yazmaz. Desen-1'in tam örneği.
**Nasıl doğrulandı:** İki dosya yan yana satır satır okundu; `tests/test_plan_a_deadman.py` yapısal
metin kapısı + Python modeli bu kayıt SIRASINI modellemiyor (model `save()`'i hep doğru değeri yazar) —
korumasız.

---

## CİDDİYET 2 — veri kaybı / sır

### [2.1] APK kurulum kapısı yalnız `/session/active`'e bakıyor — SEANSSIZ çalışan bobinlerde yükleyici yine ekranı alıyor — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI 4. parti)
**Yer:** `pf/src/hooks/useApkGuncelleme.ts:43-53` ↔ `servers/session_router.py:32-53` (uç yalnız
`_active_session` döndürür; bobin durumu yok). `/api/coil/{id}/control` ve `/batch` `is_active`'i
hiç değiştirmez.
**Tetikleyici:** Operatör seans açmadan CoilParameterPanel'den bobin başlatır, sonra güncelleme
bandında "Güncelle"ye dokunur; indirme bitince kapı `is_active:false` görür.
**Sonuç:** Bobinler hayvanın üzerinde enerjiliyken Android paket yükleyicisi kontrol ekranının üstüne
açılır; onaylanırsa telefon kumandası tedavi ortasında kaybolur — 1. turun 1 numaralı düzeltmesinin
"seanssız bobin" varyantı. Kod tabanı bu durumu ayrı gerçek durum olarak zaten tanıyor
(`ControlScreen` `hardwareRunningOutOfSession` banner'ı).
**Nasıl doğrulandı:** Kapının okuduğu uç ve `is_active`'i yazan tüm yerler grep'le dökümlendi;
çürütme ajanı telafi mekanizması bulamadı. (Aynı kör nokta `RecoveryCodeBanner.tsx:57`'de de var —
yalnız görünürlük, düşük önem.)

### [2.2] `secrets_backup.py restore` sonrası `git add -A` gerçek sırları PUBLIC repoya taşıyabiliyor — ve gitleaks bu sır sınıfını GÖRMÜYOR — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI 4. parti)
**Yer:** `build_tools/secrets_backup.py:95-127` — restore git'e hiç dokunmuyor; skip-worktree'yi
yalnız **PowerShell'de çalışmayan bash-tarzı** (` \` devamlı) bir komut olarak basıyor. Dört sır
dosyası (iki `Secrets.h` + iki `data/config.json`) git'te placeholder olarak İZLENİYOR; `--force`lu
restore'dan sonra adım atlanırsa `git add -A` gerçek ESP WiFi/MQTT sırlarını stage'ler.
**Ağırlaştırıcı (ölçüldü):** deponun tek sır kapısı gitleaks, gerçek Secrets.h içeriğinde SIFIR bulgu
veriyor (düşük-entropili WiFi/MQTT parolaları kural setine takılmıyor) — `Secrets.h` başındaki
"gitleaks kancası zaten durdurur" yorumu dayanaksız.
**Tetikleyici:** Yeni build makinesi kurulumu (aracın tam amacı olan senaryo) + ekran çıktısındaki
adımın atlanması. Repo PUBLIC (2026-08-04 denetimi, açık P0).
**Nasıl doğrulandı:** Çürütme ajanı `git ls-files -v` + `git show HEAD` + gitleaks koşusuyla ölçtü.

---

## CİDDİYET 3 — cihaz kullanılamaz / güvenlik ağı güvenilmez

### [3.1] Takas-sonrası geri-alma hatası yutuluyor — doğrulanmamış sürüm "iptal edildi" mesajıyla canlıda kalıyor — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI 7. parti)
**Yer:** `launcher/core/src/flow.rs:1067-1071` — `let _ = guncellemeyi_geri_al(...)`; geri alma
(`:682-723`) `fs::rename` hatası dönebilir ama atılıyor; çağıran (`main.rs:805-813`) yalnız profil
hatasını/iptali görür.
**Tetikleyici:** 1. turun G1 düzeltmesinin dar kalan dalı: takas yapıldı + profil adımı iptal/IO
hatası + geri-alma rename'i AV/kilitli-dosya yüzünden düştü.
**Sonuç:** Sağlık kapısı koşmamış yeni sürüm canlı ağaçta kalır; `runtime.old` sonraki turda tüketilir
(son-bilinen-çalışan yok olur); UI "iptal edildi" der. Alt-dal: `rt→runtime.bozuk` başarılı olup
`eski→rt` düşerse kurulum o oturum boyunca runtime'sız kalır (sonraki açılışta `yarim_takasi_kurtar`
toparlayabilir).
**Nasıl doğrulandı:** Statik okuma + çürütme ajanının çapraz doğrulaması (fonksiyonun sağlık-kapısı
dalında aynı çağrının sonucu OKUNUYOR — bu dalda okunmaması kasıt değil, atlama).

### [3.2] E-stop ack takibinde `command_id` çakışması — acil durdurma anında SAHTE "ESP onayı gelmedi" kırmızı alarmı — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI 5. parti)
**Yer:** `servers/api_server.py:3494` (`estop_{coil}_{ms}` — ms çözünürlüklü) + `:1237-1262`
(`_register_ack` koşulsuz üzerine yazar; `_wait_ack` pop'lar).
**Tetikleyici:** Aynı bobine aynı milisaniyede iki E-stop tetiği (manuel + ESP alarmı — alarm dalında
debounce yok, `:686` her alarmda ayrı `_emergency_stop_all`).
**Sonuç:** Bobin durmuş ve ack gelmişken ikinci bekçi "bobini elle kontrol edin" HATA bildirimi basar
(alarm yorgunluğu — kod tabanının kendisinin iki yerde önemsediği şey). Ek: `_estop_ack_watch:1286-1293`
ESP'nin açık `success=false` NACK'inde de yanlış "(2s) ONAYI GELMEDİ" metni basıyor.
**Nasıl doğrulandı:** Çürütme ajanı embedded python ile birebir repro etti (`estop_7_...` aynı id ×2;
iki advers interleaving'de sahte timeout ölçüldü). Yön fail-safe (STOP'lar gidiyor) — sonuç yalnız sahte alarm.

### [3.3] E-stop bulut aynası süreç-sabit `client_id` kullanıyor — çifte tetikte iki ayna oturumu HiveMQ'da birbirini düşürüyor — ✅ DÜZELTİLDİ (2026-08-22, bkz. DÜZELTME KAYDI 18. parti)
**Yer:** `servers/api_server.py:1435` — `_mqtt_client_id("estop-cloud")` yalnız `pub` rolünü
çağrı-benzersiz yapar (ölçüldü: iki çağrı aynı `pemf_estop-cloud_{pid}`); MQTT sözleşmesi gereği
ikinci bağlantı ilkini düşürür — deponun KENDİ E-stop kimlik değişmezinin (api_server.py:696-711,
"E-stop STOP kaybı") bulut ayağında ihlali.
**Tetikleyici:** 8 sn'lik ayna bütçesi içinde iki `_emergency_stop_all` (manuel + alarm).
**Sonuç:** İlk aynanın uçuştaki QoS-1 STOP'ları bağlantı düşünce kaybolabilir → bulut aynası tam
"çifte tetikli gerçek acil durum" anında güvenilmez. Yan not: `pemf_estop-cloud_` öneki 7+ haneli
PID'de 23-karakter broker sınırını aşar; `test_ids_are_broker_safe` yalnız ws/pub rollerini deniyor.
**Nasıl doğrulandı:** Çürütme ajanı `_mqtt_client_id` çıktısını ölçtü + kod okuma.

### [3.4] Yayın runbook'u hâlâ tüm paketleri `client-app-v1.8.0`a yükletiyor — harfiyen izlenirse bir sonraki yayında saha geneli 404 — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI 5. parti)
**Yer:** `BUILD.md:348-352` (0e2b1ed'den beri güncellenmemiş) + `pemf-app-packages/README.md:14`
(daha da eski ikinci kopya). `make_manifest.py` 1.9.16'dan beri URL'leri `--tag`ten (sürüm-başına
etiket) kurar; `base.zip` yükleme listesinde hiç yok.
**Tetikleyici:** Bir sonraki app yayınında (1.9.18) yayıncının BUILD.md §6'yı aynen uygulaması.
**Sonuç:** `layers.app` URL'si `client-app-v1.9.18/base-app.zip`i gösterir, dosya v1.8.0'a yüklenmiştir
→ her saha güncellemesi ve her taze kurulum 404 (`net.rs` 404'ü deterministik sayar, tekrar denemez).
Son yayınlarda kaza olmaması betiğe değil yayıncının ezberine bağlı.
**Nasıl doğrulandı:** Çürütme ajanı `git -S` arkeolojisi + make_manifest URL kurulumu + canlı manifest
URL'leriyle doğruladı; make_manifest'te uzak-varlık kontrolü olmadığı teyit edildi.

### [3.5] `restore_assets.ps1` "klon = çalışan sistem" vaadini tutmuyor — cat_organ çekirdek modeli hiçbir profil zip'inde yok, temiz makinede paketleme kapıda düşüyor — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI 7. parti)
**Yer:** `scripts/restore_assets.ps1:53-76` yalnız home/vet/research indirir; `inference_cat_organ`ın
3 ONNX'i (~200 MB) 2026-08-10'da home.zip'ten çıkarılıp YALNIZ `base-deps.zip`e taşındı — betik
base-deps'i hiç indirmiyor.
**Tetikleyici:** Boş makinede TEMIZ-MAKINE.md Yol B: clone → bootstrap → restore_assets ("Geri
yüklendi" der) → build → `make_base_zip`.
**Sonuç:** ~1 saatlik akışın SON kapısında `cekirdek model (cat_organ) VAR` kontrolü exit 1 —
temiz makinede yayın paketi üretilemez; kapı elle atlanırsa AI Pro organ-lokalizasyonsuz backend çıkar.
**Nasıl doğrulandı:** Çürütme ajanı üç zip'in merkezi dizinini HTTP Range ile uzaktan listeledi —
37 girdinin hiçbirinde cat_organ yok (betiğin kendi "40 indirir" yorumu da yanlış).

---

## CİDDİYET 4 — yanlış klinik çıktı / kayıt

### [4.1] Gözlem notu sıfırlama anahtarı yalnız hasta ADI — aynı isimli iki hastada A'nın notu B'nin tıbbi kaydına yazılabiliyor — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI 8. parti)
**Yer:** `pf/src/components/domain/ObservationNotesModal.tsx:64-67` — 1. turun düzeltmesi `visible`'ı
dep'ten çıkarınca tek dep `session?.patientName` (string) kaldı; `ControlScreen.tsx:97` ObsSess'e hasta
ID'si koymuyor; `session_router.py:79+` notu aktif `db_session_id` satırına yazar.
**Tetikleyici:** A'nın seansı biter, not yazılır ama kaydedilmez (modal gizlenir); AYNI İSİMLİ B için
seans başlar-biter → modal B için A'nın notu+chip'leriyle açılır ("Boncuk"/"Paşa" klinikte gerçekçi).
**Sonuç:** Fark edilmezse A'nın gözlemi B'nin kaydına gider — düzeltme öncesinde her açılış sıfırlıyordu;
delik YENİ. Doğru anahtar hasta/seans kimliğidir, isim değil.
**Nasıl doğrulandı:** Çürütme ajanı React dep semantiği + veri akışını uçtan uca izledi;
`gozlemNotuKorunmasi.test.tsx` yalnız aynı-hasta yolunu kilitliyor.

### [4.2] ESP'nin yerel TERMAL KESME olayı backend'de hiç işlenmiyor — operatör bobinin neden durduğunu göremiyor — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI 6. parti)
**Yer:** `servers/api_server.py:621-662` events dalı yalnız `selftest_*`/`wifi_*` tanır;
`thermal_stop` event'i (S3 `.ino:80-82` yayınlar) ve status'taki `thermal_lock` alanı okunmuyor.
**Tetikleyici:** Reflash sonrası bir ESP bobini 48°C'de kendini keser ve `thermal_stop` yayınlar.
**Sonuç:** Cihazın EN ÖNEMLİ yerel güvenlik eylemi backend'e/operatöre görünmez — bobin "sebepsiz
durdu" sanılır, termal kilit sürerken start redleri (`CMD_START` termal kilitte `false`) açıklamasız
kalır. HG-1/HG-2 bağlamında termal olayların görünürlüğü klinik olarak önemli.
**Nasıl doğrulandı:** events dalı + iki firmware'in yayın noktaları okundu (çürütme ajanının yan bulgusu;
ben de doğruladım).

### [4.3] HG-3 DC-yapışma latch'i PWM PASİFKEN de birikiyor — deterministik dizide faz senkronu sessizce kalıcı kapanıyor — ✅ DÜZELTİLDİ (2026-08-20, S3 firmware; ⚠️ S3 REFLASH + tezgâh — bkz. DÜZELTME KAYDI 9. parti + VERIFICATION §12)
**Yer:** `firmware/esps3_pemf_coil/CoilController.cpp:83-117` — `syncPulseISR` `s_active`'e bakmaz;
`ddsTimerISR` pasifken `s_natural_wrap` üretmez → boşta gelen her PB1 darbesi "erken kilit" sayılır,
8 darbede `s_sync_disabled=true`; `:442-451` latch yalnız FREKANS DEĞİŞİMİNDE temizlenir.
**Tetikleyici:** S3, STM bobin-1 çalışırken açılır/yeniden başlar; sonra öncekiyle AYNI frekansta seans
başlar (AI Pro hep 1.0 Hz — aynı açılıştaki 2. AI Pro seansı bu koşulu deterministik sağlar).
**Sonuç:** Bobin 6-7 faz senkronu olmadan (tek faz) çalışır → çok-bobinli faz deseni sessizce bozulur;
`sync_disabled` status'ta raporlanıyor ama backend bu alanı da işlemiyor. Yön fail-safe (DC yok) —
kusur "sessiz derece kaybı".
**Nasıl doğrulandı:** Çürütme ajanı ISR akışını simülasyonla doğruladı; PB1 kapısının yalnız bobin-1
sürülürken darbelediği STM main.c'den teyitli.

### [4.4] D-3 frekans clamp'i seans yolunu KAPSAMIYOR (kısmi düzeltme) — doğrudan API'de karma-dizi doz tutarsızlığı sürüyor — ✅ DÜZELTİLDİ (2026-08-20, bkz. DÜZELTME KAYDI 6. parti)
**Yer:** `servers/api_server.py:2144-2152` — `/api/session/start` ESP yayını `"freq": payload.frequency`
HAM; `SessionStartPayload.frequency` (:1021) kısıtsız. Clamp yalnız `/coil/{id}/control` (:1759) ve
`/coil/batch` (:1860). Donanım-uyum raporu D-3'ü "✅ düzeltildi" işaretliyor.
**Tetikleyici:** Doğrudan API ile coil_ids 6-8 içeren, frequency>1000 seans (sevk edilen UI 100'e kırpar).
**Sonuç:** STM bobinleri istenen frekansta, ESP bobinleri sessizce 1000 Hz'de → D-3'ün tarif ettiği
tutarsız doz, üçüncü yoldan geri geliyor. Yan bulgu: `tests/test_esp_freq_clamp.py:59` kapısı yalnız
kaynakta substring arıyor — bu boşluğu yapısal olarak göremez.
**Nasıl doğrulandı:** Ben + çürütme ajanı bağımsız bulduk; `git show ffd4406~1` ile fix-öncesi üç ham
siteden yalnız ikisinin düzeltildiği arkeolojiyle teyit.

### [4.5] Doz/tedavi geçmişine HİÇ KOŞMAMIŞ bobin koşuları yazılıyor — duty>99'da diziler ayrışıyor, NACK görünmüyor — ✅ DÜZELTİLDİ (teslim/kabul: 8. parti 2026-08-20; NACK-görünürlüğü + ack-bekçisi: 18. parti 2026-08-22)
**Yer:** `servers/api_server.py:1796-1797` — `_begin_coil_run` MQTT publish sonucundan ve ESP ack'inden
BAĞIMSIZ koşu kaydı açar; `:1744-1803` duty ham gider; 8266 `d>99` → NACK + start yok
(`esp8266_pemf_coil.ino:515`), S3 50'ye kırpıp çalışır; `command_error` event'i backend'de işlenmiyor,
manuel yol ack beklemiyor.
**Tetikleyici:** Doğrudan API ile duty=100 start (UI 50'ye kırpar) — ya da publish'in düştüğü her manuel start.
**Sonuç:** Bobin 8 hiç başlamamışken tedavi geçmişine koşu yazılır; 6-7 farklı dozda çalışır; operatör
redden habersiz. Doz kaydının güvenilirliği (4. tur "doz kaydı" kararının ruhu) zedeleniyor.
**Nasıl doğrulandı:** Kod okuma iki tarafta; çürütme ajanı reddin hiçbir kanaldan görünmediğini teyit etti.

### [4.6] 8266: zamanlanmış başlangıç ve resume yollarında kümülatif-tavan defekleri (bugün latent) — ✅ KAPANDI (15. parti: kusurlu makine yüzeyle birlikte KALDIRILDI — sahip kararı 2026-08-20)
**Yer:** `firmware/esp8266_pemf_coil/CoilController.cpp:428-454` — `checkSyncWait` başlatma dalları
`_suresizGecenMs`'i SIFIRLAMAZ (S3 `_beginOutput` her zaman sıfırlar) → start_at'li taze süresiz seans
eski birikimi devralır, tavan ERKEN tetiklenir (fail-safe yön ama beklenmedik erken durma).
Ters yönde: `:194-201` `CMD_SYNC_ALL` aktif seansta `stop()+start(timestamp=0)` yapar → immediate yol
sayacı SIFIRLAR (tavan uzatılabilir) ve resume sonrası `_pwmDurationSec=0` kaldığı için SÜRELİ seansı
SÜRESİZE çevirir.
**Tetikleyici:** Bugün backend ne `start_at` ne `SYNC_ALL` gönderiyor (grep boş) — latent; eski
GUI/gelecek tüketici yolları.
**Nasıl doğrulandı:** Çürütme ajanı satır satır izledi; tüm sıfırlama noktaları dökümlendi.

---

## CİDDİYET 5 — diğer işlevsel

- **[5.1]** ✅ DÜZELTİLDİ (11. parti) — `pwm_remaining_time` iki kardeşte FARKLI BİRİM: 8266 milisaniye (`CoilController.cpp:337`),
  S3 saniye (`:485`) — bugün tüketici yok; alanı okuyacak ilk tüketici bobin 8 için 1000× yanlış değer
  görür. Aynı payload'da duty anahtarı da farklı (`pwm_duty_cycle` / `pwm_duty`) — bkz. [1.2].
- **[5.2]** ✅ DÜZELTİLDİ (11. parti; `_pwmStartTimestamp` bilinçli dışarıda — parti notu) — 8266 `restorePWMState`
  `_pwmDurationSec`/`_pwmStartTimestamp` geri yüklemiyor
  (`CoilController.cpp:545`) → resume sonrası SÜRELİ seans status'ta `pwm_duration=0` (=süresiz nöbetçisi)
  raporlanır; `pwm_remaining_time` doğru — çelişkili rapor. S3 doğru yapıyor (`:571-578`).
- **[5.3]** ✅ DÜZELTİLDİ (11. parti) — S3 `CMD_UPDATE_PARAMS` fazı KOŞULSUZ uyguluyor (`CoilController.cpp:361`) — `phase` anahtarı
  olmayan set_params fazı sessizce 0'a döndürür (freq/duty ">0 ise" korumalı, faz değil). Bugün backend
  set_params göndermiyor — latent.
- **[5.4]** ✅ DÜZELTİLDİ (10. parti) — Sahadaki `PEMF_Backend.exe` dosya-özellikleri sürümü **1.9.14.0'da donmuş** (ölçüldü):
  `PEMF_Backend_onedir.spec:408` `docs/version_info.txt`'i gömüyor, onu yalnız KAPALI Inno kanalının
  `build_installer.ps1`'i yeniliyor; güncel yayın yolu hiç dokunmuyor. `versions.json._kanallar`ın
  "backend hedefi: version_info.txt" iddiası yerine gelmiyor; destek/envanter yanlış sürüm görür.
- **[5.5]** ✅ DÜZELTİLDİ (10. parti) — CHANGELOG "Paket kimliği (buildId)" satırları YANLIŞ değeri etiketliyor: katmanlı sahada
  cihazlar `layers.app` sha'sını raporlar (`install.rs:571-575` → 1.9.17'de `7a0de0cdcf38`), CHANGELOG
  `base.zip` sha'sını (`5cdb86380a55`) "buildId" ilan ediyor — 1.9.16'da da aynı (sistematik). Destek
  eşleştirmesi yanılır; CI kapısı yalnız base sha'yı kilitlediği için görmez.
- **[5.6]** ✅ DÜZELTİLDİ (14. parti) — Launcher: **Duraklat → İptal ölü** (`index.html:1662` + `main.rs:1174-1176`): komut
  "paused" ile çoktan dönmüş, `CTL_CANCEL`'ı okuyan kalmamış — İptal grileşir, ekran süresiz
  "Duraklatıldı"da kalır (Node koşumuyla ölçüldü); tek çıkış Devam Et ya da pencereyi kapatmak.
- **[5.7]** ✅ DÜZELTİLDİ (13. parti; (b) zararsızlaştı — parti notu) — Mobil güncelleme erteleme kümesi: (a) indirme sürerken "Şimdilik devam et" denirse uçuştaki
  `guncelle()` ertelemeyi okumaz — indirme bitince yükleyici o anki işin üstüne sormadan açılır
  (`useApkGuncelleme.ts:99`; seans kapısı yine de çalışır); (b) ertelemeden sonra kancanın ürettiği tüm
  mesajlar (izin_gerekli dahil) hiçbir yerde gösterilmez; (c) `MobileUpdateGate.tsx:120` `oran===null`
  yordamı tam inmiş paketten sonra bandı da susturur (soğuk açılışta kapı yeniden sorar — zarar sınırlı).
- **[5.8]** ✅ DÜZELTİLDİ (13. parti) — `_esp_telemetry_watchdog` bildirimi publish SONUCUNU okumuyor (`api_server.py:506-523`):
  broker çökükken "bağlantı kesildi sayıldı, STOP GÖNDERİLDİ" der — STOP gitmemiştir; yorumdaki
  "log'a düşülür" vaadi de gerçekleşmiyor (probe False döner, istisna atmaz).
- **[5.9]** ✅ DÜZELTİLDİ (13. parti) — `checkHealth`'in yan etkisi 1. turun F3 değişmezini `device_id` için deliyor:
  `pairing.cihazaBaglan` token takasından ÖNCE `checkHealth` çağırır (`pairing.ts:93`), o da geçen her
  cihazın kimliğini DİSKE yazar (`discovery.ts:100`) → takas düşse de kayıtlı kimlik B olur. Adres
  yazılmadığı ve merdivenin LAN basamağı kimlik istemediği için çoğu yolda kendini onarır; yalnız
  uzak-çözümleme basamağında (4.) yanlış cihazın tüneline kalıcı geçiş mümkün. Birim testleri
  checkHealth'i mock'ladığı için görünmez.
- **[5.10]** ✅ DÜZELTİLDİ (14. parti) — Kurulum İptal'i (`main.rs:522` `clear_partials(&root,&[])`) eşzamanlı kilitsiz arka plan
  ön-indirmesinin YABANCI `.part`ını da siliyor (yorumdaki "o sorun discard_pending yolundaydı"
  gerekçesi eşzamanlılıkta yanlış) — sınırlı: bir paketlik ilerleme kaybı, kendini onarır.
- **[5.11]** ✅ KISMEN DÜZELTİLDİ (16. parti: yorumlar; config.json bilinçli bırakıldı — parti notu) — S3 `Secrets.h:18` yorumu "coil id BLE provizyonla NVS'ten değişir" diyor — kod koşulsuz
  `FACTORY_COIL_ID`ye zorluyor (`NetworkManager.cpp:159`), `PREF_KEY_COIL_ID` ölü tanım, BLE coil_id
  yazamıyor → bobin 7 cihazı YALNIZ flash öncesi Secrets.h düzenlenerek üretilebilir; iki kart aynı
  Secrets.h ile flash'lanırsa ikisi de bobin 6 olur. Ayrıca `esps3/data/config.json` (`coil_id:1`)
  hiçbir kod tarafından okunmuyor — ölü/yanıltıcı dosya. Üretim-süreci tuzağı.
- **[5.12]** ✅ DÜZELTİLDİ (16. parti) — S3 tek-atımlık olay bayrakları (`thermalStopEvent`/selftest/ACK) `xQueueSend` başarısı
  doğrulanmadan tüketiliyor (`esps3_pemf_coil.ino:223` bölgesi) — kuyruk dolu penceresi çok dar
  (mDNS 2000 ms bloğu, 5 dk'da bir); pratik kayıp olasılığı düşük, E-stop ACK kaybı yalnız sahte
  "onay gelmedi" alarmı üretir (fail-safe).

---

## ŞÜPHELİ — DOĞRULANAMADI

- **Bulut aynasının uçtan uca teslimi:** `_estop_cloud_mirror` HiveMQ'ya yayınlıyor; ESP'lerin bulut
  broker'ında da `pemf/coil/{id}/control`e abone olduğu kodda görünüyor ama STOP'un buluta göçmüş
  gerçek bir ESP'ye teslimi hiçbir yerde ölçülmedi (tezgâh + gerçek HiveMQ hesabı gerekir —
  donanım-uyum raporu §4/4 zaten tezgâh maddesi).
- **8266 EEPROM yarım-yazımı:** `EEPROM.commit()` sırasında elektrik kesilirse magic+tek-baytlık XOR
  checksum'ın bozuk kaydı her zaman yakalayıp yakalamadığı ölçülmedi (checksum yalnız düşük baytları
  XOR'luyor — 256'nın katı bozulmalar geçer). Cihazda ölçüm gerekir.
- **`ApkInstallerModule` arka plan davranışı:** kod izinden (manifest'te BAL muafiyeti yok, koşulsuz
  `true` dönüş) doğrulandı ama gerçek cihazda ölçülmedi; kurtarma ucuz ("Kurulumu tekrar aç").

## KASITLI GÖRÜNÜYOR — TEYİT İSTER

- ✅ ÇÖZÜLDÜ (14. parti — sahip kararı: kurulu-güncel paketler koruma listesine alındı; eMMC disk-kazanımı duruyor) — **Önbellek temizliği geçerli paketleri de siliyor** (`flow.rs:262` + `disk.rs`): 1.9.29'da eMMC
  disk-dolma çözümü olarak ÖZELLİK ilan edildi (önceki denetim de bu gerekçeyle çürütmüştü). Ama
  ölçüldü: `ProfileRecordUnreadable` hata metni ve UI "indirilenler önbellekten gelir, yeniden İNMEZ"
  vaadi bu davranışla çelişiyor; eMMC klinikte "Onar" 20+ dk indirmeye dönüyor ve BAŞARISIZ güncelleme
  turu bile önbelleği silmiş oluyor. Sahip karar vermeli: vaadi düzelt ya da kurulu-güncel paketleri
  koruma listesine al.
- **`cloud_mqtt_provision` build'de Warn-only** (`build_backend_exe.ps1:177-181`, sahip kararı yorumu
  var; `make_base_zip` kontrol listesinde de yok — ölçüldü: dosyasız DIST "VALIDATION: PASS"):
  temiz-klon makinesinden çıkan paket sırsız çıkar, ayna sessiz devre dışı. Ayrıca üretim BAŞARISIZ
  olduğunda bayat provision dosyası silinmiyor → sır rotasyonunda eski kimlik gömülü kalır.
- ✅ ÇÖZÜLDÜ (16. parti — sahip onayı: willRetain=false) — **Retained LWT + backend'in retained-events filtresi**: `willRetain=true` artık hiçbir tüketiciye
  fayda sağlamıyor (tek abone filtreli backend; broker `persistence false`) — yalnız bayat-retained
  riski üretiyor. `willRetain=false` aynı davranışı verir; tasarım sadeleştirmesi sahibin kararı.
- **Arka plan ön-indirmesi hiçbir yoldan duraklatılamıyor/iptal edilemiyor** (`main.rs:749`
  `|| Control::Continue` — bilerek): metered/kotalı bağlantıda kullanıcının tek freni uygulamayı
  kapatmak. Bilinçli görünüyor, kayda geçirildi.
- ✅ ÇÖZÜLDÜ (15. parti — sahip kararı: KALDIRILDI; [4.6] tetikleyicisiz kalarak kapandı) — **`SET_PARAMS`/`start_at`/`SYNC_ALL` komut yüzeyleri** firmware'de duruyor ama backend'de hiçbir
  üretici yok (silinmiş PyQt GUI kalıntısı) — [4.6]/[5.3]'ün latent tetikleyicileri. Kaldırmak ya da
  backend'e bağlamak sahip kararı.

## ÇÜRÜTÜLENLER (çürütme turunun elediği — yeniden açmayın)

- `paket_onbellekte_hazir` boyut-tek kontrolü: **bilinçli ve kendi birim testiyle kilitli** tasarım
  (sha ~10 sn sürer, açılışta beklenmez; yanlış-pozitifte sha kapısı yeniden indirir) — ölçüldü, test koşuldu.
- Reconcile/bayat-STOP'un buluta yayınlanmaması: buluta göçmüş ESP'nin status'u backend'e zaten
  ULAŞMAZ → mekanizma o durumda hiç tetiklenmez; tutarlı (HG-5'in bilinen kalıntısı, cihaz-yerel
  tavan+termal sınırlıyor).
- `pairing.updateServiceConfig`'in takas öncesi çağrılması: oturum-içi config kasıtlı değişiyor
  (yorum + keşif merdiveni kendini onarıyor) — yalnız [5.9]'daki device_id yan etkisi ayakta.

---


### 18. parti — Eksik-taraması P1 kod işleri: [3.3] + [4.5] NACK yarısı + JETON Adım 4 (sahip onayı 2026-08-22)

Sahip: "p1 senin yapabileceğin kod işlerini yap … p0 kalsın not al sadece." Üç iş, aynı disiplin
(kırmızı-önce → düzeltme → mutasyon → tam süit):

| # | İş | Dosya(lar) | Test | Önce → Sonra | Mutasyon |
|---|---|---|---|---|---|
| [3.3] | estop-cloud client_id süreç-sabit + 7-haneli PID'de 24 karakter (broker 23 sınırı → ayna HİÇ bağlanamaz) | `servers/api_server.py` (`_mqtt_client_id`: `pemf_esc_{pid%1e5}_{seq}`) | `test_mqtt_client_id.py` (+3) | 3 kırmızı → 8/8 ✓ | 2/2 ✓ |
| [4.5]-NACK | `command_error` eventi işlenmiyordu + manuel ESP start ack-bekçisiz → NACK'lenen start tedavi geçmişinde "koştu" kalıyordu | `servers/api_server.py` (events dalı + `_start_ack_watch` — tekil VE batch yolu) | `test_nack_gorunurlugu.py` (7, yeni) | 5 kırmızı → 7/7 ✓ | 6/6 ✓ (batch'i unutma mutasyonu dâhil) |
| Adım 4 | `servers/jeton.py` hiçbir üretim kodundan çağrılmıyordu (bayrak açılsa bile çift yönlü no-op) | `servers/jeton.py` (`jeton_gate` + Supabase RPC taşıma) · `servers/ai_router.py:59` · `pf/apiClient.ts` (402 ayrımı) | `test_jeton_gate.py` (9, yeni) · `apiClient.jeton402.test.ts` (2, yeni) | 8+1 kırmızı → 9/9 + 35/35 ✓ | 7/7 ✓ (pro/stop kapılanır + bayrak-atlanır mutasyonları dâhil) |

**Bilinçli kararlar (18. parti):**
- **[4.5] asimetri:** NACK (kesin red) koşu kaydını KAPATIR; ack TIMEOUT'u kapatMAZ (ack QoS-0 —
  kayıp ack'te kapatmak, gerçekten çalışan bobinin dozunu kayıttan silerdi). Uyarı [1.1]'in işi.
- **Adım 4 taşıma katmanı:** belge "/api/tokens ucuna bağla" diyordu; entitlement deseniyle
  Supabase RPC'ye (`jeton_bakiyem`/`jeton_tuket`) doğrudan bağlandı — kimlik `auth.uid()`ten,
  idempotans RPC içinde; siteye fazladan sıçrama tek yeni arıza noktası eklerdi.
- **Uç eşlemesi:** `pro/stop|status|approve|reject|frame|organ|calibrate` KAPILANMAZ (stop
  güvenlik sınıfı; frame seans-içi akış — ücret seans-başına `pro/start`=5). `pro/propose`=sensor(1).
- **Bayrak durumu DEĞİŞMEDİ:** `PEMF_JETON_ENFORCED` kapalı; kapı bağlı ama uykuda. Satış açılmadı.

**P0 NOT (sahip: "kalsın, not al" — 2026-08-22):** STM 1-5 NTC termal kesme DERLEME-KAPILI
(koruma hiçbir katmanda yok — sahibin tezgâh işi) + `esp` dalı canlı sırlar. Kayıt: bellek
`pemf-acik-p0`.

**Özet:** 23 kesin bulgu (3'ü ciddiyet-1: broker-ölüyken sahte "durduruldu" onayı, firmware↔backend
status sözleşmesinin bayat-STOP güvenlik ağını öldürmesi, S3 kümülatif-tavan resume deliği; çoğu
2026-08-17 sonrası yazılan kodda ve birkaçı önceki düzeltmelerin kendisinde) + 3 doğrulanamayan
şüpheli + 5 "kasıtlı görünüyor" kalemi; hiç bakılamayanlar: gerçek donanım/tezgâh ölçümleri (tüm
firmware bulguları kod düzeyinde), HiveMQ bulut ucu, iOS/EAS, canlı Supabase RLS, Docker/GPU profili
ve pemf-vet-web'in ödeme akışı (5. turda denetlenmişti, bu turda yalnız sürüm/config tarafına bakıldı).

**Kapanış durumu (2026-08-20, 16. parti sonrası):** 23 bulgunun kod tarafında düzeltilebilir OLAN
TAMAMI kapandı ([4.6] dahil — yüzey kaldırılarak); sahip-kararı bekleyen 5 kalemin 3'ü sahip
onayıyla çözüldü (önbellek koruması, ölü yüzeyler, retained LWT), crash-loop ikizi sahip onayıyla
kapandı; AÇIK kalanlar: `esp` dalı canlı sır rotasyonu (sahip reddi — P0 kayıtlı),
`cloud_mqtt_provision` Warn-only + bayat-dosya alt kalemi, arka plan ön-indirmesinin
duraklatılamaması (bilinçli), 8266 status/ack retain=true (ayrı karar isterse ucuz), [5.7b] mesaj
yönlendirme (zararsız), pemf-app-packages/README yaşlanması ve 3 doğrulanamayan şüpheli (tezgâh/
canlı-uç ister). ⚠️ S3+8266 İKİNCİ REFLASH bekliyor (VERIFICATION §14).
