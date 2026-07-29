# PEMF Vet Landing — Lovable Sitesinden Çıkarılan Tasarım

Kaynak: `https://install-wizard-maker.lovable.app` (Lovable projesi `c57d7b06-7f05-4bd5-92e3-22fdd4959de6`).
Site **SSR (server-side rendered)** olduğu için render edilmiş HTML + derlenmiş Tailwind CSS + görseller **birebir** çıkarıldı. 3 verilen URL de **aynı** projeye işaret ediyor (preview / deployed / editor).

## Ne var (self-contained, çalışır kopya)
```
pemf_vet_landing/
├── index.html            → Ana sayfa (Landing: hero + özellikler + launcher demo)
├── download/index.html   → /download  (İstemciyi İndir — 52 MB)
├── features/index.html   → /features  (Özellikler)
├── support/index.html    → /support   (Destek)
├── design_readable.html  → Ana sayfanın script'siz, girintilenmiş (okunabilir/düzenlenebilir) markup'ı
├── favicon.ico
└── assets/
    ├── styles-k1hD6UYS.css   → Derlenmiş Tailwind v4 + tüm tasarım token'ları (82 KB)
    ├── index-jnGAdKBn.js     → React uygulaması (hidrasyon; minified)
    ├── routes-B0qTB3cr.js    → Rotalar
    ├── SiteFooter-*.js       → Footer bileşeni
    ├── hero-mockup-*.jpg      → Hero görseli
    └── launcher-banner-*.jpg  → Launcher görseli
```

## Nasıl çalıştırılır (rotalar için KÖKTEN sunum şart — mutlak `/assets/` yolları)
```bash
cd pemf_vet_landing
python -m http.server 8080
# → http://localhost:8080/  ·  /download  ·  /features  ·  /support
```
> `index.html`'i doğrudan çift-tıklamak (file://) yalnız ana sayfayı statik gösterir; rotalar + JS hidrasyonu için yerel sunucu gerekir. Kendi alan adında da site köküne konmalıdır.

## Tasarım Sistemi (styles.css `:root` — açık/koyu tema)
- **Marka rengi (primary):** `oklch(58% .11 180)` → teal/cyan
- **Arka plan:** açık `oklch(100% 0 0)` (beyaz) / koyu `oklch(12.9% .042 264.695)` (koyu navy)
- **Surface (kart/bölüm):** `oklch(98.5% .003 247)` (kırık beyaz)
- **Launcher (dashboard mockup) paleti:** bg `oklch(20% .02 260)`, chrome `oklch(14% .015 260)`, panel `oklch(24% .02 260)`, muted `oklch(70% .02 250)`, border `oklch(100% 0 0/.08)`
- **Font:** Inter (400/500/600/700) — Google Fonts
- **Radius:** `.625rem` · **Framework:** Tailwind CSS v4.2.4

## Sayfa yapısı (Tailwind class'larıyla — `design_readable.html`'de tam hali)
- `header.sticky.top-0.backdrop-blur` → logo + nav (Özellikler/İndir/Destek) + "İstemciyi İndir" butonu
- `section.px-6.py-24` (Hero) → "Sürüm 2026.1 Yayında" rozeti + başlık + indir CTA + sistem gereksinimleri
- `section.bg-surface.py-24` (Özellikler) → 01 Kesintisiz Senkronizasyon (BLE) · 02 Hasta Veritabanı · 03 Otomatik Güncellemeler
- `section.px-6.py-24` (Launcher demo) → `main.bg-launcher-bg` gömülü dashboard mockup + yama notları (v1.2.4)
- `footer.border-t` → Gizlilik / Kullanım Şartları / İletişim · © 2026 V-PEMF Technologies

## Sınır
Bu, deploy edilen siteden çıkarılan **birebir çalışan kopyadır** (HTML+CSS+JS+görsel). **Temiz React `.tsx` kaynağı** (bileşen dosyaları) yalnız Lovable editöründe / bağlı GitHub reposundadır (kimlik doğrulaması gerektirir; deploy JS'i minified olduğu için oradan çıkarılamaz). Tasarımı yeniden üretmek için gereken her şey (markup + Tailwind class'ları + token'lar + görseller) burada mevcut.
