# Temiz Makinede PEMF — Sıfırdan Çalıştırma / Build Akışı

Bu rehber **boş bir makinede** PEMF Vet'i baştan çalışır hale getirir. İki farklı ihtiyacı
net ayırır — kendi sorunuz hangisiyse ilgili yolu izleyin, ötekini okumanıza gerek yok.

| Ne istiyorsunuz? | Hangi yol | Süre |
|---|---|---|
| Kliniğe cihazı **kurup kullanmak** (build yok) | **Yol A** | ~10 dk |
| **Build / yeni sürüm yayınlamak** (geliştirme) | **Yol B** | ilk sefer ~1 saat |

> Ayrıntılı build referansı: [`BUILD.md`](../BUILD.md). Bu dosya **akış**tır (ne, hangi sırayla);
> BUILD.md **başvuru**dur (neden, hangi tuzak). Toolchain ve paketleme derinliği orada.

---

## Yol A — Klinik makinesi (sadece kurup kullan)

Hiçbir toolchain, repo, sır, komut satırı **gerekmez**. Cihaz yazılımı kendini otomatik günceller.

1. Klinik bilgisayarında tarayıcıyı aç → **indirme sitesi:** https://pemf-vet-web.vercel.app
2. **Windows İçin İndir** → `PEMFVetClient-Setup-*.exe` iner → çalıştır.
   - Kurulum ~11 MB'lık launcher'ı yazar; **runtime + AI profilleri kurulum sırasında iner**
     (internet gerekir, ilk sefer birkaç GB — sabırlı olun, ilerleme çubuğu var).
   - Yayımcı: **IBIA Teknoloji Ltd. Şti.** (UAC uyarısında bu görünmeli).
3. Profil seç (Ev Sahibi / Veteriner / Araştırma) → **Başlat**.
4. Bitti. Cihaz açılışta manifest'e bakıp yeni sürüm varsa **sessizce günceller** (süren seans
   asla kesilmez; kurulum kapat-aç anında olur). Klinik hiçbir şey yapmaz.

**Bu yolda sır/E-stop-bulut vb. hiçbir elle iş YOKTUR** — bulut E-stop aynası kimliği yayın
paketine gömülü gelir (sahip kararı). Yerel acil-durdurma + termal koruma zaten cihazda gömülü
mosquitto ile çalışır; internet olmadan da güvenlidir.

> **Donanım (bobinler):** Bu yazılım-kurulumudur. STM32/ESP kartlarının firmware'i **ayrıca**
> flash'lanır (bkz. `firmware/*/README.md`) — klinik dağıtımında bu fabrika/servis adımıdır,
> son kullanıcı yapmaz.

---

## Yol B — Build / yayın makinesi (geliştirici)

Amaç: boş bir Windows laptopunda kaynaktan **backend EXE + paketler + installer + APK** üretip
GitHub'a yayınlayabilmek. Beş adım, **sırası önemli.**

### Ön koşul
- **Windows 10/11**, **yönetici PowerShell** (MSVC + winget için), internet.
- Bu **embeddable-python klasörünü** (`python-3.10.2-embed-amd64`) makineye koyun — içinde
  self-contained Python + pinli build-deps var (sistem Python **gerekmez**). `guii` onun altındadır.
- Elinizde **sır yedeği** olmalı: `pemf-sirlar.pemfsec` (bkz. Adım 3). Yoksa build "bulut-aynasız"
  çıkar ve APK imzalanamaz — yedeği eski makinede `secrets_backup.py backup` ile alın, USB'yle taşıyın.

### Adım 0 — Kaynağı getir
İki seçenek, ikisi de olur:
- **Klasörü kopyaladıysanız** (embeddable kök dahil): kaynak + AI modeli + Python env birlikte
  gelir → Adım 3'e geçin (yalnız toolchain + sır kalır).
