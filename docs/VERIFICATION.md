# Üretim Doğrulama Checklist'i (Operasyonel)

Bu belge `PRODUCTION_READINESS_REPORT.md` §5 "Doğrulayamadıklarım" maddelerini **çalıştırılabilir
doğrulama adımlarına** çevirir. Bazıları bu ortamda zaten doğrulandı (✅); geri kalanlar çalışan
cihaz/dış-kaynak gerektirir — aşağıdaki komutları **cihazda/panelde** çalıştırın.

| # | Konu | Durum | Nasıl |
|---|------|-------|-------|
| 1 | Firmware güvenlik satürasyonu | ⏳ donanım | Bench testi (aşağıda) |
| 2 | SQLCipher sahada aktif | ✅ **DOĞRULANDI (2026-09-13)** | `C:\ProgramData\PEMF_System\PEMF_GUI` → `patients.db` + `pemf_treatment_history.db` **ŞİFRELİ**. ⚠️ Ama anahtarın makine-dışı kopyası YOK — §2a |
| 2a | ⚠️ **Anahtar emaneti** | ❌ **AÇIK (P0 sınıfı)** | Anahtar yalnız `pemf_secrets.json → auto.sqlcipher_key` (DPAPI, **makineye bağlı**). `~/pemf-sirlar.pemfsec` onu TAŞIMIYOR → makine kaybında veri **kalıcı okunamaz**. Araç: `scripts/hasta_anahtari_emanet.py` |
| 3 | Supabase RLS canlı | ✅ **DOĞRULANDI (yeniden: 2026-09-13)** | 6 tablonun altısı da anon'a **401/42501**; RPC kapısı çalışıyor |
| 4 | Cloudflare NAMED tünel | ⏳ **HÂLÂ ÖLÇÜLMEDİ** | ⚠️ 2026-09-13'te elle başlatılan backend'de `tunnelUrl` boştu ama o **launcher koşulu DEĞİL**. Doğru ölçüm: uygulamayı launcher'dan aç → `GET /api/health` → `tunnelUrl`. NAMED için Cloudflare token'ı gerekir (sahipte) |
| 5 | Bağımlılık CVE | ✅ **düşük-riskli 3'ü YAPILDI** / ⏳ onnx+torch | ölçüldü: cryptography 50.0.0 · multipart 0.0.31 · zeroconf 0.149.0 |
| 6 | AI model bütünlüğü | ✅ **DOĞRULANDI (2026-09-13)** | `scripts/model_butunluk.py` — gömülü paket **56/56 bayt-birebir** |
| 6b | AI model **lisansı** | ⏳ maintainer | envanter — AGPL kalemi `docs/AGPL-KARARI.md` |
| 7 | Yük/soak | ⚠️ **kısa koşu TEMİZ** / ⏳ uzun koşu | 25 dk: RSS +%0,9 (sızıntı YOK), DB sabit. ⚠️ eski betik **MQTT** üzerinden → ESP kapalıyken hiçbir canlı yolu zorlamıyor; yerine `scripts/soak_http_ws.py`. 72 saatlik klinik koşusu sahipte |
| 8 | KVKK anonimleştirme | ✅ **DOĞRULANDI** | `tests/test_kvkk_anonymization.py` — 3/3 + `.plain.bak` ACL fix |
| 9 | firmware `[FIX-1c]` duty geçişi | ⏳ donanım | Bench testi (aşağıda) — **YAYIN ÖNCESİ ZORUNLU** |
| 16 | **STM reflash + doz yeniden kalibrasyonu** | ⏳ donanım | §16 (aşağıda) — DDS simetrik bipolara geçti, saha cihazı kalibre DEĞİL |
| 17 | **Donmuş EXE ürün senaryoları** | ✅ **DOĞRULANDI (2026-09-17)** | `scripts/urun_senaryolari.py` — **48/48**. Sevk edilen ikiliyi çalıştırır; suit'in göremediği açılış sırasını ölçer (§17) |

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
# onnx 1.15→1.16+, torch 2.1.2→2.6+: AI-model çıktısını yeniden-doğrula (14 modül; torch-tabanlı scratch CPN dahil) + frozen EXE rebuild.
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

---

## ⏳ 15 — Araştırma AI Pro: fantom/petri 3B çerçevesi ve kapalı döngü (KABİN TEZGÂHI · SAHİBİN ELLE YAPACAĞI ADIM)

