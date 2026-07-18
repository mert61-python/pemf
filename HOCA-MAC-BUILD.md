# PEMF Vet Client — macOS'ta `.dmg` Build

Bu klasör, PEMF Vet Client'ın (Tauri v2) kaynağıdır. macOS'ta native `.dmg`/`.app` üretmek için.
(Windows'tan macOS derlemesi mümkün değil — bu yüzden Mac'te build ediliyor.)

---

## 1) Gereksinimler (tek seferlik)

```bash
# Xcode komut satırı araçları (derleyici)
xcode-select --install

# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
#  → kurulumdan sonra terminali yeniden aç (veya:  source "$HOME/.cargo/env")

# Node.js 18+  (yoksa)
#  https://nodejs.org  ya da:  brew install node
```

## 2) Build

Bu klasörde terminal aç:

```bash
npm install
npm run tauri build
```

Çıktılar:

```
src-tauri/target/release/bundle/dmg/PEMF Vet Client_0.1.0_aarch64.dmg   ← indirilebilir .dmg
src-tauri/target/release/bundle/macos/PEMF Vet Client.app
```

> Apple Silicon (M1/M2/M3) → `aarch64`; Intel Mac → `x86_64`. İki Mac tipini de kapsamak istersen her ikisinde ayrı build al.

## 3) Gatekeeper / imzalama (önemli)

İmzasız `.dmg`'yi indiren kullanıcı macOS'ta *"geliştirici doğrulanamadı"* uyarısı alır. Seçenekler:
- **Kolay:** kullanıcı `.app`'e sağ tık → **Aç** → **Aç** (bir kez).
- **Profesyonel:** Apple Developer hesabıyla `codesign` + `notarytool` ile notarize et (uyarı kalkar).

## 4) Build ÖNCESİ — paket linkini ayarla (Mert yapar/yaptı)

Client Mac'te **Docker paketini** (`PEMF-Mac-Paket`) indirir. `src/config.ts` içindeki
`MAC.packageUrl` bu paketin indirme linki olmalı:

```ts
export const MAC = {
  packageUrl: "https://.../PEMF-Mac-Paket.zip",   // ← paketi host edip gerçek link
  dockerUrl: "https://www.docker.com/products/docker-desktop/",
}
```
(Şu an placeholder. Mert paketi Drive/GitHub'a yükleyip bu satırı günceller — sonra build.)

## 5) `.dmg`'yi web sitesine ekleme

1. Üretilen `.dmg`'yi bir yere yükle (GitHub Release / Drive → herkese-açık link).
2. `pemf-vet-web/src/config.ts` → `macosReady: true` + `macosAsset` URL'i `.dmg` linki → `npx vercel --prod`.
   (VEYA linki Mert'e gönder; site zaten macOS kartını "Yakında" gösteriyor, tek satırla açılır.)

---

## ✅ Bu client Mac'te NE YAPAR (uyarlandı)

Artık Mac dalı **Docker'ı yönetir** (Windows kurulum akışı Mac'te gizli). `.dmg` açılınca ekran:

1. **Docker Desktop** — kurulu/çalışıyor mu kontrol eder; değilse "İndir"/"Aç" butonu.
2. **PEMF paketi** — `~/Downloads/PEMF-Mac-Paket` içinde arar; yoksa "İndir" butonu (`MAC.packageUrl`).
3. **PEMF'i başlat** — Docker hazır + paket varsa: `docker load` (ilk sefer) → `docker compose up -d`
   → tarayıcıda **localhost:8080** açar. "Durdur" ile `docker compose down`.

**Mac kullanıcısı akışı:** Docker Desktop kur → PEMF paketini indir + `Downloads`'a `PEMF-Mac-Paket`
olarak çıkar → bu `.dmg`'yi aç → "PEMF'i başlat". (Paketin `docker-compose.dist.yml` +
`pemf-images.tar.gz` + `ai_models/` içermesi gerekir — Mert'in hazırladığı PEMF-Mac-Paket bu yapıda.)

> Not: Bu client Docker'ı **başlatır**; PEMF'in kendisi Docker konteynerlerinde koşar (backend+AI+web).
> Windows'taki gibi native servis kurmaz — Mac'te doğru mimari budur.
