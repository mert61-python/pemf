# PEMF Backend — Operasyon Runbook (audit B-11.2)

Saha olay-müdahale rehberi. Klinik PC = Windows, servis `PemfBackend` (NSSM), LocalSystem.
Veri kökü genelde `C:\ProgramData\PEMF_System\PEMF_GUI` (`PEMF_DATA_DIR`).

## Hızlı komutlar (Yönetici PowerShell)

```powershell
# Servis durumu / yeniden başlat / durdur
Get-Service PemfBackend
nssm restart PemfBackend      # veya: Restart-Service PemfBackend
nssm stop PemfBackend

# Sağlık + sürüm + şifreleme durumu
curl http://127.0.0.1:8000/api/health        # atRestEncrypted, pairingCode, tunnelUrl
curl http://127.0.0.1:8000/metrics           # Prometheus metrikleri

# Loglar (döndürmeli, 10MB×5) + çökme kaydı
Get-Content C:\ProgramData\PEMF_System\logs\backend_service.log -Tail 100 -Wait
Get-Content C:\ProgramData\PEMF_System\logs\crash.log -Tail 50
```

## Destek paketi (teşhis için TEK dosya)

Klinikten log istemek yerine **PII maskelenmiş tek bir zip** üretin:

```powershell
# Backend ayaktaysa (tercih edilen — hasta adları GERÇEKTEN maskelenir):
curl -X POST http://127.0.0.1:8000/api/support/bundle   # base64 zip + OZET.json

# Backend çökmüşse:
python tools\destek_paketi.py            # Masaüstüne yazar
```

İçinde: sağlık/sürüm özeti (`buildId` dâhil), log kuyrukları, denetim izi **sayım** özeti.
İçinde **YOK**: `pemf_secrets.json`, `.sqlcipher_key`, veritabanları, `kurtarma-zarfi.enc`.

⚠️ `OZET.json` içinde **UYARI** alanı varsa: şifreli veritabanı açılamamış demektir; o durumda
hasta adları maskelenmemiş olabilir — göndermeden önce `logs/` içeriğine bakın.

## Denetim izi (kim, ne zaman, kaç kayıt)

Geri dönüşsüz işlemler (toplu silme, dışa/içe aktarma, operatör ekleme-çıkarma, PII maskeleme)
şifreli DB içinde **ekleme-only** `audit_events` tablosuna yazılır — **silinemez, değiştirilemez**.

```powershell
curl http://127.0.0.1:8000/api/audit/events?limit=50
curl "http://127.0.0.1:8000/api/audit/events?event_type=ai_log.delete_all"
```

"Kayıtlarım kayboldu" çağrısında ilk bakılacak yer burasıdır.

## Log yerleri
- Servis logu: `<PEMF_LOG_DIR>\backend_service.log` (döndürmeli). `PEMF_LOG_JSON=1` → JSON.
- Çökme: `<PEMF_LOG_DIR>\crash.log` (yakalanmamış istisna + thread crash).
- NSSM stdout/stderr: NSSM yapılandırmasındaki yönlendirme.

## Olay senaryoları

