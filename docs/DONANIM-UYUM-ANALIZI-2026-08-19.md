# Donanım ↔ Backend PEMF Uyum Analizi (2026-08-19)

> **Yöntem:** çok-ajanlı adversaryal analiz — 6 protokol boyutu paralel tarandı, her
> uyumsuzluk iddiası ayrı ajanla çürütülmeye çalışıldı. **14 iddia → 12 gerçek** (2 çürütüldü).
> 21 ajan, yüksek effort. Kaynak: çalışma kopyası @ commit `7e87cf9`.

> ⚠️ **Bu bir DENETİM RAPORUDUR, otomatik düzeltme DEĞİL.** HG-* maddeleri tasarım/mimari
> kararı gerektirir — sahip onayı olmadan kod değişikliği YAPILMADI.
>
> ## ÇÖZÜM DURUMU (2026-08-19 akşamı — koddan-kesin tur)
> | Kalem | Durum | Commit |
> |---|---|---|
> | D-2 (8266 `_effectiveDutyPct`) | ✅ düzeltildi (benim regresyonum) | `7e87cf9` |
> | HG-4 (backend ACK round-trip) | ✅ düzeltildi (+2 alt-bug) | `405d547` |
> | D-1 (ölü topik selftest/reset) | ✅ düzeltildi | `ffd4406` |
> | D-3 (ESP freq tavanı, 8266'ya göre) | ✅ düzeltildi | `ffd4406` |
> | D-4 (8266 LWT + backend retained-events) | ✅ düzeltildi — ⚠️ 8266 REFLASH gerekir | `ffd4406` |
> | HG-2 (STM DC-bias dalga) | ✅ düzeltildi — STM DDS simetrik bipolar (S3 sözleşmesi, net DC=0) — ⚠️ STM REFLASH + doz yeniden kalibrasyonu ZORUNLU | `356d576` |
> | HG-1 (STM termal) | ✅ kod hazır, DERLEME-KAPILI (`PEMF_NTC_TERMAL_ENABLED=0`) — NTC bağlanınca 1 yapılıp tezgahta doğrulanacak; HG-2 ile en kötü ısınma sürücüsü (DC-bias) zaten kalktı | `356d576` |
> | HG-3 (faz kilidi DC-yapışma) | ✅ kod yarısı düzeltildi — ⚠️ S3 REFLASH + tezgah skop zorunlu | `09bf8eb` |
> | HG-5 (broker failover E-stop) / HG-6 (reboot) | ⏳ deadman sahip değişmeziyle çatışıyor — karar bekliyor |  |

# PEMF HİBRİT BOBİN KOMUT UYUM RAPORU
**Kapsam:** 8 bobin / 3 işlemci ailesi (STM32 1-5, ESP32-S3 6-7, ESP8266 8) + Python backend · Kaynak: çalışma kopyası (guii)
**Doğrulama:** 12 gerçek uyumsuzluk adversaryal geçti · 2 iddia çürütüldü (rapora alınmadı)

---

## 1. TEK CÜMLE HÜKÜM

**Hayır — sistem şu an bobin komutlarında TUTARLI DEĞİL:** aynı operatör dozu (duty/freq) üç bobin ailesinde fiziksel olarak farklı alana/dalgaya dönüşüyor ve **en tehlikeli tek şey**, STM bobinlerinin (1-5) hiçbir katmanda (firmware, backend) termal kesmeye sahip olmaması ile bu bobinlerin duty≠%50'de asimetrik DC-bias'lı dalga üretip sınırsız ısınabilmesinin BİRLEŞMESİDİR — canlı hayvan üzerinde 48°C'yi aşan ısınmayı hiçbir yazılım/donanım katmanı durduramaz.

---

## 2. HASTA GÜVENLİĞİ UYUMSUZLUKLARI (öncelikli, ayrı)

### HG-1 · STM bobin 1-5 HİÇBİR katmanda termal korumasız  `tezgah_gerekli`
- **Uçlar:** STM firmware'de sıcaklık okuması/kesmesi TAMAMEN YOK — `stm32f4xx_hal_conf.h:41` `HAL_ADC_MODULE_ENABLED` yorum içinde (ADC fiziksel kapalı). Seri protokol sıcaklık taşımıyor → `api_server.py:2324-2334` bunu birebir belgeliyor ("STM bobinlerinde sicaklik/akim/alan telemetrisi YOKTUR"). Backend 48°C limiti sahip kararıyla kaldırılmış (`hardware_controller.py:30`). Buna karşılık ESP kendini korur: S3 `CoilController.cpp:239-254` (enforceThermalLimit 48/45, ağdan bağımsız), 8266 `esp8266_pemf_coil.ino:348-369`.
- **Senaryo:** STM bobin 1-5'i süren her yol (`/api/coil/{id}/control`, `/api/coil/batch`, seans) → doku 48°C'yi aşsa yalnız süre-deadline (120 dk) veya operatör keser; termal kesme YOK. Aşağıdaki HG-2 DC-bias ısınmasıyla birleşince risk büyür.
- **Fix:** Cihaz-yerel çözüm — STM'ye NTC + ADC (HAL_ADC_MODULE_ENABLED) + firmware histerezisli kesme (48/45). **⚠️ Kaldırılan backend 48°C limitini GERİ EKLEME** (sahip kararı/regresyon listesi); çözüm katmanı farklı (cihaz-firmware).

### HG-2 · DUTY anlamı STM↔ESP ayrışık — aynı değer, farklı dalga + farklı net DC  `tezgah_gerekli`
- **Uçlar:** STM `main.c:1108-1128` (v2.0 DDS): sürekli tümleyen sürüş, `state=(adj<duty)?A:B`, bir bacak hep HIGH → net ortalama = V·(2·duty−1) → **duty=%25'te −%50·V DC bias**, yalnız %50'de DC=0. ESP S3 `CoilController.cpp:105-122`: her yarı-periyotta ayna ± darbe, aralarda ikisi de LOW → **her duty'de net DC≈0**. 8266 `CoilController.cpp:87-105`: tek pin unipolar, net DC=duty. Backend'de firmware-ailesi arası duty dönüşümü YOK (`stm32_protocol_limits.py` STM32_DUTY_MAX_RATIO=None).
- **Senaryo:** 8 bobine ortak duty=%25 (`ai_router.py:446-468` "AI Auto" hepsi aynı değeri gönderir). STM 1-5 → belirgin negatif DC bias, neredeyse tek-yönlü alan + yarı-DC elektromıknatıs ısınması; ESP 6-8 → simetrik, DC=0. **Aynı parametre AYNI seansta fiziksel olarak farklı alanlar → koordineli çok-bobinli tedavi sahte.** STM'de termal kesme olmadığından (HG-1) DC-bias ısınması sınırsız.
- **Fix:** (1) Dalga sözleşmesini kararlaştır — hedef simetrik bipolar ise STM DDS'i ESP S3 gibi çift-ayna-darbe+LOW boşluklu yap, ya da backend'e per-firmware duty→eşdeğer-alan dönüşümü ekle. (2) STM termali (HG-1).

### HG-3 · Toleranslı faz kilidi UÇ freq oranında (STM ≳50× ESP) DC-yapışmayı ÖNLEMEZ  `tezgah_gerekli`
- **Uçlar:** S3 `CoilController.cpp:75-78`: syncPulseISR her RISING'de tol=tpp/50+2 penceresinde s_tick=0'lar. STM freq ≥ ~50× ESP freq iken darbe aralığı tol'den küçük → her darbe kilitler → s_tick asla yarım-periyoda (25000) ulaşamaz → çıkış tek polaritede DC. 8266 `CoilController.cpp:39-41`: bu tehlike bilinerek sync KALDIRILMIŞ. STM `main.c:1031`: farkında değil.
- **Reachability (HG-4 ile aynı kök):** Idle STM bobin1 default freq=100 Hz — `hardware_controller.py:325,48` idle coil1 freq alanına state['freq']=100.0 koyar; `main.c:1031-1033` `if(i==0 && g_pwm_started)` coil1 duty=0 olsa bile PB1'i 100 Hz'de darbeler (coil1 running/duty kontrolü YOK). Operatör STM coil2'yi çalıştırıp (keep-alive açılır, PB1=100Hz) S3 coil6'yı manuel 1 Hz sürdüğünde → S3 sayacı yakalanıp DC'ye yapışır (tol=1002 > darbe aralığı 500 tick).
- **Senaryo:** Bobinde DC akım → sürekli tek-yön alan + ısınma → yanık/aşırı-ısınma. **Normal faz iş akışı (AI Pro: tüm bobinler 1 Hz, oran 1×) GÜVENLİ**; hata yalnız manuel per-coil ile STM coil1 ≳50× ESP coil6/7 komutlandığında VE fiziksel PB1→GPIO7 hattı bağlıyken oluşur.
- **Fix:** (1) FIRMWARE — S3 syncPulseISR'a 8266 eşdeğeri gömülü koru: ardışık "çok-erken darbe" sayımıyla sync'i devre dışı bırak (s_sync_ignored sayacı VAR ama kapı olarak kullanılmıyor). (2) STM `main.c:1031` — PB1'i coil1 GERÇEKTEN çalışırken (duty>0) üret; idle referans bobin PB1 sürmesin. (3) Backend manuel yolda ≳50× ayrışmayı reddet/uyar (`api_server.py:1428-1463`).

### HG-4 · ESP ACK topiği backend'de OKUNMUYOR — STOP teslimi uygulama düzeyinde doğrulanamaz  ✅ ÇÖZÜLDÜ (405d547)
> **DURUM:** backend ack round-trip eklendi — `pemf/coil/+/ack` dinleniyor, E-stop onayı command_id ile eşleniyor, onay gelmezse operatör uyarılıyor (bloklamadan). Adversaryal review + mutasyonla doğrulandı; 2 alt-bug (retain filtresi, telemetri damga regresyonu) yakalandı ve düzeltildi.
- **Uçlar:** S3 `NetworkManager.cpp:764-785` ve 8266 `NetworkManager.cpp:744-758` → pemf/coil/{id}/ack'a command_id+success yayınlar. Backend `api_server.py:451-456` SADECE sensors/status/events/alarm+gateway/bridge SUBSCRIBE eder; **pemf/coil/+/ack YOK**, `_on_mqtt_message_api` (528-636) ack dalı YOK. command_id her yerde üretilir (1350,1383,1422,1460,1791,3137) ama HİÇBİR yerde geri okunmaz. `_mqtt_publish` (1121-1148) yalnız broker QoS-1 PUBACK okur.
- **Senaryo:** Bobin 6/7/8 WiFi'siz iken backend STOP yayınlar → broker PUBACK döner → çağıran "success" sayar, operatöre "durduruldu" gösterir; ama ESP mesajı HİÇ almaz (STOP retain=False, offline ESP asla teslim almaz). **Bobin danger-window boyunca fiziksel enerjili kalırken UI "durdu" der.** Sınırlayıcı (sıfırlamaz): ESP yerel duration timeout + yerel termal 48/45.
- **Fix:** (1) `subscribe('pemf/coil/+/ack')`; (2) msg_type=='ack' dalı + pending-command dict/timeout; (3) STOP/E-stop "confirmed" güvencesini PUBACK yerine ack round-trip'e bağla, timeout'ta AÇIK uyarı; (4) watchdog/estop STOP publish'ini retain=True yap (`api_server.py:503` yorumu bunu varsayıyor, kod yapmıyor).

### HG-5 · Broker failover — ESP buluta geçince backend'in E-stop'u ESP'ye ULAŞMAZ  `tezgah_gerekli`
- **Uçlar:** ESP (S3 `NetworkManager.cpp:579-585`, 8266 `721-738`) yerel broker'a 3 deneme sonra HiveMQ cloud'a (`Secrets.h:49/35`, TLS 8883) GEÇER. Backend HEM dinleyici HEM yayıncı YALNIZ 127.0.0.1:1883 (`api_server.py:692,1102,1120`); cloud yolu YOK. Köprü de yok (`mosquitto.conf:6` "HiveMQ bridge KALDIRILDI").
- **Senaryo:** Yerel mosquitto çöker (bilinen arıza: `mosquitto.conf:26`) ama gateway internet ayakta → ESP buluta failover → backend 127.0.0.1 probe başarısız → **E-stop ESP'ye HİÇ ulaşmaz**. Operatör tarafı SESSİZ DEĞİL (`api_server.py:1127-1137` fix → "ESP ayağı BAŞARISIZ" gösterir), sessizlik hayvan tarafında. durationSec=0 (kasıtlı süresiz, `CoilController.cpp:499`) modunda bobin YALNIZ 48°C termal kesmeye kadar enerjili kalır. ESP'de komut-kaybı deadman'i YOK.
- **Fix:** (a) ESP'ye komut-kaybı deadman'i (T sn heartbeat gelmezse hangi broker olursa olsun PWM durdur — en güvenli, süresiz-mod dahil kapsar); VEYA (b) backend E-stop'u yerel+cloud AYNA yayınlasın; VEYA (c) kontrol-kritik ESP coil'lerde cloud failover'ı KAPAT.

### HG-6 · Reboot devam (NVS/EEPROM) + backend mutabakat STOP kapsamı  `tezgah_gerekli`
- **Uçlar:** STM kalıcılık YOK (reboot=tüm coil 0, güvenli). S3 `CoilController.cpp:228,436-504` NVS'e 30sn'de kaydeder, reboot'ta kalan süreyle DEVAM eder; 8266 `CoilController.cpp:171,451-536` EEPROM aynısı. Backend reconcile `backend_service.py:358-386` YALNIZ backend açılışında çalışır (coil 1-8 STOP, retain YOK). ESP tek-başına reboot'ta reconcile YOK — `api_server.py:602-605` wifi_connected yalnız connected=True yapar, hayalet bobine STOP göndermez.
- **Senaryo:** Aktif seans ortasında ESP reboot (backend ayakta) → ESP NVS/EEPROM'dan OTONOM devam, backend sadece "bağlandı" der. Bu offline penceresinde operatörün bastığı STOP retained olmadığından KAYBOLUR. Bulut-göçmüş ESP'ye yerel reconcile hiç ulaşmaz. **BOUNDED** — firmware duration bekçisi (`:214`) + `_esp_duration_seconds` (`api_server.py:1038-1071`) duration=0'ı sonlu kapağa çevirir + yerel termal 48/45 sınırlar; süresiz DEĞİL.
- **Fix:** (a) wifi_connected/ilk-status'ta bobin running raporlarken _active_session pasifse O bobine hedefli STOP; (b) ESP boot/birth event + per-coil mutabakat; (c) STOP retain=True; (d) `_mqtt_publish`'in aktif broker'a (bulut dahil) ulaşması.

---

## 3. DİĞER GERÇEK UYUMSUZLUKLAR (risk sırasına göre)

| # | Konu | Uçlar (file:line) | Klinik sonuç | Fix |
|---|------|-------------------|--------------|-----|
| D-1 | **Ölü topik: SELFTEST + reset_pwm hiçbir ESP'ye ulaşmıyor** (cihaz-calismaz) | Backend selftest `api_server.py:1347` & reset_pwm `:1380` SADECE `pemf/esp32_{i}/command`'a yayınlar; S3 `NetworkManager.cpp:509-510` ve 8266 `:725-726` bu topiğe ABONE DEĞİL. `stop_all_coils` `hardware_controller.py:262` range(1,6) yalnız STM. | selftest ESP 6-8'de HİÇ çalışmaz (arızalı ESP sessizce geçer=yanlış tanısal güvence); reset_pwm sonrası seans-dışı ESP bobini enerjili kalır. **E-stop güvende** (coil/control'e de yayınlıyor, `:3139`). | Selftest/reset döngülerini `pemf/coil/{i}/control`'e (emergency_stop çift-yayın kalıbı gibi) yayınla; reset'te ESP 6-8'e stop publish et. |
| D-2 | **duty ÜST-SINIR sapması** (yanlis-cikti) | S3 `CoilController.cpp:280` MAX_DUTY_CYCLE=50; 8266 gerçek dalga `CoilController.cpp:358-359` `duty_t>=tpp/2` ile ~%50'ye SERT kirpar; STM tavansız (~%99.8 fiziksel, `main.c:1057-1060`). Backend ESP yoluna clamp YOK (`api_server.py:1453`), STM'ye ham ratio (`hardware_controller.py:157`). | duty>50 girilirse: STM 1-5 ~%70 asimetrik sürer, ESP 6-8 ~%50'ye kirpar → **dizi genelinde tutarsız doz; yön STM'de YUKARI** (ESP akranlarını aşar). AI Pro yolu %50'de klipliyor (etkilenmez); boşluk manuel/ham yolda. | STM manuel yoluna ESP ile aynı üst duty tavanını uygula (protocol_limits'i tek kaynak yap). **Ayrı 8266 bug (✅ DÜZELTİLDİ 7e87cf9):** `_effectiveDutyPct` hiç hesaplanmıyor (`CoilController.cpp:117`=0) → aktifken duty_cycle=0 raporluyor; `_applyPWM`'de gerçek duty_t/tpp'den hesapla. |
| D-3 | **freq aralığı: STM/backend 1-25000 / ESP 1-1000** (yanlis-cikti) | STM `main.c:176-179` FREQ_MAX=25000; backend STM yolu `normalize_frequency_hz` uygular (`hardware_controller.py:155`, tutarlı). ESP `constrain(freq,1,1000)` (S3 `CoilController.cpp:279`, 8266 `:215`). Backend ESP yolu ham (`api_server.py:1452,1524,1792`), pydantic üst sınır YOK. | freq 1001-25000 tek komutta: STM 1-5 komut değeri, ESP 6-8 sessizce 1000'e kirpar → **ESP bobinlerine yanlış tedavi frekansı.** Tipik PEMF <100 Hz, AI Pro=1 Hz güvenli; boşluk operatörün >1000 Hz komutlaması. getState telemetri kırpmayı ifşa eder. ("Faz kilidi kopar" iddiası geçersiz — üç ESP aynı kirpar.) | ESP MQTT yoluna publish'ten önce [1,1000] normalize VEYA freq>1000'i reddet (422); tercihen transport-farkındalıklı tek freq-normalize fonksiyonu. |
| D-4 | **LWT simetrisi — 8266'da last-will YOK** (yanlis-cikti) | S3 yerel+bulutta LWT ayarlar (`NetworkManager.cpp:489-503,529-537`, offline event, retain=true). 8266 `connect(clientId)` `:665` ve `:681` will PARAMETRESİZ → LWT YOK. Backend fallback: 30sn staleness watchdog (`api_server.py:481-525`); 8266 her 1sn sensör yayınlar. | Bobin 8 ANİ koparsa: S3 ~keepalive'da "koptu" der, 8266 YALNIZ ~30sn staleness ile geç fark edilir → UI'da ~30sn "canlı" + bayat sıcaklık. **Güvenlik değil** (PWM ağdan bağımsız + yerel termal). Ek: S3 retained "offline" reconnect'te temizlenmiyor → geçici churn. | 8266 connect'i S3 ile birebir yap (willTopic=pemf/coil/8/events); backend `:602` 'mqtt_connected'i de connected=True yapan dala ekle VEYA firmware reconnect'te retained "online" yayınlasın. |

