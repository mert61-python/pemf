# PEMF Headless Backend — Dağıtım Runbook'u (Faz 3–7)

> 24/7 sunucuda (Windows) **arayüzsüz** PEMF backend'i kurma, mühürleme ve test
> kılavuzu. Tüm kontrol React/Expo (Web + APK/iOS) üzerinden; backend FastAPI +
> WebSocket + MQTT + STM32 ile çalışır. GUI yoktur (bkz. [LEGACY_GUI.md](LEGACY_GUI.md)).

## Mimari (özet)

```
┌──────────────┐   REST /api/*           ┌─────────────────────────────┐   USB seri   ┌────────┐
│ React/Expo   │◄──────────────────────► │  PEMF_Backend (FastAPI:8000) │◄───────────►│ STM32  │
│ Web/APK/iOS  │   WebSocket /ws         │  + EventBus (saf Python)     │             └────────┘
└──────────────┘                         │  + MQTT dinleyici            │   MQTT 1883  ┌────────┐
        ▲   mDNS / UDP 5051 / QR / tunnel │                             │◄───────────►│ ESP32  │
        └────────────────────────────────│  Mosquitto (ayrı servis)    │             └────────┘
                                          └─────────────────────────────┘
```

İki Windows servisi: **`mosquitto`** (broker) ← **`PemfBackend`** (ona `depends`).

---

## Önkoşullar

| | Build makinesi | Hedef 24/7 sunucu |
|---|---|---|
| OS | Windows | Windows 10/11 |
| Python | **Tam CPython 3.10** (PyInstaller için) | gerekmez (EXE self-contained) |
| Yetki | — | **Administrator** |
| Donanım | — | STM32 USB (COM portu), ağ |

> EXE'yi bir kez build makinesinde üretirsiniz; hedefte Python kurulu olmasına
> gerek yoktur. Build ve hedef aynı makineyse de sorun yok.

---

## Adım 0 — Qt-free doğrulaması (her zaman önce)

