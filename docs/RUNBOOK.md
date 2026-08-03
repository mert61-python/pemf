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
| **Kötü güncelleme sonrası sorun** | **Rollback**: `curl -X POST http://127.0.0.1:8000/api/update/rollback` (previousStable'a döner, SHA256+aktif-tedavi kontrollü). Bkz. DEPLOYMENT.md. |
| **Disk dolu / yedek** | `<data>\backups\` günlük şifreli yedek (son 14) + `kurtarma-zarfi.enc`. `PEMF_BACKUP_DIR` set ise off-machine kopya. |

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
   `pemf_patients_<tarih>.db` → `pemf_patients.db`
4. Servisi başlat.

**Kod kaybolursa** yedekler yalnız orijinal makinede açılır. Kod, kaybı geri alınamaz tek şeydir.

## Güvenli kapanış
Servis durdurulunca backend tüm bobinlere STOP gönderir (STM kuyruğu boşalana kadar bekler + ESP MQTT stop). Elle acil-durdur: `curl -X POST http://127.0.0.1:8000/api/hardware/emergency_stop` (auth-muaf, fail-safe).

## Gözlemlenebilirlik
- Metrikler: `/metrics` (Prometheus scrape; LAN-muaf). Sağlık: `/api/health`.
- Uzak hata-izleme (opsiyonel): `PEMF_SENTRY_DSN` set → Sentry (PII-scrub). Varsayılan kapalı (KVKK).
