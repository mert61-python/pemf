# Üretim Doğrulama Checklist'i (Operasyonel)

Bu belge `PRODUCTION_READINESS_REPORT.md` §5 "Doğrulayamadıklarım" maddelerini **çalıştırılabilir
doğrulama adımlarına** çevirir. Bazıları bu ortamda zaten doğrulandı (✅); geri kalanlar çalışan
cihaz/dış-kaynak gerektirir — aşağıdaki komutları **cihazda/panelde** çalıştırın.

| # | Konu | Durum | Nasıl |
|---|------|-------|-------|
| 1 | Firmware güvenlik satürasyonu | ⏳ donanım | Bench testi (aşağıda) |
| 2 | SQLCipher sahada aktif | ⏳ cihaz | `/api/health` (aşağıda) |
| 3 | Supabase RLS canlı | ✅ **DOĞRULANDI** | `scratchpad/verify_supabase_rls.py` — 5/5 geçti |
| 4 | Cloudflare NAMED tünel | ⏳ cihaz | `device.env` + servis logu |
| 5 | Bağımlılık CVE | ✅ tarandı / ⏳ upgrade | `pip-audit` + izole-venv upgrade testi |
| 6 | AI model bütünlüğü/lisansı | ⏳ maintainer | SHA256 + lisans envanteri |
| 7 | Yük/soak | ⏳ cihaz | `scripts/soak_publish_5hz_8coil.py` + izleme |
| 8 | KVKK anonimleştirme | ✅ **DOĞRULANDI** | `tests/test_kvkk_anonymization.py` — 3/3 + `.plain.bak` ACL fix |
| 9 | firmware `[FIX-1c]` duty geçişi | ⏳ donanım | Bench testi (aşağıda) — **YAYIN ÖNCESİ ZORUNLU** |

---

## ✅ 3 — Supabase RLS (bu ortamda DOĞRULANDI)

`scratchpad/verify_supabase_rls.py` gömülü anon (publishable, tasarımı gereği public) anahtarla
kullanıcının kendi projesini **salt-okunur** probladı. Sonuç **5/5 geçti**:

- `devices` doğrudan SELECT → `200 []` (RLS satır sızdırmıyor)
- `patients` doğrudan SELECT → `401 permission denied for table patients`
- `resolve_device(p_device_id|p_code)` RPC → `200` (SECURITY DEFINER + anon GRANT deploy edilmiş)
- `devices` doğrudan INSERT → `401 "new row violates row-level security policy"` (anon yazamıyor)

**Sonuç:** eski anon-write policy'leri kaldırılmış, cross-tenant sızıntı kapalı, RPC tek erişim yolu.
Tekrar çalıştırmak için: `python scratchpad/verify_supabase_rls.py` (internet gerekir).

## ✅ 8 — KVKK anonimleştirme (bu ortamda DOĞRULANDI + gap kapatıldı)

`tests/test_kvkk_anonymization.py` (3 test, hepsi geçti): 5-yıl-inaktif hasta → PII `[ANONIM]` +
`anonymized=1` + arama-indeksi temizlenir (eski adla bulunamaz); aktif hasta korunur; idempotent.

**YENİ BULGU + FIX:** migration `.plain.bak` (tüm eski düz-metin DB) diskte **ACL'siz** kalıyordu →
SQLCipher'ı baypas eden PII kopyası. **Kapatıldı:** oluşturmada + startup'ta `lock_down_file` (SYSTEM+Admin)
ile kilitlenir (`sqlcipher_util.py` + `treatment_history_db.py` + `backend_service._harden_secret_file_acls`).
Kontrol (cihazda): `icacls "%APPDATA%\PEMF_GUI\*.plain.bak"` → yalnız `NT AUTHORITY\SYSTEM` + `BUILTIN\Administrators` görünmeli.

---

## ⏳ 2 — SQLCipher sahada gerçekten aktif mi (CİHAZDA)

Çalışan cihazda health uç noktasını sorgula (auth açıksa `-H "X-API-Key: <token>"` ekle):

```powershell
curl http://127.0.0.1:8000/api/health | ConvertFrom-Json | Select-Object atRestEncrypted
# Beklenen: atRestEncrypted = True
```