**Bağlam:** Araştırma modunda AI Pro artık kedi yerine iki modelle çalışıyor (Fantom Tümör, Petri
Kuyu — plan: `docs/arastirma-ai-pro-fantom-petri-plani.md`). Sürüş bilinçli olarak **kapalı**:
`PEMF_ARASTIRMA_AIPRO=0` (bkz. `deploy/device.env`). Sebep ölçülmüş bir belirsizlik, tahmin değil:

  · Karar #6'ya göre fantom/petri kabinde YATAY, tabanın hemen üstünde duracak. Kamera lensi de
    taban hizasında (Y=−25 cm) olduğu için ışın hedef düzlemini SIĞ açıyla keser: gerçek bir
    fotoğrafta kuyu konumu kabin DIŞINA düştü (−97 · −24 · +1096 cm). Eski (Z=0) düzlemle aynı
    fotoğraf (−2,3 · +7,7 · 0,0) cm veriyor.
  · Fantom doz modelinin eğitim aralığı x −5,7…−3,1 · y −6,0…+6,1 · z −3,6…+4,0 cm — yani model
    kabin ORTASINA yakın duran bir fantomla eğitilmiş. Taban yerleşimi (y ≈ −24 cm) bu aralığın
    tamamen dışında kalır (arayüz bunu "eğitim aralığı dışında" diye yazar ama doğru çerçeve
    olmadan sayı zaten anlamsızdır).

> ⚠️ **BU DEĞERLER GEÇİCİ — sahip notu (2026-09-09): "kamera ile fantom ve petri konumları için
> sahada tekrar düzeltme yapacağım".** Aşağıdaki işaret kenarı (15 cm), köşe yerleşimi (11/11 cm),
> hedef düzlemi (tabandan 5 cm) ve kamera konumu (`fixed_position_cm`) SAHADA ölçülüp
> güncellenecektir. Yazılım tarafında yapılacak tek iş yaml'daki sayıları değiştirmektir; kod
> değişikliği GEREKMEZ. Ölçüm bitene kadar `PEMF_ARASTIRMA_AIPRO` **0** kalır.

