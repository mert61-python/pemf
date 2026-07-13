# PEMF Vet — Web Sitesi (Vercel)

Veteriner **PEMF Vet Client** için indirme/tanıtım sitesi. Vite + React + TypeScript + Tailwind v4.
Kullanıcı buradan **küçük client’ı (~52 MB)** indirir; asıl uygulama client içinden iner.

## Ürün modeli (siteyi anlamak için)

**3 katman:** Website (bu proje, Vercel) → **Client/Launcher** (~52 MB, indirilir, next-next kurulur; profil seçilir, modeller iner, “Başlat” ile açılır, masaüstü kısayolları) → **Uygulama** (büyük, gömülü; React web arayüzü). Mobil ayrıdır (App/Play Store).

**İki bağımsız eksen:**
- **Kullanım profili = NE kurulur** (Ev Sahibi · Veteriner · Araştırma) — çoklu seçim, **client içinde**; yalnız seçilen AI modelleri iner.
- **Üyelik seviyesi = İŞLEM önceliği** — Başlangıç / Pro / **Pro+**. Pro **kuyrukta** bekler, **Pro+ gerçek-zamanlı** (kuyruksuz).

**Fiyat politikası:** Seviye = aylık abonelik (compute önceliği). Ev Sahibi + Veteriner seviyeye **dahil**; **Araştırma** ağır olduğu için **+₺390/ay eklenti**.

## Yapı

```
src/
├── config.ts            → TÜM içerik & fiyatlar (tek yerden düzenle)
├── main.tsx / App.tsx   → router + layout (ScrollToTop)
├── index.css            → Tasarım sistemi (Tailwind v4 @theme: teal/navy, Inter)
├── components/
│   ├── Icons.tsx        → SVG ikon seti + Logo
│   ├── Header.tsx / Footer.tsx
│   ├── DownloadButtons.tsx
│   ├── LauncherMock.tsx → dashboard/launcher önizleme (saf CSS)
│   └── PackageBuilder.tsx → profil seçim + boyut/ücret tahmini
└── pages/
    ├── Home.tsx         → hero + launcher akışı + özellikler + profiller + plan teaser
    ├── Features.tsx     → özellik detayı + launcher önizleme
    ├── Pricing.tsx      → seviyeler + karşılaştırma tablosu + profiller + eklentiler
    ├── Download.tsx     → client indir + profil seçimi + sistem gereksinimleri
    └── Support.tsx      → SSS + iletişim
public/                  → favicon, hero/launcher görselleri
vercel.json              → SPA rewrite + asset cache
```

## İçeriği düzenleme

Metin/fiyat/link **tamamı `src/config.ts`** içinde:
- `CLIENT` — sürüm, boyut, **indirme URL’leri** (win/mac). ⚠️ Şu an `#` — client yayınlanınca gerçek dosya URL’si koyun. **52 MB’lık client’ı Vercel’e koymayın**; GitHub Releases / Cloudflare R2 / S3’te barındırın, URL’yi buraya yazın.
- `PLANS` — Başlangıç / Pro / Pro+ (fiyat + `realtime`/`queue` politikası).
- `MODULES` — Ev Sahibi / Veteriner / Araştırma (boyut + `included`/`addonMonthly`).
- `ADDONS`, `COMPARE`, `FEATURES`, `LAUNCHER_STEPS`, `FAQ`, `BRAND`.

## Geliştirme

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc + vite build → dist/
npm run preview    # dist/ önizleme
```

## Vercel’e deploy

**Yol 1 — Git (önerilen):** repoyu GitHub’a push edin → Vercel’de “New Project” → repoyu seçin. Vercel Vite’ı otomatik algılar (Build: `npm run build`, Output: `dist`). `vercel.json` SPA yönlendirmesini halleder.

**Yol 2 — Vercel CLI:**
```bash
npm i -g vercel
vercel            # önizleme dağıtımı (ilk seferde login + proje bağlama)
vercel --prod     # production
```

Framework preset: **Vite** · Build: `npm run build` · Output dir: `dist`.

## Tasarım sistemi
Teal marka (`oklch(66% 0.13 184)`), koyu navy zemin, **Inter**, radius `.625rem`, Tailwind v4. Token’lar `src/index.css` `@theme` içinde; koyu/premium launcher estetiği.
