# PEMF — Docker Kurulumu

Sistem **2 image + 1 compose** ile ayağa kalkar (donanım bağımsız — STM/ESP yok, `PEMF_SIMULATE=1`):

| Servis | Image | Dockerfile | Ne |
|---|---|---|---|
| **backend** | `pemf-backend` | `Dockerfile.backend` | Python 3.10 + AI + FastAPI (:8000) |
| **frontend** | `pemf-frontend` | `Dockerfile.frontend` | Expo/React web → nginx (:8080), `/api`'yi backend'e proxy'ler |

## Dosyalar
- `Dockerfile.backend` — backend image (build context = `guii/`). Non-root çalışır; BuildKit pip cache.
- `Dockerfile.frontend` — frontend image (build context = `guii/pf`). nginx sertleştirilmiş (gzip + güvenlik başlıkları + cache).
- `requirements-docker.txt` — **backend'in Docker bağımlılıkları** (ana `requirements.txt`'e DOKUNULMAZ; sadece 4 fark: opencv-headless, sqlcipher3-binary, pyinstaller/pytest çıkarıldı).
- `docker-compose.yml` — ikisini birden ayağa kaldırır (proje adı `pemf` → `pemf-backend-1` / `pemf-frontend-1`).
- `docker.env.example` — **opsiyonel** ayar override'ları (`cp docker.env.example .env`). Compose zaten varsayılanlıdır.
- `.dockerignore` (backend) + `pf/.dockerignore` (frontend).

## Çalıştırma
```bash
# guii/ klasöründe (WSL/Linux):
docker compose up --build -d      # build + arka planda başlat
docker compose ps                 # durum (healthy?)
docker compose logs -f            # canlı log
docker compose down               # durdur (veri kalır)
docker compose down -v            # durdur + kalıcı veriyi sil
```
- Tarayıcı: **http://localhost:8080** (frontend; `/api` otomatik backend'e gider)
- Doğrudan API/debug: **http://localhost:8000/api/health**
- **Ayar değiştirme (opsiyonel):** `cp docker.env.example .env` → portlar/`PEMF_*` değerlerini düzenle. Compose `.env`'i otomatik okur.

## Profesyonel sertleştirmeler
- **Non-root:** backend `pemf` kullanıcısı ile çalışır; AI cache dizinleri (torch/ultralytics/numba/matplotlib) `/home/pemf/.cache`'e yönlendirilir.
- **nginx:** gzip, statik varlık `immutable` cache, `no-cache` HTML, güvenlik başlıkları (`X-Content-Type-Options`/`X-Frame-Options`/`Referrer-Policy`), `/healthz` sağlık ucu.
- **Healthcheck:** backend `/api/health` + frontend `/healthz` → `docker compose ps` gerçek sağlığı gösterir.
- **Sinyal/log:** `init: true` (tini, düzgün Ctrl-C/zombi), json-file log rotasyonu (10m×3).
- **Build hızı:** BuildKit pip cache mount → yeniden-build'lerde wheel'ler yeniden indirilmez (imaj boyutunu artırmaz).
- **`.env` sızıntı önlemi:** `.env*` `.dockerignore`'da → imaja girmez.

## Başlatma sırası (healthcheck)
Backend AI kütüphanelerini (torch/ultralytics/onnx) yüklerken ~30-60 sn `starting` durumunda kalır.
Compose'da **backend healthcheck** (`/api/health`, auth-muaf) + **frontend `depends_on: condition: service_healthy`**
tanımlı → nginx, backend HAZIR olana kadar başlamaz. Böylece ilk açılışta `/api` isteklerinde 502 alınmaz.
İlk `up --build` uzun sürer (imaj çekme + AI kütüphaneleri); tekrar başlatmalar hızlıdır.

## Platform desteği (Linux / macOS / Windows)
İmajlar **Linux tabanlıdır**; host yalnızca Docker'ı çalıştırır. Bu **web/demo (simülasyon)** sürümdür — donanım (STM/ESP/seri port) İÇERMEZ (klinik/donanım hâlâ Windows EXE/servis).

| Platform | Komut | Not |
|---|---|---|
| **Linux x86-64** | `docker compose up --build -d` | Native, en hızlı ortam. |
| **Intel Mac** | `docker compose up --build -d` | Docker Desktop for Mac. |
| **Apple Silicon (M1/M2/M3)** | ↓ aşağı bak | amd64 emülasyon önerilir. |
| **Windows** | `docker compose up --build -d` | WSL2 + Docker Desktop. |

### Apple Silicon (M1/M2/M3) — tek komutla çalıştırma
arm64'te bazı AI wheel'leri (`torch+cpu` / `onnxruntime` / `sqlcipher3-binary`) her sürümde bulunmayabilir.
En sorunsuz yol imajları **amd64** olarak (Rosetta/QEMU emülasyonu) çalıştırmaktır:

```bash
# guii/ içinde — tüm stack'i amd64 platformunda build+çalıştır:
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose up --build -d
```
Kalıcı istersen `docker-compose.yml`'de her iki servise ekle:
```yaml
    platform: linux/amd64
```
- Docker Desktop → **Settings → General → "Use Rosetta for x86/amd64 emulation"** açık olsun (emülasyon çok daha hızlı olur).
- Emülasyonla AI dahil **her şey çalışır**, sadece biraz yavaştır. Native arm64 istenirse wheel'ler tek tek arm64-uyumlu sürümlerle güncellenmeli (ayrı, ileri bir iş).

## Önemli notlar
1. **WSL şart** (Docker Desktop + WSL2 backend) — Docker Linux ister. Kurulum: `wsl --install` → Docker Desktop'ta WSL entegrasyonu aç.
2. **AI modelleri image'a GÖMÜLMEZ** (2 GB+). `release_assets/ai_models` host'tan `/models` olarak bağlanır (compose'da), `PEMF_AI_MODELS_DIR=/models`. Modellerin orada olması gerekir (bu repoda var).
   - *WSL notu:* `/mnt/c/...` (Windows FS) bind-mount yavaş olabilir; hız istenirse modeller bir Docker volume'e kopyalanabilir.
3. **DB (SQLCipher) + loglar** → `pemf_data` adlı kalıcı volume (`/data`). Konteyner silinse de kalır.
4. **requirements ayrımı bilerek:** lokal Windows build sürüm-kilitli kalsın, Docker'daki farklar ana sistemi bozmasın diye.
5. **Server modu:** `--no-headless-services` (mosquitto/UDP-keşif kapalı), `PEMF_REQUIRE_AUTH=1`, `PEMF_ENCRYPT_AT_REST=1`. Klinik/donanım için bu image DEĞİL — o hâlâ Windows servis/EXE.

## Sürüm uyumu
Backend pinleri ana `requirements.txt` ile birebir aynı (yalnız yukarıdaki 4 fark). `sqlcipher3-binary` prebuilt olduğundan sürümü Linux'ta değişebilir — SQLCipher 4.x DB formatı uyumludur.