- `True` → whole-DB SQLCipher aktif (PII at-rest şifreli). ✅
- `False` → `sqlcipher3` wheel eksik VEYA `PEMF_ENCRYPT_AT_REST` set değil. **Üretimde OLMAMALI.**
  - Kontrol: `%APPDATA%\PEMF_GUI\device.env` → `PEMF_ENCRYPT_AT_REST=1` var mı?
  - Kontrol: `myenv\Scripts\python -c "import sqlcipher3; print(sqlcipher3.version)"` (wheel var mı?)
  - Not: PatientDB + TreatmentDB **fail-closed** (bayrak=1 + wheel-yok → RuntimeError, düz-metin YAZMAZ).

## ⏳ 4 — Cloudflare NAMED tünel (CİHAZDA)

```powershell
# Aktif tünel türü:
Get-Content "$env:APPDATA\PEMF_GUI\device.env" | Select-String "PEMF_TUNNEL|CLOUDFLARE|TUNNEL_TOKEN"
# Servis logunda tünel URL'i sabit mi (NAMED) yoksa her restart trycloudflare.com değişiyor mu (QUICK):
Get-Content "$env:APPDATA\PEMF_GUI\logs\*.log" | Select-String "tunnel|trycloudflare|cloudflared" | Select-Object -Last 10
```

- **QUICK** (`*.trycloudflare.com`, her restart değişir, SLA yok) = P1, üretime uygun değil.
- **NAMED** (sabit hostname + `TUNNEL_TOKEN`) = üretim hedefi. Cloudflare token'ı `device.env`'e girilince
  servis oto-NAMED'e geçer (bkz. memory: pemf-connection-audit "KALAN=NAMED tünel").

## ⏳ 5 — CVE upgrade (MAINTAINER)

