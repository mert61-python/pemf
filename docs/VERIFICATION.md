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
