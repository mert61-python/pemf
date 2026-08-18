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

## Site güncelleme / Deploy

**Git bağlı (2026-08-01’den beri):** bu repo (`mert61-python/pemf-vet-web`, dal **`master`**) Vercel projesine bağlıdır → **`master`’a her push = otomatik production deploy** (canlı: https://pemf-vet-web.vercel.app). Vercel, Vite’ı otomatik algılar (Build: `npm run build`, Output: `dist`); `vercel.json` SPA yönlendirmesini halleder.

### İş akışı — siteyi güncellemek
```bash
cd pemf-vet-web
# içeriği düzenle (genellikle src/config.ts: sürüm, fiyat, link…)
git add -A
git commit -m "açıklama"
git push                 # → Vercel otomatik deploy eder (~1-2 dk)
```
Hepsi bu. Deploy’u izlemek: Vercel panosu → pemf-vet-web → Deployments.

> ⚠️ **ALTIN KURAL — değişikliği HER ZAMAN commit + push et.** Sadece `vercel --prod` (CLI) ile deploy edip commit’lemezsen repo geride kalır → bir sonraki push canlı siteyi **ESKİ koda döndürür**. (Sürüm-etiketi “mayını” tam bu yüzden oluşmuştu: CLI-deploy’lar commit’siz kalınca repo 1.9.5’te takıldı.)

**CLI (yedek — normalde gerekmez):**
```bash
npm i -g vercel
vercel login      # TERMINAL’de device-code + tarayıcıda onay (vercel.com’a web-girişi CLI’yi authlamaz)
vercel --prod     # production’a doğrudan deploy
```
Git bağlı olduğu için CLI’yi yalnız acil bir tek-seferlik durumda kullan; kullanırsan **hemen ardından commit + push** et ki repo geri kalmasın.

Framework preset: **Vite** · Build: `npm run build` · Output dir: `dist`.

## Tasarım sistemi
Teal marka (`oklch(66% 0.13 184)`), koyu navy zemin, **Inter**, radius `.625rem`, Tailwind v4. Token’lar `src/index.css` `@theme` içinde; koyu/premium launcher estetiği.

## vercel.json — güvenlik başlıklarının gerekçesi

> ⚠️ `vercel.json` **yorum kabul etmez**: şemada olmayan `"//"` anahtarı deploy'u
> `Invalid vercel.json - should NOT have additional property "//"` ile düşürür
> (2026-08-06'da bu şekilde patladı). Gerekçe bu yüzden burada tutuluyor.

- **Neden başlık var:** sitede Supabase oturumu `localStorage`'da tutuluyor ve `/odeme`
  sayfası iyzico ödeme formunu `createContextualFragment` ile gömüp script çalıştırıyor.
  Hiçbir başlık yokken sayfa iframe'e alınabiliyordu (ödeme/hesap ekranında clickjacking)
  ve HSTS olmadığı için ilk istek düz HTTP'ye düşürülebiliyordu.
- **CSP:** iyzico ödeme formu kendi script/iframe'ini enjekte eder → `iyzipay.com`
  host'larına izin verilir. `frame-ancestors 'none'` modern tarayıcılarda
  `X-Frame-Options`'ın yerini tutar. `'unsafe-inline'` iyzico formunun gereğidir;
  kaldırılırsa ödeme adımı çalışmaz.

## İndirme sayacı (2026-08-06)

`/indir` sayfasındaki sayaç GitHub Releases API'sinden (`download_count`) beslenir.

⚠️ **"Kaç kişi" değil "kaç indirme".** İki bilinen şişme kaynağı var:
1. **Oto-güncelleme** — client v1.9.3'ten beri kendini güncellerken `PEMFVetClient-Setup.exe`'yi
   yeniden indirir; kurulu her cihaz her sürümde sayacı artırır (yeni kullanıcı olmadan).
2. **Geliştirme/test indirmeleri** de sayılır.

Bu yüzden arayüzde "kullanıcı" denmez ve dipnotta oto-güncellemenin dahil olduğu yazar.
Gerçek benzersiz kullanıcı sayısı ancak Supabase `devices` kaydından çıkarılabilir.

- Runtime paketleri (`base.zip`, model zip'leri, `manifest.json`) **sayılmaz** — client'ın
  kendi çektiği bileşenlerdir, sayılsalardı sayaç anlamsızca şişerdi.
- Veri çekilemezse (ağ / GitHub saatlik 60 istek sınırı) bölüm **kendini gizler**.
- ⚠️ `vercel.json` → CSP `connect-src` **`https://api.github.com` içermek zorunda**; yoksa
  tarayıcı isteği engeller ve sayaç sessizce hiç görünmez.
