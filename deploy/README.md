# PEMF Backend — Dağıtım Rehberi (Klinik PC + 24/7 Sunucu)

**Ana fikir:** Aynı frozen EXE (`PEMF_Backend.exe`) her yerde çalışır. Fark **yalnız ortam
değişkenleri** ile → `deploy/device.env` (klinik), `deploy/server.env` (sunucu/demo),
`deploy/staging.env` (üretim-benzeri doğrulama — audit B-9.4). Python kodu değişmez; kurulum scripti
`setup_services.ps1 -Mode device|server|staging` doğru profili okur.

> **Staging (B-9.4):** Bir release'i GERÇEK klinik cihazına deploy ETMEDEN önce sınamak için
> üretim-benzeri profil: simülasyon (donanımsız) + auth/at-rest-şifreleme AÇIK + AYRI port (8010)/
> veri-kökü (`C:\ProgramData\PEMF_Staging`)/log → device/server ile çakışmaz. QA veya ayrı makine:
> `setup_services.ps1 -AppDir C:\PEMF_Staging -Mode staging`.

---

## 1) Dağıtım dosya listesi

| Dosya / klasör | Amaç | Kim için |
|---|---|---|
| `dist\PEMF_Backend\PEMF_Backend.exe` + `_internal\` | Backend (FastAPI:8000), self-contained, Python gerekmez | **BOTH** |
| `_internal\bin\mosquitto\` | MQTT broker 1883 — ESP bobin 6-8 (offline gömülü) | DEVICE |
| `_internal\frontend\dist\` | React web UI (FastAPI `/` kökünden serve) | **BOTH** |
| `_internal\deploy\device.env` / `server.env` | Profil knob'ları (EXE'ye bundle edilir) | her biri |
| `_internal\bin\cloudflared\cloudflared.exe` | Uzaktan erişim tüneli — **elle eklenir** (bkz. §4) | DEVICE |
| `_internal\database\*_template.db` | Boş DB şablonları | **BOTH** |
| `nssm.exe` | Windows servis sarmalayıcı (çökme→5sn restart) | **BOTH** |
| `setup_services.ps1` | Üretim kurulum (`-Mode device|server`) | **BOTH** |
| `install_mosquitto_service.ps1` | Mosquitto'yu ayrı servis yapar | DEVICE |
| `PEMF_Backend_Setup.iss` → `PEMFBackendSetup.exe` | Tek-tık Inno installer (klinik) | DEVICE |
| `VC_redist.x64.exe` | VC++ 2015-2022 | **BOTH** |

> 🔒 Supabase yalnız **anon (publishable)** key gömülür. `service_role` **ASLA** dağıtılmaz.

---

## 2) Klinik (device) — gerçek donanım, uzaktan erişim AÇIK

1. **Ön koşul:** Windows 10/11, Administrator. STM32 USB sürücüsü kurulu (ST-Link VCP). VC++ redist.
2. `PEMFBackendSetup.exe`'yi Administrator çalıştır → dosyalar `C:\Program Files\PEMF`'e kopyalanır.
3. Installer `setup_services.ps1 -AppDir {app} -Mode device` çağırır:
   - Bundled **mosquitto** → Windows servisi (1883).
   - **PemfBackend** servisi (NSSM) + `deploy\device.env` env'leri.
   - Firewall: TCP 8000, TCP 1883, UDP 5051.
4. **STM portu OTOMATİK** bulunur (ST-Link USB VID). Tutmazsa `device.env`'e `PEMF_STM_PORT=COMx` yaz.
5. **Uzaktan erişim** `device.env`'de açık (`PEMF_ENABLE_TUNNEL=1` + `PEMF_REQUIRE_AUTH=1`). cloudflared gerekir (§4).
6. Doğrula: `http://localhost:8000/api/health` → STM connected, 8 bobin. Mobil aynı WiFi → mDNS ile bağlanır.

---

## 3) Sunucu (server) — donanımsız demo/simülasyon, public + TLS

1. **Ön koşul:** Windows (Server da olur), Administrator. Donanım YOK. **Reverse-proxy (IIS/Nginx/Caddy) + TLS** hazırla.
2. `dist\PEMF_Backend\` klasörünü sunucuya kopyala (örn `C:\PEMF`). **Mosquitto KURMA.**
3. `setup_services.ps1 -AppDir C:\PEMF -Mode server` çalıştır:
   - Mosquitto **atlanır** (donanım yok).
   - `deploy\server.env`: `PEMF_SIMULATE=1`, `PEMF_REQUIRE_AUTH=1`, `PEMF_API_HOST=127.0.0.1`, CORS daraltılmış, tünel kapalı.
4. **Reverse-proxy** `https://<domain>` → `http://127.0.0.1:8000` (TLS proxy'de sonlanır). Dışarıya yalnız **443**.
5. `server.env`'de `PEMF_CORS_ORIGINS`'i kendi web domain'inizle değiştir. `PEMF_ENCRYPT_AT_REST=1` → `/api/health`'te `atRestEncrypted` doğrula.
6. Doğrula: `https://<domain>/api/health` 200, token'sız kontrol endpoint'i **401**.

---

## 4) cloudflared (klinik uzaktan erişim için ZORUNLU)

Klinikler farklı WiFi'den bağlanacaksa tünel gerekir; binary repoda yok:
1. İndir: https://github.com/cloudflare/cloudflared/releases → `cloudflared-windows-amd64.exe`
2. Şuraya koy: `guii\bin\cloudflared\cloudflared.exe`
3. EXE'yi yeniden derle (`build_backend_exe.ps1`) — spec artık `bin/cloudflared`'ı otomatik bundle eder.
4. Klinik kurulumunda tünel zaten `device.env` ile açık; ilk açılışta `tunnel_url` Supabase `devices`'a yazılır.

---

## 5) Token dağıtımı (auth açıkken)

`PEMF_REQUIRE_AUTH=1` iken kontrol endpoint'leri token ister:
- İlk açılışta backend `app_data\api_token.txt` üretir.
- Operatör bu token'ı **web + 8 mobil** istemciye (Ayarlar → API token) güvenli kanaldan girer.
- `emergency_stop` / `health` / discovery muaftır (token'sız çalışır).

---

## 6) Güvenlik kontrol listesi

- [ ] Sunucu public → `PEMF_REQUIRE_AUTH=1` **+** reverse-proxy/TLS **+** CORS daraltma (asla `*`).
- [ ] `service_role` anahtarı hiçbir yere konmadı (yalnız anon/publishable gömülü).
- [ ] Klinik tünel açıksa auth **otomatik zorunlu** (installer `-EnableTunnel` bunu yapar).
- [ ] Klinik MQTT: `allow_anonymous=false` + `PEMF_MQTT_USER/PASS`.
- [ ] Hasta verisi (PII) buluta GİTMİYOR (`PEMF_CLOUD_PATIENT_SYNC=0`) — yalnız local şifreli SQLite.
- [ ] Sunucu: `atRestEncrypted` doğrulandı (sqlcipher binding gömülü mü).

---

## 7) Build notu

`build_tools\PEMF_Backend_onedir.spec` artık `deploy/` (env profilleri) ve (varsa) `bin/cloudflared`'ı
da bundle eder. Build: `scripts\build_backend_exe.ps1` → `C:\PEMF_BUILD\dist\PEMF_Backend\`.