| Belirti | Kontrol / Çözüm |
|---|---|
| **Mobil bağlanmıyor (LAN)** | Firewall TCP 8000 + UDP mDNS; aynı subnet? `/api/health` yerelden 200 mü? |
| **Mobil bağlanmıyor (uzak)** | `/api/health` → `tunnelUrl` dolu mu? cloudflared çalışıyor mu? `PEMF_ENABLE_TUNNEL=1`? Token istemcide var mı (401)? |
| **"Eksik API anahtarı" (401)** | LAN'da olmamalı (muaf). Uzakta: mobil bir kez LAN'a girip token çeksin (`/api/auth/token`) veya 6-haneli pairing kodu. |
| **MQTT/ESP bobinleri ölü** | `Get-Service mosquitto` Running? `curl /api/gateway/status`. Hotspot aktif mi (device modunda logon-task)? |
| **STM bobinleri ölü** | `PEMF_STM_PORT=auto` ST-Link'i buldu mu? Sürücü? `/api/health` → `stmConnected`. |
| **atRestEncrypted=false (beklenmedik)** | `PEMF_ENCRYPT_AT_REST=1` set mi? sqlcipher3 wheel EXE'de mi? Anahtar (`.sqlcipher_key`/keyring) okunuyor mu? PatientDB fail-closed → başlatma reddeder. |
| **Kötü güncelleme sonrası sorun** | Aşağıdaki **"Kötü güncelleme"** bölümüne bakın. ⚠️ `/api/update/rollback` **KULLANMAYIN** — o uç eski (kapatılmış) EXE kanalına aittir ve hiçbir şey yapmaz. |
| **Disk dolu / yedek** | `<data>\backups\` günlük şifreli yedek (son 14) + `kurtarma-zarfi.enc`. `PEMF_BACKUP_DIR` set ise off-machine kopya. |

## Kötü güncelleme (TEK KANAL: launcher)

Cihaz yazılımını **yalnız PEMF Vet Client (launcher)** günceller. Backend'in eski
`/api/update/*` uçları kapatılmıştır (`PEMF_LEGACY_EXE_UPDATE` ile açılmadıkça); `exe/latest.json`
kanalı yayında değil, `previousStable` hiç dolmaz → **`/api/update/rollback` hiçbir şey yapmaz.**

**Klinikte (tek cihaz):**
1. Launcher zaten **sağlık kapılı**dır: yeni sürüm açılışta sağlıklı cevap vermezse eskisine
   kendi döner (`runtime.old` / `app.yedek`), paket kimliğini kaydetmez, sonraki açılışta
   önbellekten tekrar dener (**yeniden indirme yok**).
2. Sorun sağlık kapısından geçtiyse (servis ayakta ama davranış bozuk) klinikte geri alma
   **yoktur** — kurtarma yayıncı tarafındadır (aşağıya bakın). Bu arada cihazı çalışır tutmak
   için: seansı bitirin, gerekiyorsa `nssm stop PemfBackend` ile durdurun (bobinlere önce STOP
   gider) ve yayıncıyı arayın.
3. Teşhis için `runtime.bozuk` dizini varsa **silmeyin** — başarısız sürüm oradadır.

**Yayıncı tarafı (`scripts/make_manifest.py`):**

| Amaç | Bayrak | Etkisi |
|---|---|---|
| Yeni dağıtımı durdur | `--rollout 0` | Yalnız **henüz almamış** cihazlar korunur; sahadaki bozuk kurulum OLDUĞU GİBİ KALIR. |
| Sahayı zorla ilerlet (**geri çağırma**) | `--min-supported-version X.Y.Z` | Kurulu sürümü eşiğin **altında** olan her cihaz, `rollout` frenine **bakılmaksızın** güncellenir. Sürümünü söyleyemeyen kurulum da kapsama girer (fail-safe). |
| Launcher'ın kendi güncellemesini durdur | `--launcher-rollout 0` | Launcher self-update'i durur. |

⚠️ Geri çağırma **ileri** yönlüdür: düzeltilmiş bir sürüm yayınlayıp eşiği ona çekersiniz.
Eski pakete geri döndürmek için manifest'i eski paketin sha'sına yazmak gerekir; sürüm
monotonluğu olmadığı için bu **bilinçli** bir işlemdir ve yayın kaydına yazılmalıdır.

## Anahtar / veri kurtarma (KRİTİK)
- **SQLCipher anahtarı** `<data>\PEMF_GUI\.sqlcipher_key` (+ keyring). **KAYBI = şifreli hasta verisi KALICI OKUNAMAZ.** ACL: yalnız SYSTEM+Administrators.
- Sırlar tek dosyada: `<data>\PEMF_GUI\pemf_secrets.json` (kripto anahtarları DPAPI'li).
- **Aynı makinede yedekten dönüş**: servisi durdur → `<data>\backups\pemf_*_YYYYMMDD.db` dosyasını aktif DB üzerine kopyala (aynı anahtarla şifreli) → servisi başlat.

### Kurtarma kodu — donanım arızası / makine değişimi
Kripto anahtarları DPAPI `CRYPTPROTECT_LOCAL_MACHINE` ile **makineye bağlıdır**. Bu nedenle
anakart/disk arızasından ya da Windows yeniden kurulumundan sonra yedekler — off-site kopya
dahil — tek başına **açılamaz**. Bunun için kurulum bir kez **150-bit kurtarma kodu** üretir:

| | |
|---|---|
| **Kod nerede** | `<data>\PEMF_GUI\KURTARMA-KODU.txt` (ilk yedekte oluşur). **Operatör bunu makine dışına almalı** — kasa / parola yöneticisi. Aldıktan sonra dosya silinebilir. |
| **Zarf nerede** | `<data>\backups\kurtarma-zarfi.enc` ve `PEMF_BACKUP_DIR` set ise off-site kopyada. İçinde `sqlcipher_key` + `patient_fernet_key`, koddan scrypt ile türetilen anahtarla şifreli. |
| **Kodu görüntüle** | `python tools\kurtarma.py --kodu-goster` (cihaz hâlâ çalışırken) |

**Kod ve zarf ASLA aynı yerde durmamalı** — zarfın tüm koruması buna dayanır. Kod dosyası
yedek dizinine kopyalanmaz; regresyon testiyle kilitlidir.

**Yeni makinede geri yükleme:**
1. PEMF'i kur, **servisi henüz BAŞLATMA** (başlatırsan yeni bir `sqlcipher_key` üretilir ve yedekler açılmaz).
2. `python tools\kurtarma.py --zarf <yedek>\kurtarma-zarfi.enc --kod <KOD> --yaz`
   Makinede zaten anahtar varsa araç **durur** (üzerine yazmak mevcut şifreli veriyi kalıcı kaybettirir);
   gerçekten taze kurulumsa `PEMF_KURTARMA_USTUNE_YAZ=1` ile zorla.
3. En yeni yedeği kopyala: `pemf_treatment_history_<tarih>.db` → `pemf_treatment_history.db`,
   `pemf_patients_<tarih>.db` → `patients.db`  ← ⚠️ hedef ad `patients.db`; uygulama
   `pemf_patients.db` adını **hiç açmaz** (yedek dosya ön-eki ile karıştırmayın)
4. Servisi başlat.

**Kod kaybolursa** yedekler yalnız orijinal makinede açılır. Kod, kaybı geri alınamaz tek şeydir.

## Güvenli kapanış
Servis durdurulunca backend tüm bobinlere STOP gönderir (STM kuyruğu boşalana kadar bekler + ESP MQTT stop). Elle acil-durdur: `curl -X POST http://127.0.0.1:8000/api/hardware/emergency_stop` (auth-muaf, fail-safe).

## Gözlemlenebilirlik
- Metrikler: `/metrics` (Prometheus scrape; LAN-muaf). Sağlık: `/api/health`.
- Uzak hata-izleme (opsiyonel): `PEMF_SENTRY_DSN` set → Sentry (PII-scrub). Varsayılan kapalı (KVKK).