`pip-audit` 6 CVE saptadı. **Bu ortamda izole-venv uyumluluk testi yapıldı** (aşağıdaki düşük-riskli
3'ü için — bkz. rapor B-9.3). Kalan (AI-model uyumluluk testi gerektiren) `onnx`/`torch` maintainer'da:

```powershell
# Düşük-risk (test-doğrulandı): cryptography>=43.0.1, python-multipart>=0.0.31, zeroconf>=0.149.0
# starlette: FastAPI'ye bağlı → FastAPI ile birlikte yükselt.
# onnx 1.15→1.16+, torch 2.1.2→2.6+: AI-model çıktısını yeniden-doğrula (8 model) + frozen EXE rebuild.
pip install -U cryptography python-multipart zeroconf
py -3.10 -m pytest guii/tests   # yeşil olmalı (bu ortamda doğrulandı)
```

## ⏳ 6 — AI model bütünlüğü/lisansı (MAINTAINER)

```powershell
# Bütünlük: dağıtılan model SHA256'ları beklenenle eşleşiyor mu (bozulma/değişim yok):
Get-ChildItem "C:\ProgramData\PEMF_GUI\ai_models\*" -Recurse -Include *.onnx,*.pt |
  ForEach-Object { "{0}  {1}" -f (Get-FileHash $_ -Algorithm SHA256).Hash, $_.Name }
```

- Her modelin **lisansı** (ONNX/YOLO/sklearn/librosa türevleri) ticari-kullanıma uygun mu — envanter çıkar.
- Klinik-doğruluk: modellerin validasyon metrikleri (kod denetimi kapsamı DIŞI — klinik ekip).

## ⏳ 7 — Yük/soak davranışı (CİHAZDA / STAGING)

```powershell
# 8-bobin 5Hz soak (mevcut script) — uzun süre çalıştır:
py -3.10 guii/scripts/soak_publish_5hz_8coil.py
# Paralel izleme (her 30sn): süreç belleği + DB büyümesi
while ($true) {
  $p = Get-Process -Name "PEMF*" -EA SilentlyContinue
  "{0}  RAM={1}MB  DB={2}KB" -f (Get-Date -Format HH:mm:ss),
    [int]($p.WorkingSet64/1MB),
    [int]((Get-Item "$env:APPDATA\PEMF_GUI\*.db").Length/1KB)
  Start-Sleep 30
}
```

- **Bellek sızıntısı:** RAM saatler içinde monoton artıyorsa sızıntı (WS/coil-run/sensör buffer).
- **WS kararlılığı:** istemci bağlı kalıyor mu, "Concurrent send" hatası logda var mı.
- **DB büyümesi:** dakika-ortalama sayesinde ~bobin başına ~20 satır/seans olmalı (ham veri değil).

## ⏳ 1 — Firmware güvenlik satürasyonu (DONANIM BENCH)

Backend'de freq/duty/sıcaklık **clamp'i bilinçli yok** (B-1.5); güvenlik firmware'e devredilmiş. Bench:

- STM32 firmware'e **sınır-dışı** freq/duty gönder (ör. duty=%100, freq=çok yüksek) → bobin/sürücü
  fiziksel olarak satüre mi ediyor, aşırı-ısınmada kesiyor mu? Osiloskop + termal kamera ile ölç.
- **Tıbbi cihaz için:** bu, yazılı **güvenlik-dosyası (safety case)** ile kanıtlanmalı — kod okuması
  bu iddiayı test etmez. Bu, B-1.5 "yazılı risk-kabulü"nün donanım tarafı.

## ✅ 9 — firmware `[FIX-1c]` duty geçişi (DONANIM BENCH) — SAHİP TEYİDİ 2026-08-20: reflash + tezgâh sorunsuz

**Neyi doğrulayacağız.** Denetim (2026-08-17) enerjili bir bobinin frekansı **ARTIRILDIĞINDA**
duty tick'inin bayat kaldığını buldu: `g_tpp` yeni (küçük) periyoda göre yazılıyor ama
`g_duty_ticks` eski (büyük) periyottan kalıyor → ~1 sn tek-polarite ve istenen dozun 4,78×'ine
kadar on-time. Düzeltme `firmware/stm32_pemf/Core/Src/main.c` içindeki `[FIX-1c]` bloğu: duty tick'i eski/yeni periyot
ORANIYLA yeniden ölçekliyor ve `g_tpp - 1 - DDS_DEAD_TIME_TICKS` ile klempliyor.

⚠️ **BU DÜZELTME TEZGÂHTA ÖLÇÜLMEDİ.** Koşan şey C kodu değil, ISR'ın Python modelidir
(`tests/test_firmware_frekans_artisi_duty.py`) — deponun kendi `test_firmware_stop_latency.py`
yaklaşımıyla aynı sınır. C kaynağındaki düzeltmenin VARLIĞINI ayrı bir yapısal kapı denetliyor ve
mutasyonla doğrulandı, ama **hiçbiri tezgâh doğrulaması değildir**. Gerçek donanımda ölçülmeden
yayınlanmasını önermiyorum.

### Kurulum

- STM32 kartı + **tek** bobin (bobin 1 yeter), akım probu ya da bobine seri düşük-değerli şönt.
- Osiloskop: 2 kanal — CH1 = sürücü çıkışı (H-köprü faz A), CH2 = faz B. Zaman tabanı 200 ms/div
  (geçiş yakalama), sonra 5 ms/div (duty ölçümü). Tetik: **tek-atış (single)**, CH1 yükselen kenar.
- Backend'i simülatörsüz (`PEMF_SIMULATE` YOK) çalıştır; komutlar `POST /api/coil/1/control` ile.

### Ölçüm 1 — 1 Hz → 2 Hz (küçük artış)

1. `{"freq":1,"duty":50,"phase":0,"duration":5,"start":true}` gönder, dalga oturana kadar bekle.
2. Osiloskobu tek-atışa al, `{"freq":2,"duty":50,"phase":0,"duration":5,"start":true}` gönder.
3. **KABUL ÖLÇÜTÜ:** geçiş anında tek-polarite (yalnız CH1 ya da yalnız CH2 aktif) süresi
   **≤ 250 ms**. Model bu değeri bekliyor; ölçülen değeri yaz.
4. Geçişten sonra kararlı durumda duty oranını ölç: **%50 ± %2** olmalı (ölçeklenmiş, bayat değil).

### Ölçüm 2 — 1 Hz → 100 Hz (büyük artış, asıl vaka)

1. `{"freq":1,"duty":50,...}` → oturt.
2. Tek-atış tetikle, `{"freq":100,"duty":50,...}` gönder.
3. **KABUL ÖLÇÜTÜ (ikisi birlikte):**
   - tek-polarite süresi **≤ 250 ms**;
   - geçiş penceresindeki on-time oranı, **iki uç noktanın (eski %50, yeni hedef %50) HİÇBİRİNİ
     AŞMAMALI**. ⚠️ Bu ölçüt bilerek böyle: aşağı-slew (inrush/EMI) **KASITLIDIR** ve %50→%5 geçişi
     enerjiyi AZALTIR, yani "ilk 500 ms'de dozun 4,78×'i" yanlış bir değişmezdir. Doğru soru
     "oran iki uçtan birini aştı mı".
4. **Karşıt-kanıt (regresyon kapısı):** 100 Hz → 1 Hz (frekans AZALIŞI) ölç. Bu yönde düzeltme
   ÖNCESİNDE de sorun yoktu; ölçüm sonrası duty **%50 ± %2** kalmalı ve tek-polarite penceresi
   olmamalı. Düzeltme bu yönü BOZMAMALI.

### Ölçüm 3 — klemp sınırı

1. `{"freq":1,"duty":95,...}` → oturt, sonra `{"freq":25000,"duty":95,...}`.
2. **KABUL ÖLÇÜTÜ:** ölü-zaman ihlali YOK (iki faz aynı anda AKTİF OLMAMALI, tek örnek bile).
   `DDS_DEAD_TIME_TICKS` şu an 0 olduğu için klemp `g_tpp - 1`'e dayanıyor; donanımda ölü-zaman
   sürücü tarafından sağlanıyorsa bunu da yaz.

### Kayıt

Her ölçüm için: ekran görüntüsü + ölçülen tek-polarite süresi (ms) + kararlı duty (%) +
firmware sürümü/commit'i. Sonuçları bu bölümün altına ekle. ⚠️ Tıbbi cihaz için bu, yazılı
**güvenlik-dosyasının** parçasıdır — kod okuması bu iddiayı test etmez.

## ⏳ 10 — `resolve_device` tazelik penceresi (CANLI SUPABASE · **SAHİBİN ELLE YAPACAĞI ADIM**)

**Bulgu (denetim 2026-08-17).** `resolve_device` RPC'si satırı **sunucuda**
`last_seen > now() - interval '5 minutes'` ile eliyordu; mobil uygulamanın `deviceRegistry.STALE_MS`i
de 5 dakika. İki pencere **eşit** olduğu için bayat satır istemciye hiç ulaşmıyordu:
`_cozumle`nin `durum:"bayat"` dalı ve `agTanisi`nin `bayat → cihaz_kapali` teşhisi **ölü koddu**.
Sonuç: cihaz 5 dakikadan uzun süredir kapalıysa kullanıcı `{durum:"yok"}` alıyor ve ekranda
**"Kodu kontrol edin"** yazıyordu — oysa kod DOĞRU, cihaz KAPALI. (2026-08-12 saha bildiriminin
aynısı: kullanıcı defalarca kodu kontrol ediyor.)

**Depoda yapılanlar.** `database/supabase_devices.sql` penceresi 30 güne çıkarıldı (yalnız YENİ
kurulumları etkiler) ve `pf/src/services/pairing.ts`in `default` mesajı iki sebebi birlikte
söyleyecek şekilde dürüstleştirildi. Kapı: `tests/test_bayat_cihaz_gorunur.py` (10 mutasyonla
doğrulandı) — değişmez "**sunucu penceresi istemci `STALE_MS`inden GENİŞ olmalı**".

**⚠️ ELLE YAPILACAK.** Yayında olan projede kurulum betiği **tekrar çalıştırılamaz**
(`database/README.md`: sırsız v1 aşırı-yükleri geri gelir). Bu yüzden dar kapsamlı bir dosya var:

1. Supabase Dashboard → **SQL Editor** → `supabase/resolve_device_bayat_gorunur.sql` içeriğini
   yapıştır → **Run**. (Tek transaction; yalnız `resolve_device`i değiştirir, `upsert_device`e
   dokunmaz.)
2. **KABUL ÖLÇÜTÜ:** cihazı kapat, **10 dakika** bekle, telefonda eşleştirme kodunu gir. Görülmesi
   gereken: *"Cihaz kayıtlı ama şu an çevrimdışı görünüyor…"*. Hâlâ *"…çevrimiçi cihaz
   bulunamadı…"* çıkıyorsa SQL uygulanmamıştır.
3. **Karşıt-kanıt:** cihaz AÇIKKEN aynı kodu gir → normal bağlanmalı (*"Cihaz eşleştirildi ✓"*);
   ve **rastgele/yanlış** bir kod gir → *"…çevrimiçi cihaz bulunamadı…"* gelmeli.

**APK/web yayını GEREKMEZ:** sahadaki uygulamada `bayat` dalı zaten yazılı; SQL uygulandığı an
doğru mesaj görünmeye başlar. (Yeni `default` metni bir sonraki yayında gelir.)

**Güvenlik notu — bu genişletme bağlanma kararını DEĞİŞTİRMEZ.** İstemci `STALE_MS`i 5 dakikada
kalıyor ve `pairing.cihazaBaglan` ile `getRemoteUrlForDevice` yalnız `durum === "bulundu"`e bakıyor
→ bayat/zehirlenmiş `tunnel_url` hiçbir zaman kullanılmaz. Genişletme yalnızca **sebebi** istemciye
taşır. Ayrıca RPC hâlâ tam `device_id` VEYA tam 6-haneli `pairing_code` istiyor (parça/joker yok) ve
tablo dökümü kapalı.

## ✅ 11 — S3/8266 süresiz-tavan RESUME kalıcılığı (DONANIM BENCH) — SAHİP TEYİDİ 2026-08-20: reflash + tezgâh sorunsuz

**Ne değişti (2. tur denetimi [1.3], 2026-08-20):** (a) S3 `loadState`, kümülatif süresiz-mod
birikimini `_beginOutput`a PARAMETRE geçirir — içerideki `forceSaveState` NVS'e artık ≈0 değil
DOĞRU değeri yazar; (b) her resume BİR KAYIT ARALIĞI (`NVS_KAYIT_ARALIGI_MS` = 30 sn) TABAN
sayılır ve HEMEN kalıcılaştırılır (S3: `_beginOutput` içindeki kayıt; 8266: `restorePWMState`
sonundaki `savePWMState`). Yön fail-safe: resume başına en fazla 30 sn ERKEN durma.

**Tezgâh prosedürü (skop/termal gerekmez; seri log yeter):**
1. Cihaza `duration=0` (süresiz) START gönder; ~2 dk çalıştır.
2. Gücü ANİDEN kes (soft reset DEĞİL), 5 sn içinde geri ver → log'da "NVS'den devam"/"EEPROM'dan
   yuklendi ve suresiz devam" görülmeli.
3. **20 sn içinde** gücü TEKRAR kes, geri ver. KABUL: ikinci resume'da devralınan birikim
   İLKİNDEN BÜYÜK olmalı (log'a `_suresizGecenMs` başlangıç değeri eklenerek ya da NVS/EEPROM
   dökümüyle doğrula) — eski S3 davranışında bu ikinci resume birikimi ≈0'a düşürüyordu.
4. Adım 2-3'ü betikle ~10 kez tekrarla: birikim her çevrimde ≥30 sn artmalı (taban).
5. **Karşıt-kanıt:** operatörden YENİ bir START gönder → birikim SIFIRLANMALI (pencere tazelenir);
   `duration>0` (süreli) seans + tek resume → kalan süre eski davranışla aynı (taban uygulanmaz;
   8266'da EEPROM artık resume'da da yazıldığı için kalan süre resume'lar arası KORUNUR).

**Kod-düzeyi kilit:** `tests/test_plan_a_deadman.py` (A-1 TAMAMLAMASI bölümü — yorum-soyulmuş
kaynakta sıra/taban kapıları + ayrıştırıcı model; mutasyonla doğrulandı). Koşan şey C kodu değil
Python modelidir — bu bölüm tezgâhta ölçülmeden REFLASH yayınlanmamalı.

## ✅ 12 — S3 faz-senkron latch'i boşta birikmez (DONANIM BENCH) — SAHİP TEYİDİ 2026-08-20: reflash + tezgâh sorunsuz

**Ne değişti (2. tur denetimi [4.3], 2026-08-20):** `syncPulseISR` PWM pasifken PB1 darbelerini
artık tamamen YOK SAYAR (ne sayar ne latch'ler). Eskiden seans bitince donan `s_tick` kilit
penceresindeyse boşta gelen 8 darbe sync'i kapatıyor, AYNI frekanslı sonraki seans (AI Pro hep
1 Hz → `freqChanged=false` → latch bilinçli korunur) faz senkronsuz koşuyordu.

**Tezgâh prosedürü (STM bobin-1 çalışır durumda, PB1→GPIO7 bağlı):**
1. S3'te AI Pro (1 Hz) seansı başlat → status'ta `sync_disabled:false` + `sync_ignored` yaklaşık
   sabit olmalı (kilitleniyor).
2. Seansı bitir; STM bobin-1'i ÇALIŞIR bırak; ≥10 sn bekle (boşta ≥10 PB1 darbesi).
3. AYNI frekansla (1 Hz) ikinci seansı başlat. KABUL: status'ta `sync_disabled:false` kalmalı ve
   `sync_locked` artmaya devam etmeli — eski davranışta bu ikinci seans `sync_disabled:true` ile
   (tek faz) koşuyordu. Boşta beklerken `sync_locked/ignored` sayaçları da ARTMAMALI (adım 2'de not al).
4. **Karşıt-kanıt (HG-3 asıl koruması bozulmadı):** STM bobin-1 100 Hz'deyken S3'ü 1 Hz MANUEL
   sürüşe al → seans İÇİNDE latch yine oluşmalı (`sync_disabled:true`, DC-yapışma önlenir).

**Kod-düzeyi kilit:** `tests/test_s3_sync_dc_yapisma.py` ([4.3] bölümü — aktiflik semantiği modele
eklendi + ayrıştırıcı + yorum-soyulmuş yapısal kapı; mutasyonla doğrulandı).

## ✅ 13 — Kardeş-birim sözleşme paritesi (DONANIM BENCH) — SAHİP TEYİDİ 2026-08-20: reflash + tezgâh sorunsuz

**Ne değişti (2. tur denetimi [5.1]+[5.2]+[5.3], 2026-08-20):** (a) 8266 `pwm_remaining_time` artık
S3 gibi SANİYE yayınlar (eski ham milisaniyeydi — 1000×); (b) 8266 `restorePWMState` süreli seansta
`_pwmDurationSec`i kalan süreden geri kurar (eski: status resume sonrası `pwm_duration=0` = SÜRESİZ
nöbetçisi raporluyordu); (c) S3 `UPDATE` fazı yalnız `phase` anahtarı VARSA değiştirir (SET_PARAMS dalı 15. partide kaldırıldı)
(PHASE_BELIRTILMEDI nöbetçisi — fazsız komut çok-bobinli faz desenini artık sıfırlayamaz).

**Tezgâh prosedürü:**
1. **[5.1]** Bobin 8'de 10 dk'lık süreli seans başlat; ~1 dk sonra `pemf/coil/8/status` payload'ını
   dinle. KABUL: `pwm_remaining_time` ≈ 540 (SANİYE) — eski firmware ≈ 540000 (ms) yayınlardı.
   S3 (bobin 6/7) aynı senaryoda aynı mertebeyi yayınlamalı (parite).
2. **[5.2]** Bobin 8'de 10 dk'lık seans; ~2 dk sonra ESP'yi güç-çevrimle. Resume sonrası status:
   `pwm_duration` > 0 (kalan süre mertebesinde, ~480±30 — EEPROM aralık tabanı dahil) VE
   `pwm_remaining_time` ile tutarlı. **Karşıt-kanıt:** süresiz (duration=0) seans + güç-çevrimi →
   `pwm_duration` 0 KALMALI (süresiz sözleşmesi).
3. **[5.3]** S3 bobin 6-7'ye AI Pro faz desenli seans (örn. 0°/180°) başlat; ardından `phase`
   ANAHTARSIZ bir `update` (yalnız freq/duty) yayınla. KABUL: skopta iki bobin arasındaki faz farkı
   KORUNUR (eski firmware ikisini de 0°'a çekerdi). **Karşıt-kanıt:** `phase` AÇIK gönderilen update
   fazı değiştirmeli; fazsız TAZE start 0°'dan başlamalı.

**Kod-düzeyi kilit:** `tests/test_esp_kardes_birim_paritesi.py` (yorum-soyulmuş yapısal kapılar +
karşıt-kanıtlar; 4/4 mutasyonla doğrulandı). Koşan şey C değil — tezgâhta ölçülmeden REFLASH yayınlanmamalı.

## ⏳ 14 — İKİNCİ REFLASH DELTASI: crash-loop ikizi + ölü-yüzey kaldırma + LWT + tek-atımlık olaylar (DONANIM BENCH · S3+8266 REFLASH — STM DEĞİŞMEDİ)

**Bağlam:** §9-13 tezgâhı 2026-08-20'de sahip tarafından koşuldu (sorunsuz). AYNI GÜN sahip
onayıyla firmware'e dört değişiklik daha girdi (12/15/16. partiler) → S3+8266 için YENİ bir
reflash gerekir; STM32'ye dokunulmadı.

**Ne değişti:**
  (a) 12. parti — SÜRELİ resume tabanı: <30 sn crash-loop'ta süreli seans artık her çevrimde
      ≥30 sn kısalır ve biter (eski: hiç bitmezdi). Süresiz taban ([1.3]) aynen.
  (b) 15. parti — set_params/sync_all/start_at yüzeyleri ve broadcast abonelikleri KALDIRILDI;
      start artık her iki cihazda koşulsuz HEMEN başlar.
  (c) 16. parti — LWT willRetain=false (5 connect); S3 tek-atımlık olaylar kuyruk doluyken
      kaybolmaz (restore + ACK sınırlı bekleme).

**Tezgâh prosedürü:**
1. **(a)** Bobin 8'de (ve S3'te) 5 dk'lık SÜRELİ seans başlat; cihazı ~20 sn aralıklarla 15+ kez
   güç-çevrimle (brown-out benzetimi). KABUL: seans en geç ~5 dk + birkaç çevrim içinde BİTER ve
   yeniden başlamaz (eski firmware süresiz sürerdi). Karşıt: tek kesintili normal resume'da kalan
   süre en fazla ~30 sn kısalır.
2. **(b)** `pemf/coil/6/control`e `{"command":"set_params",...}` ve `sync_all` yayınla → 8266'da
   "Unknown command"; S3'te sessiz yok-sayma; `start_at`li start HEMEN başlar. Karşıt: normal
   start/stop/update/SELFTEST akışları aynen.
3. **(c)** Bobini başlat, ESP'nin fişini çek → backend ~keepalive'da "bağlantı kesildi" göstermeli
   (LWT canlı teslim — davranış DEĞİŞMEDİ). Ardından `mosquitto_sub -t pemf/coil/+/events
   --retained-only` → HİÇ retained offline KALMAMALI (eski: kalıyordu). E-stop ACK round-trip'i
   mdns penceresinde de teyit olmalı (backend "onay gelmedi" alarmı YOK).

**Kod-düzeyi kilitler:** tests/test_sureli_crashloop_ikizi.py · test_olu_komut_yuzeyleri_kaldirildi.py ·
test_esp_lwt.py · test_s3_oneshot_kaybi.py (hepsi mutasyonla doğrulandı). C bu makinede
derlenmediğinden İLK DERLEME Arduino IDE'de yapılacak — derleme hatası çıkarsa kaldırma
turundaki artık-referans demektir (kapılar yakalamadıysa bildirin).
