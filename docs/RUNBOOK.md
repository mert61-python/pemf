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
| **Disk dolu / yedek** | `<data>\backups\` günlük şifreli yedek (son 14). `PEMF_BACKUP_DIR` set ise off-machine kopya. |

## Anahtar / veri kurtarma (KRİTİK)
- **SQLCipher anahtarı** `<data>\PEMF_GUI\.sqlcipher_key` (+ keyring). **KAYBI = şifreli hasta verisi KALICI OKUNAMAZ.** Kurulumda YEDEKLEYİN (güvenli, off-machine). ACL: yalnız SYSTEM+Administrators.
- **Yedekten dönüş**: servisi durdur → `<data>\backups\pemf_*_YYYYMMDD.db` dosyasını aktif DB üzerine kopyala (aynı anahtarla şifreli) → servisi başlat.
- Sırlar tek dosyada: `<data>\PEMF_GUI\pemf_secrets.json` (kripto anahtarları DPAPI'li).

## Güvenli kapanış
Servis durdurulunca backend tüm bobinlere STOP gönderir (STM kuyruğu boşalana kadar bekler + ESP MQTT stop). Elle acil-durdur: `curl -X POST http://127.0.0.1:8000/api/hardware/emergency_stop` (auth-muaf, fail-safe).

## Gözlemlenebilirlik
- Metrikler: `/metrics` (Prometheus scrape; LAN-muaf). Sağlık: `/api/health`.
- Uzak hata-izleme (opsiyonel): `PEMF_SENTRY_DSN` set → Sentry (PII-scrub). Varsayılan kapalı (KVKK).
