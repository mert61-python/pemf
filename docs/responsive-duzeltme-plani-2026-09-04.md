# PEMF Responsive Düzeltme Planı — 2026-09-04

Kaynak: `docs/responsive-denetim-2026-09-04.md` (121 benzersiz bulgu, ikinci doğrulama). Bu plan her bulguyu dokuz kök paketinden birine bağlar; paketlerin kod düzeyi adımları 9 planlayıcı ajan tarafından üretilip iki çakışma/sıralama incelemesinden (S1-S6; S7/L/W) geçirildi, çerçeve, fazlar ve kabul kriterleri Claude tarafından yazıldı.

## 1. Hedef

Her kullanıcı, hangi cihazda olursa olsun (dar telefon, telefon yatay, tablet dikey/yatay, DPI'lı küçük PC penceresi, geniş PC, LAN tarayıcısı, sistem yazı ölçeği büyütülmüş, çentikli/klavye açık) uygulamayı okuyabilir, dokunabilir ve kritik eylemleri (ACİL DURDUR, seans başlat/durdur, hasta kaydı, giriş, kurulum) kaydırmadan ya da en fazla bir kaydırmayla yapabilir.

### Sahip kararları (2026-09-04)

Aşağıdaki 16 karar doğrudan sahibe soruldu ve plana işlendi; paket metinlerindeki 'açık sorular' bu kararlarla kapanır.

| Konu | Karar | Uygulama | Paket |
|---|---|---|---|
| Ölçek tavanı (tablet/PC) | **%110** | `OLCEK_TAVAN_BUYUK_EKRAN = 1.10`. Gövde 14→15 px, başlık 24→26 px; kenar çubuğu ve ızgara düzelir. Telefon formülü BİREBİR korunur (375/430 kareleri piksel-eş kanıtı). | S1 |
| Yatay telefon kabuğu (≥768 px) | **İkon rayı** | 72 px ikon şeridi; alt bar 428 px yüksekliğin %17'sini yiyordu. `getShellKind` rail dalı. | S2 · S5 |
| Sistem yazı ölçeği tavanı | **1,2** | `MAX_FONT_SCALE = 1.2` injectFont varsayılanı; `allowFontScaling={false}` YASAK (kapı). Erişilebilirlik korunur, düzenler sığar. | S6 |
| Seans süresi biçimi | **Her zaman dk:sn** | `formatTime` tek dal: 65:30. Klinik kapak 120 dk → en fazla 6 karakter, her ekranda sığar. | S6 |
| Klavye açıkken ACİL DURDUR | **Klavyenin üstüne taşınsın** | `bottomOffset = klavyeYüksekliği`; düğme gizlenmez, içeriğin alt ~64 px'ini örter (içerik kaydırılabilir). | S4 |
| Başlatıcı minimum yüksekliği | **540 → 460** | `tauri.conf.json` minHeight 460 + Rust'ta monitör çalışma alanına göre kırpma. 1366×768 @%150'de pencere sığar. | L |
| Başlatıcıda Esc tuşu | **Yalnızca kapatsın** | Onay pencerelerinde HİÇBİR geri çağrı çalışmaz; yanlışlıkla Esc inen 1,4 GB paketi silmez. Odak `Vazgeç` düğmesinde. | L |
| Android tablet kullanımı | **Kullanılıyor** | Tablet dikey/yatay düzen ve cihaz testi planda kalır (ikon rayı, ızgara sütunları, 768-1024 kareleri). | S2 · test matrisi |
| ACİL DURDUR erişim hatası (ekranB-2) | **Faz 0 ile birlikte** | Responsive değil DAVRANIŞ hatası: kayan düğme STM belirsizken gizleniyordu + sayfa düğmesi ~3000 px derinde. Faz 0'da düzeltilir, acil paketle yayınlanır. | Faz 0 |
| Site üst menü kırılımı | **1024 px** | `md:flex` → `lg:flex`; 768-1023 px'te (iPad dikey, küçük dizüstü) hamburger menü. Başlık sıkışması biter. | W |
| PC web kamerası (canlı mod) | **Kullanılıyor** | Web canlı mod korunur: oran kilidi ve overlay hizası PC için de uygulanır, cihaz testine PC kamerası eklenir. | S7 |
| Ekran ölçümü kapısı | **GitHub'da otomatik** | `scripts/responsive_kapisi.py` CI'ya bağlanır (windows-latest, Edge headless + CDP); baseline ilk koşuda insan onaylı. CI süresi ~4-6 dk uzar. | Faz D |
| Alt bar etiketleri | **Kısaltılsın** | 'Akıllı Teşhis'→'Teşhis', 'AI Geçmişi'→'Geçmiş', 'Seans Geçmişi'→'Seanslar'. Sesli okuyucu ve kenar çubuğu TAM adı kullanmaya devam eder. | S6 |
| Fiyat tablosu (telefon) | **Kart görünümü** | Telefonda her plan ayrı kart; yatay kaydırma gerekmez. Tabloya göre ~3 saat ek iş. | W |
| iOS gerçek cihaz testi | **Var** | Klavye, çentik ve yatay senaryoları iPhone'da doğrulanır; EAS bulut derlemesi kapanış koşulu. | Faz G |
| Uygulama kapsamı | **Tüm plan sırayla** | Faz 0'dan G'ye kesintisiz; her fazda kapılar koşturulup rapor verilir. | — |
## 2. Cihaz sınıfı başına kabul kriteri (Definition of Done)

| # | Sınıf | Kabul |
|---|---|---|
| a | Dar telefon 320-360 | Yatay taşma yok; üst barda sayfa başlığı görünür; tüm dokunma hedefleri ≥ 44×44 px (çipler ≥ 40); uzun etiketler kırpılmadan sarar veya kısa etiket kullanılır. |
| b | Telefon 375-430 | a ile aynı; ayrıca AI Hub kamera kutusu ve sonuç panelleri tek bakışta okunur. |
| c | Telefon yatay | Üst bar tek satır (alt başlık gizli); tüm modallar ve 'Daha Fazla' sayfası kaydırılabilir; ACİL DURDUR görünür; grafik yüksekliği ekranın ≤ %45'i; çentik tarafına içerik girmez. |
| d | Tablet 768-1024 | Kenar çubuğu içeriğin ≤ %25'i (768-899'da ikon rayı); ızgara sütunları GERÇEK içerik genişliğinden; kartlar taşmaz; parametre girişleri ≥ 120 px. |
| e | PC penceresi (WebView2) | Ölçek 1,0-1,10; pencere 700 px'e küçültülünce masaüstü/ray düzeni korunur (telefon kabuğu çizilmez); yeniden boyutlandırma canlı. |
| f | PC geniş 1920-2560 | İçerik ve bantlar maxWidth ile ortalanır; tablolar sayısal sütunları sağa hizalar; canvas grafik keskin. |
| g | DPI %125-200 | Canvas devicePixelRatio ile çizilir; başlatıcı penceresi çalışma alanına sığar; hiçbir minimum boyut ekranı aşmaz. |
| h | LAN / uzak tarayıcı | viewport-fit=cover; iOS Safari'de giriş alanı ≥ 16 px (zoom yok); modal yükseklikleri svh/dvh. |
| i | Sistem yazı ölçeği 0,85-1,3 | Hiçbir metin kutudan taşmaz (maxFontSizeMultiplier 1,2 varsayılan); sayısal kritik alanlar sığar; alt bar etiketleri kırpılmaz. |
| j | Çentik / klavye | Kabuk dışı ekranlar (Welcome, Auth, Gate) inset uygular; klavye açıkken odaklı giriş ve 'Kaydet/Başlat' düğmesi görünür; ilk dokunuş klavyeyi kapatmakla kalmaz. |

## 3. Fazlar ve yayın eşlemesi

Toplam tahmini efor: **~152 saat** (planlayıcı toplamı, cihaz doğrulama turları dahil) + CI kapısı ~20.5 saat. Takvim tahmini **~14-16 iş günü** tek geliştiriciyle; kabuk PR'ı (Faz B) ve cihaz turları paralelleştirilemez.

| Faz | Kapsam | Yayın | Paketler | Süre |
|---|---|---|---|---|
| 0 | Temel ölçüm + ACİL DURDUR erişimi (sahip kararı) | app 1.9.41 ile yayınlanır | <strong>ekranB-2 düzeltmesi:</strong> kayan ACİL DURDUR STM belirsizken gizlenmiyor (kalıcı kilit) + ControlScreen sayfa düğmesi sekme çubuğunun ÜSTÜNE alındı<br>Görsel regresyon referansı: 7 görünüm alanı × 5 ekran + ACİL DURDUR kareleri (PEMF_SIMULATE=1)<br>Dokunma-hedefi kapısının TABAN ihlal sayısı<br>ResponsiveGrid testi önce KIRMIZI | 1 gün |
| A1 | Davranış değiştirmeyen altyapı (tek PR) | app 1.9.41 paketine girer | S3: touch token, IconButton, Chip<br>S2: theme/layout.ts (ölçeksiz 240/200/72) + ShellLayoutContext<br>S2+S5: useResponsive birleşik (shellKind, contentWidth, isShort…) + ortak responsiveMock<br>S4: useKeyboard + KAV_BEHAVIOR_*<br>S5: ScrollableModalCard<br>S6: MAX_FONT_SCALE<br>Button.tsx tek commit (S2 flexShrink + S3 boyut + S6 sığdırma)<br>S1: layoutMax token + 13 maxWidth | 1,5 gün |
| A2 | Global görsel tavanlar (iki ayrı commit, önce/sonra görüntü) | app 1.9.41 · OTA · APK 2.3.32 | S1: OLCEK tavanı 1,10 + jest matrisi (375/430 kareleri piksel-eş)<br>S6: injectFont maxFontSizeMultiplier | 0,5 gün |
| B | HASTA GÜVENLİĞİ kabuk PR'ı (ayrı PR, cihazda ÖNCE test) | app 1.9.41 · APK 2.3.32 (vc 39) | S5: GlobalEmergencyStop compact (tek sahip, minHeight max(touch.min, rs(48)))<br>AppShell birleşik edit: S2 rail/context/panHandlers isNative + S4 KAV/klavyede alt bar gizle/E-stop klavye üstü + S5 insets L/R, isShort, Daha Fazla + S3 profileChip/iconBtn + S6 kısa etiketler<br>Jest: AppShell.rail/klavye/landscape + GlobalEmergencyStop + mevcut logout/pairing | 2 gün |
| C | Ekranlar (bağımsız küçük commit'ler; aynı dosyada sıra S1→S4→S5→S3→S6→S7) | app 1.9.41 · OTA · APK 2.3.32 · iOS EAS | S1: paramField + useStageHeight<br>S4: iç ScrollView→View, modallar KAV, Auth, app.json<br>S2: ResponsiveGrid onLayout, Dashboard hero, Welcome (+S5 inset)<br>S5: Toast, MobileUpdateGate, UpgradeModal, AiSpecApprovalModal, chart height<br>S3: Chip göçü, CoilSelector, metin bağlantıları<br>S6: süre/okuma/tablo tek satır, güncelleme bandı<br>S7: TempChart onLayout, RealtimeChart PAD/DPR, kamera kutusu oran kilidi (+ backend image_w/h), bar/pie, rozetler, DEMA iframe | 5 gün |
| D | Kapılar (mutasyonla KIRMIZI kanıtlı) | CI | S1 yapısal-boyut, S2 kabuk sözleşmesi, S3 dokunma-hedefi (sabit=0), S4 iç ScrollView, S5 modal kaydırılabilir (allowlist=0), S6 allowFontScaling yasağı<br>scripts/responsive_kapisi.py CI'ya bağlanır (baseline insan onaylı) | 1,5 gün |
| E | Başlatıcı (ayrı hat) | launcher 1.9.46 | L: main flex-start + margin:auto, max-height sorgusu, monitör çalışma alanına göre min boyut, visible:false+show, title/aria-label, kart button, openModal (inert/Escape), app penceresi min boyut<br>S3: @media (pointer: coarse) (L PR'ının commit'i)<br>Python kapısı test_launcher_responsive_kapisi.py + cargo parite | 2 gün |
| F | Site | Vercel (production-hardening) | W: min-w-0 (yüksek), Header lg, AccountButton inline, pointer:coarse 16 px input, AuthModal svh, tek koyu tema token'ı, Pricing sticky sütun, PackageBuilder rozet, Download, Footer, 2xl<br>vitest kaynak kapısı + CDP tur + Vercel önizleme | 1,5 gün |
| G | Yayın ve cihaz doğrulaması | backend 1.9.41 → OTA → APK 2.3.32 → launcher 1.9.46 → site | Önce/sonra 35+35 kare; cihaz test matrisi; yayın kapısı: Faz B klavye-açık E-stop turu + 375/430 piksel-eş + tüm kapılar yeşil | 1 gün |

### İnceleyicinin gerekçeli sırası

- **Faz 0 — Temel ölçüm (commit yok)** (yok (scratchpad + docs/screenshots)): S1 adım 0, S3 adım 9 (taban sayımı), S2 adım 3 kırmızı-önce testi — Görsel regresyon referansı (7 görünüm alanı × 5 ekran + E-stop kareleri) ve dokunma-hedefi kapısının TABAN ihlal sayısı değişiklik ÖNCESİ alınmalı; aksi hâlde 'kapı boş çalışır' ve 375/430 piksel-eşlik kanıtı üretilemez. PEMF_SIMULATE=1 backend tek örnek.
- **Faz A1 — Davranış değiştirmeyen altyapı (tek PR)** (yok (dahili; app 1.9.41 paketine girer)): S3 adım 1,3,4,10 (touch token, IconButton, Chip, jest), S2 adım 1 (theme/layout.ts ölçeksiz 240/200/72 + ShellLayoutContext), S2 adım 2 + S5 adım 1 (useResponsive birleşik: shellKind/contentWidth/isShort…, getShellKind(w,isWeb,h), ortak responsiveMock), S4 adım 1 (useKeyboard + KAV_BEHAVIOR_*), S5 adım 2 (ScrollableModalCard, KAV_BEHAVIOR_MODAL import, backdrop muaf yorumu), S6 adım 1 (MAX_FONT_SCALE sabiti), S2 adım 6 + S3 adım 2 + S6 Button (Button.tsx tek commit), S1 adım 4 (layoutMax token + 13 maxWidth) — Tüketicisi olmayan/yalnız sabit ekleyen değişiklikler; mevcut jest süiti (AppShell mock'ları ortak yardımcıya taşınır) yeşil kalır. Sonraki her faz bu API'lere bağımlı (touch, layout.ts, hook alanları, KAV sabitleri).
- **Faz A2 — Global görsel tavanlar (iki ayrı commit, ekran görüntüsü karşılaştırmalı)** (app 1.9.41 (frontend_dist) + OTA 1.4.2; APK'ya S6 ile birlikte 2.3.32): S1 adım 1-2 (OLCEK tavanı 1.10 + jest matrisi), S6 adım 2 (injectFont maxFontSizeMultiplier) — İkisi de tüm ekranları etkiler ama tek yönlü (küçülme/tavan). Telefon (375/430) kareleri piksel-eş olmalı; S6 web'de no-op. Faz B/C'nin ekran görüntüleri bu tavanla alınmalı ki karşılaştırma tek değişkenli olsun. Geri alma tek satır.
- **Faz B — HASTA GÜVENLİĞİ kabuk PR'ı (ayrı PR, cihazda ÖNCE test)** (app 1.9.41 + OTA; APK 2.3.32 (androidVersionCode 39) — cihaz turu C4 geçmeden yayın yok): S5 adım 4 (GlobalEmergencyStop compact — TEK sahip, minHeight Math.max(touch.min, rs(48))), AppShell birleşik edit: S2 adım 4 (rail/desktop/ShellLayoutContext/panHandlers isNative) + S4 adım 2 (KAV + klavyede alt bar gizle + E-stop klavye üstü) + S5 adım 3,5 (insets L/R, isShort, Daha Fazla sheet) + S3 adım 8 (profileChip/iconBtn touch) + S6 alt bar kısa etiketler, Jest: AppShell.rail/klavye/landscape + GlobalEmergencyStop.test + mevcut logout/pairing — E-stop bottomOffset satırı, `desktop` semantiği, alt bar koşulu ve panHandlers dört paketin kesişimi — parça parça inerse ara durumlarda E-stop ofseti yanlış olur. Tek PR, üç kabuk (bottom 390 / rail 800 / sidebar 1280) × klavye açık × yatay 640×360'ta PEMF_SIMULATE=1 seans turu ve E-stop tek dokunuş kanıtı olmadan birleştirilmez. Bu PR'da başka ekran değişikliği YOK.
- **Faz C — Ekranlar (bağımsız küçük commit'ler, dosya-sahibi sırası)** (app 1.9.41 + OTA 1.4.2 (masaüstü etkisi: S1/S2/S5-11); APK 2.3.32 + iOS EAS (S3/S4/S5/S6 asıl hedef)): S1 adım 6 (paramField + SensorMonitor ResponsiveGrid; camBox S7'ye devredildi), S1 adım 7 (useStageHeight), S4 adım 3,4,5,6,7 (iç ScrollView→View, modallar KAV, Auth, app.json), S2 adım 3 (ResponsiveGrid onLayout), 5 (Dashboard hero), 7+S5 adım 7 (Welcome tek commit), S5 adım 6,8,9,10,11 (Toast, MobileUpdateGate, UpgradeModal, AiSpecApprovalModal, chart height), S3 adım 5,6,7 (Chip göçü, CoilSelector, metin bağlantıları), S6 kalan adımlar (süre/okuma/tablo tek satır, güncelleme bandı), S7 (plan bekleniyor: camBox, imagePreviewContainer aspectRatio, RealtimeChart PAD/DPR, TempChart, Pie lejant) — Aynı dosyaya dokunan paketlerde sıra: S1 → S4 → S5 → S3 → S6 → S7 (yapısal → kaydırıcı → yükseklik → dokunma → yazı → grafik). Her commit kendi jest'ini ve mevcut süiti tam koşturur (yapısal çıpa kayması). AiHubScreen'de regen YOK, cerrahi edit.
- **Faz D — Kapılar (mutasyonla KIRMIZI kanıtlı)** (yok (CI)): S1 adım 5 (test_responsive_olcek_yapisal.py — sidebar çıpası layout.ts'e), S2 adım 8 (test_responsive_kabuk_sozlesmesi.py), S3 adım 9 (test_dokunma_hedefi_kapisi.py sabit=0), S4 adım 3 kapısı (test_kabuk_ic_scrollview_kapisi.py), S5 adım 12 (test_modal_kaydirilabilir_kapisi.py allowlist=0), S6 pytest yapısal kapı (allowFontScaling={false} yasağı) — Kapılar kod değişiklikleri bittikten sonra sabitlenir (ratchet sayaçları 0'a iner); her biri için önce mutasyon-kırmızı, sonra yeşil kaydı. tests.yml yol filtresiz koştuğundan pf/ değişikliğinde otomatik koşar (S3 açık soru 5 kapanır).
- **Faz E — Launcher (ayrı hat)** (launcher 1.9.46 (versions.json → sync_versions.ps1; Launcher Yayın Runbook)): L (launcher-1,2,3,4,5,6,7,8,9,10,12 + matris-9), S3 adım 12 (launcher-11, L PR'ının commit'i) — Farklı yayın zinciri (Tauri self-update, iki ad, androidTag'e dokunma); tauri.conf minHeight kararı S5 isShort ile eşgüdümlü (440 alt sınır). cargo test + test_launcher_ui_sozdizimi + test_client_arayuz_sade_dil yeşil; `cargo tauri build` (npx-tauri BOZUK).
- **Faz F — Site** (site (Vercel production = production-hardening)): W (site-1…16, ampirik-1,3,6, matris-13), S3 adım 11 (site-11, W PR'ının commit'i) — Ayrı Vercel projesi, klinik akışı yok; production-hardening dalı. Tek `@media (pointer: coarse)` bloğu. `npm test` (vitest) + `npm run build` (check:legal + tsc).
- **Faz G — Yayın ve cihaz doğrulaması** (app 1.9.41 (Inno + frontend_dist), frontendOta 1.4.2, mobile 2.3.32 / androidVersionCode 39, launcher 1.9.46, site): S1 adım 8, S2 adım 9, S3 adım 13, S4 adım 8, S5 adım 13, S6 cihaz turu — Önce/sonra 35+35 kare; backend paketi (frontend export gömülü) 1.9.41 → OTA 1.4.2 → APK 2.3.32 sırası; backend build ile APK build PARALEL KOŞMAZ; iOS EAS gerçek cihaz 'bekliyor' notu kabul. Yayın kapısı: Faz B C4 (klavye açık E-stop) + 375/430 piksel-eş + tüm kapılar yeşil.

**S7 / L / W için ek sıra notları:**

- S7 = Faz C'nin SON halkası (S1→S4→S5→S3→S6→S7); S7 adım 4 (backend image_w/h) Faz C'de herhangi bir anda inebilir (yalnız-ek), istemci adım 5-6 ondan sonra; adım 10 kapısı Faz D (sabit sayaçlı → 0).
- S7 yayın zinciri: backend 1.9.41 (adım 4 + frontend_dist gömülü) → OTA 1.4.2 → APK 2.3.32 (androidVersionCode 39); backend+APK build PARALEL KOŞMAZ; S7 adım 7 cihaz testi Faz G'de Faz B turuyla aynı oturumda (AI Pro hazırlık modunda bobin sürülmez).
- L = Faz E, pf/backend'den bağımsız hat; iç sıra 1→2(+S3 adım 12)→3→4 (visible:false 3'ten SONRA, aksi hâlde pencere hiç görünmez)→5→6→7→8→9→10→11. Yayın: versions.json launcher 1.9.46 + sync_versions.ps1 + `launcher-v1.9.46` etiketi; Faz B'yi BEKLEMEZ. L adım 8 (app ≥1024×640) Faz B S2 rail eşiğiyle cihazda birlikte doğrulanır.
- W = Faz F, ayrı Vercel hattı; iç sıra 0→1→(2+3 tek commit)→4(+S3 adım 11)→5→6→7→8→9→10→11→12; PR dalı fix/site-responsive-2026-09-04 → Vercel önizleme → production-hardening (sahip onayı). Launcher 1.9.46 yayınlanınca config.ts CLIENT.version ayrı commit.
- Faz E ve Faz F, pf Faz B/C ile PARALEL yürütülebilir (dosya kesişimi yok); tek çapraz bağ S5 isShort ↔ L minHeight (440) kararı — S5 dokümana yazar, L PAY sabit.
- Faz C S7 satırı ('plan bekleniyor') → 11 adım: 1(TempChart),2(RealtimeChart+Sensor),3(KPI),8,9,11 bağımsız küçük commit'ler; 4(backend) ayrı commit; 5+6 (kamera) tek PR + adım 7 cihaz kapısı; 10 (rf(9/10)) üç sahipli (S7/S6/Faz B).

## 4. Paketler arası çakışmalar ve çözümleri

- **S1 × S2 × S5:** Kenar çubuğu genişliği ÜÇ ayrı yerde/değerde tanımlanıyor: S1 adım 3 AppShell içinde `KENAR_CUBUGU_GENISLIK={masaustu:240,tablet:200}` (ölçeksiz, inline style); S2 adım 1 `theme/layout.ts` içinde `SIDEBAR_WIDTH=rs(248)`, `RAIL_WIDTH=rs(72)` (ölçekli, styles.sidebar.width); S5 adım 3 `styles.sidebarRail:{width:rs(72)}` + `rail = desktop && isShort` + NavButton `compact={rail}` (ikon+küçük etiket), S2 adım 4 ise NavButton'a `rail` prop'u (ikon-only, Text çizilmez). S5 landscape testi `getByText('Ayarlar')` bekler, S2 rail testi `queryByText('Ayarlar')===null` bekler → iki test birbirini KIRAR. AppShell.tsx:517 aynı satır. → _TEK KAYNAK theme/layout.ts (S2 adım 1) — ama değerler S1'in 'yapısal boyut ölçeksiz' kararıyla: `SIDEBAR_WIDTH=240`, `SIDEBAR_WIDTH_TABLET=200`, `RAIL_WIDTH=72` (rs YOK); `shellSidebarWidth(kind, isTablet)` tablette 200 döndürür. S1 adım 3 İPTAL (S2 adım 1+4'e devredilir; S1 Python kapısı `width: rs(248)` yokluğu + `SIDEBAR_WIDTH` varlığını layout.ts'te arar). Rail görünümü S2'nin `rail` prop'u (ikon-only + accessibilityLabel) — S5 adım 3(d) silinir, S5 yalnız `rail` KOŞULUNU genişletir: `getShellKind(width, isWeb, height)` → `kind==='sidebar' && height<shortHeight → 'rail'`. S5 landscape testi etiketi `getByLabelText('Ayarlar')` ile arar._
- **S2 × S4 × S5:** AppShell.tsx:399 `<GlobalEmergencyStop bottomOffset={desktop ? 0 : rs(76)} />` satırına üç paket farklı ifade yazıyor: S2 'DOKUNULMAZ' (kilit), S4 adım 2 `desktop ? 0 : klavyeAcik ? klavyeKaldirma : rs(76)`, S5 adım 3(g) `desktop ? 0 : (isShort ? rs(60) : rs(76))` + `compact={isShort}`. Sonuncu inen diğerini ezer → klavye açıkken ya da yatayda E-stop ofseti kaybolur. → _Tek birleşik ifade, tek PR (Faz B): `bottomOffset={desktop ? 0 : klavyeAcik ? klavyeKaldirma : isShort ? rs(60) : rs(76)}` ve `compact={isShort}`; öncelik sırası yorumla: klavye > kısa yükseklik > varsayılan. AppShell.klavye + AppShell.landscape testleri aynı dosyada bu üç dalı ayrı ayrı ÖLÇER (mock GlobalEmergencyStop bottomOffset/compact'ı Text'e basar). S2'nin 'dokunulmaz' kilidi 'desktop→0 dalı ve `desktop` semantiği değişmez' olarak daraltılır._
- **S2 × S4:** AppShell.tsx:246 `<View style={styles.main} {...(!desktop ? panHandlers : {})}>`: S2 adım 4(b) koşulu `!desktop && responsive.isNative` yapar; S4 adım 2(a) View'ı KeyboardAvoidingView ile değiştirir ama taslağında koşul yine `!desktop` → S4 sonra inerse web'de swipe geri gelir (kabuk-2 regresyonu) ve S2 Python kapısı (`panHandlers…isNative` regex) kırmızı olur. → _Birleşik satır: `<KeyboardAvoidingView style={styles.main} behavior={KAV_BEHAVIOR_PENCERE} enabled={responsive.isNative} {...(!desktop && responsive.isNative ? panResponder.panHandlers : {})}>`. S2 kapısı regex'i aynen tutar; S4 kapısı `grep KeyboardAvoidingView` ekler. Faz B tek PR._
- **S2 × S4 × S5:** AppShell içerik ScrollView'ı (385-393): S2 adım 4(e) contentContainerStyle'ı yalnız paddingBottom bırakıp padding/gap'i yeni iç `contentInner` View'a taşıyor (ShellLayoutContext.Provider); S5 adım 3(f) aynı contentContainerStyle'da paddingBottom'ı `isShort ? rs(120) : rs(160)` yapıyor; S4 kilidi 'paddingBottom rs(160)+insets.bottom KORUNUR' diyor. S4 kilidi S5 ile çelişir. → _S2 yapısı esas alınır; paddingBottom ifadesi: `!desktop ? { paddingBottom: (isShort ? rs(120) : rs(160)) + insets.bottom } : { paddingBottom: rs(84) }`. S4 kilidi 'kayan E-stop son satırı örtmez (paddingBottom ≥ E-stop yüksekliği + bottomOffset)' olarak yeniden yazılır; isShort'ta rs(120) ≥ rs(60)+rs(48)+md sağlanır (test: paddingBottom ≥ bottomOffset + 52 + spacing.md)._
- **S3 × S4 × S5 × S6:** AppShell alt bar bloğu (401-422) ve stilleri: S4 adım 2(d) render koşulu `!desktop && !klavyeAcik`; S5 adım 3(b,e) bottomNav insets.left/right + `bottomNavShort` + bottomItem minHeight rs(44); S3 adım 8 profileChip/header ve adım 2 iconBtn touch.min; S6 (kabuk-5) bottomLabel kısa etiket + maxFontSizeMultiplier. S3 kilidi 'GlobalEmergencyStop.tsx DOKUNULMAZ' iken S5 adım 4 dosyayı DEĞİŞTİRİYOR (compact prop). S5 `bottomItem minHeight: rs(44)` 320 px'te 38 px → S3 kapısı (rs(N) N≥52 ya da touch.*) bunu İHLAL sayar. → _Faz B'de AppShell tek birleşik edit; alt bar: `{!desktop && !klavyeAcik ? <View style={[styles.bottomNav, isShort && styles.bottomNavShort, {paddingBottom…, paddingLeft: Math.max(insets.left, spacing.sm), paddingRight: …}]}>` ; bottomItem `minHeight: touch.min` (S3 token, rs(44) YASAK). GlobalEmergencyStop.tsx'i yalnız S5 adım 4 değiştirir (tek sahip) ve `btnCompact.minHeight = Math.max(touch.min, rs(48))`; S1/S2/S3/S4 kilitleri 'yalnız S5 adım 4 commit'i dokunur, onPress/render koşulu/zIndex değişmez' olarak güncellenir._
- **S2 × S5:** useResponsive.ts dönüş nesnesi iki pakette genişliyor (S2: shellKind/contentWidth/sidebarWidth/isPointer; S5: isShort/isLandscape/isLandscapePhone) ve AppShell.logout/pairing testlerinin mock'u (`{isDesktop,isTablet,isCompact,width}`) her ikisinde ayrı ayrı güncelleniyor. S2 `getShellKind(width,isWeb)` imzası S5'in height ihtiyacını karşılamıyor (S2 açık soru 5). → _Faz A'da TEK hook PR'ı: her iki alan seti birlikte; `getShellKind(width, isWeb, height)` üç parametreli (S5 shortHeight sabiti breakpoints.ts'te, layout.ts oradan okur). Testlerde ortak `__tests__/responsiveMock.ts` yardımcı: `mockResponsive({width:1280})` tam nesneyi (isNative, shellKind, contentWidth, isShort, height…) üretir; AppShell'de `responsive.isShort === true` savunmacı okuma yine de kalır._
- **S1 × S2:** S1 adım 1 jest ortamında da ölçeği değiştirir: jest-expo Dimensions 750×1334 + Platform ios → kısa kenar 750 ≥ 600 → SCALE 1.30 → 1.10. S2 adım 3 ResponsiveGrid testi 'rs(260)=338' gibi 1.30'a pinli literal bekliyor; S1 adım 7 testi '330 = rs(300)' 1.10'a pinli. Hangisi önce inerse diğerinin testi kırmızı. → _Hiçbir jest testi rs()-türevi LİTERAL beklemez; beklentiler `rs(…)`/`spacing.*` ile hesaplanır (S3 touch.test gibi Dimensions'ı açıkça mock'layanlar hariç). S1 önce iner; S2 ResponsiveGrid testi `expect(basis).toBe(hesapla(rs(260)))`._
- **S1 × S4:** Aynı satırlar iki pakette: TreatmentHistoryScreen.tsx:223 (S1: `maxWidth: rs(1100)`→layoutMax; S4: `<ScrollView contentContainerStyle={{…paddingBottom: spacing.xxl…}}`→View + paddingBottom sil), AiHubScreen.tsx:3642 content, DashboardScreen 158-165, KpiDashboard 281, SensorMonitor 190, Settings 883-887, AiHistory 404, Patient 361. → _S1 adım 4 ÖNCE iner (yalnız maxWidth token'ı); S4 adım 3 üstüne rebase (ScrollView→View + paddingBottom temizliği). Aynı geliştirici tek gün içinde iki commit; arada CI yeşil kanıtı._
- **S1 × S3 × S4 × S5:** SensorMonitorScreen.tsx dört paket: S1 adım 6 statsGrid→ResponsiveGrid (126, 264-277), S3 adım 5 axisChip/coilBtn→Chip (71-102, 226-256), S4 adım 3 ScrollView→View (50,147,190), S5 adım 11 chart height (119). Bölgeler ayrık ama import satırları ve styles bloğu ortak → üç yönlü rebase. → _Sıra: S1(4,6) → S4(3) → S5(11) → S3(5); her biri ayrı küçük commit, stiller bloğunda yalnız kendi anahtarlarını değiştirir; `ScrollView` import'unu S4 kaldırır, S3/S5 dokunmaz._
- **S3 × S5:** UpgradeModal ve AiSpecApprovalModal kapatma (X) düğmesi: S3 adım 3 IconButton'a göç; S5 adım 9/10 aynı JSX'i ScrollableModalCard header'ı olarak yeniden yazıyor ve `close: { minWidth: rs(44), minHeight: rs(44) }` / `hitSlop={12}` kullanıyor — rs(44) 320 px'te 37 px, S5 'kapsam-5 yan etki kapandı' iddiası YANLIŞ ve S3 kapısı ihlal sayar. → _S3 adım 1+3 (touch token + IconButton) Faz A'da önce; S5 adım 9/10 header'da `<IconButton label="Kapat">` kullanır, rs(44) YASAK (touch.min). S3 adım 3'ün UpgradeModal/AiSpec parçası S5 adım 9/10'a devredilir (dosya tek sahip: S5)._
- **S2 × S3 × S6:** Button.tsx: S2 adım 6 label flexShrink (:162), S3 adım 2 size_sm/md/lg (:153-155), S6 ilkel-16 (metin ölçeği). Button.test.tsx'e üç paket ayrı assert ekliyor. → _Faz A'da Button.tsx tek commit (S3 boyut + S2 flexShrink + S6 numberOfLines/adjustsFontSizeToFit), Button.test.tsx'te üç describe bloğu; sonraki paketler dosyaya dokunmaz._
- **S3 × S2 × S5 × S4:** S3 adım 9 statik kapı SABİT sayaç (`len(ihlal) == IHLAL_TAVANI`) — S2 rail NavButton (`railItem minWidth rs(44)` → ihlal), S5 ScrollableModalCard backdrop `Pressable` + kart `Pressable onPress={()=>{}}` (dokunma hedefi değil → ihlal/belirsiz), S5 E-stop `btnCompact rs(48)` (<52 → ihlal), S4 KAV (Pressable yok, temiz). Kapı her paketin PR'ında kırmızıya döner. → _(1) Faz A'da touch token + primitifler; yeni yazılan her Pressable `touch.*` kullanır (S2 railItem `minWidth: touch.min`). (2) ScrollableModalCard backdrop/kart Pressable'larına `// dokunma-hedefi: muaf (perde/kart — hedef değil, dokunuş yutucu)` yorumu. (3) GlobalEmergencyStop `_ILKELLER` allowlist'ine EKLENMEZ; `Math.max(touch.min, rs(48))` ile geçer. (4) Kapı Faz D'de sabit=0 ile pinlenir; Faz B/C PR'larında sabit ratchet ile güncellenir (memory: sayaç kapısı)._
- **S1 × S2 × S3 × S5:** WelcomeScreen.tsx dört paket: S1 adım 4 (206/246 maxWidth), S2 adım 7 (useWindowDimensions→useResponsive, cardWrapper), S3 adım 7 (logoutBtn :252), S5 adım 7 (insets, :32 ScrollView contentContainerStyle). S2 ve S5 aynı hook/stil bloğunu ele alıyor. → _S2 adım 7 + S5 adım 7 tek commit (S2 sahibi): hook satırı bir kez, contentContainerStyle inline dizi hem layout hem insets. S1 ve S3 tek satırlık, öncesinde iner._
- **S1 × S7:** AiProPanel.camBox (891-895) S1 adım 6(2) 16:9 + maxWidth 640 yazıyor; S7 (aihub-2, plan verilmedi) aynı stile portre 3/4 – yatay 4/3 aspectRatio + maxHeight height×0.5 + CameraView ratio='4:3' öneriyor. İki farklı oran aynı satıra; S1 'S7 önce inerse zaten yapılmış' varsayımı çelişiyor (16:9 ≠ 4:3, overlay hizası aihub-2'nin özü). → _camBox tek sahip S7 (aihub-2 overlay hizası hekim-onay öncesi organ lokalizasyonu = daha kritik). S1 adım 6(2) çıkarılır; ekranB-12'nin camBox parçası S7'ye devredilir. S1 adım 7 useStageHeight ile S7 aihub-1 `maxHeight: sahneH` sözleşmesi korunur._
- **S3 × L:** launcher/app/ui/index.html: S3 adım 12 `<style>` sonuna (satır ~398 sonrası) `@media (pointer: coarse)` + `.subactions .link.danger`; L (launcher-11 AYNI bulgu, launcher-12 680 medya bloğunu kaldırıp max-height:620 bloğu, launcher-1 main justify) aynı `<style>` kuyruğunu değiştiriyor. launcher-11 iki kökte listeleniyor. → _launcher-11 tek sahip L; S3 adım 12 L PR'ının bir commit'i olur (launcher 1.9.46). `test_launcher_ui_sozdizimi.py` `<script type="module">` çıpası korunur; S3'ün `test_launcher_dokunma_hedefi.py` L PR'ında yazılır._
- **S3 × W:** pemf-vet-web: S3 adım 11 index.css `@media (pointer: coarse){nav a…min-height}` ile W site-3 `@media (pointer: coarse){input… font-size:max(1rem,1em)}` iki ayrı blok; Header.tsx S3 (py-2.5/py-3) vs site-1 (md→lg) ve site-2 (drawer max-h); Footer S3 (`tap -my-1`) vs site-16 (grid-cols); AuthModal S3 (:331) vs site-13 (:215/224); Pricing S3 (81-85 pill) vs site-5/6/7. → _Site tek PR (W sahibi), production-hardening dalı: index.css'te TEK `@media (pointer: coarse)` bloğu (dokunma tabanı + input font-size); S3 adım 11 W'ye devredilir, S3'ün vitest kaynak-kilidi W PR'ında yazılır. Vercel preview'da 390×844 dokunmatik emülasyon._
- **S4 × S5:** S5 adım 12 kapısı allowlist `{BackupPassphraseDialog, OperatorSwitcher}` ve `len==2` — kod ön-kontrolü: OperatorSwitcher ZATEN `<ScrollView` + `maxHeight: rs(200)` taşıyor (:119, :206) → (b) ile geçer, istisna değil; S4 adım 5 BackupPassphraseDialog'a ScrollView + maxHeight '92%' ekleyince o da geçer. Sabit 2 yanlış; S4 sonrası 0 olmalı. Ayrıca S5 ScrollableModalCard KAV'ı inline `Platform.OS==='ios' ? 'padding'` yazıyor, S4 tek kaynak `KAV_BEHAVIOR_MODAL` ihraç ediyor. → _S4 (adım 1,5) Faz A/C'de S5 adım 12'den ÖNCE; kapı allowlist BOŞ, `assert len(_ISTISNA)==0`. ScrollableModalCard `import { KAV_BEHAVIOR_MODAL } from '@/hooks/useKeyboard'` (S5 adım 2, S4 adım 1'e bağımlı)._
- **S3 × S6:** MobileUpdateBanner.tsx: S3 adım 3 X → IconButton + bant gap; S6 kapsam-7 bant düzeni (büyük yazıda sütuna sarma). MobileUpdateBanner.test.tsx `getByLabelText('Güncelleme bildirimini kapat')` iki paket için de çıpa. → _Tek commit (S3 sahibi) iki değişiklik birlikte; test etiketi değişmez; S6 yalnız `maxFontSizeMultiplier`/flexWrap ekler._
- **S5 × L:** L launcher-2 min pencere yüksekliğini 440-540'a (work_area'ya göre) düşürünce WebView2 mantıksal yüksekliği <500 olabilir → S5 `isShort` PC'de tetiklenir: alt başlık gizlenir, sidebar rail'e döner (S5 açık soru 4). S1 adım 7'nin 700×540 doğrulama pini de kayar. → _Karar bu incelemede: isShort kabuk davranışı `responsive.isNative || height < 440` ile PC'de yalnız gerçekten kısa pencerede (L'nin alt sınırı 440) devreye girer; 440-540 arası PC'de rail+alt-başlık-gizli KABUL (kısa pencere kısa penceredir), S5 dokümana yazar. S1 adım 7 doğrulaması 700×540 VE 700×460'ta koşar (hook 207 px ≥ rs(180) tabanı)._
- **S1 × S7:** AiHubScreen.tsx:1436 (VisionModule) ve :3523 (CatOrganModule) imagePreviewContainer View'ına iki paket farklı stil yazıyor: S1 adım 7 `style={[styles.imagePreviewContainer, { height: sahneH }]}` (useStageHeight, 6 kullanım), S7 adım 5 `style={[styles.imagePreviewContainer, isLive && { height: undefined, minHeight: rs(200) }]}` + onLayout. S7 kilidi 'statik modda rs(300) SABİT kalır' derken S1 aynı kutuyu sahneH yapıyor; xaiIsiHaritasiBoyut.test rs(300) literaline PİNLİ DEĞİL (doğrulandı: 'sayısal yükseklik veya aspectRatio' ölçüyor). → _TEK birleşik ifade, sıra S1 adım 7 → S7 adım 5: `style={[styles.imagePreviewContainer, { height: sahneH }, isLive && !autoAdjust && { height: undefined, minHeight: rs(200) }]}` + onLayout. Dal sahipliği: canlı telefon-kamera dalı S7 (açık px kutu, kameraKutusu), statik + sunucu-karesi (autoAdjust) dalı S1 (sahneH). S7 kilit metni 'statik = sahneH (S1 adım 7)' olarak düzeltilir; xaiStage/scStage S1'de kalır. AiProPanel.camBox tek sahip S7._
- **S7 × S6 × S3 × Faz B (AppShell):** S7 adım 10 kapısı pf/src genelinde `fontSize: rf(9|10)` SIFIR eşleşme istiyor; grep ile 17 nokta var ve yalnız 5'i S7 dosya listesinde. Dışarıda kalanlar: CoilParameterPanel (:346, :365, :429) ve SessionProgressCard (:242, :254) → S6 adım 4 dosyaları; AppShell (:621 wsTextOff, :648 notifBadgeText, :686 bottomLabel) → Faz B kabuk PR'ı; ControlScreen :1015 ve AiReviewControls :154/:166 hiçbir planda yok. Kapı ilk koşuda kırmızı. → _Sahip S7, üç katman: (a) AppShell'deki 3 nokta Faz B kabuk PR'ında (bottomLabel S6 adım 3 ile aynı commit; notifBadgeText rf(9)→typography.small rozet genişliği ekran görüntüsüyle doğrulanır); (b) CoilParameterPanel/SessionProgressCard noktaları S6 adım 4 commit'inde; (c) kalan 9 nokta S7 adım 10. Kapı Faz D'de sabit=0; Faz C boyunca SABİT SAYAÇ ile ratchet. `rfMin` yardımcısı EKLENMEZ (typography.small/caption tek desen)._
- **S1 × S4 × S5 × S3 × S7:** SensorMonitorScreen.tsx beş paket: mevcut sıra S1(4,6)→S4(3)→S5(11)→S3(5); S7 adım 2(d) aynı chartArea bloğunu (111-121) yatay ScrollView'a sarıyor, `useResponsive` import'u ve S4'ün KALDIRDIĞI `ScrollView` import'unu geri getiriyor; S5 adım 11 aynı RealtimeChart JSX'inin height satırını, S7 width satırını değiştiriyor. S4'ün test_kabuk_ic_scrollview_kapisi.py `<ScrollView` arıyorsa yatay ScrollView'ı ihlal sayar (AiHistory yatay çipleri de aynı sorunu yaşar). → _Sıra S1→S4→S5→S3→S7, her biri ayrı commit. S7 `<ScrollView horizontal` kelimesini AÇILIŞ ETİKETİYLE AYNI SATIRA yazar; S4 kapı regex'i `<ScrollView(?![^>]*\bhorizontal\b)`. RealtimeChart JSX'inde width/height tek yerde: `width={grafikW} height={grafikH}` (S5 grafikH, S7 grafikW). S2 sonrası isCompact içerik-farkında → 768 dikey tablette yatay kaydırma da açılır: KABUL, dokümana yazılır; S7 testleri ortak responsiveMock ile._
- **S3 × L:** launcher-11 L'ye devredildi ama İÇERİK çelişiyor: S3 adım 12 coarse listesinde `.chip` ve `.pw-toggle` var, `.link.danger { flex-basis:100% }` HER cihazda; L adım 2 listesi `.seg button,.hbtn,.link,.mbtn,.ctlbtn`, `.link.danger { margin-left:auto }` yalnız coarse. `.chip` TIKLANABİLİR DEĞİL (renderChips span, onclick yok — doğrulandı); `.pw-toggle` (şifre göster) tıklanabilir ve L listesinde yok. → _Tek blok (L adım 2): `.seg button, .hbtn, .link, .mbtn, .ctlbtn, .pw-toggle { min-height:44px }`, `.chip` çıkarılır; danger için tek kural coarse altında `.subactions .link.danger { flex-basis:100%; justify-content:center; margin-top:4px }` (ayrı satır), fare düzeninde değişmez. S3'ün test_launcher_dokunma_hedefi.py YAZILMAZ; kural L adım 9 test_launcher_responsive_kapisi.py içinde tek test._
- **S3 × W:** S3 adım 11 `.tap` (@layer components, 44 px HER cihazda) + `@media (pointer: coarse){ nav a, footer a, .pill-toggle button {min-height:44px} }`; W adım 4 katmansız coarse INPUT bloğu, W adım 10 Footer `inline-block py-1.5` (32 px), W adım 7 pill `py-2.5` (40 px), W adım 5/9 `inline-flex min-h-11`. İki ayrı coarse bloğu ve iki farklı Footer hedef değeri. → _TEK katmansız `@media (pointer: coarse)` bloğu (W adım 4): input 16 px kuralı + `nav a, footer a, .pill-toggle button, [role=menu] button { min-height:44px; padding-block:.625rem }`. `.tap` sınıfı EKLENMEZ. Footer: fare 32 px (W), coarse 44 px (blok). Pricing pill sarmalayıcıya `pill-toggle`. S3'ün dokunma-hedefi.test.ts yazılmaz; W adım 12 responsive-kapilari.test.ts coarse bloğunda `footer a` ve `nav a` seçicilerini pinler._
- **L × mevcut test tests/test_baslat_kapisi_etiket.py:** L adım 5 applyLang() içine `etiketle("btn-web", x.web)` … 4 çağrı ekliyor. test_baslat_kapisi_etiket.py applyLang'ı `_fonksiyon` ile çıkarıp Node'da sahte `$` (setAttribute'suz nesne) ve stub'larla koşturuyor; `etiketle` harness'te tanımsız → ReferenceError → MEVCUT KAPI KIRMIZI. → _Aynı L commit'inde harness güncellenir: `function etiketle() {}` stub'ı + `$` nesnesine `setAttribute() {}`. Alternatif (harness'e dokunmadan): applyLang içinde `if (typeof etiketle === "function")` — show() içindeki `typeof startKapisiAc` deseni. Tercih: harness güncelle; L adım 9 statik kapısı dört `etiketle("btn-…"` çağrısını sayar._
- **L × mevcut cargo testi guncelleme_ekrani_sirasi_ve_acilis_bekcisi:** L adım 4 doğrulaması '`fn main()` gövdesinde (setup yoluyla) show() var' diyor; oysa show() ayrı `fn pencereyi_calisma_alanina_sigdir` içinde olacak → `fn main()` gövde araması boş döner. Mevcut test yalnız `kip < bekçi < Builder` sırasını ölçüyor (main.rs:2397-2413), `.setup` eklenmesi onu bozmaz. → _Genişletilmiş test iki çıpa: (1) `fn main()` gövdesinde `.setup(` ve `pencereyi_calisma_alanina_sigdir(` çağrısı; (2) `fn pencereyi_calisma_alanina_sigdir` gövdesinde `set_size(` < `center()` < `show()` ve show()'un `if let` bloğunun DIŞINDA (koşulsuz) olduğu. gunc kipinde `set_size(` < `eval(` < `show()`. KARŞIT-KANIT: show() satırı silinince kırmızı._
- **W × Tailwind v4 üretim sırası:** W adım 2 drawer için `max-h-[calc(100vh-4rem)] max-h-[calc(100dvh-4rem)]` 'vh sınıfı ÖNCE yazılır' diyerek fallback kuruyor. Tailwind v4'te üretilen CSS sırası HTML'deki sınıf sırasına DEĞİL aday adına göre: ÖLÇÜLDÜ (tailwindcss 4.3.2 compile → dvh kuralı ÖNCE, vh SONRA) → vh her tarayıcıda kazanır, dvh HİÇ uygulanmaz; W adım 12 kapısı yine yeşil görünür. → _Yalnız `max-h-[calc(100dvh-4rem)]` (dvh Chrome 108 / Safari 15.4+) ya da index.css'te `@layer components { .drawer-kutu { max-height: calc(100vh - 4rem); max-height: calc(100dvh - 4rem); } }`. W adım 12 kapısına `max-h-[calc(100vh-4rem)]` YOKLUĞU eklenir. AuthModal `max-h-[calc(100svh-2rem)] sm:max-h-[calc(100dvh-2rem)]` varyantlı → sorun yok._
- **S5 × L:** isShort PC'de `height < 440` ile L adım 8 sınır durumu: 1366@%150'de app penceresi min yüksekliği tam 440 (wa 480−40) → `height < 440` false → S5 kısa-kabuk davranışı tam 440 px'te devreye girmez. → _S5 eşiği `height <= 440` ya da L PAY 40→48 (pencere 432). Tercih: L PAY sabit kalır, S5 `<=`; S1 adım 7 doğrulama pini 700×540 + 700×460 + 911×440._
- **S1 × S4 × S7:** KpiDashboardScreen.tsx: S1 adım 4 (:281 maxWidth), S4 adım 3 (:188/:276 ScrollView→View), S7 adım 3 (148-183 chartsSection + styles 292-319, tableCard `maxWidth: rs(720)`). DemaSimulatorScreen.tsx: S1 adım 4 (:126), S3 adım 3 (yenile IconButton), S7 adım 10 (:187) + adım 11 (15-60). SessionDetailModal.tsx: S1 adım 4 (:554), S6 adım 6 (tablo hücreleri), S7 adım 1 (TempChart 406-441, :638). AiSpecApprovalModal.tsx: S5 adım 10 ScrollableModalCard'a YENİDEN YAZIYOR, S7 adım 10 aynı stil bloğunda metaLabel/rel/xai/th. → _Dosya-sahibi sırası korunur: S1→S4→S7 (Kpi), S1→S3→S7 (Dema), S1→S6→S7 (SessionDetail), S5→S7 (AiSpec). S7 çıpaları satır numarasına değil stil ANAHTARINA pinlenir (`metaLabel:`, `tableCard:`, `chartWrap:`); S7 adım 3 tableCard `rs(720)` S1 kapısıyla uyumlu (<800). AiHubScreen'de regen YOK, cerrahi edit._

**Hasta güvenliği notları:**

- ACİL DURDUR bileşenine (GlobalEmergencyStop.tsx) YALNIZ S5 adım 4 dokunur; onPress/performEmergencyStop/render koşulu/zIndex 10000/pointerEvents değişmez; compact yalnız genişlik/konum. minHeight tabanı touch.min ile ≥44 her ölçekte (0.85'te rs(48)=41 tuzağı kapatıldı). Klavye açıkken ASLA gizlenmez, klavyenin üstüne taşınır (S4 kararı korunur).
- Faz B kabuk PR'ı yayın öncesi PEMF_SIMULATE=1 ile ÜÇ kabuk × klavye × yatay matrisinde 'hasta seç → Seans Başlat → E-stop tek dokunuş → simülatörde running=0 → geçmişe kayıt' turu ŞART; ekran görüntüsü kanıtı docs/screenshots'a.
- ekranB-2 (YÜKSEK, hasta güvenliği) HİÇBİR PAKETTE YOK: STM 'offline' raporlayınca normalizeStmCoils bobinleri running:false yapıyor → kayan E-stop kayboluyor, sayfa-içi E-stop 8 kart altında ~3000 px derinde. Bu bulgu responsive değil davranış hatasıdır; ayrı, ÖNCELİKLİ bir P0 paket (S0) olarak Faz B'den ÖNCE ele alınmalı: E-stop görünürlüğü `stm==='offline' && sonBilinenRunning>0` iken de sürsün + sayfa-içi E-stop sekme içeriğinin ÜSTÜNE. ekranA-15 (Dashboard kart-içi E-stop yazısı typography.small, 44 altı) da aynı pakete.
- CoilSelector (S3 adım 6) yanlış bobin seçimi riski: hitSlop ≤ gap/2 kuralı; seans sürerken seçicinin kilitli olduğu mevcut davranış coilDurdurmaOnayi/CoilDurationHonesty testleriyle korunur; 320 px cihazda 8×10 dokunuş 10/10 kanıtı.
- AiSpecApprovalModal (S5 adım 10) hekim onay kapısı: onApprove/onDismiss semantiği değişmez; 'Onayla ve Başlat' ScrollView DIŞINDA (yapısal test) — onaysız tedavi başlamaz değişmezi aiHubOtonomOnayKapisi.test ile kilitli kalır.
- AiProPanel 'Vazgeç' (hazırlık iptali, S3 adım 5) Chip'e göçerken onPress kimliği AiProPanelB1.test + test_ai_pro_asamali_akis ile doğrulanır.
- ObservationNotesModal (S4 adım 4) tıbbi kayıt: bobin running iken gizlenme + sıfırlamama sözleşmesi (gozlemNotuKorunmasi.test) değişmez; Atla/Kaydet ScrollView dışında.
- Welcome 'Çıkış' ve Settings 'Farklı Profile Geçiş' teardown yolları (S2/S3/S5 Welcome edit'leri) guardTeardown'a dokunmaz; AppShell.logout.test GERÇEK useTeardownGuard ile kilitler.
- Bağlantı durumu 2-durumlu, profil kalıcılığı yok, PII maske opt-in, backend safety-limit tekrar eklenmez — hiçbir paket bu sahip kararlarına dokunmuyor (doğrulandı). Yeni native modül eklenmiyor (EAS/APK zinciri sabit).
- Geri alma: her adım ayrı commit, `git revert` (checkout ile DEĞİL); tavanlar tek satır (OLCEK_TAVAN_BUYUK_EKRAN=1.30, MAX_FONT_SCALE=Infinity, KAV enabled={false}).
- AI PRO ORGAN OVERLAY (tıbbi karar ekranı): kutu oranı backend image_w/h'den türer; backend `IMREAD_COLOR` EXIF yönelimini UYGULUYOR (ölçüldü) → overlay ve canlı önizleme aynı yönelimde. Mikroservis (:8100) yolunda boyut PIL lazy size ile ALINMAZ (ham/döndürülmemiş → portre karede w/h ters → hizasızlık). Hekim onayı öncesi lokalizasyon ekranı olduğundan S7 adım 7 cihaz testi (kayma ≤%2, yönelim, mikroservis profili) geçmeden APK/OTA yayını YOK.
- E-STOP ERİŞİMİ (AI Pro): kayan ACİL DURDUR yalnız bobin running iken çizilir; HAZIRLIK aşamasında tek E-stop ControlScreen sayfa-içi düğme (:732) AiProPanel'in ALTINDA. S7 adım 6 kutuyu büyütür → tavan Math.min(0.5×yükseklik, rs(420)); 320×568'de hazırlık→seans geçişinde kayan E-stop kaydırmasız görünür olmalı (cihaz kapısı).
- AiProPanel'de yalnız stil/sarmalayıcı değişir; start/stop/capture/ownedRef/interval ve test_ai_pro_asamali_akis çıpaları birebir korunur; PR'da test_ai_pro_* tam koşar.
- Backend yalnız-EK alanlar (image_w/h, imageW/H); auth-muafiyet, allowlist, route-contract sayacı, safety-limit değişmez.
- LAUNCHER: `.setup` halkası `on_window_event Destroyed → safe_stop_coils → kill` sırasına dokunmaz; `visible:false` + KOŞULSUZ show() JS'ten bağımsız (2026-08-29 'JS ayrıştırılamadı' sınıfı görünmez donmaya dönüşmez); Escape confirm'de HİÇBİR geri çağrı çalıştırmaz (resume onayı noCb=discard_pending 1,4 GB siler); inert closeModal'da koşulsuz kalkar + boot() sigortası.
- SİTE: indirme kapısı ve auth akışı değişmez (download-gate-wiring); `maximum-scale` eklenmez; dış istek yok (KVKK); FREE_MODE/jeton metinleri değişmez.
- RealtimeChart 'akışı durmuş bobin sağ uca ulaşmaz' dürüstlük değişmezi ve ortak zaman penceresi S7 adım 2'de dokunulmaz — yalnız PAD/DPR.

**Regresyon riskleri ve kilitleri:**

- E-STOP OFSETİ (Faz B): üç dallı bottomOffset ifadesi yanlış birleşirse klavye açıkken/yatayda düğme alt barın veya klavyenin altında kalır. Kilit: AppShell.klavye.test (keyboardDidShow→offset===yükseklik, hide→rs(76)), AppShell.landscape.test (isShort→rs(60), compact=true), GlobalEmergencyStop.test (compact/normal: bulunur + press→performEmergencyStop + minHeight≥44 320 mock'ta); cihaz C4 PEMF_SIMULATE=1.
- E-STOP 44 ALTI: S5 `btnCompact minHeight rs(48)` 0.85 ölçekte 41 px (<44). Kilit: `Math.max(touch.min, rs(48))` + S3 kapısı GlobalEmergencyStop'u allowlist DIŞINDA tarar + touch.test 320 mock'unda GlobalEmergencyStop flatten minHeight ≥ 44.
- JEST ÖLÇEK KAYMASI: S1 sonrası jest-expo ortamında SCALE 1.30→1.10; rs literal'ine pinli her test (mevcut 75 dosyada grep `toBe(\d+)` ile rs kaynaklı olanlar) kırmızıya döner. Kilit: Faz A2 PR'ında TAM jest süiti; beklentiler rs()/spacing ile hesaplanır.
- SWIPE-GEZİNME: KAV'a geçişte `panHandlers` spread'i ya da `&& isNative` düşerse telefonda sekme kaydırma kaybolur / web'de fare sürüklemesi sekme değiştirir. Kilit: AppShell.logout.test (mevcut swipe senaryosu) + AppShell.rail.test ({bottom,isNative:false}→responder prop yok) + S2 Python regex.
- desktop SEMANTİĞİ: `desktop = shellKind !== 'bottom'` — getShellKind height parametresiyle rail'e düşen 926×428 yatay telefonda desktop=true → alt bar yok, E-stop offset 0, paddingBottom rs(84). Kilit: layout.test tablo satırı (926,428,native)→rail ve landscape testinde 'Daha Fazla' YOK + E-stop render.
- ÇIPA KAYMASI (Python): test_surum_kaymasi_guvenlik_sozlesmesi `<SurumFarkiBanner />` string'i AppShell'de aynen kalmalı (S2 adım 4 ScrollView yeniden yapılandırırken satır taşınabilir ama metin değişmez). Kilit: Faz B PR'ında `pytest tests -k 'surum or responsive or kabuk or dokunma or modal'` + tam süit (E-stop bekçi sızıntısı dışlama kuralı).
- İÇ SCROLLVIEW → VIEW (S4 adım 3): AiHub `container:{flex:1}` içindeki lazy modüller ve PatientScreen `flex:1` View'da yükseklik 0'a çökebilir (ScrollView contentContainer'da flex:1 etkisizdi, düz View'da değil). Kilit: aiHubAccordion/aiHubOtonomOnayKapisi + crashGuards testleri ve 390×844/1280×800 ekran görüntüsü; `flex:1` container'lar S4'te KALDIRILIR (yorum: 'AppShell kaydırır').
- S5 MODAL KAPISI YANLIŞ-KIRMIZI: AppShell `<Modal` içeriyor, bugün maxHeight 0 — kapı S5 adım 5 (moreSheet maxHeight) inmeden yazılırsa kırmızı; BackupPassphraseDialog S4 adım 5 inmeden kırmızı. Kilit: Faz D sırası, allowlist=0 sabit sayaç.
- S3 RATCHET SAYACI: Faz B/C'de eklenen her Pressable sayacı oynatır → CI kırmızı. Kilit: her PR açıklamasında 'IHLAL_TAVANI N→M' satırı; PR CI'da kapı koşar; belirsiz sınıfı kırmızı yapmaz.
- S6 injectFont ERKEN DÖNÜŞ: `if (flat.fontFamily) return props;` (fonts.ts:51) ÖNCESİNE eklenmezse ikon-fontlu Text'ler tavansız kalır; `applyGlobalInter()` jest'te çağrılmadığından test doğrudan `injectFont` üzerinde. Kilit: fonts.test (export edilen injectFont: fontFamily'li Text için de maxFontSizeMultiplier===MAX_FONT_SCALE; yerel prop ezilmez; allowFontScaling=false hiç yok pytest).
- TELEFON DEĞİŞMEZLİĞİ (S1): native kısa kenar <600 için formül birebir; mutasyon `_buyukEkran` dalını silince web satırı kırmızı. Kilit: tokens.olcek.test 9 satır + 375/430 kareleri piksel-eş (Faz G).
- TESTLERDE useResponsive MOCK EKSİK ALANI: `shellKind` undefined → `desktop=false` → masaüstü testleri alt bar bekler ve KIRILIR. Kilit: ortak responsiveMock yardımcısı, `isShort === true` savunmacı okuma; AppShell içinde `shellKind ?? (isDesktop||isTablet ? 'sidebar' : 'bottom')` geri-uyum satırı.
- CI YOL FİLTRESİ: frontend.yml yalnız pf/** — Python kapıları tests.yml'de filtresiz koşar (doğrulandı); site ve launcher hatları ayrı. Kilit: test_ci_workflow_gate.py mevcut; yeni kapı dosyaları tests/ altında conftest ile otomatik toplanır.
- PRE-COMMIT FORMATLAYICI: çok dosyalı Faz B/C commit'lerinde formatlayıcı dosyayı değiştirince commit sessizce iptal olur. Kilit: her commit sonrası `git log -1` + `git status` (AM/MM → re-add).
- RealtimeChart DPR: `canvas.width` ataması context durumunu sıfırlar → canvasBoyutla lineJoin/lineCap'ten ÖNCE, setTransform her draw'da; dpr>3 bellek (~5 MB) — `Math.min(3, dpr)`.
- chart-kit PieChart merkezi: yanlış paddingLeft → pasta kart dışına taşar (overflow:hidden sessiz kırpma) → ekran görüntüsü + `paddingLeft === String(Math.round(chartW/4))` testi.
- S7 adım 10 rf(9/10) kapısı: 17 noktanın 12'si başka paketlerde → sabit sayaçsız yazılırsa Faz C boyunca CI kırmızı; notifBadgeText rf(9)→11 rozet taşması.
- Tailwind v4 sınıf sırası (ölçüldü): iki aynı-özellikli arbitrary sınıf → aday adı sırası, HTML sırası değil → vh/dvh fallback illüzyonu; kapı yanlış-yeşil.
- Launcher applyLang harness (test_baslat_kapisi_etiket.py) `etiketle` ReferenceError / `setAttribute` yok → mevcut kapı kırmızı; aynı commit'te stub.
- Launcher kart button: `<div class=meta>` button içinde geçersiz → span; `width:100%`/`text-align:left` unutulursa kartlar daralır/ortalanır.
- inert takılı kalma → tüm launcher arayüzü ölü (fare dahil); closeModal koşulsuz + boot() sigortası + Node birim testi 'iki modal açıkken biri kapanınca inert kalır' karşıt-kanıtı.
- `visible:false`: show() monitör okunamasa da koşmalı; macOS/Linux paketleri doğrulanmadı.
- L adım 3 min pencere 440-460 ↔ S5 isShort: 440-460 PC'de rail + alt başlık gizli (kabul); tam 440 sınırında `<` vs `<=`.
- Site Header lg: 768-1023 tablet hamburger görür (sahip UX kararı).
- W adım 6 `html{color-scheme:dark}` yerel select/date kontrolleri koyulaşır; Odeme formu görüntüsü.
- S7 adım 5 `ratio="4:3"`: Android önizleme FILL→FIT; 16:9 sensörlü cihazlarda ResolutionSelector 4:3'e düşer (cihazda ölçülmeli); iOS/web'de yok sayılır.
- S7 adım 2(d) yatay ScrollView: S4 kapı regex'i `horizontal`ı muaf tutmazsa kırmızı.
- S7 adım 4 mikroservis yolu ek decode (~1-3 ms) — PIL lazy KULLANILMAZ; `test_ai_mikroservis_modalite_kapisi` mock delegate_infer ile alan eklenmesi test edilir.
- L adım 10 windows-latest'te msedge var → kapı CI'da koşar; deterministik değilse yanlış-kırmızı; opt-in bayrağı olmadan 'sessizce yeşil' riski.
- Pre-commit formatlayıcı çok dosyalı commit'i sessizce iptal edebilir → `git log -1` doğrula.

**İncelemede düzeltilen plan adımları (uygulamada bu düzeltmeler esastır):**

- S1 adım 3: İPTAL — sidebar genişliği AppShell'de inline sabit yerine S2 adım 1 theme/layout.ts'te tek kaynak (SIDEBAR_WIDTH=240, SIDEBAR_WIDTH_TABLET=200, RAIL_WIDTH=72, ölçeksiz). Adım 5 Python kapısı `KENAR_CUBUGU_GENISLIK` yerine layout.ts'te `SIDEBAR_WIDTH\s*=\s*240` ve AppShell'de `width: rs(248)` yokluğunu pinler.
- S1 adım 6: (2) camBox değişikliği ÇIKARILIR — aihub-2 (S7) aynı stili portre 3/4 / yatay 4/3 + maxHeight ile çözüyor; 16:9 overlay hizasını bozar. ekranB-12'nin camBox parçası S7'ye devredilir. (3) SensorMonitor ResponsiveGrid `minItemWidth={160}` S2 adım 3 sonrası rs(160) ile ölçeklenir — 1.10 tavanda 176 px, 1920'de 4+4 korunur; test beklentisi rs() ile.
- S1 adım 7: Jest beklentisi '1080 → 330 (=rs(300), 1.10)' S1 adım 1 inmeden 390'dır; test `rs(300)` ile hesaplasın. Doğrulama pini 700×540'a ek 700×460 (L min pencere kararı).
- S1 adım 2: `jest.doMock('react-native')` tokens.ts'in yeni `breakpoints` import'unu etkilemez (breakpoints RN import etmiyor) — doğru; ancak S3 touch.test aynı modülü `jest.spyOn(Dimensions,'get')` ile mock'luyor: iki yaklaşım tek yardımcıda (`olcekYukle(w,h,os)`) birleştirilsin.
- S2 adım 1: `SIDEBAR_WIDTH = rs(248)`, `RAIL_WIDTH = rs(72)` → ölçeksiz 240/72 + tablet 200 (S1 kararı; PC'de 322 px sidebar sorunu S1 tavanıyla değil bu sabitle çözülür). `getShellKind(width, isWeb, height)` üç parametreli: `kind==='sidebar' && height < shortHeight → 'rail'` (S5 açık soru 5 kapanır). layout.test'e (926,428,native)→rail satırı.
- S2 adım 3: Test beklentileri 'rs(260)=338' gibi literal DEĞİL, `rs(260)` ile hesaplanır (S1 sonrası jest ölçeği 1.10). `unit = rs(minItemWidth) + 2*spacing.sm` — spacing.sm de rs'li, tutarlı.
- S2 adım 4: (b) panHandlers koşulu KAV'a taşınır (S4 adım 2 ile aynı satır): `<KeyboardAvoidingView … {...(!desktop && responsive.isNative ? panResponder.panHandlers : {})}>`. (d) NavButton `railItem: { minWidth: touch.min, minHeight: touch.min }` (rs(44) YASAK — S3 kapısı). (f) mock güncellemesi ortak responsiveMock yardımcısından. GlobalEmergencyStop satırı 'dokunulmaz' yerine Faz B birleşik ifadesi.
- S2 adım 8: Python kapısı (2) regex'i KAV satırında da eşleşmeli: `KeyboardAvoidingView[^\n]*isNative|panHandlers[^\n]*isNative` — spread satırı KAV açılış etiketinin devamında olabilir; regex re.S ile etiket bloğunu tarasın.
- S3 adım 3: UpgradeModal ve AiSpecApprovalModal X göçü S5 adım 9/10'a devredilir (o adımlar header'ı IconButton ile yazar). S3 adım 3 yalnız AppShell/PatientGate/MobileUpdateBanner/SurumFarkiBanner/DemaSimulator/TreatmentHistory. kabuk-3 (headerRight taşması) adım 8'e eklenir: isCompact'ta OperatorSwitcher çipi ikon-only + headerLeft minWidth '40%'.
- S3 adım 9: Kapı Faz D'de sabit=0 ile pinlenir; Faz B/C PR'larında ratchet. `_ILKELLER` allowlist'ine GlobalEmergencyStop EKLENMEZ (Math.max(touch.min, rs(48)) ile geçer). ScrollableModalCard backdrop/kart Pressable'ları 'muaf (perde/kart dokunuş yutucu)' yorumuyla. Açık soru 5 kapanır: tests.yml yol filtresiz (doğrulandı, .github/workflows/tests.yml:20) → pf/ değişince zaten koşar; frontend.yml'ye ek adım gerekmez.
- S3 adım 11: W (site) PR'ına devredilir; index.css'te site-3 ile TEK `@media (pointer: coarse)` bloğu. Test dosyası `pemf-vet-web/src/components/__tests__/` mevcut (doğrulandı), vitest 4.
- S3 adım 12: L (launcher 1.9.46) PR'ına devredilir; launcher-12'nin 680 medya bloğu kaldırması ile aynı `<style>` kuyruğu. test_client_arayuz_sade_dil.py index.html'de 'Client' kelimesini yasaklıyor — yeni CSS yorumlarında 'client' geçmesin.
- S3 adım 13: 'kapattığı' listesinden site-11 ve launcher-11 W/L paketlerine taşınır; ekranC-4 (sil ikonu 26 px) ve ekranA-15 (kart-içi E-stop yazı/yükseklik) S3 kapsamına eklenir.
- S4 adım 2: `enabled={responsive.isNative}` — mock'larda isNative yoksa undefined → RN varsayılanı true (zararsız) ama ortak mock'a eklenir. bottomOffset ve panHandlers satırları Faz B birleşik ifadesiyle (S2/S5). Kilit 'paddingBottom rs(160)+insets.bottom KORUNUR' → 'paddingBottom ≥ bottomOffset + E-stop yüksekliği' (S5 isShort rs(120) ile uyumlu).
- S4 adım 3: AiHub `container:{flex:1}` ve Patient `container:{flex:1}` 'dokunulmaz' DEĞİL — ScrollView contentContainer'da etkisizdi, düz View'da lazy modül yüksekliğini 0'a çekebilir; kaldırılır (yorum: AppShell kaydırır). Kapı (2) TextInput içeren dosyalarda dikey ScrollView: AppShell/NotificationCenter'da TextInput yok (doğrulandı) → S5 moreSheet ScrollView'ı etkilenmez.
- S4 adım 5: S5 adım 12 kapısı bu adıma bağlı: BackupPassphraseDialog ScrollView+maxHeight aldıktan sonra S5 allowlist BOŞ (OperatorSwitcher ZATEN :119/:206'da ScrollView+maxHeight taşıyor — S5'in '2 istisna' sayımı bugün bile yanlış).
- S5 adım 2: KAV behavior inline `Platform.OS==='ios' ? 'padding'` yerine `import { KAV_BEHAVIOR_MODAL } from '@/hooks/useKeyboard'` (S4 adım 1 tek kaynak; Android Modal penceresi adjustResize gerekçesi orada). Backdrop ve kart Pressable'larına S3 muaf yorumu.
- S5 adım 3: (d) sidebarRail/NavButton compact={rail} SİLİNİR — rail görünümü S2 adım 4 `rail` prop'u (ikon-only); S5 yalnız getShellKind height parametresiyle koşulu genişletir. `rail = desktop && isShort` yerine `rail = shellKind==='rail'`. (e) bottomItem `minHeight: touch.min` (rs(44) 320'de 38 px, S3 kapısı ihlal). Landscape testi `getByText('Ayarlar')` → `getByLabelText('Ayarlar')`. (g) bottomOffset Faz B birleşik ifadesi.
- S5 adım 4: `btnCompact.minHeight: rs(48)` 0.85 ölçekte 41 px → HASTA GÜVENLİĞİ ihlali ('ASLA 44 altı' iddiası yanlış). `minHeight: Math.max(touch.min, rs(48))` (S3 adım 1'e bağımlı). Test: Dimensions 320 mock'unda flatten minHeight ≥ 44. Diğer paketlerin 'GlobalEmergencyStop.tsx dokunulmaz' kilitleri 'yalnız S5 adım 4 commit'i' olarak güncellenir.
- S5 adım 9: `close: { minWidth: rs(44), minHeight: rs(44) }` 320'de 37 px — kapsam-5 KAPANMAZ; `<IconButton label="Kapat">` (S3 adım 3 primitifi, touch.min). Aynı düzeltme adım 10 header X (`hitSlop={12}` + rs(20) ikon) için.
- S5 adım 12: Allowlist `{BackupPassphraseDialog, OperatorSwitcher}` + `len==2` YANLIŞ: OperatorSwitcher bugün zaten geçer; S4 adım 5 sonrası BackupPassphraseDialog da geçer → `_ISTISNA=set()`, `assert len==0`. AppShell `<Modal` içerdiğinden kapı adım 5 (moreSheet maxHeight) inmeden kırmızı — Faz D'de yazılır.
- S5 adım 13: Bulgu JSON'una 'durum' alanı YAZILMAZ (şemada yok, ikinci doğrulama tek kaynağı); durum satırı docs/responsive-denetim-2026-09-04.md'ye.
- S6 adım 2: Plan metni kesik geldi; doğrulanan: fonts.ts:51 `if (flat.fontFamily) return props;` — tavan bu satırdan ÖNCE `out = {...props, maxFontSizeMultiplier: props.maxFontSizeMultiplier ?? MAX_FONT_SCALE}` ile, `allowFontScaling === false` ise atla; sonraki tüm return'ler `out` tabanlı. applyGlobalInter jest'te çağrılmadığından test doğrudan export edilen injectFont üzerinde. Web'de RNW prop'u filtreler (no-op) — doğru.
- S6 adım 0: AppShell alt bar kısa etiketleri (kabuk-5) Faz B kabuk PR'ına dahil; S3 adım 8 ile aynı stil bloğu (bottomItem/bottomLabel). CoilParameterPanel (ekranB-8) tek sahibi S6 — ekranB-1'in header flexWrap parçası da buraya.
- S7 adım 4: Tasarım kararının gerekçesi YANLIŞ: 'cv2.imdecode EXIF'i yok sayar' — ÖLÇÜLDÜ (cv2 4.11.0, gömülü python): Orientation=6 JPEG 200×100 → `cv2.imdecode(..., cv2.IMREAD_COLOR)` (h,w)=(200,100) yani EXIF UYGULANIYOR; `_decode_image` tam bu bayrağı kullanıyor (ai_router.py:206). Sonuç lehte (image_w/h ekran yönelimli) ama iki düzeltme şart: (1) PIL lazy `.size` HAM/döndürülmemiş boyut verir → mikroservis yolu için `_kare_boyutu_ekle` PIL header'dan DEĞİL `cv2.imdecode(IMREAD_COLOR)` ya da `ImageOps.exif_transpose` ile ölçmeli, aksi hâlde portre karede w/h TERS gelir (tıbbi ekranda hizasızlık); (2) landmark (:527) `b64_image`in kaynağı hangi dizi ise onun shape'i; segmentation/thermal `_encode_jpg_b64(img)` küçültmüyor → `img.shape`. Yanıtlar yalnız-ek. Kanıt tests/test_ai_kare_boyutu.py'ye EXIF-6 sentetik JPEG testi olarak eklenir (mutasyon: IMREAD_IGNORE_ORIENTATION verilince kırmızı).
- S7 adım 5: (a) Stil ifadesi S1 adım 7 ile birleşik (çakışma 1). (b) `AiResult` arayüzüne (AiHubScreen.tsx:149-176) `image_w?: number; image_h?: number` EKLENMELİ — `result.image_w` TS strict'te derlenmez. (c) catOrganCanliKalinti mock'u `CameraView: () => null` → `ratio` prop'unu ölçmek için `(p) => React.createElement('CameraView', p)`; `UNSAFE_getByType` ile ratio '4:3' okunur. (d) AiHub kare akışı `skipProcessing:true` ama `shrinkForUpload` üzerinden geçiyor ve backend EXIF uyguluyor → yönelim tutarlı; adım 7 protokolüne 'portre/yatay yönelim' satırı eklenir. (e) `Image.getSize` fallback web'de data: URI ile çalışır; jest mock xaiIsiHaritasiBoyut'ta var.
- S7 adım 6: (a) AiProPanel :599 `takePictureAsync({ base64:true, skipProcessing:true })` → EXIF'li HAM JPEG backend'e; backend IMREAD_COLOR EXIF'i uyguladığından image_w/h ekran yönelimli. (b) `FrameResult` tipine `image_w?/image_h?`, LiveDataContext `AiVisionData` tipine `imageW?/imageH?` eklenir — `(v as any)` YAZILMAZ. (c) flipBtn `width/height: rs(44)` S3 kapısında İHLAL (320 px'te 38 px) → `touch.min`; AiHub flipCameraBtn (:3677) de aynı — plan 'zaten rs(44)' diyor, yanlış. (d) camBox `height: rs(200)` kaldırılınca placeholder için `minHeight: rs(160)` + `justifyContent:'center'`. (e) HASTA GÜVENLİĞİ: ControlScreen sayfa-içi ACİL DURDUR (:732) AiProPanel'in ALTINDA; kutu büyüyünce aşağı iner. Kayan E-stop yalnız bobin running iken görünür → HAZIRLIK aşamasında tek E-stop sayfa-içi olan → tavan `Math.min(0.5×ekranH, rs(420))` + 320×568'de kaydırma mesafesi ölçülür; gerekirse 0.4. (f) test_ai_pro_asamali_akis çıpaları (`}, [hazirlik, mobileResult, organId, duration]);` ve HAZIRLIK_TAVAN_MS bloğu 6-boşluk kapanış) korunur.
- S7 adım 7: 'Başarısızsa pictureSize ile eşitle' notu: expo-camera 56 `pictureSize` verilince `ratio` YOK SAYILIR → ikisi birlikte verilmez. Protokole eklenir: (1) kare yönelimi (portre telefon → image_h > image_w; ters gelirse backend EXIF yolu bozuk), (2) mikroservis (:8100) profili ayrı ölçüm (PIL lazy tuzağı), (3) hazırlıkta sayfa-içi E-stop'a kaydırma mesafesi. Test HAZIRLIK modunda (bobin sürülmez).
- S7 adım 2: (a) `canvasBoyutla` ctx.lineJoin/lineCap atamalarından (RealtimeChart.tsx:47-48) ÖNCE çağrılmalı — `canvas.width` ataması 2D context durumunu SIFIRLAR. (b) `draw` useCallback bağımlılıkları (:135) → width/height eklenmeli. (c) `dpr = Math.min(3, …)` ve `setTransform` her draw'da. (d) SensorMonitor: S4 `ScrollView` import'unu kaldırmış olacak → S7 geri ekler, `horizontal` aynı satırda. (e) Web'de fare kullanıcısı yatay sürükleyemez → `showsHorizontalScrollIndicator`; PC'de isCompact false — kabul.
- S7 adım 3: PieChart merkez formülü YANLIŞ. chart-kit 6.12.3 dist/PieChart.js:91-92 (doğrulandı): `<G x={width/2/2 + paddingLeft} y={height/2}>` → merkez x = chartW/4 + paddingLeft. Ortalamak için `paddingLeft={String(Math.round(chartW / 4))}`, `center={[0,0]}`; plandaki formül yarıçapı çıkarıyor (pasta sola kayar). `absolute` yalnız lejant metnini etkiler → hasLegend=false ile anlamsız, kaldır. BarChart `style.paddingRight` (varsayılan 64) doğru. Test beklentisi `flatten(style).paddingRight === rs(24)` — literal değil.
- S7 adım 1: Mevcut kod `<Svg width="100%" height={rs(260)} viewBox="0 0 720 260">` — sorun `preserveAspectRatio` (meet) ile 720→300 px'te yazıların 0.42× küçülmesi; ölçüm yaklaşımı doğru. `h = rs(240)` yerine mevcut rs(260) korunmalı. SessionDetailModal.tsx:26 import satırında `rf` YOK → eklenir. S6 adım 6 aynı dosyada → S6 önce, S7 rebase. Kaynak kapısı çıpası `const width = 720;`.
- S7 adım 10: Dosya listesi eksik (çakışma 2): 17 nokta → S7 9 + S6 5 + Faz B 3. `rfMin` yardımcısı eklenmez. Kaynak kapısı `capraz.kaynak_yolu('pf/src')` doğru; regex `fontSize:\s*rf\(\s*(9|10)\s*\)` + Faz C boyunca SABİT SAYAÇ, Faz D'de 0. liveIndicator tam-genişlik şerit `left:12,right:12` flipCameraBtn ile çakışmaz.
- S7 adım 11: Mevcut `webHeight` state'i (DemaSimulatorScreen.tsx:23) — türetilmiş değere geçiş doğru; `useWindowDimensions` zaten import. iframe `contentDocument` aynı origin (backend /simulator/) — tünelde farklı origin try/catch. Test: web mock'unda `simulatorContainer` flatten height ölçülür.
- S7 adım 9: `styles.soundBarRow` üç yerde (2688 Kedi Sesi, 3053 Histopat, 3599 CatOrgan güven çubuğu) — compact stili yalnız 2688/3053'e; `soundBarLabel width: rs(96)` → `minWidth` yapınca 3599'daki hizalama da değişir → ekran görüntüsü.
- L adım 11: Dosya listesi YANLIŞ: `launcher/app/Cargo.toml` `version.workspace = true` — sürüm `launcher/Cargo.toml [workspace.package]`te. Tek kaynak `versions.json` (launcher 1.9.45 → 1.9.46) + `build_tools/sync_versions.ps1`. Yayın tetikleyicisi `launcher-v1.9.46` etiketi. Site config.ts CLIENT.version güncellemesi (test_version_visibility) W hattında ayrı commit.
- L adım 10: (a) `tests/launcher_gorunum_alani_olc.py` pytest tarafından TOPLANMAZ (varsayılan `test_*.py`) → `tests/test_launcher_gorunum_alani.py` (skipif msedge yok) ya da salt betik. (b) `windows-latest` runner'da msedge VAR → tests.yml backend(windows) işinde kapı GERÇEKTEN koşar → deterministik viewport (CDP) ya da `PEMF_GORUNUM_ALANI=1` opt-in. (c) `websocket-client` requirements-test.txt'te YOK → ~60 satırlık RFC 6455 istemcisi `tests/_cdp.py` ortak modülü; W adım 0 cdp_eval.py de aynı modülü kullanır.
- L adım 5: (a) test_baslat_kapisi_etiket harness'i (çakışma 6). (b) `header.authed` toggle `refreshAuth` değil `setAuthUi` (2057-2064) içine — logout yolu tek noktadan geçer. (c) İD'ler doğrulandı: btn-web(426), btn-guide(430), btn-about(434), btn-logout(441). (d) 1180 px `.brand p` bloğu kalır, yalnız 1040 bloğu silinir. (e) test_client_arayuz_sade_dil yalnız I18N TR/EN değerlerini tarar — title/aria-label mevcut x.* metinleri → güvenli.
- L adım 6: `<div class="meta">` button içinde geçersiz HTML — `createElement("span")` + CSS `.card .meta { display:block }`. Global `button` reset (index.html:45) `.card`ın border/background'unu ezmez, ama `text-align:center` UA kuralı → `.card { width:100%; text-align:left }` ŞART. `card.disabled = busy` → `if (busy) return` çift güvence, kalır. Node birim testi test_arkaplan_bar_davranisi'nin `El` sınıfını yeniden kullanabilir.
- L adım 7: (a) `guide-body` (:619) HTML'e `tabindex="-1"`. (b) `.modal` (:322) `max-height: calc(100vh - 48px); overflow-y:auto`. (c) `bootNetwork` resume onayı (:2265) etkileşimsiz açılır → openModal `confirm-no` odağı + inert; `boot()` başında inert=false sigortası ZORUNLU. (d) Yeni fonksiyonlar `function ad(...) {` + 6-boşluk kapanış (test_self_update `_fonksiyon` çıkarıcısı). (e) Escape dinleyicisi `document` düzeyinde.
- L adım 8: cargo testi `s4_rotasyon_bellegi_de_tazeler_ve_sahiplenme_once_ceker` `open_app_window(` ÇAĞRISINI blok sınırı çıpası olarak kullanıyor → fonksiyon adı ve çağrı yeri değişmez. Monitör okunamazsa `min_inner_size` VERİLMEZ. `app.get_webview_window("main")` o anda görünür (show() 250 ms'de) → current_monitor dolu.
- L adım 3: API doğrulandı (tauri 2.11.5): `Monitor::work_area() -> &PhysicalRect<i32,u32>`, `scale_factor()`, `WebviewWindow::current_monitor/primary_monitor/show/set_min_size/eval`. CI: tests.yml launcher işi `cargo test --workspace --all-targets --locked` → yeni testler koşar, Cargo.lock'a dokunulmaz. test_uretici_kimligi yalnız publisher/identifier okur → minHeight/visible güvenli.
- L adım 4: `w2.eval(...)` sayfa yüklenmeden hata dönebilir (`let _ =` yutar; boot() sınıfı zaten ekler → idempotent). Test hedefi `fn pencereyi_calisma_alanina_sigdir` gövdesinde aranır. `visible:false` gunc kipinde de config'den gelir → zıplama biter. macOS/Linux doğrulanmadı (açık soru).
- L adım 9: `_css_kurali` çıpası `main {` çok satırlı — regex `main \{[^}]*\}` kullan (girinti değişirse kırılmasın). Node testleri `node` yoksa skip. test_hata_mesaji_anlasilir:128 `#error .errdetail` çıpası etkilenmez.
- W adım 2: dvh/vh fallback (çakışma 8). `AccountButton inline` prop'u adım 3'te tanımlanıyor → adım 2 tek başına `tsc -b` düşer → 2+3 tek commit. `lg:flex` ×2 / `lg:hidden` ×2 simetri kapısı doğru.
- W adım 4: Katmansız blok kararı DOĞRU (theme<base<components<utilities; katmansız kazanır). S3'ün 44 px kuralları aynı bloğa. `App.tsx` `behavior: 'instant'` TS lib.dom'da var. `input:not([type='checkbox'])` Pricing:96 accent kutusunu korur.
- W adım 6: `--color-danger` @theme'e eklenince `text-danger` üretiliyor (ÖLÇÜLDÜ). AuthModal.tsx:246 kapatma-onayı bloğu: auth-modal-focus.test.ts:60 HAM kaynakta `window.confirm` (yorum) arıyor → o yorum satırına dokunulmaz. `html { color-scheme: dark }` yerel form kontrollerini koyulaştırır — Odeme formu ekran görüntüsü.
- W adım 7: `bg-gradient-to-l` v4'te hâlâ üretiliyor ama kanonik `bg-linear-to-l`; kapı birini pinler. `.bg-table-sticky` `@layer utilities` içinde düz sınıf — varyant gerekmediği için çalışır. `min-w-[140px]` sticky sütun 320 px'te 4 plan sütununa 180 px bırakır — kaydırma ipucu şart.
- W adım 12: `import.meta.glob` `vite/client` tipleri tsconfig.app.json'da var → `tsc -b` geçer. Kapıya eklenecekler: `max-h-[calc(100vh-4rem)]` YOKLUĞU, coarse bloğunda `footer a`/`nav a`, `text-danger` ≥1. `CSS.lastIndexOf('@layer')` kontrolü `.bg-table-sticky` coarse bloğundan ÖNCE olduğu sürece doğru. '15 dosya' = mevcut 14 + 1.
- W adım 10: Footer Link `inline-block py-1.5` (32 px) fare için; coarse 44 px tek bloktan. 'İptal, İade ve Cayma Hakkı' 320'de tek satır ölçümü korunur.
- W adım 0: cdp_eval.py `websocket-client`e bağımlı — L adım 10 ile ortak `tests/_cdp.py` (saf stdlib) kullanılırsa depoya alınabilir; CI'ya eklenmez.

**Planlarda eksik bulunanlar / tamamlayıcı kararlar:**

- S7 (grafik/kamera: aihub-1, aihub-2, aihub-3, aihub-11, ekranB-5, ekranB-6, ekranB-11, ekranC-2, ekranC-3 YÜKSEK), L (launcher 13 bulgu, 2 YÜKSEK) ve W (site 17 bulgu, ampirik-1 YÜKSEK) planları bu incelemeye VERİLMEDİ ('9 kök' denmiş, 6 geldi); S6 planı adım 2 kod taslağında KESİLMİŞ (adım 3+ görünmüyor). Çakışma tablosu bu üç paket için yalnız rapordaki öneri metinlerinden çıkarıldı.
- Köksüz 27 bulgu hiçbir pakette yok: ekranB-2 (YÜKSEK, hasta güvenliği — bkz. güvenlik notu), kabuk-3 (orta: headerRight 320'de başlığı yutuyor — S3 adım 8 header'a dokunurken kapatılmalı), kabuk-10, ekranA-8/9/11/15/18/20, ekranB-7/13, ekranC-4/6/9/10/12/15, aihub-7/8/9/13/14, ilkel-14/15, kapsam-6/8, matris-12. ekranA-15 ve ekranC-4 (sil düğmesi 26 px, yanlış dokunuşla silme) S3 kapsamına alınmalı; ekranC-6 S2 (isCompact) kapsamına.
- Rapor S3/L/W bağlı-bulgu listelerindeki `ekranA-12`, `ampirik-2`, `ampirik-3`, `ampirik-6`, `ampirik-7`, `matris-10`, `matris-13` id'leri bulgular JSON'unda YOK (121 kayıt) — hayalet id'ler; JSON'da 'ikinci.karar'=='bilgi' ve 'ikinci.tekrar' alanı hiçbir kayıtta dolu değil (tekrar birleştirme zaten yapılmış).
- Ortak jest yardımcısı (responsiveMock, darTelefon/olcekYukle) hiçbir planda tek dosya olarak tanımlı değil — S1/S2/S3/S5 her biri kendi mock'unu yazıyor; `pf/src/__tests__/yardimci/responsive.ts` olarak Faz A1'e eklenmeli.
- ekranB-1'in CoilParameterPanel header flexWrap/adjustsFontSizeToFit parçası S2 dışına bırakıldı ama S6 (ekranB-8 CoilParameterPanel 356-365) aynı bileşene dokunuyor — sahibi belirsiz; S6'ya ver.
- Görsel regresyon betiği (Edge headless + CDP) scratchpad'de kalırsa Faz G'de tekrar üretilemez; `pf/scripts/gorsel_regresyon.ps1` olarak depoya alınması (S1 açık soru 5) kararlaştırılmalı — bu inceleme 'depoya' öneriyor.
- Sürüm zinciri planlarda belirsiz: pf değişiklikleri ÜÇ kanaldan çıkar (backend paketi 1.9.41 frontend_dist gömülü, frontendOta 1.4.2 frontend_version.json, mobile 2.3.32/androidVersionCode 39). versions.json tek kaynak + sync_versions.ps1; manifest sürümü üç yerde (bellek). Hiçbir plan androidVersionCode artışını yazmıyor.
- S5 adım 13 bulgu JSON'una 'durum' alanı yazmayı planlıyor — JSON şemasında alan yok; docs/*.md durum satırı yeterli, JSON'a dokunulmasın (ikinci doğrulama tek kaynağı bozulur).
- S7 tip güncellemeleri hiçbir adımda yok: AiHubScreen `AiResult` (image_w/h), AiProPanel `FrameResult`, LiveDataContext `AiVisionData` (imageW/H) — TS strict için şart; adım 4-5-6 dosya listelerine eklenmeli.
- S7 adım 4 için mikroservis yolu testi (`delegate_infer` mock'u ile `_kare_boyutu_ekle`) ve EXIF-6 sentetik JPEG testi planda yok.
- S7 web canlı mod (VisionModule PC webcam) kullanımı belirsiz (açık soru) — sahip kararı alınmadan adım 7 tablosu yarım.
- L adım 2 coarse listesinde `.pw-toggle` eksik; `.chip` gereksiz (tıklanamaz).
- L adım 5 logout sonrası `header.authed` güncelleme yolu (setAuthUi) dosyaya yazılmalı.
- L adım 10 CI ortam kararı (windows-latest msedge) ve ortak stdlib CDP modülü (`tests/_cdp.py`) tanımsız; W adım 0 cdp_eval.py aynı bağımlılığı taşıyor.
- L adım 11 sürüm zinciri: versions.json + build_tools/sync_versions.ps1 hiç anılmıyor; launcher/app/Cargo.toml elle düzenlenemez (workspace).
- W: launcher 1.9.46 yayını sonrası config.ts CLIENT.version/indirme boyutu güncellemesi (test_version_visibility, test_site_paket_boyutlari) W planında yok — Faz F sonrası küçük commit.
- W adım 12 kapısı: `max-h-[calc(100vh-4rem)]` yokluğu, coarse bloğunda `footer a`/`nav a`, `text-danger` ≥1 — eklenmeli.
- Ortak jest yardımcısı (responsiveMock) S7 testlerinde de kullanılmalı — Faz A1'deki tek dosyaya pinlenir.
- docs/responsive-denetim-2026-09-04.bulgular.json'a 'durum' alanı yazılmaz — docs/*.md durum satırıyla sınırlanır.

**Köksüz (paketlere dağıtılan) bulgular:** aşağıdakiler bir sistemik köke bağlı değil; en yakın paketin dosya sahibi tarafından Faz C'de kapatılır — `kabuk-3`, `kabuk-10`, `ekranA-8`, `ekranA-9`, `ekranA-11`, `ekranA-15`, `ekranA-18`, `ekranA-20`, `ekranB-2`, `ekranB-7`, `ekranB-13`, `ekranC-4`, `ekranC-6`, `ekranC-9`, `ekranC-10`, `ekranC-12`, `ekranC-15`, `aihub-7`, `aihub-8`, `aihub-9`, `aihub-13`, `aihub-14`, `ilkel-14`, `ilkel-15`, `matris-12`, `kapsam-6`, `kapsam-8`. `ekranB-2` (sayfa-içi ACİL DURDUR 8 kart altında + STM offline'da kayan düğmenin kaybolması) responsive değil DAVRANIŞ hatasıdır: ayrı, öncelikli düzeltme (LiveDataContext.normalizeStmCoils + ControlScreen sticky E-stop).


## 5. Paket planları (kök başına)

### S1 — Ölçek sabiti (3 bulgu: 0 yüksek / 1 orta / 2 düşük)

Bağlı bulgular: `kabuk-1`, `ekranB-12`, `aihub-10`

**Hedef:** Telefonda (kısa kenar < 600, native) mevcut ölçek formülü BİREBİR korunurken; tablet/PC/LAN tarayıcısında ölçek tavanını 1.10'a indirmek, 'yapısal' boyutları (sidebar genişliği, ekran-konteyner maxWidth'leri, önizleme sahne yüksekliği) ölçekten çıkarıp sabit/canlı hâle getirmek ve bunu iki kapıyla (jest ölçek-matrisi + Python yapısal-boyut kapısı) kilitlemek. ACİL DURDUR erişimi ve seans akışında hiçbir mantık değişikliği yok; yalnız stil sayıları değişir.

**Tasarım kararları:**
- SEÇENEK KARŞILAŞTIRMASI — (a) tavanı ortama göre düşürmek: 1 dosya (tokens.ts) değişir, etkisi 48 dosyaya YAYILIR ama yalnız kısa kenar ≥600/web ortamlarında ve tek yönlü (her şey %15 küçülür = denetimin istediği 'telefon büyütmesi' görünümünün kalkması); telefon formülü dokunulmadığı için APK'da sıfır fark. (b) SCALE'i canlı (useWindowDimensions) yapmak: 43 dosyadaki modül-düzeyi StyleSheet.create + tokens'tan türeyen spacing/typography sabitleri (48 dosya) hook/context'e çevrilmeli (~500 çağrı noktası, 2-3 hafta, yüksek regresyon); üstelik FAYDASI YOK — PC'de kısa kenar hiçbir zaman 540'ın altına inmez (tauri minHeight 540), telefonda min(w,h) döndürmede zaten değişmez; canlı gereken TEK şey yükseklik (aihub-10) ve o hook'la yerel çözülür. REDDEDİLDİ. (c) yalnız yapısal boyutları ölçekten çıkarmak: 1 sidebar + 13 ekran-konteyner maxWidth + 3 sahne yüksekliği = 17 nokta; tavan düşmese bile gerekli çünkü maxWidth 'CSS px tavan' anlamındadır, telefon-orantı değil. KARAR: (a)+(c) birlikte, kademeli (her faz ayrı commit, ayrı ekran görüntüsü karşılaştırması).
- TAVAN DEĞERİ: web (Platform.OS==='web' ve kısa kenar ≥480) ile native kısa kenar ≥600 için OLCEK_TAVAN_BUYUK_EKRAN = 1.10 (rf yumuşatmasıyla yazı 1.07×: gövde 14→15 px, başlık 24→26 px). 1.0 yerine 1.10 seçildi: Windows %100 DPI'lı 1920 px monitörde 14 px gövde metnini bugünkü 17 px'e alışmış klinik kullanıcı 'küçüldü' diye algılar; 1.10 orta yol. Sabit dışa aktarılıyor; sahip ekran görüntülerine bakıp 1.0'a çekerse tek satır. Telefon web tarayıcısı (LAN, sınıf h, kısa kenar <480) telefon formülünde kalır.
- EŞİK NEDEN 600 (breakpoints.tablet=768 DEĞİL): kısa kenar karşılaştırılıyor; 700×540 WebView2 penceresinin kısa kenarı 540'tır, 768 eşiği onu telefon formülüne (1.30) düşürürdü. Web'de eşik 480 (breakpoints.phone) — PC penceresi hiçbir zaman 480'in altına inemez. Native 600 = Android 'sw600dp' tablet sınırı ile aynı.
- ROLLBACK TASARIMI: eski davranış = `OLCEK_TAVAN_BUYUK_EKRAN = 1.30`; sabit tek satır olduğundan geri alma 1 satır + yeniden export. Yapısal fazlar (sidebar, maxWidth, sahne) bağımsız commit'ler; her biri tek başına geri alınabilir.
- MEVCUT DESENLER: AppShell'de zaten `responsive.isTablet` var → sidebar genişliği inline style ile; AiHub bileşenleri zaten `useResponsive()` çağırıyor → sahne yüksekliği hook'u aynı yere; Skeleton/onLayout deseni SensorMonitor için ResponsiveGrid'e devrediliyor; Python kapıları `tests/capraz.oku` + regex (test_ai_zaman_asimi.py deseni).
- HASTA GÜVENLİĞİ: GlobalEmergencyStop.tsx DOSYASINA DOKUNULMUYOR; yalnız dolaylı etki: PC'de minHeight 68→57 px, yazı 18→16 px, bottomOffset rs(76) 99→84 px (alt bar da aynı oranda küçüldüğü için hiza korunur). 44 px dokunma tavanının çok üstünde kalır; zIndex/position/mantık değişmez. Telefonda sıfır değişiklik. Faz 6'da PEMF_SIMULATE=1 ile bobin çalışırken 700×540 ve 911×512'de ACİL DURDUR'un alt barın üstünde bütün göründüğü ekran görüntüsüyle kanıtlanır.
- Modal/kart maxWidth'leri (420-560 px, 12 nokta) rs() içinde BIRAKILDI: telefonda width:'100%' zaten bağlayıcı, PC'de tavanla artık yalnız %10 büyürler; dokunmak S1'in kapsamını şişirir. Python kapısı yalnız ≥800 px konteyner sınırlarını yasaklar.

| # | Adım | Dosyalar | Değişiklik | Kapattığı | Doğrulama | Risk | Efor (s) |
|---|---|---|---|---|---|---|---|
| 0 | Temel ekran görüntüleri (değişiklik ÖNCESİ) — görsel regresyon referansı | `C:\Users\merta\AppData\Local\Temp\claude\c--Users-merta-Downloads-python-3-10-2-embed-amd64\5c8db92a-75b8-4d12-a3bd-48cc304d47b5\scratchpad\s1-once\ (yeni, geçici)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\package.json (scripts.web → expo start --web --port 3001; salt okunur)` | Denetimin yöntemiyle (Edge headless + CDP ile görünüm alanı ZORLANARAK; --window-size tek başına yetmiyor) pf web export'unu 7 görünüm alanında render et: 375×812, 430×932, 640×360 (yatay telefon), 700×540 (launcher min), 768×1024 (tablet dikey), 911×512 (1366×768 @%150), 1920×1080. Ekranlar: Dashboard, Kontrol (Otoma… |  | 7×5 = 35 PNG 'önce' klasöründe; her karede pencere/DPI etiketi dosya adında. Betik tekrar koşunca aynı isimleri üretir (diff için). | Yok (salt okuma). Backend'i PEMF_SIMULATE=1 ile ayrı portta aç; ⚠️ iki backend aynı anda AÇMA (bellek notu). | 1.5 |
| 1 | tokens.ts: ölçek tavanını ortama göre ver (telefon formülü BİREBİR korunur) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\theme\tokens.ts` | Satır 10-14'teki tek clamp'i iki katmanlı yap: kısa kenar hesabı aynı; 'büyük ekran' tespiti = native'de kısaKenar ≥ 600, web'de kısaKenar ≥ 480 (breakpoints.phone). Büyük ekranda üst sınır OLCEK_TAVAN_BUYUK_EKRAN = 1.10, aksi hâlde eski 1.30. rf() formülü değişmez (yumuşatma 0.7 aynı kalır → 1.07). `SCALE`'i `OLCEK` … | `kabuk-1` | Yeni jest testi (adım 2) + `npx tsc --noEmit` + `npm test` (mevcut 40 test dosyası piksel assert etmiyor, snapshot yok → yeşil kalmalı). Ekran görüntüsü: adım 0 betiği 'sonra-1' klasörüne; 375/430'da… | ORTA: telefon dışı tüm ekranlarda görsel değişim (tek yönlü küçülme). Mantık değişmez; ACİL DURDUR yalnız boyut olarak küçülür (57 px ≥ 44). Geri alma: OLCEK_T… | 1.5 |
| 2 | Jest ölçek matrisi: telefon değişmezliği + tavan kanıtı (isolateModules) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\theme\__tests__\tokens.olcek.test.ts (yeni)` | jest.isolateModules + jest.doMock('react-native') ile Dimensions.get ve Platform.OS'u satır satır değiştirip tokens'ı yeniden yükle. Matris: (320×568,android)→0.85; (375×812,ios)→1.00; (430×932,android)→1.147; (480×1000 native)→1.28 (telefon formülü, tavan 1.30 hâlâ); (768×1024,android)→1.10; (1920×1080,web)→1.10; (70… | `kabuk-1` | `npm test -- tokens.olcek`; MUTASYON: OLCEK_TAVAN_BUYUK_EKRAN'ı 1.30'a çevir → web/tablet satırları KIRMIZI olmalı; Platform dalını sil → 700×540 web satırı kırmızı. Kırmızı kanıtı alınmadan kapı say… | Düşük. jest-expo varsayılan Dimensions 750×1334 olduğundan doMock kullanılmazsa test yanlış ortamda 'geçer' — bu yüzden her satır isolateModules içinde. | 1 |
| 3 | AppShell: kenar çubuğu genişliğini ölçeksiz sabit yap, tablette daralt | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\AppShell.tsx (satır 517 `width: rs(248)`, render satırı ~208 `<View style={styles.sidebar}>`)` | styles.sidebar'dan `width` kaldır; modül üstünde `export const KENAR_CUBUGU_GENISLIK = { masaustu: 240, tablet: 200 } as const;` tanımla; render'da `<View style={[styles.sidebar, { width: responsive.isTablet ? KENAR_CUBUGU_GENISLIK.tablet : KENAR_CUBUGU_GENISLIK.masaustu }]}>`. Tablette sidebar `padding: spacing.xl` →… | `kabuk-1` | Mevcut AppShell.logout/pairing testleri yeşil. Ekran görüntüsü 768×1024: sidebar 200 px (önce 322), içerik ≥ 500 px; 911×512: sidebar 200 px; 1920: 240 px. Python kapısı (adım 5) `width: rs(248)` yok… | Düşük. Desktop dalında sidebar dışında düzen değişmiyor; ACİL DURDUR masaüstünde bottomOffset 0, konumu sidebar'a bağlı değil. Geri alma: inline width'i kaldır… | 1 |
| 4 | Ekran-konteyner maxWidth'lerini ölçeksiz `layoutMax` token'ına taşı (13 nokta) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\theme\tokens.ts (yeni export layoutMax)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\ControlScreen.tsx:856`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\SensorMonitorScreen.tsx:190`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\DashboardScreen.tsx:163` | tokens.ts'e `export const layoutMax = { icerik: 1100, genis: 1200, aiHub: 980, ayar: 900 } as const;` (ölçeksiz, CSS px). Her noktada `maxWidth: rs(1100)` → `maxWidth: layoutMax.icerik` vb. (1200→genis, 980→aiHub, 900→ayar). Modal/kart maxWidth'leri (420-560) DOKUNULMAZ. Telefonda etkisi yok (width:'100%' bağlayıcı). | `ekranB-12`, `kabuk-1` | `npx tsc --noEmit`; `grep -rnE "maxWidth: rs\((8[0-9]{2}|9[0-9]{2}|1[0-9]{3})\)" pf/src` boş; ekran görüntüsü 1920×1080: Kontrol içerik 1100 px (önce 1430), Sensörler 1200 (önce 1560). Python kapısı … | Düşük; yalnız üst sınır sayıları. Geri alma: sabitleri rs() ile sar. | 1 |
| 5 | Python yapısal-boyut kapısı: tavan + sidebar sabiti + ≥800 px maxWidth'te rs() yasağı | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\tests\test_responsive_olcek_yapisal.py (yeni; capraz.oku deseni)` | Üç değişmez: (1) tokens.ts'de `OLCEK_TAVAN_BUYUK_EKRAN = 1.10` (regex `OLCEK_TAVAN_BUYUK_EKRAN\s*=\s*1\.10`) ve `Platform.OS === "web"` dalı bulunur; (2) pf/src altındaki tüm .ts/.tsx'te `maxWidth:\s*rs\(\s*(\d+)\s*\)` eşleşmelerinde sayı < 800 (konteyner tavanı ölçeklenemez), ihlal listesi dosya:satır ile raporlanır;… | `kabuk-1`, `ekranB-12` | `..\python.exe -m pytest tests/test_responsive_olcek_yapisal.py -q` yeşil; MUTASYON kanıtı: tokens.ts'de tavanı 1.30 yap → (1) kırmızı; ControlScreen'e `maxWidth: rs(1100)` geri koy → (2) kırmızı; Ap… | Düşük. tests.yml'de kapı otomatik toplanır (conftest tabanlı); route-contract sayacı ilgisiz (endpoint yok). | 1 |
| 6 | ekranB-12 kalan: ParamField tavanı, AI Pro kamera kutusu oranı, Sensörler kart ızgarası | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\ControlScreen.tsx:935 (paramField)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\AiProPanel.tsx:891-895 (camBox)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\SensorMonitorScreen.tsx:126, 264-277 (statsGrid/statCard)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\ResponsiveGrid.tsx (salt kullanım)` | (1) paramField: `{ flex: 1, minWidth: rs(140), maxWidth: rs(260) }` — 1100 px'te 4 alan × 260 sol hizalı, gerilme biter. (2) camBox: `height: rs(200)` yerine `width: '100%', maxWidth: 640, aspectRatio: 16/9, alignSelf: 'center', height: undefined` — resizeMode='contain' ile siyah bant kalkar; telefonda 343 px genişlik… | `ekranB-12` | AiProPanel 5 test dosyası (B1/Sahiplik/SessizKare/Web/WebOnizleme) yeşil — stil değişimi davranışa dokunmaz. Ekran görüntüsü 1920: Kontrol ParamField ≤260 px, camBox 640×360 ortalı, Sensörler 4+4; 76… | Düşük-orta: camBox içinde CameraView (mobil) `height:'100%'` ile ebeveyne bağlı — aspectRatio'lu ebeveyn yükseklik verir, sorun yok; yine de Android cihazda ca… | 2 |
| 7 | aihub-10: canlı sahne yüksekliği hook'u (useStageHeight) — önizleme/heatmap/sc sahnesi | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\hooks\useStageHeight.ts (yeni)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\hooks\__tests__\useStageHeight.test.ts (yeni)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\AiHubScreen.tsx (imagePreviewContainer kullanımları 1436, 1867, 2087, 2838, 3019, 3523; xaiStage 822; scStage 3313; stiller 3661, 3672, 3761)` | Hook: `const { height } = useWindowDimensions(); return Math.min(rs(300), Math.max(rs(180), Math.round(height * 0.45)));` — useWindowDimensions canlı olduğundan pencere küçülünce/yatay dönünce daralır. Altı bileşen zaten `useResponsive()` çağırıyor (1076, 1747, 1968, 2727, 2931, 3365) → hemen altına `const sahneH = us… | `aihub-10` | Jest: useWindowDimensions mock'la — height 540 → 243 (0.45×540; rs(300)=330'dan küçük), height 1080 → 330 (=rs(300) tavan, jest ortamı web-dışı 750 kısa kenar → 1.10), height 360 → 198 (=rs(180) taba… | Düşük: yalnız yükseklik; AI akışı/otonom onay kapısı mantığı dokunulmaz. AiHubScreen 3800 satır — 8 nokta cerrahi edit, regen YOK. Geri alma: inline height diz… | 2 |
| 8 | Görsel regresyon karşılaştırması + cihaz testi + sahip kararı (tavan 1.10 mu 1.0 mı) | `C:\Users\merta\AppData\Local\Temp\claude\c--Users-merta-Downloads-python-3-10-2-embed-amd64\5c8db92a-75b8-4d12-a3bd-48cc304d47b5\scratchpad\s1-sonra\`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\docs\responsive-denetim-2026-09-04.md (§S1 durum notu, isteğe bağlı)` | Adım 0 betiğini 'sonra' klasörüne koştur; önce/sonra yan yana (375 ve 430 kareleri PIKSEL-EŞ olmalı → telefon değişmedi kanıtı; diğerleri beklenen küçülme). PEMF_SIMULATE=1 ile bobin çalışırken 700×540 ve 911×512'de ACİL DURDUR karesi: buton bütün, alt barın üstünde, alt satırı örtmüyor. Sahibe 1920×1080 ve 911×512 ka… | `kabuk-1`, `ekranB-12`, `aihub-10` | Önce/sonra 35+35 kare; 375/430 karelerde sıfır piksel farkı; jest + Python kapıları yeşil ve mutasyonda kırmızı kanıtlı; cihaz listesi (cihaz_testi) tamamlandı. | Karar riski: 1.0 seçilirse klinik PC'de 'küçüldü' şikâyeti; 1.10 varsayılan. Geri alma: tavan 1.30 (tek satır) + yapısal commit'ler bağımsız revert. | 2.5 |

<details><summary>Kod taslakları</summary>

**1. tokens.ts: ölçek tavanını ortama göre ver (telefon formülü BİREBİR korunur)**

```
import { breakpoints } from "@/theme/breakpoints";
const BASE_WIDTH = 375;
/** Büyük ekran tavanı (tablet/PC/LAN tarayıcı). Eski davranış = 1.30 (geri alma için). */
export const OLCEK_TAVAN_BUYUK_EKRAN = 1.10;
export const OLCEK_TAVAN_TELEFON = 1.30;
const NATIVE_BUYUK_KISA_KENAR = 600; // Android sw600dp tablet sınırı
const { width: _w, height: _h } = Dimensions.get("window");
const _kisaKenar = Math.min(_w, _h) || BASE_WIDTH;
const _buyukEkran = Platform.OS === "web" ? _kisaKenar >= breakpoints.phone : _kisaKenar >= NATIVE_BUYUK_KISA_KENAR;
const _tavan = _buyukEkran ? OLCEK_TAVAN_BUYUK_EKRAN : OLCEK_TAVAN_TELEFON;
export const OLCEK = Math.min(Math.max(_kisaKenar / BASE_WIDTH, 0.85), _tavan);
const SCALE = OLCEK; // rs()/rf() gövdeleri değişmez
```

**2. Jest ölçek matrisi: telefon değişmezliği + tavan kanıtı (isolateModules)**

```
function olcekYukle(w: number, h: number, os: string) {
  let sonuc = 0;
  jest.isolateModules(() => {
    jest.doMock("react-native", () => ({
      Dimensions: { get: () => ({ width: w, height: h, scale: 2, fontScale: 1 }) },
      Platform: { OS: os, select: (o: any) => o[os] ?? o.default },
    }));
    sonuc = require("@/theme/tokens").OLCEK;
  });
  return sonuc;
}
test.each([[375,812,"ios",1.0],[768,1024,"android",1.10],[1920,1080,"web",1.10],[700,540,"web",1.10]])("%i×%i %s → %f", (w,h,os,b) => expect(olcekYukle(w,h,os)).toBeCloseTo(b, 3));
```

**3. AppShell: kenar çubuğu genişliğini ölçeksiz sabit yap, tablette daralt**

```
export const KENAR_CUBUGU_GENISLIK = { masaustu: 240, tablet: 200 } as const;
// render:
const sidebarW = responsive.isTablet ? KENAR_CUBUGU_GENISLIK.tablet : KENAR_CUBUGU_GENISLIK.masaustu;
<View style={[styles.sidebar, { width: sidebarW, padding: responsive.isTablet ? spacing.lg : spacing.xl }]}>
```

**4. Ekran-konteyner maxWidth'lerini ölçeksiz `layoutMax` token'ına taşı (13 nokta)**

```
// tokens.ts
/** Ekran-konteyner tavanları — CSS px, ÖLÇEKSİZ (rs ile ÇARPMA: PC'de 1100→1430 hatası). */
export const layoutMax = { icerik: 1100, genis: 1200, aiHub: 980, ayar: 900 } as const;
// ControlScreen.tsx
container: { ..., maxWidth: layoutMax.icerik, alignSelf: "center" },
```

**5. Python yapısal-boyut kapısı: tavan + sidebar sabiti + ≥800 px maxWidth'te rs() yasağı**

```
_MAXW = re.compile(r"maxWidth:\s*rs\(\s*(\d+)\s*\)")
def test_KRITIK_konteyner_tavani_olceklenmez():
    ihlal = []
    for p in capraz.kaynak_yolu("pf/src").rglob("*.ts*"):
        if "__tests__" in p.parts: continue
        for no, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = _MAXW.search(satir)
            if m and int(m.group(1)) >= 800: ihlal.append(f"{p.name}:{no} rs({m.group(1)})")
    assert not ihlal, "maxWidth ≥800 rs() ile ÇARPILAMAZ → layoutMax kullan:\n" + "\n".join(ihlal)
```

**6. ekranB-12 kalan: ParamField tavanı, AI Pro kamera kutusu oranı, Sensörler kart ızgarası**

```
// AiProPanel.tsx
camBox: {
  width: "100%", maxWidth: 640, aspectRatio: 16 / 9, alignSelf: "center",
  backgroundColor: "#000", borderRadius: 12, alignItems: "center", justifyContent: "center",
  overflow: "hidden", borderWidth: 1, borderColor: "#1e3a5f",
},
// SensorMonitorScreen.tsx
<ResponsiveGrid minItemWidth={160}>{kartlar}</ResponsiveGrid>
statCard: { backgroundColor: "#0a0f1e", borderRadius: 12, padding: spacing.md, borderWidth: 1, gap: spacing.xs },
```

**7. aihub-10: canlı sahne yüksekliği hook'u (useStageHeight) — önizleme/heatmap/sc sahnesi**

```
// hooks/useStageHeight.ts
import { useWindowDimensions } from "react-native";
import { rs } from "@/theme/tokens";
/** Görüntü sahnesi yüksekliği: rs(300) tavan, pencere yüksekliğinin %45'i, rs(180) taban. CANLI. */
export function useStageHeight(): number {
  const { height } = useWindowDimensions();
  return Math.min(rs(300), Math.max(rs(180), Math.round(height * 0.45)));
}
```

</details>

**Bağımlılıklar:** S2 (ResponsiveGrid onLayout + contentWidth + ikon-ray sidebar): Adım 3'teki KENAR_CUBUGU_GENISLIK sabitini S2 ray genişliği (72) ile GENİŞLETİR, yeniden tanımlamaz; Adım 6 SensorMonitor ResponsiveGrid'e geçtiği için S2 inince otomatik iyileşir. S1 S2'yi BEKLEMEZ.; S7 (aihub-1 kamera aspectRatio, aynı resizeMode): Adım 6 camBox ve Adım 7 useStageHeight aynı sahneyi paylaşır → S7 uygulayıcısı `maxHeight: sahneH` + aspectRatio birleşimini kullanır; iki taraf aynı hook'a pinlenir.; S3 (touch token `max(44, rs(44))`): tavan 1.10 ile PC'de rs(44)=48 — S3'ün ölçekten bağımsız tabanı bu kökle çelişmez; S3 tokens.ts'e eklerken Adım 1'in OLCEK export'unu kullanır.; S5 (isShort/yükseklik): Adım 7 hook'u S5'in `isShort` eşiğiyle (height<500) tutarlı — S5 gelince hook içindeki 0.45 çarpanı isShort'ta 0.40'a çekilebilir.; L (launcher min pencere): tauri minHeight 540 → Adım 7'nin 700×540 doğrulaması bu değere pinli; L min pencereyi work_area'ya göre kırparsa 472-516 px'te de hook 212-232 px verir (rs(180) taban üstünde) — ek iş yok.; Bellek: iki backend aynı anda AÇMA; backend+APK build paralel KOŞMAZ; AiHubScreen'de regen yerine cerrahi edit.

**Kilitler:**
- TELEFON DEĞİŞMEZLİĞİ: native kısa kenar < 600 ve web kısa kenar < 480'de SCALE formülü ve 1.30 tavanı BİREBİR eski — jest matrisi eski/yeni formülü yan yana hesaplar; 375/430 ekran görüntüleri piksel-eş olmalı (klinik APK'da sıfır regresyon).
- ACİL DURDUR: GlobalEmergencyStop.tsx DEĞİŞTİRİLMEZ; bobin çalışırken her rotada, alt barın üstünde, bütün görünür (700×540 ve 911×512 kanıt karesi ŞART). Seans başlat/durdur/onay mantığına hiçbir dokunuş yok — bu kök yalnız stil sayıları.
- TEK KAYNAK: ölçek tavanı yalnız tokens.ts'deki OLCEK_TAVAN_BUYUK_EKRAN; ekranlarda Platform/Dimensions ile yerel ölçek YASAK (Dimensions.get yalnız tokens.ts'de kalır — grep kapısı).
- KONTEYNER TAVANI ÖLÇEKLENMEZ: maxWidth ≥ 800 px asla rs() içinde olamaz → layoutMax (Python kapısı, mutasyonla kırmızı kanıtlı).
- SAHNE YÜKSEKLİĞİ: imagePreviewContainer/xaiStage/scStage tek hook'tan (useStageHeight); stil varsayılanı rs(300) korunur (hook'suz kullanım kırılmaz).
- GERİ ALMA: her adım ayrı commit; tavan geri alma = tek satır 1.30. Bellek: geri alımı git checkout ile YAPMA (commit'siz fix'i siler), revert kullan; pre-commit formatlayıcı sonrası `git log -1` doğrula.

**Cihaz testi:**
- Android telefon (klinik, 375-430 dp, APK): Dashboard/Kontrol/AI Hub/Sensörler — ÖNCE ile görsel fark YOK; kamera kutusu (AiProPanel aspectRatio) canlı karede doğru; ACİL DURDUR alt barın üstünde.
- Android telefon YATAY (640-930×360-430): AI Hub önizleme kutusu ≤ %45 yükseklik (≈198-230 px), buton satırı kaydırmadan görünür.
- Android tablet 768-800 dp dikey (supportsTablet=true): sidebar 200 px, içerik ≥ 500 px, yazı 1.07× (önce 1.21×); ızgara 2 sütun düzenli.
- PC WebView2 %100 DPI 1920×1080 maximize: sidebar 240 px, Kontrol içerik 1100 px, ParamField ≤ 260 px, camBox 640×360 ortalı, Sensörler 4+4 kart.
- PC WebView2 pencere 700×540 (tauri min): telefon kabuğu; AI Hub kutusu 243 px, rozet+flip+not aynı karede; bobin çalışırken ACİL DURDUR bütün görünür.
- Laptop 1366×768 @%150 DPI (mantıksal 911×512): tablet düzeni, sidebar 200 px, içerik ≥ 650 px; ACİL DURDUR alt satırı örtmüyor.
- LAN tarayıcı: telefon Chrome/Safari (kısa kenar <480) → telefon ölçeği; PC Chrome → 1.10; pencere yeniden boyutlandırıldığında AI Hub kutusu canlı daralıyor (F12 device toolbar ile).
- DPI %200 1920×1080 (mantıksal 960×540): tablet düzeni, kutu 243 px, sidebar 200 px.

**Açık sorular (sahip kararı):**
- Tavan 1.10 mu 1.0 mı? (Adım 8'de 1920×1080 ve 911×512 önce/sonra kareleriyle sahip kararı; varsayılan 1.10.)
- Klinikte native Android TABLET (APK) fiilen kullanılıyor mu? Kullanılmıyorsa native eşik 600 yalnız katlanabilir/phablet'i etkiler ve 1.10 tabletle sınırlı kalır; kullanılıyorsa tablet karesi cihaz testine eklenmeli.
- 700-767 px WebView2 penceresinde telefon kabuğu (alt bar) kalması istenen davranış mı? Bu kök padding'i 31→26 yapar ama kabuk seçimi S2/L kapsamı — 700 px'te tablet kabuğuna geçilsin mi (breakpoints.tablet 768→700)?
- Modal/kart maxWidth'leri (420-560, 12 nokta) rs() içinde bırakıldı; sahip PC'de diyalogların %10 büyük kalmasını da istemiyorsa ayrı bir küçük adımla (layoutMax.dialog) ölçeksizleştirilebilir — S1'e dahil edilsin mi?
- Ekran görüntüsü betiği (Edge headless + CDP) denetimde vardı; scratchpad'e mi, yoksa depo `pf/scripts/` altına kalıcı görsel-regresyon aracı olarak mı konsun?

**Toplam efor:** ~13.5 saat

### S2 — Pencere genişliğinden ızgara / kompaktlık (9 bulgu: 1 yüksek / 7 orta / 1 düşük)

Bağlı bulgular: `kabuk-2`, `kabuk-8`, `ekranA-1`, `ekranA-2`, `ekranA-3`, `ekranA-13`, `ekranB-1`, `ekranC-1`, `aihub-4`

**Hedef:** Düzen kararları (sütun sayısı, kompakt düğme satırı, hero kart genişliği, profil kartı dizilimi) pencere yerine GERÇEK içerik genişliğinden verilsin; 640/768-899px aralığında tam kenar çubuğu yerine ikon-only 'ray' kabuk çizilsin; web/fare ortamında swipe-gezinme bağlanmasın. Kabuk türü + kenar çubuğu genişliği + içerik genişliği tahmini TEK saf fonksiyonda (theme/layout.ts) toplanıp useResponsive ile paylaşılsın; AppShell ölçtüğü içerik genişliğini context ile aşağı geçirsin; ResponsiveGrid ilk render'da bu tahmini, sonra kendi onLayout ölçümünü kullansın (flicker yok). ACİL DURDUR erişimi ve seans akışı her kabuk türünde (bottom/rail/sidebar) değişmeden kalsın.

**Tasarım kararları:**
- Kabuk türü üç değerli: 'bottom' (alt bar + swipe, telefon) | 'rail' (ikon-only rs(72) kenar çubuğu) | 'sidebar' (mevcut rs(248)). Eşikler: width ≥ 900 → sidebar; native'de width ≥ 768 (tablet dikey/yatay telefon) veya web'de width ≥ 640 (küçültülmüş PC penceresi, launcher min 700) → rail; aksi → bottom. Saf fonksiyon `getShellKind(width, isWeb)` theme/layout.ts'te → jest tablo testi ile kilitlenir.
- Kenar çubuğu genişlikleri tek kaynağa taşınır: `SIDEBAR_WIDTH = rs(248)`, `RAIL_WIDTH = rs(72)` (theme/layout.ts). AppShell stil dosyasındaki sabit buradan okur; useResponsive/ResponsiveGrid AppShell'i import ETMEZ (döngüsel import yok). S1 (SCALE tavanı) düzeltmesi bu sabitleri ölçeksiz yapmak isterse yalnız bu dosya değişir.
- İçerik genişliği iki katmanlı: (1) tahmin `estimateContentWidth = width − kenarÇubuğu − 2×spacing.xl` — ilk render'da ve pencere değiştiğinde anında; (2) ölçüm — AppShell içerik View'ının onLayout değeri. AppShell bunu `ShellLayoutContext` ile sağlar; useResponsive `contentWidth = ctx?.contentWidth ?? width` döndürür → kabuk DIŞINDAKİ ekranlar (Welcome, Auth, Gate) için pencere genişliği, yani mevcut davranış korunur.
- `isCompact` içerik-farkında olur: `layout ∈ {compact, phone} || contentWidth < 560`. AiHubScreen'deki 20 isCompact kullanımının tamamı düzen amaçlı (btnRow → column, %100 genişlik) olduğu grep ile doğrulandı → AiHub'da kod değişikliği gerekmez, aihub-4 hook'tan kapanır.
- ResponsiveGrid: kendi dış View'ını onLayout ile ölçer (SensorMonitor:111 / Kpi:151 / Skeleton:34 deseni). Ölçüm gelene kadar `contentWidth + 2×spacing.sm` tahmini kullanılır (grid'in marginHorizontal −sm olduğundan ölçülen genişlik kap+2sm'dir) → '1 sütun → N sütun' flicker'ı yok. Sütun = clamp(floor(gridW / (rs(minItemWidth) + 2×sm)), 1, columns). `columns` (layout üst sınırı: wide 4) korunur → 1920+ geniş ekranda 5-6 sütun regresyonu olmaz. minItemWidth çağıran yerlerde ölçeksiz kalır, grid içinde rs() ile ölçeklenir (kart içi padding/yazı da rs ile büyüdüğünden tutarlı).
- AppShell'de mevcut `desktop` değişkeninin ADI ve anlamı korunur (`desktop = shellKind !== 'bottom'`): alt bar, 'Daha Fazla' sheet'i, üst-bar Ayarlar ikonu, içerik paddingBottom (rs(160)+inset / rs(84)) ve `GlobalEmergencyStop bottomOffset` mantığı satır satır AYNI kalır → E-stop ofseti regresyonu riski sıfıra yakın. Yeni `rail` yalnız kenar çubuğu genişliğini ve NavButton görünümünü değiştirir.
- Swipe panHandlers yalnız `!desktop && responsive.isNative` iken bağlanır (kabuk-2). Web'de RN-web responder sistemi fare sürüklemesini yakalamaz; telefonda davranış değişmez.
- Dashboard hero kartları hook'suz düzeltilir: `minWidth: rs(280)` → `flexBasis: rs(280), flexShrink: 1, minWidth: 0` (flexGrow korunur). Yoga'da flexShrink varsayılanı 0 olduğundan kart kaptan taşıyordu; flexBasis sarma kararını verir, flexShrink tek başına kalınca kapa sığdırır → kart-içi ACİL DURDUR düğmesinin sağ kenarı kırpılmaz.
- Welcome kendi `width < 768` eşiğini bırakıp `useResponsive().layout` kullanır; kart sarmalayıcıya layout'a göre flexBasis (tablet %47 + maxWidth rs(380); desktop/wide %30) verilir. Welcome kabuk dışında olduğundan contentWidth = width → 'isMobile' anlamı değişmez.
- GlobalEmergencyStop'a DOKUNULMAZ: root düzeyinde absolute (left/right spacing.md, ortalanmış, zIndex 10000) kaldığından kabuk türünden bağımsız her rotada görünür; rail (94px) ile ortalanmış ~250px düğme 768px'te çakışmaz (ölçüm: düğme ≈259-509px aralığında).
- Test mock'ları: AppShell.logout/pairing testleri useResponsive'ı sabit nesneyle mock'luyor; yeni alanlar (shellKind, contentWidth, isNative) mock'a eklenir, aksi hâlde `shellKind` undefined → 'bottom' varsayımıyla desktop testleri kırılır. Mutasyon-önce kuralı: ResponsiveGrid testi önce eski (width tabanlı) kodla KIRMIZI görülür, sonra düzeltme uygulanır.

| # | Adım | Dosyalar | Değişiklik | Kapattığı | Doğrulama | Risk | Efor (s) |
|---|---|---|---|---|---|---|---|
| 1 | Kabuk düzeni tek kaynağı: theme/layout.ts + ShellLayoutContext | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\theme\layout.ts (YENİ)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\context\ShellLayoutContext.ts (YENİ)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\theme\__tests__\layout.test.ts (YENİ)` | Saf, bağımlılıksız (yalnız tokens.rs/spacing) modül: ShellKind tipi, SIDEBAR_WIDTH/RAIL_WIDTH sabitleri, eşikler (SIDEBAR_MIN=900, RAIL_MIN_NATIVE=768, RAIL_MIN_WEB=640, COMPACT_CONTENT=560), getShellKind(width,isWeb), shellSidebarWidth(kind), estimateContentWidth(width,kind). Ayrı dosyada `ShellLayoutContext = create… | `kabuk-2`, `ekranA-3` | jest tablo testi (layout.test.ts): [639,web]→bottom, [640,web]→rail, [700,web]→rail (launcher min penceresi), [767,native]→bottom, [768,native]→rail, [899,*]→rail, [900,*]→sidebar, [1920,*]→sidebar; … | Düşük — henüz hiçbir tüketici yok, davranış değişmez. Geri alma: iki dosyayı sil. | 1 |
| 2 | useResponsive'a shellKind / contentWidth / içerik-farkında isCompact | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\hooks\useResponsive.ts`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\hooks\__tests__\useResponsive.test.tsx (YENİ)` | Hook `ShellLayoutContext`'i okur; `contentWidth = ctx?.contentWidth ?? width` (kabuk dışında pencere = mevcut davranış); `shellKind = getShellKind(width, isWeb)`; `isCompact = layout compact/phone || contentWidth < COMPACT_CONTENT`; ek `sidebarWidth`, `isPointer` (= isWeb; ileride hover:hover sorgusuna genişletilebili… | `aihub-4`, `kabuk-2` | renderHook testi (useWindowDimensions mock'lu): (a) 768px, context yok → isCompact false, contentWidth 768; (b) 768px, Provider {contentWidth: 340} → isCompact TRUE (aihub-4 senaryosu); (c) 1280px, P… | Düşük-orta — isCompact anlamı genişliyor; tüm tüketiciler (AiHubScreen 20 kullanım, 2 AppShell testi) grep ile düzen amaçlı doğrulandı. AppShell context sağlay… | 1.5 |
| 3 | ResponsiveGrid: onLayout ölçümü + tahminle ilk render + rs(minItemWidth) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\ResponsiveGrid.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\ResponsiveGrid.test.tsx (YENİ — ÖNCE yaz, kırmızı gör)` | Satır 12-13'teki `width / columns < minItemWidth` hesabı kaldırılır. Dış View'a onLayout; ölçüm gelene kadar `contentWidth + 2×spacing.sm` (grid marginHorizontal −sm olduğundan) tahmini kullanılır; sütun = clamp(floor(gridW / (rs(minItemWidth) + 2×sm)), 1, columns). 1px altı onLayout titreşimi setState'i tetiklemez. C… | `ekranA-1`, `ekranB-1`, `ekranC-1`, `kabuk-8` | RNTL testi: useResponsive mock'lanır ({contentWidth: 352, columns: 2, ...}) → 4 çocuklu grid, minItemWidth 260 → hücre flexBasis '100%' (1 sütun; eski kod 2 sütun → test ÖNCE KIRMIZI); `fireEvent(get… | Orta — 6 ekranı etkiler (Dashboard, Control, Patient, KPI, TreatmentHistory, AiHub). rs() ile ölçekleme PC'de (SCALE 1.3) sütun sayısını DÜŞÜRÜR (örn. 1024px +… | 2.5 |
| 4 | AppShell: rail kabuğu, içerik genişliği context'i, web'de swipe kapalı | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\AppShell.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\AppShell.logout.test.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\AppShell.pairing.test.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\AppShell.rail.test.tsx (YENİ)` | (a) :99 `desktop = responsive.isDesktop || responsive.isTablet` → `const { shellKind } = responsive; const desktop = shellKind !== 'bottom'; const rail = shellKind === 'rail';` — `desktop` adı ve tüm alt tüketicileri (alt bar, sheet, Ayarlar ikonu, paddingBottom, GlobalEmergencyStop bottomOffset) DEĞİŞMEZ. (b) :246 pa… | `ekranA-3`, `kabuk-2`, `kabuk-8`, `aihub-4` | AppShell.rail.test.tsx: useResponsive mock {width: 800, shellKind:'rail', isNative:false, isWeb:true} → alt bar (accessibilityLabel 'Daha Fazla') YOK, nav düğmeleri accessibilityLabel ile var ama eti… | HASTA GÜVENLİĞİ (orta, yönetilen): GlobalEmergencyStop root'ta absolute kalır ve `desktop` semantiği değişmediğinden ofseti aynı; rail'de alt bar olmadığından … | 4.5 |
| 5 | Dashboard hero kartları: minWidth → flexBasis + flexShrink | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\DashboardScreen.tsx` | styles.patientCard/treatmentCard (:188-189): `minWidth: rs(280)` yerine `flexBasis: rs(280), flexShrink: 1, minWidth: 0` (flex: 1 / 1.4 → flexGrow: 1 / 1.4). Sarma kararı flexBasis ile aynı kalır (iki kart 364+364+16 > kap → alt alta), tek başına kalan kart kaptan geniş olamaz → kart-içi ACİL DURDUR düğmesinin sağ ken… | `ekranA-2` | Ekran görüntüsü 768×1024 (rail sonrası içerik ≈612px → iki kart alt alta, kenar taşması yok) ve 1280×800 (yan yana, 1:1.4 oran korunur); jest snapshot gerekmez. Cihaz: iPad dikeyde donanım çalışırken… | Düşük — yalnız stil; düğmenin onPress'i ve accessibility'si değişmez. Geri alma: iki satır. | 0.5 |
| 6 | Button etiketi taşma emniyeti (aihub-4 ikincil) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\Button.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\Button.test.tsx` | styles.label (:162) → `{ color: colors.white, fontWeight: '700', flexShrink: 1 }`; label Text'e zaten `numberOfLines={1}` varsa ellipsis işler, yoksa eklenir. Yoga'da flexShrink 0 olduğundan native'de metin komşu düğmenin üstüne taşıyordu, web'de sert kırpılıyordu. AiHubScreen'de kod değişikliği YOK (isCompact adım 2'… | `aihub-4` | Button.test.tsx'e: label Text stilinin `flexShrink: 1` içerdiği (StyleSheet.flatten) assert'i; mevcut Button testleri yeşil. Ekran görüntüsü 768×1024 AI Hub → 'Galeriden Seç / Fotoğraf Çek / Canlı Ka… | Düşük — Button uygulama genelinde kullanılıyor; flexShrink yalnız sığmayan durumda devreye girer, normal düğmelerde görsel fark yok. Seans Başlat/Durdur düğmel… | 0.5 |
| 7 | WelcomeScreen: kendi eşiği yerine useResponsive().layout | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\WelcomeScreen.tsx` | :22-24 `useWindowDimensions` + `isMobile = width < 768` → `const { layout, isCompact } = useResponsive(); const isMobile = isCompact;` (kabuk dışında contentWidth = width → anlam aynı). :67 cardsContainer flexDirection korunur. cardWrapper (:209-212) `flex: 1, minWidth: rs(280)` → layout'a göre inline: tablet → `{ fle… | `ekranA-13` | Ekran görüntüsü 768×1024 (2 kart yan yana + 3. ortalanmış, kart ≤ rs(380)), 1024×768 (3 kart tek satır), 800×360 (kartlar kaydırılabilir, üst çubuk görünür), 390×844 (dikey liste — değişmemeli). Mevc… | Düşük — Welcome kabuk dışı, seans akışına girmez. Geri alma: tek dosya. | 1 |
| 8 | CI sözleşme kapısı (Python) + tam jest süiti | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\tests\test_responsive_kabuk_sozlesmesi.py (YENİ)` | Kök .github CI'da koşan pytest'e küçük sözleşme: (1) ResponsiveGrid.tsx `onLayout` içerir ve `width / columns` ifadesi YOK; (2) AppShell.tsx'te panHandlers bağlanan satır `isNative` içerir; (3) AppShell.tsx `ShellLayoutContext.Provider` içerir; (4) useResponsive.ts `COMPACT_CONTENT` okur. Memory kuralı gereği her asse… | `kabuk-8`, `kabuk-2` | `cd guii/pf && npx jest` TAM süit yeşil (yapısal çıpa kayması memory'si: yalnız yeni testler değil, hepsi); `npm run typecheck`; `pytest guii/tests -k 'responsive or surum'`; her yeni assert için bir… | Düşük — yalnız test. Geri alma: dosyayı sil. | 1.5 |
| 9 | Görsel + cihaz doğrulaması ve seans/E-stop tur testi | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\docs\screenshots (karşılaştırma çıktıları)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf (export:web)` | Kod değişikliği yok. `npm run export:web` → Edge headless + CDP (denetim yöntemi; `--window-size` innerWidth'i değiştirmiyor, setDeviceMetricsOverride şart) ile 11 görünüm alanı (320×568, 390×844, 640×360, 700×540, 768×1024, 800×360, 911×512, 1024×768, 1280×800, 1920×1080, 2560×1440) × 6 grid ekranı + Welcome + AI Hub… | `ekranA-1`, `ekranB-1`, `ekranC-1`, `ekranA-2`, `ekranA-3`, `ekranA-13`, `aihub-4`, `kabuk-2` | Kabul ölçütleri: 768×1024'te Dashboard MetricCard 2 sütun ≥ rs(180) hücre, CoilCard tek sütun tam genişlik; Kontrol bobin kartı ≥ rs(320) (başlık rozetleri tek satır); Hastalar kartında ad okunur + 3… | Doğrulama adımı; bulgu çıkarsa ilgili adıma dönülür. Fiziksel cihaz eksikse (iPad) Edge 768×1024 + Android emülatör tablet profili ile geçilir, iPad 'kısmen do… | 3 |

<details><summary>Kod taslakları</summary>

**1. Kabuk düzeni tek kaynağı: theme/layout.ts + ShellLayoutContext**

```
// theme/layout.ts
import { rs, spacing } from "@/theme/tokens";
export type ShellKind = "bottom" | "rail" | "sidebar";
export const SIDEBAR_WIDTH = rs(248);
export const RAIL_WIDTH = rs(72);
export const SIDEBAR_MIN = 900, RAIL_MIN_NATIVE = 768, RAIL_MIN_WEB = 640, COMPACT_CONTENT = 560;
export function getShellKind(width: number, isWeb: boolean): ShellKind {
  if (width >= SIDEBAR_MIN) return "sidebar";
  if (width >= (isWeb ? RAIL_MIN_WEB : RAIL_MIN_NATIVE)) return "rail";
  return "bottom";
}
export const shellSidebarWidth = (k: ShellKind) => k === "sidebar" ? SIDEBAR_WIDTH : k === "rail" ? RAIL_WIDTH : 0;
export const estimateContentWidth = (width: number, k: ShellKind) => Math.max(0, width - shellSidebarWidth(k) - 2 * spacing.xl);
// context/ShellLayoutContext.ts
export const ShellLayoutContext = createContext<{ contentWidth: number } | null>(null);
```

**2. useResponsive'a shellKind / contentWidth / içerik-farkında isCompact**

```
const ctx = useContext(ShellLayoutContext);
const isWeb = Platform.OS === "web";
const shellKind = getShellKind(width, isWeb);
const contentWidth = ctx?.contentWidth ?? width;   // kabuk dışı (Welcome/Auth) → pencere
const isCompact = layout === "compact" || layout === "phone" || contentWidth < COMPACT_CONTENT;
return { width, height, layout, columns, isCompact, isTablet, isDesktop, isWeb, isNative: !isWeb, isPointer: isWeb, shellKind, sidebarWidth: shellSidebarWidth(shellKind), contentWidth };
```

**3. ResponsiveGrid: onLayout ölçümü + tahminle ilk render + rs(minItemWidth)**

```
const { contentWidth, columns } = useResponsive();
const [measured, setMeasured] = useState(0);
const gridW = measured || contentWidth + 2 * spacing.sm;
const unit = rs(minItemWidth) + 2 * spacing.sm;
const targetColumns = Math.max(1, Math.min(columns, Math.floor(gridW / unit)));
const basis = `${100 / targetColumns}%` as const;
const onLayout = (e: LayoutChangeEvent) => { const w = e.nativeEvent.layout.width; if (Math.abs(w - measured) > 1) setMeasured(w); };
<View style={styles.grid} onLayout={onLayout} testID="responsive-grid">
```

**4. AppShell: rail kabuğu, içerik genişliği context'i, web'de swipe kapalı**

```
const { shellKind } = responsive;
const desktop = shellKind !== "bottom";   // ad + tüm alt mantık korunur
const rail = shellKind === "rail";
const [contentW, setContentW] = useState(() => estimateContentWidth(responsive.width, shellKind));
useEffect(() => { setContentW(estimateContentWidth(responsive.width, shellKind)); }, [responsive.width, shellKind]);
...
<View style={styles.main} {...(!desktop && responsive.isNative ? panResponder.panHandlers : {})}>
...
<ScrollView contentContainerStyle={!desktop ? { paddingBottom: rs(160) + insets.bottom } : { paddingBottom: rs(84) }} keyboardShouldPersistTaps="handled">
  <View style={styles.contentInner} onLayout={(e) => setContentW(e.nativeEvent.layout.width)}>
    <ShellLayoutContext.Provider value={{ contentWidth: contentW }}>{children}</ShellLayoutContext.Provider>
  </View>
</ScrollView>
// NavButton
{!rail && <Text style={[...]} numberOfLines={1}>{label}</Text>}
```

**5. Dashboard hero kartları: minWidth → flexBasis + flexShrink**

```
patientCard:   { flexGrow: 1,   flexShrink: 1, flexBasis: rs(280), minWidth: 0, gap: spacing.md },
treatmentCard: { flexGrow: 1.4, flexShrink: 1, flexBasis: rs(280), minWidth: 0, gap: spacing.md },
```

**6. Button etiketi taşma emniyeti (aihub-4 ikincil)**

```
label: { color: colors.white, fontWeight: "700", flexShrink: 1 },
```

**7. WelcomeScreen: kendi eşiği yerine useResponsive().layout**

```
const { layout, isCompact, height } = useResponsive();
const wrap = layout === "tablet" ? { flexBasis: "47%" as const, flexGrow: 0, maxWidth: rs(380) }
  : (layout === "desktop" || layout === "wide") ? { flexBasis: "30%" as const, flexGrow: 1, maxWidth: rs(420) }
  : { width: "100%" as const };
<FadeInView delay={90} style={[styles.cardWrapper, wrap]}>
```

**8. CI sözleşme kapısı (Python) + tam jest süiti**

```
grid = (KOK/'pf/src/components/ui/ResponsiveGrid.tsx').read_text(encoding='utf-8')
kod = '\n'.join(l for l in grid.splitlines() if not l.strip().startswith('//'))
assert 'onLayout' in kod, 'grid kendi genişliğini ölçmüyor (S2 regresyonu)'
assert 'width / columns' not in kod, 'sütun yine PENCERE genişliğinden'
shell = (KOK/'pf/src/components/ui/AppShell.tsx').read_text(encoding='utf-8')
assert re.search(r'panHandlers[^\n]*isNative|isNative[^\n]*panHandlers', shell), 'swipe web\'de de bağlı'
```

</details>

**Bağımlılıklar:** Adım sırası zorunlu: 1 → 2 → 3 → 4; 5/6/7 adım 2'den sonra bağımsız; 8-9 en son. Adım 4 tamamlanana kadar contentWidth = width olduğundan adım 2-3 ara durumda eski davranışı korur (güvenli aşamalı birleştirme).; S1 (tokens.ts SCALE tavanı) bu planın ÖNÜNDE değil; ancak S1 uygulanınca SIDEBAR_WIDTH/RAIL_WIDTH'in rs()'siz sabitlenmesi yalnız theme/layout.ts'i değiştirir (tasarım kararı 2). S1 uygulanmadan önce rail'de RAIL_WIDTH = rs(72) = 94px olur (kabul edilebilir).; S5 (yükseklik/isShort) bu hook'a `isShort` ekleyip 800×360 yatay telefonda rail yerine bottom'a düşürmek isteyebilir → getShellKind imzası `(width, isWeb, height?)` olarak genişletilebilir; şimdi 3 parametreli tasarlanmadı, açık soru.; AppShell jest testleri (logout/pairing) useResponsive'ı sabit nesneyle mock'luyor → adım 4 ile birlikte mock güncellemesi ŞART, aksi hâlde shellKind undefined.; Python sözleşme kapısı guii/tests/test_surum_kaymasi_guvenlik_sozlesmesi.py AppShell.tsx'te `<SurumFarkiBanner />` string'ini arıyor — adım 4'te bu satır aynen korunmalı.; Ekran görüntüsü doğrulaması için pf web export (`npm run export:web`, scripts/postexport-web.js) ve Edge headless; embedded python ile çıktı alınırken PYTHONIOENCODING=utf-8 (memory).

**Kilitler:**
- GlobalEmergencyStop bileşenine ve AppShell'deki `<GlobalEmergencyStop bottomOffset={desktop ? 0 : rs(76)} />` satırına DOKUNULMAZ; `desktop` değişkeninin anlamı 'alt bar YOK' olarak korunur (rail ve sidebar ikisi de desktop=true).
- Alt bar / 'Daha Fazla' sheet / içerik paddingBottom (rs(160)+inset) mantığı satır satır aynı kalır; yalnız kenar çubuğu genişliği ve NavButton görünümü değişir.
- Telefonda (native, shellKind=bottom) swipe-gezinme davranışı değişmez; yalnız web'de bağlanmaz.
- Bağlantı durumu 2-durumlu (online/offline) kalır; profil kalıcılığı eklenmez; SurumFarkiBanner/UpdateBanner/RecoveryCodeBanner sıralaması korunur (mevcut memory kararları).
- ResponsiveGrid'in Children.toArray + stabil key düzeltmesi (hayalet hücre) korunur.
- tokens.ts SCALE'e bu planda dokunulmaz (S1'in işi); rs(248)/rs(72) sabitleri theme/layout.ts'e taşınır ama değerleri değişmez.
- Kontrol ekranı bobin Başlat/Durdur ve CoilParameterPanel iç düzeni bu planda değişmez (ekranB-1'in header flexWrap/flexShrink önerileri ayrı, S2-dışı kozmetik adım olarak sonraya).
- AiHubScreen'de kod değişikliği yapılmaz (isCompact hook'tan içerik-farkında olur) — 20 kullanımın hepsinin düzen amaçlı olduğu grep ile teyit edildi.

**Cihaz testi:**
- iPad 768×1024 dikey (sınıf d): rail kenar çubuğu, Dashboard metrik 2 sütun / bobin 1 sütun, Kontrol bobin kartı başlığı tek satır, Hastalar kartında ad + 3 düğme kart içinde, AI Hub 3 düğme alt alta, Welcome 2+1 kart; seans başlat → kayan ACİL DURDUR görünür ve çalışır.
- iPad 1024×768 yatay: tam sidebar (≥900), 2 sütun bobin kartı; E-stop ofseti 0, alt bar yok.
- Android telefon yatay 800×360 (sınıf c): rail (native ≥768) + içerik kaydırılabilir; E-stop görünür; S5 gelene kadar 'kabul edilebilir' notu.
- Android telefon dikey 390×844: HİÇBİR DEĞİŞİKLİK — alt bar, swipe-gezinme (sola/sağa çekince sekme), 'Daha Fazla' sheet, E-stop rs(76) ofseti aynen.
- PC WebView2 (sınıf e): launcher 'app' penceresi maximize → tam sidebar; pencere 700-899px'e daraltılınca rail'e, 640'ın altına inemez (minWidth 700); içerikte fare ile yatay sürükleme sekme DEĞİŞTİRMEZ; 900'ü geçince tam sidebar'a döner (histerezis yok — titreme gözlenirse açık soru 3).
- 1366×768 @%150 DPI dizüstü (sınıf g, 911×512 mantıksal): rail + Kontrol bobin kartları ≥ rs(320); @%200 (683px): rail (web ≥640) — telefon kabuğu görülmez.
- LAN tarayıcı (sınıf h) Chrome/Safari 1280 ve 768: web export ile aynı kabuk; Safari'de onLayout ölçümü ilk render'da geliyor mu (flicker) gözle.
- PEMF_SIMULATE=1 sanal donanımla her kabuk türünde tam seans turu: hasta seç → Seans Başlat → E-stop → geçmişe kayıt; ayrıca donanım 'seans dışı çalışıyor' durumunda Dashboard kart-içi ACİL DURDUR'un rail kabuğunda kırpılmadan görünmesi.

**Açık sorular (sahip kararı):**
- Rail eşiği native tabletlerde de 768-899 mü olsun (planın varsayımı: EVET, ekranA-3 önerisi) yoksa yalnız web'de mi? Native tablet dikeyde alternatif 'alt bar' (desktop=isDesktop) daha az kod ama ekranA-3 rail'i öneriyor.
- SIDEBAR_MIN=900 sınırı: 900-1023px'te tam sidebar (322px) ile içerik ≈516-640px kalır (Patient 340→442 ile 1 sütun). 1024 (desktop breakpoint) daha tutarlı olabilir; sahip tercihi.
- Pencere 899↔900 sınırında sürekli yeniden boyutlandırmada rail↔sidebar titremesi olursa 16px histerezis eklensin mi? (İlk sürümde yok; cihaz testi 5'te gözlenecek.)
- ResponsiveGrid'de minItemWidth'in rs() ile ölçeklenmesi PC'de sütun sayısını düşürür (tasarım kararı 5). S1 SCALE tavanı düşürülünce bu etki azalır; S1 önce mi uygulanmalı, yoksa S2 rs()'siz mi başlasın?
- S5 ile ortak imza: getShellKind'a height parametresi (isShort → bottom) şimdi mi eklensin? Planda eklenmedi; S5 sahibi karar versin.
- ekranB-1'in CoilParameterPanel header flexWrap / readingValue adjustsFontSizeToFit ikincil önerileri bu S2 planının dışında bırakıldı (kozmetik, ayrı adım) — S2 kapanışı için yeterli sayılacak mı?

**Toplam efor:** ~16 saat

### S3 — Dokunma hedefleri (18 bulgu: 0 yüksek / 8 orta / 10 düşük)

Bağlı bulgular: `ekranA-10`, `ekranA-14`, `ekranB-4`, `ekranB-15`, `ekranC-5`, `ekranC-7`, `ekranC-8`, `aihub-5`, `ilkel-3`, `ilkel-4`, `ilkel-5`, `ilkel-7`, `matris-8`, `ampirik-4`, `ampirik-5`, `kapsam-2`, `kapsam-3`, `kapsam-5`

**Hedef:** Tüm dokunulabilir öğeler (a-d, i sınıfları: 320-430 px telefon, tablet, yazı ölçeği 0.85-1.3) ≥ 44 px (çipler ≥ 40 px + gap ≥ 8) olsun; minimumlar rs() ile AŞAĞI ölçeklenmesin; komşu hedefler binişmesin (hitSlop ≤ gap/2). Bu değişmezler tests/ altında sabit-sayaçlı statik kapı + jest primitif testleriyle kilitlensin. Site ve launcher'da yalnız dokunmatik cihazlarda (`pointer: coarse`) 44 px taban. ACİL DURDUR (GlobalEmergencyStop.btn minHeight rs(52) = 44-68 px) ve seans başlat/durdur akışına DOKUNULMAZ; yalnız tabana eklenir.

**Tasarım kararları:**
- ORTAK TOKEN: tokens.ts'e `touch = { min: Math.max(44, rs(44)), sm: Math.max(40, rs(40)), slop: {top:8,bottom:8,left:8,right:8}, slopFor(gap) }` — tabanlar ölçekle BÜYÜR ama küçülmez (ilkel-7 kökü). `slopFor(gap)=Math.max(0, Math.floor(gap/2))` bobin-seçici kuralını tek yere pinler.
- İKİ YENİ İLKEL, SIFIR GÖRSEL DEĞİŞİKLİK İLKESİ: `components/ui/Chip.tsx` (minHeight touch.sm, paddingVertical spacing.sm, hitSlop 4) ve `components/ui/IconButton.tsx` (AppShell.iconBtn deseni: minWidth/minHeight touch.min + hitSlop 8 + zorunlu accessibilityLabel). Her ikisi `style/activeStyle/textStyle` geçişine izin verir → mevcut renkler (axisChipMag, organChipActive, #1d4ed8 vb.) aynen kalır; göç = stil objesini prop'a taşımak.
- MİNİMUM DEĞİŞİKLİK: ikon-only TouchableOpacity'ler IconButton'a; çip dizileri Chip'e; metin-bağlantılar ve segment/tab düğmeleri yalnız `minHeight: touch.min` + paddingVertical eklemesiyle (bileşen ağacı değişmez, mevcut jest testleri — PatientGate.test, SurumFarkiBanner.test, MobileUpdateBanner.test, AiSpecApprovalModal.test — aynı accessibilityLabel'larla geçmeye devam eder).
- hitSlop ≤ gap/2 KURALI: CoilSelector width/height `touch.min`, grid gap spacing.sm, hitSlop `touch.slopFor(spacing.sm)` (3-5 px). RN hit-test'te aralığa dokunuş sağdaki kardeşe gidiyordu; kural binişmeyi sıfırlar.
- WEB PARİTESİ: RNW'de hitSlop garantisi yok (ampirik-4 kararı) → AuthScreen/Settings/Welcome'da çözüm padding+minHeight (her iki platformda çalışır); hitSlop yalnız native ek tampon.
- SİTE/LAUNCHER: fare kullanıcısına görsel bedel ödetmemek için `@media (pointer: coarse)` altında 44 px taban; Tailwind v4 tarafında ek olarak `min-h-11` sınıfı doğrudan (metin bağlantıları için her cihazda zararsız).
- STATİK KAPI (pytest, tests/test_dokunma_hedefi_kapisi.py): Pressable/TouchableOpacity JSX açılışı → style referanslarını StyleSheet.create bloğuna çözer; `touch.*`/`minHeight ≥ 44`/`hitSlop ≥ 10`/`styles.iconBtn` varsa GEÇER; çözülemeyen dinamik stil 'belirsiz' sayacına; `// dokunma-hedefi: muaf (gerekçe)` satır-öncesi yorumu ile gerekçeli muafiyet. İki SABİT SAYAÇ (ihlal + muaf) eşitlik kontrolü (memory: 'Route Contract Sayaç Kapısı'/'Kapı KIRMIZI olduğunu kanıtla' — kapı içinde sentetik mutasyon öz-testi).
- HASTA GÜVENLİĞİ SINIRI: GlobalEmergencyStop.tsx ve ControlScreen seans başlat/durdur düğmeleri (Button primitifi) bu turda YALNIZ taban artışı görür (Button.size_md `Math.max(touch.min, rs(46))`); E-stop rs(52) zaten 0.85'te 44 → dokunulmaz. Her adım ayrı commit; geri alma = tek `git revert`.
- SEGMENT/TAB: `minHeight: touch.min` yerine `touch.sm` (40) — tam genişlikte yarım düğmeler, ikinci doğrulama 'düşük' dedi; 44 header'ı büyütürdü.

| # | Adım | Dosyalar | Değişiklik | Kapattığı | Doğrulama | Risk | Efor (s) |
|---|---|---|---|---|---|---|---|
| 1 | tokens.ts'e ölçekle küçülmeyen `touch` token'ı | `pf/src/theme/tokens.ts` | rf() tanımının altına `touch` export'u. `min`/`sm` aşağı ölçeklenmez (Math.max), yukarı ölçeklenir (tablet 1.3 → 57/52). `slop` standart hitSlop, `slopFor(gap)` binişme kuralı. Ayrıca `typography.small` için 12 px taban SADECE dokunulabilir metinlerde kullanılmak üzere `touch.linkFont = Math.max(12, rf(11))` (ampirik-… | `ilkel-7` | jest: pf/src/theme/__tests__/touch.test.ts — `jest.isolateModules` + `Dimensions.get` mock 320×568 → `touch.min===44 && rs(44)===38` (tabanın gerçekten devreye girdiğini kanıtlar); 430×932 → `touch.m… | Yok (yalnız yeni export). Geri alma: dosyadan bloğu sil. | 0.5 |
| 2 | Button, AppShell.iconBtn ve modal düğmelerinde rs(44/46/38) → touch.* | `pf/src/components/ui/Button.tsx`, `pf/src/components/ui/AppShell.tsx`, `pf/src/components/domain/BackupPassphraseDialog.tsx`, `pf/src/components/domain/OperatorSwitcher.tsx` | Button.tsx:153-155 `size_sm: minHeight touch.sm`, `size_md: Math.max(touch.min, rs(46))`, `size_lg: Math.max(touch.min, rs(54))`. AppShell.tsx:593 `iconBtn: { minWidth: touch.min, minHeight: touch.min, ... }`. BackupPassphraseDialog.tsx:114/115/119/124 ve OperatorSwitcher.tsx:209/214/218/221 `minHeight: rs(44)` → `min… | `ilkel-7` | jest: Button.test.tsx'e `StyleSheet.flatten(getByRole('button').props.style).minHeight >= 44` (320 mock) eklenir; mevcut BackupPassphraseDialog.test / AppShell.logout.test yeşil kalır. Ekran görüntüs… | DÜŞÜK. Seans düğmeleri büyür ama davranış aynı; çift-tık koruması değişmez. PIN diyaloğunda (OperatorSwitcher) liste satırı büyür → maxHeight rs(200) içinde da… | 1 |
| 3 | IconButton ilkeli + 9 ikon-only düğmenin göçü (X kapat, zil, bağlantı yenile, yenile, not düzenle) | `pf/src/components/ui/IconButton.tsx (yeni)`, `pf/src/components/ui/AppShell.tsx`, `pf/src/components/domain/PatientGate.tsx`, `pf/src/components/domain/AiSpecApprovalModal.tsx` | Yeni `IconButton` (Pressable sarmalı, `label` zorunlu → accessibilityLabel, `style` geçişi). Göç: AppShell:275-284 wsContainer Pressable → `style={[styles.iconBtn, styles.wsContainer]} hitSlop={touch.slop}` (nokta 44 px kutuda ortalanır; çevrimdışı metni flexShrink korunur); AppShell:285-298 zil → `style={[styles.icon… | `matris-8`, `ilkel-3`, `kapsam-2`, `kapsam-3`, `kapsam-5`, `ekranB-4`, `ekranC-5` | jest: IconButton.test.tsx (flatten minWidth/minHeight ≥ 44; label yoksa TS hatası). Mevcut PatientGate.test / AiSpecApprovalModal.test / MobileUpdateBanner.test / SurumFarkiBanner.test `getByLabelTex… | ORTA (ekranB-4/ekranC-5'in çip kısmı adım 5/7'de kapanır; buradaki kapatma yalnız ikon parçası). AppShell header yüksekliği artar → içerik alanı ~10 px azalır;… | 2.5 |
| 4 | Chip + ChipRow ilkeli (görsel geçişli, 40 px taban, gap spacing.sm) | `pf/src/components/ui/Chip.tsx (yeni)`, `pf/src/components/ui/__tests__/Chip.test.tsx (yeni)` | `Chip({label, active, onPress, style, activeStyle, textStyle, activeTextStyle, accessibilityLabel, disabled, left?})`: TouchableOpacity, `accessibilityRole='button'`, `accessibilityState={{selected: active}}`, minHeight touch.sm, paddingVertical spacing.sm, paddingHorizontal spacing.md, borderRadius radius.full, justi… |  | jest Chip.test.tsx: 320 mock'ta flatten minHeight ≥ 40; `fireEvent.press` onPress 1 kez; `accessibilityState.selected` aktifle değişir; `style` override rengi ezer ama minHeight'ı ezemez (style dizis… | Yok (henüz kullanılmıyor). Geri alma: dosyayı sil. | 1.5 |
| 5 | Çip dizilerinin Chip/ChipRow'a göçü (7 dosya, 11 çip stili) | `pf/src/components/domain/ObservationNotesModal.tsx`, `pf/src/screens/AiHistoryScreen.tsx`, `pf/src/screens/SensorMonitorScreen.tsx`, `pf/src/screens/ControlScreen.tsx` | ObservationNotesModal:123-133 REACTIONS → `<ChipRow>` + `<Chip style={styles.chip} activeStyle={styles.chipActive} ...>`; `styles.chips` silinir; isCompact'ta `style={{ flexBasis: '48%' }}` (2 sütun, CoilCard.mini deseni). AiHistoryScreen:389-400 yerel `Chip` fonksiyonu kaldırılır, ui/Chip import edilir (yatay ScrollV… | `ilkel-4`, `ekranC-8`, `ekranB-4`, `aihub-5`, `ekranA-10` | jest: gozlemNotuKorunmasi.test.tsx + AiProPanel*.test.tsx yeşil (Chip aynı accessibilityRole/label; `getByText('Vazgeç')` çalışır). Adım 9 kapısı sayaç düşer. Ekran görüntüsü 320/375/768 + Android ya… | ORTA — en geniş adım. AiProPanel 'Vazgeç' hazırlık iptali güvenlik eylemi: test_ai_pro_asamali_akis + AiProPanelB1.test onPress kimliğini doğrular. AiHub 3.6k … | 4 |
| 6 | CoilSelector: 44 px kare + gap spacing.sm + hitSlop ≤ gap/2 + seçili durumda yalnız-renk-değil | `pf/src/screens/ControlScreen.tsx` | :962-972 `coilSelectorGrid gap: spacing.sm`; `coilSelectorBtn width/height: touch.min`; `coilSelectorBtnActive` + `borderWidth: 2`; :808 `hitSlop={touch.slopFor(spacing.sm)}` (3-5 px, binişme 0). Metin: seçiliyken `✓` öneki yerine (rakam tek karakter, kutu 44) `accessibilityState.selected` zaten var; görsel için borde… | `ekranB-15` | jest: yeni `coilSelectorHitSlop.test.tsx` — 320 mock'ta render, `getByLabelText(/Bobin 3/)` props.hitSlop.left*2 ≤ flatten(grid).gap; width ≥ 44. Mevcut coilDurdurmaOnayi.test / CoilDurationHonesty.t… | HASTA GÜVENLİĞİ İLGİLİ (yanlış bobin seansa girer) ama değişiklik dokunma alanını DARALTIP netleştirir; onToggle mantığı değişmez. Seans sürerken selector zate… | 0.75 |
| 7 | Metin bağlantıları, segment/tab düğmeleri, giriş alanları: padding + touch tabanı | `pf/src/screens/AuthScreen.tsx`, `pf/src/screens/SettingsScreen.tsx`, `pf/src/screens/WelcomeScreen.tsx`, `pf/src/components/ui/NotificationCenter.tsx` | AuthScreen: :491 `forgotRow: { alignSelf:'flex-end', minHeight: touch.min, justifyContent:'center', paddingHorizontal: spacing.sm, marginTop: rs(-4) - spacing.sm }`; :492 forgotText `fontSize: touch.linkFont`; :535 `switchRow: { alignItems:'center', justifyContent:'center', minHeight: touch.min, marginTop: 0 }`, switc… | `ampirik-4`, `ampirik-5`, `ekranA-10`, `ekranA-14`, `ilkel-5`, `ekranC-5`, `ekranC-7` | Ampirik: denetimin CDP betiğiyle (metrics_pf_gate.json üreten) web export 320/390 → 'Şifremi unuttum?' h ≥ 44, tabs h ≥ 40, inputs h ≥ 44, tiny-metin listesi boş. jest: AppShell.logout.test (Welcome … | DÜŞÜK-ORTA. Welcome 'Çıkış' ve Settings 'Farklı Profile Geçiş' seans-teardown yolları: yalnız stil, guardTeardown çağrısı değişmez (test_desktop_session/AppShe… | 2.5 |
| 8 | AppShell profileChip + wsContainer için dosya-içi düzeltme ve header yükseklik kontrolü | `pf/src/components/ui/AppShell.tsx` | Adım 3'ün AppShell parçasının tamamlayıcısı: :594 `profileChip: minHeight: touch.min` (paddingVertical xs korunur, alignItems center → ikon ortalanır). headerRight gap spacing.md korunur; wsContainer/zil/ayarlar/profil dört öğe 320 px'te ~44×4 + 3×12 = 212 px → headerLeft `flex:1, minWidth:0` başlığı kısaltır (mevcut … | `matris-8` | Ekran görüntüsü 320×568, 375×812, 768×1024 (web export + Android emülatör): header sağ grubu taşmıyor, başlık okunur. jest AppShell.pairing.test / AppShell.logout.test yeşil. onLayout ile header yüks… | DÜŞÜK. Header büyümesi içerik alanını 320×568'de ~%2 azaltır; ACİL DURDUR kayan (zIndex 10000) → görünürlüğü değişmez; Adım 13 cihaz testinde seans sırasında E… | 0.5 |
| 9 | Statik kapı: tests/test_dokunma_hedefi_kapisi.py (sabit sayaç + mutasyon öz-testi) | `tests/test_dokunma_hedefi_kapisi.py (yeni)`, `tests/capraz.py (yalnız kullanılır)` | capraz.oku ile pf/src/**/*.tsx (`__tests__` hariç) taranır. (1) StyleSheet.create bloğu parantez-eşlemeli ayrıştırılır → `ad → gövde` sözlüğü; bir stil 'yeterli' sayılır eğer gövdesinde `minHeight: touch.`, `height: touch.`, `width: touch.`, `minHeight: Math.max(touch`, `minHeight: rs(N)` N≥52 (0.85×52=44), `minHeight… | `ilkel-7`, `ekranB-4`, `aihub-5`, `matris-8` | pytest tests/test_dokunma_hedefi_kapisi.py -v: öz-testler yeşil; taban ölçümünde sayaç sabitle eşit; kasıtlı mutasyon (AppShell iconBtn'den minHeight'ı sil) → KIRMIZI (memory kuralı). PEMF_CAPRAZ_KAY… | DÜŞÜK; yanlış pozitif = kırmızı CI. Strateji: belirsiz sayacı ayrı (kırmızı yapmaz, sadece sabit), muafiyet gerekçe zorunlu. Geri alma: dosyayı sil. | 3 |
| 10 | jest kilitleri: touch token 320'de, Chip/IconButton/Button tabanları | `pf/src/theme/__tests__/touch.test.ts (yeni)`, `pf/src/components/ui/__tests__/Chip.test.tsx (yeni)`, `pf/src/components/ui/__tests__/IconButton.test.tsx (yeni)`, `pf/src/components/ui/__tests__/Button.test.tsx` | Adım 1/2/3/4'te tarif edilen testlerin toplu yazımı. Ortak yardımcı `__tests__/olcek.ts`: `darTelefon()` = `jest.spyOn(Dimensions,'get').mockReturnValue({width:320,height:568,scale:2,fontScale:1})` + `jest.isolateModules(() => require('@/theme/tokens'))`. Button.test'e size_sm/md/lg için `minHeight ≥ 40/44/44` (320) v… | `ilkel-7` | `cd pf && npm test -- touch Chip IconButton Button` yeşil; mutasyon: tokens.ts'te `Math.max(44, rs(44))` → `rs(44)` yapınca touch.test KIRMIZI (kanıt). CI frontend.yml pf/** değişince koşar. | Yok. Geri alma: dosyaları sil. | 1.5 |
| 11 | Site (pemf-vet-web): min-h-11 sınıfları + @media (pointer: coarse) tabanı | `pemf-vet-web/src/index.css`, `pemf-vet-web/src/components/Footer.tsx`, `pemf-vet-web/src/context/AuthModal.tsx`, `pemf-vet-web/src/pages/Download.tsx` | index.css `@layer components` sonuna `.tap { display:inline-flex; align-items:center; min-height:44px }` ve `@media (pointer: coarse) { nav a, footer a, .pill-toggle button { min-height: 44px; padding-block: .625rem } }`. Footer.tsx:34/40 Link → `className="tap -my-1 hover:text-fg"` (dikey ritim: gap-2 → gap-1). AuthM… | `site-11` | vitest kaynak-kilidi (mevcut auth-modal-focus.test.ts deseni): Footer/AuthModal/Download'da `tap` sınıfı ve Pricing'de `py-2.5` regex ile; index.css'te `pointer: coarse` bloğu var. Tarayıcı: Chrome D… | DÜŞÜK (pazarlama sitesi, klinik akışı yok). Footer yüksekliği masaüstünde ~+40 px. Geri alma: revert + Vercel önceki deploy. | 1.5 |
| 12 | Launcher: @media (pointer: coarse) 44 px + 'Uygulamayı kaldır' ayrı satır | `launcher/app/ui/index.html`, `tests/test_launcher_ui_sozdizimi.py (yalnız koşulur)`, `tests/test_launcher_dokunma_hedefi.py (yeni, küçük)` | index.html `<style>` sonuna (mevcut @media max-width bloklarının, satır ~398, altına): `@media (pointer: coarse) { .seg button, .hbtn, .link, .mbtn, .chip { min-height: 44px; padding-inline: 14px; } .subactions { gap: 12px 28px; } .pw-toggle { min-width: 44px; min-height: 44px; } }`. Her cihazda: `.subactions .link.da… | `launcher-11` | pytest tests/test_launcher_ui_sozdizimi.py (script bloğu bozulmadı) + yeni test: `pointer: coarse` bloğunda `.link` ve `.seg button` selektörleri ve `min-height: 44px` var; `.link.danger` `flex-basis… | DÜŞÜK. Launcher self-update yolu (memory: launcher oto-güncelleme) CSS'ten bağımsız. Uninstall akışı onay modalı korunur. Geri alma: revert; index.html'e hered… | 1 |
| 13 | Cihaz doğrulama turu + sayaç sabitlerini 0'a indirme + docs kapanış notu | `tests/test_dokunma_hedefi_kapisi.py (sabitler)`, `docs/responsive-denetim-2026-09-04.md (S3 durum satırı)` | Tüm adımlar sonrası `IHLAL_TAVANI` hedefi 0 (muaf sayacı gerekçeli kalanlar); pf web export 320/390/768 CDP ölçümü ve APK'da fiziksel cihaz turu (cihaz_testi listesi). Raporun S3 bölümüne 'kapandı: tarih, kapı adı, muaf listesi' satırı. | `ilkel-7`, `aihub-5`, `ekranB-4`, `ekranC-5`, `matris-8`, `ilkel-3`, `ilkel-4`, `ilkel-5`, `kapsam-2`, `kapsam-3`, `kapsam-5`, `ampirik-4`, `ampirik-5`, `ekranA-10`, `ekranA-14`, `ekranB-15`, `ekranC-7`, `ekranC-8`, `site-11`, `launcher-11` | pytest tests -q (tam süit; memory: E-stop bekçi sızıntısı için tam-süit hata-yok testi hariç tutma kuralına uy) + `cd pf && npm run typecheck && npm test` + `cd pemf-vet-web && npm test && npm run bu… | Doğrulama adımı; kod riski yok. | 2.5 |

<details><summary>Kod taslakları</summary>

**1. tokens.ts'e ölçekle küçülmeyen `touch` token'ı**

```
// tokens.ts — rf()'nin altına
/** Dokunma hedefi tabanları: rs() ile ASLA küçülmez (320px'te rs(44)=38 idi), tablette büyür. */
export const touch = {
  min: Math.max(44, rs(44)),          // ikon/düğme/giriş/modal düğmesi
  sm: Math.max(40, rs(40)),           // çip, segment, tab
  slop: { top: 8, bottom: 8, left: 8, right: 8 } as const,
  /** Komşu hedefler binişmesin: hitSlop ≤ gap/2 (bobin seçici, çip satırı). */
  slopFor(gap: number) { const s = Math.max(0, Math.floor(gap / 2)); return { top: s, bottom: s, left: s, right: s }; },
  linkFont: Math.max(12, rf(11)),     // dokunulabilir küçük metin 12px altına inmesin
};
```

**2. Button, AppShell.iconBtn ve modal düğmelerinde rs(44/46/38) → touch.***

```
// Button.tsx
import { ..., touch } from "@/theme/tokens";
size_sm: { minHeight: touch.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
size_md: { minHeight: Math.max(touch.min, rs(46)), paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
size_lg: { minHeight: Math.max(touch.min, rs(54)), paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
```

**3. IconButton ilkeli + 9 ikon-only düğmenin göçü (X kapat, zil, bağlantı yenile, yenile, not düzenle)**

```
// components/ui/IconButton.tsx
import { Pressable, StyleSheet, type PressableProps, type StyleProp, type ViewStyle } from "react-native";
import { touch } from "@/theme/tokens";
interface Props extends Omit<PressableProps, "style"> { label: string; style?: StyleProp<ViewStyle>; children: React.ReactNode; }
/** İkon-only düğme: 44×44 taban (AppShell.iconBtn deseni) + hitSlop; a11y etiketi ZORUNLU. */
export function IconButton({ label, style, children, hitSlop = touch.slop, ...rest }: Props) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} hitSlop={hitSlop} style={[s.btn, style]} {...rest}>
      {children}
    </Pressable>
  );
}
const s = StyleSheet.create({ btn: { minWidth: touch.min, minHeight: touch.min, alignItems: "center", justifyContent: "center" } });

// PatientGate.tsx:90 örnek göç
<IconButton label="Kapat" onPress={() => setAcik(false)}><X color={colors.textMuted} size={rs(17)} /></IconButton>
```

**4. Chip + ChipRow ilkeli (görsel geçişli, 40 px taban, gap spacing.sm)**

```
export function Chip({ label, active, onPress, style, activeStyle, textStyle, activeTextStyle, accessibilityLabel, disabled, left }: ChipProps) {
  return (
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ selected: !!active, disabled: !!disabled }}
      accessibilityLabel={accessibilityLabel ?? label} disabled={disabled} onPress={onPress}
      hitSlop={touch.slopFor(spacing.sm)} style={[s.chip, style, active && s.active, active && activeStyle]}>
      {left}
      <Text style={[s.text, textStyle, active && s.textActive, active && activeTextStyle]} numberOfLines={1}>{label}</Text>
    </TouchableOpacity>
  );
}
export function ChipRow({ children, style }) { return <View style={[s.row, style]}>{children}</View>; }
const s = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { minHeight: touch.sm, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: radius.full,
          flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs,
          backgroundColor: "#1e293b", borderWidth: 1, borderColor: "#334155" },
  active: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6" },
  text: { color: colors.textMuted, fontSize: typography.caption, fontWeight: "600" },
  textActive: { color: colors.white, fontWeight: "700" },
});
```

**5. Çip dizilerinin Chip/ChipRow'a göçü (7 dosya, 11 çip stili)**

```
// ObservationNotesModal.tsx
const { isCompact } = useResponsive();
<ChipRow>
  {REACTIONS.map((r) => (
    <Chip key={r} label={r} active={selected.has(r)} onPress={() => toggle(r)}
      style={[styles.chip, isCompact && { flexBasis: "48%" }]} activeStyle={styles.chipActive}
      textStyle={styles.chipText} activeTextStyle={styles.chipTextActive} />
  ))}
</ChipRow>
// styles: chip'ten paddingVertical/paddingHorizontal/borderRadius SİLİNİR (Chip verir), renkler kalır.

// AiHubScreen.tsx xaiToggle
xaiToggle: { minHeight: touch.min, justifyContent: "center", marginBottom: spacing.xs },
```

**6. CoilSelector: 44 px kare + gap spacing.sm + hitSlop ≤ gap/2 + seçili durumda yalnız-renk-değil**

```
coilSelectorGrid: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
coilSelectorBtn: { width: touch.min, height: touch.min, borderRadius: 10, ... },
coilSelectorBtnActive: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6", borderWidth: 2 },
// JSX
hitSlop={touch.slopFor(spacing.sm)}   // kural: hitSlop ≤ gap/2 → komşu bobinle binişme yok
```

**7. Metin bağlantıları, segment/tab düğmeleri, giriş alanları: padding + touch tabanı**

```
// AuthScreen.tsx
forgotRow: { alignSelf: "flex-end", minHeight: touch.min, justifyContent: "center", paddingHorizontal: spacing.sm, marginTop: rs(-4) - spacing.sm },
forgotText: { color: colors.primary, fontSize: touch.linkFont, fontWeight: "700" },
tab: { flex: 1, minHeight: touch.sm, paddingVertical: spacing.sm, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
field: { ..., minHeight: touch.min },
// TreatmentHistoryScreen.tsx
<Button size="sm" variant="success" label="Kaydet" onPress={handleSaveNotes} />
<Button size="sm" variant="ghost" label="İptal" onPress={async () => {
  if (notes !== (session.patient_notes || "") && !(await platformConfirm("Değişiklikler silinsin mi?"))) return;
  setIsEditingNotes(false); setNotes(session.patient_notes || "");
}} />
```

**8. AppShell profileChip + wsContainer için dosya-içi düzeltme ve header yükseklik kontrolü**

```
profileChip: {
  flexDirection: "row", alignItems: "center", gap: rs(5), minHeight: touch.min,
  paddingVertical: spacing.xs, paddingHorizontal: spacing.sm,
  borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgAlt,
},
```

**9. Statik kapı: tests/test_dokunma_hedefi_kapisi.py (sabit sayaç + mutasyon öz-testi)**

```
_ETIKET = re.compile(r"<(?:TouchableOpacity|Pressable|AnimatedPressable)\b(.*?)>", re.S)
_YETERLI = re.compile(r"(?:minHeight|height|width|minWidth)\s*:\s*(?:touch\.|Math\.max\(\s*touch\.|rs\((5[2-9]|[6-9]\d|\d{3})\)|(4[4-9]|[5-9]\d|\d{3})\b)")
_MUAF = re.compile(r"//\s*dokunma-hedefi:\s*muaf\s*\((.+?)\)")

def _tara(kaynak: str) -> Tarama:  # saf: (ihlal, belirsiz, muaf) satır listeleri
    stiller = _stylesheet_ayikla(kaynak)  # ad -> gövde (parantez-eşlemeli)
    for m in _ETIKET.finditer(kaynak):
        props = m.group(1)
        if _muaf_yorumu(kaynak, m.start()): ...; continue
        if _hitslop_yeterli(props) or _YETERLI.search(_inline_style(props)): continue
        adlar = re.findall(r"styles?\.(\w+)", props)
        if any(_YETERLI.search(stiller.get(a, "")) or a == "iconBtn" for a in adlar): continue
        if "style={" in props and not adlar and "{{" not in props: belirsiz.append(...); continue
        ihlal.append((satir, ozet))

IHLAL_TAVANI = 0      # yayın öncesi hedef; taban ölçümünde ~45 ile başlar, her adımda düşürülür
def test_KRITIK_dokunma_hedefi_sayaci():
    t = _tara_agac()
    assert len(t.ihlal) == IHLAL_TAVANI, "\n".join(t.ihlal)  # düştüyse de sabiti güncelle (ratchet)

def test_kapi_kirmizi_yanabiliyor():  # mutasyon öz-testi
    assert len(_tara('<TouchableOpacity onPress={x}><X/></TouchableOpacity>').ihlal) == 1
```

**10. jest kilitleri: touch token 320'de, Chip/IconButton/Button tabanları**

```
// touch.test.ts
it("KRİTİK: 320px telefonda dokunma tabanı 44'ün altına İNMEZ", () => {
  jest.spyOn(Dimensions, "get").mockReturnValue({ width: 320, height: 568, scale: 2, fontScale: 1 } as any);
  jest.isolateModules(() => {
    const { touch, rs } = require("@/theme/tokens");
    expect(rs(44)).toBe(38);        // ölçek gerçekten küçültüyor → taban ANLAMLI
    expect(touch.min).toBe(44);
    expect(touch.sm).toBe(40);
    expect(touch.slopFor(7)).toEqual({ top: 3, bottom: 3, left: 3, right: 3 });
  });
});
```

**11. Site (pemf-vet-web): min-h-11 sınıfları + @media (pointer: coarse) tabanı**

```
/* index.css */
@layer components {
  .tap { display: inline-flex; align-items: center; min-height: 44px; }
}
@media (pointer: coarse) {
  nav a, footer a, .pill-toggle button { min-height: 44px; padding-block: 0.625rem; }
}
```

**12. Launcher: @media (pointer: coarse) 44 px + 'Uygulamayı kaldır' ayrı satır**

```
@media (pointer: coarse) {
  .seg button, .hbtn, .link, .mbtn, .chip { min-height: 44px; padding-inline: 14px; }
  .subactions { gap: 12px 28px; }
  .pw-toggle { min-width: 44px; min-height: 44px; }
}
.subactions .link.danger { flex-basis: 100%; justify-content: center; margin-top: 4px; }
```

</details>

**Bağımlılıklar:** Adım 1 (touch token) → 2,3,4,5,6,7,8,10 hepsinin ön koşulu.; Adım 4 (Chip) → 5. Adım 3 (IconButton) → 5'in AiProPanel/TreatmentHistory parçalarından bağımsız ama aynı dosyalara dokunur; 3 önce, 5 sonra (rebase kolaylığı).; Adım 9 kapısı adım 2'den ÖNCE bir kez koşturulup taban sayılmalı (sabit = mevcut ihlal sayısı), sonra her adımda düşürülür; aksi halde 'kapı boş çalışır' tuzağı (memory: Kapı Ortam Varsayımı).; S1 kökü (SCALE tavanı) ile çakışma: touch.min `Math.max(44, rs(44))` S1 tavan değişse de geçerli; S1 planı rs() semantiğini değiştirirse adım 10 touch.test yeniden koşulmalı.; S6 kökü (maxFontSizeMultiplier) ekranC-7 etiket kırpılmasının yazı-ölçeği parçasını genel çözer; buradaki `maxFontSizeMultiplier={1.2}` tek satır o gelince kaldırılabilir.; Site Vercel production=production-hardening dalı (memory: Tek Depo) — adım 11 PR o dala.; Launcher değişikliği yayın için launcher runbook'unu (memory: Launcher Yayın Runbook, iki ad) izler; bu plan yalnız kaynak değişikliğini kapsar.; Backend + APK build paralel koşmaz (memory: Yayın 2026-08-27) — adım 13 cihaz turu için APK build'i tek başına.

**Kilitler:**
- tests/test_dokunma_hedefi_kapisi.py — SABİT SAYAÇ (ihlal/belirsiz/muaf) + mutasyon öz-testi; yeni Pressable/TouchableOpacity 44 altı hedefle giremez.
- pf/src/theme/__tests__/touch.test.ts — 320 px'te touch.min===44 (rs(44)===38 kanıtıyla); tokens'ta Math.max kaldırılırsa kırmızı.
- pf/src/components/ui/__tests__/Chip.test.tsx, IconButton.test.tsx, Button.test.tsx (boyut satırları) — primitif tabanları.
- pf/src/screens/__tests__/coilSelectorHitSlop.test.tsx — hitSlop ≤ gap/2 kuralı bobin seçicide.
- pemf-vet-web vitest dokunma-hedefi.test.ts — `tap` sınıfı + pointer:coarse bloğu kaynak kilidi.
- tests/test_launcher_dokunma_hedefi.py — pointer:coarse bloğu + danger ayrı satır; test_launcher_ui_sozdizimi.py mevcut JS ayrıştırma kapısı.
- Mevcut a11y-etiket testleri (PatientGate/AiSpecApprovalModal/MobileUpdateBanner/SurumFarkiBanner/AppShell.logout) göçte etiketlerin korunduğunu kilitler.

**Cihaz testi:**
- 320×568 Android (küçük telefon, yazı ölçeği 1.0 ve 1.3) APK: Kontrol → 8 bobin seçici, her bobine 10 dokunuş → 10/10 doğru; aralığa dokunuş seçmez; seans başlat → ACİL DURDUR görünür ve ilk dokunuşta durdurur (header büyümesi E-stop'u örtmüyor).
- 360×800 Android + 390×844 iOS: AppShell üst bar zil / bağlantı yenile / profil / ayarlar — her biri ilk dokunuşta açılır, komşuya kaçmaz; PatientGate X; MobileUpdateBanner X (Güncelle'ye kaçmadan 5/5 kapanır — 128 MB indirme başlamaz).
- Seans Gözlem Notu modalı (320 ve 768): 6 tepki çipi eldivenli parmakla 5/5 doğru; kaydedilen not backend'de doğru tepkiyle (tıbbi kayıt).
- AI Pro: hazırlık sırasında 'Vazgeç' ilk dokunuşta iptal eder; organ çipleri doğru seçilir. AI Hub: ısı haritası anahtarına dokunuş analizi BAŞLATMAZ; CKD Evet/Hayır 10 satırda komşu satıra kayma yok; 'Eklenti' rozeti akordeonu açmaz.
- Giriş kapısı (web export + APK, 320): 'Şifremi unuttum?' ve 'Kayıt ol' ilk dokunuşta; Kayıt formu 12 alan ≥ 44 px; placeholder 'Ünvan — opsiyonel' tam görünür.
- Seans Geçmişi: not düzenle ikonu → Kaydet/İptal Button'ları; İptal not değiştiyse önce sorar. Hastalar segment 320 + yazı ölçeği 1.15'te sayaç görünür.
- Tablet 768×1024 (yatay ve dikey): touch.min = rs(44)=57 px büyüme kabul edilebilir, Sensörler eksen/bobin çipleri tek satırda taşmıyor.
- Surface/dokunmatik Windows (%200 DPI) launcher: TR/EN seçici, alt bağlantılar ≥ 44 px; 'Uygulamayı kaldır' ayrı satırda; fare ile ölçüler eskisi gibi. Site: telefonda Footer yasal bağlantıları ve fiyat Aylık/Yıllık anahtarı ilk dokunuşta.

**Açık sorular (sahip kararı):**
- `ekranA-12` ve `ampirik-7` rapor metninde S3'e bağlı görünüyor ama bulgular JSON dizisinde bu id'ler YOK (121 kayıt tarandı, S3 kök=18 kayıt). Kanonik id'leri farklı mı, yoksa raporda hayalet mi? Plan bunları kapsamıyor.
- AppShell header yüksekliğinin telefonda ~+10 px büyümesi kabul mü, yoksa zil/ws/profil için 'görsel küçük, dokunma kutusu 44' (hitSlop-ağırlıklı) mı tercih edilir? Plan görünür kutu 44 (Material) varsayıyor; alternatif header'ı büyütmez ama web'de (RNW) hitSlop güvenilmez.
- Segment/tab için touch.sm (40) tabanı yeterli mi (ikinci doğrulama 'düşük' dedi), yoksa sahip 44 istiyor mu?
- TreatmentHistory 'İptal'e onay diyaloğu eklemek (not değiştiyse) davranış değişikliğidir — sahip onayı gerekir mi? Eklenmezse ekranC-5 yalnız hedef boyutuyla kapanır.
- Statik kapı hangi CI hattında koşsun: tests.yml (backend, capraz.py deseni — pf/** değişince de yol filtresi yüzünden tetiklenmeyebilir) mi, frontend.yml'ye ek `pytest tests/test_dokunma_hedefi_kapisi.py` adımı mı? Öneri: ikisi de (frontend.yml'ye tek satır).
- GlobalEmergencyStop.btn `minHeight: rs(52)` 0.85'te tam 44 — `Math.max(touch.min, rs(52))` ile pinlensin mi? Sahip kararı: hasta güvenliği bileşenine dokunmadan bırakıldı; tek satırlık taban eklemesi zararsız ama plan dışında tutuldu.

**Toplam efor:** ~22.75 saat

### S4 — Klavye (8 bulgu: 0 yüksek / 5 orta / 3 düşük)

Bağlı bulgular: `kabuk-7`, `ekranA-6`, `ekranA-7`, `ekranA-16`, `ekranB-9`, `ekranC-13`, `aihub-6`, `ilkel-11`

**Hedef:** Klavye açıkken (iOS + Android 11+ edge-to-edge + yatay telefon) her giriş alanı ve onun Kaydet/Başlat/Bağlan düğmesi görünür ve İLK dokunuşta çalışır; ACİL DURDUR klavye açıkken de erişilebilir kalır; kabuk içindeki 8 ekranın gereksiz iç dikey ScrollView'ları kaldırılır (tek kaydırıcı = AppShell, 'handled'); alt-sayfa/ortalı modallar (gözlem notu, yedek parolası, operatör PIN) klavye ve kısa yükseklikte kaydırılabilir + düğmeleri sabit. Kapatılan bulgular: kabuk-7 (+ekranC-11, matris-7 tekrar), ekranA-7, aihub-6, ilkel-11, ekranB-9 (+ilkel-19 tekrar), ekranA-6, ekranA-16, ekranC-13. ampirik-10 bulgu değil → cihaz testi adımında ölçülür.

**Tasarım kararları:**
- YENİ NATİVE BAĞIMLILIK YOK (react-native-keyboard-controller / react-native-edge-to-edge eklenmez): RN 0.85 KeyboardAvoidingView Android'de keyboardDidShow olayıyla çalışır (KeyboardAvoidingView.js:210-213) ve edge-to-edge'de doğru screenY alır; native modül eklemek EAS iOS + APK yeniden derleme ve launcher paket sürüm zinciri demek. Kabuk KAV + küçük useKeyboard hook'u yeterli.
- İKİ FARKLI KAV DAVRANIŞI, TEK KAYNAK (hooks/useKeyboard.ts): KAV_BEHAVIOR_PENCERE = iOS veya Android API≥30 → 'padding' (aktivite penceresi daralmaz); KAV_BEHAVIOR_MODAL = yalnız iOS 'padding' (RN Modal Android'de kendi penceresini adjustResize ile daraltır; padding eklemek ÇİFT boşluk yapar). Bu ayrım kodda yorumla gerekçelendirilir.
- KAV, AppShell'de styles.main View'inin YERİNE geçer (root'un doğrudan çocuğu): RN KAV frame'i onLayout ile EBEVEYNE göre ölçer (KeyboardAvoidingView.js:124-127, 110); root pencere kökü olduğundan frame.y=insets.top, alt kenar=pencere altı → keyboardVerticalOffset=0 DOĞRU. Bulgudaki 'keyboardVerticalOffset=insets.top' önerisi burada ÇİFT sayım olurdu; yalnız KAV main'in İÇİNE konursa gerekir.
- HASTA GÜVENLİĞİ — ACİL DURDUR klavye açıkken GİZLENMEZ, klavyenin ÜSTÜNE taşınır: bottomOffset = klavye yüksekliği (iOS'ta endCoordinates.height home-indicator alanını içerir → insets.bottom düşülür; Android'de RN ime−systemBars verir → olduğu gibi). Pressable ScrollView dışında olduğundan dokunuş klavye kapatmadan doğrudan performEmergencyStop'a gider. Buton içeriğin alt ~64px'ini örter ama içerik kaydırılabilir (content paddingBottom rs(160) korunur).
- Alt navigasyon klavye açıkken (yalnız !desktop && native) unmount edilir: edge-to-edge'de zaten klavye altında kalıyor, Android ≤10 legacy resize'da klavyenin üstüne binip 64px çalıyordu; gizlemek her iki durumda tutarlı. Web'de Keyboard olayı hiç gelmez → hiç gizlenmez (masaüstü/LAN etkilenmez).
- İç dikey ScrollView'lar SİLİNİR, FlatList'e geçilmez: hiçbir ekranda RefreshControl / stickyHeaderIndices / FlatList / scrollTo / onScroll yok (grep doğrulandı); AiHistory'nin iki YATAY çip ScrollView'ı ve PatientGate/OperatorSwitcher'ın nestedScrollEnabled listeleri kalır. Sticky filtre (ekranC-13 madde 3) ayrı iyileştirme kalemi olarak açık soruya yazıldı.
- Alt padding TEK yerde (AppShell content rs(160)+insets.bottom / rs(84)): ekranların kendi paddingBottom xl/xxl değerleri kaldırılır → sayfa sonu boşluğu ~190-210px'ten ~150px'e iner (ekranA-16, ekranC-13 madde 1).
- NotificationCenter compact kipinde ScrollView YOK (düz View) + Dashboard maxVisible 4: Android'de nestedScrollEnabled'sız iç liste hiç kaydırılamıyordu, iOS'ta sayfayı takıyordu; tam liste zaten üst-bar zili (AppShell:472, maxVisible 20) ile ulaşılabilir. Modal'daki tam kipe nestedScrollEnabled eklenir.
- app.json'a android.softwareKeyboardLayoutMode:'resize' YALNIZ prebuild tutarlılığı için yazılır; android/ git'te olduğundan üretim davranışını değiştirmez ve edge-to-edge'de tek başına YETMEZ — asıl çözüm KAV. 'pan' seçilmez: tüm pencereyi (header + ACİL DURDUR dahil) yukarı iter.
- Doğrulama üç katman: (1) jest davranış testleri (Keyboard olayını sahte-yayınlayıp alt bar/ACİL DURDUR ofsetini ÖLÇ), (2) python statik kapı (kabuk içi ekranlarda dikey ScrollView yasağı + modallarda keyboardShouldPersistTaps) — kapıya mutasyon koşturup KIRMIZI olduğu kanıtlanır, (3) gerçek cihaz turu (Android 15 APK + iOS EAS) çünkü klavye yerleşimi headless'ta ölçülemez (ampirik-10).

| # | Adım | Dosyalar | Değişiklik | Kapattığı | Doğrulama | Risk | Efor (s) |
|---|---|---|---|---|---|---|---|
| 1 | useKeyboard hook'u + KAV davranış sabitleri (altyapı, tek kaynak) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\hooks\useKeyboard.ts (YENİ)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\hooks\__tests__\useKeyboard.test.ts (YENİ)` | Yeni hook `useKeyboard()` → `{ acik, yukseklik }`: iOS'ta keyboardWillShow/WillHide, Android'de keyboardDidShow/DidHide dinler (RN KAV ile aynı seçim, KeyboardAvoidingView.js:200-213); web'de hiç abone olmaz (RNW Keyboard.addListener no-op, her zaman kapalı). Aynı dosyadan iki sabit: `KAV_BEHAVIOR_PENCERE` (iOS || And… | `kabuk-7`, `ekranA-6` | jest `useKeyboard.test.ts` (renderHook, @testing-library/react-native 13): `jest.spyOn(Keyboard,'addListener')` ile geri çağrıları yakala; keyboardDidShow({endCoordinates:{height:300}}) → acik=true,y… | Düşük. Yeni dosya, mevcut davranışı değiştirmez. Geri alma: dosyayı sil (henüz tüketici yok). | 1.5 |
| 2 | AppShell: main → KeyboardAvoidingView, klavye açıkken alt bar gizle, ACİL DURDUR klavye üstüne | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\AppShell.tsx (satır 4 import, 245 main View, 385-394 ScrollView değişmez, 399 GlobalEmergencyStop, 401-422 bottomNav)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\AppShell.klavye.test.tsx (YENİ)` | (a) `<View style={styles.main} {...panHandlers}>` → `<KeyboardAvoidingView style={styles.main} behavior={KAV_BEHAVIOR_PENCERE} enabled={responsive.isNative} {...panHandlers}>` (KAV kalan prop'ları View'a geçirir → swipe PanResponder aynen çalışır; root'un doğrudan çocuğu olduğundan keyboardVerticalOffset=0). İçindeki … | `kabuk-7`, `ekranC-11`, `matris-7`, `ekranA-7`, `aihub-6`, `ekranB-9` | jest `AppShell.klavye.test.tsx` (AppShell.logout.test.tsx mock seti kopyalanır; GlobalEmergencyStop mock'u `({bottomOffset}) => <Text testID="estop-offset">{String(bottomOffset)}</Text>`; mockDesktop… | ORTA — HASTA GÜVENLİĞİ: ACİL DURDUR ofset hesabı yanlışsa buton klavye altında/üstünde kısmen gizlenir; mevcut durumdan (tamamen klavye altında) daha kötü olam… | 2.5 |
| 3 | Kabuk içi 8 ekranda iç dikey ScrollView → View; alt padding tekilleştirme; NotificationCenter compact düz liste | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\SettingsScreen.tsx (428, 868; styles.container 883-887)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\AiHubScreen.tsx (291/352 ve 509/617; styles.content 3642)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\DashboardScreen.tsx (36, 146, 152; styles.container 158-165)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\NotificationCenter.tsx (68-74; styles.list/listCompact 149-150)` | Her ekranda `<ScrollView contentContainerStyle={X} showsVerticalScrollIndicator={false}>` → `<View style={X}>` (kapanış etiketi de), kullanılmayan `ScrollView` import'u kaldırılır (AiHistory'de kalır: yatay çipler). AppShell'in ScrollView'ı zaten `keyboardShouldPersistTaps='handled'` → klavye açıkken 'Cihaza Bağlan' /… | `ekranA-7`, `aihub-6`, `ekranA-16`, `ekranC-13` | (1) Python kapısı `tests/test_kabuk_ic_scrollview_kapisi.py` (tests/test_destek_adresi_tek_kaynak.py deseni): SABİT ekran listesi (8 ad) için `<ScrollView(?![^>]*\bhorizontal\b)[^>]*>` eşleşmesi 0 ol… | Düşük-orta. Davranış: iç ScrollView'lar hiçbir platformda kendi kaydırmasını üretmiyordu (yükseklik sınırı yok), yani görsel sonuç aynı; tek fark AiHub/Patient… | 3 |
| 4 | ObservationNotesModal: iOS KAV + Atla/Kaydet satırı ScrollView DIŞINA (sheet altına sabit) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\ObservationNotesModal.tsx (110-160; styles 167-177, 204)` | `<View style={styles.backdrop}>` → `<KeyboardAvoidingView style={styles.backdrop} behavior={KAV_BEHAVIOR_MODAL}>` (Android'de Modal penceresi zaten adjustResize ile daralır → undefined; iOS 'padding'). btnRow (147-158) ScrollView'ın DIŞINA, card'ın son çocuğu olarak taşınır: `style={[styles.btnRow, { paddingHorizontal… | `ekranB-9`, `ilkel-19` | jest: mevcut `gozlemNotuKorunmasi.test.tsx` (getByLabelText('Gözlem notları'), getByText('💾 Kaydet'), 'Uyudu' çipleri) DEĞİŞMEDEN yeşil — düğmeler artık ScrollView dışında ama aynı ağaçta. Yeni asser… | Düşük. Modal, bobin running raporlayınca gizlenme davranışı (kasıtlı) ve sıfırlama effect'i değişmiyor. Yatay Android'de sheet ≈160px: başlık+çipler ScrollView… | 1 |
| 5 | BackupPassphraseDialog + OperatorSwitcher: iOS KAV, kart maxHeight %92, içerik ScrollView, liste yüksekliği ekran yüksekliğine göre | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\BackupPassphraseDialog.tsx (52-54 perde/Card, 106-108 stiller)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\OperatorSwitcher.tsx (96-98 perde/Card, 119 liste, 201-206 stiller)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\__tests__\BackupPassphraseDialog.test.tsx (ek assert)` | Her iki diyalogda `<View style={styles.perde}>` → `<KeyboardAvoidingView style={styles.perde} behavior={KAV_BEHAVIOR_MODAL}>`; `kart` stiline `maxHeight: '92%'` eklenir, `gap: spacing.sm` karttan çıkıp ScrollView contentContainerStyle'a taşınır; Card'ın çocukları `<ScrollView keyboardShouldPersistTaps="handled" showsV… | `ilkel-11` | jest: mevcut BackupPassphraseDialog.test.tsx (getByLabelText('Yedek parolası'/'Yedek parolası tekrar'/'Yedeği oluştur') + press akışları) DEĞİŞMEDEN yeşil; ek test: `UNSAFE_getByType(ScrollView).prop… | Düşük. PIN/parola mantığı, MIN_PAROLA politikası, operatör geçişi değişmiyor. Card içine ScrollView: Card yüksekliği içerik kadar, %92'de kırpılır (Yoga: sabit… | 1.5 |
| 6 | AuthScreen: Android edge-to-edge'de de KAV 'padding' (tek kaynak sabit) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\AuthScreen.tsx (10 import, 179)` | `behavior={Platform.OS === "ios" ? "padding" : undefined}` → `behavior={KAV_BEHAVIOR_PENCERE}`; kısa yorum: 'Android ≥11 edge-to-edge (gradle.properties edgeToEdgeEnabled=true) aktivite penceresini klavyeyle DARALTMAZ; manifest adjustResize yetmez.' AuthScreen root View pencere kökü ve KAV onun doğrudan çocuğu (styles… | `ekranA-6` | jest: Platform.OS='android', Platform.Version=34 mock'u ile AuthScreen render → `UNSAFE_getByType(KeyboardAvoidingView).props.behavior==='padding'`; Version=28 → undefined. Mevcut Auth testleri (vars… | Düşük. Android ≤10'da (legacy resize) geçici çift boşluk, onLayout ile düzelir; Expo 56 varsayılan minSdk 24 ama saha cihazları Android 12+. Geri alma: tek sat… | 0.5 |
| 7 | app.json: android.softwareKeyboardLayoutMode='resize' (prebuild tutarlılığı, belgeleme) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\app.json (expo.android bloğu)` | `"android": { ..., "softwareKeyboardLayoutMode": "resize" }` eklenir. NOT (commit mesajına): android/ dizini git'te ve AndroidManifest.xml:26 zaten adjustResize → üretim davranışı DEĞİŞMEZ; yalnız ileride `expo prebuild --clean` koşulursa manifest aynı kalsın diye. Edge-to-edge'de resize tek başına yetmez; asıl çözüm … | `kabuk-7`, `ilkel-11` | `python -c "import json;print(json.load(open('pf/app.json'))['expo']['android']['softwareKeyboardLayoutMode'])"` → resize; `grep -n windowSoftInputMode pf/android/app/src/main/AndroidManifest.xml` hâ… | Yok. Geri alma: satırı sil. | 0.25 |
| 8 | Cihaz doğrulama turu (Android 15 APK + iOS EAS) — ampirik-10 kapanışı, HASTA GÜVENLİĞİ kapısı | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf (APK: scripts\build_apk.ps1; iOS: EAS bulut)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\docs\responsive-denetim-2026-09-04.md (S4 satırına ölçüm notu + ekran görüntüsü adları)` | Backend PEMF_SIMULATE=1 ile (stm32_simulator) bobin çalıştırılıp klavye açıkken ACİL DURDUR erişimi ve tüm S4 senaryoları gerçek cihazda ölçülür; ekran görüntüleri docs/ altına (pf_klavye_*.png) alınır; rapordaki 'olasi' kesinlikler 'kesin/ölçüldü' olarak güncellenir. Yayın ancak C4 (ACİL DURDUR) geçince. | `kabuk-7`, `ekranA-6`, `ekranA-7`, `aihub-6`, `ilkel-11`, `ekranB-9` | cihaz_testi listesindeki C1-C9 senaryoları; her biri için 'giriş görünür mü / düğme ilk dokunuşta çalıştı mı / ACİL DURDUR görünür ve durdurdu mu' üçlüsü kayıt altına alınır. Başarısız senaryo → ilgi… | iOS EAS derlemesi kotasız/gecikmeli olabilir → Android APK + iOS Simulator (Expo Go değil, dev-client) ile ön ölçüm; iOS gerçek cihaz ölçümü yayın notuna 'bekl… | 3 |

<details><summary>Kod taslakları</summary>

**1. useKeyboard hook'u + KAV davranış sabitleri (altyapı, tek kaynak)**

```
// pf/src/hooks/useKeyboard.ts
import { useEffect, useState } from "react";
import { Keyboard, Platform, type KeyboardEvent } from "react-native";
/** AKTİVİTE penceresi (AppShell, AuthScreen): iOS her zaman; Android edge-to-edge (API>=30) adjustResize'ı YOK SAYAR → padding. */
export const KAV_BEHAVIOR_PENCERE =
  Platform.OS === "ios" || (Platform.OS === "android" && Number(Platform.Version) >= 30) ? "padding" : undefined;
/** RN Modal kendi penceresinde ADJUST_RESIZE + edge-to-edge KAPALI (ReactModalHostView.kt:329,391) → Android kendisi daralır; yalnız iOS. */
export const KAV_BEHAVIOR_MODAL = Platform.OS === "ios" ? "padding" : undefined;
export function useKeyboard(): { acik: boolean; yukseklik: number } {
  const [kb, setKb] = useState({ acik: false, yukseklik: 0 });
  useEffect(() => {
    if (Platform.OS === "web") return;
    const goster = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    const gizle = Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide";
    const s1 = Keyboard.addListener(goster, (e: KeyboardEvent) => setKb({ acik: true, yukseklik: e.endCoordinates?.height ?? 0 }));
    const s2 = Keyboard.addListener(gizle, () => setKb({ acik: false, yukseklik: 0 }));
    return () => { s1.remove(); s2.remove(); };
  }, []);
  return kb;
}
```

**2. AppShell: main → KeyboardAvoidingView, klavye açıkken alt bar gizle, ACİL DURDUR klavye üstüne**

```
import { KeyboardAvoidingView, Platform, ... } from "react-native";
import { useKeyboard, KAV_BEHAVIOR_PENCERE } from "@/hooks/useKeyboard";
...
const kb = useKeyboard();
const klavyeAcik = !desktop && kb.acik;
// iOS yüksekliği home-indicator alanını içerir; Android (ReactRootView) ime−systemBars verir.
const klavyeKaldirma = Platform.OS === "ios" ? Math.max(kb.yukseklik - insets.bottom, 0) : kb.yukseklik;
...
<KeyboardAvoidingView style={styles.main} behavior={KAV_BEHAVIOR_PENCERE} enabled={responsive.isNative}
  {...(!desktop ? panResponder.panHandlers : {})}>
  {/* header, bantlar, content ScrollView — DEĞİŞMEZ */}
</KeyboardAvoidingView>
{/* HASTA GÜVENLİĞİ: klavye açıkken de erişilebilir — klavyenin ÜSTÜNE taşınır, ASLA gizlenmez */}
<GlobalEmergencyStop bottomOffset={desktop ? 0 : klavyeAcik ? klavyeKaldirma : rs(76)} />
{!desktop && !klavyeAcik ? (<View style={[styles.bottomNav, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>…</View>) : null}
```

**3. Kabuk içi 8 ekranda iç dikey ScrollView → View; alt padding tekilleştirme; NotificationCenter compact düz liste**

```
// SettingsScreen.tsx:428  (aynı kalıp 7 ekranda)
-    <ScrollView contentContainerStyle={styles.container}>
+    <View style={styles.container}>
 ...
-    </ScrollView>
+    </View>
// styles.container: paddingBottom: spacing.xxl  → SİL (AppShell rs(160)+insets.bottom tek kaynak)

// NotificationCenter.tsx:68
-  <ScrollView style={compact ? styles.listCompact : styles.list} showsVerticalScrollIndicator={false}>
+  {compact ? (
+    <View>{items}</View>                       // Dashboard: dış ScrollView kaydırır; iç liste YOK
+  ) : (
+    <ScrollView style={styles.list} nestedScrollEnabled showsVerticalScrollIndicator={false}>{items}</ScrollView>
+  )}
// DashboardScreen.tsx:146  <NotificationCenter maxVisible={4} compact />

# tests/test_kabuk_ic_scrollview_kapisi.py (öz)
_EKRANLAR = ("DashboardScreen","SettingsScreen","PatientScreen","AiHistoryScreen","KpiDashboardScreen","TreatmentHistoryScreen","SensorMonitorScreen","AiHubScreen")
_DIKEY_SV = re.compile(r"<ScrollView(?![^>]*\bhorizontal\b)[^>]*>", re.S)
def test_kabuk_icinde_dikey_scrollview_yok():
    for ad in _EKRANLAR:
        kaynak = (_KOK / "pf/src/screens" / f"{ad}.tsx").read_text(encoding="utf-8")
        assert not _DIKEY_SV.search(kaynak), f"{ad}: AppShell zaten kaydırıyor ('handled'); iç dikey ScrollView klavye açıkken ilk dokunuşu yutar (S4)"
```

**4. ObservationNotesModal: iOS KAV + Atla/Kaydet satırı ScrollView DIŞINA (sheet altına sabit)**

```
import { KeyboardAvoidingView, ... } from "react-native";
import { KAV_BEHAVIOR_MODAL } from "@/hooks/useKeyboard";
<Modal visible={visible} transparent animationType="slide" onRequestClose={skip}>
  <KeyboardAvoidingView style={styles.backdrop} behavior={KAV_BEHAVIOR_MODAL}>
    <View style={styles.card}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.md, gap: spacing.md }}
        keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        {/* başlık, hasta, tepki çipleri, Notlar TextInput — DEĞİŞMEZ */}
      </ScrollView>
      {/* Düğmeler ScrollView DIŞINDA: klavye açıkken de Atla/Kaydet görünür ve tek dokunuşla çalışır */}
      <View style={[styles.btnRow, { paddingHorizontal: spacing.lg, paddingBottom: insets.bottom + spacing.lg }]}>
        …Atla / 💾 Kaydet (aynı TouchableOpacity'ler)…
      </View>
    </View>
  </KeyboardAvoidingView>
</Modal>
```

**5. BackupPassphraseDialog + OperatorSwitcher: iOS KAV, kart maxHeight %92, içerik ScrollView, liste yüksekliği ekran yüksekliğine göre**

```
// BackupPassphraseDialog.tsx (OperatorSwitcher aynı kalıp)
<Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
  <KeyboardAvoidingView style={styles.perde} behavior={KAV_BEHAVIOR_MODAL}>
    <Card style={styles.kart}>
      <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}
        contentContainerStyle={{ gap: spacing.sm }}>
        {/* başlık, not, girişler, hata, satirBtn — DEĞİŞMEZ */}
      </ScrollView>
    </Card>
  </KeyboardAvoidingView>
</Modal>
// styles: kart: { width: "100%", maxWidth: rs(440), maxHeight: "92%" }   // gap ScrollView'a taşındı

// OperatorSwitcher.tsx
const { height } = useResponsive();
<ScrollView style={[styles.liste, { maxHeight: height < 520 ? rs(110) : rs(200) }]} nestedScrollEnabled>
```

**6. AuthScreen: Android edge-to-edge'de de KAV 'padding' (tek kaynak sabit)**

```
import { KAV_BEHAVIOR_PENCERE } from "@/hooks/useKeyboard";
-<KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.flex}>
+{/* Android >=11 edge-to-edge: aktivite penceresi klavyeyle daralmaz (adjustResize yok sayılır) → padding ŞART */}
+<KeyboardAvoidingView behavior={KAV_BEHAVIOR_PENCERE} style={styles.flex}>
```

**7. app.json: android.softwareKeyboardLayoutMode='resize' (prebuild tutarlılığı, belgeleme)**

```
"android": {
  "package": "com.pemf.vet",
  ...
  "softwareKeyboardLayoutMode": "resize"
}
```

</details>

**Bağımlılıklar:** Adım 2, 4, 5, 6 → Adım 1'e bağlı (useKeyboard + KAV_BEHAVIOR_* sabitleri).; Adım 3'ün klavye faydası (ilk dokunuşta düğme) Adım 2'den bağımsız; ancak 'iç ScrollView → View' Adım 2'deki KAV ile birlikte test edilmeli (KAV padding + tek ScrollView).; Adım 8 tüm adımlardan sonra; APK build (scripts/build_apk.ps1, C:\pb kısa dizin) + iOS EAS bulut derlemesi gerekir; backend build ile paralel koşmaz.; Sürüm: react-native 0.85.3 (KAV Android keyboardDidShow ile çalışır, ReactRootView IME inset'ten yükseklik verir), expo 56.0.11, react-native-safe-area-context 5.7.0, @testing-library/react-native 13.3 (renderHook), jest-expo 56. Yeni npm bağımlılığı YOK.; Python kapısı için embedded python: `PYTHONIOENCODING=utf-8 C:\...\python.exe -m pytest tests/test_kabuk_ic_scrollview_kapisi.py`; jest: `cd pf && npx jest` (tam süit).

**Kilitler:**
- HASTA GÜVENLİĞİ: GlobalEmergencyStop hiçbir klavye/yerleşim durumunda null'a düşürülmez; yalnız bottomOffset değişir (klavye üstü). Testte ölçülür (Adım 2).
- AppShell content ScrollView'ının `keyboardShouldPersistTaps='handled'` ve `paddingBottom: rs(160)+insets.bottom` değerleri KORUNUR (kayan ACİL DURDUR son satırı örtmesin — önceki denetim kararı).
- ControlScreen ve seans akışı (SessionProgressCard, CoilParameterPanel, useSessionControl) DOKUNULMAZ; ObservationNotesModal'ın bobin running iken gizlenme + sıfırlamama sözleşmesi (gozlemNotuKorunmasi.test) değişmez.
- Alt bar yalnız `!desktop && klavye açık && native` iken gizlenir; masaüstü/web/tablet yerleşimi ve swipe-gezinme (PanResponder, primaryItems) aynen kalır (AppShell.logout.test yeşil).
- Yeni native modül eklenmez (EAS/APK sürüm zinciri, launcher katmanlı paket etkilenmez).
- app.json değişikliği manifestteki adjustResize'ı değiştirmez; 'pan' kipine GEÇİLMEZ.
- Bulgu 'keyboardVerticalOffset=insets.top' önerisi UYGULANMAZ (KAV root'un doğrudan çocuğu → çift sayım olur); KAV main'in içine alınırsa o zaman gerekir — yorumla belgelenir.

**Cihaz testi:**
- C1 Android 15 APK dikey (390×844): Ayarlar → 'Manuel Sunucu Adresi' alanına odaklan → alan klavye üstünde görünür; 'Bağlantıyı Test Et' İLK dokunuşta çalışır (toast/sonuç), alt bar gizli.
- C2 Android 15 + iOS dikey: Hastalar → yeni hasta formu → en alt alan (ör. notlar/kilo) odaklı iken alan ve 'Kaydet' görünür; kaydırarak üst alanlara dönülebilir.
- C3 Android 15 + iOS: Akıllı Teşhis → CKD formu 14 alan → 'Kırmızı küre' odaklı iken görünür; klavye açıkken CKD Evet/Hayır çipi ve 'CKD Analizini Başlat' ilk dokunuşta tepki verir.
- C4 HASTA GÜVENLİĞİ (PEMF_SIMULATE=1, bobin 1-2 running): Kontrol → Manuel → 'Süre (dk)' odaklı, klavye AÇIK → ACİL DURDUR klavyenin hemen üstünde görünür; tek dokunuşta 'Tüm bobinler durduruldu ✓' ve simülatörde running=0. Her iki platformda + yatay 640×360.
- C5 Ana Ekran (telefon): bildirim listesi (≥6 bildirim) üzerinde dikey sürükleme SAYFAYI kaydırır (iç liste yok); sayfa sonu boşluğu ~150px (önce ~200).
- C6 Seans sonu Gözlem Notu: iOS dikey + Android yatay (640×360) → 'Notlar' odaklı iken yazı görünür, 'Atla / 💾 Kaydet' klavye üstünde sabit ve tek dokunuşla çalışır.
- C7 Yatay telefon (640×360) + Android font ölçeği 1.3: Ayarlar → Yedek oluştur → parola alanı odaklı → 'Yedeği Oluştur' kaydırarak erişilir; Üst bar → Kullanıcı Değiştir → PIN odaklı → 'Geçiş Yap' görünür.
- C8 Kayıt Ol (Android 15 + iOS): 'Klinik acil telefon' odaklı iken 'Hesap Oluştur' görünür ve ilk dokunuşta çalışır; yatay 640×360'ta form baştan sona kaydırılabilir.
- C9 Regresyon: swipe ile sekme geçişi (Ana Ekran ↔ Kontrol) klavye kapalıyken çalışır; klavye kapanınca alt bar geri gelir, ACİL DURDUR rs(76) ofsetine döner; masaüstü client (Tauri/WebView2 1280×800) ve LAN tarayıcı (telefon) yerleşimi değişmedi (ekran görüntüsü karşılaştırması).
- C10 Cihaz sınıfı kapsamı: a (küçük telefon 360×640), b (iPhone), c (yatay telefon), d (Android tablet — KAV enabled, alt bar yok → yalnız KAV padding), i (font ölçeği 1.3), j (çentikli iPhone insets.bottom>0 → ACİL DURDUR ofset hesabı).

**Açık sorular (sahip kararı):**
- Sahip kararı: klavye açıkken ACİL DURDUR'un klavyenin ÜSTÜNDE yüzmesi (içeriğin alt ~64px'ini örter) kabul mü, yoksa yalnız 'klavye kapanınca görünür' mü? Plan güvenli tarafı (görünür) seçti.
- iOS gerçek cihaz ölçümü için EAS derleme kotası/süresi var mı? Yoksa Android APK + iOS Simulator ile yayın, iOS gerçek cihaz 'bekliyor' notuyla.
- Android ≤10 (API<30) cihaz sahada var mı? Varsa legacy resize + KAV geçici çift boşluk kabul edilebilir mi (kendini düzeltiyor), yoksa KAV_BEHAVIOR_PENCERE'de API<30 için undefined kalsın (plan böyle).
- ekranC-13 madde 3 (AiHistory/TreatmentHistory'de sabit filtre çipleri = AppShell `scroll={false}` + FlatList + stickyHeaderIndices) ayrı iyileştirme kalemi olarak istenir mi? Bu plan bilinçli kapsam dışı bıraktı.
- AiSpecApprovalModal (Red gerekçesi TextInput, ortalı kart maxHeight %88) ve PatientGate arama alanı S4 bulgularında yok; aynı KAV_BEHAVIOR_MODAL kalıbı 0.5 saatle uygulansın mı (tutarlılık)?
- Dashboard/Kpi/Sensor container'larının `padding: spacing.md` + AppShell content `padding: spacing.xl` çift yatay padding'i S4 dışı (S1/S5 kökü) — burada bırakıldı; o kökün planında ele alınmalı.

**Toplam efor:** ~13.25 saat

### S5 — Yükseklik, yatay telefon, safe-area, modallar (10 bulgu: 0 yüksek / 6 orta / 4 düşük)

Bağlı bulgular: `kabuk-4`, `kabuk-6`, `kabuk-9`, `ekranA-4`, `ekranA-5`, `ekranB-3`, `ekranB-10`, `ilkel-12`, `kapsam-1`, `kapsam-4`

**Hedef:** (1) useResponsive'a isShort/isLandscape/isLandscapePhone ekleyip kabuğu kısa yükseklikte sıkıştırmak (alt başlık gizli, ≥768 yatayda ikon-rail, <768 yatayda kompakt alt bar, ACİL DURDUR daima görünür ve ≥48 px). (2) Ortak ScrollableModalCard ilkeli (maxHeight = pencere − inset'ler, gövde ScrollView, SABİT eylem satırı, backdrop-dokunuş kapatma, iOS KAV) ve UpgradeModal + AiSpecApprovalModal'ın buna taşınması. (3) AppShell köküne + absolute katmanlara (bottomNav, E-stop, Toast) insets.left/right; Welcome/Auth/MobileUpdateGate'e insets. (4) Sabit grafik/liste yüksekliklerini height'a bağlamak. (5) Kilit: jest testleri + Python 'modal kaydırılabilir' kapısı + 640×360/667×375/812×375/932×430 görünüm-alanı ekran görüntüleri.

**Tasarım kararları:**
- isShort eşiği 500 px (rapor S5 + ekranB-3 ikinci doğrulama). isLandscape = width > height. isLandscapePhone = isShort && isLandscape. Kabuk davranışı isShort'a bağlanır, isLandscapePhone yalnız yerleşim (rail/2 sütun) için.
- ≥768 yatay telefonda (Pixel 7 Pro 926×428, S23 vb. — çentikli telefonların büyük çoğunluğu) 'sidebar→bottom bar' YERİNE ikon-rail (rs(72), NavButton compact) seçildi: alt bar 360 px yüksekliğin ~72 px'ini (%20) yerdi, rail dikeyden 0 px alır. Görev notundaki 'sidebar→bottom bar' seçeneği reddedildi; gerekçe dikey alan. desktop bayrağı (E-stop bottomOffset=0, panResponder kapalı) DEĞİŞMEZ → seans akışı/E-stop mantığı aynı dalda kalır.
- ACİL DURDUR HASTA GÜVENLİĞİ: compact kipte bile minHeight rs(48), tam metin, zIndex 10000, sağ-alt hizalı maxWidth rs(240). Hiçbir koşulda gizlenmez/küçültülmez (yalnız genişliği daralır). GlobalEmergencyStop kabul testi ile kilitlenir.
- ScrollableModalCard: maxHeight yüzde DEĞİL mutlak (height − insets.top − insets.bottom − 2×spacing.md) → yüzde hesabı çentikli/yatay cihazda yanıltıyordu. Gövde ScrollView style flexShrink:1 flexGrow:0 (Yoga'da çocuklar varsayılan flexShrink:0 → maxHeight aşılınca taşıyordu; ekranB-10 kök nedeni). Eylem satırı (footer) ScrollView DIŞINDA, her zaman görünür. İç ScrollView'lar (tableWrap) düz View olur → tek kaydırıcı (iç içe ScrollView Android'de dokunuşu çalıyordu).
- Alt-sayfa (flex-end) modallar (ObservationNotesModal, DevicePairingGuide, SessionDetailModal) zaten ScrollView + maxHeight ile kurulu → bu turda DOKUNULMAZ; BackupPassphraseDialog/OperatorSwitcher (S4/S3 kökleri) ScrollableModalCard'a taşınacak adaylar olarak Python kapısının allowlist'ine yazılır.
- Absolute konumlu katmanlar (bottomNav, GlobalEmergencyStop.wrap, toastContainer) kök View'un paddingLeft/Right'ından ETKİLENMEZ (Yoga absolute = padding-kutusuna göre) → her biri kendi left/right'ında Math.max(insets.left, spacing.x) alır; normal flex çocukları (sidebar, header, content) kök padding ile çözülür.
- useResponsive mock'ları (AppShell.logout/pairing testleri) height/isShort döndürmüyor → kabukta `responsive.isShort === true` biçiminde savunmacı okunur; mock'lara isShort:false, height:800 eklenir ama kod undefined'a dayanır.
- SCALE (tokens.ts) açılışta kısa kenardan bir kez hesaplanır; yatayda değişmez → rs() değerleri yatayda büyümez, plan buna güvenir. rs()'e dokunulmaz (S1 kökü).
- Klavye (KAV) kabuk düzeyi S4'ün işi (kabuk-7); bu plan yalnız ScrollableModalCard içine iOS KAV koyar (ekranB-10 red gerekçesi TextInput). Android adjustResize zaten var.
- Efor: rapor S5 için 1-2 gün; burada 19,5 saat (cihaz doğrulaması dahil).

| # | Adım | Dosyalar | Değişiklik | Kapattığı | Doğrulama | Risk | Efor (s) |
|---|---|---|---|---|---|---|---|
| 1 | useResponsive'a isShort / isLandscape / isLandscapePhone + jest anlık görüntüsü | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\hooks\useResponsive.ts`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\hooks\__tests__\useResponsive.test.ts (YENİ)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\AppShell.logout.test.tsx (mock genişlet)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\AppShell.pairing.test.tsx (mock genişlet)` | useResponsive() dönüşüne üç alan ekle: isShort = height < SHORT_HEIGHT (500, breakpoints.ts'e `shortHeight: 500` sabiti olarak koy — tek kaynak), isLandscape = width > height, isLandscapePhone = isShort && isLandscape. Mevcut alanlar değişmez (geriye uyumlu). İki AppShell testindeki useResponsive mock'una `height: 800… |  | jest: hooks/__tests__/useResponsive.test.ts — react-native useWindowDimensions'ı jest.mock ile 390×844 (isShort false), 844×390 (isShort+isLandscapePhone true), 1280×800 (false), 1200×480 (isShort tr… | Düşük. Yalnız ek alan; tüketici yok. Geri alma: üç satırı sil. | 1 |
| 2 | Ortak ScrollableModalCard ilkeli (maxHeight + gövde ScrollView + sabit eylem satırı + inset'ler) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\ScrollableModalCard.tsx (YENİ)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\ScrollableModalCard.test.tsx (YENİ)` | Yeni ilkel: props { visible, onRequestClose, onBackdropPress?, header?: ReactNode, footer?: ReactNode, children, maxWidth?=rs(520), align?: 'center'|'bottom', testID?, accessibilityLabel?, contentGap? }. Yapı: Modal(transparent, fade) > KeyboardAvoidingView(iOS padding, flex:1) > Pressable backdrop (onBackdropPress; p… |  | jest: (a) footer düğümü ScrollView'un DIŞINDA: `within(getByTestId('x-govde')).queryByText('Onayla')` null, `getByText('Onayla')` var; (b) backdrop press → onBackdropPress çağrılır, kart içi press → … | Düşük (yeni dosya, tüketici yok). Yoga uyarısı: ScrollView'a flexShrink:1 verilmezse maxHeight aşılır → test (c) + adım 9 yapısal testi kilitler. Geri alma: do… | 3 |
| 3 | AppShell: insets.left/right (kök + absolute katmanlar) ve kısa-yükseklik kabuk davranışı (alt başlık gizli, ikon-rail, kompakt alt bar) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\AppShell.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\AppShell.landscape.test.tsx (YENİ)` | (a) :209 root style'a `paddingLeft: insets.left, paddingRight: insets.right` ekle (sidebar/header/content normal flex çocuğu → kapsanır). (b) :402 bottomNav: `paddingLeft: Math.max(insets.left, spacing.sm), paddingRight: Math.max(insets.right, spacing.sm)` (absolute → kök padding etkilemez). (c) `const isShort = respo… | `kabuk-6`, `ekranB-3` | jest AppShell.landscape.test.tsx (AppShell.logout mock kalıbı): (1) mock {width:812,height:375,isTablet:true,isDesktop:false,isShort:true,isLandscape:true} → queryByText(subtitle) null, nav etiketler… | ORTA — kabuk her rotanın çatısı. HASTA GÜVENLİĞİ: E-stop render koşulu ve zIndex'e DOKUNULMAZ; rail yalnızca sidebar genişliğini değiştirir. panResponder `desk… | 3.5 |
| 4 | GlobalEmergencyStop: compact prop (sağ-alt, dar) + insets.left/right — daima görünür | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\GlobalEmergencyStop.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\GlobalEmergencyStop.test.tsx (YENİ)` | Props'a `compact?: boolean` ekle. wrap style: `left: Math.max(spacing.md, insets.left), right: Math.max(spacing.md, insets.right)`; compact iken `alignItems: 'flex-end'` ve btn'e `maxWidth: rs(240)`; minHeight rs(52) → compact'ta rs(48) (ASLA 44 altı), paddingVertical spacing.sm. Metin/label/hint/pointerEvents/zIndex/… | `ekranB-3`, `kabuk-6` | jest GlobalEmergencyStop.test.tsx: useLiveData mock snapshot.coils=[{running:true}] → compact=true ve compact=false iken accessibilityLabel 'Acil durdur' düğmesi VAR, press → performEmergencyStop çağ… | HASTA GÜVENLİĞİ — en kritik bileşen. Yalnız stil/konum değişir; onPress ve render koşuluna dokunulmaz. Kilit: pemf-device-safety-shutdown değişmezleri; test 'c… | 0.75 |
| 5 | 'Daha Fazla' sheet'i: maxHeight + ScrollView + yatayda 2 sütun; bildirim paneli yüksekliği | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\AppShell.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\NotificationCenter.tsx` | AppShell :425-466 moreSheet: Pressable'a `maxHeight: Math.round(responsive.height * 0.85)`; başlık sabit, moreEntries.map bir `<ScrollView contentContainerStyle={[styles.moreList, responsive.isLandscape && styles.moreListLandscape]} testID='daha-fazla-liste'>` içine; moreRow'a isLandscape iken `width: '48%'` (moreList… | `kabuk-4`, `ilkel-12` | jest (AppShell.landscape.test.tsx'e ekle): mock {width:667,height:375,isCompact:true,isShort:true,isLandscape:true}, userMode 'veterinarian' → 'Daha Fazla' press → getByTestId('daha-fazla-liste') Scr… | Düşük. moreSheet içindeki ScrollView Modal'da → panResponder etkilenmez. Çıkış satırı (LOGOUT_ITEM) listede kalır; handleLogout aynı. Geri alma: ScrollView'ı V… | 1.5 |
| 6 | ToastProvider: insets.top/left/right + spring toValue 0 | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\ToastProvider.tsx` | `const insets = useSafeAreaInsets();` (Provider _layout.tsx:32'de SafeAreaProvider'ın çocuğu → hook çalışır). Animated.View style'a inline `{ top: insets.top + spacing.md, left: Math.max(spacing.md, insets.left), right: Math.max(spacing.md, insets.right) }`; :65 spring toValue 20 → 0 ve :62 setValue(-20) aynı (yukarıd… | `kabuk-9` | Mevcut ToastProvider'ı mock'layan testler etkilenmez (mock). Testlerde SafeAreaProvider'sız gerçek ToastProvider kullanan var mı: `grep -rn 'ToastProvider>' pf/src --include=*.test.tsx` → varsa react… | Düşük. Kritik toast'lar ('Acil durdurma gönderiliyor…') konum dışında değişmez. Geri alma: sabitleri geri koy. | 0.5 |
| 7 | WelcomeScreen + AuthScreen: safe-area inset'leri (AppShell dışı ekranlar) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\WelcomeScreen.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\AuthScreen.tsx` | Her ikisine `import { useSafeAreaInsets } from 'react-native-safe-area-context'` + `const insets = useSafeAreaInsets();`. Welcome :32 ScrollView contentContainerStyle → `[styles.container, { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl, paddingLeft: Math.max(spacing.xl, insets.left), … | `ekranA-4`, `ekranA-5` | Bu ekranları render eden mevcut testler (`grep -ln 'WelcomeScreen\|AuthScreen' pf/src/**/__tests__`) SafeAreaProvider'sızsa useSafeAreaInsets mock'u ekle (AppShell.logout kalıbı :31-33). Cihaz: Andro… | Düşük. Welcome 'Çıkış' guardTeardown akışı (seans sürerken) değişmez. Geri alma: inline style'ı kaldır. | 0.75 |
| 8 | MobileUpdateGate: kök ScrollView + inset'ler + kısa yükseklikte sıkı düzen ('Şimdilik devam et' daima erişilir) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\MobileUpdateGate.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\__tests__\MobileUpdateGate.test.tsx` | :134 `<View style={styles.root} testID='mobil-acilis-kapisi'>` → `<ScrollView style={styles.rootScroll} contentContainerStyle={[styles.root, { paddingTop: Math.max(spacing.xl, insets.top), paddingBottom: Math.max(spacing.xl, insets.bottom), paddingLeft: Math.max(spacing.xl, insets.left), paddingRight: Math.max(spacing… | `kapsam-1` | jest MobileUpdateGate.test.tsx: mevcut 'kapı asla kalıcı kilitlenmez' süiti (getByTestId('mobil-acilis-kapisi'), 'kapi-devam', 'kapi-atla') AYNEN yeşil; yeni test: `UNSAFE_getByType(ScrollView)` kök … | ORTA — açılış kapısı; dosya başlığındaki 'kapı asla kalıcı kilitlenmez' ilkesi. Yalnız sarmalayıcı değişir; durum/zamanlayıcı/ertelme mantığına dokunulmaz. Mev… | 1.5 |
| 9 | UpgradeModal → ScrollableModalCard (backdrop-dokunuşla kapanma, kısa yükseklikte sıkı kart) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\UpgradeModal.tsx` | :47-77 Modal/backdrop/card → `<ScrollableModalCard visible onRequestClose={onClose} onBackdropPress={onClose} maxWidth={rs(420)} cardStyle={[styles.card, isShort && styles.cardShort]} header={<X düğmesi (iconBtn deseni: minWidth/minHeight rs(44), alignSelf flex-end)>} footer={<TouchableOpacity style={styles.btn} onPre… | `kapsam-4` | jest (yeni UpgradeModal.test.tsx, EntitlementContext mock): 'Anladım' getByText → press onClose; backdrop press onClose; 'Anladım' ScrollView gövdesinin DIŞINDA (within(getByTestId('upgrade-modal-gov… | Düşük. Modal bilgilendirici; seans akışıyla ilgisi yok. Geri alma: revert. | 1 |
| 10 | AiSpecApprovalModal → ScrollableModalCard (Onayla/Reddet SABİT eylem satırı; tek kaydırıcı) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\AiSpecApprovalModal.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\__tests__\AiSpecApprovalModal.test.tsx` | :85-192 → `<ScrollableModalCard visible onRequestClose={kapat} onBackdropPress={kapat} maxWidth={rs(520)} testID='ai-onay' accessibilityLabel='AI seans önerisi onay penceresi' header={s.head (başlık + X)} footer={rejecting ? <Vazgeç/Reddet actions> : <Reddet/Onayla ve Başlat actions>}>` gövde: lead, summary, rel, xai,… | `ekranB-10` | jest AiSpecApprovalModal.test.tsx'e ekle: (1) 8 bobinli SPECS + useResponsive mock height:360 → getByLabelText('Öneriyi onayla ve seansı başlat') var ve press → onApprove; (2) YAPISAL kilit: `within(… | ORTA — hekim onay kapısı ('onaysız tedavi başlamaz'). Onay/red handler'ları ve onDismiss semantiği değişmez; yalnız yerleşim. Kilit: mevcut aiHubOtonomOnayKapi… | 1.5 |
| 11 | SensorMonitor grafik yüksekliğini pencere yüksekliğine bağla | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\SensorMonitorScreen.tsx` | :119 `height={rs(280)}` → `const { height: winH } = useResponsive();` ve `height={Math.max(rs(160), Math.min(rs(280), Math.round(winH * 0.45)))}` (yatay 360 → 162, 375 → 169, dikey → 280). RealtimeChart PAD sabitleriyle plotH ≥ ~100 px kalır; canvas/svg width-height prop'ları zaten dinamik (RealtimeChart.tsx:231-244). | `ekranB-3` | jest: SensorMonitor'u render eden test varsa useResponsive mock ekle; yeni küçük test: mock height 360 → RealtimeChart mock'unun height prop'u ≤ rs(170) ve ≥ rs(160); height 844 → rs(280). Ekran görü… | Düşük. Yalnız görsel yükseklik. 500-620 px pencerede grafik 225-280 arasında değişir → PC'de küçük pencerede hafif küçülme (kabul). Geri alma: sabit rs(280). | 0.5 |
| 12 | Kilit: Python 'modal kaydırılabilir' kapısı (allowlist + SABİT sayaç) ve kırmızı kanıtı | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\tests\test_modal_kaydirilabilir_kapisi.py (YENİ)` | pf/src altında `<Modal` içeren her .tsx (test hariç) için: (a) `ScrollableModalCard` import ediyor VEYA (b) dosyada `<ScrollView` ve `maxHeight` ikisi de var; ikisi de yoksa kırmızı. Bilinen istisnalar SABİT allowlist: {'components/domain/BackupPassphraseDialog.tsx' (S4 ilkel-11), 'components/domain/OperatorSwitcher.t… | `kapsam-4`, `ekranB-10`, `kabuk-4` | Kapı KIRMIZI kanıtı (memory: kapi-kirmizi-oldugunu-kanitla): geçici olarak UpgradeModal'daki ScrollableModalCard import'unu yorumla → pytest kırmızı; geri al → yeşil (git checkout ile DEĞİL, elle ger… | Düşük. Yanlış-pozitif: sheet modallar (flex-end) zaten ScrollView+maxHeight taşıyor → geçer. Geri alma: dosyayı sil. | 1.5 |
| 13 | Cihaz + görünüm-alanı doğrulama turu (yatay telefon, çentik, yazı ölçeği) ve bulgu JSON güncellemesi | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\docs\responsive-denetim-2026-09-04.bulgular.json (durum alanı)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf (expo export:web + Android build)` | Kod değişikliği yok. (a) `npm run export:web` → Edge headless + CDP ile 640×360, 667×375, 812×375, 932×430, 320×568, 911×512 görünüm alanlarında: Sensörler (seans sürerken E-stop), Daha Fazla sheet, Bildirimler, AI onay modalı (8 bobin), UpgradeModal 'research'. (b) Android emülatör (Pixel 5 API 34 edge-to-edge + 16:9… | `ekranB-3`, `kabuk-4`, `kabuk-6`, `kabuk-9`, `ekranA-4`, `ekranA-5`, `ekranB-10`, `ilkel-12`, `kapsam-1`, `kapsam-4` | Ekran görüntüleri docs/responsive-denetim-2026-09-04-s5-kanit/ altına; her bulgu id'si için önce/sonra çifti. Kabul ölçütü: (1) 667×375 seans sürerken E-stop görünür ve dokunulur (≥48 px), (2) AI ona… | Düşük (doğrulama). iOS çentik (insets.left 44-59) yalnız EAS build ile ölçülür → açık soru. Backend + APK build paralel koşmaz (memory: yayın 2026-08-27). | 2.5 |

<details><summary>Kod taslakları</summary>

**1. useResponsive'a isShort / isLandscape / isLandscapePhone + jest anlık görüntüsü**

```
// theme/breakpoints.ts
export const shortHeight = 500; // px; altı = 'kısa' (yatay telefon, küçük tarayıcı penceresi)
// hooks/useResponsive.ts
const isShort = height < shortHeight;
const isLandscape = width > height;
return { width, height, layout, columns, isCompact, isTablet, isDesktop,
  isShort, isLandscape, isLandscapePhone: isShort && isLandscape,
  isWeb: Platform.OS === "web", isNative: Platform.OS !== "web" };
```

**2. Ortak ScrollableModalCard ilkeli (maxHeight + gövde ScrollView + sabit eylem satırı + inset'ler)**

```
export function ScrollableModalCard({ visible, onRequestClose, onBackdropPress, header, footer, children, maxWidth = rs(520), align = "center", testID, accessibilityLabel, cardStyle }: Props) {
  const insets = useSafeAreaInsets();
  const { height } = useResponsive();
  const maxH = Math.max(rs(200), height - insets.top - insets.bottom - spacing.md * 2);
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onRequestClose}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <Pressable style={[s.backdrop, align === "bottom" && s.backdropBottom,
          { paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + spacing.md,
            paddingLeft: Math.max(spacing.md, insets.left), paddingRight: Math.max(spacing.md, insets.right) }]}
          onPress={onBackdropPress}>
          <Pressable onPress={() => {}} style={[s.card, { maxWidth, maxHeight: maxH }, cardStyle]} testID={testID} accessibilityLabel={accessibilityLabel}>
            {header}
            <ScrollView style={s.body} contentContainerStyle={s.bodyContent} keyboardShouldPersistTaps="handled" testID={testID ? `${testID}-govde` : undefined}>{children}</ScrollView>
            {footer ? <View style={s.footer}>{footer}</View> : null}
          </Pressable>
        </Pressable>
      </KeyboardAvoidingView>
    </Modal>);
}
const s = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", alignItems: "center", justifyContent: "center" },
  backdropBottom: { justifyContent: "flex-end" },
  card: { width: "100%", backgroundColor: colors.panel, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, flexDirection: "column" },
  body: { flexShrink: 1, flexGrow: 0 },
  bodyContent: { gap: spacing.sm },
  footer: { flexShrink: 0, paddingTop: spacing.sm },
});
```

**3. AppShell: insets.left/right (kök + absolute katmanlar) ve kısa-yükseklik kabuk davranışı (alt başlık gizli, ikon-rail, kompakt alt bar)**

```
const isShort = responsive.isShort === true;
const rail = desktop && isShort;
<View style={[styles.root, { paddingTop: insets.top, paddingLeft: insets.left, paddingRight: insets.right }]}>
  {desktop ? (
    <View style={[styles.sidebar, rail && styles.sidebarRail]}>
      <View style={styles.brand}><Image .../>{!rail && <Text style={styles.brandTitle}>PEMF Vet</Text>}</View>
      <ScrollView ...>{navItems.map(item => <NavButton ... compact={rail} />)}<NavButton ... compact={rail} danger /></ScrollView>
    </View>) : null}
  <View style={[styles.header, isShort && styles.headerShort]}>
    <Text style={styles.title} numberOfLines={1}>{title}</Text>
    {!isShort && <Text style={styles.subtitle} numberOfLines={2}>{subtitle}</Text>}
  ...
  <GlobalEmergencyStop bottomOffset={desktop ? 0 : (isShort ? rs(60) : rs(76))} compact={isShort} />
  <View style={[styles.bottomNav, isShort && styles.bottomNavShort, { paddingBottom: Math.max(insets.bottom, spacing.sm), paddingLeft: Math.max(insets.left, spacing.sm), paddingRight: Math.max(insets.right, spacing.sm) }]}>
// styles: sidebarRail: { width: rs(72), padding: spacing.sm, gap: spacing.md, alignItems: "center" },
// headerShort: { paddingVertical: spacing.sm }, bottomNavShort: { paddingTop: spacing.xs }
```

**4. GlobalEmergencyStop: compact prop (sağ-alt, dar) + insets.left/right — daima görünür**

```
export function GlobalEmergencyStop({ bottomOffset = 0, compact = false }: { bottomOffset?: number; compact?: boolean }) {
  ...
  <View style={[styles.wrap, compact && styles.wrapCompact, { bottom: bottomOffset + insets.bottom + spacing.md, left: Math.max(spacing.md, insets.left), right: Math.max(spacing.md, insets.right) }]} pointerEvents="box-none">
    <Pressable onPress={onPress} style={[styles.btn, compact && styles.btnCompact]} ...>
// wrapCompact: { alignItems: "flex-end" }, btnCompact: { maxWidth: rs(240), minHeight: rs(48), paddingVertical: spacing.sm }
```

**5. 'Daha Fazla' sheet'i: maxHeight + ScrollView + yatayda 2 sütun; bildirim paneli yüksekliği**

```
<Pressable onPress={() => {}} style={[styles.moreSheet, { paddingBottom: insets.bottom + spacing.lg, maxHeight: Math.round(responsive.height * 0.85) }]}>
  <Text style={styles.moreTitle}>Diğer Ekranlar</Text>
  <ScrollView style={{ flexShrink: 1 }} contentContainerStyle={[styles.moreList, responsive.isLandscape && styles.moreListLandscape]} testID="daha-fazla-liste">
    {moreEntries.map((entry) => ... <Pressable style={[styles.moreRow, responsive.isLandscape && styles.moreRowHalf, ...]} />)}
  </ScrollView>
</Pressable>
// moreList: { gap: spacing.xs }, moreListLandscape: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }, moreRowHalf: { width: "48%" }
```

**6. ToastProvider: insets.top/left/right + spring toValue 0**

```
const insets = useSafeAreaInsets();
<Animated.View pointerEvents="box-none" style={[styles.toastContainer, { top: insets.top + spacing.md, left: Math.max(spacing.md, insets.left), right: Math.max(spacing.md, insets.right), opacity, transform: [{ translateY }] }]}>
// Animated.spring(translateY, { toValue: 0, useNativeDriver: true })
```

**7. WelcomeScreen + AuthScreen: safe-area inset'leri (AppShell dışı ekranlar)**

```
const insets = useSafeAreaInsets();
<ScrollView contentContainerStyle={[styles.container, {
  paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl,
  paddingLeft: Math.max(spacing.xl, insets.left), paddingRight: Math.max(spacing.xl, insets.right) }]} bounces={false}>
```

**8. MobileUpdateGate: kök ScrollView + inset'ler + kısa yükseklikte sıkı düzen ('Şimdilik devam et' daima erişilir)**

```
const insets = useSafeAreaInsets();
const { isShort } = useResponsive();
return (
  <ScrollView style={styles.rootScroll} bounces={false} keyboardShouldPersistTaps="handled" testID="mobil-acilis-kapisi"
    contentContainerStyle={[styles.root, { paddingTop: Math.max(spacing.xl, insets.top), paddingBottom: Math.max(spacing.xl, insets.bottom), paddingLeft: Math.max(spacing.xl, insets.left), paddingRight: Math.max(spacing.xl, insets.right) }]}>
    <Image source={LOGO} style={[styles.logo, isShort && styles.logoShort]} resizeMode="contain" />
    ...
// rootScroll: { flex: 1, backgroundColor: colors.bg }, root: { flexGrow: 1, alignItems: "center", justifyContent: "center" }, logoShort: { width: rs(56), height: rs(56) }
```

**9. UpgradeModal → ScrollableModalCard (backdrop-dokunuşla kapanma, kısa yükseklikte sıkı kart)**

```
<ScrollableModalCard visible={visible} onRequestClose={onClose} onBackdropPress={onClose} maxWidth={rs(420)} testID="upgrade-modal"
  cardStyle={[styles.card, isShort && styles.cardShort]}
  header={<TouchableOpacity style={styles.close} onPress={onClose} accessibilityRole="button" accessibilityLabel="Kapat"><X size={20} color={colors.textMuted} /></TouchableOpacity>}
  footer={<TouchableOpacity style={styles.btn} onPress={onClose} accessibilityRole="button"><Text style={styles.btnText}>Anladım</Text></TouchableOpacity>}>
  <View style={[styles.iconRing, isShort && styles.iconRingShort]}><Icon size={isShort ? 22 : 30} color={colors.primary} /></View>
  <Text style={styles.title}>{title}</Text> ...
</ScrollableModalCard>
// close: { alignSelf: "flex-end", minWidth: rs(44), minHeight: rs(44), alignItems: "center", justifyContent: "center" }
```

**10. AiSpecApprovalModal → ScrollableModalCard (Onayla/Reddet SABİT eylem satırı; tek kaydırıcı)**

```
<ScrollableModalCard visible={visible} onRequestClose={kapat} onBackdropPress={kapat} maxWidth={rs(520)} testID="ai-onay"
  header={<View style={s.head}><Text style={s.title}>AI Seans Önerisi</Text><TouchableOpacity onPress={kapat} hitSlop={12} ...><X size={rs(20)} /></TouchableOpacity></View>}
  footer={rejecting ? (
    <View style={s.actions}>{/* Vazgeç + Reddet */}</View>
  ) : (
    <View style={s.actions}>{/* Reddet + Onayla ve Başlat */}</View>)}>
  <Text style={s.lead}>…</Text>
  <View style={s.summary}>…</View>
  <View style={s.table}>{/* eski tableWrap; ScrollView DEĞİL, maxHeight YOK */}</View>
  {rejecting && (<View style={s.rejectBox}><Text style={s.rejectLabel}>Red gerekçesi (kayda geçer)</Text><TextInput … /></View>)}
</ScrollableModalCard>
```

**11. SensorMonitor grafik yüksekliğini pencere yüksekliğine bağla**

```
const { height: winH } = useResponsive();
const chartH = Math.max(rs(160), Math.min(rs(280), Math.round(winH * 0.45)));
<RealtimeChart … width={Math.min(chartW, 1200)} height={chartH} />
```

**12. Kilit: Python 'modal kaydırılabilir' kapısı (allowlist + SABİT sayaç) ve kırmızı kanıtı**

```
_KAYNAK = _KOK / "pf" / "src"
_ISTISNA = {"components/domain/BackupPassphraseDialog.tsx", "components/domain/OperatorSwitcher.tsx"}  # S4/S3 planlarında kapanır
def test_istisna_sayaci_sabit():
    assert len(_ISTISNA) == 2, "yeni istisna = bilinçli karar; bu sayacı ve S-planını güncelle"
@pytest.mark.parametrize("dosya", sorted(p for p in _KAYNAK.rglob("*.tsx") if "__tests__" not in p.parts and "<Modal" in p.read_text(encoding="utf-8")))
def test_modal_kaydirilabilir(dosya):
    rel = dosya.relative_to(_KAYNAK).as_posix()
    if rel in _ISTISNA: pytest.skip("bilinen borç")
    m = dosya.read_text(encoding="utf-8")
    ok = "ScrollableModalCard" in m or ("<ScrollView" in m and "maxHeight" in m)
    assert ok, f"{rel}: Modal kaydırılamaz/maxHeight'sız (S5 kökü) — ScrollableModalCard kullan"
```

</details>

**Bağımlılıklar:** Adım 1 (useResponsive.isShort) → adım 3, 5, 8, 9, 10, 11 (hepsi isShort/height okur).; Adım 2 (ScrollableModalCard) → adım 9, 10, 12 (kapı ilkelin adını arar).; Adım 4 (GlobalEmergencyStop compact) ↔ adım 3 (AppShell compact prop'u geçer) — birlikte commit'lenmeli; aksi hâlde tip hatası.; S4 kökü (kabuk-7: AppShell içerik KeyboardAvoidingView + klavye açıkken alt bar gizleme/E-stop ofseti 0): ekranB-3'ün klavye kısmı ORADA kapanır; bu plan yalnız modal içi KAV'ı kapsar. S4 planı AppShell.tsx:385-393'ü değiştirir → bu planın adım 3(f) ile aynı satırlar: sıralama S5 önce, S4 sonra (ya da tek PR).; S3 kökü (touch token): UpgradeModal X (kapsam-5) ve AiSpec X (ilkel-3) hedefleri adım 9/10'da iconBtn deseniyle yan etki olarak büyür; S3 planı bunları 'zaten kapandı' saymadan önce doğrulasın.; S1 kökü (rs SCALE tavanı) değişirse rs(160)/rs(280)/rs(72) mutlak değerleri kayar; plan oranlara (height×0.45) dayandığı için kırılmaz.; Python kapısı (adım 12) CI tests.yml yol filtresi: pf/ değişikliğinde koşmalı (test_ci_workflow_gate.py mevcut kalıbı kontrol).

**Kilitler:**
- jest hooks/__tests__/useResponsive.test.ts — 5 görünüm alanı anlık görüntüsü (320×568, 390×844, 844×390, 1200×480, 1280×800); rapor §6 kilit (3).
- jest ui/__tests__/ScrollableModalCard.test.tsx — footer ScrollView dışında (yapısal), backdrop/kart dokunuş semantiği, maxHeight = height − inset'ler.
- jest ui/__tests__/AppShell.landscape.test.tsx — isShort'ta subtitle yok, nav etiketleri var, E-stop RENDER EDİLİYOR (hasta güvenliği), Daha Fazla sheet ScrollView + tüm rotalar erişilir; dikeyde regresyon yok.
- jest ui/__tests__/GlobalEmergencyStop.test.tsx — compact ve normal kipte düğme bulunur, minHeight ≥ rs(44), press → performEmergencyStop.
- jest domain/__tests__/AiSpecApprovalModal.test.tsx — 'Onayla ve Başlat' ScrollView gövdesinin DIŞINDA (within(...) null) + press onApprove.
- jest domain/__tests__/MobileUpdateGate.test.tsx — kök ScrollView flexGrow:1; mevcut 'kapı asla kalıcı kilitlenmez' süiti aynen.
- Python tests/test_modal_kaydirilabilir_kapisi.py — her <Modal dosyası ScrollableModalCard VEYA ScrollView+maxHeight; istisna allowlist SABİT sayaç (=2); mutasyonla kırmızı kanıtlandı.
- Görünüm-alanı ekran görüntüsü kapısı (rapor §6 faz 3; bu turda elle): 640×360 / 667×375 / 812×375 / 932×430 web export'ta Sensörler+E-stop, AI onay, UpgradeModal, Daha Fazla, Bildirimler.

**Cihaz testi:**
- Android emülatör Pixel 5 (API 34, edge-to-edge, 393×851 → yatay 851×393 = TABLET dalı): seans sürerken yatay → ikon-rail, subtitle yok, E-stop sağ-altta ≥48 px, tek dokunuşla 'Tüm bobinler durduruldu ✓'.
- Android emülatör 16:9 profili (640×360 yatay = PHONE dalı, iPhone SE/8 eşdeğeri): Daha Fazla sheet'inde 'Sensörler' ve 'Seans Geçmişi' erişilir; alt bar kompakt; E-stop görünür.
- Aynı emülatör + Ayarlar → Yazı boyutu 1.3: MobileUpdateGate 'guncelleme' durumu (sahte manifest) yatayda → 'Şimdilik devam et' kaydırılarak erişilir ve kapı açılır; UpgradeModal 'research' 320×568 dikeyde X + 'Anladım' görünür.
- Çentikli Android (kamera deliği, emülatörde 'Display cutout' geliştirici seçeneği: çift/köşe) yatay: başlığın ilk harfi ve ilk nav ögesi örtülmez; toast çentik altına girmez.
- AI Pro öneri onayı (8 bobin, xaiSensitivity dolu) yatay 640×360: tablo kaydırılır, 'Reddet' → gerekçe TextInput + klavye açıkken 'Reddet' onay düğmesi görünür (KAV), 'Onayla ve Başlat' dokunulur.
- Welcome (3 profil kurulu) + Auth 'Kayıt Ol' modu edge-to-edge dikey ve yatay: e-posta/Çıkış ve logo halkası durum çubuğu altında değil; alt bilgi gesture çubuğu üstünde.
- PC WebView2 (launcher, 880×600 ve 700×540 minimum) ve tarayıcı 1920×1080: isShort false → hiçbir kabuk değişikliği yok (regresyon kontrolü); Bildirimler paneli PC'de daha fazla öğe gösterir.
- iOS (EAS build, iPhone 14/15 yatay insets.left 47-59): sidebar/rail çentik dışında; toast Dynamic Island altında başlar — EAS erişimi yoksa açık soru olarak kaydet.

**Açık sorular (sahip kararı):**
- ≥768 yatay telefonda ikon-rail (bu plan) mı, görev notundaki 'sidebar→bottom bar' mı? Rail dikeyden 0 px alır; bottom bar ~72 px (360'ın %20'si). Sahip kararı gerekiyorsa rail varsayılan, tek satırlık `rail` koşuluyla geri çevrilebilir.
- E-stop compact kipinde metin '🚨 ACİL DURDUR (3 bobin)' rs(240) genişlikte adjustsFontSizeToFit ile küçülür — bobin sayısını compact'ta gizlemek kabul edilebilir mi, yoksa iki satıra mı izin verilsin? (Hasta güvenliği: metin okunurluğu.)
- iOS doğrulaması yalnız EAS bulut build ile mümkün (memory: pemf-ios-eas-build); bu tur için Android emülatör + web export yeterli sayılacak mı?
- isShort eşiği 500 px tarayıcıda küçültülmüş pencereyi de (1200×480) 'kısa' sayar → PC'de subtitle gizlenir ve sidebar rail olur. Kabul mü, yoksa `isNative` ile sınırlansın mı? (Plan: kabul — kısa pencere kısa penceredir.)
- Python kapısının allowlist'indeki BackupPassphraseDialog/OperatorSwitcher S4/S3 planlarında ScrollableModalCard'a taşınınca sayaç 2→0 güncellenecek — o planların sahibi kim?
- ilkel-12 'PC'de maxVisible 40' önerisi (ikinci doğrulama kozmetik dedi) bu turda YAPILMADI; istenirse AppShell.tsx:472 tek satır.

**Toplam efor:** ~19.5 saat

### S6 — Sistem yazı ölçeği (7 bulgu: 0 yüksek / 3 orta / 4 düşük)

Bağlı bulgular: `kabuk-5`, `ekranA-19`, `ekranB-8`, `ilkel-16`, `ilkel-18`, `matris-1`, `kapsam-7`

**Hedef:** (1) Uygulama genelinde tek-nokta yazı ölçeği tavanı (MAX_FONT_SCALE=1.2, tokens.ts tek kaynak; allowFontScaling={false} ASLA — erişilebilirlik korunur); (2) kritik sayısal alanlar (KALAN/GEÇEN süre, bobin canlı okumaları, tablo hücreleri) numberOfLines=1 + adjustsFontSizeToFit ile HER ölçekte tek satırda okunur; (3) alt bar kısa etiketlerle 320-360 px'te ayırt edilir; (4) yan yana düğmeler, şifre kuralları ve güncelleme bandı büyük yazıda sütuna iner/sarılır; (5) jest 'Text varsayılanı' testi + pytest yapısal kapı ile regresyon kilidi; (6) cihazda yazı ölçeği 1.3 (ve 0.85) test listesi. Bulgular: matris-1, kabuk-5, ekranB-8, ilkel-16, ilkel-18, ekranA-19, kapsam-7. Seans akışı ve ACİL DURDUR erişimi hiçbir adımda değişmez.

**Tasarım kararları:**
- Tavan 1.2 (1.0 değil): kullanıcının erişilebilirlik tercihine kısmen saygı; 1.3'te bile en fazla %20 büyüme → mevcut düzenler sığar. Sahip 1.3'ü isterse sabit tek satır (tokens.ts MAX_FONT_SCALE) değişir.
- allowFontScaling={false} HİÇBİR yerde kullanılmaz (pytest kapısı bunu kilitler) — görme zorluğu olan operatör için ölçek tamamen kapatılmaz; yalnız tavanlanır.
- Global tavan injectFont() içinde, `flat.fontFamily` erken-dönüşünden ÖNCE uygulanır (ikon-fontlu Text'ler de kapsansın). Yerel `maxFontSizeMultiplier` verilmişse dokunulmaz (?? semantiği) → alt bar/rozet gibi sabit kutular 1 ile daha sıkı tavanlanabilir.
- Web'de maxFontSizeMultiplier/adjustsFontSizeToFit no-op (react-native-web filtreler) → PC/WebView2/LAN yüzeylerine etki yok; PC ölçek sorunu S1 kökünde.
- Kritik sayısal alanlarda mevcut proje deseni kullanılır: `numberOfLines={1} adjustsFontSizeToFit minimumFontScale` (btnStopText, GlobalEmergencyStop, KpiDashboard tablo zaten böyle).
- Alt bar: görünen metin kısa etiket (`short`), `accessibilityLabel` TAM etiket kalır → TalkBack ve mevcut `getByLabelText('Daha Fazla')` testleri bozulmaz; masaüstü kenar çubuğunda tam etiket sürer.
- Seans süresi biçimi 3 blokta 'h:mm:ss' yerine 'mm:ss' (65:30): klinik kapak 120 dk → en fazla 6 karakter; saatli biçim 320 px'te normal ölçekte bile taşıyordu. Sahip görsel onayı gerekir (bkz. açık sorular).
- rf() tabanına global Math.max koymak REDDEDİLDİ: typography.small 139 yerde kullanılıyor, rf(9)/rf(10) 17 yerde → sistemik boyut değişimi bu kökün kapsamı dışında; bant metnine hedefli taban (12 px) verilir.
- Seans detayı tablosu sabit sütun genişliğini korur (minWidth ile satır bazlı büyüme başlık/hücre hizasını bozar); yatay ScrollView zaten var → sütunlar biraz genişletilir + hücreler tek satır.
- MobileUpdateBanner'ın seans/bobin kapısı (`useDonanimCalisiyor`) ve erteleme mantığı DOKUNULMAZ; yalnız stil/düzen değişir.
- AppShell.bottomItem stiline S3 (dokunma hedefi) kökü de dokunacak → bu adım S3 ile aynı PR'da ya da S3'ten sonra rebase edilerek uygulanmalı (çakışma önlemi).

| # | Adım | Dosyalar | Değişiklik | Kapattığı | Doğrulama | Risk | Efor (s) |
|---|---|---|---|---|---|---|---|
| 1 | tokens.ts: MAX_FONT_SCALE tek-kaynak sabiti | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\theme\tokens.ts` | rf() tanımının altına dışa aktarılan sabit ekle: sistem yazı ölçeği tavanı. Yorumda NEDEN 1.2 (1.3'te alt bar/süre/tablo taşıyor, 1.0 erişilebilirliği keser) yazılsın. Başka dosya bu sayıyı ham yazmamalı. | `matris-1` | tsc --noEmit (pf: npm run typecheck); adım 9'daki jest testi sabiti import eder. | Yok (yalnız sabit ekleme). Geri alma: satırı sil. | 0.25 |
| 2 | fonts.ts injectFont(): varsayılan maxFontSizeMultiplier (global tavan) + dışa aktarım | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\theme\fonts.ts` | injectFont() içinde, `isInput`/Text tip kontrolünden hemen SONRA ve `if (flat.fontFamily) return props;` (satır 51) erken dönüşünden ÖNCE: props.maxFontSizeMultiplier == null ve allowFontScaling !== false ise props'u kopyalayıp MAX_FONT_SCALE ata. Sonraki tüm `return` ifadeleri bu yeni `out` nesnesini döndürsün. Fonks… | `matris-1`, `kabuk-5`, `ekranB-8`, `ilkel-16`, `ilkel-18`, `ekranA-19` | Adım 9 jest testi: injectFont(Text,{children:'x'}).maxFontSizeMultiplier === MAX_FONT_SCALE; TextInput (placeholder ile) de; yerel 1 verilince 1 kalır; fontFamily:'Ionicons' olsa da tavan var; View'a… | DÜŞÜK. Her Text'e bir prop daha kopyalanıyor (spread) — render maliyeti ihmal edilebilir (aynı fonksiyon zaten style flatten ediyor). ACİL DURDUR metni (Global… | 1.5 |
| 3 | AppShell: alt bar kısa etiketler + bottomLabel/title/rozet tavanı | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\AppShell.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\AppShell.logout.test.tsx` | (a) `interface NavItem`'a `short?: string`; allNavItems'ta ai:'Teşhis', ai_history:'Geçmiş', history:'Seanslar' (history hiçbir profilde ilk 4'te değil ama gelecekte sıralama değişirse hazır). (b) NavButton'a `text?: string` prop'u: görünen metin `text ?? label`, `accessibilityLabel={label}` TAM kalır. Alt barda `text… | `kabuk-5`, `matris-1` | AppShell.logout.test.tsx'e (mockDesktop=false, mockMode='veterinarian'/'pet_owner') yeni it: getByText('Teşhis') var, queryByText('Akıllı Teşhis') alt barda yok, getByLabelText('Akıllı Teşhis') BULUN… | ORTA-DÜŞÜK. Etiket metni ürün kararı (sahip 'Teşhis' yerine başka kelime isteyebilir) — metin sabiti tek satır. Rota/swipe/E-stop konumu (GlobalEmergencyStop b… | 2 |
| 4 | SessionProgressCard + CoilParameterPanel: kritik sayısal alanlar tek satır ve sığdırılır | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\SessionProgressCard.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\CoilParameterPanel.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\__tests__\SessionProgressCard.yaziOlcegi.test.tsx` | SessionProgressCard: (a) formatTime → her zaman 'mm:ss' (h>0 → '65:30'); saatli dal kaldırılır (klinik kapak 120 dk → en fazla 6 karakter). (b) GEÇEN ve KALAN timeValue Text'lerine `numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6} maxFontSizeMultiplier={1.1}` (btnStopText deseninin aynısı); 'Süresiz' de b… | `ekranB-8`, `matris-1` | Yeni jest: render(<SessionProgressCard isActive elapsedSec={3930} remainingSec={3270} durationSec={7200} .../>) → getByText('65:30') ve getByText('54:30'); KALAN Text props: numberOfLines===1, adjust… | HASTA GÜVENLİĞİ SINIRINDA: KALAN süresi ve ACİL DURDUR aynı kartta. Değişiklik yalnız Text prop'u + stil; buton ağacı, onEmergencyStop, disabled durumu DEĞİŞME… | 2.5 |
| 5 | Button etiketi sığdırma + AiHub PetOwnerAiScreen düğme satırları compact'ta sütun | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\Button.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\AiHubScreen.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\ui\__tests__\Button.test.tsx` | Button.tsx: label Text'ine `adjustsFontSizeToFit minimumFontScale={0.8}` (numberOfLines=1 zaten var; global 1.2 tavanı adım 2'den gelir); styles.content'e `flexShrink: 1, minWidth: 0`; styles.label'a `flexShrink: 1`. AiHubScreen.tsx: PetOwnerAiScreen (satır 358'den başlayan bileşen — 539 ve 749 satırlarını içeren fonk… | `ilkel-16` | Button.test.tsx'e it: render(<Button label='Analiz Ediliyor...' />) → Text props numberOfLines===1 && adjustsFontSizeToFit===true && minimumFontScale===0.8; mevcut çift-tık testleri yeşil. aiHubAccor… | DÜŞÜK. adjustsFontSizeToFit yalnız native; web'de ellipsis sürer (PC geniş). 'Seans Başlat' gibi kritik etiketler daha okunur olur. Geri alma: iki dosyada ilgi… | 1.5 |
| 6 | SessionDetailModal bobin tablosu: hücreler tek satır, sütunlar biraz geniş | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\SessionDetailModal.tsx` | Tüm th ve td Text'lerine `numberOfLines={1} maxFontSizeMultiplier={1.1}`; td'lere ayrıca `adjustsFontSizeToFit minimumFontScale={0.75}` (KpiDashboard tablo deseni). Tekrarı azaltmak için dosya başında `const HUCRE = { numberOfLines: 1, maxFontSizeMultiplier: 1.1 } as const;` ve `{...HUCRE}`. Sütun genişlikleri: colTim… | `ilkel-18` | Yeni/mevcut jest (SessionDetailModal için test yok → küçük test: apiGet mock ile 2 coilRun render, 'Başlangıç' Text props.numberOfLines===1). Cihaz: Seans Geçmişi → bir seans detayı, ölçek 1.3, 360 p… | DÜŞÜK (salt-okunur tablo). Geri alma: dosya. | 1 |
| 7 | AuthScreen şifre kuralları: esnek hücre (büyük yazıda tek sütun) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\screens\AuthScreen.tsx` | styles.rule: `width: '48%'` → `flexBasis: '48%', flexGrow: 1, minWidth: rs(130)`; styles.ruleText'e `flexShrink: 1`. Rule() bileşeni ve checks mantığı değişmez. | `ekranA-19` | npm run typecheck; Edge headless (denetimin CDP yöntemi) 320×568 web export'ta Kayıt formu ekran görüntüsü: 4 kural 2×2 hizalı; cihazda ölçek 1.3 + 320 px → kurallar tek sütuna iner, sarma yok. | DÜŞÜK. Geri alma: 2 satır. | 0.5 |
| 8 | MobileUpdateBanner: 12 px taban + dar telefonda sütun düzeni | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\MobileUpdateBanner.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\components\domain\__tests__\MobileUpdateBanner.test.tsx` | `const { width } = useResponsive(); const dar = width < 360;`. Yapı: bant → [üst satır: ikon + metin bloğu] + [eylemler: Güncelle/Kur + X]; dar ise bant `flexDirection:'column', alignItems:'stretch'` ve eylemler satırı altta sağa yaslı (Güncelle düğmesi `flex:1` tam genişlik). styles.alt `fontSize: Math.max(typography… | `kapsam-7` | MobileUpdateBanner.test.tsx mevcut testler (getByLabelText ile düğme) yeşil; yeni it: jest.mock('@/hooks/useResponsive') width:320 → bant kökünün style'ında flexDirection 'column'; width:390 → 'row'.… | DÜŞÜK. Kapı mantığı değişmez (HASTA GÜVENLİĞİ: seansta gizli kuralı test ediliyor). Geri alma: dosya. | 1.5 |
| 9 | Kilitler: jest 'Text varsayılanı' testi + pytest yapısal kapı (mutasyonla KIRMIZI kanıtı) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pf\src\theme\__tests__\fonts.yaziOlcegi.test.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\tests\test_arayuz_yazi_olcegi_kapisi.py` | Jest: injectFont saf-fonksiyon testleri (adım 2'deki 5 durum) + applyGlobalInter() sonrası render(<Text>) uçtan uca. Pytest (tests.yml'de `pytest tests` ile koşar): (1) fonts.ts'de 'maxFontSizeMultiplier' ataması 'if (flat.fontFamily) return' konumundan ÖNCE ve 'MAX_FONT_SCALE' tokens'tan import ediliyor; (2) pf/src'd… | `matris-1`, `ekranB-8`, `kabuk-5` | pf: `npm test -- fonts.yaziOlcegi` yeşil; kök: `pytest tests/test_arayuz_yazi_olcegi_kapisi.py -v` yeşil; her iki kapı için mutasyon koşusu KIRMIZI kanıtı commit mesajına not edilir (bellek: 'Kapı KI… | Yok (test). Python kapısı UTF-8 okumalı (embedded python cp1254 tuzağı). Geri alma: test dosyalarını sil. | 1.5 |
| 10 | Cihaz doğrulaması (yazı ölçeği 1.3 ve 0.85) + ekran görüntüsü seti + rapor güncellemesi | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\docs\responsive-denetim-2026-09-04.md` | cihaz_testi listesini 320×568 AVD + 360 px gerçek telefon + 430 px telefonda Android 'Yazı boyutu' en büyük (≈1.3) ve en küçük (0.85) ile koş; 1.0 referans görüntüleriyle yan yana kaydet (docs/responsive/S6/*.png). Rapor §S6'ya 'kapatıldı' + kalan notlar (ör. web tarayıcı zoom S1'e ait). | `matris-1`, `kabuk-5`, `ekranB-8`, `ilkel-16`, `ilkel-18`, `ekranA-19`, `kapsam-7` | Aşağıdaki cihaz_testi listesinin tamamı geçer; ACİL DURDUR her ekranda görünür ve tek dokunuşla çalışır (PEMF_SIMULATE=1). | Yok. APK build backend build ile paralel koşmaz (bellek). | 2 |

<details><summary>Kod taslakları</summary>

**1. tokens.ts: MAX_FONT_SCALE tek-kaynak sabiti**

```
// ── S6: SİSTEM YAZI ÖLÇEĞİ TAVANI ───────────────────────────────────────
// Android 'Yazı boyutu' 1.3'te alt bar etiketi, KALAN süresi, bobin okumaları ve tablo
// hücreleri taşıyordu. Ölçek KAPATILMAZ (erişilebilirlik), yalnız tavanlanır. Tek kaynak:
// fonts.ts injectFont() her Text/TextInput'a bunu varsayılan olarak verir.
export const MAX_FONT_SCALE = 1.2;
```

**2. fonts.ts injectFont(): varsayılan maxFontSizeMultiplier (global tavan) + dışa aktarım**

```
import { MAX_FONT_SCALE } from "./tokens";

export function injectFont(type: any, props: any): any {
  if (!props) return props;
  const isInput = type === TextInput || "placeholder" in props;
  if (type !== Text && !isInput) return props;
  // S6: sistem yazı ölçeği tavanı — fontFamily erken-dönüşünden ÖNCE (ikon fontlu Text'ler de kapsansın).
  // Yerel değer verilmişse (alt bar: 1) dokunma; allowFontScaling=false ise anlamsız.
  let out = props;
  if (out.maxFontSizeMultiplier == null && out.allowFontScaling !== false)
    out = { ...out, maxFontSizeMultiplier: MAX_FONT_SCALE };
  const flat: any = { ...(StyleSheet.flatten(out.style) || {}) };
  if (flat.fontFamily) return out;
  const w = String(flat.fontWeight ?? "400");
  flat.fontFamily = FAMILY_BY_WEIGHT[w] || FAMILY_BY_WEIGHT["400"];
  delete flat.fontWeight;
  if (flat.fontStyle === "italic") delete flat.fontStyle;
  return { ...out, style: flat };
}
```

**3. AppShell: alt bar kısa etiketler + bottomLabel/title/rozet tavanı**

```
interface NavItem { key: RouteKey; label: string; short?: string; icon: LucideIcon; }
{ key: "ai", label: "Akıllı Teşhis", short: "Teşhis", icon: BrainCircuit },
{ key: "ai_history", label: "AI Geçmişi", short: "Geçmiş", icon: ClipboardList },
// NavButton
function NavButton({ label, text, icon: Icon, active, compact, danger, onPress }: { label: string; text?: string; ... }) {
  ...
  <Text style={[...]} numberOfLines={1} maxFontSizeMultiplier={compact ? 1 : undefined}>{text ?? label}</Text>
// alt bar çağrısı
<NavButton key={item.key} label={item.label} text={item.short} ... />
// başlık
<Text style={styles.title} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.75} maxFontSizeMultiplier={1.1}>{title}</Text>
// rozet
notifBadge: { ..., minWidth: rs(16), minHeight: rs(16), ... }
<Text style={styles.notifBadgeText} maxFontSizeMultiplier={1}>…</Text>
```

**4. SessionProgressCard + CoilParameterPanel: kritik sayısal alanlar tek satır ve sığdırılır**

```
function formatTime(sec: number): string {
  // S6: 3 blokta 'h:mm:ss' 320 px'te normal ölçekte bile taşıyordu → 'mm:ss' (65:30). Klinik kapak 120 dk.
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
<Text style={[styles.timeValue, { color: ... }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6} maxFontSizeMultiplier={1.1}>
  {indefinite ? "Süresiz" : formatTime(remainingSec)}
</Text>
timeBlock: { flex: 1, minWidth: 0 },
timeBlockCenter: { flex: 0.6, alignItems: "center" },
// CoilParameterPanel.Reading
<Text style={[styles.readingValue, !active && { color: "#475569" }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>{value}</Text>
reading: { flex: 1, minWidth: 0, alignItems: "center" },
```

**5. Button etiketi sığdırma + AiHub PetOwnerAiScreen düğme satırları compact'ta sütun**

```
// Button.tsx
<Text
  style={[styles.label, LABEL[size], variant === "ghost" && styles.ghostLabel, variant === "secondary" && styles.secondaryLabel]}
  numberOfLines={1}
  adjustsFontSizeToFit
  minimumFontScale={0.8}
>
content: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, flexShrink: 1, minWidth: 0 },
label: { color: colors.white, fontWeight: "700", flexShrink: 1 },
// AiHubScreen.tsx (PetOwnerAiScreen)
const { isCompact } = useResponsive();
<View style={[{ flexDirection: "row", gap: spacing.md }, isCompact && { flexDirection: "column" }]}>
  <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
```

**6. SessionDetailModal bobin tablosu: hücreler tek satır, sütunlar biraz geniş**

```
const HUCRE = { numberOfLines: 1, maxFontSizeMultiplier: 1.1 } as const;
<Text style={[styles.th, styles.colTime]} {...HUCRE}>Başlangıç</Text>
<Text style={[styles.td, styles.colNum]} {...HUCRE} adjustsFontSizeToFit minimumFontScale={0.75}>
  {run.frequency_hz != null ? `${run.frequency_hz} Hz` : "—"}
</Text>
colTime: { width: rs(100) }, colNum: { width: rs(84) }, colHw: { width: rs(76) },
```

**7. AuthScreen şifre kuralları: esnek hücre (büyük yazıda tek sütun)**

```
rule: { flexDirection: "row", alignItems: "center", gap: rs(6), flexBasis: "48%", flexGrow: 1, minWidth: rs(130) },
ruleText: { color: colors.textMuted, fontSize: typography.caption, flexShrink: 1 },
```

**8. MobileUpdateBanner: 12 px taban + dar telefonda sütun düzeni**

```
const { width } = useResponsive();
const dar = width < 360;
<View style={[styles.bant, dar && styles.bantDar]}>
  <View style={styles.ust}>
    <Download color={colors.primary} size={rs(16)} />
    <View style={{ flex: 1 }}>{/* baslik + alt (değişmedi) */}</View>
  </View>
  {oran === null ? (
    <View style={[styles.eylemler, dar && styles.eylemlerDar]}>{/* Güncelle/Kur + X (değişmedi) */}</View>
  ) : null}
</View>
// stiller
bant: { flexDirection: "row", alignItems: "center", gap: spacing.sm, ... },
bantDar: { flexDirection: "column", alignItems: "stretch" },
ust: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flex: 1 },
eylemler: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
eylemlerDar: { justifyContent: "flex-end", marginTop: spacing.xs },
alt: { color: colors.textMuted, fontSize: Math.max(typography.caption, 12), marginTop: rs(2) },
btnText: { color: "#04121F", fontWeight: "800", fontSize: typography.caption },
```

**9. Kilitler: jest 'Text varsayılanı' testi + pytest yapısal kapı (mutasyonla KIRMIZI kanıtı)**

```
// fonts.yaziOlcegi.test.tsx
import { Text, TextInput, View } from "react-native";
import { render } from "@testing-library/react-native";
import { injectFont, applyGlobalInter } from "@/theme/fonts";
import { MAX_FONT_SCALE } from "@/theme/tokens";
it("Text varsayılanı: maxFontSizeMultiplier = MAX_FONT_SCALE (yerel değer korunur, ikon fontu kapsanır)", () => {
  expect(injectFont(Text, { children: "x" }).maxFontSizeMultiplier).toBe(MAX_FONT_SCALE);
  expect(injectFont(TextInput, { placeholder: "p" }).maxFontSizeMultiplier).toBe(MAX_FONT_SCALE);
  expect(injectFont(Text, { maxFontSizeMultiplier: 1, children: "x" }).maxFontSizeMultiplier).toBe(1);
  expect(injectFont(Text, { style: { fontFamily: "Ionicons" }, children: "x" }).maxFontSizeMultiplier).toBe(MAX_FONT_SCALE);
  expect(injectFont(View, { children: null }).maxFontSizeMultiplier).toBeUndefined();
});
it("uçtan uca: applyGlobalInter sonrası render edilen Text tavanlı", () => {
  applyGlobalInter();
  expect(render(<Text>x</Text>).toJSON()!.props.maxFontSizeMultiplier).toBe(MAX_FONT_SCALE);
});
# test_arayuz_yazi_olcegi_kapisi.py
_PF = Path(__file__).resolve().parent.parent / "pf" / "src"
def test_injectfont_tavani_fontfamily_donusunden_once():
    s = (_PF / "theme/fonts.ts").read_text(encoding="utf-8")
    assert "MAX_FONT_SCALE" in s and s.index("maxFontSizeMultiplier") < s.index("if (flat.fontFamily) return")
def test_allowfontscaling_false_yasak():
    kotu = [p for p in _PF.rglob("*.tsx") if "allowFontScaling={false}" in p.read_text(encoding="utf-8")]
    assert not kotu, kotu
@pytest.mark.parametrize("dosya,capa", [("components/domain/SessionProgressCard.tsx", 'formatTime(remainingSec)}'), ("components/domain/CoilParameterPanel.tsx", "{value}</Text>")])
def test_kritik_sayisal_alan_tek_satir(dosya, capa):
    s = (_PF / dosya).read_text(encoding="utf-8"); i = s.index(capa); acilis = s.rfind("<Text", 0, i)
    assert "numberOfLines={1}" in s[acilis:i] and "adjustsFontSizeToFit" in s[acilis:i]
```

</details>

**Bağımlılıklar:** Adım 2 → Adım 1 (MAX_FONT_SCALE import).; Adım 9 → Adım 2, 3, 4 (çıpaları o değişikliklere pinler); önce yazılıp KIRMIZI görülmesi de kabul (bellek: mutasyonu önce yaz).; Adım 3 (AppShell.bottomItem) ↔ S3 kökü (dokunma hedefi rs(44)) aynı stile dokunur → aynı PR ya da S3 sonrası rebase.; Adım 3 başlık (headerLeft) ↔ kabuk-3 bulgusu (S? üst bar sıkışması) — headerLeft düzeltmesi title'ın genişliğini artırır; sırasız uygulanabilir, çakışma yalnız aynı satırlar.; Adım 8 MobileUpdateBanner testleri Platform.OS='android' mock'una bağlı (mevcut test dosyası zaten yapıyor).; Web export (PC/WebView2) bu kökten ETKİLENMEZ; PC ölçek sorunları S1 (ölçek tavanı) kökünde.; APK build (adım 10) backend EXE build ile paralel koşmaz (bellek: pemf-yayin-2026-08-27-gece).

**Kilitler:**
- jest: pf/src/theme/__tests__/fonts.yaziOlcegi.test.tsx — injectFont saf fonksiyon (5 durum) + applyGlobalInter uçtan uca; frontend.yml `npm test` ile CI'da koşar.
- jest: AppShell.logout.test.tsx'e kısa etiket + a11y tam etiket + bottomLabel maxFontSizeMultiplier===1 testi.
- jest: SessionProgressCard.yaziOlcegi.test.tsx — 'mm:ss' biçimi, KALAN Text prop'ları, <60 sn kırmızı renk KORUNUR, 'Süresiz'.
- jest: Button.test.tsx — label Text adjustsFontSizeToFit/minimumFontScale.
- jest: MobileUpdateBanner.test.tsx — dar (320) sütun / normal satır; seansta gizli kuralı mevcut testte sürer.
- pytest: tests/test_arayuz_yazi_olcegi_kapisi.py — (1) tavan fontFamily-dönüşünden önce + MAX_FONT_SCALE tek kaynak, (2) allowFontScaling={false} YASAK, (3) kritik sayısal Text çıpaları numberOfLines={1}+adjustsFontSizeToFit; tests.yml ile CI'da koşar. Her kapı için mutasyon KIRMIZI kanıtı.
- Var olan hasta-güvenliği testleri regresyon bekçisi: durdurmaTuruParalel, CoilDurationHonesty, AppShell.logout (E-stop teyidi), crashGuards (Ana Ekran E-stop erişimi).

**Cihaz testi:**
- Hazırlık: Android Ayarlar → Ekran → Yazı boyutu = en büyük (≈1.3); cihazlar: 320×568 AVD, 360 px gerçek telefon, 430 px telefon; backend PEMF_SIMULATE=1.
- Alt bar (vet + pet_owner profili): 5 slotta hiçbir etiket '…' değil; 'Teşhis'/'Geçmiş' kısa etiketleri; TalkBack ile odaklanınca 'Akıllı Teşhis' TAM okunuyor.
- Üst bar: 'Seans Kontrol Merkezi' başlığı 375 px'te tek satır; bildirim rozeti (5 ve 99+) rakamı dikeyde kesik değil.
- Kontrol → seans başlat (süre 120 dk, sanal donanım): GEÇEN/%/KALAN tek satır, üst üste binme yok; 65 dk geçince '65:30' biçimi; KALAN <60 sn kırmızı ve okunur; 'Durdur' ve 'ACİL DURDUR' butonları görünür, ACİL DURDUR tek dokunuşla bobinleri durduruyor (kayan GlobalEmergencyStop dahil).
- Bobin kartı canlı okumaları ('0.000' A, mT, Hz, DC%) 320 px'te 4 hücrede sığıyor.
- Seans Geçmişi → seans detayı → Bobin Çalışmaları tablosu: satır yükseklikleri eşit, hücreler tek satır, yatay kaydırma çalışıyor.
- Kayıt formu (320 px): 4 şifre kuralı tek sütuna iniyor, 'karakter' sarmıyor; Giriş Yap düğmesi okunur.
- AI Hub pet_owner: fotoğraf seçildikten sonra 'Yeni Fotoğraf'/'Teşhis Et' ve ses sekmesinde 'Kaydet'/'Ses Yükle' alt alta, etiketler tam; 'Analiz Ediliyor...' kırpılmıyor.
- Güncelleme bandı (staging manifest ile yeni sürüm): 320 px'te metin ≥12 px, düğmeler alt satırda; seans/bobin çalışırken bant görünmüyor.
- Yazı boyutu = en küçük (0.85): güncelleme bandı ve typography.small metinler hâlâ okunur (≥ ~10 px); alt bar etiketleri değişmiyor (tavan 1).
- Kontrol: Yazı boyutu 1.0 ile 1.3 ekran görüntüleri yan yana docs/responsive/S6/ altına; masaüstü (PC WebView2) ve LAN tarayıcıda görünüm değişmediği doğrulanır (web no-op).

**Açık sorular (sahip kararı):**
- Tavan 1.2 mi 1.3 mü? (1.3 seçilirse alt bar/rozet yerel tavanları 1 kalır ama süre/tablo sığdırma minimumFontScale'e daha çok yaslanır — erişilebilirlik vs. düzen dengesi; sahip kararı.)
- Alt bar kısa etiketleri: 'Teşhis' (Akıllı Teşhis), 'Geçmiş' (AI Geçmişi) kelimeleri sahip onayı gerektirir; alternatif: width<360'ta ikon-only alt bar (etiket gizli) — tercih edilmedi çünkü 4 ikon tek başına ayırt edilmez.
- Seans süresi biçimi 'mm:ss' (65:30) — operatör 'h:mm:ss'e alışıksa alternatif: yalnız isCompact'ta mm:ss, geniş ekranda h:mm:ss (SessionProgressCard'a useResponsive eklenir, +0.5 saat).
- MobileUpdateBanner dar eşiği 360 px (rapor önerisi) — 375 px'te de düğmeler dar kalıyorsa eşik isCompact (480) yapılabilir; cihaz testinde karar.
- TextInput'larda da tavan 1.2 uygulanacak (injectFont ikisini de yakalıyor) — form girdilerinde büyük yazı isteniyorsa TextInput hariç tutulabilir (tek koşul satırı).

**Toplam efor:** ~14.25 saat

### S7 — Grafik ve kamera katmanları (9 bulgu: 1 yüksek / 6 orta / 2 düşük)

Bağlı bulgular: `ekranB-5`, `ekranB-6`, `ekranB-11`, `ekranC-2`, `ekranC-3`, `aihub-1`, `aihub-2`, `aihub-3`, `aihub-11`

**Hedef:** Her grafik/kamera katmanı GERÇEK ölçülen genişlikten (onLayout) ve gerçek kare oranından (backend image_w/image_h) türesin; web canvas DPR ile keskin; önizleme + overlay AYNI piksel kutusunda AYNI oran → AI Pro/CatOrgan organ işaretleri canlı görüntüye birebir otursun; çubuk/lejant/rozet 320 px'te okunur kalsın. Hasta güvenliği değişmezleri (ACİL DURDUR erişimi, seans akışı, AiProPanel hazırlık/kare-akışı kapıları) DOKUNULMADAN.

**Tasarım kararları:**
- Ölçüm deseni: KpiDashboard.chartInner'daki `onLayout → useState(width)` deseni tek standart; yeni bağımlılık/hook yok. SVG/canvas boyutu = ölçülen px, viewBox = aynı px (ölçek 1:1) → fontSize rf() doğrudan px olur.
- Kare oranı KAYNAĞI = backend. ai_router.py yanıtları (ai_pro/frame, vision/cat_organ, vision/landmark, vision/segmentation, vision/thermal) ve `ai_vision` WS yayını yalnız image_base64 taşıyor; boyut (oh, ow) kodda hesaplanıp ATILIYOR. Yanıtlara `image_w`/`image_h` (WS'de `imageW`/`imageH`) EKLENİR (yalnız-ek, geriye uyumlu). İstemci: alan yoksa `Image.getSize(dataUri)` (xaiIsiHaritasiBoyut testi zaten mock'luyor) ile geri düşer; o da yoksa varsayılan portre 3/4, yatay 4/3. takePictureAsync'in width/height'ı KULLANILMAZ (Android'de EXIF-rotasyon öncesi/sonrası belirsiz; cv2.imdecode EXIF'i yok sayar).
- Kamera kutusu: `aspectRatio` + `maxHeight` KOMBİNASYONU KULLANILMAZ (maxHeight kırpınca genişlik %100 kalır, oran yine bozulur). Bunun yerine ölçülen kutu genişliğinden AÇIK px kutu hesaplanır: kutuH = min(kutuW/oran, ekranH*0.55[AiHub]/0.5[AiPro]); kutuW2 = kutuH*oran; kamera+overlay `{width:kutuW2, height:kutuH, alignSelf:'center'}` → cover ≡ contain ≡ tam dolum. Android CameraView'a `ratio="4:3"` (expo-camera 56: FIT_CENTER'a geçer, ResolutionSelector 4:3) → önizleme akışı da kareyle aynı oranda. iOS resizeAspectFill ve web objectFit:cover kutu tam oranlı olduğu için kırpmaz.
- STATİK (canlı olmayan) modda imagePreviewContainer rs(300) sabit KALIR: B2 ısı-haritası kilidi (xaiIsiHaritasiBoyut.test) analiz görseli ile xaiStage'in aynı rs(300) çerçevede olmasını ölçüyor; yalnız CANLI modda kutu oranlı olur.
- Overlay resizeMode 'contain' KALIR (sunucu işaretlerini asla kırpma); kutu tam oranlı olduğu için letterbox oluşmaz. Alternatif 'canlı modda CameraView'ı gizle' REDDEDİLDİ: 3,5 sn kare aralığında operatör kadraj için canlı önizlemeye muhtaç.
- Web canvas: piksel boyutu width*dpr, CSS boyutu width px (100% değil), ctx.setTransform(dpr,0,0,dpr,0,0); çizim mantığı değişmez. SensorMonitor'daki `Math.min(chartW, 1200)` kaldırılır (container maxWidth rs(1200) zaten sınırlıyor).
- Saf hesaplar dışa alınır ve birim testlenir: `hesaplaPad(width, showTemp)`, `canvasBoyutla(canvas, ctx, w, h, dpr)`, `kameraKutusu(kutuW, oran, ekranH, tavanOran)` → jest'te DOM/canvas gerekmez; bileşen testleri RNTL ile onLayout fireEvent.
- Çubuk dolguları yüzdeyle (`height: '76%'`) — soundBarFill'in width-yüzde deseniyle aynı; en küçük yazı tabanı typography.small (rf(11)); güvenlik rozeti tam-genişlik şerit.
- chart-kit PieChart lejantı kapatılır (hasLegend={false}); lejant RN View ile grafiğin ALTINA flexWrap satırı olarak çizilir (chart-kit'in SVG-içi x=width/2.5 sabitinden kurtuluş). BarChart style.paddingRight dar kartta rs(24).
- Kapılar: (1) jest bileşen/birim testleri birincil; (2) tests/test_responsive_grafik_kapisi.py — capraz.kaynak_yolu ile pf/src'ye çıpalı kaynak-regex kapısı (yoksa ATLA, PEMF_CAPRAZ_KAYNAK_ZORUNLU=1'de düşer), çıpalar GERÇEK ifadeye pinli (ör. `const width = 720` yok; `fontSize: rf(9|10)` yok; dBarFill `%`); (3) backend pytest image_w/h; (4) cihaz testi zorunlu (kamera hizası tıbbi karar ekranı).

| # | Adım | Dosyalar | Değişiklik | Kapattığı | Doğrulama | Risk | Efor (s) |
|---|---|---|---|---|---|---|---|
| 1 | Seans Detayı sıcaklık grafiği: viewBox'ı ölçülen genişliğe eşitle | `pf/src/components/domain/SessionDetailModal.tsx (TempChart, satır 406-441 ve 467/487/498; styles.chartWrap 638)`, `pf/src/components/domain/__tests__/SessionDetailModal.tempChart.test.tsx (YENİ)` | TempChart içinde `const width = 720; const height = 260;` sabitlerini kaldır. chartWrap'a `onLayout={(e)=>setW(e.nativeEvent.layout.width)}` + `testID="seans-sicaklik-grafigi"` ekle; `const [w, setW] = useState(0)`; w>0 iken Svg'yi `width={w} height={h} viewBox={`0 0 ${w} ${h}`}` ile kur (h = rs(240)). `narrow = w < 4… | `ekranC-3` | jest (RNTL): apiGet mock'u temp noktalı seans döndürür; `fireEvent(getByTestId('seans-sicaklik-grafigi'),'layout',{nativeEvent:{layout:{width:300,height:0}}})` → `UNSAFE_getByType(Svg).props.width===… | Düşük — salt görsel bileşen, seans akışıyla ilgisi yok. Geri alma: dosyayı önceki commit'e çevir (tek dosya). Not: ilk render'da w=0 → Svg çizilmez (KpiDashboa… | 2 |
| 2 | RealtimeChart: PAD'i genişlikten türet + web canvas DPR + 1200 kapağını kaldır + dar ekranda yatay kaydırma | `pf/src/components/visual/RealtimeChart.tsx (draw() 50-54 ve 240-245; NativeRealtimeChart 254-256; SvgText 345/350)`, `pf/src/components/visual/chartLayout.ts (YENİ: hesaplaPad, canvasBoyutla)`, `pf/src/screens/SensorMonitorScreen.tsx (satır 111-121 chartArea; 118 `Math.min(chartW,1200)`)`, `pf/src/components/visual/__tests__/chartLayout.test.ts (YENİ)` | (a) chartLayout.ts: `export function hesaplaPad(width:number, showTemp:boolean){ const narrow = width < 400; return { top: 20, bottom: 40, left: narrow ? 44 : 60, right: showTemp ? (narrow ? 44 : 60) : 12 }; }` ve `export function canvasBoyutla(canvas:{width:number;height:number}, ctx:{setTransform:Function}, w:number… | `ekranB-5`, `ekranB-6` | jest birim: hesaplaPad(320,false)→{left:44,right:12}, hesaplaPad(800,true)→{60,60}; canvasBoyutla sahte canvas {width:0,height:0} + ctx.setTransform jest.fn, dpr=2, w=600 → canvas.width 1200, setTran… | Orta-düşük — canlı grafik yalnız görselleştirme; seans kontrolü/E-stop bu ekranda AppShell'de, dokunulmuyor. Yatay ScrollView dış dikey ScrollView içinde: RN i… | 3 |
| 3 | KPI: pasta lejantını RN View'a taşı, bar paddingRight'ı daralt, bobin tablosunu sağa hizala | `pf/src/screens/KpiDashboardScreen.tsx (chartsSection 148-183; styles 292-319)`, `pf/src/screens/__tests__/kpiGrafikLejant.test.tsx (YENİ)` | (a) PieChart: `hasLegend={false}`, `paddingLeft={String(Math.max(0, Math.round(chartW/2 - rs(220)/2.5)))}` (chart-kit: pie merkezi x = width/4+paddingLeft... — ölçüp ortala), `center={[0,0]}`, `absolute` kaldır. Altına `<View style={styles.pieLegend}>{pieData.map(d => <View style={styles.pieLegendItem}><View style={[s… | `ekranC-2`, `ekranC-15` | jest (RNTL, kpiSicaklikDurustlugu.test mock deseni): apiGet kpi {modeDistribution:{'Yara İyileşmesi':3,'Ağrı':2}} → chartInner onLayout width 230 → `UNSAFE_getByType(PieChart).props.hasLegend===false… | Düşük — rapor ekranı, seans akışı yok. chart-kit PieChart merkez hesabı sürüme bağlı (6.12.3 dist/PieChart.js: G x=width/4+15+paddingLeft?) — ekran görüntüsüyl… | 3 |
| 4 | Backend: AI kare yanıtlarına gerçek boyut (image_w/image_h) ekle | `servers/ai_router.py (ai_pro/frame ~1853-1862; hazırlık önizleme yayını ~1031-1045; seans yayını ~1268-1285; /vision/cat_organ ~3040-3075; /vision/landmark ~527-535; /vision/segmentation 1941; /vision/thermal 2034)`, `tests/test_ai_kare_boyutu.py (YENİ)`, `tests/test_ai_pro_hazirlik_onizleme_yayini.py (genişlet)` | Her yanıtta `oh, ow` zaten hesaplanıyor (küçültme için). Küçültme SONRASI boyutu yanıta ekle: `"image_w": int(img_out.shape[1]), "image_h": int(img_out.shape[0])` (ai_pro/frame, cat_organ, landmark, segmentation, thermal — her birinde encode edilen dizinin shape'i). WS `ai_vision` data'sına `"imageW": ov.shape[1], "im… | `aihub-1`, `aihub-2` | pytest: test_ai_kare_boyutu.py — test_ai_pro_sahiplik_kare.py'deki `owned` fixture ve 1280×960 sahte kare ile /ai/ai_pro/frame → `image_w`/`image_h` int ve base64 decode edilen JPEG boyutuna EŞİT (PI… | Düşük — ek alan; hiçbir mevcut istemci okumuyor. AI Pro seans döngüsü (_ai_pro_loop) yayın gövdesine 2 int ekler, zamanlama etkisi yok. Mikroservis yolunda ek … | 2 |
| 5 | Kamera kutusu oran kilidi: AiHub VisionModule + CatOrganModule (canlı mod) | `pf/src/screens/AiHubScreen.tsx (VisionModule 1436-1485; CatOrganModule 3523-3543; styles 3661/3673-3677)`, `pf/src/utils/kameraKutusu.ts (YENİ: kareOrani, kameraKutusu)`, `pf/src/utils/__tests__/kameraKutusu.test.ts (YENİ)`, `pf/src/screens/__tests__/catOrganCanliKalinti.test.tsx (genişlet)` | (a) kameraKutusu.ts: `kareOrani(r:{image_w?:number;image_h?:number}|null, portre:boolean)` → r.image_w&&r.image_h ? w/h : (portre ? 3/4 : 4/3); `kameraKutusu(kutuW, oran, ekranH, tavan=0.55)` → `{ const h = Math.min(kutuW/oran, Math.round(ekranH*tavan)); return { width: Math.round(h*oran), height: Math.round(h) }; }`.… | `aihub-1` | jest birim: kameraKutusu(335, 3/4, 800) → {width:335,height:447}; tavan: kameraKutusu(1274, 4/3, 700) → height 385, width 513; kareOrani({image_w:1280,image_h:960},true)=4/3, kareOrani(null,true)=0.7… | ORTA — tıbbi karar ekranı (organ konumu). Yanlış oran = eskisiyle aynı hizasızlık, daha kötü değil; ama regresyon ihtimali: Android'de `ratio="4:3"` çekilen fo… | 4 |
| 6 | AI Pro paneli camBox oran kilidi + flipBtn 44 px | `pf/src/components/domain/AiProPanel.tsx (camBox JSX 723-760; styles 891-903)`, `pf/src/components/domain/__tests__/AiProPanelKutuOrani.test.tsx (YENİ)` | `useResponsive` import et (`width`, `height`). `const [kutuW,setKutuW]=useState(0)`; oran: web → `kareOrani({image_w:(v as any)?.imageW, image_h:(v as any)?.imageH}, false)`; mobil → `kareOrani(mobileResult, height > width)`; boyut = kameraKutusu(kutuW, oran, height, 0.5) ve `height` üst sınırı `Math.min(..., rs(420))… | `aihub-2` | jest (AiProPanelB1 mock seti, mobil): start → hazırlık → fetch /frame yanıtı {image_base64, image_w:960, image_h:1280} → camBox onLayout 300 → cam sarmalayıcı flatten(style) {width:300,height:400}; o… | ORTA-YÜKSEK dosya (seans başlat/durdur, kare akışı, E-stop ile aynı ekran). Değişiklik YALNIZ stil/sarmalayıcı View; `start/stop/capture` mantığı, ownedRef, in… | 3 |
| 7 | Kamera hizası CİHAZ doğrulaması (tıbbi karar kapısı) | `docs/responsive-denetim-2026-09-04.md (§S7 cihaz doğrulama notu — ekran görüntüleri)`, `pf/src/screens/AiHubScreen.tsx (yalnız ölçüm sonucu gerektirirse tavan/oran ince ayarı)` | Kod değişikliği yok (gerekirse ince ayar). Protokol: A4'e basılı kedi fotoğrafı + kenarlarında 4 ArUco/QR işaret; AI Pro (Kontrol) ve AI Hub → Kedi Organ canlı mod. Sunucu overlay'i karenin kendisini içerdiğinden 'hayalet' kenarlar canlı görüntüyle çakışmalı: overlay opacity 0.8'de kâğıt kenarı ile canlı kâğıt kenarı … | `aihub-1`, `aihub-2` | Cihaz testi tablosu (6 sınıf × 2 ekran) ekran görüntüleriyle; kayma ölçümü (ekran görüntüsünde piksel). Başarısızsa: Android'de `pictureSize` ile önizleme/çekim çözünürlüğü eşitle veya image_w/h ile … | Kamera kütüphanesi davranışı cihaza göre değişir (ölçmeden bilinemez); bu adım plan içindeki tek 'ölç-sonra-karar' noktasıdır. Seans: testler HAZIRLIK modunda … | 3 |
| 8 | Fantom/Petri D1–D7 duty çubukları: yüzde dolgu + okunur etiket | `pf/src/screens/AiHubScreen.tsx (1933, 2164 dBarFill; 3721-3723 stiller)`, `pf/src/screens/__tests__/dutyCubuguOrani.test.tsx (YENİ)` | İki yerde `height: Math.max(2, Math.round((min(max(d,0),0.5)/0.5)*26))` → `height: `${Math.max(4, Math.round(Math.min(Math.max(d,0),0.5)/0.5*100))}%`` (soundBarFill width-yüzde deseni). Tekrarı önlemek için `const dutyYuzde = (d:number) => `${Math.max(4, Math.round(Math.min(Math.max(d,0),0.5)/0.5*100))}%`` modül-üstü … | `aihub-3` | jest (xaiIsiHaritasiBoyut mock seti): Fantom modülü → fetch {tumors:[{D:[0.5,0.25,0]}]} → dBarFill flatten(style).height sırasıyla '100%','50%','4%'; dBarLabel fontSize ≥ rf(11). Kaynak kapısı: AiHub… | Düşük — sonuç paneli görseli. Geri alma: iki satır + 2 stil. | 1 |
| 9 | Kedi Sesi / Histopatoloji olasılık çubukları: dar ekranda dikey düzen | `pf/src/screens/AiHubScreen.tsx (CatSoundModule 2685-2696; HistopathModule 3050-3061; styles 3712-3716)`, `pf/src/screens/__tests__/olasilikCubuguCompact.test.tsx (YENİ)` | İki modülde `isCompact` zaten okunuyor. Satırı `isCompact` iken `<View style={[styles.soundBarRow, isCompact && styles.soundBarRowCompact]}>` → soundBarRowCompact: {flexDirection:'column', alignItems:'stretch', gap: 2}; üstte `<View style={{flexDirection:'row', justifyContent:'space-between'}}>` etiket + yüzde, altta … | `aihub-11` | jest: useWindowDimensions mock {width:320,height:640} → Kedi Sesi sonucu top_k 3 → soundBarRow flatten flexDirection 'column', ray Track ebeveyn genişliği tam; width 1024 → 'row', label minWidth rs(9… | Düşük. Geri alma: stil koşulunu kaldır. | 1.5 |
| 10 | Rozet/etiket en küçük yazı tabanı + tam-genişlik güvenlik rozeti | `pf/src/screens/AiHubScreen.tsx (styles 3676-3680 liveIndicator/liveText/serverCamNote; JSX 1449-1454, 1478-1481, 3533-3536)`, `pf/src/components/domain/AiProPanel.tsx (906 metricLabel)`, `pf/src/components/domain/AiSpecApprovalModal.tsx (214-223 metaLabel/rel/xai/th)`, `pf/src/theme/tokens.ts (rfMin yardımcısı)` | tokens.ts: `export function rfMin(size:number, min=11){ return Math.max(rf(min), rf(size)); }` — (tercih: doğrudan typography.small/caption kullan; rfMin yalnız ara boyutlar için). liveText, serverCamNote, metricLabel, th, xai, rel → `typography.small`; metaLabel → typography.small; rel/relWarn → `typography.caption` … | `aihub-14`, `ilkel-14` | pytest tests/test_responsive_grafik_kapisi.py: capraz.kaynak_yolu('pf/src') altında regex `fontSize:\s*rf\((9|10)\)` sıfır eşleşme (kırmızı kanıtı: bir dosyaya rf(10) ekleyip koş → düşer). jest AiSpe… | Düşük — metin boyutu; AiSpecApprovalModal onay akışı (Onayla/Reddet) mantığına dokunulmaz. liveIndicator şeride dönüşünce flipCameraBtn (sağ-alt) ile çakışmaz … | 1.5 |
| 11 | DEMA simülatörü web iframe yüksekliği pencereyi izlesin | `pf/src/screens/DemaSimulatorScreen.tsx (15, 23, 52-60)`, `pf/src/screens/__tests__/demaSimulatorYukseklik.test.tsx (YENİ)` | `const [nativeHeight, setNativeHeight] = useState<number|null>(null)`; `const webHeight = Platform.OS==='web' ? (nativeHeight ?? Math.max(rs(480), Math.round(height*0.78))) : (nativeHeight ?? Math.max(640, Math.round(height*0.78)))` — height değişince türetilir (state'e kilitlenmez). iframe `onLoad={(e)=>{ setLoading(… | `ekranB-11` | jest (Platform web mock, AiProPanelWeb.test deseni): useWindowDimensions mock height 1080 → simulatorContainer height 842; rerender height 700 → 546 (rs(480) tabanı); onLoad ile contentDocument scrol… | Düşük. contentDocument cross-origin ise (tünel/uzak erişimde farklı origin) try/catch sessiz düşer, yükseklik pencere oranına döner. Geri alma: tek dosya. | 1.5 |

<details><summary>Kod taslakları</summary>

**1. Seans Detayı sıcaklık grafiği: viewBox'ı ölçülen genişliğe eşitle**

```
const [w, setW] = useState(0);
const h = rs(240); const narrow = w > 0 && w < 400;
const PAD = { top: 20, right: narrow ? 12 : 20, bottom: 36, left: narrow ? 40 : 48 };
const plotW = w - PAD.left - PAD.right; const plotH = h - PAD.top - PAD.bottom;
const xTicks = narrow ? 3 : 5;
<View style={styles.chartWrap} testID="seans-sicaklik-grafigi" onLayout={(e)=>setW(e.nativeEvent.layout.width)}>
  {w > 0 && (<Svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}> ... <SvgText fontSize={rf(11)} .../> ...</Svg>)}
</View>
```

**2. RealtimeChart: PAD'i genişlikten türet + web canvas DPR + 1200 kapağını kaldır + dar ekranda yatay kaydırma**

```
// draw() başı
const dpr = Math.min(3, (typeof window !== 'undefined' && window.devicePixelRatio) || 1);
canvasBoyutla(canvas, ctx, width, height, dpr);
const W = width, H = height;
const PAD = hesaplaPad(width, showTemp);
// JSX
<canvas ref={canvasRef as any} style={{ display: 'block', width, height, borderRadius: 8 }} />
// SensorMonitorScreen
const { isCompact } = useResponsive();
const grafikW = isCompact ? Math.max(chartW, rs(480)) : chartW;
{isCompact ? <ScrollView horizontal>{grafik}</ScrollView> : grafik}
```

**3. KPI: pasta lejantını RN View'a taşı, bar paddingRight'ı daralt, bobin tablosunu sağa hizala**

```
<PieChart data={pieData} width={chartW} height={rs(220)} chartConfig={chartConfig} accessor="population" backgroundColor="transparent" paddingLeft={String(Math.max(0, Math.round(chartW/2 - rs(220)/2.5 - chartW/4)))} hasLegend={false} />
<View style={styles.pieLegend}>
  {pieData.map((d) => (
    <View key={d.name} style={styles.pieLegendItem}>
      <View style={[styles.pieLegendDot, { backgroundColor: d.color }]} />
      <Text style={styles.pieLegendText} numberOfLines={1}>{d.population} {d.name}</Text>
    </View>))}
</View>
```

**4. Backend: AI kare yanıtlarına gerçek boyut (image_w/image_h) ekle**

```
# ai_pro/frame (img_out encode edildikten sonra)
return JSONResponse(content={
    "status": "success",
    "image_base64": b64_image,
    "image_w": int(img_out.shape[1]), "image_h": int(img_out.shape[0]),
    ...})
# ai_vision yayını
"data": {"type": ..., "imageBase64": b64, "imageW": int(ov.shape[1]), "imageH": int(ov.shape[0]), ...}
```

**5. Kamera kutusu oran kilidi: AiHub VisionModule + CatOrganModule (canlı mod)**

```
// utils/kameraKutusu.ts
export function kareOrani(r: { image_w?: number; image_h?: number } | null | undefined, portre: boolean): number {
  const w = Number(r?.image_w), h = Number(r?.image_h);
  return w > 0 && h > 0 ? w / h : (portre ? 3 / 4 : 4 / 3);
}
export function kameraKutusu(kutuW: number, oran: number, ekranH: number, tavan = 0.55) {
  const h = Math.min(kutuW / oran, Math.round(ekranH * tavan));
  return { width: Math.round(h * oran), height: Math.round(h) };
}
// AiHubScreen canlı dal
<View style={[styles.imagePreviewContainer, isLive && { height: undefined, minHeight: rs(200) }]} onLayout={(e) => setKutuW(e.nativeEvent.layout.width)}>
  {isLive && kutuW > 0 && (
    <View style={[{ position: 'relative', alignSelf: 'center' }, kameraKutusu(kutuW, oran, ekranH)]}>
      <CameraView ref={cameraRef} style={styles.cameraView} facing={facing} ratio="4:3" />
      {result?.image_base64 && <Image source={{ uri: `data:image/jpeg;base64,${result.image_base64}` }} style={styles.cameraOverlay} />}
```

**6. AI Pro paneli camBox oran kilidi + flipBtn 44 px**

```
const { width: ekranW, height: ekranH } = useResponsive();
const [kutuW, setKutuW] = useState(0);
const oran = IS_WEB ? kareOrani({ image_w: (v as any)?.imageW, image_h: (v as any)?.imageH }, false) : kareOrani(mobileResult, ekranH > ekranW);
const kutu = kutuW > 0 ? kameraKutusu(kutuW, oran, Math.min(ekranH, rs(840)), 0.5) : null;
<View style={styles.camBox} onLayout={(e) => setKutuW(e.nativeEvent.layout.width)}>
  ... <View style={[styles.cam, kutu, { alignSelf: 'center' }]}>
        <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing={facing} ratio="4:3" />
```

**8. Fantom/Petri D1–D7 duty çubukları: yüzde dolgu + okunur etiket**

```
const dutyYuzde = (d: number) => `${Math.max(4, Math.round((Math.min(Math.max(d, 0), 0.5) / 0.5) * 100))}%`;
<View style={[styles.dBarFill, { height: dutyYuzde(d) as any }]} />
<Text style={styles.dBarLabel}>D{j + 1}</Text>
<Text style={styles.dBarLabel}>%{Math.round(Math.min(Math.max(d, 0), 0.5) * 200)}</Text>
```

**11. DEMA simülatörü web iframe yüksekliği pencereyi izlesin**

```
const { height } = useWindowDimensions();
const [olculen, setOlculen] = useState<number | null>(null);
const webHeight = olculen ?? Math.max(Platform.OS === 'web' ? rs(480) : 640, Math.round(height * 0.78));
<iframe ... onLoad={(e) => { setLoading(false); try { const h = (e.currentTarget as any).contentDocument?.documentElement?.scrollHeight || 0; if (h > 240 && h < 12000) setOlculen(h); } catch {} }} />
```

</details>

**Bağımlılıklar:** Adım 5-6 (istemci oran kilidi) → Adım 4 (backend image_w/image_h) SONRA; istemci Image.getSize fallback'i sayesinde eski backend'le de çalışır ama birebir hiza için 4 şart.; Adım 7 (cihaz testi) → 4, 5, 6 bitmiş APK + launcher build (⚠️ backend+APK build PARALEL KOŞMAZ — bellek notu).; ekranC-2'nin '1024 masaüstü 3 sütun / iPad 2 sütun dar kart' kısmı S2 kökündeki ekranC-1 (ResponsiveGrid gerçek içerik genişliği) düzeltmesine bağlı; Adım 3 ondan bağımsız uygulanır, tam kapanış ekranC-1 ile.; Adım 10 kaynak kapısı (rf(9)/rf(10) yasağı) S6 kökü (maxFontSizeMultiplier) ile aynı dosyalara dokunur → aynı PR'da veya S6'dan SONRA rebase ile.; Adım 2 SensorMonitor yatay ScrollView → useResponsive import (mevcut hook).; Jest süiti: pf/ içinde `npm test` (jest-expo, RNTL 13); pytest: guii kökünde tam süit, `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` ile yayın makinesinde.; Backend değişikliği (Adım 4) manifest sürümü ÜÇ yerde (bellek notu) — yayınla birlikte.

**Kilitler:**
- HASTA GÜVENLİĞİ: ACİL DURDUR (AppShell) ve seans başlat/durdur akışı hiçbir adımda değişmez; AiProPanel'de yalnız stil/sarmalayıcı View değişir — start/stop/capture/ownedRef/interval/hazirlik mantığı ve `(running || hazirlik) && permission?.granted` koşulu, `if (IS_WEB || (!running && !hazirlik)) return;`, KARE_ARALIK_SEANS_MS/HAZIRLIK_MS, ARDISIK_ONAY, `güven %${guvenYuzde}` metni, asama bloğu backtick sayısı (tests/test_ai_pro_asamali_akis.py regex çıpaları) BİREBİR korunur.
- AiHubScreen otonom-mod yaşam döngüsü (1099-1140: autoAdjust, mountedRef, liveAbortRef) ve autoAdjust sunucu-karesi dalı (1437-1463) DEĞİŞMEZ; yalnız telefon-kamera canlı dalı oranlanır.
- B2 ısı-haritası boyut kilidi (xaiIsiHaritasiBoyut.test): statik modda imagePreviewContainer rs(300) ve xaiStage rs(300) AYNI kalır; `height:'100%'` yalnız sabit-yükseklikli ebeveyn içinde.
- Backend: yalnız-EK alanlar (image_w/image_h, imageW/imageH); mevcut alanlar/şema/auth-muafiyet/allowlist DEĞİŞMEZ; yeni endpoint YOK (route-contract sayaç kapısı etkilenmez). AI uçları sahip-talebiyle auth-muaf (bellek) — geri koyma.
- AiSpecApprovalModal onay/red mantığı ve hekim onay kapısı değişmez; yalnız fontSize.
- Overlay `resizeMode:'contain'` korunur — sunucu işaretleri ASLA kırpılmaz.
- RealtimeChart ortak zaman penceresi / 'akışı durmuş bobin sağ uca ulaşmaz' değişmezi (tıbbi grafik dürüstlüğü) aynen; yalnız PAD/DPR.
- Kapı kırmızı kanıtı: her yeni test/regex kapısı için mutasyon koşturulur (bellek: 'Kapı KIRMIZI Olduğunu Kanıtla'); çıpalar gerçek ifadeye pinlenir, satır numarasına değil.

**Cihaz testi:**
- Android telefon 320-360 px dikey (a): Seans Detayı sıcaklık grafiği eksen yazıları ≥10 px okunuyor; Sensörler grafiği yatay kayıyor, 8 bobin ayrık; Fantom D çubukları %; Kedi Sesi çubukları dikey düzen; rozet şeridi tek/iki satır hizalı (Yazı boyutu 1.3 ile de).
- Android telefon 375-430 dikey (b) + iPhone: AI Hub → Kedi Organ canlı mod: overlay 'hayalet' kenarı canlı kâğıt kenarıyla çakışıyor (kayma ≤%2 kutu genişliği); Kontrol → AI Pro hazırlık: organ kutusu canlı görüntüde doğru yerde; flip düğmesi 44 px.
- Android yatay (c): kamera kutusu 4:3 yatay, tavan ekranın %55/%50'si; sayfa kaydırılabilir; E-stop erişimi kaydırmasız.
- iPad dikey/yatay (d): AI Pro kutusu rs(420) tavanında, iki yanı siyah değil (oranlı); KPI pie lejantı altta.
- PC WebView2 launcher %100/%150/%200 DPI (f/h): Sensörler canvas keskin (eksen 11 px net); Sensörler 1920'de canvas tam genişlik (1200 kapağı yok); AI Pro web sunucu karesi büyük kutuda; DEMA iframe maximize sonrası büyüyor.
- LAN tarayıcı telefon DPR 3 (e): Sensörler canvas keskin; web canlı mod (VisionModule) webcam oranı kutuya oturuyor.
- Klinik güvenlik turu (her yapıda): ACİL DURDUR her ekranda tek dokunuşla erişilebilir; AI Pro hazırlık → öneri → onay → seans → durdur akışı değişmemiş (bobin sürülmeden hazırlık modunda test).

**Açık sorular (sahip kararı):**
- ilkel-2 ve ilkel-9 bulgular JSON'da yok (rapor §Birleştirilen tekrarlar: ilkel-2→ekranC-3, ilkel-9→ekranB-6). Ayrı adım açılmadı; orkestratör kanonik id ile kapatsın.
- Android'de `ratio="4:3"` çekilen fotoğrafın (ImageCapture) çözünürlük seçicisini de 4:3'e zorluyor mu? Kod (buildResolutionSelector) öyle gösteriyor ama cihazda ölçülmeli (Adım 7). Aksi hâlde `pictureSize` ile eşitleme gerekir.
- Web canlı mod (VisionModule, PC webcam) klinikte gerçekten kullanılıyor mu? Kullanılmıyorsa `isLive` düğmesi web'de gizlenebilir (kapsam daraltma) — sahip kararı.
- DEMA simülatörünün kaynağı bu depoda mı (backend /simulator/ statik)? Varsa native ile aynı postMessage(String(h)) sözleşmesi simülatöre eklenip web'de de dinlenebilir; yoksa yalnız contentDocument ölçümü.
- AiProPanel kutusu büyüyünce ControlScreen'de ACİL DURDUR'un kaydırmasız görünürlüğü korunuyor mu (320×568 dikey)? Değilse AI Pro tavanı 0.5→0.4 (Adım 7'de ölçülecek).
- Backend `_kapili_devret` (mikroservis :8100) yolunda image_w/h eklemek için ek decode kabul mü, yoksa mikroservis yanıtına da alan eklensin mi (ai_service repo değişikliği)?

**Toplam efor:** ~26.5 saat

### L — Başlatıcı (13 bulgu: 2 yüksek / 4 orta / 7 düşük)

Bağlı bulgular: `launcher-1`, `launcher-2`, `launcher-3`, `launcher-4`, `launcher-5`, `launcher-6`, `launcher-7`, `launcher-8`, `launcher-9`, `launcher-10`, `launcher-11`, `launcher-12`, `matris-9`

**Hedef:** Başlatıcı her Windows DPI/çalışma-alanı kombinasyonunda (1366×768 @%125/%150, 1920×1080 @%200, 2560×1440 @%100, dokunmatik Surface) ekrana sığar; içerik pencereden uzun olduğunda en üstten başlayıp kaydırılabilir (başlık/lead asla kırpılmaz); ikon-only düğmeler tooltip + erişilebilir ad taşır; profil kartları ve üç modal yalnız klavyeyle kullanılabilir; güncelleme kipi penceresi ilk kareden doğru boyutta/doğru içerikle görünür; uygulama ('app') penceresi 'geri yükle' sonrasında da masaüstü kırılma noktasını korur. Hiçbir adım kapanış/E-stop yolunu (on_window_event Destroyed → safe_stop_coils → kill), Başlat kapısını (startKapisiAc/Kapat) ya da seans akışını değiştirmez.

**Tasarım kararları:**
- Dikey taşma için `justify-content: flex-start` + `.stage { margin: auto 0 }` (her Chromium sürümünde çalışır); `safe center` yalnız ek olarak, tek başına DEĞİL — WebView2 evergreen olsa da offline installer ile gelen eski runtime'lar olabilir.
- Pencere boyutu iki katmanlı: tauri.conf statik taban (minHeight 540→460, minWidth 700 kalır) + Rust setup'ta monitör çalışma alanına göre dinamik kırpma. Kırpma mantığı SAF fonksiyona (`ana_pencere_boyutu`, `uygulama_pencere_boyutu`) alınır → cargo test ile pariteli; tauri API çağrıları ince sarmalayıcıda kalır.
- gunc kipindeki '250 ms gecikmeli iş parçacığı' kalıbı (main.rs:2079-2089, 'setup içinde ezildi, ölçüldü' notu) normal kipte de aynen kullanılır — yeni bir zamanlama deseni icat edilmez.
- `visible:false` + `show()` YALNIZ Rust tarafındaki koşulsuz zamanlayıcıya bağlanır; JS'e ('pencereyi göster' komutu gibi) bağlanmaz. Gerekçe: 2026-08-29 arızasında JS hiç ayrıştırılamadı — JS'e bağlı show() pencereyi hiç göstermez, görünmez donmuş uygulama üretirdi.
- Genişlik ekseninde 680 kuralı silinir; asıl kritik eksen YÜKSEKLİK olduğundan `@media (max-height: 620px)` eklenir. pf breakpoints.ts (tablet 768 / desktop 1024) yorum satırında referanslanır ama launcher kendi eşiklerini kullanır (kabuk genişlikleri farklı).
- Global rem/clamp yazı ölçeği dönüşümü YAPILMAZ (launcher-10 ikinci doğrulama): dikey bütçeyi büyütüp launcher-1'i geri getirir. Yalnız alt sınır (10-11.5px → 11-12px) ve ≥1600px için .stage 680px.
- Modal odak yönetimi `inert` özniteliğiyle (Chromium 102+, WebView2'de var); elle Tab-döngüsü kodu yazılmaz. `closeModal` inert'i KOŞULSUZ kaldırır (kaldırılmazsa Başlat/E-stop'a giden tüm yol klavyeden kilitlenir).
- Escape = 'vazgeç' DEĞİL 'kapat': confirm'de Escape hiçbir geri çağrıyı (ne cb ne noCb) çalıştırmaz. Gerekçe: resumeTitle onayının noCb'si `discard_pending` (inen 1,4 GB'ı SİLER) — yanlışlıkla basılan Escape veri silmemeli. Odak `confirm-no`ya taşınır → Enter güvenli varsayılan (Vazgeç).
- Kartlar `<button type=button aria-pressed>` olur; `busy` iken `disabled` verilir (mevcut `if (busy) return` görsel karşılık bulur). Kart DOM yapısı (box/pico/meta/size) değişmez — renderCards'ı çağıran depNotice/updateInstallBtn dokunulmaz.
- Header 1040 eşiği kaldırılır; etiketler `header.authed` sınıfıyla (oturum açıkken) ve `@media (max-width: 860px)` ile gizlenir; her durumda title + aria-label kalıcı çözümdür (launcher-3 ikinci doğrulama: 880'de oturum açıkken etiketler zaten sığmıyor).
- Mevcut kapıların çalışma biçimi korunur: test_launcher_ui_sozdizimi (node --check tüm script) → yeni JS geçerli kalmalı; test_client_arayuz_sade_dil (I18N TR değerleri) → yeni i18n anahtarı eklenmez, title/aria-label mevcut x.web/x.guide/x.about/x.logout metinlerini kullanır; test_self_update_ekran_kilidi `_fonksiyon(ham, imza)` çıkarıcısı → `function show(id)`, `startKapisiAc/Kapat`, `trySelfUpdate` imzaları ve girintili `      }` kapanışı değişmez.
- Yeni kapı `tests/test_launcher_responsive_kapisi.py` yorum-soyulmuş metinde çalışır (test_client_arayuz_sade_dil `_soy` yeniden kullanılır) ve her kural için KARŞIT-KANIT (mutasyon) testi taşır — 'Kapı KIRMIZI olduğunu kanıtla' kuralı.

| # | Adım | Dosyalar | Değişiklik | Kapattığı | Doğrulama | Risk | Efor (s) |
|---|---|---|---|---|---|---|---|
| 1 | Dikey taşma kökü: main flex-start + .stage margin:auto (+ safe center) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\ui\index.html` | CSS satır 94-96: `main { ... justify-content: center; }` → `justify-content: flex-start;` ve `.stage { width:100%; max-width:560px; margin: auto 0; }`. Auto margin sığdığında dikey ortalar, taştığında 0'a düşer → içerik en üstten başlar ve main'in overflow:auto'su ile kaydırılır. `html.gunc main { justify-content:cent… | `launcher-1`, `ampirik-2`, `launcher-8` | (a) Statik kapı (adım 11): main kuralında `justify-content: flex-start` ve .stage'de `margin: auto 0`; (b) ampirik: headless Edge/Chromium (msedge --headless --screenshot) ile modül-script'i stub'lan… | DÜŞÜK. Yalnız CSS; JS/E-stop yolu dokunulmaz. Görsel risk: kısa içerikte ortalama korunuyor mu (auto margin) — (c) ile ölçülür. Geri alma: 3 satırı eski değeri… | 0.5 |
| 2 | Medya sorguları: ölü 680 kuralını sil, @media (max-height:620px) + geniş ekran + dokunmatik ekle | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\ui\index.html` | Satır 398-402 `@media (max-width: 680px)` bloğu SİLİNİR (minWidth 700 → asla tetiklenmez; .brand p ve .hbtn span zaten 1180/1040'ta gizli). Yerine üç blok: (1) `@media (max-height: 620px)` — .title 22px, .lead margin-bottom 10px, .check 64px (svg 34px), .pct 36px/min-height 40px, .cards gap 6px, .card padding 9px 12px… | `launcher-12`, `launcher-10`, `launcher-11` | (a) Statik kapı: kaynakta `max-width: 680px` YOK, `max-height:` medya sorgusu VAR, `pointer: coarse` VAR, `.reqtag` font-size ≥ 11px; (b) ampirik: 911×480 viewport (1366@%150 maximize) s-login ve s-s… | DÜŞÜK. Yalnız CSS. Dikkat: `.link.danger { margin-left:auto }` s-ready subactions'ta 'Uygulamayı kaldır'ı sağa iter — yalnız coarse'ta; fare düzeninde değişmez… | 1 |
| 3 | Rust: ana pencereyi monitör çalışma alanına göre boyutla (saf fonksiyon + setup) ve tauri.conf minHeight 460 | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\src\main.rs`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\tauri.conf.json` | tauri.conf.json windows[0]: `"minHeight": 540` → `460` (adım 1-2 ile içerik 460'ta kaydırılabilir). main.rs: (1) saf `fn ana_pencere_boyutu(wa_w: f64, wa_h: f64) -> ((f64,f64),(f64,f64))` — mantıksal çalışma alanından (pencere, min) döner: pay 40px, üst sınır 880×600, min 700×460, alt taban 640×400 (çok küçük sanal ek… | `launcher-2`, `matris-10` | (a) `cargo test -p pemf-vet-client ana_pencere_boyutu` (launcher/ kökünde; workspace Cargo.lock orada): 1366@%150 → wa 911×480 → ((871,440),(700,440)); 1366@%125 → 1093×576 → ((880,536),(700,460)); 1… | ORTA. Rust değişikliği; `Manager` zaten import (satır 15). HASTA GÜVENLİĞİ: on_window_event Destroyed bloğuna DOKUNULMAZ — `.setup` ayrı bir zincir halkası; E-… | 2 |
| 4 | Güncelleme kipi zıplaması: visible:false + boyutlandıktan sonra show() + gunc sınıfını ilk kareden önce eval | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\tauri.conf.json`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\src\main.rs` | tauri.conf windows[0]'a `"visible": false`. Normal kip: adım 3'teki iş parçacığı sonunda `w.show()` (zaten taslakta). gunc kipi (`guncelleme_ekranini_calistir` setup'ı, 2079-2089): iş parçacığında set_min_size(None)/set_resizable(false)/set_size/center'dan SONRA `w2.eval("document.documentElement.classList.add('gunc')… | `launcher-9` | (a) Statik kapı: tauri.conf `windows[0].visible == false`; main.rs yorum-soyulmuş: `fn guncelleme_ekranini_calistir` gövdesinde `set_size(` < `eval(` < `show()` sırası ve `fn main()` gövdesinde (setu… | ORTA-DÜŞÜK. En kötü durum: show() çağrısı bir nedenle koşmazsa pencere görünmez → bu yüzden show() iş parçacığında hiçbir `?`/erken dönüşün ARKASINDA değil, ko… | 1 |
| 5 | Header: ikon-only düğmelere title + aria-label; 1040 eşiği yerine header.authed + 860; dar pencerede marka koruması | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\ui\index.html` | JS applyLang() (1479+): `t-web/t-guide/t-about/t-logout` textContent satırlarının yanına düğme başına `title` + `setAttribute('aria-label', …)` (mevcut x.web/x.guide/x.about/x.logout — yeni i18n anahtarı YOK). refreshAuth sonrası (2060, `$("auth-box").hidden = !authed`) `document.querySelector('header').classList.togg… | `launcher-3`, `launcher-7` | (a) Node birim (test_self_update_ekran_kilidi `_fonksiyon` kalıbı): `function etiketle` çıkarılıp sahte `$` ile koşturulur → title ve aria-label = verilen metin; (b) statik kapı: applyLang gövdesinde… | DÜŞÜK. `header.authed` sınıfı authed değişince güncellenmeli — tek yer (2060) + logout sonrası aynı fonksiyon koşuyor mu kontrol et (btn-logout → askConfirm → … | 1 |
| 6 | Profil kartları: div → button type=button aria-pressed, focus-visible halkası, busy iken disabled | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\ui\index.html` | renderCards() (1539-1580): `document.createElement("div")` → `"button"`; `card.type = "button"; card.setAttribute("aria-pressed", String(on)); card.disabled = busy;` — geri kalan DOM (box/pico/meta/size), onclick mantığı, depNotice()/updateInstallBtn() çağrıları AYNEN kalır. CSS `.card`: `width: 100%; text-align: left… | `launcher-4` | (a) Node birim: `renderCards` gövdesi `_fonksiyon` ile çıkarılır; sahte `document.createElement` (tagName, attrs, children kaydeden nesne), `$`, `withDeps`, `orderedKeys`, `PROFILE_META`, `sizes`, `b… | DÜŞÜK. Kartın iç <em class=reqtag>, <span>, <b> öğeleri button içinde geçerli (phrasing content; <div class=meta> button içinde teknik olarak flow content ama … | 1 |
| 7 | Modallar: openModal/closeModal (odak + inert + Escape + role=dialog) ve confirm-body pre-wrap | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\ui\index.html` | JS: `openModal(id, focusId)` → overlay.hidden=false; header/main/footer `inert=true`; `sonOdak = document.activeElement`; focus(focusId). `closeModal(id)` → hidden=true; başka görünür overlay yoksa inert'i KOŞULSUZ kaldır; sonOdak'a dön. Kullanım: about → openModal('about','about-close'); guide → openModal('guide','gu… | `launcher-5`, `launcher-6` | (a) Node birim (`_fonksiyon` kalıbı, sahte DOM: hidden/inert/focus kaydı): openModal('confirm','confirm-no') → header/main/footer.inert==true, odak confirm-no; closeModal → inert false, odak eski öğe… | ORTA (davranışsal). En büyük risk inert'in takılı kalması → tüm arayüz klavye/fare için ölü; closeModal her yolda koşar ve `acik` kontrolü ile koşulsuz kaldırı… | 2 |
| 8 | Uygulama ('app') penceresi: inner_size + çalışma alanına kırpılmış min_inner_size | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\src\main.rs` | open_app_window (415-418): saf `fn uygulama_pencere_boyutu(wa_w, wa_h) -> ((f64,f64),(f64,f64))` → pencere (1280,800) ve min (1024,640) her biri `min(·, wa-40)`; monitör `app.get_webview_window("main")` → `current_monitor()` (launcher'ın olduğu monitör; yoksa `app.primary_monitor()`); Builder'a `.inner_size(pw,ph).min… | `matris-9` | (a) cargo test `uygulama_pencere_boyutu`: 1920×1040 (@%100, görev çubuğu düşülmüş) → ((1280,800),(1024,640)); 911×480 (1366@%150) → ((871,440),(871,440)) — ekrandan küçük; 1093×576 → ((1053,536),(102… | DÜŞÜK-ORTA. HASTA GÜVENLİĞİ dolaylı olumlu: pf'teki ACİL DURDUR düğmesi masaüstü düzeninde sabit görünür kalır (telefon kabuğuna düşmez). Kapanış yolu (Destroy… | 1 |
| 9 | Kapılar: tests/test_launcher_responsive_kapisi.py (statik + Node davranış + mutasyon) ve cargo parite testleri | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\tests\test_launcher_responsive_kapisi.py`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\src\main.rs` | Yeni Python kapısı (test_client_arayuz_sade_dil `_soy` ve test_self_update `_fonksiyon` kalıpları yeniden kullanılır; yorum-soyulmuş metinde çalışır): test_KRITIK_main_flex_start_ve_stage_margin_auto; test_KRITIK_olu_680_sorgusu_YOK_max_height_VAR; test_KRITIK_ikon_dugmeler_etiketli (etiketle × 4); test_KRITIK_kartlar… | `launcher-1`, `launcher-2`, `launcher-3`, `launcher-4`, `launcher-5`, `launcher-6`, `launcher-9`, `launcher-12`, `matris-9` | `cd launcher && cargo test` (workspace kökü; Cargo.lock launcher/ altında) tüm testler yeşil; `python -m pytest tests/test_launcher_responsive_kapisi.py tests/test_launcher_ui_sozdizimi.py tests/test… | DÜŞÜK. Yapısal çıpalar (`\n main {`) refaktörde kayabilir — çıpayı gerçek CSS seçicisine ve fonksiyon imzasına pinle, tam süiti koştur (bellek: 'Yapısal Çıpa K… | 2.5 |
| 10 | Ampirik görünüm-alanı kapısı (isteğe bağlı CI, yerelde zorunlu): headless Edge + 5 viewport ekran görüntüsü ve ölçüm | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\tests\launcher_gorunum_alani_olc.py`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\ui\index.html` | Denetimde kullanılan yöntem betiğe alınır: index.html'in `<script type=module>` bloğu stub'lanmış kopyası (`window.__TAURI__` sahte) geçici dizine yazılır; her ekran (s-login+hata, s-select+dep-notice+hata, s-ready+notice, s-install) için `hidden` öznitelikleri elle açılır; msedge `--headless=new --window-size=W,H --s… | `launcher-1`, `launcher-7`, `launcher-8`, `launcher-10`, `launcher-11`, `launcher-12` | Betik yerelde koşar, 5×4 PNG üretir; docs/responsive-denetim-2026-09-04.md §6 'Kilitler (2)' maddesiyle uyumlu. CI'da msedge yoksa skip — bellek kuralı 'Kapı Ortam Varsayımı → ÇOĞUNLUK': skip edilen … | DÜŞÜK. Ürün kodu değişmez. Edge sürümü/CDP farkları betiği kırabilir → yalnız yerel kapı. | 2 |
| 11 | Cihaz/klavye kabul turu + sürüm ve yayın notu | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\tauri.conf.json`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\launcher\app\Cargo.toml`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\docs\responsive-denetim-2026-09-04.md` | Launcher sürümü 1.9.45 → 1.9.46 (manifest sürümü ÜÇ yerde — bellek: AI Zaman Aşımı + Yayın notu); Launcher Yayın Runbook'a göre sadece-client yayını (androidTag'e dokunma; sürümsüz+sürümlü iki ad). Denetim raporunda L bölümüne 'kapatıldı (1.9.46)' notu ve bulgu JSON'unda ilgili kayıtlara `durum: kapandi` alanı (rapor … | `launcher-1`, `launcher-2`, `launcher-3`, `launcher-4`, `launcher-5`, `launcher-6`, `launcher-7`, `launcher-8`, `launcher-9`, `launcher-10`, `launcher-11`, `launcher-12`, `matris-9` | cihaz_testi listesindeki 8 senaryo; self-update kanıtı: 1.9.45 kurulu makinede 1.9.46'ya oto-güncelleme → gunc penceresi zıplamadan açılır, kapanır, yeni sürüm 'Hazır!' ekranıyla ekrana sığmış açılır. | DÜŞÜK. Yayın adımı; sahip onayı gerektiren dış servise yayın (GitHub Release) — teyit alınır. | 1.5 |

<details><summary>Kod taslakları</summary>

**1. Dikey taşma kökü: main flex-start + .stage margin:auto (+ safe center)**

```
main { flex: 1; overflow: auto; display: flex; flex-direction: column;
  align-items: center; justify-content: flex-start; padding: 18px 30px; text-align: center; }
/* auto margin: sığınca ortalar, taşınca 0 → üstten başla + kaydır (launcher-1) */
.stage { width: 100%; max-width: 560px; margin: auto 0; }
html.gunc main { padding: 22px 30px; justify-content: flex-start; }
#error { ...; white-space: pre-wrap; overflow-wrap: anywhere; overflow-x: hidden; }  /* max-height/overflow:auto KALDIRILDI */
```

**2. Medya sorguları: ölü 680 kuralını sil, @media (max-height:620px) + geniş ekran + dokunmatik ekle**

```
@media (max-height: 620px) {
  main { padding: 10px 20px; }
  .title { font-size: 22px; }  .lead { margin-bottom: 10px; }
  .check { width: 64px; height: 64px; margin-bottom: 12px; }  .check svg { width: 34px; height: 34px; }
  .pct { font-size: 36px; min-height: 40px; margin-bottom: 8px; }
  .cards { gap: 6px; }  .card { padding: 9px 12px; }
  .btn.big { padding: 12px 32px; }  .subactions { margin-top: 12px; }  .form { gap: 8px; }
}
@media (min-width: 1600px) { .stage { max-width: 680px; } body { font-size: 15px; } }
@media (pointer: coarse) {
  .seg button, .hbtn, .link, .mbtn, .ctlbtn { min-height: 44px; padding-inline: 14px; }
  .subactions { gap: 12px 28px; }  .link.danger { margin-left: auto; }
}
```

**3. Rust: ana pencereyi monitör çalışma alanına göre boyutla (saf fonksiyon + setup) ve tauri.conf minHeight 460**

```
/// Saf: monitör ÇALIŞMA ALANI (mantıksal px) → (pencere, min) boyutu. launcher-2/matris-10.
fn ana_pencere_boyutu(wa_w: f64, wa_h: f64) -> ((f64, f64), (f64, f64)) {
    const PAY: f64 = 40.0;
    let w = 880f64.min(wa_w - PAY).max(640.0);
    let h = 600f64.min(wa_h - PAY).max(400.0);
    ((w, h), (700f64.min(w), 460f64.min(h)))
}
fn pencereyi_calisma_alanina_sigdir(w: tauri::WebviewWindow) {
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(250)); // config setup'ı ezer (ölçüldü, gunc kipiyle aynı)
        let m = w.current_monitor().ok().flatten().or_else(|| w.primary_monitor().ok().flatten());
        if let Some(m) = m {
            let sf = m.scale_factor(); let wa = m.work_area();
            let ((pw, ph), (mw, mh)) = ana_pencere_boyutu(wa.size.width as f64 / sf, wa.size.height as f64 / sf);
            let _ = w.set_min_size(Some(tauri::LogicalSize::new(mw, mh)));
            let _ = w.set_size(tauri::LogicalSize::new(pw, ph));
            let _ = w.center();
        }
        let _ = w.show(); // adım 4: visible:false ile birlikte, JS'e BAĞLI DEĞİL
    });
}
// Builder zinciri: .manage(AppState::default()).setup(|app| { if let Some(w) = app.get_webview_window("main") { pencereyi_calisma_alanina_sigdir(w); } Ok(()) })
```

**4. Güncelleme kipi zıplaması: visible:false + boyutlandıktan sonra show() + gunc sınıfını ilk kareden önce eval**

```
// gunc kipi setup iş parçacığı (mevcut 250 ms kalıbı):
let _ = w2.set_min_size(None::<tauri::Size>);
let _ = w2.set_resizable(false);
let _ = w2.set_size(tauri::LogicalSize::new(640.0, 400.0));
let _ = w2.center();
// header/footer İLK KAREDEN ÖNCE gizli (JS boot'u beklemeden; boot da ekler → idempotent)
let _ = w2.eval("document.documentElement.classList.add('gunc')");
let _ = w2.show(); // KOŞULSUZ: JS çökse de pencere görünür
// tauri.conf.json windows[0]: "visible": false
```

**5. Header: ikon-only düğmelere title + aria-label; 1040 eşiği yerine header.authed + 860; dar pencerede marka koruması**

```
function etiketle(id, metin) { const b = $(id); b.title = metin; b.setAttribute("aria-label", metin); }
// applyLang() içinde:
$("t-web").textContent = x.web;   etiketle("btn-web", x.web);
$("t-guide").textContent = x.guide; etiketle("btn-guide", x.guide);
$("t-about").textContent = x.about; etiketle("btn-about", x.about);
$("t-logout").textContent = x.logout; etiketle("btn-logout", x.logout);
// refreshAuth (2060) yanına:
document.querySelector("header").classList.toggle("authed", authed);
/* CSS */
header.authed .hbtn span { display: none; }  header.authed #auth-email { max-width: 120px; }
@media (max-width: 860px) { .hbtn span { display: none; } }
.brand { min-width: 54px; }
@media (max-width: 800px) { #offline-badge span:last-child { display: none; } #auth-email { max-width: 90px; } }
```

**6. Profil kartları: div → button type=button aria-pressed, focus-visible halkası, busy iken disabled**

```
const card = document.createElement("button");
card.type = "button";
card.className = "card" + (on ? " sel" : "");
card.setAttribute("aria-pressed", String(on));
card.disabled = busy;
/* CSS */
.card { ...; width: 100%; text-align: left; }
.card:focus-visible { outline: 2px solid var(--teal); outline-offset: 2px; }
.card:disabled { opacity: 0.6; cursor: default; }
```

**7. Modallar: openModal/closeModal (odak + inert + Escape + role=dialog) ve confirm-body pre-wrap**

```
const KABUK = () => [...document.querySelectorAll("header, main, footer")];
let sonOdak = null;
function openModal(id, focusId) {
  sonOdak = document.activeElement;
  $(id).hidden = false;
  KABUK().forEach((el) => { el.inert = true; });
  const f = $(focusId); if (f) f.focus();
}
function closeModal(id) {
  $(id).hidden = true;
  const acik = ["about", "guide", "confirm"].some((k) => !$(k).hidden);
  if (!acik) KABUK().forEach((el) => { el.inert = false; }); // KOŞULSUZ kaldır: Başlat yolu kilitlenmesin
  if (sonOdak && typeof sonOdak.focus === "function") sonOdak.focus();
}
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("confirm").hidden) { closeModal("confirm"); confirmCb = null; confirmNoCb = null; return; } // kapat ≠ karar
  for (const k of ["guide", "about"]) if (!$(k).hidden) { closeModal(k); return; }
});
// askConfirm sonu: $("confirm").hidden = false; → openModal("confirm", "confirm-no");
```

**8. Uygulama ('app') penceresi: inner_size + çalışma alanına kırpılmış min_inner_size**

```
fn uygulama_pencere_boyutu(wa_w: f64, wa_h: f64) -> ((f64, f64), (f64, f64)) {
    const PAY: f64 = 40.0;
    ((1280f64.min(wa_w - PAY), 800f64.min(wa_h - PAY)), (1024f64.min(wa_w - PAY), 640f64.min(wa_h - PAY)))
}
let mon = app.get_webview_window("main").and_then(|w| w.current_monitor().ok().flatten())
    .or_else(|| app.primary_monitor().ok().flatten());
let mut b = tauri::WebviewWindowBuilder::new(app, "app", tauri::WebviewUrl::External(parsed))
    .title("PEMF Vet").maximized(true);
if let Some(m) = mon {
    let sf = m.scale_factor(); let wa = m.work_area();
    let ((pw, ph), (mw, mh)) = uygulama_pencere_boyutu(wa.size.width as f64 / sf, wa.size.height as f64 / sf);
    b = b.inner_size(pw, ph).min_inner_size(mw, mh);
} else { b = b.inner_size(1280.0, 800.0); }
let built = b.build();
```

**9. Kapılar: tests/test_launcher_responsive_kapisi.py (statik + Node davranış + mutasyon) ve cargo parite testleri**

```
# tests/test_launcher_responsive_kapisi.py (özet)
def _css_kurali(soyulmus, secici):  # `main {` ... `}` bloğunu döndür
    i = soyulmus.index(f"\n      {secici} {{"); j = soyulmus.index("}", i); return soyulmus[i:j]
def test_KRITIK_main_flex_start_ve_stage_margin_auto():
    s = _soy(UI.read_text(encoding="utf-8"))
    assert "justify-content: flex-start" in _css_kurali(s, "main"), "main içeriği ortalıyor → taşan başlık kaydırılamaz (launcher-1)"
    assert re.search(r"margin:\s*auto 0", _css_kurali(s, ".stage")), ".stage margin:auto yok"
def test_KARSIT_KANIT_main_center_kapiyi_KIRMIZI_yapar():
    s = _soy(UI.read_text(encoding="utf-8")).replace("justify-content: flex-start", "justify-content: center", 1)
    assert "justify-content: flex-start" not in _css_kurali(s, "main")
// main.rs tests:
#[test] fn ana_pencere_boyutu_calisma_alanina_sigar() {
    assert_eq!(ana_pencere_boyutu(911.0, 480.0), ((871.0, 440.0), (700.0, 440.0)));
    assert_eq!(ana_pencere_boyutu(1920.0, 1040.0), ((880.0, 600.0), (700.0, 460.0)));
    let ((w, h), (mw, mh)) = ana_pencere_boyutu(500.0, 300.0); assert!(mw <= w && mh <= h && w >= 640.0);
}
```

**10. Ampirik görünüm-alanı kapısı (isteğe bağlı CI, yerelde zorunlu): headless Edge + 5 viewport ekran görüntüsü ve ölçüm**

```
# öz: her (ekran, viewport) için
# olc = {'baslik_top_main_top_farki': title.top - main.top, 'yatay_tasma': se.scrollWidth - innerWidth, 'link_h': min(.link heights)}
# assert olc['baslik_top_main_top_farki'] >= 0   # launcher-1
# assert olc['yatay_tasma'] <= 0                    # launcher-7/8
# (pointer:coarse emülasyonu ayrı koşu) assert olc['link_h'] >= 44  # launcher-11
```

</details>

**Bağımlılıklar:** Adım 2 (max-height sorgusu) ve adım 3 (minHeight 460) birlikte anlamlı: 460'a inen pencerede içerik adım 1+2 sayesinde kaydırılabilir/sığar; adım 3 tek başına uygulanırsa 460'ta başlık kırpılır (adım 1 olmadan).; Adım 4 (visible:false) adım 3'teki show() çağrısına bağlıdır — adım 4 önce uygulanırsa normal kipte pencere HİÇ görünmez. Sıra: 3 → 4.; Adım 7 (openModal) adım 6'dan bağımsız ama aynı 'erişilebilirlik turunda' cihazda test edilir; adım 9'daki Node testleri `_fonksiyon(ham, imza)` çıkarıcısına dayandığından adım 5/6/7'deki yeni fonksiyonlar `function ad(...) {` imzasıyla ve 6 boşluk girintili `      }` kapanışıyla yazılmalı.; cargo test launcher/ kökünde (workspace Cargo.lock orada; launcher/app altında Cargo.lock yok). Rust toolchain: bootstrap.ps1 (bellek: Portabilite).; Tauri 2.11.5 (registry'de doğrulandı): `Monitor::work_area() -> &PhysicalRect<i32,u32>`, `Monitor::scale_factor()`, `WebviewWindow::current_monitor/primary_monitor`, `AppHandle::primary_monitor`, `WebviewWindow::show/eval` mevcut; `use tauri::{Emitter, Manager}` main.rs:15'te zaten var.; Python kapıları embedded python ile: `PYTHONIOENCODING=utf-8 ..\python.exe -m pytest` (PATH'te python yok — bu oturumda ölçüldü); node yoksa Node tabanlı testler skip.; Mevcut kapılarla uyum: test_launcher_ui_sozdizimi (tüm script node --check), test_self_update_ekran_kilidi (show/startKapisi*/trySelfUpdate imzaları DEĞİŞMEZ), test_client_arayuz_sade_dil (I18N TR değerlerine 'client/SHA-256/cache' girmez; yeni anahtar yok), test_uretici_kimligi (tauri.conf publisher/identifier dokunulmaz), cargo `f5_kapanis_sirasi_estop_ONCE...` ve `guncelleme_ekrani_sirasi_ve_acilis_bekcisi` (on_window_event ve main() sırası korunur).; Adım 8 (app penceresi min boyutu) pf tarafındaki S2 (kabuk-2: 640-767 'rail' düzeni) ile tamamlayıcı — pf düzeltmesi gelmese de app penceresi ≥1024 mantıksal genişlikte açılır.

**Kilitler:**
- tests/test_launcher_responsive_kapisi.py::test_KRITIK_main_flex_start_ve_stage_margin_auto (+KARSIT_KANIT) — main `justify-content: center`a geri dönerse KIRMIZI (launcher-1).
- tests/test_launcher_responsive_kapisi.py::test_KRITIK_olu_680_sorgusu_YOK_max_height_VAR — `max-width: 680px` yeniden eklenirse ya da `max-height` sorgusu silinirse KIRMIZI (launcher-12).
- tests/test_launcher_responsive_kapisi.py::test_KRITIK_tauri_conf_min_yukseklik_ve_visible — minHeight > 460, visible != false, minWidth != 700 ya da identifier değişirse KIRMIZI (launcher-2, launcher-9; identifier bekçisi test_uretici_kimligi ile çift).
- tests/test_launcher_responsive_kapisi.py::test_KRITIK_modal_inert_escape_odak — Escape confirm'de noCb (discard_pending) ÇAĞIRIRSA KIRMIZI; closeModal inert'i kaldırmazsa KIRMIZI (launcher-5 + veri-silme koruması).
- tests/test_launcher_responsive_kapisi.py::test_KRITIK_kartlar_button_aria_pressed — renderCards div'e dönerse ya da busy'de disabled verilmezse KIRMIZI (launcher-4).
- tests/test_launcher_responsive_kapisi.py::test_KRITIK_ikon_dugmeler_etiketli — dört hbtn'den birinde etiketle() eksikse KIRMIZI (launcher-3).
- launcher/app/src/main.rs tests::ana_pencere_boyutu_calisma_alanina_sigar ve ::uygulama_pencere_boyutu_ekrandan_buyuk_OLMAZ — pencere/min boyutu çalışma alanı−40'ı aşarsa KIRMIZI (launcher-2, matris-9).
- launcher/app/src/main.rs tests::guncelleme_ekrani_sirasi_ve_acilis_bekcisi (genişletilmiş) — gunc setup'ta set_size < eval < show sırası bozulur ya da `fn main()` gövdesinden show() kaybolursa KIRMIZI (launcher-9; görünmez pencere koruması).
- Mevcut: launcher/app/src/main.rs tests::f5_kapanis_sirasi_estop_ONCE_yakalama_kill_ONCE_orphan_HARIC — HASTA GÜVENLİĞİ: .setup eklerken on_window_event/E-stop sırası bozulursa KIRMIZI (değişmeden korunur).
- Mevcut: tests/test_launcher_ui_sozdizimi.py (node --check) — yeni JS'te tek bir kaçış hatası ürünü açılmaz kılar; her adımdan sonra koşturulur.
- Yerel yayın-öncesi: tests/launcher_gorunum_alani_olc.py 5 viewport ölçümü (başlık main üstünün altında, yatay taşma yok, coarse'ta hedef ≥44) — CI'da msedge yoksa skip, runbook'ta zorunlu.

**Cihaz testi:**
- 1366×768 @%150 (mantıksal 911×512, görev çubuğu ile 480) laptop: launcher 871×440 açılır, tamamen görünür; s-ready'de 'Profilleri değiştir / Onar / Uygulamayı kaldır' ve footer 'Destek' FAREYLE tıklanır; s-login'de 'Şifremi unuttum / Hesap oluştur / Çevrimdışı başlat' görünür; maximize'da 911×480 içerik başlık kırpılmadan kaydırılır.
- 1366×768 @%125 (1093×614) ve 1920×1080 @%200 (960×540): pencere görev çubuğunun üstünde kalır (alt kenar gizlenmez), yükseklik ≤ çalışma alanı−40.
- 1920×1080 @%100 ve 2560×1440 @%100 maximize: .stage 560/680px, 'GEREKLİ' rozeti ≥11px okunur; hiçbir yatay kaydırma yok.
- Pencereyi elle 700×460'a küçült: header'da logo + 'PEMF Vet' görünür (oturum açık + çevrimdışı rozetiyle), ikon-only düğmelerde hover tooltip (title) çıkar; s-select+dep-notice+hata kaydırılabilir, 'Kullanım profilinizi seçin' başlığı en üstte.
- Yalnız klavye turu (fare çekili): Tab ile TR/EN → Web Sitesi → Kılavuz → Hakkında → kartlar (odak halkası) → Space ile seç → 'Kur ve Başlat' Enter; Onar → onay açılır, Tab yalnız Vazgeç/Devam, Enter=Vazgeç, Escape kapatır (geri çağrı yok); 'Uygulamayı kaldır' onayı açıkken arkadaki Başlat'a Tab ile ulaşılamaz; Kılavuz'da PageDown gövdeyi kaydırır; modal kapanınca odak açan düğmeye döner ve arayüz tamamen tepkili (inert kalkmış).
- Yarım kalan kurulum senaryosu (PEMF_SIMULATE ya da .part dosyası bırakarak): 'Kurulum yarım kaldı' onayında Escape → hiçbir şey silinmez (discard_pending çağrılmaz, .part dosyaları duruyor); 'İptal et' → silinir.
- Self-update (1.9.45 → 1.9.46): `--guncelleme-ekrani` penceresi ilk kareden 640×400, header/footer yok, zıplama/ikinci-uygulama hissi yok (ekran kaydı); işaret silinince kapanır; yeni sürüm 'Hazır!' ile açılır.
- Dokunmatik Windows (Surface/2-in-1 @%200): TR/EN, Web Sitesi, alt bağlantılar ≥44px yüksek; 'Uygulamayı kaldır' Onar'dan ayrık; parmakla yanlış bağlantıya basma yok.
- Uygulama penceresi: Başlat → maximize açılır; 'Geri yükle' → 1280×800 (ya da çalışma alanı−40), 1024×640 altına küçülmez; pf kenar çubuğu (desktop) düzeni ve ACİL DURDUR düğmesi görünür; %150 DPI laptopta pencere ekrana sığar; pencereyi kapat → 'main' açık kalır, backend güvenle durur (E-stop yolu, mevcut davranış).
- Regresyon: seans sürerken (PEMF_SIMULATE=1) launcher penceresini yeniden boyutlandır/modal aç-kapa → backend/seans etkilenmez; 'main'i kapat → safe_stop_coils sırası log'da görünür (mevcut değişmez).

**Açık sorular (sahip kararı):**
- minHeight 540→460 sahip kararı mı? Alternatif: config 540 kalır, yalnız Rust dinamik olarak küçük çalışma alanında 440-460'a iner (adım 3 taslağı iki durumu da destekler; 460 statik taban daha öngörülebilir).
- pointer:coarse'ta 'Uygulamayı kaldır'ı `margin-left:auto` ile sağa ayırmak yerine ayrı satıra almak tercih edilir mi (görsel karar)?
- Escape'in confirm'de HİÇBİR geri çağrı çalıştırmaması (kapat ≠ karar) — özellikle 'Kurulum yarım kaldı' onayı için doğru mu, yoksa Escape orada da 'Devam Et'e (veri korunur) eşlenmeli mi?
- launcher-9 için `visible:false`: macOS/Linux paketleri (dmg/deb/appimage) aynı setup yolunu kullanıyor — oralarda show() davranışı cihazda doğrulanmadı; Linux canlı kurulum varsa (bellek: Vet Native Linux) bir kez elle bakılmalı.
- Ampirik görünüm-alanı betiği (adım 10) CI'ya mı yalnız yerel runbook'a mı? CI runner'da msedge yoksa kapı skip olur (bellek: 'Kapı Ortam Varsayımı → ÇOĞUNLUK').

**Toplam efor:** ~15.5 saat

### W — Web sitesi (17 bulgu: 1 yüksek / 6 orta / 10 düşük)

Bağlı bulgular: `site-1`, `site-2`, `site-3`, `site-4`, `site-5`, `site-6`, `site-7`, `site-8`, `site-9`, `site-10`, `site-11`, `site-12`, `site-13`, `site-14`, `site-15`, `site-16`, `ampirik-1`

**Hedef:** 320-360 px telefonda hiçbir sayfa yatay taşmasın (document.scrollWidth === innerWidth); 768-1023 tablet dikeyde başlık sıkışmasın; iOS Safari'de giriş/kayıt modalı klavye ve araç çubuğuyla erişilebilir kalsın, input odağında yakınlaşma olmasın; dokunma hedefleri ≥ 40-44 px; fiyat tablosu mobilde satır etiketi kaybetmeden kaydırılsın; site temasının OS temasından bağımsız kalması; tüm bunlar mevcut vitest kapılarını (14 dosya) ve indirme-kapısı/auth akışını bozmadan, her adım ayrı commit ve geri alınabilir olarak.

**Tasarım kararları:**
- `dark:` KARARI — varyant TANIMLAMA, sınıfları KALDIR: site tek koyu temadır (index.css 16, 44-47); `@custom-variant dark` + `<html class="dark">` OS bağını koparır ama kodda hiç var olmayan bir açık tema için ikinci renk seti taşımaya devam eder. Bunun yerine 10 kullanım (AccountButton 130/148/149, AuthModal 246/264, Download 141, Odeme 183, Pricing 36/37, ResetPassword 70) token'a taşınır: @theme'e `--color-danger` eklenir, `text-warning` / `text-success` / `text-danger` kullanılır; yeni vitest kapısı `src/` içinde `dark:` görünmesini yasaklar (tek-tema değişmezi kilitlenir). Opsiyonel: `html { color-scheme: dark }` (yerel form kontrolleri/kaydırma çubuğu koyu). Sahip aksini isterse tek satırlık varyant alternatifi adım 6'da not edilmiştir.
- Header kırılımı lg (1024): 768-1023 arasında tablet kullanıcısı hamburger görür — dokunmatik için daha uygun ve içerik ~803 px istediğinden md'de sığdırma mümkün değil. Alternatif (CTA'yı ikona indirme) reddedildi: 'PEMF Vet’i İndir' metni sade-dil.test.ts:82 çapasıdır ve pazarlama CTA'sı gizlenmemeli.
- Tailwind v4 KATMAN SIRASI (kritik): `@import 'tailwindcss'` → theme < base < components < utilities; katmansız CSS hepsini yener. `.input { font-size }` components katmanında, `text-sm` utilities katmanında → 16 px input kuralı `@layer base` içine yazılırsa KAYBEDER. Bu yüzden `@media (pointer: coarse)` ve `prefers-reduced-motion` blokları index.css sonunda KATMANSIZ yazılır (yorumla gerekçelendirilir). `maximum-scale=1` ASLA kullanılmaz (yakınlaştırma erişilebilirliği).
- Tablo: ilk sütun `sticky left-0` + sağ kenar gradyan ipucu + '← kaydırın →' (AppScreenshots:82 deseniyle aynı). `border-collapse` + sticky Chrome'da satır çizgisini sticky hücrenin altında kaybettirir → tablo `border-separate border-spacing-0`, `border-b` tr'den th/td'ye taşınır. Sticky hücre zemini `bg-bg-soft/50` bölüm zeminiyle birebir eşleşsin diye `color-mix(in oklch, var(--color-bg-soft) 50%, var(--color-bg))` utility'si eklenir. Mobil kart görünümü (COMPARE→liste) bu turda YAPILMAZ (FREE_MODE fiyat tutarsızlığı ayrı iş, bkz. açık sorular).
- AuthModal: `max-h-[90vh]` → `max-h-[calc(100svh-2rem)] sm:max-h-[calc(100dvh-2rem)]` (mobilde svh = araç çubuğu görünürken de sığar; sm+ dvh); overlay `overflow-y-auto` + `place-items-start sm:place-items-center`; gönder düğmesi form (zaten overflow-y-auto) içinde `sticky bottom-0`. Odak-hapsi efektine ve `auth-modal-focus.test.ts` çapalarına ('// Esc ile kapat + odağı diyaloğa al', 'const isSignup', yorumdaki 'window.confirm') DOKUNULMAZ.
- Kanıt zinciri: her düzeltme (1) kaynak-metin vitest kapısı (projede jsdom yok; mevcut `?raw` + `kaynakSoy` deseni), (2) CDP ölçümü (scratchpad'deki cdp_eval.py, `Emulation.setDeviceMetricsOverride` ile — `--window-size` GEÇERSİZ, rapor §9 notu), (3) Vercel önizleme URL'sinde gerçek cihaz. Ampirik kapı = 320/360/390/640×360/768/911×512/1024/1280/1920/2560'ta scrollWidth === innerWidth.
- Mevcut desenler tercih: `md:hidden` ipucu paragrafı (AppScreenshots), `btn-primary text-sm` (Header ölçüsü), `min-w-0` + `truncate` (LauncherMock), `shrink-0` düğme grupları; yeni bileşen/kütüphane YOK, bağımlılık eklenmez (CSP ve KVKK notu: dış istek yok).
- Geniş ekran (site-14) en düşük öncelik ve en son: 20 `max-w-6xl` kullanımına `2xl:max-w-7xl` ek sınıfı (sed ile, metin kapılarını etkilemez); tek `.wrap` utility'sine toplama bu turda yapılmaz (diff büyür, kazanç kozmetik).

| # | Adım | Dosyalar | Değişiklik | Kapattığı | Doğrulama | Risk | Efor (s) |
|---|---|---|---|---|---|---|---|
| 0 | Taban çizgisi: test/lint/build yeşil + CDP ölçüm işleri hazır | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\package.json`, `C:\Users\merta\AppData\Local\Temp\claude\c--Users-merta-Downloads-python-3-10-2-embed-amd64\5c8db92a-75b8-4d12-a3bd-48cc304d47b5\scratchpad\responsive\cdp_eval.py`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\scripts\responsive\jobs_site.json (YENİ, isteğe bağlı)` | Kod değişikliği yok. `npm test`, `npm run lint`, `npx tsc -b`, `npx vite build` koşulup yeşil olduğu kaydedilir. `npx vite preview --port 4173` ile yerel derleme açılır; cdp_eval.py için bir iş listesi (jobs_site.json) hazırlanır: /, /features, /pricing, /download, /support + AuthModal açık durumu (js: document.queryS… |  | Komut çıktıları: 14 vitest dosyası geçer; CDP baseline 320×568 → innerWidth=391 (bulgu yeniden üretildi). Bu ölçüm sonraki adımların 'yeşil' karşılaştırma tabanıdır. | Yok (salt okuma/ölçüm). Edge headless başlatılamazsa `EDGE` yolu güncellenir; `--hide-scrollbars` ölçümü etkilemez. | 0.5 |
| 1 | YÜKSEK: LauncherMock sarmalayıcısına min-w-0 — 320/360 px'te sayfa yatay taşması | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\pages\Home.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\pages\Features.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\components\LauncherMock.tsx` | Home.tsx:51 ve Features.tsx:63 `<div className="lg:pl-6">` → `<div className="min-w-0 lg:pl-6">` (grid öğesinin otomatik minimumu sıfırlanır; track kapsayıcı genişliğine iner, iç `span.min-w-0 + truncate` alt başlığı '…' ile kısaltır). Ek güvence (kök nedende): LauncherMock.tsx:48 `<span className="min-w-0">` → `<span… | `ampirik-1`, `site-12` | CDP: 320×568 ve 360×800 (mobile:true) için `/` ve `/features` → sw === innerWidth (391→320/360) ve `.glow-ring` genişliği ≤ 280/320; giriş modalı açıkken 'Şifremi unuttum' getBoundingClientRect().rig… | Çok düşük. lg+ (2 sütun) düzeninde grid sütunu 1fr olduğundan görsel değişim yok. Geri alma: iki satırlık sınıf değişikliği, `git revert`. | 0.5 |
| 2 | Header: masaüstü nav lg'ye, nowrap, drawer kaydırma kabı, dokunma hedefleri | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\components\Header.tsx` | Header.tsx: 21 `hidden items-center gap-1 md:flex` → `hidden items-center gap-1 lg:flex`; 27 NavLink `px-3 py-2` → `px-3 py-2.5` (hedef 40 px, tablet dokunmatik); 37 `hidden items-center gap-3 md:flex` → `... lg:flex`; 39 CTA `btn-primary text-sm` → `btn-primary text-sm whitespace-nowrap`; 46 hamburger `md:hidden` → `… | `site-1`, `site-2`, `site-11` | CDP 768×1024 ve 820×1180: `nav` display none, hamburger görünür; 1024×768: nav görünür ve `header` yüksekliği 64 px (düğme iki satıra kırılmadı: CTA getBoundingClientRect().height ≤ 44). 640×360 yata… | Düşük. 768-1023'te tablet kullanıcısı artık hamburger görür (sahip UX kararı; bkz. açık soru 2). Drawer overflow'u AccountButton menüsünü (absolute) kırpabilir… | 1 |
| 3 | AccountButton: menü genişlik sınırı + drawer'da akışa alınan (inline) menü + 12 px bilgi metni | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\components\AccountButton.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\components\Header.tsx` | AccountButton.tsx:23 imza `{ onNavigate, inline }: { onNavigate?: () => void; inline?: boolean }`; 58 ve 81 `btn-ghost text-sm` → `btn-ghost text-sm whitespace-nowrap` (site-1 tamamlayıcı; inline'da `w-full` eklenir); 91 menü sınıfı: `inline ? 'static mt-2 w-full' : 'absolute right-0 mt-2 w-72 max-w-[calc(100vw-2.5rem… | `site-15`, `site-12`, `site-1` | CDP 320×568 oturum açık simülasyonu zor (Supabase) → kaynak kapısı: vitest `inline ? 'static` ve `max-w-[calc(100vw-2.5rem)]` var, `text-[11px]` AccountButton'da YOK. Manuel: Vercel önizlemede test h… | Düşük; oturum açmış kullanıcı yolu. Geri alma: prop varsayılanı false → eski davranış; tek dosya revert. | 0.75 |
| 4 | index.css + App.tsx + AppScreenshots: dokunmatikte 16 px input (katmansız), hareket-azalt, anında kaydırma | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\index.css`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\App.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\components\AppScreenshots.tsx` | index.css SONUNA (tüm @layer bloklarından sonra, KATMANSIZ — components'teki `.input{font-size:.875rem}` ve utilities'teki `text-sm`'i yenmesi için; gerekçe yorum olarak yazılır): `@media (pointer: coarse) { input:not([type=checkbox]):not([type=radio]), select, textarea { font-size: max(1rem, 1em); } }` — AuthModal FI… | `site-3`, `site-4` | CDP: mobile:true + `Emulation.setTouchEmulationEnabled {enabled:true}` sonra `matchMedia('(pointer: coarse)').matches === true` (ön koşul) ve modal açıkken `getComputedStyle(document.querySelector('i… | Düşük. `input` seçicisi checkbox/radio dışlanır (Pricing:96 accent kutusu büyümesin). `transition-duration .01ms` btn hover'ı etkilemez (yalnız reduce tercihin… | 0.75 |
| 5 | AuthModal: svh/dvh yükseklik, kaydırılabilir overlay, yapışkan gönder düğmesi, 'Şifremi unuttum' hedefi | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\context\AuthModal.tsx` | AuthModal.tsx:215 overlay `fixed inset-0 z-[100] grid place-items-center bg-black/60 p-4 backdrop-blur-sm` → `fixed inset-0 z-[100] grid place-items-start overflow-y-auto bg-black/60 p-4 backdrop-blur-sm sm:place-items-center`; 224 diyalog `card flex max-h-[90vh] w-full max-w-md flex-col p-7` → `card flex max-h-[calc(… | `site-13`, `site-11` | `npm test` → auth-modal-focus.test.ts 6 test geçer (çapalar korunur); metin-guveni AuthModal metinlerine bakar, değişmedi. CDP 360×640 mobile:true, modal + 'Kayıt olun' + Veteriner Hekim seçili: diya… | Orta-düşük: giriş/indirme kapısı akışı (requireAuth → pendingRef → indirme) bu dosyada; yalnız JSX sınıfları ve bir sarmalayıcı div değişir, mantık satırlarına… | 1 |
| 6 | Tek koyu tema: `dark:` çiftlerini token'a taşı + `--color-danger` + kapı | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\index.css`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\components\AccountButton.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\context\AuthModal.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\pages\Download.tsx` | index.css @theme (33-34) altına `--color-danger: oklch(70% 0.19 25);` (≈ red-400, koyu zeminde ≈ 6:1); isteğe bağlı `html { color-scheme: dark; }` @layer base'e. Sonra 10 yerde: `text-amber-700 dark:text-amber-300` / `text-amber-600 dark:text-amber-400` → `text-warning`; `text-emerald-700 dark:text-emerald-300` / `tex… | `site-10` | `grep -rn 'dark:' src --include=*.tsx` → 0. Vitest (adım 12): `import.meta.glob('../**/*.tsx', {query:'?raw', eager:true})` ile tüm bileşenlerde `dark:` yok (tek-tema değişmezi) — MUTASYON: bir dosya… | Çok düşük (yalnız renk sınıfları). Odeme.tsx metin kapıları (odeme-donem-bedeli, metin-guveni) sınıf değil metin okur. Geri alma: revert. | 0.75 |
| 7 | Pricing: yapışkan ilk sütun + kenar gradyanı + kaydırma ipucu; fiyat kartı hizası; kurumsal kart lg; pill hedefleri | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\pages\Pricing.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\index.css` | (a) Tablo 159-181: sarmalayıcı `mt-8 overflow-x-auto` → `relative mt-8`; içine `<div className="overflow-x-auto overscroll-x-contain">`; sağ kenar ipucu: `<div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-bg-soft to-transparent md:hidden" />`; tablo `w-full min-w-[56… | `site-5`, `site-6`, `site-7`, `site-11` | CDP 320×568 ve 390×844 /pricing: tablo sarmalayıcı `scrollLeft = 200` sonrası ilk sütundaki 'Aylık jeton hakkı' hücresi getBoundingClientRect().left ≥ 0 (yapışık), body sw === innerWidth (sayfa genel… | Düşük; tablo yapısal değişikliği (border-separate) görünümü 1 px kadar değiştirebilir → görüntü karşılaştır. Geri alma: revert. Not: FREE_MODE bandı 'ücretsiz'… | 1.5 |
| 8 | PackageBuilder: 'Önerilen' rozetini akışa al (başlık üstüne binme) | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\components\PackageBuilder.tsx` | PackageBuilder.tsx:41-55: `absolute right-4 top-4` rozet kaldırılır; başlık satırı `<div className="flex items-center gap-3">` içine: onay kutusu (shrink-0), `<span className="min-w-0 flex-1 text-lg font-bold">{m.name}</span>`, ardından `{m.recommended && <span className="shrink-0 rounded-full bg-primary/15 px-2 py-0.… | `site-8`, `site-12` | CDP 768×1024 ve 820×1180 /pricing: 'Veteriner Hekim' başlık span'ı ile 'Önerilen' rozetinin getBoundingClientRect() dikdörtgenleri KESİŞMİYOR (right(başlık) ≤ left(rozet)). Vitest: PackageBuilder'da … | Çok düşük. Geri alma: revert. | 0.5 |
| 9 | Download: kart ızgarası xl, CTA text-sm nowrap, bilgi satırı hizası, 12 px Android notu, dokunma hedefleri | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\pages\Download.tsx` | Download.tsx:39 kart `card flex flex-col p-7` → `card flex flex-col p-5 xl:p-7`; 57 düğme sınıfına `text-sm whitespace-nowrap` (Header CTA ölçüsü, ~180 px ≤ iç alan); 67 'Yakında' span'ına da `text-sm`; 76 'Çıkınca haber ver' `mt-2 text-center text-xs ...` → `mt-1 inline-flex min-h-11 items-center justify-center text-… | `site-9`, `site-11`, `site-12` | `npm test` → download-gate-wiring 3 test geçer. CDP 1024×768 ve 1280×800 /download: birincil düğme `getClientRects().length === 1` (tek satır) ve yükseklik ≤ 44; 320×568: 'Çıkınca haber ver' yüksekli… | Düşük; indirme kapısı düğmeleri yalnız sınıf değişir (onClick/download aynı). Geri alma: revert. | 0.75 |
| 10 | Footer: dar ekranda tek sütun + bağlantı dokunma hedefleri | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\components\Footer.tsx` | Footer.tsx:30 `grid grid-cols-2 gap-x-10 gap-y-2 text-sm text-muted` → `grid grid-cols-1 gap-y-6 text-sm text-muted min-[400px]:grid-cols-2 min-[400px]:gap-x-6 sm:gap-x-10`; 31/37 sütunlar `flex flex-col gap-2` → `flex flex-col gap-1`; 34/40 Link `hover:text-fg` → `inline-block py-1.5 hover:text-fg` (hedef 32 px, adım… | `site-16`, `site-11` | CDP 320×568: Footer Link'lerinin her biri `offsetHeight ≥ 32` ve 'İptal, İade ve Cayma Hakkı' `getClientRects().length === 1`; 390×844: iki sütun. Ekran görüntüsü 320/390. `npm test` (Footer'ı okuyan… | Çok düşük. Geri alma: revert. | 0.5 |
| 11 | Geniş ekran (≥1536): kapsayıcı 2xl:max-w-7xl, hero tipografisi, sınırlı parıltı | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\pages\Home.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\pages\Features.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\pages\Pricing.tsx`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\components\Header.tsx` | 20 `max-w-6xl` kullanımı (Header 2, Footer 1, Home 4, Features 4, Pricing 8, AppScreenshots 1) → `max-w-6xl 2xl:max-w-7xl` (sed: `s/max-w-6xl/max-w-6xl 2xl:max-w-7xl/g` yalnız bu 6 dosyada; Header/Footer da aynı ölçüye bağlı kalır). Home.tsx:26 başlık `... lg:text-[3.4rem]` → `... lg:text-[3.4rem] 2xl:text-6xl`; 29 pa… | `site-14` | CDP 1920×1080 ve 2560×1440 `/`: `.max-w-6xl` kapsayıcı genişliği 1280 (7xl), 1280×800'de 1152 (değişmedi); görüntü karşılaştırması. `npm run lint` + `npx vite build` (CSS `min()` derlenir). Metin kap… | Çok düşük, kozmetik; en son ve bağımsız commit — sahip beğenmezse tek revert. | 0.75 |
| 12 | Kapı + kanıt: vitest `responsive-kapilari.test.ts`, CDP tam tur, Vercel önizleme + cihaz turu | `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\__tests__\responsive-kapilari.test.ts (YENİ)`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\pemf-vet-web\src\__tests__\_soyucu.ts`, `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\docs\responsive-denetim-2026-09-04.md` | Yeni kaynak-metin kapısı (mevcut desen: `?raw` import + `kaynakSoy`, node:fs YOK — tsc -b test dosyalarını da derler): (1) tek-tema: tüm `src/**/*.tsx` (import.meta.glob eager ?raw) içinde `dark:` yok; (2) LauncherMock sarmalayıcıları: Home/Features'ta `<LauncherMock` öncesindeki açılış div'inde `min-w-0`; (3) Header … | `ampirik-1`, `site-1`, `site-2`, `site-3`, `site-4`, `site-5`, `site-8`, `site-9`, `site-10`, `site-11`, `site-12`, `site-13`, `site-14`, `site-15`, `site-16`, `site-6`, `site-7` | `npm test` 15 dosya yeşil + her yeni kapı için mutasyon kanıtı (commit mesajında); `npx tsc -b`, `npm run lint`, `npx vite build` yeşil (site-ci ile aynı sıra, Node 22). CDP tam tur: 11 viewport × 5 … | Kapı çok sıkı yazılırsa gelecekteki refaktörde yanlış-kırmızı (memory: yapısal çıpa kırılganlığı) → çıpalar sınıf adına değil semantik koşula (regex) pinlenir … | 1.5 |

<details><summary>Kod taslakları</summary>

**1. YÜKSEK: LauncherMock sarmalayıcısına min-w-0 — 320/360 px'te sayfa yatay taşması**

```
// Home.tsx:51 / Features.tsx:63
<div className="min-w-0 lg:pl-6">
  <LauncherMock />
</div>
// LauncherMock.tsx:48
<span className="min-w-0 flex-1">
  <span className="block truncate text-xs font-bold text-white/90">PEMF Vet</span>
  <span className="block truncate text-[10px] text-white/40">Veteriner PEMF seans + yapay zekâ teşhis platformu</span>
</span>
```

**2. Header: masaüstü nav lg'ye, nowrap, drawer kaydırma kabı, dokunma hedefleri**

```
<nav className="hidden items-center gap-1 lg:flex"> ... `rounded-md px-3 py-2.5 text-sm font-medium ...` </nav>
<div className="hidden items-center gap-3 lg:flex">
  <AccountButton />
  <Link to="/download" className="btn-primary text-sm whitespace-nowrap"><Download className="h-4 w-4" />PEMF Vet’i İndir</Link>
</div>
<button className="grid h-10 w-10 place-items-center rounded-md text-muted hover:text-fg lg:hidden" ...>
{open && (
  <div className="max-h-[calc(100vh-4rem)] max-h-[calc(100dvh-4rem)] overflow-y-auto overscroll-contain border-t border-border/70 bg-bg-soft lg:hidden">
    <nav className="mx-auto flex max-w-6xl flex-col gap-1 px-5 py-4"> ... `rounded-md px-3 py-3 text-sm font-medium ...`
      <div className="mt-2 px-3"><AccountButton inline onNavigate={() => setOpen(false)} /></div>
```

**3. AccountButton: menü genişlik sınırı + drawer'da akışa alınan (inline) menü + 12 px bilgi metni**

```
export default function AccountButton({ onNavigate, inline = false }: { onNavigate?: () => void; inline?: boolean }) {
  ...
  const menuCls = inline
    ? 'static mt-2 w-full'
    : 'absolute right-0 z-50 mt-2 w-72 max-w-[calc(100vw-2.5rem)]'
  ...
  <div role="menu" className={`${menuCls} rounded-xl border border-border bg-bg p-4 text-left shadow-xl`}>
  ...
  <div className="mt-1 text-xs leading-relaxed text-muted">{jeton.aylikHak...}</div>
```

**4. index.css + App.tsx + AppScreenshots: dokunmatikte 16 px input (katmansız), hareket-azalt, anında kaydırma**

```
/* ⚠️ KATMANSIZ (bilerek): Tailwind v4'te theme<base<components<utilities; `.input` (components) ve
   `text-sm` (utilities) bu kuralı yenmesin diye @layer DIŞINDA. iOS Safari <16px input odağında
   yakınlaştırır; maximum-scale=1 ile ÇÖZÜLMEZ (erişilebilirlik). */
@media (pointer: coarse) {
  input:not([type='checkbox']):not([type='radio']), select, textarea { font-size: max(1rem, 1em); }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto !important; }
  *, *::before, *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; }
}
// App.tsx
window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
```

**5. AuthModal: svh/dvh yükseklik, kaydırılabilir overlay, yapışkan gönder düğmesi, 'Şifremi unuttum' hedefi**

```
<div className="fixed inset-0 z-[100] grid place-items-start overflow-y-auto bg-black/60 p-4 backdrop-blur-sm sm:place-items-center" onMouseDown={...}>
  <div ref={dialogRef} role="dialog" ... className="card flex max-h-[calc(100svh-2rem)] w-full max-w-md flex-col p-5 sm:max-h-[calc(100dvh-2rem)] sm:p-7">
    ...
    <button type="button" onClick={handleReset} disabled={busy} className="inline-flex min-h-11 items-center px-2 -mr-2 text-xs text-muted hover:text-primary disabled:opacity-60">Şifremi unuttum</button>
    ...
    <div className="sticky bottom-0 -mx-0.5 bg-bg-soft pt-2">
      <button type="submit" disabled={busy || !ready} className="btn-primary w-full disabled:opacity-60">{busy ? 'Lütfen bekleyin…' : isSignup ? 'Kayıt ol' : 'Giriş yap'}</button>
    </div>
```

**6. Tek koyu tema: `dark:` çiftlerini token'a taşı + `--color-danger` + kapı**

```
/* index.css @theme */
--color-danger: oklch(70% 0.19 25);
/* AccountButton.tsx:146-150 */
sonuc.ok
  ? 'border-emerald-500/40 bg-emerald-500/10 text-success'
  : 'border-red-500/40 bg-red-500/10 text-danger'
/* AuthModal.tsx:246 */
<p className="text-sm text-warning">Girdiğiniz bilgiler kaybolacak. Pencere kapatılsın mı?</p>
```

**7. Pricing: yapışkan ilk sütun + kenar gradyanı + kaydırma ipucu; fiyat kartı hizası; kurumsal kart lg; pill hedefleri**

```
<div className="relative mt-8">
  <div className="overflow-x-auto overscroll-x-contain">
    <table className="w-full min-w-[560px] border-separate border-spacing-0 text-sm">
      <thead><tr>
        <th className="sticky left-0 z-10 min-w-[140px] bg-table-sticky border-b border-border py-3 pr-3 text-left font-medium text-muted"></th>
        {PLANS.map((c) => <th key={c.tier} className={`border-b border-border px-3 py-3 text-center font-bold ${c.highlight ? 'text-primary' : ''}`}>{c.name}</th>)}
      </tr></thead>
      <tbody>{COMPARE.map((row) => (
        <tr key={row.label}>
          <td className="sticky left-0 z-10 bg-table-sticky border-b border-border/60 py-3 pr-3 font-medium">{row.label}</td>
          ...
  </div>
  <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-bg-soft to-transparent md:hidden" />
</div>
<p className="mt-2 text-center text-xs text-muted/70 md:hidden">← kaydırın →</p>
```

**8. PackageBuilder: 'Önerilen' rozetini akışa al (başlık üstüne binme)**

```
<div className="flex items-center gap-3">
  <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-md border transition-colors ${on ? ... : ...}`}><Check className="h-4 w-4" /></span>
  <span className="min-w-0 flex-1 text-lg font-bold">{m.name}</span>
  {m.recommended && (
    <span className="shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-xs font-semibold text-primary">Önerilen</span>
  )}
</div>
```

**9. Download: kart ızgarası xl, CTA text-sm nowrap, bilgi satırı hizası, 12 px Android notu, dokunma hedefleri**

```
className={`mt-6 ${primary ? 'btn-primary' : 'btn-ghost'} text-sm whitespace-nowrap cursor-pointer disabled:cursor-wait disabled:opacity-60`}
...
<div className="flex items-start gap-1.5"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" /> Sürüm {version} · {CLIENT.releaseDate}</div>
...
<div className="mx-auto mt-10 grid max-w-5xl gap-5 sm:grid-cols-2 xl:grid-cols-4">
```

**10. Footer: dar ekranda tek sütun + bağlantı dokunma hedefleri**

```
<div className="grid grid-cols-1 gap-y-6 text-sm text-muted min-[400px]:grid-cols-2 min-[400px]:gap-x-6 sm:gap-x-10">
  <div className="flex flex-col gap-1">
    <div className="text-xs font-semibold uppercase tracking-wide text-fg/60">Menü</div>
    {NAV.map((n) => <Link key={n.to} to={n.to} className="inline-block py-1.5 hover:text-fg">{n.label}</Link>)}
```

**11. Geniş ekran (≥1536): kapsayıcı 2xl:max-w-7xl, hero tipografisi, sınırlı parıltı**

```
<div className="mx-auto grid max-w-6xl 2xl:max-w-7xl items-center gap-12 px-5 py-20 sm:px-6 lg:grid-cols-2 lg:py-28">
<h1 className="mt-5 text-4xl font-extrabold leading-[1.08] sm:text-5xl lg:text-[3.4rem] 2xl:text-6xl">
/* index.css */ radial-gradient(min(60%, 900px) 55% at 50% 0%, ...)
```

**12. Kapı + kanıt: vitest `responsive-kapilari.test.ts`, CDP tam tur, Vercel önizleme + cihaz turu**

```
import { describe, it, expect } from 'vitest'
import { kaynakSoy } from './_soyucu'
import HEADER from '../components/Header.tsx?raw'
import CSS from '../index.css?raw'
const TSX = import.meta.glob('../**/*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('site tek koyu tema', () => {
  it('hiçbir bileşen dark: varyantı kullanmaz (OS teması siteyi değiştiremez)', () => {
    for (const [ad, src] of Object.entries(TSX)) expect(kaynakSoy(src), `${ad}: dark: kaldır, text-warning/success/danger kullan`).not.toMatch(/\bdark:/)
  })
})
describe('index.css dokunmatik input kuralı katmansız', () => {
  it('pointer: coarse bloğu son @layer kapanışından sonra gelir', () => {
    const i = CSS.indexOf('@media (pointer: coarse)'); const j = CSS.lastIndexOf('@layer')
    expect(i).toBeGreaterThan(-1); expect(i, 'kural @layer içine girmiş → .input/text-sm onu yener').toBeGreaterThan(j)
  })
})
```

</details>

**Bağımlılıklar:** Yerel: Node ≥22 (site-ci ile aynı; Node 20'de supabase import'u WebSocket yüzünden düşer), `npm ci` tamam; embedded python (C:\...\python-3.10.2-embed-amd64\python.exe — PATH'te `python` YOK) + `websocket-client` paketi ve Edge (C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe) cdp_eval.py için.; cdp_eval.py şu an yalnız oturum scratchpad'inde (…\scratchpad\responsive\cdp_eval.py); depoya alınmazsa oturum sonunda kaybolur → adım 0'da kopyalama kararı.; CI: yalnız kök .github/workflows/site.yml (paths: pemf-vet-web/**) — check:legal → lint → tsc -b → vitest → vite build; yeni test dosyası `?raw` deseni kullanmalı (node:fs → TS2591 ile build düşer).; Vercel: production dalı production-hardening (memory: PEMF Tek Depo); PR dalı `fix/site-responsive-2026-09-04` önizleme URL'si üretir; canlıya alma sahip onayıyla (dış servise yayın).; Sıra bağımlılığı: adım 2 (Header drawer overflow) ↔ adım 3 (AccountButton inline) birlikte yayınlanmalı; adım 6 (token) adım 5'ten önce ya da sonra fark etmez ama AuthModal iki kez dokunulur → aynı PR.; Tasarım tokenları index.css @theme'de (bg 13%, bg-soft 16%, warning, success); `--color-danger` yeni.

**Kilitler:**
- HASTA GÜVENLİĞİ: site ACİL DURDUR/seans akışı içermez; ancak İNDİRME KAPISI ve GİRİŞ akışı (AuthModal pendingRef → requireAuth → download) değişmez — download-gate-wiring.test.ts: Download.tsx/DownloadButtons.tsx'te `href={` ve `.url` YASAK, `onClick={() => download(` ŞART.
- auth-modal-focus.test.ts çapaları: '// Esc ile kapat + odağı diyaloğa al' yorumu, 'const isSignup', efekt `}, [])`, `requestCloseRef.current()`, yorumdaki 'window.confirm' metni — AuthModal'da bu satırlara DOKUNMA.
- sade-dil.test.ts:82 Header'da /PEMF Vet['’]i İndir/ metni kalmalı (CTA ikona indirilemez, metin gizlenemez).
- metin-guveni / odeme-donem-bedeli / hesap-ve-kalanlar kapıları Home/Pricing/Download/AuthModal/Odeme/ResetPassword/config ham metnini okur → yalnız className değiştir, kullanıcıya görünen metin ekleme/çıkarma YAPMA ('← kaydırın →' hariç; aynı metin AppScreenshots'ta zaten kapıdan geçiyor).
- index.html viewport'a `maximum-scale=1` / `user-scalable=no` EKLENMEZ (erişilebilirlik); Google Fonts geri EKLENMEZ (KVKK notu, index.html 40-48).
- FREE_MODE=true, jeton/satış metinleri, LEGAL_DOCS, COMPANY alanları (check-legal kapısı) değişmez.
- LauncherMock: gerçek client'a göre çizilmiş maket; e-posta/kimlik alanı EKLENMEZ, 'Kurulumu onar/Uygulamayı kaldır' metinleri launcher I18N ile aynı kalır.
- Vercel CSP (vercel.json): dış script/style eklenmez; tüm CSS yerel.
- Commit disiplini: her adım ayrı commit, pre-commit formatlayıcı commit'i sessizce iptal edebilir → `git log -1` doğrula (memory).

**Cihaz testi:**
- iPhone SE/13 Safari (a, b, j): / ve /features 320-390 px'te yatay kaydırma yok; giriş modalında e-posta alanına odak → yakınlaşma YOK; kayıt → Veteriner Hekim formunda klavye açıkken 'Kayıt ol' düğmesi ulaşılabilir; araç çubuğu görünürken 'Kayıt olun' satırı ekranda.
- iPhone SE yatay 667×375 (c): hamburger → drawer kayıyor, 'PEMF Vet’i İndir' CTA'ya ulaşılıyor; oturum açıkken Hesabım menüsü drawer içinde akışta.
- Android Chrome 360 px, sistem yazı ölçeği 1.3 (a, i): ana sayfa taşma yok; /download Android notu okunur (12 px+); footer tek sütun 320'de / iki sütun 400+.
- iPad dikey 768×1024 (d): başlıkta hamburger; /pricing 'Önerilen' rozeti başlığı örtmüyor; kurumsal kart dikey düzen; tablo ilk sütun yapışık + sağ gradyan.
- iPad yatay / 1024×768 (d, e): masaüstü nav tek satır, düğmeler tek satır; fiyat kartları 2×2, 'Seç' düğmeleri hizalı; /download kartları 2×2, CTA tek satır.
- Windows dizüstü 1366×768 @%150 (g, 911 mantıksal): başlık hamburger, kurumsal kart dikey, hiçbir taşma; 1920 ve 2560 monitör (f): kapsayıcı 1280, parıltı sınırlı.
- OS teması AÇIK olan Windows/macOS'ta (h): Pricing?checkout=error bandı, AuthModal kapatma onayı ve Hesabım iptal mesajı koyu tema renginde (OS'tan bağımsız).
- prefers-reduced-motion açık (Windows 'Animasyon efektleri' kapalı): sayfa geçişinde kayma animasyonu yok, galeri ok düğmeleri anında kaydırır.

**Açık sorular (sahip kararı):**
- `dark:` kararı: öneri 'sınıfları kaldır + token' (adım 6). Sahip ileride gerçek açık tema planlıyorsa `@custom-variant dark (&:where(.dark, .dark *))` + `<html class="dark">` yolu tercih edilmeli — hangisi?
- Header 768-1023 px'te hamburger kabul edilebilir mi (iPad dikey artık masaüstü nav görmez)? Alternatif: bu aralıkta 'Giriş yap' düğmesini drawer'a taşıyıp nav'ı md'de tutmak (ölçüm: nav 351 + logo 108 + CTA 179 + oluk 48 + gap ≈ 700 → sığar) — istenirse adım 2 buna göre değişir.
- Pricing tablosu: mobilde kart/liste görünümü (COMPARE→plan başına liste) istenir mi? Bu turda yalnız sticky sütun + ipucu yapılıyor. Ayrıca FREE_MODE bandı 'ücretsiz' derken tablo/kartların ₺ göstermesi (rapor gözlemi) iş kuralı kararı bekliyor — bu plan kapsamı dışı.
- LauncherMock alt başlığı ('Veteriner PEMF seans + yapay zekâ teşhis platformu') <400 px'te '…' ile kısalacak; tamamen gizlensin mi (`hidden min-[400px]:block`)?
- cdp_eval.py + iş listesi depoya (pemf-vet-web/scripts/responsive/) alınsın mı, yoksa yalnız yerel ölçüm aracı olarak mı kalsın? CI'ya eklenmesi önerilmiyor (Edge + python bağımlılığı).
- Bulgular JSON'unda 'ikinci' alanı yok (görev tanımı 'ikinci.karar/tekrar' bekliyordu); tekrar eşlemesi rapor §8 satır 386'dan alındı — doğru mu, yoksa güncel bir JSON sürümü mü var?
- Vercel önizlemede gerçek cihaz turu için test hesabı (Supabase) — AccountButton/inline menü doğrulaması oturum gerektirir; hangi hesap kullanılacak?

**Toplam efor:** ~11 saat

## 6. CI kapısı: görünüm alanı + dokunma hedefi

CI GÖRÜNÜM-ALANI + DOKUNMA-HEDEFİ KAPISI — tasarım (yalnız okundu; hiçbir depo dosyası değiştirilmedi)

##### 0. Ampirik ön-doğrulama (bu turda scratchpad'de yapıldı, depoya DOKUNULMADI)
Taslak betik `scratchpad\responsive_kapisi.py` olarak yazıldı ve gömülü `python.exe` (3.10.2, stdlib) ile **gerçekten koşturuldu**:
- **Yöntem yeniden kullanıldı:** ampirik ajanın `cdp_shot.py`/`cdp_eval.py` akışı (Edge `--headless=new --remote-debugging-port` → `/json/new` PUT → WS → `Emulation.setDeviceMetricsOverride` → `Runtime.evaluate` → `Page.captureScreenshot`). `--window-size` tek başına görünüm alanını değiştirmediği (504×473) için CDP ŞART — betik bunu belgeliyor.
- **Bağımlılık sorunu çözüldü:** yerelde `websocket-client 1.9.0` + `websockets 15.0.1` gömülü python'da var, ama `requirements-test.txt`'te YOK (CI `pip install -r requirements-test.txt` kurar) ve CI setup-python'da hiçbiri yok → betik **~60 satırlık RFC 6455 metin-çerçeve istemcisi** taşıyor (`CdpWs`: el sıkışma, maskeli gönderim, 126/127 uzunluk, ping→pong, parça birleştirme; Origin başlığı bilerek gönderilmez — Chrome 403 tuzağı). Ekran görüntüsü (≈1 MB base64) dahil çalıştı.
- **Statik sunum:** `http.server.ThreadingHTTPServer` + SPA geri dönüşü (`/pricing` → `index.html`), boş port; pf/dist `/_expo/...` mutlak yolları ve site `/assets/...` sorunsuz.
- **Launcher durumları:** `index.html` geçici kopyasına `</body>` öncesi durum enjeksiyon betiği eklenir (ampirik ajanın `_inject.js`'i); Tauri modül betiği `window.__TAURI__.core` satırında ölür → DOM enjeksiyonla kurulur; `file:///…?v=login|select|install|ready|error|gunc|detect`.
- **Ölçülen (kapının doğruluğu):** launcher 700×540'ta `login/select/ready` üçünde de **ust-kesik** (ilk içerik 40-56 px < header altı 75 px → `launcher-1` birebir; ekran görüntüsünde "Giriş yapın" başlığı üst çubuğun altında), 880×600'de `select` de kesik (2. doğrulama notuyla uyumlu); pf 320/640'ta "Şifremi unuttum?" 84×12 / 92×14 (`ampirik-4`), Giriş Yap/Kayıt Ol sekmeleri 115×30 (`ilkel-7` sınıfı); site 320'de `main.scrollWidth 391 > 320` (`ampirik-1`), "Çıkınca haber ver" 222×16 (`site-11`), altbilgi bağlantıları 20 px (`site-16`).
- **KIRMIZI KANITI (mutasyon, depoya dokunmadan `--mutasyon` CSS enjeksiyonu):** `#btn-install{display:none} .stage{min-width:1200px}` → `kritik/Kur ve Başlat = GIZLI` + `tasma-main 1070>880` → **exit 1**. Kapı boş çalışmıyor.
- **Bulunan tuzaklar (betiğe işlendi):** (1) `--user-data-dir` GÖRELİ verilince Edge CDP portunu hiç açmıyor → `Path(...).resolve()`; (2) Git-Bash/MSYS `/`-ile başlayan argümanı Windows yoluna çeviriyor → site durum adları eğik çizgisiz (`ana, download, …`); (3) site `html{scroll-behavior:smooth}` (`site-4`) `scrollIntoView`'u animasyonlu yapıp sahte DISARIDA üretti → ölçümden önce `scrollBehavior='auto'`; (4) Windows'ta `ConnectionResetError 10054` izleri → `SessizSunucu.handle_error`; (5) WCAG 2.5.8 aralık muafiyeti eklenmeden altbilgi listesi 85 gürültü satırı üretiyordu → muafiyetle 29 (kalanlar gerçek `site-16`).

##### 1. Betik: `scripts/responsive_kapisi.py` (taslak aşağıda; scratchpad kopyası doğrulanmış hâli)
**Sözleşme:** `--hedef {pf,launcher,site}`; `--pf-dist/--site-dist` (varsayılan `pf/dist`, `pemf-vet-web/dist`); `--cikti` (PNG + `rapor_<hedef>.json`); `--baseline` (varsayılan `tests/responsive_kapisi_baseline.json`); `--zorunlu` (ortam yoksa 3 yerine 2 — CI'da ŞART); `--gorunum 320x568,911x512`; `--durum login,select`; `--mutasyon "<css>"`; `--bayat-hata` (ratchet); `--png-yok`. Çıkış: **0** yalnız baseline'daki bilinenler · **1** YENİ bulgu · **2** altyapı/kullanım hatası · **3** ortam yok (tarayıcı ya da derleme çıktısı yok; yerelde atlanır).
**Ortam kararı (memory `kapi-ortam-varsayimi-cogunluk`):** `CI` bayrağı KULLANILMAZ; tarayıcı YETENEĞİ aranır (`--tarayici`, `PEMF_TARAYICI`, Edge x86/x64, Chrome, `/usr/bin/microsoft-edge|google-chrome|chromium`, `shutil.which`). Yoksa 3; CI `--zorunlu` verdiği için orada 2 (windows-latest'te Edge her zaman var).
**Bulgu anahtarı:** `hedef/durum/kontrol/eleman@kova` — kova = `dar`(≤430) / `orta`(431-1024) / `genis`(>1024); 8 görünümde 8 ayrı satır yerine en fazla 3 → baseline az oynar. Eleman anahtarı = innerText | aria-label | id | tag (40 kar.).
**Dokunma katmanları:** mobil emülasyon (w≤430 ya da h≤430, ve 768 tablet) → eşik 44; masaüstü görünümleri → 24 (WCAG 2.5.8 AA). Şiddet: kısa kenar <24 → `yuksek`, 24-43 → `orta`. Muafiyetler (bilgi listesine düşer, kırmızı yapmaz): satır-içi `display:inline` `<a>`; **aralık muafiyeti** (eşik çaplı daire komşu hedefe değmiyorsa). Giriş alanları (`input[type=text]`) kapsam DIŞI (ampirik-5 ayrı ele alınır).
**Kritik elemanlar (VAR + GÖRÜNÜR + scrollIntoView sonrası görünüm alanında + `elementFromPoint` ile örtülmemiş):** pf giriş: "Giriş Yap" gönder (son eşleşme), "Kayıt Ol" sekmesi, "Şifremi unuttum"; pf kayıt (sekmeye tıklayarak): "Kayıt Ol/Hesap Oluştur" gönder. Launcher login: `#btn-login #btn-forgot #btn-signup #btn-offline-start`; select: `#btn-install` (**Kur ve Başlat**), `#btn-sel-cancel`, `#cards .card`; install: `#btn-pause #btn-cancel`; ready: `#btn-start #btn-change #btn-repair #btn-uninstall #foot-support`; error: `#error #btn-repair`; gunc: `#gunc-lead`. Site ana: `header button` (ilk GÖRÜNÜR: masaüstünde "Giriş yap", mobilde Menü); download: `main button[data-kapi='indir'], main button`.
**Launcher'a özel `ust-kesik`:** `main.scrollTop=0` iken `main section:not([hidden])` ilk çocuğunun `top < header.bottom-1` → yüksek (launcher-1'in doğrudan ölçümü).

##### 2. Uygulama adımları (dosya · değişiklik · kapattığı/kilitlediği bulgu · doğrulama · risk · geri alma)
**A1. `scripts/responsive_kapisi.py` — taslağı depoya al** (aşağıdaki `betik_taslagi`; scratchpad'de doğrulandı). Son rötuşlar: `tempfile` importunu sil (ruff F401 → `lint.yml` kırmızı olur); `--baseline-yaz` bayrağı ekle (gözlenen bulguları `{"anahtar","bulgu":"?","eklendi":"<tarih>"}` olarak birleştirir; insan `bulgu` alanına denetim kimliğini yazar); `rapor_<hedef>.json` içine `aralikMuaf/satirIci` bilgi listeleri zaten yazılıyor. · **Kilitler:** launcher-1, launcher-2 (911×512/1024×576 DPI görünümlerinde `ready` alt bağlantıları + `login` bağlantıları DISARIDA/ORTULU kontrolüyle — yalnız tarayıcı-içi kısmı, bkz. sınırlar), launcher-3/7 (hbtn ikon-only durumunda `title` yok → ileride `kritik` listesine `#btn-guide[title]` eklenerek), launcher-11, ampirik-1, ampirik-4, ilkel-7 (pf giriş sekmeleri), site-1 (768'de başlık düğmeleri 36 px), site-5 (pricing 320 taşma kontrolü), site-11, site-16, matris-12 (viewport meta — ayrı basit grep kontrolü A5'e). · **Doğrulama:** `PYTHONIOENCODING=utf-8 ..\python.exe scripts\responsive_kapisi.py --hedef launcher --durum select --gorunum 880x600 --mutasyon "#btn-install{display:none}" --png-yok` → exit 1 ve çıktıda `kritik/Kur ve Başlat`; mutasyonsuz + seed'li baseline → exit 0. · **Risk:** yok (salt ölçüm; ürün koduna dokunmaz). · **Geri alma:** dosyayı sil.
**A2. `tests/responsive_kapisi_baseline.json` — bilinen bulgu izin listesi (seed).** `--baseline-yaz` ile üç hedef için üret, her kayda `bulgu` (denetim kimliği: `launcher-1`, `site-16`, `ampirik-4`…) ve gerekirse `not` yaz. Kural: yeni anahtar = kırmızı; baseline'daki anahtar gözlenmezse **BAYAT** uyarısı, `--bayat-hata` ile kırmızı (bir düzeltme yayına girince ilgili satır SİLİNİR → ratchet yalnız küçülür). · **Doğrulama:** `tests/test_responsive_kapisi.py::test_baseline_her_kayit_bulgu_kimligi_tasir` (her `bulgu` değeri `docs/responsive-denetim-2026-09-04.bulgular.json` içindeki bir `id` ya da `kabul:<gerekçe>`). · **Risk:** gevşek seed gerçek regresyonu gizler → seed yalnız bu turda ölçülen anahtarlarla, her satır kimlikli. · **Geri alma:** dosyayı sil (kapı o anda tüm mevcut sorunlarla kırmızı olur — bilinçli).
**A3. Kritik elemanları metne değil ÇIPAYA pinle (memory `pemf-yapisal-capa-kirilganligi`).** `pemf-vet-web/src/pages/Download.tsx:51` birincil `<button>`'a `data-kapi="indir"`; `pemf-vet-web/src/components/AccountButton.tsx:59` "Giriş yap" düğmesine `data-kapi="giris"`; pf `AuthScreen.tsx:376` gönder `Pressable`'ına `testID="auth-gonder"` (RN-web `data-testid` basar), `:288` şifremi unuttum `testID="auth-sifre"`, `:206/213` sekmeler `testID="auth-sekme-giris|kayit"`; launcher zaten id'li. Betikte `css` seçicileri buna çevir (metin regex yedek kalır). · **Kapattığı:** —; kırılganlığı önler (Türkçe metin değişince kapı yanlış kırmızı olmasın). · **Doğrulama:** jest mevcut `AppShell.*.test.tsx` desenine göre `getByTestId("auth-gonder")` (varlık); betik `kritik` = OK. · **Risk:** sıfır davranış etkisi. · **Geri alma:** öznitelikleri kaldır.
**A4. `.github/workflows/responsive.yml` — YENİ iş akışı** (`tests.yml`'e EKLENMEZ: `test_ci_workflow_gate.py::BEKLENEN_ISLER={"backend","launcher","sir-taramasi"}` TAM eşitlikle kilitli; ayrıca `frontend.yml/site.yml` `defaults.run.working-directory` kilidi var → bağımsız dosya en temiz). YAML `ci_entegrasyonu` alanında. Runner **windows-latest**: WebView2 = Edge/Chromium + Segoe UI (launcher üretim platformu; ubuntu'da DejaVu daha geniş metin → sahte taşma), `msedge.exe` runner imajında hazır. Matris `hedef ∈ {launcher, pf, site}`, `fail-fast:false`; pf işi `npm install --legacy-peer-deps` + `npm run export:web` (frontend.yml ile aynı; `postexport-web.js` dahil — memory `pemf-web-frontend-deploy`), site işi Node 22 `npm ci` + `npx vite build` (site.yml ile aynı); Python 3.10 setup-python, pip YOK. `PYTHONIOENCODING=utf-8` (betik `sys.stdout.reconfigure` de yapıyor). Artefakt `responsive-<hedef>` (`rapor_*.json` + PNG'ler, `_profil` hariç) `if: always()`, 14 gün. · **Doğrulama:** `tests/test_responsive_kapisi.py::test_KRITIK_workflow_var_ve_zorunlu` (dosya var; `paths` `pf/`, `pemf-vet-web/`, `launcher/app/ui/`, betik ve baseline'ı içerir; her matris çalıştırmasında `--zorunlu` geçer; artefakt adımı `always()`; `runs-on` windows) — memory `pemf-test-varlik-degil-uygulama-olc`: "isim geçiyor" değil, adım komut satırında `--zorunlu` regex'i. İlk koşuda `workflow_dispatch` ile tetikle, artefaktı indirip PNG'leri göz-kontrol et. · **Risk:** pf export CI'da ~4-6 dk; `npm install` lockfile sapması (frontend.yml aynı yolu kullanıyor, kabul). · **Geri alma:** dosyayı sil.
**A5. `tests/test_responsive_kapisi.py` — kapı-kapısı** (memory `kapi-kirmizi-oldugunu-kanitla`): (a) AST çıpası: `GORUNUMLER["launcher"]` (700,540) ve (911,512) içerir, `GORUNUMLER["pf"]` (320,568) ve (640,360) içerir, `DOKUNMA_MIN_MOBIL == 44`, `DOKUNMA_MIN_MASAUSTU == 24` (`ast.literal_eval` ile, düz metin değil); (b) `HEDEFLER["launcher"]["select"]` kritik listesinde `#btn-install`, `["ready"]`'de `#btn-uninstall` ve `#foot-support`; (c) **iki uçlu canlı test** — tarayıcı YETENEĞİ varsa (`tarayici_bul()` import edilip çağrılır; yoksa `pytest.skip`): `subprocess.run([sys.executable, "scripts/responsive_kapisi.py", "--hedef","launcher","--durum","select","--gorunum","880x600","--png-yok","--mutasyon","#btn-install{display:none}"], env={"PYTHONIOENCODING":"utf-8"})` → rc 1 ve stdout'ta `kritik/Kur ve Başlat`; aynı komut mutasyonsuz gerçek baseline ile → rc 0 (windows-latest'te Edge var → CI'da da kanıtlanır; `tests.yml` filtresiz olduğu için her push'ta ~20 sn); (d) `pf/dist/index.html` viewport meta `viewport-fit=cover` (matris-12) — düzeltme girince aktifleşecek `xfail(strict=True)`. · **Risk:** launcher testi ~15-20 sn; `tests.yml` Linux ayağında Edge yok → skip (kapı Windows ayağında koşar; memory: ürün Windows). · **Geri alma:** dosyayı sil.
**A6. Belgeleme:** `scripts/README.md` "Build & yayın" tablosuna satır; `docs/responsive-denetim-2026-09-04.md §6 kilit (2)` maddesine "uygulandı: `scripts/responsive_kapisi.py` + `responsive.yml`" notu (yalnız plan onaylanınca).

##### 3. Faz 2 (ayrı PR, +8 saat): pf OTURUM-İÇİ kabuk — ACİL DURDUR görünürlüğü
Statik `pf/dist` yalnız Auth ekranını çizer (Supabase oturumu yok; backend yok) → ACİL DURDUR (GlobalEmergencyStop, Dashboard kartı, SessionProgressCard, ControlScreen sayfa-sonu) bugün ÖLÇÜLEMİYOR. Tasarım: `pf/app/vitrin.tsx` rotası, yalnız `process.env.EXPO_PUBLIC_VITRIN === "1"` iken içerik çizer (aksi hâlde `Redirect href="/"`); sahte `LiveDataContext` (activeTreatment.isActive=true, 8 bobin running) + sahte auth ile `AppShell` içinde Dashboard/Kontrol/Sensörler. Kapı işi pf export'unu `EXPO_PUBLIC_VITRIN=1` ile alır; `build_backend_exe.ps1` üretim export'u bayraksız (rota pasif). Kritik: `testID="acil-durdur-global"` (GlobalEmergencyStop.tsx:75-93), `acil-durdur-kart` (DashboardScreen.tsx:114), `acil-durdur-seans` (SessionProgressCard.tsx:144), `acil-durdur-sayfa` (ControlScreen.tsx:733) → 8 görünümde VAR+GÖRÜNÜR+ÖRTÜLMEMİŞ, özellikle 640×360 (ekranB-3), 320 (ekranA-15 yükseklik ≥52) ve 768 (ekranC-1 sidebar). Kilitlediği: ekranA-15, ekranB-2 (sayfa-sonu düğmesi ulaşılabilirlik), ekranB-3, kabuk-3 (üst bar taşması), kabuk-5 (alt bar etiket kırpma → `dokunma` + görünürlük), ekranC-1/ekranA-1 (grid taşma). **Hasta güvenliği:** vitrin rotası hiçbir seans/E-stop kodunu değiştirmez; yalnız sahte bağlamla çizer. Üretim kapısı: `tests/test_responsive_kapisi.py::test_vitrin_uretim_exportunda_YOK` (`pf/dist/_expo/**/*.js` içinde `vitrin` rota adı ve `EXPO_PUBLIC_VITRIN` gerçek değerinin bulunmaması; Expo `EXPO_PUBLIC_*`'ı derlemede inline eder).

##### 4. Hasta-güvenliği ve regresyon notu
Kapı ürün davranışına dokunmaz; A3'teki `testID/data-kapi` öznitelikleri render/olay akışını değiştirmez. ACİL DURDUR erişimi ve seans akışı hiçbir adımda değişmiyor; Faz 2 tam tersine bunları ölçülebilir kılar. Baseline'a `kritik/*` sınıfı bir kayıt ASLA eklenmez (kritik eleman kaybı hiçbir zaman "bilinen" sayılmaz) — bunu `test_baseline_kritik_kayit_ICERMEZ` kilitler.

##### 5. Efor (gerçekçi)
Faz 1: betik son rötuş + `--baseline-yaz` 3 s · baseline seed + kimliklendirme 2 s · çıpa öznitelikleri (pf/site) 1 s · workflow + ilk yeşil koşu döngüsü 3,5 s · pytest kapı + mutasyon kanıtı 2,5 s · belge 0,5 s ≈ **12,5 s**. Faz 2 (vitrin rotası + 4 testID + üretim-dışı kilidi) ≈ **8 s**. Toplam ≈ 20,5 s.

**Betik (taslak, depoda):** `rk_launcher, rk_mut, rk_pf, rk_site3)` → `scripts/responsive_kapisi.py` (stdlib-only, Edge/Chrome headless + CDP; CI'ya Faz D'de bağlanır; baseline `tests/responsive_kapisi_baseline.json` ilk koşuda insan eliyle onaylanır) · **Görünüm alanları:** pf: 320x568 (mobil), pf: 360x800 (mobil), pf: 640x360 (telefon yatay, mobil), pf: 700x540 (launcher min penceresi), pf: 768x1024 (tablet dikey, mobil/dokunma), pf: 911x512 (1366x768 @%150 DPI), pf: 1280x720, pf: 1920x1080, launcher: 700x540 (min pencere), launcher: 880x600 (varsayılan), launcher: 911x512 (1366 @%150), launcher: 1024x576 (1280 @%125), launcher: 1280x720, launcher: 1920x1080, launcher 320/360/640 ÜRETİM DIŞI (ampirik-9) — ölçülmez, site: 320x568, 360x800, 390x844, 640x360, 768x1024 (mobil), site: 911x512, 1280x720, 1920x1080 (masaüstü), Mobil emülasyon = w<=430 ya da h<=430 ya da 768 tablet: Emulation.setDeviceMetricsOverride{mobile:true} + setTouchEmulationEnabled; deviceScaleFactor 1 (DPI sınıfı görünüm boyutuyla temsil edilir)

**Kontroller:**
- tasma: max(document.scrollingElement.scrollWidth, body.scrollWidth) <= innerWidth+1; ayrıca <main> için main.scrollWidth <= main.clientWidth+1 (launcher ve site main kullanır) — teşhis için taşan ilk 8 eleman (tag/anahtar/sağ kenar) rapora yazılır. Şiddet yüksek.
- dokunma: seçici `button,a[href],[role=button|link|tab|switch|checkbox|radio|menuitem],input[type=checkbox|radio|submit],summary`; görünür (rect>0, visibility/display/opacity) ve aria-hidden dışı; kısa kenar < eşik → bulgu. Eşik: mobil emülasyonda 44 px, masaüstünde 24 px (WCAG 2.5.8 AA). Şiddet: <24 yüksek, 24-43 orta. Muafiyet (bilgi listesi, kırmızı yapmaz): display:inline <a> (metin akışı) ve ARALIK muafiyeti (eşik çaplı daire komşu hedefe değmiyorsa). Metin giriş alanları kapsam dışı (ampirik-5 ayrı).
- kritik: hedef×durum başına liste — pf giriş: 'Giriş Yap' gönder, 'Kayıt Ol' sekmesi, 'Şifremi unuttum'; pf kayıt (sekmeye tıklayıp): 'Kayıt Ol/Hesap Oluştur' gönder; launcher login: #btn-login #btn-forgot #btn-signup #btn-offline-start; select: #btn-install (Kur ve Başlat) #btn-sel-cancel #cards .card; install: #btn-pause #btn-cancel; ready: #btn-start #btn-change #btn-repair #btn-uninstall #foot-support; error: #error #btn-repair; gunc: #gunc-lead; site ana: header ilk görünür button (Giriş yap / Menü); download: main button[data-kapi=indir]. Durumlar: YOK / GIZLI / DISARIDA (scrollIntoView sonrası viewport dışında) / ORTULU (elementFromPoint başka eleman; örten adı raporda) / OK. Hepsi yüksek; baseline'a ASLA alınmaz (pytest kilidi).
- ust-kesik (launcher): main.scrollTop=0 iken `main section:not([hidden])` ilk çocuğunun rect.top < header.bottom-1 → 'içerik üstten kesik, kaydırmayla ulaşılamaz' (launcher-1'in doğrudan ölçümü; 700x540 ve 880x600'de login/select/ready üçünde de yakalandı).
- png: her hedef/durum/görünüm için Page.captureScreenshot → <cikti>/<hedef>/<durum>_<w>x<h>.png; CI artefaktı (14 gün). Tam-sayfa görüntü isteğe bağlı (site için sh>vh ise ikinci override — ampirik betikteki desen).
- rapor: <cikti>/rapor_<hedef>.json — ölçümler (vw/vh/sw/sh/bodySW/mainSW, taşanlar, küçükler, kritik durumları, ustKesik), bilgi listeleri (satirIci, aralikMuaf), bulgular, yeni, bilinen sayısı, bayat. UTF-8 (PYTHONIOENCODING tuzağına karşı reconfigure + encoding).
- baseline eşiği: anahtar = hedef/durum/kontrol/eleman@kova (dar<=430 / orta<=1024 / genis); baseline'da OLMAYAN anahtar → exit 1; baseline'da olup görülmeyen → BAYAT uyarısı, --bayat-hata ile exit 1 (ratchet: düzeltme girince satır silinir, liste yalnız küçülür). Her baseline kaydı denetim bulgu kimliği taşır (pytest doğrular).
- mutasyon kanıtı: --mutasyon '<css>' sayfaya enjekte edilir (depoya dokunmadan); '#btn-install{display:none} .stage{min-width:1200px}' ile ölçüldü → kritik GIZLI + tasma-main → exit 1. pytest iki uçtan koşar: mutasyonla 1, mutasyonsuz baseline ile 0.
- ölçüm hatası: sekme/WS istisnası bir kez yeniden denenir; ikinci hata `olcum-hatasi` bulgusu (yüksek) — sessiz atlama yok.
- bilgi (kırmızı yapmaz, raporda): <11 px yazı taraması ileride eklenebilir (ampirik betikteki `tiny` deseni); giriş alanı yükseklikleri; satır-içi bağlantılar.

**CI entegrasyonu:** Mevcut durum: `.github/workflows/` altında Windows runner ZATEN var (tests.yml backend matrisi `windows-latest`, launcher işi `windows-latest`; launcher.yml matrisi windows-latest/macos-14/ubuntu-22.04). frontend.yml (pf, node 20, ubuntu, `npm install --legacy-peer-deps` + lint/tsc/jest) ve site.yml (node 22, ubuntu, `npm ci` + check:legal/lint/tsc -b/vitest/`npx vite build`) yol-filtreli. `tests/test_ci_workflow_gate.py` `tests.yml` iş kümesini TAM eşitlikle ({backend, launcher, sir-taramasi}) ve frontend/site.yml `working-directory`'lerini kilitler → kapı YENİ bir dosyada: `.github/workflows/responsive.yml` (kök `.github/`, alt dizinde DEĞİL — aynı test bunu da kilitler).

Runner kararı: **windows-latest** — WebView2 (launcher + masaüstü pf) Edge/Chromium'dur, Segoe UI metrikleri aynı; runner imajında `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` hazır. Ubuntu daha ucuz ama DejaVu/Liberation fontları metni genişletip sahte taşma üretir; site için bile Windows ölçümü kabul edilebilir vekildir. Betik yine de Linux/macOS yollarını da tanır (yerel geliştirici).

```yaml
# .github/workflows/responsive.yml
name: responsive-kapisi
# Görünüm-alanı taşması + dokunma hedefi + kritik eleman (ACİL DURDUR / Kur ve Başlat / Giriş yap) görünürlüğü.
# Edge headless + CDP; `--window-size` görünüm alanını DEĞİŞTİRMEZ (ölçüldü) → Emulation.setDeviceMetricsOverride.
# tests.yml'e EKLENMEDİ: test_ci_workflow_gate BEKLENEN_ISLER kümesini tam eşitlikle kilitler; bu hat yol-filtrelidir.
on:
  push:
    branches: [ main, master, production-hardening, "feature/**", "fix/**" ]
    paths: [ "pf/**", "pemf-vet-web/**", "launcher/app/ui/**", "scripts/responsive_kapisi.py",
             "tests/responsive_kapisi_baseline.json", ".github/workflows/responsive.yml" ]
  pull_request:
    paths: [ "pf/**", "pemf-vet-web/**", "launcher/app/ui/**", "scripts/responsive_kapisi.py",
             "tests/responsive_kapisi_baseline.json", ".github/workflows/responsive.yml" ]
  workflow_dispatch:
concurrency:
  group: responsive-${{ github.ref }}
  cancel-in-progress: true
permissions:
  contents: read
jobs:
  kapi:
    name: görünüm alanı (${{ matrix.hedef }})
    runs-on: windows-latest      # WebView2 = Edge/Chromium + Segoe UI; launcher üretim platformu
    timeout-minutes: 25
    strategy:
      fail-fast: false           # bir hedefin düşmesi diğerlerini gizlemesin
      matrix:
        hedef: [launcher, pf, site]
    env:
      PYTHONIOENCODING: utf-8    # gömülü/CI python stdout cp1254 tuzağı (memory)
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.10" }   # pip YOK — betik stdlib

      # pf web export (frontend.yml ile aynı kurulum yolu; `npm run export:web` = expo export + postexport-web.js)
      - if: matrix.hedef == 'pf'
        uses: actions/setup-node@v4
        with: { node-version: "20", cache: npm, cache-dependency-path: pf/package-lock.json }
      - if: matrix.hedef == 'pf'
        working-directory: pf
        run: |
          npm install --legacy-peer-deps
          npm run export:web

      # site derlemesi (site.yml ile aynı; Node 22 ŞART)
      - if: matrix.hedef == 'site'
        uses: actions/setup-node@v4
        with: { node-version: "22", cache: npm, cache-dependency-path: pemf-vet-web/package-lock.json }
      - if: matrix.hedef == 'site'
        working-directory: pemf-vet-web
        run: |
          npm ci
          npx vite build

      - name: Responsive kapısı (${{ matrix.hedef }})
        # --zorunlu: tarayıcı/derleme yoksa 3 (atla) DEĞİL 2 (hata) — CI'da sessiz atlama yasak
        run: python scripts/responsive_kapisi.py --hedef ${{ matrix.hedef }} --zorunlu --cikti responsive_cikti

      - name: Ekran görüntüleri + rapor (her koşuda)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: responsive-${{ matrix.hedef }}
          path: |
            responsive_cikti/**
            !responsive_cikti/_profil/**
          retention-days: 14
          if-no-files-found: warn
```

Süreler (tahmin): launcher ≈ 1,5 dk (6 görünüm × 7 durum, PNG dahil), site ≈ 2,5 dk (npm ci + vite + 8×5), pf ≈ 6-8 dk (npm install + expo export ~4-5 dk + 8×2). pf değişikliği üç işi de tetikler (basitlik; gerekirse `dorny/paths-filter` ile ayrıştırılır).

Kilitler: `tests/test_responsive_kapisi.py` (tests.yml filtresiz koştuğu için her push'ta): workflow dosyası var + `runs-on` windows + üç hedef matriste + her çalıştırma satırında `--zorunlu` + artefakt adımı `if: always()` + paths listesi `pf/`, `pemf-vet-web/`, `launcher/app/ui/`, betik ve baseline'ı içerir; AST çıpaları (görünüm listeleri, 44/24 eşikleri, kritik seçiciler); baseline kayıtları bulgu kimlikli ve `kritik/` içermez; tarayıcı yeteneği varsa (`tarayici_bul()`) launcher select 880x600 için mutasyonlu koşu rc==1 + mutasyonsuz rc==0 (Windows ayağında koşar, Linux ayağında skip).

Yerel koşu: `PYTHONIOENCODING=utf-8 ..\python.exe scripts\responsive_kapisi.py --hedef launcher` (pf/site için önce `npm run export:web` / `npx vite build`). Çıktı `..\PEMF_BUILD\responsive_kapisi\`.

**Sınırlar:**
- pf OTURUM-İÇİ kabuk ölçülemiyor: statik pf/dist yalnız Auth ekranını çizer (Supabase oturumu + backend yok) → ACİL DURDUR (GlobalEmergencyStop, Dashboard kartı, SessionProgressCard, Kontrol sayfa-sonu), alt bar, sidebar, ResponsiveGrid bugün kapı dışında. Faz 2 tasarımı: EXPO_PUBLIC_VITRIN=1 ile derlenen `pf/app/vitrin.tsx` rotası (sahte LiveData/auth bağlamı, aktif seans) + 4 testID; üretim export'unda rota pasif ve pytest ile yokluğu doğrulanır.
- launcher-2 (pencere ekrandan taşar, 540 altına küçülemez) tarayıcıda YALNIZ vekil olarak ölçülür (911x512 / 1024x576 görünümlerinde kritik elemanların DISARIDA/ORTULU olmaması). OS pencere/min-size davranışı ve WebView2'nin gerçek DPI ölçeklemesi kapsam dışı → main.rs `set_min_size/work-area` mantığı için Rust birim testi ayrı.
- Deterministik Android/iOS davranışları ölçülmez: sistem yazı ölçeği (S6), gerçek klavye (S4), safe-area çentik (S5), PanResponder/ScrollView çakışmaları, native Modal. Bunlar kod okuması + cihaz testi ile kalır (rapor §2 ile aynı).
- Tarayıcı emülasyonu ≠ WebView2/Safari birebir: font metrikleri Windows runner'da Segoe UI (WebView2 ile aynı), ama iOS Safari `vh`/16px-zoom (site-3, site-13) ve Android Chrome davranışları ölçülmez; DPI %125-200 yalnız mantıksal görünüm boyutuyla temsil edilir (deviceScaleFactor=1).
- Dokunma hedefi taraması statik DOM'a bakar: RN Pressable `hitSlop` (ekranB-15) DOM'a yansımaz → hitSlop çakışması ölçülemez; RN-web'de bazı TouchableOpacity'ler role=button taşımayabilir (yalnız accessibilityRole verilenler yakalanır) → eksik role bulgusu değil, kapsam boşluğudur. Giriş alanı yükseklikleri (ampirik-5) kapsam dışı.
- Gürültü/baseline riski: site altbilgi bağlantıları gibi 20 px hedefler mobil 44 eşiğinde bilinçli bulgudur (site-16); baseline seed'i insan eliyle kimliklendirilmeli; 'kabul' notu olmadan baseline'a satır eklenmez, `kritik/` sınıfı hiçbir zaman baseline'a alınmaz.
- Zamanlama: pf export CI'da 4-6 dk; Expo bundle hidrasyonu için sabit 3,5 sn bekleme (flaky olursa `--bekle` artırılır ya da `document.querySelector('[data-testid=auth-gonder]')` bekleme döngüsü eklenir). Tek yeniden deneme var; ikinci hata `olcum-hatasi` bulgusu olarak kırmızı.
- Metin-regex kritik seçiciler (pf 'Giriş Yap', 'Kayıt Ol') Türkçe metin değişince yanlış kırmızı verir → A3 adımında testID/data-kapi çıpalarına pinlenmeli (memory: yapısal çıpa kırılganlığı).
- Git-Bash'ten çağrıda '/'-ile başlayan argümanlar MSYS tarafından Windows yoluna çevrilir (site durumu '/' sessizce atlandı, ölçüldü) → durum adları eğik çizgisiz; pwsh/CI etkilenmez.
- Ubuntu runner'a taşınırsa fontlar (DejaVu) metni genişletir → baseline yeniden seed edilmeli; runner değişikliği baseline'ı geçersiz kılar.
- Kapı düzeltme YAPMAZ: yalnız regresyon kilididir (rapor §6 Faz 3 'kilit (2)'). Mevcut 121 bulgudan bu turda doğrudan ölçülenler: launcher-1, launcher-11, ampirik-1, ampirik-4, ilkel-7 (giriş sekmeleri), site-1 (kısmen), site-11, site-16; düzeltmeler girdikçe baseline satırları silinir (ratchet).

## 7. Cihaz test matrisi (her fazın kapanışında)

| Cihaz | Senaryolar |
|---|---|
| Android telefon (dar, 360×800) | Yazı ölçeği 1,0 ve 1,3; dikey + yatay; klavye ile hasta formu, CKD formu, gözlem notu; ACİL DURDUR seans sürerken yatayda ve klavye açıkken |
| Android tablet 10" (800×1280) | Dikey: kenar çubuğu rayı, ızgara sütunları, bobin kartları; yatay: 3 sütun |
| iPhone (EAS build, çentikli) | Yatay çentik tarafı; klavye açıkken Auth/Hasta formu/Gözlem notu; safe-area üst/alt |
| Klinik PC 1366×768 @%150 | Başlatıcı: giriş, profil seçimi, hazır, indirme, güncelleme penceresi; uygulama: pencere 700×540'a küçültme, tekrar büyütme |
| PC 1920×1080 @%100 ve %125 | Sensör grafiği keskinlik; KPI tablosu hizası; bantlar ortalı |
| Telefon tarayıcısı (LAN, iOS Safari + Android Chrome) | Giriş kapısı, viewport-fit, input zoom yok, modal yükseklikleri |
| A4 baskı + ArUco işaretli kedi fotoğrafı (AI Pro / Kedi Organ canlı mod) | Sunucu işaretleri canlı görüntüye birebir oturuyor (S7 tıbbi karar kapısı) |

## 8. Bulgu → paket eşlemesi (tam liste)

| Kimlik | Şiddet | Kök | Ekran | Sorun (kısa) |
|---|---|---|---|---|
| `launcher-1` | Yüksek | L | s-login, s-select (dep-notice/hata ile), s-ready … | main hem overflow:auto hem justify-content:center (sütun flex) ve .stage'de margin:auto yok. İçerik main'den uzun olunca flexbox içeriği or… |
| `launcher-2` | Yüksek | L | tüm ekranlar (özellikle s-ready alt bağlantıları,… | Pencere 880x600 mantıksal, minHeight 540 — Windows DPI ölçeğinde mantıksal çalışma alanı bunun altına iniyor: 1366x768 @%150 → 911x512, gör… |
| `ekranC-1` | Yüksek | S2 | Hastalar (hasta kartı ızgarası); aynı kök neden G… | ResponsiveGrid sütun sayısını PENCERE genişliğinden hesaplıyor, kenar çubuğunu (tablet+desktop'ta gösterilen rs(248)=322px) ve AppShell'in … |
| `ekranC-3` | Yüksek | S7 | Seans Geçmişi → Seans Detayı modalı (Sıcaklık Gra… | TempChart SVG sabit viewBox 720×260 ile width='100%' + height rs(260) çiziliyor (preserveAspectRatio varsayılan 'meet'). Telefonda modal ka… |
| `ampirik-1` | Yüksek | W | Web sitesi ana sayfa (/) hero bölümü ve /features… | LauncherMock'un üst şeridindeki `truncate` (white-space:nowrap) alt başlık 'Veteriner PEMF seans + yapay zekâ teşhis platformu' (229px) + l… |
| `launcher-3` | Orta | L | header — her ekran | ≤1040px genişlikte .hbtn span display:none oluyor ama düğmelerde title/aria-label yok; 'Web Sitesi', 'Kılavuz', 'Hakkında' ve 'Çıkış' yalnı… |
| `launcher-4` | Orta | L | s-select profil kartları | Kartlar tabindex/role/keydown olmayan div'ler; yalnız onclick. Klavyeyle (Tab) hiçbir karta odaklanılamaz, Enter/Space ile seçilemez; 'Kur … |
| `launcher-5` | Orta | L | Hakkında, Kılavuz, Onay (Onar/Kaldır/İptal) modal… | Modal açılınca odak modala taşınmıyor, Escape kapatmıyor, odak tuzağı yok. Klavye kullanıcısı 'Onar' onayında Enter'a basınca hiçbir şey ol… |
| `launcher-6` | Orta | L | Onay modalı — 'Uygulamayı kaldır' (KVKK metni) ve… | uninBody ve bgCancelConfirm '\n\n' ve '• ' madde işaretleriyle yazılmış ama <p id=confirm-body>'ye textContent ile konuyor ve .modal p'de w… |
| `kabuk-1` | Orta | S1 | Kabuk geneli — sidebar, spacing, typography (tüm … | SCALE uygulama açılışında BİR KEZ, kısa kenar/375 formülüyle hesaplanıp 1.30'a clamp'leniyor. Tablet, PC (WebView2), LAN tarayıcı ve DPI %1… |
| `aihub-4` | Orta | S2 | Tüm görüntü modüllerinin 'Galeriden Seç / Fotoğra… | isCompact yalnız pencere genişliğine bakıyor (width<768). 768-1023 px'de AppShell kenar çubuğu rs(248)=322 px (SCALE 1.3) alıyor → içerik k… |
| `ekranA-1` | Orta | S2 | Dashboard (Ana Ekran) — metrik ve bobin ızgarası | Sütun sayısı PENCERE genişliğinden hesaplanıyor, kenar çubuğu (rs(248)=322px, ölçek 1.3) ve iki kat içerik padding'i düşülmüyor. 768px tabl… |
| `ekranA-2` | Orta | S2 | Dashboard — Hasta Özeti / Aktif Seans kartları | heroGrid kartlarında minWidth rs(280)=364px (ölçek 1.3). 768px tablet dikey (iPad) veya 770px'e daraltılmış launcher penceresinde AppShell … |
| `ekranA-3` | Orta | S2 | Dashboard ve Settings (tüm AppShell ekranları) — … | 768-834px tablet dikeyde 'tablet' layout'u masaüstü gibi işleniyor: sabit rs(248)=322px kenar çubuğu ekranın %39-42'sini alıyor, içeriğe 35… |
| `ekranB-1` | Orta | S2 | Kontrol → Manuel sekmesi, STM32 (1-5) ve WiFi (6-… | ResponsiveGrid sütun sayısını PENCERE genişliğinden hesaplıyor, kartların içine yerleştiği gerçek konteyner genişliğinden değil. Tablet/mas… |
| `kabuk-2` | Orta | S2 | Kabuk navigasyonu — PC küçültülmüş pencere / yüks… | desktop = isDesktop||isTablet → sidebar yalnız width ≥768 iken; launcher min penceresi 700px, 1366px ekranda %200 DPI 683px, %175'te 780px … |
| `kabuk-8` | Orta | S2 | Grid kullanan 6 ekran (Dashboard, Kontrol, Hastal… | Sütun sayısı PENCERE genişliğinden hesaplanıyor, sidebar düşülmüyor. Tablet dikey 768px: layout=tablet → columns=2, minItemWidth kontrolü 7… |
| `aihub-5` | Orta | S3 | Isı haritası anahtarı (6 modül), CKD Evet/Hayır d… | Dokunma hedefleri 44 px'in çok altında: xaiToggle paddingVertical rs(4) + 11 px yazı ≈ 22 px yüksek (switch rolü); ckdCatBtn ≈ 22-24 px (10… |
| `ampirik-4` | Orta | S3 | pf giriş kapısı (web export ve aynı kodla APK) — … | 'Şifremi unuttum?' ve 'Hesabın yok mu? Kayıt ol' bağlantıları yalnız metin yüksekliğinde dokunma hedefi: 320px'te 84×12px, 390px'te 92×14px… |
| `ekranB-4` | Orta | S3 | Sensörler (eksen/bobin filtre çipleri), Kontrol →… | Dokunma hedefleri 44 px'in çok altında: SensorMonitor coilBtn paddingVertical 6 (ölçeksiz) + 12 px metin ≈ 26 px yükseklik; axisChip/target… |
| `ekranC-5` | Orta | S3 | Seans Geçmişi (not düzenleme başlığı) | Not düzenleme tetikleyicisi 14px Edit3 ikonunu padding'siz TouchableOpacity içinde → 14×14px dokunma hedefi; 'Kaydet' / 'İptal' yalnız meti… |
| `ilkel-4` | Orta | S3 | Seans Gözlem Notu – hasta tepkisi çip'leri | Chip paddingVertical spacing.xs (3-5px) + 11px yazı → yükseklik ~21-24px; 6 çip yan yana sarılıyor ve satır arası gap 4px. Dokunma hedefi 4… |
| `ilkel-7` | Orta | S3 | Tüm ilkeller: Button, giriş alanları, modal düğme… | Dokunma hedefi minimumları rs() ile ölçekleniyor: 320px'te SCALE=0.853 → rs(44)=38, rs(46)=39, rs(38)=32; 360px'te rs(44)=42. Yani tam da d… |
| `kapsam-2` | Orta | S3 | AppShell üst bantları — mobil güncelleme bandı (A… | Bandı kapatan X düğmesi yalnız rs(15) piksellik ikon; TouchableOpacity'ye hitSlop, padding, minWidth/minHeight verilmemiş → dokunma hedefi … |
| `matris-8` | Orta | S3 | AppShell üst bar — bildirim zili, bağlantı yenile… | Dokunma hedefleri 44 px'in çok altında: zil = 16 px ikon + padding rs(4) → ~24×24 px; 'Bağlantıyı yenile' Pressable'ı 10 px'lik nokta (çevr… |
| `aihub-6` | Orta | S4 | CKD formu (14 sayısal giriş), Hastalık vitalleri,… | (1) AiHubScreen ve PetOwnerAiScreen kendi iç ScrollView'ını AppShell ScrollView'ının içine kuruyor ama `keyboardShouldPersistTaps` vermiyor… |
| `ekranA-7` | Orta | S4 | Settings — 'Uzak cihaza bağlan' ve 'Manuel Sunucu… | (1) Settings'in kendi ScrollView'inde keyboardShouldPersistTaps yok (varsayılan 'never'): native'de klavye açıkken 'Cihaza Bağlan' / 'Bağla… |
| `ekranB-9` | Orta | S4 | Kontrol → seans-sonu gözlem notu alt-sayfası; Man… | Uygulamada KeyboardAvoidingView yalnız AuthScreen'de var; AppShell ScrollView ve ObservationNotesModal'da yok. iOS'ta (EAS build) alt-sayfa… |
| `ilkel-11` | Orta | S4 | Yedek parolası diyaloğu; Kullanıcı Değiştir (PIN)… | Ortalanmış Card, ScrollView'sız ve maxHeight'sız. Telefon yatayda (360-430px) klavye açılınca kalan ~150-200px'e başlık+not+2 giriş+hata+dü… |
| `kabuk-7` | Orta | S4 | Kabuk içerik alanı — TextInput içeren 9 ekran/bil… | Kabuk ScrollView'i KeyboardAvoidingView ile sarılı değil ve alt bar position:absolute bottom:0. iOS'ta (EAS build var) klavye açılınca içer… |
| `ekranA-4` | Orta | S5 | Welcome (profil seçimi) — üst çubuk (e-posta + Çı… | Ekran AppShell dışında render ediliyor (PemfApp.tsx:49) ve safe-area inset kullanmıyor; tek üst boşluk ScrollView'in paddingVertical xxl (2… |
| `ekranB-10` | Orta | S5 | Kontrol → AI Pro → 'AI önerisi onay' modalı, tele… | Kart `maxHeight:'88%'` olan düz View (ScrollView değil); içinde başlık + açıklama + 4 meta hücresi (2 satıra sarar) + güven satırı + XAI sa… |
| `ekranB-3` | Orta | S5 | Sensörler ve Kontrol — telefon YATAY | Yatay telefonda (yükseklik 360-430 px) AppShell üst bar (~85 px) + alt gezinme (~72 px) sabit; seans sürerken kayan ACİL DURDUR (52 px + rs… |
| `kabuk-4` | Orta | S5 | 'Daha Fazla' alt sheet'i (mobil navigasyon) | Sheet ScrollView'suz ve maxHeight'sız düz View; veteriner/araştırma profilinde 6 rota + Çıkış = 7 satır × (minHeight rs(48)+gap 4) + başlık… |
| `kapsam-1` | Orta | S5 | Mobil açılış kapısı — 'guncelleme' durumu (yeni A… | Kapı kökü kaydırılamayan, dikeyde ortalanmış bir View (`root: flex:1, alignItems/justifyContent:center`); ScrollView yok. app.json `orienta… |
| `kapsam-4` | Orta | S5 | AI Hub — kilitli özellik bilgilendirme modalı (Up… | Kart kaydırılamıyor (ScrollView yok) ve dikeyde ortalanıyor. İçerik yüksekliği: padding 2×32 + ikon halkası 64 + başlık 24 px (2-3 satır) +… |
| `ekranB-8` | Orta | S6 | Kontrol → aktif seans kartı (GEÇEN / % / KALAN) v… | timeRow 3 eşit flex:1 blok; timeValue `typography.title` (rf(24) → 375'te 24 px, 430'da ~26 px) + numberOfLines/adjustsFontSizeToFit YOK ve… |
| `kabuk-5` | Orta | S6 | Alt navigasyon çubuğu + üst bar başlığı | 5 slot, flex:1 → 320px'te slot ≈ 61px (padding sonrası ~53px), 360px'te ~61px. bottomLabel rf(10) bold, numberOfLines=1: 'Akıllı Teşhis' (1… |
| `matris-1` | Orta | S6 | Tüm uygulama (Android sistem yazı boyutu) | Projede hiçbir Text/TextInput'ta allowFontScaling veya maxFontSizeMultiplier yok (grep pf/src = 0). RN varsayılanı sistem yazı ölçeğini uyg… |
| `aihub-1` | Orta | S7 | AI Hub → VisionModule (FGS/Segmentasyon/Termal) v… | Isı haritasıyla AYNI SINIF sorun canlı-kamera overlay'inde duruyor: CameraView önizlemesi sabit rs(300) yükseklikli kutuyu 'cover' (kırpara… |
| `aihub-2` | Orta | S7 | Kontrol → AI Pro kamera kutusu (mobil telefon kam… | Aynı overlay sınıfı AI Pro'da da var: camBox sabit rs(200) yükseklik, CameraView %100/%100 (cover), camOverlay absolute + contain → organ l… |
| `aihub-3` | Orta | S7 | Fantom Tümör ve Petri Kuyu sonuç panelleri → D1–D… | Çubuk dolgu yüksekliği ölçeklenmemiş sabit 26 px ile hesaplanıyor, ama ray yüksekliği rs(26). Tablet/büyük telefon/PC'de (SCALE=1.3) ray 34… |
| `ekranB-5` | Orta | S7 | Sensörler → canlı grafik, dar telefon | Grafik iç kenar boşlukları sabit `PAD = {left:60, right:60, top:20, bottom:40}` (rs'siz). 320 px telefonda konteyner ≈ 320 − 2×20 (xl@0.85)… |
| `ekranB-6` | Orta | S7 | Sensörler → web canvas grafiği (PC/WebView2 ve ta… | Canvas piksel boyutu `width={width} height={height}` (1×) ama CSS `width:100%; height:auto` → devicePixelRatio hesaba katılmıyor. Windows D… |
| `ekranC-2` | Orta | S7 | Raporlar (Performans Grafikleri) | PieChart lejant metni chart-kit içinde x=width/2.5'ten başlar ve `absolute` ile 'sayı + mod adı' yazar. 320px telefonda kart içi genişlik ≈… |
| `site-1` | Orta | W | Header / masaüstü nav (md ≥768px) | Masaüstü nav md (768px) kırılımında açılıyor ama içerik ~800px istiyor: logo+marka (~114px) + 4 NavLink (~348px) + 'Giriş yap'/'Hesabım' bt… |
| `site-11` | Orta | W | İndir kartları alt bağlantıları, Giriş modalı 'Şi… | Dokunma hedefleri 44px altında: (1) Download 'Çıkınca haber ver', '.AppImage (tüm dağıtımlar)', '.rpm (Fedora / RHEL)' `text-xs` düz metin … |
| `site-13` | Orta | W | Giriş / Hesap oluştur modalı (klavye açıkken) | Diyalog `max-h-[90vh]`; `vh` iOS Safari'de büyük viewport'u (araç çubuğu gizli) baz alır. Araç çubuğu görünürken ve klavye açıkken (iOS kla… |
| `site-3` | Orta | W | Giriş/Kayıt modalı, Ödeme formu, Şifre sıfırlama … | Tüm form girişleri 14px (`font-size: 0.875rem` / `text-sm`). iOS Safari, font-size <16px olan input'a odaklanınca sayfayı otomatik yakınlaş… |
| `site-5` | Orta | W | Fiyatlandırma / Plan karşılaştırması tablosu | Tablo `min-w-[560px]`; 320-430px telefonda görünür alan 280-390px → satır etiketi + en fazla 1-2 plan sütunu görünüyor, kalan 2-3 plan sağa… |
| `site-8` | Orta | W | Fiyatlandırma / Kurulum profilleri seçici (Packag… | md (768px) kırılımında 3 sütun: kart genişliği ≈ 227px, iç alan ≈ 179px. 'Veteriner Hekim' kartında (config.ts 299 `recommended: true`) `ab… |
| `aihub-9` | Orta | — | CKD (Böbrek Hastalığı) formu — Laboratuvar/Vital … | Hücre width:'47%' → 320 px'de ~108 px; etiket typography.small (≈10 px) numberOfLines=1 olduğundan birimli etiketler kırpılır: 'Kan şekeri … |
| `ekranA-15` | Orta | — | Dashboard — Aktif Seans kartındaki ACİL DURDUR | Kart-içi acil durdur metni typography.small (rf(11) ≈ 10-13px) — ekrandaki en kritik düğmenin yazısı en küçük yazı boyutunda; düğme yüksekl… |
| `ekranA-8` | Orta | — | Settings — 'Ayarları Kaydet' satırı | Düğme ve durum metni flexDirection:'row' içinde; statusText'e flex/flexShrink verilmemiş (RN varsayılan flexShrink:0) ve satır sarmıyor. 32… |
| `ekranB-2` | Orta | — | Kontrol → Manuel sekmesi (sayfa sonu ACİL DURDUR) | Sayfa-içi 'TÜM BOBİNLERİ ACİL DURDUR' düğmesi Manuel sekmesinde 8 bobin kartının ALTINDA; telefonda kartlar ~300 px × 8 ≈ 2500-3000 px kayd… |
| `ekranB-7` | Orta | — | Kontrol → AI Pro sekmesi, dar telefon | 'Süre (dk) | Kalan | Yeniden Konumla' satırı 3 eşit flex:1 hücre; 320 px telefonda hücre ≈ 85 px, düğme iç genişliği ~70 px ve '🎯 Yeniden K… |
| `ekranC-4` | Orta | — | Seans Geçmişi (SessionCard başlık satırı) | Sağ küme (StatusPill 'Kesintiye Uğradı' ≈135px + paylaş ikonu + 'PDF' + sil ikonu, gap dahil ≈258px) 320-360px telefonda kart içi ≈236-270p… |
| `ekranC-6` | Orta | — | Hastalar (başlık düğmeleri) | Başlık View'ı flexWrap ama içindeki düğme satırı (line 198) flexWrap DEĞİL ve Button etiketi numberOfLines=1, flexShrink yok. Veteriner pro… |
| `ekranC-9` | Orta | — | AI Geçmişi (üst sayaç + Geçmişi Sil / Yenile) | headerRow: sayaç Text'i flexShrink/numberOfLines'sız, sağda iki metin düğmesi (ikon 16 + small yazı, minHeight yok → ≈18px yükseklik). 320p… |
| `kabuk-3` | Orta | — | Üst bar (tüm rotalar) | headerRight flexShrink:0 ve OperatorSwitcher çipi maxWidth rs(190) (e-posta/operatör adı taşıyor; ctx her zaman var → çip her zaman çizilir… |
| `launcher-10` | Düşük | L | tüm ekranlar — geniş/4K pencere ve %100 ölçekli y… | Arayüz pencere boyutuna göre ölçeklenmez: 2560x1440 ya da 4K @%100'de (kullanıcı pencereyi maximize ederse) sahne 560px'lik ada olarak orta… |
| `launcher-11` | Düşük | L | header dil seçici, alt bağlantılar (Şifremi unutt… | Dokunmatik Windows 2-in-1/tablet (Surface, %200 DPI) ya da dokunmatik klinik PC'de: .seg TR/EN düğmeleri ~28px yüksek, .link 13px + 6px pad… |
| `launcher-12` | Düşük | L | tüm ekranlar 700-1040px aralığı | Tek 'kompakt' kırılma noktası 680px, pencere ise 700'ün altına inemez → kural asla tetiklenmez; .title 24px küçültmesi ölü. 700-1040 aralığ… |
| `launcher-7` | Düşük | L | header — oturum açık + çevrimdışı rozeti görünürk… | 700px genişlikte (ya da 1366@%150'de ~911px'e kadar küçültülmüş pencerede) header-actions flex:0 0 auto/nowrap ve tahmini toplam ≈603px (se… |
| `launcher-8` | Düşük | L | hata kutusu — s-select/s-install/s-ready/s-login … | hataCumlesi() eşleşmeyen hatalarda ham mesaj doğrudan #error'a yazılır; #error white-space:pre-wrap ama overflow-wrap/word-break yok (yalnı… |
| `launcher-9` | Düşük | L | s-guncelleme (--guncelleme-ekrani kipi) | Pencere config'den 880x600 olarak açılır; Rust 250ms sonra 640x400'e küçültüp ortalar; html.gunc sınıfı ise JS boot'ta invoke('guncelleme_m… |
| `matris-9` | Düşük | L | PC — uygulama ('app') WebView2 penceresi | Uygulama penceresi yalnız .maximized(true) ile açılır; min_inner_size ve inner_size yok. Kullanıcı 'geri yükle' deyince Tauri varsayılanı 8… |
| `aihub-10` | Düşük | S1 | Canlı kamera / görüntü önizleme kutusu — PC'de We… | Önizleme kutusu sabit rs(300) yükseklik; SCALE açılışta kısa kenardan hesaplandığı için PC'de (kısa kenar ≥ 540 → clamp 1.3) her zaman 390 … |
| `ekranB-12` | Düşük | S1 | Kontrol (Otomatik/Manuel param satırı, AI Pro kam… | PC/tablette rs() SCALE hep 1.30 (kısa kenar ≥ 488) → `maxWidth: rs(1100)` = 1430 px, `rs(1200)` = 1560 px: hedeflenen 1100/1200 sınırı aşıl… |
| `ekranA-13` | Düşük | S2 | Welcome — profil kartları (tablet) | Kendi eşiği (width<768) ve kart minWidth rs(280)=364px: 768px tablet dikeyde kartlar tek tek tam genişlik (≈706px) olarak alt alta; 84px ik… |
| `ampirik-5` | Düşük | S3 | pf Kayıt Ol formu — dar telefon | 320px (rs ölçeği 0.85) ile 12 giriş alanının yüksekliği 36px'e düşüyor (390'da 41px); Android'de 44-48px önerilen dokunma yüksekliğinin alt… |
| `ekranA-10` | Düşük | S3 | Settings — ikincil düğmeler ve 'Düzenle' bağlantı… | btnOutline paddingVertical spacing.sm (7-10px) + 14px metin → 31-37px yükseklik; 'Düzenle' TouchableOpacity'de hiç padding yok, 11px metin … |
| `ekranA-14` | Düşük | S3 | Welcome — Çıkış düğmesi | paddingVertical spacing.sm (7-8px) + 11px metin → ~29px yükseklik; hasta güvenliğiyle ilişkili (seans sürerken teardown onayı açan) bir eyl… |
| `ekranB-15` | Düşük | S3 | Kontrol → Bobin Seçimi (8 düğme) — tüm sekmeler | CoilSelector düğmeleri rs(40) kare, aralarında gap spacing.xs (320'de 3 px, 375'te 4 px) ama her düğmeye 8 px hitSlop veriliyor → komşu düğ… |
| `ekranC-7` | Düşük | S3 | Hastalar / Seans Geçmişi / AI Geçmişi (Benim–Tüm … | Segment yarım-genişlik düğmeleri paddingVertical sm(8) + caption(12) → toplam ≈28-30px yükseklik (<44 dokunma hedefi). Etiket numberOfLines… |
| `ekranC-8` | Düşük | S3 | AI Geçmişi (hasta / modül filtre çipleri) | Çipler paddingVertical xs(4) + caption(12) → ≈22px yükseklik (<44 hedef). Ayrıca yatay çip ScrollView'ı, AppShell'in ana View'ındaki PanRes… |
| `ilkel-3` | Düşük | S3 | AI Seans Önerisi onay modalı – Kapat (X) | Kapat düğmesi padding'siz/hitSlop'suz TouchableOpacity; dokunma hedefi ikon boyutu kadar (rs(20) → 17-26px). Dokunmatikte ıskalanır; hasta … |
| `ilkel-5` | Düşük | S3 | Bildirimler paneli – 'Okundu işaretle' / 'Temizle' | Eylem düğmeleri padding spacing.xs (3-5px) + typography.small (9-11px) → ~19-22px yüksek, ~60px geniş; yan yana 8px boşlukla. 'Temizle' ger… |
| `kapsam-3` | Düşük | S3 | AppShell üst bantları — sürüm farkı bandı | Kapatma X'i rs(16) ikon + hitSlop 8 → toplam dokunma alanı ≈ 32×32 px (<44). Dar telefonda (a) ve büyük yazı ölçeğinde (i) metin bloğu büyü… |
| `kapsam-5` | Düşük | S3 | AI Hub — UpgradeModal kapatma düğmesi | X düğmesi absolute konumlu, ikon 20 px + padding rs(6) → dokunma hedefi ≈ 32×32 px (<44). Kart köşesinde, 32 px'lik kart padding'inin içind… |
| `ekranA-16` | Düşük | S4 | Dashboard — alt bildirim listesi ve sayfa sonu | Ekran AppShell ScrollView'i içinde İKİNCİ bir dikey ScrollView döndürüyor, içinde de compact NotificationCenter'ın maxHeight rs(120)'lik ÜÇ… |
| `ekranA-6` | Düşük | S4 | Auth — Kayıt Ol formu, klavye açıkken | Android'de KeyboardAvoidingView behavior=undefined; klavye yönetimi tamamen manifest adjustResize'a bırakılmış. Proje edge-to-edge (gradle.… |
| `ekranC-13` | Düşük | S4 | Dört ekran (kaydırma yapısı) | Her ekran AppShell'in dikey ScrollView'ı İÇİNDE kendi dikey ScrollView'ını açıyor; Patient/AiHistory container'daki flex:1 scroll içeriğind… |
| `ekranA-5` | Düşük | S5 | Auth (giriş/kayıt) — kart üstü ve alt bilgi | Kök View inset kullanmıyor; ScrollView içeriği ortalı olduğundan giriş modunda sorun görünmez, fakat Kayıt Ol modunda 13 alanlık form ekran… |
| `ilkel-12` | Düşük | S5 | Bildirimler sayfası (üst bar zilinden açılan pane… | Liste maxHeight rs(240) sabit. (1) Tablet/PC'de 20 bildirim 240px'lik kutuda kaydırılır; 1080px ekranın %78'i boş. (2) Telefon yatayda: she… |
| `kabuk-6` | Düşük | S5 | Kabuk — sidebar, header, bottom-nav (yatay + çent… | Yalnız insets.top (root) ve insets.bottom (bottom-nav/sheet) uygulanıyor; insets.left/right hiç okunmuyor. Telefon YATAYDA çentik/kamera de… |
| `kabuk-9` | Düşük | S5 | Toast bildirimleri (tüm ekranlar) | Toast kabı top: rs(40) sabit, useSafeAreaInsets yok; ToastProvider SafeAreaProvider içinde ama root'un paddingTop'unun DIŞINDA (_layout.tsx… |
| `ekranA-19` | Düşük | S6 | Auth — şifre kuralı göstergesi (Kayıt) | Kural satırları width '48%': 320px telefonda kart içi ≈238px → 114px hücre; 'En az 8 karakter' caption (rf 12→10-11px) + 14px nokta + gap ≈… |
| `ilkel-16` | Düşük | S6 | Yan yana iki Button içeren satırlar (AiHub btnRow… | Etiket numberOfLines=1 ve adjustsFontSizeToFit yok; font ölçeği 1.3'te (rf(14.5)×1.3 ≈ 19px) veya 320px'te iki düğme yan yana ('Analizi Baş… |
| `ilkel-18` | Düşük | S6 | Seans Detayı → Bobin Çalışmaları tablosu | Sütunlar sabit genişlik (colNum rs(78), colHw rs(70)); font ölçeği 1.3'te 'Başlangıç', 'Maks. °C', '1000 Hz', '12dk 30sn' hücre genişliğini… |
| `kapsam-7` | Düşük | S6 | AppShell üst bantları — mobil güncelleme bandı (d… | Bandın eylem talimatını taşıyan alt metin `rf(11)`; tokens.ts SCALE 320 px telefonda 0.85 → rf(11)=10 px, düğme metni rf(12)=11 px. Kullanı… |
| `aihub-11` | Düşük | S7 | Kedi Sesi 'En olası 3 durum' ve Histopatoloji 'Tü… | Satır: etiket sabit rs(96) + ray flex:1 + yüzde sabit rs(40). 320 px'de sonuç kutusu içi ≈ 200 px → ray 200−82−14−34 ≈ 70 px: %5 ile %15 fa… |
| `ekranB-11` | Düşük | S7 | Simülasyon → web (WebView2 launcher, LAN tarayıcı) | Web'de iframe yüksekliği `useState(Math.max(640, height*0.78))` ile YALNIZ ilk render'da hesaplanıyor; içerik-yüksekliği postMessage ölçümü… |
| `site-10` | Düşük | W | Hesap menüsü, Giriş modalı, Fiyat/İndir/Ödeme dur… | Site TEK koyu tema (body bg oklch 13%, index.css 44-47) ama durum metinleri Tailwind `dark:` varyantına bağlı; Tailwind v4'te `@custom-vari… |
| `site-12` | Düşük | W | Ana sayfa hero maketi, İndir/Android notları, Hes… | `text-[10px]` ve `text-[11px]` ile gerçek içerik yazılıyor: maketin 'Kurulumu onar / Uygulamayı kaldır / Profilleri değiştir' satırı ve alt… |
| `site-14` | Düşük | W | Ana sayfa hero ve tüm bölümler (geniş ekran) | Kapsayıcı `max-w-6xl` (1152px) ve başlık `lg:text-[3.4rem]` sabit; 1920px'te içerik %60, 2560px'te %45 genişlikte kalıyor, `.bg-hero` ızgar… |
| `site-15` | Düşük | W | Mobil menü içindeki 'Hesabım' açılır kutusu | Menü `absolute right-0 w-72` (288px); mobil drawer'da sarmalayıcı genişliği 320-40-24 = 256px → menü sarmalayıcının 32px solundan başlıyor,… |
| `site-16` | Düşük | W | Footer bağlantı sütunları (dar telefon) | `grid-cols-2 gap-x-10` 320px'te sütun başına (280-40)/2 = 120px bırakıyor; 'İptal, İade ve Cayma Hakkı', 'Mesafeli Satış Sözleşmesi', 'KVKK… |
| `site-2` | Düşük | W | Header mobil menü (drawer) | Mobil menü `sticky top-0` header'ın İÇİNDE, kendi scroll kabı yok. Açıkken toplam yükseklik ≈ 64 (bar) + 32 (py-4) + 4×40 (linkler) + 12 (g… |
| `site-4` | Düşük | W | Tüm sayfa geçişleri (ScrollToTop) | `html { scroll-behavior: smooth }` koşulsuz ve ScrollToTop `window.scrollTo(0,0)` çağırıyor (CSS scroll-behavior'a uyar). Footer'daki bir b… |
| `site-6` | Düşük | W | Fiyatlandırma / plan kartları | lg (1024px) kırılımında 4 sütun: kart genişliği (1024-48-72)/4 ≈ 226px, p-7 sonrası iç alan ≈ 170px; 1152px'te ≈ 202px. Büyük fiyat satırı … |
| `site-7` | Düşük | W | Fiyatlandırma / Kurumsal + deneme kartı | sm (640px) kırılımında yatay düzen açılıyor ve düğme grubu `shrink-0` + iki düğme yan yana (~320px). 640-~900px'te metin bloğuna 640-48-80(… |
| `site-9` | Düşük | W | İndir / platform kartları | max-w-5xl (1024px) kapsayıcıda lg'de 4 sütun: kart iç genişliği ≈ 229-56 = 173px. Birincil düğme 'Giriş yap ve indir' (ikon 16 + gap 8 + me… |
| `aihub-13` | Düşük | — | Evcil Hayvan Sahibi ekranı — 'Kamerayı Aç' / 'Gal… | İki flex:1 düğme, padding spacing.xl (20-31 px) ve yazı typography.subtitle (14-19 px), numberOfLines yok. 320 px'de her düğmeye ~121 px, i… |
| `aihub-14` | Düşük | — | Canlı kamera rozetleri ('KAMERA AKTİF', 'ÖNİZLEME… | Güvenlik mesajı taşıyan rozet yazıları rf(10) → 320 px telefonda 9 px, dBar etiketi 8 px; rs/rf küçültmesi + koyu yarı saydam zemin. 'BOBİN… |
| `aihub-7` | Düşük | — | AI Hub modül kartı listesi (Araştırma modunda 'Ek… | Kart satırı: ikon rs(44) + label/desc + Eklenti rozeti + ▼ chevron. 320 px'de kullanılabilir genişlik ≈ 232 px; ikon 37 + üç gap 30 + rozet… |
| `aihub-8` | Düşük | — | VisionModule Yüz Ağrısı (FGS) başlık satırı — dar… | Başlık + alt başlık `flex:1` solda, sağda dikey yığılmış 'Otonom Biofeedback' anahtarı (ikon 16 + yazı 11 px + padding) ve 'Kuyruklu · Pro+… |
| `ekranA-11` | Düşük | — | Settings — Donanım Bakım düğmeleri | btnOutline'da flexDirection tanımlı değil (sütun); ikon `marginRight: 8` ile satır beklenerek eklenmiş → ikon metnin ÜSTÜNDE ayrı satırda ç… |
| `ekranA-18` | Düşük | — | Settings — giriş alanı yer tutucuları | 'Eşleştirme kodu (örn: A3F9K2) veya cihaz kimliği' (46 kar.) ve '192.168.1.100 veya https://xxxx.trycloudflare.com' (50 kar.) yer tutucular… |
| `ekranA-20` | Düşük | — | Settings — Hesap Bilgileri (salt-okunur) | Info satırında etiket ve değer yan yana; değer sağa hizalı, numberOfLines=2. 320-360px'te 'Adres' değeri (açık adres genelde 40-80 kar.) 2 … |
| `ekranA-9` | Düşük | — | Settings — Cihaz Eşleştirme kodu satırı | Eşleştirme kodu Text'i flex:1 almıyor (hemen altındaki cihaz-kimliği satırında var). 'Bu cihazın eşleştirme kodu: A3F9K2 (uzaktan geçersiz)… |
| `ekranB-13` | Düşük | — | Sensörler ve Simülasyon — dar/yatay telefon | AppShell zaten routeMeta başlığı+alt başlığı çiziyor; SensorMonitor ('📡 Sensör Monitörü' + alt metin) ve DemaSimulator (typography.title 24… |
| `ekranC-10` | Düşük | — | AI Geçmişi (açık kart detay satırları) | detailRow: anahtar flexShrink:0, değer flex:1 sağa hizalı. 320px telefonda (kart içi ≈220px) 'Tahmini kalp atım aralığı' gibi uzun anahtar … |
| `ekranC-12` | Düşük | — | AI Geçmişi, Raporlar | AppShell içerik alanı zaten padding spacing.xl (320px'te 20px) veriyor; AiHistory headerRow/segment/chipsRow/list ayrıca paddingHorizontal/… |
| `ekranC-15` | Düşük | — | Raporlar (Bobin Detayları tablosu) | 6 sütun flex:1 ile container maxWidth rs(1200)=1560px'e kadar gerilir: 1920-2560 PC'de her sütun ≈250px, değerler sola hizalı → '0.000' ile… |
| `ilkel-14` | Düşük | — | AI öneri modalı meta hücreleri/tablo başlıkları; … | metaLabel rf(10) → 320px'te 9px, rel/xai/th rf(11) → 10px; SVG eksen yazıları 10-11 (viewBox küçülmesiyle daha da küçük). Hekim 'Lokalizasy… |
| `ilkel-15` | Düşük | — | PC/tarayıcıda tüm düğmeler (Tauri WebView2, LAN t… | Pressable'da hover/focus-visible stili yok (yalnız basış-scale). Fare kullanıcısı düğmenin tıklanabilir olduğunu imleç/renk değişimiyle gör… |
| `kabuk-10` | Düşük | — | İçerik alanı — Ayarlar, Sensörler, AI Geçmişi, Si… | Kabuk içerik ScrollView'inde maxWidth/ortalama yok; grid kullanmayan ekranlar (Ayarlar, Sensörler, AI Geçmişi) ve tüm banner'lar 1920-2560p… |
| `kapsam-6` | Düşük | — | AppShell üst bantları — kurtarma kodu / güncellem… | Bantlar AppShell içerik ScrollView'unun DIŞINDA, yalnız `margin: spacing.sm` ile tam genişliğe yayılıyor; AppShell'in `content` stili de ma… |
| `kapsam-8` | Düşük | — | AppShell üst bantları — kurtarma kodu bandı (dar … | Satır düzeni (ikon | flex:1 metin | 'Kaydettim' düğmesi ≈ 90 px) dar telefonda (a, 320 px) metne ≈ 165 px bırakır; 2 cümle + dosya yolu (`C… |
| `matris-12` | Düşük | — | LAN/uzak tarayıcı — iOS Safari / PWA, yatay | Viewport meta'da viewport-fit=cover yok → iOS Safari'de yatay çentikli telefonda sayfa çentik dışına letterbox'lanır (kenarlarda body arka … |

---
*Üretim: `plan_uret.py` — 9 planlayıcı + 2 inceleyici + 1 kapı tasarımcısı; çerçeve Claude.*