```powershell
python scripts\check_headless_imports.py
```
`SONUÇ: YEŞİL (startup Qt-free)` görmelisiniz. **KIRMIZI ise** biri backend'e Qt
importu sızdırmış — build etmeyin, önce düzeltin. (build_backend_exe.ps1 bunu
otomatik çalıştırır ve KIRMIZI'da durur.)

## Adım 1 — Frontend'i derle (Faz 6)

```powershell
cd frontend
npm install
npx expo export --platform web --output-dir dist
cd ..
```
Çıktı `frontend\dist\` → PyInstaller spec bunu EXE içine gömer ve FastAPI `/`
kökünden servis eder. (COOP/COEP header'ları SharedArrayBuffer/SQLite için zaten ayarlı.)

## Adım 2 — Backend EXE'sini build et (Faz 4)

```powershell
.\scripts\build_backend_exe.ps1
```
Sıra: guard-check (YEŞİL şart) → mevcut `myenv`/embeddable Python (fresh venv KURMAZ,
indirme yok) → PyInstaller. `PYTHONNOUSERSITE=1` izolasyon + `C:\PEMF_BUILD` kısa yola
build (Windows 260-karakter sınırı). Çıktı: `C:\PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe`.
Hızlı test:
```powershell
C:\PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe --port 8000
# Başka terminal: http://localhost:8000  ve  http://localhost:8000/api/health
```

## Adım 2.5 — (ALTERNATİF) Tek-tık installer ⭐

Manuel servis kurulumu (Adım 3-4) yerine her şeyi paketleyen Inno Setup installer:

```powershell
# Build çıktısını guii\dist\PEMF_Backend'e koy (installer .iss oradan okur):
Copy-Item C:\PEMF_BUILD\dist\PEMF_Backend guii\dist\PEMF_Backend -Recurse -Force
# Derle (Inno Setup 6 gerekir):
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build_tools\PEMF_Backend_Setup.iss
```
Çıktı: `build_tools\Output\PEMFBackendSetup_v1.4.0.exe`. Hedefte **admin** ile çalıştır:
- Mosquitto + Backend Windows servislerini otomatik kurar ([setup_services.ps1](scripts/setup_services.ps1)),
- VC++ redist + firewall (1883/8000/5051) yapar, `http://localhost:8000`'i tarayıcıda açar.
- **Kaldırma:** Denetim Masası → "PEMF Medical Backend" → servisleri de temizler.

Bu yolu seçersen **Adım 3-4'ü ATLA**.

## Adım 3 — Mosquitto'yu servis yap (Faz 3) — *Yönetici PowerShell*

```powershell
.\scripts\install_mosquitto_service.ps1
```
Bundle'daki `bin\mosquitto\` ile offline kurar; otomatik başlatma + çökme-restart +
firewall (1883). `services.msc` → `mosquitto` = Running olmalı.

## Adım 4 — Backend'i servis yap (Faz 5) — *Yönetici PowerShell*

```powershell
.\scripts\install_backend_service.ps1
```
Frozen EXE'yi bulursa onu, yoksa python+script'i NSSM ile kurar. `PemfBackend`
servisi `mosquitto`'ya **depends** ile bağlanır; broker'ı kendi başlatmaz
(`--no-mosquitto-ensure`, sadece izler). Çökerse 5 sn'de otomatik restart.

> **Açılış sırası:** Windows önce `mosquitto`'yu, sonra `PemfBackend`'i başlatır.

---

## Frontend bağlantı matrisi (Faz 6)

| İstemci | Backend adresi | Konfig |
|---|---|---|
| **Sunucu Web** (aynı makine tarayıcı) | `http://localhost:8000` | Sıfır konfig — `window.location.origin` |
| **Aynı Wi-Fi mobil** (APK/iOS) | otomatik bulunur | mDNS + UDP 5051 + `/api/health` subnet tarama + QR |
| **Uzak mobil** | Cloudflare tunnel URL | `/api/qr` ile QR tara, veya Ayarlar'da elle gir |
| Elle | `http://<ip>:8000` veya `https://...trycloudflare.com` | Ayarlar → kaydedilir (`@pemf_server_address`) |

Override (build zamanı): `EXPO_PUBLIC_PEMF_API_BASE_URL`, `EXPO_PUBLIC_PEMF_WS_URL`.

---

## Adım 5 — Doğrulama & 24/7 dayanıklılık testi (Faz 7)

**Smoke (servis ayakta):**
```powershell
Invoke-RestMethod http://localhost:8000/api/health        # status: online, stmConnected
Invoke-RestMethod http://localhost:8000/api/gateway/status # mqtt/broker durumu
```
- [ ] React Web `/` açılıyor, canlı veri (WebSocket `/ws` snapshot) geliyor
- [ ] STM32 takılı → `/api/health` `stmConnected: true`
- [ ] Bobin komutu round-trip: `/api/coil/1/control` (start) → WS'te `stm_coil_update`
- [ ] Acil durdurma: `/api/hardware/emergency_stop` → tüm bobinler durur
- [ ] ESP MQTT yolu: `/api/coil/6/control` → broker → cihaz

**Crash drill (fail-safe):**
- [ ] `PEMF_Backend.exe` process'ini öldür → NSSM 5 sn'de yeniden başlatır
- [ ] Çöküş anında `backend_service` finally bloğu donanımı güvenli durdurur
- [ ] STM firmware Watchdog ikinci güvenlik katmanı

**Reboot & mobil:**
- [ ] Sunucuyu yeniden başlat → `mosquitto` → `PemfBackend` otomatik gelir
- [ ] Telefon aynı Wi-Fi'de uygulamayı açınca sunucuyu otomatik bulur
- [ ] (Uzak) Cloudflare tunnel ile bağlanır

**Rollback:** Sorun olursa GUI hâlâ `python main.py --gui` ile açılabilir (Faz 8'e kadar).

---

## Sorun giderme

| Belirti | Bakılacak |
|---|---|
| Servis başlamıyor | `C:\ProgramData\PEMF_System\logs\backend_service_stderr.log` |
| Build KIRMIZI | `python scripts\check_headless_imports.py` çıktısı (Qt sızıntısı) |
| MQTT yok | `services.msc` → `mosquitto` Running mı? Firewall 1883? |
| STM bağlanmıyor | COM portu LocalSystem altında erişilebilir mi? Sürücü? |
| Mobil bulamıyor | Firewall UDP 5051 + TCP 8000; aynı subnet mi? |

## Sürüm geri alma (Rollback) — *runbook (audit B-9.2)*

Kötü bir OTA güncellemesi sahada sorun çıkarırsa **önceki kararlı sürüme dönülür**. GitHub
release'leri tag-başına immutable (silinmez) → her sürümün installer'ı korunur.

**Yol 1 — Tek-tık (önerilen):** Backend, manifest'teki `previousStable` (son iyi sürüm) hedefini
tanır. Operatör mobil/web'den **Geri Al** eylemini tetikler → `POST /api/update/rollback` →
installer indirilir + **SHA256 + Authenticode doğrulanır** + **aktif tedavi yoksa** sessiz kurulur.
Durum: `GET /api/update/status` → `previousStable` alanı rollback hedefini gösterir.

```bash
# Uzaktan (LAN'da token gerekmez; tünelde X-API-Key):
curl -X POST http://<cihaz-ip>:8000/api/update/rollback
```

**Yol 2 — Elle:** `pemf-update` reposu → `exe` branch → önceki sürüm tag'inin
`PEMFBackendSetup.exe` asset'ini indir → cihazda çalıştır:
```bat
PEMFBackendSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```
Servis (`PemfBackend`) installer tarafından durdurulur, EXE değiştirilir, yeniden başlatılır.

**Güvenlik:** Rollback de apply ile AYNI zinciri kullanır — SHA256 ZORUNLU, aktif-tedavi-varsa
REDDED (fail-closed). `previousStable` manifest'te yoksa Yol-2 (elle) kullanılır.

**Yayınlama tarafı:** `scripts/publish_release.ps1` yeni sürüm yayınlarken mevcut manifest'in
sürümünü otomatik `previousStable` olarak taşır → rollback hedefi hep bir önceki sürümdür.
