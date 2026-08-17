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

## ⏳ 9 — firmware `[FIX-1c]` duty geçişi (DONANIM BENCH · **YAYIN ÖNCESİ ZORUNLU**)

**Neyi doğrulayacağız.** Denetim (2026-08-17) enerjili bir bobinin frekansı **ARTIRILDIĞINDA**
duty tick'inin bayat kaldığını buldu: `g_tpp` yeni (küçük) periyoda göre yazılıyor ama
`g_duty_ticks` eski (büyük) periyottan kalıyor → ~1 sn tek-polarite ve istenen dozun 4,78×'ine
kadar on-time. Düzeltme `firmware/main.c` içindeki `[FIX-1c]` bloğu: duty tick'i eski/yeni periyot
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