**2026-09-09 SAHİP ÖLÇÜSÜ yapılandırmaya yazıldı:** işaret kenarı **15 cm** (yeni basılı sayfa
`PEMF_ArUco_Marker_5X5_50_ID0_15cm_A4.pdf`; 10 cm sayfası SİLİNDİ), köşe yerleşimi 8/8 → **11/11 cm**
(15 cm işaretin sessiz bölgesi 8 cm'lik merkezde duvardan taşardı), hedef düzlemi **tabandan 5 cm**
(`hedef_duzlem_eksen: "Y"`, `hedef_duzlem_cm: -20.0`).

> ⚠️ **ÖLÇÜLDÜ: tabandan 5 cm de mevcut kamera konumuyla YETMİYOR.** Gerçek ArUco'lu fotoğrafta
> kuyu (−48,3 · −20,0 · **+445,4**) cm çıkıyor = kabin dışı; `Y = 0` (kabin ortası) ve eski dikey
> düzlem sağlam. Sebep aynı: kamera lensi taban hizasında (Y = −25), 5 cm'lik yükseklik ışını hâlâ
> sığ açıyla kesiyor. Bu yüzden bayrak 0 kalıyor ve aşağıdaki adım 4 bir SEÇİM gerektiriyor.

**Yapılacak ölçüm (seçenekler ve tablo: `ai_hub/KABIN_KURULUM_KILAVUZU.md` §0.5):**
1. Kabin işaretini (15 cm, A4 ArUco) arka duvara DÜZ ve duvara PARALEL yapıştır (merkez sol
   duvardan 11 cm, tavandan 11 cm). YAPIŞTIRDIKTAN SONRA CETVELLE ÖLÇ ve gerçek değeri yaz:
   `qr_to_origin_cm = [32.5 - a, -(25 - b), -25]` (a = sol duvardan, b = tavandan cm);
   `to_marker_cm`i de yeniden hesapla (kapı: tests/test_kabin_config_65x50x50.py).
2. Hedef tepsisinin yüksekliğini ölç ve `hedef_duzlem_eksen: "Y"` + `hedef_duzlem_cm: <ölçülen>`
   yaz (varsayılan hâlâ eski davranış: `"Z"` / 0,0 — AI Hub tek-foto analizi bozulmasın diye).
3. Kabinde bilinen bir noktaya (ör. tepsi merkezinden 10 cm sağa) hedef koy; Kontrol → AI Pro →
   Hazırlığı Başlat ile önizlemede okunan **Konum (mm)** değerini şeritten oku. KABUL: okunan
   koordinat elle ölçülen konumla ±2 cm içinde ve kabin sınırları içinde.
4. Fantom için: fantomu modelin eğitim aralığına (kabin ortasına) yükseltmek mi, kamerayı üst
   köşeye taşımak mı — karar ölçüme göre verilir. Kamera taşınırsa **kedi akışı yeniden
   doğrulanmalıdır** (aynı kamera onu da besliyor).
5. Ölçüm kabul edilirse `PEMF_ARASTIRMA_AIPRO=1` yapılır (kurulum bunu NSSM servis ortamına yazar;
   backend `.env`i KENDİ okumaz). Doğrulama: `GET /api/ai/hazirlik?derin=1` yanıtında
   `arastirmaAiPro.acik == true`.

**Kabul kriterleri (bayrak açıldıktan sonra, bobinler BAĞLI):**
  · Hazırlık şeridi özneyi bulur ("fantom/petri plakası aranıyor" → "konumlandı").
  · 3B rozet "kabin işaretiyle doğrulandı ✓" der; işaret kadrajdan çıkarılınca öneri ÜRETİLMEZ
    (güven tavanı 0,25 < eşik 0,3) ve şerit sebebi söyler.
  · Onay ekranı: Hedef adı, Konum (mm), göreli alan (hedefte/çevrede), süre, 7/7 bobin.
  · Onayla → seans başlar; hedef kadrajdan çıkarılınca ~30 sn içinde bobinler DURUR ve şerit
    "hedef görülmüyor" der; hedef geri konunca sürüş kendiliğinden devam eder.
  · ACİL DURDUR her aşamada bobinleri durdurur (seans tipinden bağımsız).

**Kod-düzeyi kilitler (bunlar tezgâhın YERİNE GEÇMEZ):** tests/test_ai_pro_arastirma_bayragi.py ·
test_ai_pro_arastirma_saglayicilari.py · test_ai_pro_arastirma_gercek_pipeline.py ·
test_ai_pro_frame_arastirma.py · test_koordinat_donusumu_karakterizasyon.py ·
test_ai_pro_arayuz_profil_tablosu.py (hepsi mutasyonla doğrulandı).

---

## ⏳ 16 — STM REFLASH (DDS simetrik bipolar) + DOZ YENİDEN KALİBRASYONU  ·  **B3**

> **Neden zorunlu:** HG-2 düzeltmesiyle STM sürüş dalgası **asimetrik DC-bias'lıdan simetrik
> bipolara** çevrildi (`356d576`). Aynı `duty` değeri artık **farklı bir alan** üretiyor —
> sahadaki cihazın doz eğrisi bu yüzden **kalibre DEĞİL**. Reflash yapılmadan cihaz eski
> firmware'i koşmaya devam eder; reflash yapılıp kalibrasyon yapılmazsa arayüzdeki mT değeri
> ile gerçek alan ayrışır.

### 16.1 — Yakılabilir çıktı (CubeIDE AÇMADAN)

⚠️ **CubeIDE'de "Generate Code" `main.c`i EZER** (`docs/PEMF_SISTEM_RAPORU`/bellek kaydı).
Bu yüzden reflash için CubeIDE'yi hiç açmayın; depodan üretilen ikiliyi yakın:

```powershell
python scripts\firmware_derle.py --stm --cikti firmware_cikti
```

Betik derler, `_printf_float` bağını doğrular (⚠️ bağlı değilse TÜM telemetri sessizce ölür —
bkz. bellek `pemf-stm-printf-float-sessiz-sensor-olumu`) ve şunları üretir:

| Dosya | Kullanım |
|---|---|
| `pemf.bin` | STM32CubeProgrammer → **adres `0x08000000`** |
| `pemf.hex` | CubeProgrammer / ST-Link Utility (adres dosyanın içinde) |
| `pemf.elf` | Hata ayıklama / sembol |

Betik her dosyanın **SHA256**'sını basar. Yaktığınız dosyanın özetini aşağıya yazın — bu,
"sahadaki cihazda depodaki kaynak mı koşuyor" sorusunun tek kanıtıdır.

**Yakma (CubeProgrammer):** ST-LINK → Connect → Erase & Program → `pemf.bin`, `0x08000000`,
"Verify programming" **işaretli** → Start. Sonra **Disconnect + karta güç döngüsü**.

### 16.2 — Reflash sonrası ilk kontrol (kalibrasyondan ÖNCE)

1. Backend'i simülatörsüz çalıştır (`PEMF_SIMULATE` **YOK**).
2. `GET /api/coil/7` → `transport` **`stm32`** olmalı (ESP değil).
3. Bobin 1'i kısa sür: `POST /api/coil/1/control {"freq":10,"duty":50,"duration":5,"start":true}`.
4. ⚠️ **TELEMETRİ KAPISI:** gelen `STM_TELE` satırında `B=`, `T=`, `I=` alanları **sayılı**
   olmalı. Boşsa (`B=,T=,A=,I=`) firmware'de `_printf_float` bağlanmamıştır — **kalibrasyona
   başlamayın**, o hâlde ölçeceğiniz her şey sıfırdır.

### 16.3 — Doz eğrisi (asıl iş)

> ⚠️ **DÜZELTME (2026-09-13) — `measuredPeakMt` KULLANMAYIN.**
> Bu bölüm ilk yazımında ölçümü `measuredPeakMt` üzerinden tarif ediyordu. **YANLIŞTI.**
> `measuredPeakMt` = seans boyu en büyük **|B|**, yani *işaretsiz tepe BÜYÜKLÜĞÜ* — ve
> firmware'in kendi notu bunu açıkça söylüyor (`main.c:1083`): *"`B=` tepe BÜYÜKLÜKTÜR ve
> işaretsiz olduğu için unipolar (0→+B) ile bipolari (−B→+B) AYNI gösterir"*. **Yakındaki
> sabit bir DC alan bu değeri SAPTIRIR.**
>
> Sahada ölçüldü (S3 reflash sonrası, bobinler boşta):
> `[MagChk] ilk-bosta-pencere |B|=0.589 mT (X:-0.037 Y:-0.502 Z:0.305)` → dünya alanının
> (~47 µT) **12,5 katı**, üst eşiğin (150 µT) **3,9 katı**. Yani o sensörün yanında
> demir/mıknatıs var ve |B| tabanlı her okuma bu kadar kayar.
>
> **Doğrusu: TEPEDEN-TEPEYE.** İşaretli uçlardan türetilir ve ofset farkta sadeleşir:
> `pp_x = XP − XN`, `pp_y = YP − YN`, `pp_z = ZP − ZN`.
> Bu alanlar STM_TELE'de yayınlanıyor ve backend ayrıştırıcısında `mag_x_min` / `mag_x_max` …
> olarak ZATEN çözülüyor (`headless_core._parse_stm_tele`).

Ölçüm, bobin başına **tepeden-tepeye** değerle yapılır (yukarıdaki not). Aralık ±24,6 mT'ye
açıldı — eski ayar 4,92 mT'de sessizce sarıyordu (bellek `pemf-manyetik-zirve-ve-aralik`).

Her bobin için (1-7), sabit `freq = 10 Hz`, prob bobin merkezinde ve **sabit mesafede**:

| duty (%) | pp_x (mT) | pp_y (mT) | pp_z (mT) | Not |
|---|---|---|---|---|
| 10 | | | | |
| 25 | | | | ⚠️ eski firmware'de burada −%50·V DC bias vardı |
| 50 | | | | tek "eski = yeni" noktası |
| 75 | | | | |
| 90 | | | | |

**Kabul ölçütü:**

1. Eğri **monoton artan** olmalı (duty büyürken pp küçülmemeli).
2. Aynı bobinin üç ekseni **birbiriyle tutarlı** ölçeklenmeli: duty iki katına çıkınca
   pp_x/pp_y/pp_z oranları kabaca korunmalı. Korunmuyorsa prob KAYMIŞTIR — ölçümü
   tekrarlayın, eğriyi yazmayın.

> ⚠️ **ESKİ ÖLÇÜMLE DOĞRUDAN KIYASLAMAYIN.** Bu bölüm bir ara sürümde *"duty=%50'de eski
> ölçümle ±%10 içinde olmalı"* diyordu — **yanlıştı ve kaldırıldı.** Eski kayıtlar `|B|`
> (işaretsiz tepe büyüklüğü) cinsindendi; buradaki değerler **tepeden-tepeye**. Simetrik
> bipolar bir dalgada `pp ≈ 2 × |B|tepe`, üstelik eski `|B|` kayıtları yakındaki DC ofsetle
> de kaymıştı. İki birimi ±%10 diye kıyaslamak uydurma bir kabul ölçütü üretirdi.
> Elinizde ESKİ bir **pp** kaydı varsa onunla kıyaslayabilirsiniz; `|B|` kaydıyla kıyaslamayın.

⚠️ **SARMA KONTROLÜ:** sarma sınırı **ham eksen uçları** (`XP`, `XN`, …) içindir: bunlardan
biri **±24,6 mT**'ye dayanıyorsa değer sarmış olabilir. ⚠️ `pp` değerinin kendisine bakmayın —
simetrik bir dalgada pp, tek eksen sınırının **iki katına** kadar çıkabilir (≈49 mT) ve sınıra
dayanmadan da geçerlidir. Şüpheli satırı geçersiz sayın, probu uzaklaştırıp tekrarlayın.
Sarma tespit EDİLEMEZ — tek savunma aralığın kendisidir.

### 16.4 — Kayıt (güvenlik dosyası)

Şunlar yazılmadan kalibrasyon tamamlanmış sayılmaz:

- Yakılan dosyanın **SHA256**'sı + yakma tarihi
- 7 bobin × 5 duty tablosu (yukarıdaki)
- Prob tipi ve mesafesi (mm) — tekrarlanabilirliğin tek koşulu
- `_printf_float` kapısının **geçtiği** (16.2 adım 4)

> ⚠️ Bu ölçüm yapılmadan arayüzdeki "Yoğunluk (mT)" değeri **hedef** değeri gösterir, ölçülen
> alanı değil. Klinik kararı ona dayandırmayın.

---

## ✅ 17 — Donmuş EXE ürün senaryoları (BU ORTAMDA DOĞRULANDI · 2026-09-17)

**Betik:** `scripts/urun_senaryolari.py` · **Kapısı:** `tests/test_urun_senaryolari_kapisi.py`

### Neden test suiti yetmiyor

2026-09-13'te birim testler **yeşilken** ürün hasta geçmişini kaybediyordu: üçüncü bir yol
(şablon kopyalayıcı) açılışta önce davranıyordu ve hiçbir test o **sırayı** görmüyordu.
Suit "fonksiyon doğru mu" diye sorar; bu betik **"sevk edilen ikili, gerçek diskte, gerçek
açılış sırasıyla doğru mu"** diye sorar. İkisi ayrı sorulardır ve biri ötekinin yerine geçmez.

Aynı ders 2026-09-16/17 denetim turunda ikinci kez alındı: denetimin 13 iddiasından 10'u
**ölçüt yerine görünüşe** dayandığı için yanlış çıktı. Bu yüzden burada hiçbir madde kaynaktan
okunarak "doğrulanmış" sayılmaz.

### Nasıl çalıştırılır

```bash
# önce paketle (EXE bayatsa betik zaten DURUR)
pwsh -NoProfile -File scripts/build_backend_exe.ps1

python scripts/urun_senaryolari.py HEPSI          # 48 senaryo
python scripts/urun_senaryolari.py A              # yalnız veri yolu
python scripts/urun_senaryolari.py C --exe <yol>  # başka bir paketi ölç
```

⚠️ Betik **bayat-ikili nöbetiyle** başlar: EXE izlenen kaynaklardan eskiyse ölçüm anlamsızdır
ve çalışma **durur**. Çalışma alanı depo ağacının dışındadır (senaryolar ACL-kilitli ve bozuk
dosyalar üretir). Makine anahtar deposu koşum öncesi/sonrası karşılaştırılır — ürün oraya
yazsaydı sahibin gerçek anahtarını ezme sınıfı doğardı; **yazmadı**.

### Gruplar ve korudukları

| Grup | Senaryo | Ne koruyor |
|---|---|---|
| **A** veri yolu | 16 | Düz→SQLCipher göçü (iki DB), **yarım göç kurtarması**, ACL-kilitli yedekten kurtarma, emanet politikası, idempotans, uçtan uca kalıcılık, bayat `.enc.tmp` artığı |
| **B** ürün yüzeyi | 15 | Ana React arayüzü + simülatör **gerçekten sunuluyor**, önbellek politikası, derin AI hazırlığı, kod koruması, çalışma-anı pip yasağı, araştırma AI Pro 409 kapısı, rota yüzeyinde ölü girdi yok |
| **C** güvenlik | 13 | Jeton zorlaması **E-stop/seans durdurmayı asla kapılamaz**, auth tünelde zorunlu–yerelde serbest, sağlık ucu launcher nonce'unu/cihaz kimliğini **tünele sızdırmaz** |
| **D** bozuk sır dosyası | 4 | `pemf_secrets.json` bozuksa **yeni anahtar ÜRETİLMEZ** (üretilse tüm şifreli tıbbi kayıt kalıcı okunamaz olurdu), karantina kanıtı kalıcıdır, operatörün çıkış yolu açıktır |

### Ölçülen sonuç (2026-09-17, EXE 15:16, 1.9.50)

**48/48 geçti.** Öne çıkanlar:

- **Yarım göç üründe toparlanıyor:** `db` YOK + `.plain.bak` VAR halinde backend ayağa kalkıyor,
  DB geri geliyor ve SQLCipher'a göçüyor. **Yedek ACL-KİLİTLİYKEN de** toparlanıyor — 2026-09-13
  saha arızasının tam sınıfı.
- **Tek bayrak artık iki DB'yi birden yönetiyor:** `PEMF_KEEP_PLAIN_BACKUP=1` hem hasta hem
  tedavi yedeğini emanete alıyor; eski ad `PEMF_KEEP_PLAIN_BAK` hâlâ onurlandırılıyor **ve iki
  DB için de ayrı ayrı uyarı veriyor**. (A1 öncesi bu bayrak yalnız bir tarafı etkiliyordu.)
- **Göç veriyi taşıyor:** "SQLCipher başlığı" yetmez — göç sonrası kayıt ürünün kendi API'sinden
  okundu.
- **Bozuk sır dosyası fail-closed:** yeni anahtar üretilmiyor, bozuk kopya karantinaya alınıyor,
  dosya silinse bile karantina kanıtı kararı sürdürüyor; kanıt kaldırılınca cihaz normal açılıyor.

### ⚠️ Bu koşumda ÜRÜN DEĞİL ÖLÇÜM ARACI yanlış çıktı (5 kez)

Kayda geçiyor çünkü aynı tuzak tekrar edecek:

| Belirti | Gerçek sebep |
|---|---|
| "Ana arayüz varlık sunmuyor" | Desen `/assets/` (Vite) aranıyordu; ürün **Expo** paketi, varlıklar `/_expo/static/...` |
| "XAI zinciri çözülmüyor" | `em_ref_stats_eksik: []` (boş liste = **iyi haber**) `all()` ile kırmızı yapıyordu |
| "Emanet log'u yok" | Backend `logs/backend_service.log`a yazıyor; yalnız stdout'a bakılmıştı |
| "buildId boş" | `get_build_id()` launcher'sız açılışta **bilerek** boş döner — uydurma değer üretmez |
| "Şema patladı" | `.plain.bak` elde uydurulmuş oyuncak şemayla kurulmuştu; şema **ürüne üretilir** |

**Kural:** bir senaryo kırmızı döndüğünde önce *"ölçüm doğru yerde mi bakıyor"* sorulur; ürün
suçlanmadan önce ölçüm aracı kanıtlanır.

### Takımın kendi kapısı

`tests/test_urun_senaryolari_kapisi.py` (8 test, hepsi mutasyonla kırmızı görüldü) betiği
**koşturmaz** — CI'da EXE yoktur. Koruduğu şey takımın güvenilirliği: senaryo sayısının sessizce
küçülmemesi, **karşıt-kanıt** senaryolarının (A0 · B9b · C0 · C9) durması, bayat-ikili nöbetinin
`main`'den çağrılması ve bayatlıkta gerçekten **durması**, senaryo kodlarının benzersizliği,
sabit kullanıcı yolu bulunmaması, çalışma alanının depo ağacının dışında kalması.

> ⚠️ Karşıt-kanıt senaryoları neden zorunlu: C1–C4 "jeton zorlaması açıkken E-stop kapılanmıyor"
> der. Jeton kapısı **hiç çalışmasaydı** da aynı yeşili verirlerdi. C0 (kapı ücretli analizi
> gerçekten 402 ile reddediyor) olmadan o dördü hiçbir şey kanıtlamaz.
