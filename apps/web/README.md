# PEMF Vet — Web Sitesi (Vercel)

Veteriner **PEMF Vet Client** için indirme/tanıtım sitesi. Vite + React + TypeScript + Tailwind v4.
Kullanıcı buradan **küçük client’ı (~3 MB NSIS launcher)** indirir; asıl uygulama (büyük) client içinden iner.

## Ürün modeli (siteyi anlamak için)

**3 katman:** Website (bu proje, Vercel) → **Client/Launcher** (~3 MB NSIS launcher, indirilir, next-next kurulur; profil seçilir, modeller iner, “Başlat” ile açılır, masaüstü kısayolları) → **Uygulama** (büyük, gömülü; React web arayüzü). Mobil ayrıdır (App/Play Store).

**İki bağımsız eksen:**
- **Kullanım profili = NE kurulur** (Ev Sahibi · Veteriner · Araştırma) — çoklu seçim, **client içinde**; yalnız seçilen AI modelleri iner.
- **Üyelik seviyesi = JETON hakkı** — Başlangıç / Kullandıkça Öde / Pro / **Pro+**. 1 jeton = 1 yapay zekâ analizi; her seviye aylık bir jeton hakkı verir (devretmez), satın alınan jeton süresizdir. (Eski “işlem önceliği / kuyruk / gerçek-zamanlı” çerçevesi sahip kararıyla kaldırıldı — 2026-08-20; tek kaynak `src/config.ts` `JETON`.)

**Fiyat politikası:** Ücretli seviyeler aylık abonelik (jeton hakkı) + isteğe bağlı **Kullandıkça Öde** (aylık ücret yok, yalnız harcanan jeton faturalanır). Ev Sahibi + Veteriner profili seviyeye **dahil**; **Araştırma** ağır olduğu için **+₺390/ay eklenti**. ⚠️ Satış şu an **kapalı** (`FREE_MODE = true`): tüm profiller ücretsiz/indirilebilir, ücret etiketleri gizli — iyzico canlıya geçince `false` yapılır.

## Yapı

```
src/
├── config.ts            → TÜM içerik & fiyatlar (tek yerden düzenle)
├── main.tsx / App.tsx   → router + layout (ScrollToTop + ErrorBoundary + AuthProvider)
├── index.css            → Tasarım sistemi (Tailwind v4 @theme: teal/navy, Inter)
├── context/
│   ├── AuthContext.tsx  → Supabase oturumu (React context)
│   └── AuthModal.tsx    → giriş / kayıt / şifre-sıfırlama modali
├── lib/                 → yardımcılar: supabase (istemci), checkout, download, jeton, planFiyat, os, usageStats, authHatalari
├── components/
│   ├── Icons.tsx        → SVG ikon seti + Logo
│   ├── Header.tsx / Footer.tsx
│   ├── AccountButton.tsx → hesap menüsü (giriş/çıkış, abonelik iptali, jeton bakiyesi)
│   ├── DownloadButtons.tsx / DownloadGate.tsx → indirme butonları + oturum kapısı (indirmeden önce giriş)
│   ├── DownloadStats.tsx → GitHub Releases indirme sayacı
│   ├── AppScreenshots.tsx → telefon çerçeveli uygulama ekran görüntüsü galerisi
│   ├── ErrorBoundary.tsx → hata sınırı
│   ├── LauncherMock.tsx → dashboard/launcher önizleme (saf CSS)
│   └── PackageBuilder.tsx → profil seçim + boyut/ücret tahmini
└── pages/
    ├── Home.tsx         → hero + launcher akışı + özellikler + profiller + plan teaser
    ├── Features.tsx     → özellik detayı + launcher önizleme
    ├── Pricing.tsx      → seviyeler + karşılaştırma tablosu + profiller + eklentiler
    ├── Download.tsx     → client indir + profil seçimi + sistem gereksinimleri
    ├── Odeme.tsx        → iyzico ödeme/abonelik akışı (/odeme)
    ├── Legal.tsx        → yasal belge sayfaları (LEGAL_DOCS'tan üretilir)
    ├── ResetPassword.tsx → şifre sıfırlama (/sifre-sifirla)
    ├── Support.tsx      → SSS + iletişim
    └── NotFound.tsx     → 404
api/                     → Vercel serverless (iyzico abonelik + jeton): checkout · callback · webhook · cancel · tokens (+ _lib/iyzico·util, _types)
public/                  → favicon, hero/launcher görselleri, screenshots/
vercel.json              → SPA rewrite + güvenlik başlıkları (CSP/HSTS) + asset cache
```