- **Git'ten geliyorsanız:**
  ```powershell
  git clone https://github.com/mert61-python/pemf.git guii
  cd guii
  ```
  (Bu durumda AI modelleri git'te yok — Adım 2 onları indirir.)

### Adım 1 — Toolchain: `bootstrap.ps1`
Boş makineye tüm derleme araçlarını tek komutla kurar (Node, Git, gh, JDK 17, Inno Setup, Rust +
cargo-tauri, MSVC C++ Build Tools, Android NDK 27 + CMake 3.22.1). **İdempotent** — tekrar
çalıştırılabilir.
```powershell
.\bootstrap.ps1                 # her şeyi kur
.\bootstrap.ps1 -SkipAndroid    # APK'ya ihtiyaç yoksa NDK'yı (~1 GB) atla
.\bootstrap.ps1 -VerifyOnly     # sadece durum tablosu (ne var / ne eksik)
```
Sonra **bir kez** oturum aç (bunlar makineye özeldir, taşınmaz):
```powershell
gh auth login          # GitHub Releases yayını için (hesap: mert61-python)
```

### Adım 2 — AI model ağırlıkları: `restore_assets.ps1`
**Yalnız git'ten geldiyseniz gerekir** (klasörü kopyaladıysanız zaten var). Büyük ağırlıklar
(2,1 GB) git'te tutulamıyor (GitHub 100 MiB sınırı + LFS ücretli) → Releases'ten iner, **SHA256
doğrulamalı** (atlanamaz — tıbbi cihaz, yanlış ağırlık yanlış klinik çıktı demek).
```powershell
.\scripts\restore_assets.ps1
```

### Adım 3 — Makine-özel sırlar: `secrets_backup.py restore` ⭐ (yeni makinenin kilit adımı)
Git'e **hiçbir zaman** girmeyen 7 sır (2× ESP `Secrets.h`, 2× ESP `data/config.json`, bulut
E-stop provizyonu, Android `keystore.properties`, release imza anahtarı `.jks`) bu adımda yerine
oturur. Yedek dosyasını (USB'den) getirip:
```powershell
..\python.exe build_tools\secrets_backup.py restore --in D:\yedek\pemf-sirlar.pemfsec
```
Betik bittiğinde ekrana **iki hatırlatma** basar — ikisini de yapın:
1. **skip-worktree** (dört tracked sır dosyasının `git add -A` ile yanlışlıkla commit'lenmesini
   önler — betiğin bastığı komutu aynen çalıştırın).
2. `pf/android/keystore.properties` içindeki `storeFile` yolunun bu makinede doğru olduğunu
   kontrol edin (release `.jks` geri yüklendiyse `~/.pemf-keys/` altına koyun ya da yolu güncelleyin).

> ⚠️ `.pemfsec` **şifresiz** (parola sahip kararıyla kaldırıldı) — sadece base64 ile toplanmış.
> Dosyayı ele geçiren sırları okur. Git'e koymayın, e-posta/genel buluta yollamayın; USB /
> şifre-yöneticisi eki gibi erişimi sınırlı yerde taşıyın. Ayrıntı: `build_tools/secrets_backup.py`.

### Adım 4 — Derle + doğrula
```powershell
.\scripts\build_backend_exe.ps1 -SkipWeb     # frozen backend EXE (~5-10 dk, çıktı guii\PEMF_BUILD)
```
**Temiz-makine boot testi** (Python KURULU OLMADAN çalışmalı — frozen olmanın kanıtı):
```powershell
$env:PYTHONPATH=""; $env:PYTHONHOME=""
.\PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe --host 127.0.0.1 --port 8213
# başka pencerede:  curl http://127.0.0.1:8213/api/health   →  {"status":"online","version":"..."}
```
Bundan sonrası (paketleme → GitHub Release → manifest → site) **yayın akışıdır** —
[`BUILD.md` §6](../BUILD.md) adım adım anlatır (sıra: paketler ÖNCE, manifest EN SON, rollout
artık her zaman %100).

---

## Hızlı hata çözümü

| Belirti | Neden / çözüm |
|---|---|
| `bootstrap` "yeni terminal aç" diyor | winget PATH'i açık terminale yansımaz — PowerShell'i kapat-aç, `bootstrap -VerifyOnly` ile teyit et. |
| Build'de "cloud_mqtt_provision YOK" uyarısı | Adım 3 atlanmış → paket **bulut-aynasız** çıkar (yerel E-stop etkilenmez). Sır yedeğini restore edip yeniden derleyin. |
| APK imzası başarısız / keystore bulunamadı | `keystore.properties`'teki `storeFile` yolu bu makinede yanlış (Adım 3.2). |
| `git add -A` sır dosyalarını stage'liyor | skip-worktree uygulanmamış (Adım 3.1) — restore çıktısındaki komutu çalıştırın. |
| Frozen EXE health 404 | Uç `/api/health`'tir (`/health` değil). Farklı port deneyin, log: `PEMF_BUILD\dist\...\` yanındaki çıktı. |
| Klinik "Ortam algılanıyor…"da donuyor | Launcher bug'ı — sahaya **çalıştırılıp screencap ile doğrulanmamış** launcher yayınlanmış demektir (bkz. launcher runbook). |

---

*Referanslar: build derinliği [`BUILD.md`](../BUILD.md) · firmware/flash [`firmware/README.md`](../firmware/README.md) · sır yedeği aracı [`build_tools/secrets_backup.py`](../build_tools/secrets_backup.py) · sürüm tek-kaynağı [`versions.json`](../versions.json).*