---

## 4. TEZGAHTA ÖLÇÜLMELİ (koddan kesinleşmez — dalga/faz/dead-time/sıcaklık)

1. **STM asimetrik/DC-bias dalganın gerçek ısınması** (HG-1/HG-2): duty=%25 → −%50·V bias'ın doku-yüzey sıcaklığı 48°C'yi aşıyor mu? Osiloskop + termal + akım probu.
2. **Üç topolojinin alan-eşdeğerliği** (HG-2): aynı sayısal duty/freq STM (bipolar-bölme), S3 (bipolar-boşluklu yarı-periyot), 8266 (unipolar tek-faz) ailelerinde EŞİT B-alanı veriyor mu? Alan probu.
3. **DC-yapışma** (HG-3/HG-4): STM coil1=100 Hz PB1 + S3 coil6=1 Hz komutuyla bobin ucunda DC/ısınma osiloskop+termal ile doğrula. **Fiziksel PB1→GPIO7 hattı shipped donanımda BAĞLI mı?** — bağlı değilse hata pratikte tetiklenmez.
4. **E-stop danger-window** (HG-4/HG-5): ESP WiFi-partition + STOP senaryosunda bobin ne kadar sürede de-enerjize oluyor? Yerel mosquitto düşür + ESP'ye ayrı internet ver, E-stop'un buluttaki bobine ULAŞMADIĞINI ve enerjili kalma süresini ölç.
5. **8266 ani-kopuş termal kapsaması** (HG-4, D-4): ~30sn ağ-kör pencerede yerel 48/45 termal-trip gerçekten durduruyor mu?
6. **Reboot resume** (HG-6): ESP'yi seans ortasında reboot et — NVS/EEPROM resume gerçekten oluyor mu, offline STOP kayboluyor mu, firmware duration+termal kapağı kesiyor mu?
7. **Dead-time / shoot-through** (çürütülen, ama fiziksel): STM `main.c:138-152` DDS_DEADTIME_NOP_ITERS=21 NOP boşluğu (~0.75-1.25µs, ÖLÇÜLMEMİŞ) gerçek MOSFET turn-off gecikmesini aşıyor mu? Veri sayfası + osiloskop.
8. **8266 SELFTEST davranışı** (D-1): 8266'da SELFTEST handler'ı yok — self-test davranışını tanımla/doğrula.

