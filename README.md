# PEMF Vet Client (Launcher)

Riot/Valorant-benzeri **masaüstü launcher** — Tauri v2 + React + TypeScript + Tailwind v4.
Website'den indirilen küçük client; asıl PEMF Vet uygulamasını (AI modelleri gömülü) indirir,
kurar ve **"Başlat"** ile açar. Masaüstüne hem client hem uygulama kısayolu koyar.

## Akış (Riot mantığı)
1. **Profil seçimi** — Ev Sahibi / Veteriner / Araştırma (çoklu); yalnız seçilenlerin AI modelleri iner.
2. **İndirme/Kurulum** — ilerleme çubuğu (Rust `install://progress` event'i).
3. **Başlat** — uygulamayı açar (React web, `http://localhost:8000`) — masaüstü app kısayoluyla aynı.

## Yapı
```
src/                     → React launcher UI
├── App.tsx              → 3 adım (profiles → installing → ready)
├── config.ts           → profiller, APP_URL, marka
├── index.css           → tasarım sistemi (web ile aynı: teal/navy, Inter)
└── Icons.tsx
src-tauri/               → Rust (native)
├── src/lib.rs          → start_install / launch_app / create_shortcuts / is_installed / installed_profiles
├── tauri.conf.json     → pencere 1000×680 koyu tema
└── Cargo.toml
```

## Geliştirme / Build
Önkoşul: **Rust** (rustup), **VS2022 C++ build tools**, **WebView2** (Win10/11'de gömülü).
```bash
npm install
npm run tauri dev      # geliştirme penceresi (HMR)
npm run tauri build    # release .exe + installer → src-tauri/target/release/bundle/
```

## ⚠️ v1 durumu (bu iskelet)
- **İndirme SİMÜLASYONdur** (`lib.rs::start_install` ilerleme event'i üretir; gerçek dosya inmez).
  Gerçeğe geçince: `start_install` içinde **reqwest** ile asıl uygulama paketini + seçili profil
  modellerini indir (progress = bayt/toplam). Kaynak website ile aynı host (GitHub Releases / R2).
  Kurulum = Inno/NSIS installer'ı sessiz çalıştır ya da arşiv çıkar.
- **launch_app** GERÇEK: `http://localhost:8000` açar (uygulama servisi çalışıyorsa).
- **create_shortcuts** GERÇEK: masaüstüne `PEMF Vet.url` (uygulama) + `PEMF Vet Client.lnk` (client).
- Marker: `%LOCALAPPDATA%\PEMFVetClient\installed.json`.

## Bağlam
- Website (indirme sayfası): ayrı proje `pemf-vet-web/` (Vercel).
- Uygulama (büyük app): mevcut PEMF backend + React web (`localhost:8000`) — client bunu başlatır.
- Fiyat/profil modeli website ile aynı: Seviye=Pro/Pro+ (compute önceliği), Araştırma=+₺390 eklenti.