## İçeriği düzenleme

Metin/fiyat/link **tamamı `src/config.ts`** içinde:
- `CLIENT` / `DOWNLOAD_HOST` — sürüm, boyut, **indirme kaynağı** (GitHub Releases; `windowsTag` tek kaynak, asset adı etiketten türetilir). **Client’ı (ve app/deps katmanlarını) Vercel’e koymayın**; harici host’ta durmalı.
- `PLANS` — Başlangıç / Kullandıkça Öde / Pro / Pro+ (fiyat + `jetonHakki`). ⚠️ Eski `realtime`/`queue` alanları SİLİNDİ; ayrım artık jeton hakkına dayanır.
- `JETON` — jeton ücretlendirme modeli (plan hakları, işlem maliyeti, ek paketler, kullandıkça-öde). Tek kaynak.
- `MODULES` — Ev Sahibi / Veteriner / Araştırma (boyut + `included`/`addonMonthly`); `RESEARCH_ADDON` araştırma eklenti tarifesi.
- `FREE_MODE` — `true` iken satış kapalı: tüm profiller ücretsiz, ücret etiketleri gizli (iyzico canlıya geçince `false`).
- `COMPANY` — satıcı/şirket kimliği (yasal zorunlu, tek kaynak); `LEGAL_DOCS` — yasal sayfa slug/başlıkları (route + footer + `Legal.tsx` buradan üretilir); `MEDICAL_DISCLAIMER`.
- `NAV`, `ADDONS`, `COMPARE`, `FEATURES`, `LAUNCHER_STEPS`, `PATCH`, `FAQ`, `BRAND`.

## Geliştirme

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc + vite build → dist/
npm run preview    # dist/ önizleme
```

## Site güncelleme / Deploy

**Git bağlı — TEK DEPO (2026-08-18'den beri):** bu klasör `mert61-python/pemf` deposunun
**`pemf-vet-web/` alt dizinidir** (eski ayrı `pemf-vet-web` deposu silindi; tam aynası
`../../pemf-vet-web-arsiv-2026-08-18.bundle`). Vercel projesi tek depoya bağlı:
**Root Directory = `pemf-vet-web`**, üretim dalı **`production-hardening`** → her push'ta
otomatik production deploy (canlı: https://pemf-vet-web.vercel.app). Vercel Vite'ı otomatik
algılar (Build: `npm run build`, Output: `dist`); `vercel.json` SPA yönlendirmesini halleder.
**Ignored Build Step** ayarlı: siteye dokunmayan commit'ler build tetiklemez (ölçüldü: son 40
commit'in 39'u site dışıydı). CI: kök `.github/workflows/site.yml` (**Node 22 şart** —
Node 20'de supabase-js "yerleşik WebSocket yok" ile düşer).

> ⚠️ **Ignored Build Step SIĞ-KLONA DAYANIKLI olmalı** (2026-08-19'da öğrenildi): Vercel
> repo'yu `--depth=10` ile klonlar. Firmware'e arka arkaya çok commit atınca Vercel'in
> "önceki deploy" olarak hatırladığı sha bu 10-commit penceresinin dışına düştü; komut
> `git diff <sha>` yapınca **`fatal: bad object`** verip deploy'u "Error"a düşürdü (canlı
> site etkilenmedi — Error yayınlanmaz, ama her push'ta hata maili geldi). Komut artık
> önce `git cat-file -e <sha>` ile objeyi test ediyor; yoksa (sığ klon) DERLE tarafına
> düşüyor. Tam komut Vercel projesi ayarlarında (`commandForIgnoringBuildStep`).

### İş akışı — siteyi güncellemek
```bash
# guii kökünden — içerik genellikle pemf-vet-web/src/config.ts (sürüm, fiyat, link…)
git add -A pemf-vet-web
git commit -m "açıklama"
git push                 # → site-ci koşar + Vercel otomatik deploy eder (~1-2 dk)
```
Hepsi bu. Deploy'u izlemek: Vercel panosu → pemf-vet-web → Deployments.

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

İndir (`/download`) sayfasındaki sayaç GitHub Releases API'sinden (`download_count`) beslenir (`DownloadStats.tsx`).

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