---

## 5. SAĞLAM ÇIKANLAR (gerçekten uyumlu — 2 iddia çürütüldü)

- **Shoot-through / duty tavanı runtime-güvenli:** ESP tarafında asıl koruma MAX_DUTY_CYCLE değil, TICK-seviyesi klemp — S3 `CoilController.cpp:371-372` (yarim-DEAD_TIME) ve 8266 `:359` (`duty_t>=tpp/2→(tpp/2)-1`); yarı-periyot+ölü-zamandan hesaplanır, backend değerinden BAĞIMSIZ, yazılımdan devre dışı bırakılamaz. Backend duty=90 gönderse bile shoot-through OLMAZ. Tek kalan: ölü/yanıltıcı `ESP_LIVE_DUTY_MAX_RATIO=1.0` sabiti (kod-hijyeni, çalışma-zamanı riski değil).
- **Dead-time mekanizması yapısal olarak doğru:** STM `main.c:1110-1127` break-before-make (önce karşı bacağı kapat → NOP → sonra aç); S3 yapısal 2-tick + "ikisi asla HIGH değil" değişmezi (`CoilController.cpp:114-122`); 8266 tek-pin topolojik olarak bağışık. Farklı donanım→farklı mekanizma DOĞRUDUR, uyumsuzluk değil.
- **STM seri protokol tutarlı:** STM_OK/NACK/READY/ERR `headless_core._handle_stm_line`'da tam işleniyor; freq [1,25000] STM firmware ile backend normalize birebir eşleşir.
- **AI Pro faz iş akışı güvenli:** HEM STM 1-5 HEM ESP 6-7'ye `_AI_PRO_FREQ_HZ=1.0` (`ai_router.py:522,749,771`) → oran 1× → DC-yapışma OLUŞMAZ.
- **E-stop birincil yolu (`pemf/coil/{id}/control`) STM+ESP'ye ulaşır** (broker yerelken); reset_pwm birincil güvenlik yolu değil.
- **STM reboot güvenli başlar** (kalıcılık yok, tüm coil 0).

---

**Öncelik sırası (sahip kararı gereken):**
1. STM cihaz-yerel termal kesme (HG-1) + duty dalga sözleşmesi kararı (HG-2) — sürekli, koşulsuz risk.
2. ESP komut-kaybı deadman'i (HG-5 + HG-4 + HG-6'yı tek hamlede kapatır — en yüksek kaldıraç).
3. Backend ACK round-trip (HG-4) — E-stop "confirmed" güvencesini gerçek yap.
4. Ölü topik fix (D-1) + ESP freq/duty clamp (D-2, D-3) — kod-kesin, tezgah gerektirmez.
