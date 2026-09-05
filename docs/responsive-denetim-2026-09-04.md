# PEMF Responsive Tasarım Denetimi — 2026-09-04

**İkinci doğrulama:** bu sürümde her bulgu Claude tarafından kaynak kodda tek tek yeniden açıldı (bkz. §8).

**Kapsam:** pf (mobil APK + PC/WebView2 web export + LAN tarayıcı), başlatıcı istemcisi (launcher/app/ui), tanıtım ve indirme sitesi (pemf-vet-web). **Soru:** Her kullanıcı hangi ekranda kullanırsa kullansın arayüz düzgün görünüyor mu?

## 1. Karar

**Hayır — henüz tam responsive değil.** Altyapı var ve çoğu yerde doğru kurulmuş (breakpoint tek kaynağı, `useResponsive`, `ResponsiveGrid`, safe-area kabukta, içerik geniş ekranda `maxWidth` ile ortalanıyor, hover'a bağımlı işlev yok, hareket-azalt desteği). Buna rağmen **5 yüksek, 55 orta, 61 düşük** şiddette, koda karşı doğrulanmış **121 bulgu** var; çoğu **dokuz sistemik kök nedene** iniyor. Telefon dikeyde çekirdek akış çalışıyor; **telefon yatay, tablet dikey, DPI'lı küçük PC penceresi ve sistem yazı ölçeği** senaryolarında düzen bozuluyor. Bulguların 31%'i 'kısmen' (doğru ama etkisi sınırlı/koşullu) olarak işaretlendi. {IKINCI_CUMLE}

| Şiddet | Sayı | Anlamı |
|---|---|---|
| Yüksek | 5 | kullanıcı işi yapamıyor ya da veri okunamıyor |
| Orta | 55 | ciddi görsel bozulma / zor kullanım |
| Düşük | 61 | kozmetik |

## 2. Yöntem

- 22 bağımsız denetçi ajan: 10 bulucu (alan başına), 1 kapsam eleştirmeni (okunmamış 6 arayüz dosyasını tamamladı), alan başına çürütücü (her bulgu dosya+satır kanıtıyla yeniden okundu; 'doğru / kısmen / yanlış' kararı ve şiddet düzeltmesi).
- Ampirik ölçüm: Edge headless ile pf web export (giriş kapısı + kayıt formu), başlatıcı HTML'i (7 ekran durumu) ve canlı site (4 sayfa) **11 görünüm alanında** (320×568 … 2560×1440, 640×360 yatay telefon, 700×540 başlatıcı minimumu, 911×512 = 1366×768 @%150 DPI) render edilip 148 görüntü incelendi. Not: `--window-size` tek başına düzen görünüm alanını değiştirmiyor (innerWidth sabit kalıyor); ölçümler CDP ile görünüm alanı zorlanarak alındı.
- Ölçülemeyenler: Android sistem yazı ölçeği, gerçek klavye, çentik — bunlar kod okumasıyla değerlendirildi ve 'olası' olarak işaretlendi.

## 3. Cihaz sınıfı matrisi

✓ düzgün · △ kusurlu ama kullanılabilir · ✗ bozuluyor · — geçerli değil

| Sınıf | Ekran | pf uygulama | Başlatıcı | Site | Not (pf) | Not (başlatıcı) | Not (site) |
|---|---|---|---|---|---|---|---|
| a | Dar telefon 320-360 px | △ | — | ✗ | Üst bar sıkışıyor, dokunma hedefleri 38 px'e iniyor, uzun etiketler kırpılıyor | — | Ana sayfa yatay taşıyor (LauncherMock) |
| b | Telefon 375-430 px | △ | — | △ | Genel düzen iyi; dokunma hedefleri ve yazı ölçeği sorunları | — | Dokunma hedefleri, tablo ipucu |
| c | Telefon yatay | ✗ | — | ✓ | Yükseklik hiç hesaba katılmıyor; modallar/sayfalar kaydırılamıyor; sol-sağ safe-area yok | — | Sorun görülmedi |
| d | Tablet 768-1024 | ✗ | — | △ | Kenar çubuğu %42 + %130 ölçek → içerik 352 px; ızgara sütunları yanlış | — | Üst çubuk 768-830 px'te sıkışıyor |
| e | PC penceresi (WebView2) | △ | △ | — | Ölçek hep %130; 700-767 px'te telefon kabuğu | 700-1040 px'te ortalanmış taşma (üst kısım kaydırılamıyor) | — |
| f | PC geniş 1920-2560 | ✓ | △ | △ | maxWidth ile ortalanıyor | 560 px'lik ada, 11-12 px yazı | 1152 px sabit kapsayıcı, 4K'da küçük |
| g | DPI %125-200 | △ | ✗ | ✓ | Canvas grafik bulanık; ölçek üst üste biniyor | Min pencere 540 px > çalışma alanı 472-516 px | rem tabanlı, sorunsuz |
| h | LAN / uzak tarayıcı | △ | — | — | viewport-fit=cover yok (iOS yatay); Safari input/klavye davranışı | — | — |
| i | Sistem yazı ölçeği | ✗ | — | — | Hiçbir Text sınırlandırılmamış; alt bar, süre, tablo taşıyor | — | — |
| j | Çentik / klavye | △ | — | △ | Klavye yalnız Giriş'te yönetiliyor; Welcome/Gate inset'siz | — | Modal 90vh, iOS zoom |

## 4. Sistemik kök nedenler (öncelik sırası)

Bulguların büyük kısmı aşağıdaki dokuz kökten geliyor; kökü düzeltmek bağlı bulguları topluca kapatır.

### S1. Ölçek sabiti PC/tablette hep %130

**Yer:** `pf/src/theme/tokens.ts:10-25` · **Bağlı bulgu:** 8 (`matris-3`, `kabuk-1`, `ekranC-14`, `ilkel-17`, `ampirik-8`, `ekranB-12`, `matris-4`, `aihub-10`) · **Efor:** 2-4 saat, tek dosya + 3 dokunuş; en çok bulguyu kapatan değişiklik

rs()/rf() ölçeği uygulama açılışında BİR KEZ, kısa kenar/375 formülüyle hesaplanıp 1,30'a sabitleniyor. Kısa kenarı 488 px'i geçen HER tablet, PC penceresi ve LAN tarayıcısında bütün boşluk, yazı, kenar çubuğu (248→322 px) ve maxWidth sınırları (1100→1430 px) %30 büyüyor; pencere küçültülünce yeniden hesaplanmıyor. Tablet dikeyde içeriğe 352 px kalması ve PC'de 'telefon büyütmesi' görünümü buradan geliyor.

**Çözüm:** SCALE tavanını ortama göre ver: web/PC ve kısa kenar ≥ 600 px'te 1,0-1,10; kenar çubuğu genişliğini ölçeksiz sabit tut; maxWidth sınırlarını rs() ile çarpma. Pencere yeniden boyutlandığında useResponsive üzerinden canlı değer kullan.

### S2. Sütun ve kompaktlık PENCERE genişliğinden hesaplanıyor, kenar çubuğu düşülmüyor

**Yer:** `pf/src/components/ui/ResponsiveGrid.tsx:11-14, hooks/useResponsive.ts, AppShell.tsx:99` · **Bağlı bulgu:** 10 (`ekranA-1`, `ekranB-1`, `ekranC-1`, `kabuk-8`, `ilkel-8`, `aihub-4`, `ekranA-2`, `ekranA-3`, `ekranA-13`, `kabuk-2`) · **Efor:** 1 gün; 3 yüksek + 7 orta bulguyu kapatır

ResponsiveGrid ve isCompact yalnız pencere genişliğine bakıyor. 768 px'ten itibaren 322 px'lik kenar çubuğu açıldığı halde ızgara 2-3 sütun kuruyor: 768 dikey tablette hücre ≈176 px (metrik değerleri kırpılıyor), 770 px'e daraltılmış PC penceresinde aynı sorun; AI Hub'da üç düğme yan yana sıkışıyor. Tablet dikeyde kenar çubuğu ekranın %42'sini alıyor.

**Çözüm:** ResponsiveGrid kendi genişliğini onLayout ile ölçsün (Skeleton/SensorMonitor deseni); useResponsive'a contentWidth (pencere − kenar çubuğu − iç boşluk) ve buna dayalı isCompact ekle; 768-899 px tablette ikon-only 'ray' kenar çubuğu (72 px).

### S3. Dokunma hedefleri 44 px'in altında ve ölçekle küçülüyor

**Yer:** `tokens.ts + 20'den fazla bileşen` · **Bağlı bulgu:** 22 (`ilkel-7`, `aihub-5`, `ekranB-4`, `ekranC-5`, `matris-8`, `ilkel-3`, `ilkel-4`, `ilkel-5`, `kapsam-2`, `kapsam-3`, `kapsam-5`, `ampirik-4`, `ampirik-5`, `ekranA-10`, `ekranA-12`, `ekranA-14`, `ekranB-15`, `ekranC-7`, `ekranC-8`, `site-11`, `ampirik-7`, `launcher-11`) · **Efor:** 1-2 gün; sistematik tarama + ilkel

rs(44) 320 px telefonda 38 px'e iniyor; çipler (eksen/bobin/organ/CKD Evet-Hayır/semptom), ısı haritası anahtarı, bildirim eylemleri, 'Şifremi unuttum', not düzenle/Kaydet/İptal, banner kapatma X'leri, AI onay modalı kapatma, 8'li bobin seçicide hitSlop çakışması… 22-30 px hedefler. Tıbbi kayda giden seçimlerde (hasta tepkisi çipleri, CKD) yanlış seçim riski.

**Çözüm:** tokens.ts'e ölçekten bağımsız `touch = { min: max(44, rs(44)), sm: 40 }` ekle; ortak Chip ilkeli (minHeight 40, paddingVertical sm); tüm ikon-düğmelere AppShell.iconBtn (44×44) + hitSlop; bobin seçicide hitSlop ≤ gap/2.

### S4. Klavye yönetimi yalnız Giriş ekranında

**Yer:** `AppShell.tsx:385-394; yalnız AuthScreen'de KeyboardAvoidingView` · **Bağlı bulgu:** 12 (`kabuk-7`, `ekranC-11`, `ekranA-6`, `ekranA-7`, `aihub-6`, `ilkel-11`, `ilkel-19`, `ekranB-9`, `matris-7`, `ampirik-10`, `ekranA-16`, `ekranC-13`) · **Efor:** 1 gün; kabuk + 6 ekranda iç ScrollView temizliği

Hasta formu, seans notu, ayarlar, CKD formu (14 alan), bobin parametreleri: iOS'ta ve yatay telefonda alt yarıdaki girişler klavyenin altında kalıyor; iç ScrollView'larda keyboardShouldPersistTaps olmadığından 'Başlat/Kaydet' düğmesine ilk dokunuş yalnız klavyeyi kapatıyor. Android 15 edge-to-edge ile adjustResize güvencesi de zayıflıyor.

**Çözüm:** Kabuk düzeyinde tek çözüm: AppShell içerik alanını KeyboardAvoidingView (iOS padding) ile sar, klavye açıkken alt çubuğu gizle ve ACİL DURDUR ofsetini 0'a çek; ekranların kendi iç ScrollView'larını düz View yap (kabuk zaten kaydırıyor ve 'handled' veriyor); alt-sayfa modallarını KAV ile sar.

### S5. Yükseklik ve yatay telefon hiç hesaba katılmıyor; sol/sağ safe-area yok

**Yer:** `useResponsive.ts, AppShell.tsx:209, modallar` · **Bağlı bulgu:** 18 (`matris-6`, `kabuk-4`, `kabuk-6`, `kabuk-11`, `ekranB-3`, `ekranB-14`, `kapsam-1`, `kapsam-4`, `ilkel-6`, `ilkel-10`, `ilkel-12`, `ekranB-10`, `matris-5`, `ekranA-4`, `ekranA-5`, `matris-11`, `ilkel-13`, `kabuk-9`) · **Efor:** 1-2 gün

Düzen yalnız genişliğe bakıyor. 640-930×360-430 px yatay telefonda üst bar (~90 px) + alt bar (~72 px) + kayan ACİL DURDUR içeriğin alt üçte birini örtüyor; 'Daha Fazla' sayfası, güncelleme kapısı, plan modalı, AI onay modalı ve yedek parolası diyaloğu ekrandan uzun ve kaydırılamıyor. Çentik tarafındaki insets.left/right hiç okunmuyor (iOS yatay, Android kamera deliği).

**Çözüm:** useResponsive'a `isShort = height < 500`; kısa yükseklikte alt başlığı gizle, kenar çubuğu yerine alt bar; grafik yüksekliklerini yüksekliğe bağla; tüm ortalanmış modalları ScrollView + maxHeight ile kur; AppShell köküne insets.left/right.

### S6. Sistem yazı ölçeği sınırlandırılmamış

**Yer:** `hiçbir Text'te allowFontScaling / maxFontSizeMultiplier yok` · **Bağlı bulgu:** 7 (`matris-1`, `kabuk-5`, `ekranB-8`, `ilkel-16`, `ilkel-18`, `ekranA-19`, `kapsam-7`) · **Efor:** Yarım gün

Android 'Yazı boyutu' 1,3'te alt bar etiketleri ('Akıllı Teşhis', 'Seans Geçmişi'), seans süresi (1:05:30), bobin tablosu hücreleri, yan yana düğme etiketleri taşıyor/kırpılıyor; rozet sayıları 16 px kutudan çıkıyor.

**Çözüm:** fonts.ts injectFont() içinde varsayılan `maxFontSizeMultiplier: 1.2` (tek nokta, web'de etkisiz); kritik sayısal alanlara adjustsFontSizeToFit + minimumFontScale; alt bar için kısa etiketler.

### S7. Grafik ve kamera katmanları sabit oranla çiziliyor

**Yer:** `SessionDetailModal, RealtimeChart, AiHubScreen kamera/bar, KpiDashboard pie` · **Bağlı bulgu:** 11 (`ekranC-3`, `ilkel-2`, `ekranB-5`, `ekranB-6`, `ilkel-9`, `aihub-1`, `aihub-2`, `aihub-3`, `ekranC-2`, `aihub-11`, `ekranB-11`) · **Efor:** 1-2 gün

Sıcaklık grafiği 720×260 sabit viewBox ile telefonda 4 px'lik eksen yazısına küçülüyor; canlı grafik canvas'ı devicePixelRatio'suz (DPI'lı PC ve telefon tarayıcısında bulanık) ve 60 px sabit kenarlarla 320 px'te 140 px çizim alanı; canlı kamera önizlemesi 'cover' ile kırpılırken üstündeki işaret katmanı 'contain' ile hizasız (ısı haritası hatasıyla aynı sınıf; AI Pro organ konumu doğrulama ekranı dahil); Fantom/Petri çubukları ölçeksiz 26 px ile yanlış oran; pasta lejantı kesiliyor.

**Çözüm:** Grafik genişliğini onLayout'tan al, viewBox'ı ölçülen boyuta eşitle; canvas'ı DPR ile ölçekle ve kenarları genişliğe göre daralt; kamera kutusuna sabit yükseklik yerine aspectRatio, önizleme ve katmana AYNI resizeMode; çubuk dolgusunu yüzdeyle ver; pasta lejantını RN View ile çiz.

### L. Başlatıcı: ortalanmış taşma, DPI'da sığmayan pencere, klavye erişilebilirliği

**Yer:** `launcher/app/ui/index.html, tauri.conf.json` · **Bağlı bulgu:** 15 (`ampirik-2`, `launcher-1`, `launcher-2`, `matris-10`, `launcher-3`, `launcher-4`, `launcher-5`, `launcher-6`, `launcher-12`, `launcher-7`, `launcher-8`, `launcher-9`, `launcher-10`, `launcher-11`, `matris-9`) · **Efor:** 1 gün

main hem overflow:auto hem justify-content:center: içerik pencereden uzun olunca üst kısım kaydırılamayan negatif alana düşüyor (1366×768 @%150'de profil seçimi başlığı görünmüyor — ölçüldü). Pencere min 700×540 mantıksal; %150-200 DPI'lı dizüstünde çalışma alanı 472-516 px olduğundan alt düğmeler ekran dışında. ≤1040 px'te düğmeler ikon-only kalıyor ama title/aria-label yok; profil kartları klavyeyle seçilemiyor; modallarda odak/Escape yok; 680 px medya sorgusu ölü (pencere 700'ün altına inemiyor).

**Çözüm:** `main { justify-content:flex-start } .stage { margin:auto 0 }`; min boyutu monitör çalışma alanına göre kırp (work_area − 40); ikon-only düğmelere title/aria-label; kartları button + aria-pressed yap; openModal() ile odak + inert + Escape; 680 kuralı yerine `@media (max-height: 620px)`.

### W. Site: 320 px'te ana sayfa taşıyor; tablet başlığı sıkışıyor; dokunma ve iOS ayrıntıları

**Yer:** `pemf-vet-web/src` · **Bağlı bulgu:** 21 (`ampirik-1`, `site-1`, `ampirik-3`, `site-5`, `ampirik-6`, `matris-13`, `site-3`, `site-13`, `site-11`, `ampirik-7`, `site-16`, `site-2`, `site-7`, `site-8`, `site-10`, `site-12`, `site-14`, `site-15`, `site-4`, `site-6`, `site-9`) · **Efor:** 1 gün

LauncherMock'taki nowrap alt başlık grid hücresinin min-content genişliğini 371 px'e çıkarıp 320-360 px telefonda tüm sayfayı yatay taşırıyor (ölçüldü). Üst çubuk 768 px'te masaüstü düzenine geçiyor ama ~800 px istiyor. Fiyat tablosu 560 px min genişlikle kayıyor, ilk sütun sabit değil, kaydırma ipucu yok. Form girişleri 14 px → iOS Safari odakta yakınlaştırıyor. Giriş modalı 90vh (iOS araç çubuğu + klavye). Alt bilgi bağlantıları 20 px hedef; 320 px'te iki sütun sıkışıyor. Tek koyu tema olduğu halde durum renkleri `dark:` varyantına bağlı (Tailwind v4'te tanımsız).

**Çözüm:** Home/Features sarmalayıcısına `min-w-0` (yüksek — tek satır); Header kırılımını lg'ye çek + `whitespace-nowrap`; tabloya sticky ilk sütun + kenar gradyanı; `@media (pointer:coarse)` ile input 16 px; modal `100svh`; footer `grid-cols-1 min-[400px]:grid-cols-2`; Link'lere `py-1.5`; `@custom-variant dark`.

## 5. Yüksek şiddetli bulgular

### ampirik-1 — Web sitesi ana sayfa (/) hero bölümü ve /features 'Masaüstü uygulaması' bölümü …

**Yer:** `pemf-vet-web/src/components/LauncherMock.tsx (kök neden) + pemf-vet-web/src/pages/Home.tsx:16,51 ve Features.tsx:63 (yerleşim)` (LauncherMock.tsx 39-62; Home.tsx 16 ve 51; Features.tsx 63) · **Cihaz:** dar telefon 320-360, telefon 375-430 · **Doğrulama:** dogru/kesin

LauncherMock'un üst şeridindeki `truncate` (white-space:nowrap) alt başlık 'Veteriner PEMF seans + yapay zekâ teşhis platformu' (229px) + logo 28 + sürüm çipi 61 + boşluklar, mock'un min-content genişliğini 371px'e çıkarıyor; mock'u tutan grid öğesi (`<div className="lg:pl-6">`) `min-width:auto` olduğu için grid sütunu bu genişliğin altına inemiyor ve TÜM SAYFA 391px'e (371+2×20 padding) zorlanıyor. 320 ve 360px telefonlarda hero başlığı 'Kontrol Standardı' ve açıklama paragrafı sağdan KESİLİYOR ('...elektromanyetik ala', 'PEMF Vet'i indir', 'Sürüm 1.9.45 · 3 MB kurulu'), sayfa yatay kaydırma kazanıyor; giriş modalı da 391px'e göre konumlanıp 'Şifremi unuttum' bağlantısı ekran dışına taşıyor (l=259,r=344 > 320). /features'ta 'Tek pencereden yöneti[m]' başlığı ve 'Son güncelleme' kartı da kesiliyor.

**Kanıt:** CDP ölçümü 320×568: innerWidth=391, document.scrollWidth=391 (download/pricing sayfalarında 320); `.glow-ring` display:none yapılınca scrollWidth 391→320 (bisect kanıtı). Header çocukları: `span.min-w-0` w=229 (truncate/nowrap), `ml-auto shrink-0` w=61, logo 28. 360×800'de de innerWidth=391. Görüntüler: web_home_320x568.png (başlık ve paragraf sağdan kesik), web_home_320x568_scroll520.png (mock k…

**Öneri:** Tek satırlık kesin çözüm: Home.tsx:51 ve Features.tsx:63 sarmalayıcısına `min-w-0` (`<div className="min-w-0 lg:pl-6">`). Grid öğesinin min-width'i 0 olunca track container genişliğine iner; LauncherMock'un iç `span.min-w-0 + truncate` yapısı zaten var olduğu için alt başlık kendiliğinden '…' ile kısalır — LauncherMock.tsx'e ek `flex-1` şart değil (isteğe bağlı: :50 alt başlığa `hidden sm:block`). Doğrulama: cdp_eval.py ile 320/360'ta document.scrollingElement.scrollWidth === innerWidth ve `.glow-ring` genişliği ≤ 280px.

### ekranC-1 — Hastalar (hasta kartı ızgarası); aynı kök neden Geçmiş/KPI ızgaralarını da etki…

**Yer:** `pf/src/components/ui/ResponsiveGrid.tsx (+ AppShell.tsx, PatientScreen.tsx)` (ResponsiveGrid.tsx:12-14; AppShell.tsx:99, 517; PatientScreen.tsx:297-329, 394) · **Cihaz:** telefon yatay, tablet 768-1024, PC pencere (WebView2), DPI %125-200 · **Doğrulama:** dogru/kesin

ResponsiveGrid sütun sayısını PENCERE genişliğinden hesaplıyor, kenar çubuğunu (tablet+desktop'ta gösterilen rs(248)=322px) ve AppShell'in 2×spacing.xl padding'ini düşmüyor. iPad dikey 768px: 768/2=384≥340 → 2 sütun; gerçek içerik 768-322-62=384px → hücre ≈192-21=171px, kart içi ≈127px. Hasta kartında 3 aksiyon düğmesi (3×rs(44)=171px + boşluklar ≈191px) + 24px ikon → hasta adı 0 genişliğe düşer, düğmeler kart kenarından taşar. Aynı şey telefon yatayda (800px → 'tablet', sidebar açılır) ve DPI %150 laptopta (1366×768 → 911×512 mantıksal) olur. 1024px masaüstü: 3 sütun → kart içi ≈150px, aynı bozulma.

**Kanıt:** ResponsiveGrid.tsx:12-13 const { width, columns } = useResponsive(); const targetColumns = width / columns < minItemWidth ? Math.max(1, columns - 1) : columns; AppShell.tsx:517 width: rs(248) // desktop = isDesktop || isTablet (satır 99) PatientScreen.tsx:394 actionBtnIcon: { ... minWidth: rs(44), minHeight: rs(44) ... } // ×3 yan yana

**Öneri:** Öneri doğru; en küçük değişiklik: useResponsive'a `contentWidth = width - ((isTablet||isDesktop) ? rs(248) : 0) - 2*spacing.xl` ekleyip ResponsiveGrid.tsx:13'te `width` yerine bunu kullan (targetColumns = max(1, floor(contentWidth/minItemWidth)) ile clamp). PatientScreen cardHeader'a flexWrap:'wrap' + actions'a `flexBasis:'100%'` (hücre < ~300px iken) ver ki aksiyon satırı başlığın altına insin. Öncelikle tokens.ts SCALE üst sınırını PC/tablette düşürmek (ekranC-14) bu bulgunun büyüklüğünü de azaltır.

### ekranC-3 — Seans Geçmişi → Seans Detayı modalı (Sıcaklık Grafiği)

**Yer:** `pf/src/components/domain/SessionDetailModal.tsx` (406-441, 462-502, 638) · **Cihaz:** dar telefon 320-360, telefon 375-430, telefon yatay, yazı ölçeği · **Doğrulama:** dogru/kesin

TempChart SVG sabit viewBox 720×260 ile width='100%' + height rs(260) çiziliyor (preserveAspectRatio varsayılan 'meet'). Telefonda modal kart içi ≈270-300px → ölçek ≈0.38: eksen yazıları fontSize 11/10 → ≈4px (okunamaz), çizim alanı 720×260 → ≈270×98px; 260px yüksekliğindeki kutuda üstte/altta ≈80px boş bant kalır. Sıcaklık eğrisi 98px yüksekliğe sıkışır, 48°C eşiği görsel olarak ayırt edilemez.

**Kanıt:** SessionDetailModal.tsx:406-407 const width = 720; const height = 260; SessionDetailModal.tsx:441 <Svg width="100%" height={rs(260)} viewBox={`0 0 ${width} ${height}`}> SessionDetailModal.tsx:467 fontSize={11} // viewBox birimi → 0.38 ölçekte ≈4px

**Öneri:** Öneri doğru: chartWrap'a onLayout ile genişliği al (KpiDashboard chartInner deseni), `width` sabitini ölçülen genişlikle, `height`i rs(240) ile değiştir ve viewBox'ı aynı boyutlarla kur; fontSize'ları rf(11)/rf(10) yap; ölçülen genişlik < 400 ise X etiket sayısını 5→3 ve PAD.left'i 40'a düşür. (c) sınıfını listeden çıkar.

### launcher-1 — s-login, s-select (dep-notice/hata ile), s-ready (notice+hata ile), s-install (…

**Yer:** `launcher/app/ui/index.html` (96-98, 128 (main / .stage)) · **Cihaz:** PC pencere (WebView2), DPI %125-200 · **Doğrulama:** dogru/kesin

main hem overflow:auto hem justify-content:center (sütun flex) ve .stage'de margin:auto yok. İçerik main'den uzun olunca flexbox içeriği ortalar: taşan kısım ÜSTE ve alta eşit dağılır; üstteki kısım kaydırma başlangıcının önünde kalır ve hiçbir kaydırmayla ulaşılamaz. 700x540 minimum pencerede kullanılabilir yükseklik 540-75(header)-43(footer)-36(main padding)=386px. Giriş ekranı tek başına ≈414px (başlık 45 + 2 satır lead 58 + form 200 + düğme 57 + alt bağlantılar 54) → 'Giriş yapın' başlığının üst ~14px'i kesilir; 'E-posta ve parola gerekli' hatası eklenince (~60px) ≈44px kesilir, başlık okunmaz. Profil seçimi: 3 kart 241 + başlık/lead 103 + düğme 57 = 401 (>386); dep-notice (~86) veya 'Geri dön' (52) veya hata kutusu (≤166) eklenince 50-200px üstten kesilir → 'Kullanım profilinizi seçin' ve ilk kartın üstü görünmez. 1366x768 @%150 maximize (911x~480 mantıksal) durumunda alan 326px'e düşer; 'Hazır!' ekranı (~390px) bile üstten kesilir (yeşil onay ikonu + başlık).

**Kanıt:** main { flex: 1; overflow: auto; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 18px 30px; ... } .stage { width: 100%; max-width: 560px; }

**Öneri:** Her ortamda çalışan çözüm: `main { justify-content: flex-start; }` + `.stage { margin: auto 0; }` (auto margin sığdığında ortalar, taştığında 0'a düşer ve içerik en üstten başlayıp kaydırılabilir). `justify-content: safe center` Chromium 115+ (WebView2 evergreen) için ek olarak konabilir ama tek başına bırakılmasın. Buna ek olarak `@media (max-height: 620px) { main { padding: 10px 20px } .title { font-size: 22px } .lead { margin-bottom: 10px } .check { width:64px; height:64px } .btn.big { padding: 12px 32px } }` ile 540 bütçesine (386px) login+hata (≈482px) sığdırılamaz ama fark 30-40px'e iner; kalan kısım kaydırmayla erişilir.

### launcher-2 — tüm ekranlar (özellikle s-ready alt bağlantıları, s-login 'Şifremi unuttum/Hesa…

**Yer:** `launcher/app/tauri.conf.json` (13-19 (windows[0]); main.rs 2079-2089 yalnız gunc kipinde min_size kaldırılıyor) · **Cihaz:** DPI %125-200, PC pencere (WebView2) · **Doğrulama:** dogru/kesin

Pencere 880x600 mantıksal, minHeight 540 — Windows DPI ölçeğinde mantıksal çalışma alanı bunun altına iniyor: 1366x768 @%150 → 911x512, görev çubuğu düşünce ≈472px; 1280x720 @%125 → 1024x576-32 ≈ 544 (600 için yetmez); 1920x1080 @%200 → 960x540-24 ≈ 516. Pencere ekrandan ~70-130px taşar; kullanıcı 540'ın altına küçültemez, maximize da min-track-size nedeniyle yine 540'ta kalır; başlık çubuğu ekranın üstünden yukarı sürüklenemez. main içeriği pencerede ortalandığı için (launcher-1) s-ready'de 'Profilleri değiştir / Onar / Uygulamayı kaldır' (içerik ≈103-529px konumunda, alt bağlantılar ≈500-529) ve footer 'Destek' ekranın dışında kalır; s-login'de 'Şifremi unuttum / Hesap oluştur / Çevrimdışı başlat' görünmez. Mouse ile bu düğmelere ulaşılamaz (yalnız Tab ile). Sahada 1366x768 @%150 en yaygın laptop yapılandırması.

**Kanıt:** "width": 880, "height": 600, "minWidth": 700, "minHeight": 540, "resizable": true, "center": true

**Öneri:** main.rs normal-kip `.setup`'ında: `let m = w.current_monitor()?; let wa = m.work_area(); let sf = m.scale_factor(); let h = ((wa.size.height as f64 / sf) - 40.0).min(600.0); w.set_min_size(Some(LogicalSize::new(700.0, h.min(540.0).max(440.0)))); w.set_size(LogicalSize::new(880.0, h)); w.center();` — gunc kipindeki 250ms notu burada da geçerli, aynı gecikmeli iş parçacığı kalıbını kullan. Paralel olarak minHeight'ı 460'a indir ve launcher-1'in `margin:auto` + max-height medya sorgusunu ekle ki 460'ta içerik kaydırılabilir kalsın.

## 6. Uygulama planı

| Faz | İçerik | Kapattığı bulgu | Süre |
|---|---|---|---|
| 0 — Acil | 7 yüksek: site `min-w-0`; başlatıcı `margin:auto` + DPI min-boyut; ResponsiveGrid onLayout + contentWidth; sıcaklık grafiği onLayout; seans kartı sağ küme sarma | 7 yüksek + ~10 orta | 1-2 gün |
| 1 — Altyapı | S1 ölçek tavanı, S3 touch token + Chip ilkeli, S4 kabuk KeyboardAvoidingView + iç ScrollView temizliği, S5 isShort + insets.left/right, S6 maxFontSizeMultiplier | ~70 bulgu | 4-6 gün |
| 2 — Ekranlar | S7 grafik/kamera katmanları; AI Hub başlık/rozet/bar; Ayarlar-Hastalar-Geçmiş satır sarmaları; başlatıcı erişilebilirlik; site header/tablo/modal | ~50 bulgu | 4-5 gün |
| 3 — Kozmetik ve kilit | düşük şiddetli kalanlar; CI'da görünüm-alanı görüntü kapısı (320/640×360/768/911×512/1920) + dokunma-hedefi statik taraması | ~25 bulgu | 2-3 gün |

**Kilitler (regresyon önlemi):** (1) `tests/` altına `rs(44)`/`minHeight` taraması: Pressable/TouchableOpacity içeren dosyalarda 44 px altı sabitleri raporlayan kapı; (2) Edge headless + CDP ile 5 görünüm alanında `document.scrollingElement.scrollWidth <= innerWidth` ve seçili elemanların `getBoundingClientRect` genişliği ≥ 44 kontrolü; (3) jest'te `useResponsive` için 320/768/1024/1920 anlık görüntüleri.

## 7. Alan bazlı bulgu listesi

Kök sütunu bulgunun bağlı olduğu sistemik kökü gösterir (S1-S7, L, W). Tam metinler `docs/responsive-denetim-2026-09-04.bulgular.json` dosyasında.

### Uygulama kabuğu, tema, navigasyon (pf) — 0 yüksek / 7 orta / 3 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `kabuk-1` | Orta | `theme/tokens.ts` | SCALE uygulama açılışında BİR KEZ, kısa kenar/375 formülüyle hesaplanıp 1.30'a clamp'leniyor. Tablet, PC (WebView2), LAN tarayıcı ve DPI %125-200 senaryolarının HEPSİNDE kısa kenar ≥ 488px olduğundan her boyut sabit %30 büyür: si… | d,e,f,g,h | tokens.ts'de SCALE'i Platform.OS==='web' veya kısa kenar ≥ breakpoints.tablet iken 1 (en fazla 1.10) yap; sidebar genişliğini rs() yerine sabit 232-248 tut ve AppShell'de responsive.isTablet iken 200… | S1 | dogru |
| `kabuk-2` | Orta | `theme/breakpoints.ts` | desktop = isDesktop||isTablet → sidebar yalnız width ≥768 iken; launcher min penceresi 700px, 1366px ekranda %200 DPI 683px, %175'te 780px sınırda. Bu aralıkta PC kullanıcısı TELEFON kabuğu görür: rf(10) etiketli alt bar, 'Daha F… | e,g,h | AppShell'de panHandlers'ı `!desktop && responsive.isNative` koşuluna bağla (useResponsive zaten isNative döndürüyor); 640-767 aralığı için desktop yerine `rail` düzeni (ikon-only ~72px sidebar) ekle:… | S2 | kismen — 700-767 px PC penceresi yalnız %200 DPI'lı 1366 px ekranda ya da elle küçültülmüş pencerede oluşur; kod doğru, olasılık düşük. |
| `kabuk-3` | Orta | `components/ui/AppShell.tsx` | headerRight flexShrink:0 ve OperatorSwitcher çipi maxWidth rs(190) (e-posta/operatör adı taşıyor; ctx her zaman var → çip her zaman çizilir) + profil çipi (~50px) + Ayarlar 44px + bağlantı noktası + zil + 4×gap(12) ≈ 340-370px. 3… | a,b,i | OperatorSwitcher'a `compact` prop'u (AppShell isCompact'ta ikon-only, maxWidth rs(44)); üst bardaki ayrı Ayarlar ikonunu compact'ta kaldır (Daha Fazla sheet'inde zaten var); headerRight'a flexShrink:… |  | dogru |
| `kabuk-4` | Orta | `components/ui/AppShell.tsx` | Sheet ScrollView'suz ve maxHeight'sız düz View; veteriner/araştırma profilinde 6 rota + Çıkış = 7 satır × (minHeight rs(48)+gap 4) + başlık + padding + insets.bottom ≈ 430-460px. Telefon YATAY (360-430px yükseklik) iken sheet ekr… | c,i | moreSheet'e `maxHeight: responsive.height * 0.85` ver ve satırları ScrollView'a al (useResponsive.height zaten mevcut); yatayda (width > height) satırları iki sütun flexWrap ile diz. | S5 | kismen |
| `kabuk-5` | Orta | `components/ui/AppShell.tsx` | 5 slot, flex:1 → 320px'te slot ≈ 61px (padding sonrası ~53px), 360px'te ~61px. bottomLabel rf(10) bold, numberOfLines=1: 'Akıllı Teşhis' (13 karakter ≈ 70px) ve 'Seans Geçmişi' normal ölçekte bile 'Akıllı Te…' olarak kırpılır; An… | a,b,i | NavItem'a `short` etiket (ai:'Teşhis', dashboard:'Ana', ai_history:'AI Geçmişi'→'Geçmiş') ekle ve compact'ta onu kullan; bottomLabel/title Text'ine maxFontSizeMultiplier={1.2}; tokens'a MAX_FONT_SCAL… | S6 | dogru |
| `kabuk-7` | Orta | `components/ui/AppShell.tsx` | Kabuk ScrollView'i KeyboardAvoidingView ile sarılı değil ve alt bar position:absolute bottom:0. iOS'ta (EAS build var) klavye açılınca içerik yükselmez → ekranın alt yarısındaki girişler (hasta formu alt alanları, ayarlar) klavye… | a,b,c,j | styles.main View'ini KeyboardAvoidingView (behavior iOS 'padding', keyboardVerticalOffset insets.top) ile sar; useKeyboard/Keyboard.addListener ile klavye açıkken bottomNav'ı gizle (isCompact && !key… | S4 | kismen |
| `kabuk-8` | Orta | `components/ui/ResponsiveGrid.tsx` | Sütun sayısı PENCERE genişliğinden hesaplanıyor, sidebar düşülmüyor. Tablet dikey 768px: layout=tablet → columns=2, minItemWidth kontrolü 768/2=384 ≥ 260 geçer; ancak sidebar rs(248)=322px (kabuk-1) + content padding 2×31 sonrası… | d,g | ResponsiveGrid'de dış View'a onLayout ekleyip gerçek genişlikten hesapla: cols = clamp(floor(w / minItemWidth), 1, columns); ek olarak useResponsive'e `contentWidth` alanı (width − (desktop ? SIDEBAR… | S2 | dogru |
| `kabuk-10` | Düşük | `components/ui/AppShell.tsx` | Kabuk içerik ScrollView'inde maxWidth/ortalama yok; grid kullanmayan ekranlar (Ayarlar, Sensörler, AI Geçmişi) ve tüm banner'lar 1920-2560px'te sidebar sonrası ~1600-2200px'e gerilir: tek satır ayar/switch satırları 2 metreye yay… | f | AppShell content'e `layout==='wide' ? { maxWidth: 1440, alignSelf:'center', width:'100%' }` ekle (tek noktadan) ve ekran-içi rs(900)/rs(1100) sınırlarını AppShell'e devret; banner'ları da aynı kapsay… |  | kismen |
| `kabuk-6` | Düşük | `components/ui/AppShell.tsx` | Yalnız insets.top (root) ve insets.bottom (bottom-nav/sheet) uygulanıyor; insets.left/right hiç okunmuyor. Telefon YATAYDA çentik/kamera deliği kenara geçer (iOS ~44-48pt, Android edge-to-edge cutout): width ≥768 (ör. 800x360, 93… | c,j | root'a `paddingLeft: insets.left, paddingRight: insets.right` (209); bottomNav absolute olduğundan ona `paddingHorizontal: Math.max(insets.left, spacing.sm)`; ToastProvider/GlobalEmergencyStop de ayn… | S5 | kismen |
| `kabuk-9` | Düşük | `components/ui/ToastProvider.tsx` | Toast kabı top: rs(40) sabit, useSafeAreaInsets yok; ToastProvider SafeAreaProvider içinde ama root'un paddingTop'unun DIŞINDA (_layout.tsx:32-34). iPhone Dynamic Island/çentik (insets.top 47-59pt) ve Android edge-to-edge status … | b,c,j | Hijyen olarak useSafeAreaInsets ile `top: insets.top + spacing.md` kullan (Provider SafeAreaProvider çocuğu → hook çalışır) ve spring toValue'yu 0'a çek; left/right'a insets.left/right ekle. | S5 | kismen |

### Cihaz matrisi, yazı ölçeği, yön (pf) — 0 yüksek / 2 orta / 2 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `matris-1` | Orta | `components/ui/AppShell.tsx` | Projede hiçbir Text/TextInput'ta allowFontScaling veya maxFontSizeMultiplier yok (grep pf/src = 0). RN varsayılanı sistem yazı ölçeğini uygular; ölçek 1.3'te en riskli 5 yer: (1) alt bar etiketleri rf(10)→13px, 5 slotlu barda 'Ak… | a,b,i | fonts.ts injectFont() içinde `if (props.maxFontSizeMultiplier == null) props = { ...props, maxFontSizeMultiplier: 1.2 }` (web'de etkisiz, zararsız). SessionProgressCard timeRow'da timeBlock'lara `fle… | S6 | kismen |
| `matris-8` | Orta | `components/ui/AppShell.tsx` | Dokunma hedefleri 44 px'in çok altında: zil = 16 px ikon + padding rs(4) → ~24×24 px; 'Bağlantıyı yenile' Pressable'ı 10 px'lik nokta (çevrimiçiyken metin yok) → ~10×10 px; profil çipi paddingVertical rs(4) + 16 px ikon → ~26 px … | a,b,c,d,i | Üç Pressable'a `style={[styles.iconBtn, ...]}` (minWidth/minHeight rs(44), center) + `hitSlop={8}`; wsIndicator noktasını 44 px kutuda ortala; profileChip'e `minHeight: rs(44)` (padding'i artırmadan,… | S3 | dogru |
| `matris-12` | Düşük | `pf/dist/index.html` | Viewport meta'da viewport-fit=cover yok → iOS Safari'de yatay çentikli telefonda sayfa çentik dışına letterbox'lanır (kenarlarda body arka planı yerine beyaz/siyah şerit), safe-area-context web'de 0 döndürür. Ayrıca body{overflow… | h,j | postexport-web.js'e: `h = h.replace(/(name="viewport" content="[^"]*)"/, '$1, viewport-fit=cover, interactive-widget=resizes-content"')` + `<style>` içine `html,body{background:#121827}` (colors.bg) … |  | dogru |
| `matris-9` | Düşük | `launcher/src/main.rs` | Uygulama penceresi yalnız .maximized(true) ile açılır; min_inner_size ve inner_size yok. Kullanıcı 'geri yükle' deyince Tauri varsayılanı 800×600'e düşer ve pencere ~200 px'e kadar küçültülebilir. 800 px'te (SCALE 1.30 yükleme an… | e,g | Builder'a `.inner_size(1280.0, 800.0)` ekle ve min boyutu monitöre göre clamp'le: `let wa = app.primary_monitor()?.work_area()` (mantıksal) → `.min_inner_size((1024.0).min(wa.w-40.0), (640.0).min(wa.… | L | dogru |

### Ekranlar: Giriş, Karşılama, Ana Ekran, Ayarlar (pf) — 0 yüksek / 7 orta / 11 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `ekranA-1` | Orta | `components/ui/ResponsiveGrid.tsx (+ screens/DashboardScreen.tsx, components/ui/AppShell.tsx)` | Sütun sayısı PENCERE genişliğinden hesaplanıyor, kenar çubuğu (rs(248)=322px, ölçek 1.3) ve iki kat içerik padding'i düşülmüyor. 768px tablet dikeyde gerçek içerik genişliği ≈352px iken 2 sütun (≈176px hücre): MetricCard değeri (… | d,e,g,h | ResponsiveGrid'de pencere yerine ÖLÇÜLEN kap genişliğini kullan: `const [w,setW]=useState<number|null>(null); <View onLayout={e=>setW(e.nativeEvent.layout.width)}>`, `cols = Math.max(1, Math.floor((w… | S2 | dogru · Yüksek→Orta — 768 dikey tablette hücre ~176 px: metrik değerleri SIĞIYOR (33 px bold '1000 Hz' ≈126 px), CoilCard alt metrikleri sıkışıyor — kırılma değil sıkışma. |
| `ekranA-15` | Orta | `screens/DashboardScreen.tsx` | Kart-içi acil durdur metni typography.small (rf(11) ≈ 10-13px) — ekrandaki en kritik düğmenin yazısı en küçük yazı boyutunda; düğme yüksekliği padding md (10-16) + 13px ≈ 33-45px. Dar telefonda ve düşük yazı ölçeğinde 44pt altı, … | a,b,c,i,e | emergencyBtn'e `minHeight: rs(52), paddingVertical: spacing.md` ve emergencyBtnText'e `fontSize: rf(15), letterSpacing: 0.4` (GlobalEmergencyStop.tsx:75-93 token'ları); ya da stilleri GlobalEmergency… |  | dogru |
| `ekranA-2` | Orta | `screens/DashboardScreen.tsx` | heroGrid kartlarında minWidth rs(280)=364px (ölçek 1.3). 768px tablet dikey (iPad) veya 770px'e daraltılmış launcher penceresinde AppShell kenar çubuğu sonrası içerik ≈352px → kart minimum genişliği kaptan büyük, sağ kenardan 12p… | d,e | minWidth'i `Math.min(rs(280), contentWidth - 2*spacing.md)` ile sınırla ya da useResponsive().isTablet iken `flexBasis: '100%', minWidth: 0` uygula; kök çözüm ekranA-3'teki kenar çubuğu daraltması. | S2 | dogru |
| `ekranA-3` | Orta | `components/ui/AppShell.tsx` | 768-834px tablet dikeyde 'tablet' layout'u masaüstü gibi işleniyor: sabit rs(248)=322px kenar çubuğu ekranın %39-42'sini alıyor, içeriğe 352-418px kalıyor (dar telefondan biraz geniş). Settings'te Ad/Soyad satırı 147px'lik giriş … | d | AppShell'de `const rail = responsive.isTablet && responsive.width < 900;` → sidebar'a `width: rail ? rs(72) : Math.min(rs(248), width*0.26)` ve NavButton'a `compact={rail}` (ikon-only, label gizli); … | S2 | dogru |
| `ekranA-4` | Orta | `screens/WelcomeScreen.tsx` | Ekran AppShell dışında render ediliyor (PemfApp.tsx:49) ve safe-area inset kullanmıyor; tek üst boşluk ScrollView'in paddingVertical xxl (27-32px). iPhone (durum çubuğu 47-59pt) ve edge-to-edge Android'de (gradle edgeToEdgeEnable… | a,b,c,j | `const insets = useSafeAreaInsets();` → ScrollView contentContainerStyle'a `[styles.container, { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl, paddingLeft: Math.max(… | S5 | dogru |
| `ekranA-7` | Orta | `screens/SettingsScreen.tsx (+ AppShell.tsx)` | (1) Settings'in kendi ScrollView'inde keyboardShouldPersistTaps yok (varsayılan 'never'): native'de klavye açıkken 'Cihaza Bağlan' / 'Bağlantıyı Test Et'e ilk dokunuş yalnızca klavyeyi kapatır, ikinci dokunuş gerekir (AppShell'in… | a,b,c,d,i | SettingsScreen kökünü düz `<View style={styles.container}>` yap (AppShell zaten kaydırıyor; iç ScrollView gereksiz) — bu hem (1)'i hem ekranA-16 türü iç-içe kaydırmayı çözer. AppShell'de `Keyboard.ad… | S4 | kismen |
| `ekranA-8` | Orta | `screens/SettingsScreen.tsx` | Düğme ve durum metni flexDirection:'row' içinde; statusText'e flex/flexShrink verilmemiş (RN varsayılan flexShrink:0) ve satır sarmıyor. 320-360px telefonda düğme (~155px) + 'Ayarlar başarıyla kaydedildi.' (~170px) > 232-252px ka… | a,b,i | `actions: { flexWrap: 'wrap' }` + `statusText: { flex: 1, minWidth: rs(160), flexShrink: 1 }`; ya da başarı/hata durumunu dosyada zaten kullanılan `showToast(...)` ile ver ve satırdaki Text'i kaldır. |  | dogru |
| `ekranA-10` | Düşük | `screens/SettingsScreen.tsx` | btnOutline paddingVertical spacing.sm (7-10px) + 14px metin → 31-37px yükseklik; 'Düzenle' TouchableOpacity'de hiç padding yok, 11px metin → ~14px dokunma hedefi; saklama süresi çipleri ve 'Şifreli Yedek Oluştur'/'Yedekten Geri Y… | a,b,c,i | btnOutline/testBtn/autoBtn'e `minHeight: rs(44)`; 'Düzenle'ye `hitSlop={12}` + `style={{ paddingVertical: spacing.sm, paddingHorizontal: spacing.sm }}`; uzun vadede components/ui/Button (size_md minH… | S3 | kismen |
| `ekranA-11` | Düşük | `screens/SettingsScreen.tsx` | btnOutline'da flexDirection tanımlı değil (sütun); ikon `marginRight: 8` ile satır beklenerek eklenmiş → ikon metnin ÜSTÜNDE ayrı satırda çiziliyor, düğme iki katlı ve asimetrik görünüyor. Tüm cihaz sınıflarında; dar ekranda meti… | a,b,c,d,e,f,g,h | btnOutline'a `flexDirection: 'row', gap: spacing.sm` ekle, iki inline `marginRight: 8`'i kaldır (btnPrimary 996-1004 zaten row+gap deseninde). |  | dogru |
| `ekranA-13` | Düşük | `screens/WelcomeScreen.tsx` | Kendi eşiği (width<768) ve kart minWidth rs(280)=364px: 768px tablet dikeyde kartlar tek tek tam genişlik (≈706px) olarak alt alta; 84px ikon + ortalanmış 2 satırlık metin devasa boş kartlarda yüzer. 1024px tablet yatayda 2 kart … | c,d | useWindowDimensions yerine `useResponsive().layout`: tablet için `cardWrapper: { flexBasis: '48%', maxWidth: rs(380), flexGrow: 0 }`, desktop/wide'da 3 kart için `flexBasis: '31%'`; yatay telefonda `… | S2 | dogru |
| `ekranA-14` | Düşük | `screens/WelcomeScreen.tsx` | paddingVertical spacing.sm (7-8px) + 11px metin → ~29px yükseklik; hasta güvenliğiyle ilişkili (seans sürerken teardown onayı açan) bir eylem için 44pt altında; ekranA-4 ile birleşince üst yarısı durum çubuğu altında. | a,b,c,j | `minHeight: rs(44), paddingHorizontal: spacing.lg` ekle veya `<Button variant="ghost" size="md" icon={LogOut} label="Çıkış">` (components/ui/Button). | S3 | dogru |
| `ekranA-16` | Düşük | `screens/DashboardScreen.tsx (+ NotificationCenter.tsx)` | Ekran AppShell ScrollView'i içinde İKİNCİ bir dikey ScrollView döndürüyor, içinde de compact NotificationCenter'ın maxHeight rs(120)'lik ÜÇÜNCÜ ScrollView'i var. Telefonda 120px'lik liste üzerinde başlayan dikey kaydırma iç liste… | a,b,c,d | DashboardScreen kökünü `<View style={styles.container}>` yap ve `paddingBottom: spacing.xxl`'i kaldır; NotificationCenter compact modda ScrollView yerine düz View + `maxVisible={4}` (Dashboard'da) ya… | S4 | kismen |
| `ekranA-18` | Düşük | `screens/SettingsScreen.tsx` | 'Eşleştirme kodu (örn: A3F9K2) veya cihaz kimliği' (46 kar.) ve '192.168.1.100 veya https://xxxx.trycloudflare.com' (50 kar.) yer tutucuları tek satırda kırpılır; 320-375px'te (≈200-230px alan) kullanıcı yalnız 'Eşleştirme kodu (… | a,b,d,i | Placeholder'ları kısalt: 'Kod veya cihaz kimliği', 'IP ya da tünel adresi'; örnekleri mevcut helperText'e taşı. |  | dogru |
| `ekranA-19` | Düşük | `screens/AuthScreen.tsx` | Kural satırları width '48%': 320px telefonda kart içi ≈238px → 114px hücre; 'En az 8 karakter' caption (rf 12→10-11px) + 14px nokta + gap ≈ 105px. Android yazı ölçeği 1.3'te metin 14px'e çıkınca hücreye sığmaz, 'karakter' ikinci … | a,i | `rule: { flexBasis: '48%', flexGrow: 1, minWidth: rs(130) }` ve ruleText'e `flexShrink: 1` — büyük yazıda kurallar otomatik tek sütuna iner, hizalama bozulmaz. | S6 | kismen |
| `ekranA-20` | Düşük | `screens/SettingsScreen.tsx` | Info satırında etiket ve değer yan yana; değer sağa hizalı, numberOfLines=2. 320-360px'te 'Adres' değeri (açık adres genelde 40-80 kar.) 2 satırda '…' ile kesilir, 'Klinik / Muayenehane' etiketi (flexShrink yok) değeri ~110px'e s… | a,b,i | `useResponsive().isCompact` iken infoRow'u `flexDirection: 'column', alignItems: 'flex-start'` yap, infoValue `textAlign: 'left'` ve numberOfLines'ı kaldır; geniş ekranda `infoLabel: { flexBasis: rs(… |  | dogru |
| `ekranA-5` | Düşük | `screens/AuthScreen.tsx` | Kök View inset kullanmıyor; ScrollView içeriği ortalı olduğundan giriş modunda sorun görünmez, fakat Kayıt Ol modunda 13 alanlık form ekrandan uzun olunca içerik üste yaslanır ve logo halkası (rs(84)) durum çubuğu/çentik altına g… | a,b,c,j | `const insets = useSafeAreaInsets();` → contentContainerStyle `[styles.scroll, { paddingTop: spacing.xxl + insets.top, paddingBottom: spacing.xxl + insets.bottom }]`. | S5 | dogru |
| `ekranA-6` | Düşük | `screens/AuthScreen.tsx` | Android'de KeyboardAvoidingView behavior=undefined; klavye yönetimi tamamen manifest adjustResize'a bırakılmış. Proje edge-to-edge (gradle.properties edgeToEdgeEnabled=true, targetSdk 35) — Android 15'te edge-to-edge pencerede ad… | a,b,d,i | Android'de de `behavior="padding"` (RN 0.85 KAV, Keyboard olayındaki yüksekliği kullanır; edge-to-edge ile çalışır) veya AppShell'in kök View'ına `useAnimatedKeyboard`/`Keyboard.addListener('keyboard… | S4 | kismen · Orta→Düşük — Android'de KAV behavior=undefined DOĞRU; ancak Expo'nun edge-to-edge katmanı adjustResize davranışını korur — 'ScrollView kısalmaz' iddiası cihazda d… |
| `ekranA-9` | Düşük | `screens/SettingsScreen.tsx` | Eşleştirme kodu Text'i flex:1 almıyor (hemen altındaki cihaz-kimliği satırında var). 'Bu cihazın eşleştirme kodu: A3F9K2 (uzaktan geçersiz)' 320-360px'te pairBox içine (≈210-230px) sığmayıp sarar ve Text kabın tüm genişliğini alı… | a,b,i | pairCodeText'e `flex: 1, flexShrink: 1` (alt satırdaki desenle aynı); Copy ikonunu `<View style={{ minWidth: rs(24), alignItems: 'flex-end' }}>` içine al. |  | kismen |

### Ekranlar: Kontrol, Sensörler, Simülatör (pf) — 0 yüksek / 10 orta / 4 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `ekranB-1` | Orta | `components/ui/ResponsiveGrid.tsx (+ ControlScreen.tsx 609-660, CoilParameterPanel.tsx 156-211, 372)` | ResponsiveGrid sütun sayısını PENCERE genişliğinden hesaplıyor, kartların içine yerleştiği gerçek konteyner genişliğinden değil. Tablet/masaüstü düzeninde AppShell rs(248)=322 px kenar çubuğu + 2×spacing.xl(31) içerik boşluğu düş… | d,e,f,g | ResponsiveGrid'e onLayout ile gerçek genişlik ölçümü (SensorMonitorScreen:111 chartArea deseni): `const [w,setW]=useState(0); const cols = w ? Math.max(1, Math.floor((w + spacing.sm*2) / (rs(minItemW… | S2 | dogru · Yüksek→Orta — 182 px bobin kartı kullanışsız derecede dar ama parametre girişleri erişilebilir; 'iş yapılamıyor' eşiği aşılmıyor. |
| `ekranB-10` | Orta | `components/domain/AiSpecApprovalModal.tsx` | Kart `maxHeight:'88%'` olan düz View (ScrollView değil); içinde başlık + açıklama + 4 meta hücresi (2 satıra sarar) + güven satırı + XAI satırı + `tableWrap maxHeight rs(200)` tablo + düğme satırı ≈ 420-470 px. Yatay telefonda 88… | c,a | Kart gövdesini (lead, summary, rel, xai, tablo) `<ScrollView style={{flexShrink:1}}>` içine al, actions'ı kartın altında sabit bırak; tableWrap'i ScrollView'e çevirmeyi bırak (tek kaydırıcı). `const … | S5 | dogru |
| `ekranB-2` | Orta | `screens/ControlScreen.tsx (+ GlobalEmergencyStop.tsx 35-37, LiveDataContext.tsx 73-94)` | Sayfa-içi 'TÜM BOBİNLERİ ACİL DURDUR' düğmesi Manuel sekmesinde 8 bobin kartının ALTINDA; telefonda kartlar ~300 px × 8 ≈ 2500-3000 px kaydırma derinliğinde. Bu normalde kayan GlobalEmergencyStop ile telafi ediliyor, ancak kayan … | a,b,c,e | Sayfa-içi E-stop'u tab bar'ın (ControlScreen:494) hemen üstüne, SessionProgressCard altına taşı (isActive iken kart zaten E-stop taşıdığından `!isActive` koşuluyla göster) — sayfa sonundakini kaldır.… |  | kismen |
| `ekranB-3` | Orta | `screens/SensorMonitorScreen.tsx (+ AppShell.tsx, GlobalEmergencyStop.tsx, SessionProgressCard.tsx)` | Yatay telefonda (yükseklik 360-430 px) AppShell üst bar (~85 px) + alt gezinme (~72 px) sabit; seans sürerken kayan ACİL DURDUR (52 px + rs(76)+insets offset) içerik alanının alt üçte birini örtüyor → görünür içerik ~150-200 px. … | c,j | SensorMonitor: `const { height } = useResponsive(); height={Math.max(rs(160), Math.min(rs(280), Math.round(height*0.45)))}`. AppShell'de `const landscapePhone = width > height && height < 500` koşulu… | S5 | kismen |
| `ekranB-4` | Orta | `screens/SensorMonitorScreen.tsx, ControlScreen.tsx, components/domain/AiProPanel.tsx, DemaSimulatorScreen.tsx, PatientGate.tsx` | Dokunma hedefleri 44 px'in çok altında: SensorMonitor coilBtn paddingVertical 6 (ölçeksiz) + 12 px metin ≈ 26 px yükseklik; axisChip/targetChip/organChip paddingVertical spacing.xs (3-5 px) + 11 px metin ≈ 22-26 px; AI Pro 'Vazge… | a,b,c,d,i | Ortak `Chip` primitifi (components/ui) — `minHeight: rs(40), paddingVertical: spacing.sm, hitSlop 4`; 5 yerdeki çip stilini ona bağla, satır gap'lerini spacing.sm yap. PatientGate X ve DemaSimulator … | S3 | dogru |
| `ekranB-5` | Orta | `components/visual/RealtimeChart.tsx` | Grafik iç kenar boşlukları sabit `PAD = {left:60, right:60, top:20, bottom:40}` (rs'siz). 320 px telefonda konteyner ≈ 320 − 2×20 (xl@0.85) − 2×10 (md) ≈ 260 px → çizim alanı 140 px. 8 bobin × 2000 noktalı seri 140 px'e sıkışınca… | a,b | PAD'i genişlikten türet: `const narrow = width < 400; const PAD = { top: 20, bottom: 40, left: narrow ? 44 : 60, right: showTemp ? (narrow ? 44 : 60) : 12 };` (iki dalda da). useResponsive().isCompac… | S7 | dogru |
| `ekranB-6` | Orta | `components/visual/RealtimeChart.tsx (+ SensorMonitorScreen.tsx 118)` | Canvas piksel boyutu `width={width} height={height}` (1×) ama CSS `width:100%; height:auto` → devicePixelRatio hesaba katılmıyor. Windows DPI %125-%200'de (WebView2 launcher) ve telefon tarayıcısında (DPR 2-3) 11 px eksen etiketl… | g,h,f,e | draw() başında: `const dpr = (typeof window!=='undefined' && window.devicePixelRatio) || 1; if (canvas.width !== width*dpr) { canvas.width = width*dpr; canvas.height = height*dpr; } ctx.setTransform(… | S7 | dogru |
| `ekranB-7` | Orta | `components/domain/AiProPanel.tsx` | 'Süre (dk) | Kalan | Yeniden Konumla' satırı 3 eşit flex:1 hücre; 320 px telefonda hücre ≈ 85 px, düğme iç genişliği ~70 px ve '🎯 Yeniden Konumla' `numberOfLines={1} adjustsFontSizeToFit` ile ~6-7 px'e küçülüyor → okunmuyor. 5'li… | a,b,i | `row`'a `flexWrap:'wrap'`, üç hücreye `flexBasis: rs(120), flexGrow: 1` (isCompact'ta düğme tam satıra düşer); calBtnText `numberOfLines={2}` + `minHeight rs(40)`. metric'e `flexBasis: '30%', minWidt… |  | dogru |
| `ekranB-8` | Orta | `components/domain/SessionProgressCard.tsx (+ CoilParameterPanel.tsx 356-365)` | timeRow 3 eşit flex:1 blok; timeValue `typography.title` (rf(24) → 375'te 24 px, 430'da ~26 px) + numberOfLines/adjustsFontSizeToFit YOK ve allowFontScaling açık. Android font-scale 1.3'te ~34 px; 1 saati aşan seansta '1:05:30' ≈… | a,b,i,d | timeValue'ya `numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6} maxFontSizeMultiplier={1.2}`; timeBlockCenter `flex: 0.6`; isCompact'ta `formatTime`'ı 'dk:sn' (h>0 → '65:30') yap. CoilPar… | S6 | dogru |
| `ekranB-9` | Orta | `components/domain/ObservationNotesModal.tsx (+ AppShell.tsx 385-394, CoilParameterPanel.tsx 236-242)` | Uygulamada KeyboardAvoidingView yalnız AuthScreen'de var; AppShell ScrollView ve ObservationNotesModal'da yok. iOS'ta (EAS build) alt-sayfa modalındaki çok satırlı 'Notlar' girişi ve hemen altındaki 'Atla / 💾 Kaydet' düğmeleri kl… | c,j,b | ObservationNotesModal: backdrop'u `KeyboardAvoidingView behavior={Platform.OS==='ios'?'padding':undefined} style={{flex:1, justifyContent:'flex-end'}}` yap; btnRow'u ScrollView DIŞINA (card'ın son ço… | S4 | kismen |
| `ekranB-11` | Düşük | `screens/DemaSimulatorScreen.tsx` | Web'de iframe yüksekliği `useState(Math.max(640, height*0.78))` ile YALNIZ ilk render'da hesaplanıyor; içerik-yüksekliği postMessage ölçümü sadece native WebView'e enjekte ediliyor (iframe için karşılığı yok). Launcher penceresi … | e,h,c,g | Web dalında: `const webHeight = Platform.OS==='web' ? Math.max(rs(480), Math.round(height*0.78)) : nativeHeight` (state'siz, `height`'a bağlı). Aynı origin olduğundan `onLoad={(e)=>{ try { const h = … | S7 | dogru |
| `ekranB-12` | Düşük | `screens/ControlScreen.tsx, components/domain/AiProPanel.tsx, screens/SensorMonitorScreen.tsx` | PC/tablette rs() SCALE hep 1.30 (kısa kenar ≥ 488) → `maxWidth: rs(1100)` = 1430 px, `rs(1200)` = 1560 px: hedeflenen 1100/1200 sınırı aşılıyor. 1430 px içerikte ParamField (flex:1, minWidth) 4 giriş × ~340 px ortalanmış metinle … | d,f,e | Konteyner maxWidth'lerini ölçeksiz sabit yaz (`maxWidth: 1100` / `1200`) — rs() telefon içi orantı içindir. ParamField'e `maxWidth: rs(240)`; camBox'a `height: undefined, aspectRatio: 16/9, width:'10… | S1 | dogru |
| `ekranB-13` | Düşük | `screens/SensorMonitorScreen.tsx, DemaSimulatorScreen.tsx` | AppShell zaten routeMeta başlığı+alt başlığı çiziyor; SensorMonitor ('📡 Sensör Monitörü' + alt metin) ve DemaSimulator (typography.title 24 px kart) ekran içinde ikinci bir başlık daha basıyor → yatay telefonda 200 px'lik görünür… | a,c | SensorMonitor: ScrollView→View, container'dan padding'i kaldır (AppShell zaten spacing.xl veriyor), başlığı silip yalnız CANLI/GECİKMELİ rozetini `alignSelf:'flex-end'` ince satır olarak bırak. DemaS… |  | dogru |
| `ekranB-15` | Düşük | `screens/ControlScreen.tsx` | CoilSelector düğmeleri rs(40) kare, aralarında gap spacing.xs (320'de 3 px, 375'te 4 px) ama her düğmeye 8 px hitSlop veriliyor → komşu düğmelerin dokunma alanları ~11-13 px üst üste biniyor; iki düğme arasına dokunmak hangi bobi… | a,b,i | `width/height: Math.max(rs(44), 44)`, gap spacing.sm, hitSlop'u `{2,2,2,2}` yap (kural: hitSlop ≤ gap/2). Seçili duruma `borderWidth: 2` + '✓' metin öneki ekle (yalnız-renk değil). | S3 | dogru |

### Ekranlar: Hastalar, Seans Geçmişi, Raporlar, AI Geçmişi (pf) — 2 yüksek / 5 orta / 6 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `ekranC-1` | Yüksek | `components/ui/ResponsiveGrid.tsx (+ AppShell.tsx, PatientScreen.tsx)` | ResponsiveGrid sütun sayısını PENCERE genişliğinden hesaplıyor, kenar çubuğunu (tablet+desktop'ta gösterilen rs(248)=322px) ve AppShell'in 2×spacing.xl padding'ini düşmüyor. iPad dikey 768px: 768/2=384≥340 → 2 sütun; gerçek içeri… | c,d,e,g | Öneri doğru; en küçük değişiklik: useResponsive'a `contentWidth = width - ((isTablet||isDesktop) ? rs(248) : 0) - 2*spacing.xl` ekleyip ResponsiveGrid.tsx:13'te `width` yerine bunu kullan (targetColu… | S2 | dogru |
| `ekranC-3` | Yüksek | `components/domain/SessionDetailModal.tsx` | TempChart SVG sabit viewBox 720×260 ile width='100%' + height rs(260) çiziliyor (preserveAspectRatio varsayılan 'meet'). Telefonda modal kart içi ≈270-300px → ölçek ≈0.38: eksen yazıları fontSize 11/10 → ≈4px (okunamaz), çizim al… | a,b,c,i | Öneri doğru: chartWrap'a onLayout ile genişliği al (KpiDashboard chartInner deseni), `width` sabitini ölçülen genişlikle, `height`i rs(240) ile değiştir ve viewBox'ı aynı boyutlarla kur; fontSize'lar… | S7 | dogru |
| `ekranC-2` | Orta | `screens/KpiDashboardScreen.tsx` | PieChart lejant metni chart-kit içinde x=width/2.5'ten başlar ve `absolute` ile 'sayı + mod adı' yazar. 320px telefonda kart içi genişlik ≈230px (AppShell 20+KPI 10+grid 7+kart 7 padding ×2) → lejant 150px'ten başlayıp 'Yara İyil… | a,b,d,e,g | hasLegend={false} + lejantı RN View ile grafiğin altına (flexWrap satırı, renk noktası + ad + sayı; chart-kit'in x=width/2.5 sabitinden kurtul); pie'ı center=[chartW/4 - ...] yerine paddingLeft'i `St… | S7 | dogru |
| `ekranC-4` | Orta | `screens/TreatmentHistoryScreen.tsx` | Sağ küme (StatusPill 'Kesintiye Uğradı' ≈135px + paylaş ikonu + 'PDF' + sil ikonu, gap dahil ≈258px) 320-360px telefonda kart içi ≈236-270px'e sığmaz; flexWrap ile sarılsa da kümenin min-içeriği (pill 135px) titleArea'yı ≈90px'e … | a,b,i | useResponsive().isCompact iken `row`'u flexWrap yap ve sağ kümeye `flexBasis:'100%'` + justifyContent:'flex-end' ver (aksiyonlar ikinci satıra iner, titleArea tam genişlik); ya da titleArea'ya minWid… |  | dogru · Yüksek→Orta — Hasta adı 8 karaktere kırpılıyor ve sil/paylaş hedefleri küçük; detay ekranı bilgiye erişimi koruyor. |
| `ekranC-5` | Orta | `screens/TreatmentHistoryScreen.tsx` | Not düzenleme tetikleyicisi 14px Edit3 ikonunu padding'siz TouchableOpacity içinde → 14×14px dokunma hedefi; 'Kaydet' / 'İptal' yalnız metin (≈17px yükseklik, minHeight yok, aralarında 8px). Telefonda ve tablet parmak kullanımınd… | a,b,c,d,i | Üç düğmeye de `hitSlop={{top:12,bottom:12,left:12,right:12}}` + minHeight rs(44) ve paddingHorizontal spacing.sm ver (en ucuz); ya da Kaydet/İptal için `<Button size="sm" variant="primary|secondary">… | S3 | dogru |
| `ekranC-6` | Orta | `screens/PatientScreen.tsx` | Başlık View'ı flexWrap ama içindeki düğme satırı (line 198) flexWrap DEĞİL ve Button etiketi numberOfLines=1, flexShrink yok. Veteriner profilinde 'Tümünü Sil' (secondary, ikon+metin, md padding ≈126px) + 'Yeni Hasta Kayıt' (≈166… | a,i | Satıra `flexWrap:'wrap'` ekle (en küçük değişiklik; ikinci düğme alt satıra sarılır). Ek olarak isCompact'ta 'Tümünü Sil'i ikon-only (label='' + minWidth rs(44), accessibilityLabel) yapıp kalan geniş… |  | kismen |
| `ekranC-9` | Orta | `screens/AiHistoryScreen.tsx` | headerRow: sayaç Text'i flexShrink/numberOfLines'sız, sağda iki metin düğmesi (ikon 16 + small yazı, minHeight yok → ≈18px yükseklik). 320px telefonda içerik ≈252px (çift padding, bkz. ekranC-12): '123 kayıt (filtreli)' ≈110px + … | a,i | count'a `flex:1, numberOfLines:1`; headerRow'a flexWrap:'wrap'; refreshBtn'e minHeight rs(44) + paddingHorizontal spacing.sm + hitSlop; 'Geçmişi Sil'i `<Button size="sm" variant="secondary">` ile ayr… |  | kismen |
| `ekranC-10` | Düşük | `screens/AiHistoryScreen.tsx` | detailRow: anahtar flexShrink:0, değer flex:1 sağa hizalı. 320px telefonda (kart içi ≈220px) 'Tahmini kalp atım aralığı' gibi uzun anahtar ≈160px alır → değere 40-60px kalır, çok basamaklı/uzun metin değerler 4-6 satıra sarılır (… | a,f | detailKey'e `flexShrink:1, maxWidth:'55%'` (tek satır değişiklik) ve isCompact'ta detailRow'u `flexDirection:'column', alignItems:'flex-start'` yapıp value'yu sola hizala; isDesktop'ta detailGrid'i `… |  | dogru |
| `ekranC-12` | Düşük | `screens/AiHistoryScreen.tsx, KpiDashboardScreen.tsx (+ AppShell.tsx)` | AppShell içerik alanı zaten padding spacing.xl (320px'te 20px) veriyor; AiHistory headerRow/segment/chipsRow/list ayrıca paddingHorizontal/marginHorizontal lg (14px), KPI container padding md (10px) ekliyor → 320px telefonda her … | a,b | AiHistory'de headerRow/segment/list'in yatay padding/margin'ini kaldır; yalnız chipsRow'a tam-kanat için `marginHorizontal:-spacing.xl, paddingHorizontal:spacing.xl` (ScrollView style + contentContai… |  | dogru |
| `ekranC-13` | Düşük | `screens/PatientScreen.tsx, AiHistoryScreen.tsx, KpiDashboardScreen.tsx, TreatmentHistoryScreen.tsx (+ AppShell.tsx)` | Her ekran AppShell'in dikey ScrollView'ı İÇİNDE kendi dikey ScrollView'ını açıyor; Patient/AiHistory container'daki flex:1 scroll içeriğinde etkisiz olduğundan iç ScrollView sınırsız büyüyüp dış kaydırır (çalışır) ama: (1) alt pa… | e,h,b | İç ScrollView'ları düz View ile değiştir (davranış aynı, gereksiz katman gider, alt padding'ler tekilleşir). Sticky filtre isteniyorsa AppShell'e `scroll={false}` prop'u ekleyip AiHistory/TreatmentHi… | S4 | kismen |
| `ekranC-15` | Düşük | `screens/KpiDashboardScreen.tsx` | 6 sütun flex:1 ile container maxWidth rs(1200)=1560px'e kadar gerilir: 1920-2560 PC'de her sütun ≈250px, değerler sola hizalı → '0.000' ile 'mT' başlığı arasında 200px boşluk, ondalıklar alt alta hizalanmaz (tabular-nums var ama … | f,e | Sayısal tableCell'lere `textAlign:'right'` (Bobin sütunu 'left'), tableHead'e aynı hiza; tableCard'a `maxWidth: rs(720), alignSelf:'flex-start'` ya da isDesktop'ta tabloyu chartsSection ResponsiveGri… |  | dogru |
| `ekranC-7` | Düşük | `screens/PatientScreen.tsx, TreatmentHistoryScreen.tsx, AiHistoryScreen.tsx` | Segment yarım-genişlik düğmeleri paddingVertical sm(8) + caption(12) → toplam ≈28-30px yükseklik (<44 dokunma hedefi). Etiket numberOfLines=1: 320px telefonda her yarı ≈126px; 'Benim Hastalarım (12)' Android yazı ölçeği ≥1.15'te … | a,i | Üç ekrandaki segmentBtn'e minHeight rs(40) ekle (tek satırlık değişiklik); PatientScreen'de Text'e maxFontSizeMultiplier={1.2} ve isCompact'ta etiketi 'Benim (12)' / 'Klinik (240)' yap. Ortak `ScopeS… | S3 | kismen |
| `ekranC-8` | Düşük | `screens/AiHistoryScreen.tsx (+ AppShell.tsx PanResponder)` | Çipler paddingVertical xs(4) + caption(12) → ≈22px yükseklik (<44 hedef). Ayrıca yatay çip ScrollView'ı, AppShell'in ana View'ındaki PanResponder'ın altında: |dx|>28 ve dx>1.8·dy olan her yatay hareketi sahipleniyor ve onPanRespo… | a,b,c | Çiplere paddingVertical spacing.sm + minHeight rs(36) ver (hedef ≈36-40px, çip için yeterli). PanResponder için değişiklik gerekmez; istenirse 10+ hastada çipleri isCompact'ta flexWrap ile 2 satıra s… | S3 | kismen — Dokunma hedefi kısmı doğru. PanResponder'ın yatay çip ScrollView'ini 'çalması' şüpheli: native ScrollView dokunuşta yanıtlayıcı olur, ebeveyn onMoveS… |

### AI Hub ve AI modülleri (pf) — 0 yüksek / 7 orta / 6 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `aihub-1` | Orta | `screens/AiHubScreen.tsx` | Isı haritasıyla AYNI SINIF sorun canlı-kamera overlay'inde duruyor: CameraView önizlemesi sabit rs(300) yükseklikli kutuyu 'cover' (kırparak) doldururken, üstüne absolute basılan işaretli kare `resizeMode:'contain'` ile letterbox… | a,b,c,d,e,f,h | imagePreviewContainer'dan sabit `height: rs(300)`'ü kaldırıp canlı modda kutuya kare oranını ver: `const { width, height } = useResponsive(); const portre = height > width;` → `{ aspectRatio: portre … | S7 | dogru |
| `aihub-2` | Orta | `components/domain/AiProPanel.tsx` | Aynı overlay sınıfı AI Pro'da da var: camBox sabit rs(200) yükseklik, CameraView %100/%100 (cover), camOverlay absolute + contain → organ lokalizasyon işaretleri canlı görüntüyle hizasız (yuksek riskli ekran: hekim onay öncesi or… | a,b,d,f,g | camBox: sabit height yerine `aspectRatio: IS_WEB ? 4/3 : (height > width ? 3/4 : 4/3)` + `maxHeight: Math.min(rs(420), Math.round(height*0.5))` (useResponsive); mobilde CameraView'a `ratio="4:3"`. fl… | S7 | dogru |
| `aihub-3` | Orta | `screens/AiHubScreen.tsx` | Çubuk dolgu yüksekliği ölçeklenmemiş sabit 26 px ile hesaplanıyor, ama ray yüksekliği rs(26). Tablet/büyük telefon/PC'de (SCALE=1.3) ray 34 px olur → duty tam (0.5) olsa bile çubuk %76 dolu görünür (veri yanlış okunur); 320 px te… | a,b,d,e,f,g,i | Dolguyu yüzdeyle ver: `{ height: `${Math.round(Math.min(Math.max(d,0),0.5)/0.5*100)}%` }` — soundBarFill (3715) zaten width-yüzde deseni kullanıyor, aynı yaklaşım. dBarLabel'ı `typography.small` (rf(… | S7 | dogru |
| `aihub-4` | Orta | `screens/AiHubScreen.tsx` | isCompact yalnız pencere genişliğine bakıyor (width<768). 768-1023 px'de AppShell kenar çubuğu rs(248)=322 px (SCALE 1.3) alıyor → içerik kolonu ~400 px kalıyor ama isCompact=false olduğundan 3 buton YAN YANA, her biri ~120 px: B… | c,d,g | En sağlam çözüm: useResponsive'e `contentWidth = width - ((isTablet||isDesktop) ? rs(248) : 0)` türet ve `isCompact = layout∈{compact,phone} || contentWidth < 560`; btnRow'lar (1493, 1891, 2112, 3549… | S2 | dogru |
| `aihub-5` | Orta | `screens/AiHubScreen.tsx` | Dokunma hedefleri 44 px'in çok altında: xaiToggle paddingVertical rs(4) + 11 px yazı ≈ 22 px yüksek (switch rolü); ckdCatBtn ≈ 22-24 px (10 satır üst üste, komşu satıra kayma kolay); symptomBtn ≈ 30 px; scChip ≈ 26 px; organChip … | a,b,c,d,i | Ortak: `minHeight: rs(44)` (AppShell.iconBtn 592 deseni) — xaiToggle, ckdCatBtn (+ ckdCatRow'a `minHeight: rs(44)`), hazirlikIptal, organChip. Çiplerde (symptomBtn/scChip/organChip) görsel boyutu kor… | S3 | dogru |
| `aihub-6` | Orta | `screens/AiHubScreen.tsx` | (1) AiHubScreen ve PetOwnerAiScreen kendi iç ScrollView'ını AppShell ScrollView'ının içine kuruyor ama `keyboardShouldPersistTaps` vermiyor (varsayılan 'never') → klavye açıkken 'CKD Analizini Başlat' / 'Teşhisi Başlat' düğmesine… | a,b,c,j | AiHubScreen kökünü ScrollView yerine düz `View` yap (AppShell zaten kaydırıyor ve keyboardShouldPersistTaps='handled' veriyor) — PetOwnerAiScreen (509) için de aynı; iç ScrollView kalacaksa `keyboard… | S4 | kismen |
| `aihub-9` | Orta | `screens/AiHubScreen.tsx` | Hücre width:'47%' → 320 px'de ~108 px; etiket typography.small (≈10 px) numberOfLines=1 olduğundan birimli etiketler kırpılır: 'Kan şekeri (mg/dL)' → 'Kan şekeri (m…', 'Kırmızı küre (mil/µL)' → 'Kırmızı küre…', 'Beyaz küre (/µL)'… | a,i,f | ckdNumLabel numberOfLines={2} (ckdNumCell yüksekliği değişir, sorun değil) veya birimi TextInput placeholder'ına taşı (`placeholder="mg/dL"`, etiket 'Kan şekeri'). Grid için `ResponsiveGrid minItemWi… |  | kismen |
| `aihub-10` | Düşük | `screens/AiHubScreen.tsx` | Önizleme kutusu sabit rs(300) yükseklik; SCALE açılışta kısa kenardan hesaplandığı için PC'de (kısa kenar ≥ 540 → clamp 1.3) her zaman 390 px. Pencere 700×540'a küçültülünce (genişlik <768 → alt bar + mobil düzen): görünür içerik… | c,e,g | `const stageHeight = Math.min(rs(300), Math.round(useResponsive().height * 0.45))` — useWindowDimensions canlı güncellendiği için pencere küçülünce/yatay dönünce kutu daralır; imagePreviewContainer, … | S1 | kismen |
| `aihub-11` | Düşük | `screens/AiHubScreen.tsx` | Satır: etiket sabit rs(96) + ray flex:1 + yüzde sabit rs(40). 320 px'de sonuç kutusu içi ≈ 200 px → ray 200−82−14−34 ≈ 70 px: %5 ile %15 farkı 7 px, çubuklar okunamaz. Etiket 82 px'e sığmayan '1. Anne çağrısı', '2. Çiftleşme' num… | a,i | CatSound/Histo satırlarında isCompact'ta (CatSoundModule 2727 ve HistopathModule 2931 zaten useResponsive okuyor) etiket + yüzdeyi üst satıra, rayı alta tam genişlik al — CatOrgan listesi (3596-3603)… | S7 | kismen |
| `aihub-13` | Düşük | `screens/AiHubScreen.tsx` | İki flex:1 düğme, padding spacing.xl (20-31 px) ve yazı typography.subtitle (14-19 px), numberOfLines yok. 320 px'de her düğmeye ~121 px, iç metne ~81 px kalır → 'Galeriden Seç' iki satıra kırılır, 'Kamerayı Aç' tek satır → düğme… | a,i | bigActionBtn/secondaryActionBtn'e `justifyContent:'center'` (tek satırlık düzeltme, içerik ortalanır) + `paddingHorizontal: spacing.md`; bigActionText/secondaryActionText'e `textAlign:'center'`. isCo… |  | kismen |
| `aihub-14` | Düşük | `screens/AiHubScreen.tsx` | Güvenlik mesajı taşıyan rozet yazıları rf(10) → 320 px telefonda 9 px, dBar etiketi 8 px; rs/rf küçültmesi + koyu yarı saydam zemin. 'BOBİN SÜRÜLMÜYOR' / 'GÜNCEL DEĞİL' uyarısı 9 px'te fark edilmeyebilir. Rozet absolute (top:12,r… | a,b,i | liveText/serverCamNote/metricLabel → `typography.small` (rf(11), alt sınır); uyarı durumunda (`!aiVisionFresh || preview`) `typography.caption`. liveIndicator'a `left:12, right:12` verip üst kenar bo… |  | dogru |
| `aihub-7` | Düşük | `screens/AiHubScreen.tsx` | Kart satırı: ikon rs(44) + label/desc + Eklenti rozeti + ▼ chevron. 320 px'de kullanılabilir genişlik ≈ 232 px; ikon 37 + üç gap 30 + rozet ~73 + chevron ~15 çıkınca metne ~77 px kalır → 'Yara Kapanma (Scratch)' → 'Yara Kapan…', … | a,b,i,f | isCompact'ta rozeti label satırından çıkarıp desc'in yanına (ikinci satır) taşı veya yalnız Lock ikonu göster; moduleLabel numberOfLines={2}. Desktop/wide'da moduleGrid'i `ResponsiveGrid minItemWidth… |  | dogru |
| `aihub-8` | Düşük | `screens/AiHubScreen.tsx` | Başlık + alt başlık `flex:1` solda, sağda dikey yığılmış 'Otonom Biofeedback' anahtarı (ikon 16 + yazı 11 px + padding) ve 'Kuyruklu · Pro+ anlık' etiketi. Sağ blok ~145 px sabit kalınca 320 px'de başlığa ~87 px düşer: 'Yüz Ağrıs… | a,b,i | VisionModule zaten `isCompact` okuyor (1076): başlık satırını `isCompact ? {flexDirection:'column', gap: spacing.sm} : {flexDirection:'row', ...}` yap; kompaktta sağ bloğu `flexDirection:'row', flexW… |  | dogru · Orta→Düşük — 320 px'te başlık 3-4 satıra kırılıyor; içerik kaybı yok. |

### UI ilkelleri, görsel bileşenler, modallar (pf) — 0 yüksek / 3 orta / 7 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `ilkel-11` | Orta | `components/domain/BackupPassphraseDialog.tsx` | Ortalanmış Card, ScrollView'sız ve maxHeight'sız. Telefon yatayda (360-430px) klavye açılınca kalan ~150-200px'e başlık+not+2 giriş+hata+düğmeler (~300px) sığmaz; 'Yedeği Oluştur'/'Geçiş Yap' düğmesi ekran dışında kalır ve kaydır… | c,i,j | Her iki diyalogda perde'yi `KeyboardAvoidingView(behavior: ios ? 'padding' : undefined)` ile sar (AuthScreen deseni), Card içeriğini `ScrollView keyboardShouldPersistTaps='handled'`e al, kart'a `maxH… | S4 | dogru |
| `ilkel-4` | Orta | `components/domain/ObservationNotesModal.tsx` | Chip paddingVertical spacing.xs (3-5px) + 11px yazı → yükseklik ~21-24px; 6 çip yan yana sarılıyor ve satır arası gap 4px. Dokunma hedefi 44px'in yarısı, yanlış çip seçilir ('Endişeli' yerine 'Uyudu') — tıbbi kayda giden veri. | a,b,d,i | `chip: { minHeight: 40, paddingVertical: spacing.sm, justifyContent: 'center' }`, `chips: { gap: spacing.sm }`, `chipText: typography.caption`; useResponsive().isCompact'ta `flexBasis: '48%'` ile 2 s… | S3 | dogru |
| `ilkel-7` | Orta | `theme/tokens.ts` | Dokunma hedefi minimumları rs() ile ölçekleniyor: 320px'te SCALE=0.853 → rs(44)=38, rs(46)=39, rs(38)=32; 360px'te rs(44)=42. Yani tam da dokunmanın en zor olduğu dar telefonlarda Button md 39px, sm 32px, PIN/parola girişleri ve … | a,b | tokens.ts'e `export const touch = { min: Math.max(44, rs(44)), sm: Math.max(40, rs(40)) }` ekle; Button size_md/size_lg → touch.min, size_sm → touch.sm; PIN/parola girişleri ve modal düğmelerinde `mi… | S3 | dogru · Düşük→Orta — Kök neden (S3): rs(44) 320 px'te 38 px — dokunma hedefi minimumlarının ölçekle KÜÇÜLMESİ sistemik; tek başına düşük görünse de 20+ bulgunun kaynağı. |
| `ilkel-12` | Düşük | `components/ui/NotificationCenter.tsx` | Liste maxHeight rs(240) sabit. (1) Tablet/PC'de 20 bildirim 240px'lik kutuda kaydırılır; 1080px ekranın %78'i boş. (2) Telefon yatayda: sheet marginTop insets.top+31 + konteyner padding + başlık (~30) + liste 240 ≈ 330px > 360px … | c,d,e,f | list maxHeight'ını `Math.min(useResponsive().height * 0.6, rs(560))` yap (PC'de daha fazla öğe görünür), yatay güvenliği için AppShell.notifSheet'e `maxHeight: height − insets.top − spacing.xl*2` + N… | S5 | kismen |
| `ilkel-14` | Düşük | `components/domain/AiSpecApprovalModal.tsx` | metaLabel rf(10) → 320px'te 9px, rel/xai/th rf(11) → 10px; SVG eksen yazıları 10-11 (viewBox küçülmesiyle daha da küçük). Hekim 'Lokalizasyon güveni: %42 — DÜŞÜK' uyarısını 10px'te okur; dar telefonda ve DPI'da çok küçük yazı. | a,b,g | En küçük taban typography.small (rf(11)); rel/relWarn → typography.caption + fontWeight 700; metaLabel → typography.small; tokens.rf'ye `Math.max(size >= 10 ? 11 : size, …)` alt sınırı ya da `rfMin(s… |  | dogru |
| `ilkel-15` | Düşük | `components/ui/Button.tsx` | Pressable'da hover/focus-visible stili yok (yalnız basış-scale). Fare kullanıcısı düğmenin tıklanabilir olduğunu imleç/renk değişimiyle göremez; klavye ile Tab'da odak halkası tarayıcı varsayılanına kalır (RNW bazı sürümlerde out… | e,f,h | style'ı fonksiyon yap: `({ hovered, focused, pressed }) => [ …, hovered && { opacity: 0.92 }, focused && { borderWidth: 2, borderColor: colors.cyan } ]`; Animated.createAnimatedComponent(Pressable) f… |  | kismen |
| `ilkel-16` | Düşük | `components/ui/Button.tsx` | Etiket numberOfLines=1 ve adjustsFontSizeToFit yok; font ölçeği 1.3'te (rf(14.5)×1.3 ≈ 19px) veya 320px'te iki düğme yan yana ('Analizi Başlat' / 'Yeniden Çek') etiketler '…' ile kırpılır — düğmenin ne yaptığı okunmaz. AiHub isCo… | a,i | Button.label'a `adjustsFontSizeToFit minimumFontScale={0.8} maxFontSizeMultiplier={1.2}`, content'e `flexShrink:1, minWidth:0`; AiHubScreen 539 ve 749 satır gruplarını da `isCompact && { flexDirectio… | S6 | kismen |
| `ilkel-18` | Düşük | `components/domain/SessionDetailModal.tsx` | Sütunlar sabit genişlik (colNum rs(78), colHw rs(70)); font ölçeği 1.3'te 'Başlangıç', 'Maks. °C', '1000 Hz', '12dk 30sn' hücre genişliğini aşıp 2 satıra sarar → satırlar farklı yükseklikte, hizalama bozulur. Yatay ScrollView say… | i,a | th/td Text'lere `numberOfLines={1} maxFontSizeMultiplier={1.2}`; sütunları `minWidth` yap ve `tableRow alignItems: 'stretch'`; isteğe bağlı: isCompact'ta colNum rs(78)→rs(68) ve başlıkları kısalt ('B… | S6 | dogru |
| `ilkel-3` | Düşük | `components/domain/AiSpecApprovalModal.tsx` | Kapat düğmesi padding'siz/hitSlop'suz TouchableOpacity; dokunma hedefi ikon boyutu kadar (rs(20) → 17-26px). Dokunmatikte ıskalanır; hasta güvenliği açısından kritik bir modalda 'erteleme' yolu zor erişilir. | a,b,c,d | `style={{ minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' }} hitSlop={8}` (ham 44 — rs ile küçültme, bkz. ilkel-7). | S3 | dogru · Orta→Düşük — Kapat (X) küçük ama aynı modalda tam boy 'Reddet' düğmesi var; erteleme yolu kapalı değil. |
| `ilkel-5` | Düşük | `components/ui/NotificationCenter.tsx` | Eylem düğmeleri padding spacing.xs (3-5px) + typography.small (9-11px) → ~19-22px yüksek, ~60px geniş; yan yana 8px boşlukla. 'Temizle' geri alınamaz bir eylem ve 'Okundu işaretle'nin hemen yanında — dokunmatikte hedef küçük ve k… | a,b,d | `actionBtn: { minHeight: 40, paddingHorizontal: spacing.md, justifyContent: 'center' }`, `headerActions gap: spacing.md`; 'Temizle'yi `<Button variant="ghost" size="sm">` ile çiz (Button.size_sm minH… | S3 | dogru · Orta→Düşük — 'Temizle' onay diyaloğuyla korunuyor; hedef küçük ama yıkıcı sonuç yok. |

### Bantlar ve kapılar (pf; kapsam turu) — 0 yüksek / 3 orta / 5 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `kapsam-1` | Orta | `components/domain/MobileUpdateGate.tsx` | Kapı kökü kaydırılamayan, dikeyde ortalanmış bir View (`root: flex:1, alignItems/justifyContent:center`); ScrollView yok. app.json `orientation: default` olduğundan telefon YATAY tutulunca (c, ~360-430 px yükseklik) içerik yüksek… | c,i | Kökü `<ScrollView style={{flex:1, backgroundColor: colors.bg}} contentContainerStyle={{flexGrow:1, alignItems:'center', justifyContent:'center', padding: spacing.xl}} keyboardShouldPersistTaps='handl… | S5 | dogru |
| `kapsam-2` | Orta | `components/domain/MobileUpdateBanner.tsx` | Bandı kapatan X düğmesi yalnız rs(15) piksellik ikon; TouchableOpacity'ye hitSlop, padding, minWidth/minHeight verilmemiş → dokunma hedefi ~15×15 px (öneri ≥44). Dar/normal telefonda (a, b) ve tablette (d) parmakla tutturmak zor;… | a,b,d,i | `style={{ minWidth: rs(44), minHeight: rs(44), alignItems:'center', justifyContent:'center' }}` + `hitSlop={{top:10,bottom:10,left:6,right:10}}` ekle (AppShell.tsx 587 `iconBtn` stili ile aynı kalıp … | S3 | dogru |
| `kapsam-4` | Orta | `components/UpgradeModal.tsx` | Kart kaydırılamıyor (ScrollView yok) ve dikeyde ortalanıyor. İçerik yüksekliği: padding 2×32 + ikon halkası 64 + başlık 24 px (2-3 satır) + açıklama ('research' metni ~150 karakter → 272-64=208 px genişlikte ≈ 6 satır × 22) + pla… | c,i,h | Backdrop'u `<Pressable style={styles.backdrop} onPress={onClose}>` içinde `<ScrollView contentContainerStyle={{flexGrow:1, justifyContent:'center', alignItems:'center'}}>` ile sar; kart `Pressable on… | S5 | dogru |
| `kapsam-3` | Düşük | `components/domain/SurumFarkiBanner.tsx` | Kapatma X'i rs(16) ikon + hitSlop 8 → toplam dokunma alanı ≈ 32×32 px (<44). Dar telefonda (a) ve büyük yazı ölçeğinde (i) metin bloğu büyürken hedef sabit kalır; kaçırılan dokunuş bandın altındaki içeriğe gider. Tek etkisi bandı… | a,b,i | hitSlop'u `{top:14,bottom:14,left:14,right:14}` yap veya AppShell `iconBtn` (minWidth/minHeight rs(44)) stilini uygula; `accessibilityRole="button"` ekle. | S3 | dogru |
| `kapsam-5` | Düşük | `components/UpgradeModal.tsx` | X düğmesi absolute konumlu, ikon 20 px + padding rs(6) → dokunma hedefi ≈ 32×32 px (<44). Kart köşesinde, 32 px'lik kart padding'inin içinde; dar telefonda (a, b) parmakla ıskalanır. Boyutlar ham sayı (20, 30, borderRadius 12) → … | a,b | `close` stiline `minWidth: rs(44), minHeight: rs(44), alignItems:'center', justifyContent:'center'` ver ve `top/right: spacing.sm` yap; `hitSlop={{top:8,bottom:8,left:8,right:8}}` ekle; ikon boyutlar… | S3 | dogru |
| `kapsam-6` | Düşük | `components/domain/RecoveryCodeBanner.tsx` | Bantlar AppShell içerik ScrollView'unun DIŞINDA, yalnız `margin: spacing.sm` ile tam genişliğe yayılıyor; AppShell'in `content` stili de maxWidth vermiyor. PC geniş (f, 1920-2560) ve LAN tarayıcı (h) tam ekranda RecoveryCodeBanne… | f,h,e | AppShell.tsx'te bantları ve `content`'i ortak sarmalayıcıya al: `<View style={{ width:'100%', maxWidth: responsive.isDesktop ? rs(1100) : undefined, alignSelf:'center' }}>` (`responsive` zaten 88'de … |  | dogru |
| `kapsam-7` | Düşük | `components/domain/MobileUpdateBanner.tsx` | Bandın eylem talimatını taşıyan alt metin `rf(11)`; tokens.ts SCALE 320 px telefonda 0.85 → rf(11)=10 px, düğme metni rf(12)=11 px. Kullanıcı Android yazı ölçeğini 0.85'e çekmişse (i) ≈ 8.5 px etkin boyut. Dosyadaki M12 notu bu m… | a,i | `alt` için `fontSize: Math.max(rf(11), 12)` veya `typography.caption`; `useResponsive().isCompact && width < 360` iken bandı `flexDirection:'column', alignItems:'stretch'` yap ve 'Güncelle'+X'i alt s… | S6 | dogru |
| `kapsam-8` | Düşük | `components/domain/RecoveryCodeBanner.tsx` | Satır düzeni (ikon | flex:1 metin | 'Kaydettim' düğmesi ≈ 90 px) dar telefonda (a, 320 px) metne ≈ 165 px bırakır; 2 cümle + dosya yolu (`C:\ProgramData\...\KURTARMA-KODU.txt`, kesme yok, `\n` ile ayrı satır) 11 px yazıyla ≈ 10-1… | a,b,i | `useResponsive().isCompact` iken bandı `flexDirection:'column', alignItems:'stretch'` yap; 'Kaydettim'i altta tam genişlik. Dosya yolunu ayrı `<Text selectable numberOfLines={2} ellipsizeMode="middle… |  | kismen |

### Başlatıcı istemci arayüzü (launcher) — 2 yüksek / 4 orta / 6 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `launcher-1` | Yüksek | `launcher/ui/index.html` | main hem overflow:auto hem justify-content:center (sütun flex) ve .stage'de margin:auto yok. İçerik main'den uzun olunca flexbox içeriği ortalar: taşan kısım ÜSTE ve alta eşit dağılır; üstteki kısım kaydırma başlangıcının önünde … | e,g | Her ortamda çalışan çözüm: `main { justify-content: flex-start; }` + `.stage { margin: auto 0; }` (auto margin sığdığında ortalar, taştığında 0'a düşer ve içerik en üstten başlayıp kaydırılabilir). `… | L | dogru · Orta→Yüksek — CDP ölçümüyle doğrulandı: varsayılan 880×600 pencerede bile profil-seçim başlığı üst çubuğun altında ve kaydırmayla ulaşılamıyor; 1366×768 @%150'de d… |
| `launcher-2` | Yüksek | `launcher/tauri.conf.json` | Pencere 880x600 mantıksal, minHeight 540 — Windows DPI ölçeğinde mantıksal çalışma alanı bunun altına iniyor: 1366x768 @%150 → 911x512, görev çubuğu düşünce ≈472px; 1280x720 @%125 → 1024x576-32 ≈ 544 (600 için yetmez); 1920x1080 … | g,e | main.rs normal-kip `.setup`'ında: `let m = w.current_monitor()?; let wa = m.work_area(); let sf = m.scale_factor(); let h = ((wa.size.height as f64 / sf) - 40.0).min(600.0); w.set_min_size(Some(Logic… | L | dogru |
| `launcher-3` | Orta | `launcher/ui/index.html` | ≤1040px genişlikte .hbtn span display:none oluyor ama düğmelerde title/aria-label yok; 'Web Sitesi', 'Kılavuz', 'Hakkında' ve 'Çıkış' yalnız 15px çizgi ikon olarak kalıyor. Launcher 880 genişlikte açıldığından (ve 1366@%150'de ma… | e,g | applyLang() içinde (1479+) etiketleri yazdığın satırların yanına `$("btn-web").title = $("btn-web").ariaLabel = x.web;` (guide/about/logout için aynı) ekle — dil değişince güncellenir, ikon-only kipt… | L | dogru |
| `launcher-4` | Orta | `launcher/ui/index.html` | Kartlar tabindex/role/keydown olmayan div'ler; yalnız onclick. Klavyeyle (Tab) hiçbir karta odaklanılamaz, Enter/Space ile seçilemez; 'Kur ve Başlat' seçim olmadan disabled kaldığından yalnız klavye kullanan (ya da fare sürücüsü … | e,g | renderCards'ta `document.createElement("button")` + `type="button"` + `aria-pressed=String(on)` kullan; `button { font:inherit; border:0; background:none; color:inherit }` (45) zaten sıfırlıyor, `.ca… | L | dogru |
| `launcher-5` | Orta | `launcher/ui/index.html` | Modal açılınca odak modala taşınmıyor, Escape kapatmıyor, odak tuzağı yok. Klavye kullanıcısı 'Onar' onayında Enter'a basınca hiçbir şey olmaz; Tab, arkadaki (overlay altındaki) header/sahne düğmelerinde dolaşır — 'Kaldır' onayı … | e,g | Ortak `openModal(overlayId, focusId)`: overlay.hidden=false; document.querySelector('main, header, footer').forEach(el => el.inert = true) (WebView2/Chromium 102+ inert destekler — Tab tuzağını bedav… | L | dogru |
| `launcher-6` | Orta | `launcher/ui/index.html` | uninBody ve bgCancelConfirm '\n\n' ve '• ' madde işaretleriyle yazılmış ama <p id=confirm-body>'ye textContent ile konuyor ve .modal p'de white-space:pre-wrap yok → tüm satır sonları boşluğa çöker: 'İndirilen uygulama ve AI model… | e,g | `#confirm-body { white-space: pre-wrap; }` tek satır yeterli (bgCancelConfirm için değişiklik gerekmez). İhtiyat olarak `.modal { max-height: calc(100vh - 48px); overflow-y: auto; }` eklenebilir ama … | L | kismen |
| `launcher-10` | Düşük | `launcher/ui/index.html` | Arayüz pencere boyutuna göre ölçeklenmez: 2560x1440 ya da 4K @%100'de (kullanıcı pencereyi maximize ederse) sahne 560px'lik ada olarak ortada kalır, header sol/sağ uçları 2500px ayrılır; yazılar 10-13.5px'te fiziksel olarak ~2mm … | f,g | Yalnız alt sınırı düzelt: .reqtag 11px, .errdetail 12px, footer/.brand p 12px. Geniş ekran için `@media (min-width: 1600px) { .stage { max-width: 680px } body { font-size: 15px } }` yeterli; global r… | L | kismen |
| `launcher-11` | Düşük | `launcher/ui/index.html` | Dokunmatik Windows 2-in-1/tablet (Surface, %200 DPI) ya da dokunmatik klinik PC'de: .seg TR/EN düğmeleri ~28px yüksek, .link 13px + 6px padding ≈ 32px, .hbtn ≈ 33px, ikon-only hbtn 41x33 → 44px hedefin altında; 'Onar' ile 'Uygula… | e,g | `@media (pointer: coarse) { .seg button, .hbtn, .link, .mbtn { min-height: 44px; padding-inline: 14px } .subactions { gap: 12px 28px } }`; 'Uygulamayı kaldır'ı `margin-left:auto` ya da ayrı satırla d… | L | dogru |
| `launcher-12` | Düşük | `launcher/ui/index.html` | Tek 'kompakt' kırılma noktası 680px, pencere ise 700'ün altına inemez → kural asla tetiklenmez; .title 24px küçültmesi ölü. 700-1040 aralığında (varsayılan 880 pencere ve 1366@%150 maximize dahil) düğme etiketlerini gizlemek dışı… | e,g | 680 kuralını kaldırıp (.brand p ve .hbtn span zaten 1180/1040'ta gizli) yerine `@media (max-height: 620px)` bloğunu ekle: .title 22px, .lead margin-bottom 10px, .check 64px, .pct 36px/min-height 40px… | L | dogru |
| `launcher-7` | Düşük | `launcher/ui/index.html` | 700px genişlikte (ya da 1366@%150'de ~911px'e kadar küçültülmüş pencerede) header-actions flex:0 0 auto/nowrap ve tahmini toplam ≈603px (seg 76 + 3 ikon düğme 123 + authbox 12+120+4+35+4+2=177 + 'Çevrimdışı' rozeti ~103 + 'v1.9.4… | e,g | `.brand { min-width: 54px }` (logo 42 + boşluk) ile logoyu koru; `@media (max-width: 800px) { #offline-badge span:last-child { display:none } #auth-email { max-width: 90px } }` ile aksiyon grubunu ≈5… | L | kismen |
| `launcher-8` | Düşük | `launcher/ui/index.html` | hataCumlesi() eşleşmeyen hatalarda ham mesaj doğrudan #error'a yazılır; #error white-space:pre-wrap ama overflow-wrap/word-break yok (yalnız .errdetail'de var). Boşluksuz uzun belirteç içeren mesajlar — 'https://github.com/…/rele… | e,g | Ucuz sigorta: `#error { overflow-wrap: anywhere; overflow-x: hidden; }`. fail() else dalında da ham mesajı .errdetail sınıfında ikinci bir div'e koymak yerine tek div bırak ama `overflow-wrap` ile ye… | L | kismen |
| `launcher-9` | Düşük | `launcher/src/main.rs + launcher/ui/index.html` | Pencere config'den 880x600 olarak açılır; Rust 250ms sonra 640x400'e küçültüp ortalar; html.gunc sınıfı ise JS boot'ta invoke('guncelleme_modu') dönünce eklenir. Aradaki sürede tam boy pencerede header (TR/EN, Web Sitesi, Kılavuz… | e,g | tauri.conf.json windows[0]'a `"visible": false`; gunc kipinde set_size/center bittikten sonra `w2.show()`, normal kipte setup sonunda `w.show()` (launcher-2'deki boyut ayarıyla aynı yerde). JS tarafı… | L | dogru |

### Tanıtım ve indirme sitesi (pemf-vet-web) — 0 yüksek / 6 orta / 10 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `site-1` | Orta | `site/components/Header.tsx` | Masaüstü nav md (768px) kırılımında açılıyor ama içerik ~800px istiyor: logo+marka (~114px) + 4 NavLink (~348px) + 'Giriş yap'/'Hesabım' btn-ghost (~107px) + 'PEMF Vet'i İndir' btn-primary (~175px) + gap'ler + 48px oluk ≈ 800px >… | d,e,g | Header.tsx 21 ve 37'de `md:flex` → `lg:flex`, 46'da `md:hidden` → `lg:hidden`, 55'te `md:hidden` → `lg:hidden`; ek olarak CTA ve 'Giriş yap' düğmelerine `whitespace-nowrap` ver. 768-1023 arasında tab… | W | dogru |
| `site-11` | Orta | `site/pages/Download.tsx` | Dokunma hedefleri 44px altında: (1) Download 'Çıkınca haber ver', '.AppImage (tüm dağıtımlar)', '.rpm (Fedora / RHEL)' `text-xs` düz metin düğmeler ≈ 16px yükseklik, `mt-1/mt-2` ile alt alta → yanlış paketi indirme riski; (2) Aut… | a,b,c,d | Footer.tsx 34/40 Link'lere `py-1.5 -my-0.5 inline-block` (hedef ≥32px, adım 36); AuthModal 331 ve Download 76/90/100'e `inline-flex min-h-11 items-center px-2`; Pricing 82-84 pill'lere `py-2.5`; Head… | W | kismen |
| `site-13` | Orta | `site/context/AuthModal.tsx` | Diyalog `max-h-[90vh]`; `vh` iOS Safari'de büyük viewport'u (araç çubuğu gizli) baz alır. Araç çubuğu görünürken ve klavye açıkken (iOS klavye layout viewport'u küçültmez) 90vh'lik kutunun alt bölümü — 'Giriş yap/Hesap oluştur' g… | a,b,j | AuthModal.tsx 215: overlay'e `overflow-y-auto` + `place-items-start sm:place-items-center`; 224: `max-h-[90vh]` → `max-h-[calc(100svh-2rem)] sm:max-h-[calc(100dvh-2rem)]` ve `p-5 sm:p-7`. Gönder düğm… | W | dogru |
| `site-3` | Orta | `site/index.css` | Tüm form girişleri 14px (`font-size: 0.875rem` / `text-sm`). iOS Safari, font-size <16px olan input'a odaklanınca sayfayı otomatik yakınlaştırır; blur sonrası zoom kalır, sayfa yatay kaydırılabilir hale gelir ve modal `fixed inse… | a,b,c | index.css @layer base'e `@media (pointer: coarse) { input, select, textarea, .input { font-size: max(1rem, 1em); } }` ekle (tek nokta; `.input` ve FIELD'i ayrıca değiştirmeye gerek kalmaz). maximum-s… | W | dogru |
| `site-5` | Orta | `site/pages/Pricing.tsx` | Tablo `min-w-[560px]`; 320-430px telefonda görünür alan 280-390px → satır etiketi + en fazla 1-2 plan sütunu görünüyor, kalan 2-3 plan sağa gizli. İlk sütun sabitlenmediği için sağa kaydırınca 'Aylık jeton hakkı', 'Destek yanıt s… | a,b,g | Pricing.tsx 163 ve 174: ilk th/td'ye `sticky left-0 z-10 bg-bg-soft` (section zemini bg-bg-soft/50 olduğundan opak bg-bg-soft kullan) + `min-w-[140px]`; 159'daki div altına `<p className="mt-2 text-c… | W | dogru |
| `site-8` | Orta | `site/components/PackageBuilder.tsx` | md (768px) kırılımında 3 sütun: kart genişliği ≈ 227px, iç alan ≈ 179px. 'Veteriner Hekim' kartında (config.ts 299 `recommended: true`) `absolute right-4 top-4` konumlu 'Önerilen' rozeti (~60px) ile aynı satırdaki onay kutusu (24… | d,g | PackageBuilder.tsx 41-55: rozeti absolute'tan çıkar — başlık satırını `flex items-center gap-3` yerine `flex items-center gap-3 pr-0` + başlık span'ına `min-w-0 flex-1` ver ve rozeti aynı satırın son… | W | dogru |
| `site-10` | Düşük | `site/components/AccountButton.tsx` | Site TEK koyu tema (body bg oklch 13%, index.css 44-47) ama durum metinleri Tailwind `dark:` varyantına bağlı; Tailwind v4'te `@custom-variant dark` tanımlanmadığından `dark:` = işletim sistemi `prefers-color-scheme: dark`. OS'u … | a,b,c,d,e,f,h | index.css'e `@custom-variant dark (&:where(.dark, .dark *));` + index.html 2'ye `<html lang="tr" class="dark">` ekle (tek değişiklikle 12 yerin tümü OS'tan kopar). Ya da AccountButton 130/149 ve Auth… | W | kismen |
| `site-12` | Düşük | `site/components/LauncherMock.tsx` | `text-[10px]` ve `text-[11px]` ile gerçek içerik yazılıyor: maketin 'Kurulumu onar / Uygulamayı kaldır / Profilleri değiştir' satırı ve alt bilgi 10-11px; Download'da Android rol notu ve sürüm notu (`DOWNLOAD_HOST.androidRolNotu`… | a,b,i | Download.tsx 121-122 ve AccountButton.tsx 106: `text-[11px]` → `text-xs leading-relaxed`; LauncherMock 76/99: `text-white/45`/`/40` → `text-white/60`, 110 `text-white/30` → `/50`. PackageBuilder 42 r… | W | dogru |
| `site-14` | Düşük | `site/pages/Home.tsx` | Kapsayıcı `max-w-6xl` (1152px) ve başlık `lg:text-[3.4rem]` sabit; 1920px'te içerik %60, 2560px'te %45 genişlikte kalıyor, `.bg-hero` ızgara+parıltı tam genişlikte devam ettiğinden hero iki yanda geniş boş ızgara alanı bırakıyor;… | f | Home.tsx 16 ve diğer `max-w-6xl` kapsayıcılara `2xl:max-w-7xl`; 26'ya `2xl:text-6xl`, 29'a `2xl:text-xl`; index.css 175 `60% 55%` → `min(60%, 900px) 55%`. Header/Footer max-w'yi de aynı token'a bağla… | W | dogru |
| `site-15` | Düşük | `site/components/AccountButton.tsx` | Menü `absolute right-0 w-72` (288px); mobil drawer'da sarmalayıcı genişliği 320-40-24 = 256px → menü sarmalayıcının 32px solundan başlıyor, 320px ekranda tam sol kenara yapışık (0 marj) çıkıyor; 320 altındaki mantıksal genişlikle… | a,c,g | AccountButton.tsx 91: `w-72` → `w-72 max-w-[calc(100vw-2.5rem)]`; drawer için `inline?: boolean` prop'u ekleyip Header 72'den `inline` geçir → menü `static mt-2 w-full` (akışa alınır, CTA'yı örtmez, … | W | dogru |
| `site-16` | Düşük | `site/components/Footer.tsx` | `grid-cols-2 gap-x-10` 320px'te sütun başına (280-40)/2 = 120px bırakıyor; 'İptal, İade ve Cayma Hakkı', 'Mesafeli Satış Sözleşmesi', 'KVKK Aydınlatma Metni' 14px'te 2-3 satıra kırılıyor, 'Fiyatlandırma' sol sütunda tek başına ge… | a,g | Footer.tsx 30: `grid grid-cols-2 gap-x-10` → `grid grid-cols-1 gap-y-6 min-[400px]:grid-cols-2 min-[400px]:gap-x-6 sm:gap-x-10`; 34/40 Link'lere `py-1` (site-11 ile aynı düzeltme). | W | dogru |
| `site-2` | Düşük | `site/components/Header.tsx` | Mobil menü `sticky top-0` header'ın İÇİNDE, kendi scroll kabı yok. Açıkken toplam yükseklik ≈ 64 (bar) + 32 (py-4) + 4×40 (linkler) + 12 (gap) + ~42 (Giriş yap) + ~44 (İndir CTA) + margin'ler ≈ 370-380px. Telefon yatayda (viewpor… | c,e | Header.tsx 55'teki sarmalayıcıya `max-h-[calc(100dvh-4rem)] overflow-y-auto` ekle (tek satır, sticky yapı değişmez). AccountButton menüsü için site-15 önerisiyle birlikte uygula. | W | kismen |
| `site-4` | Düşük | `site/App.tsx` | `html { scroll-behavior: smooth }` koşulsuz ve ScrollToTop `window.scrollTo(0,0)` çağırıyor (CSS scroll-behavior'a uyar). Footer'daki bir bağlantıya sayfanın en altından tıklayınca YENİ sayfa render edilir ve viewport eski kaydır… | a,b,c,d,e,f,h | App.tsx 23: `window.scrollTo({ top: 0, left: 0, behavior: 'instant' })`. index.css @layer base'e `@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto } *, *::before, *::after { tra… | W | dogru |
| `site-6` | Düşük | `site/pages/Pricing.tsx` | lg (1024px) kırılımında 4 sütun: kart genişliği (1024-48-72)/4 ≈ 226px, p-7 sonrası iç alan ≈ 170px; 1152px'te ≈ 202px. Büyük fiyat satırı `text-4xl font-extrabold` (36px): FREE_MODE'da 'Şu an ücretsiz' (~280px) ve 'Kullandıkça Ö… | d,e,g | Pricing.tsx 121: `text-3xl xl:text-4xl leading-tight min-h-[2.4em]` (2 satırlık sabit yükseklik → düğmeler hizalanır); kartı `p-6 xl:p-7`. Alternatif: 108'de `lg:grid-cols-4` → `xl:grid-cols-4` ile 1… | W | dogru |
| `site-7` | Düşük | `site/pages/Pricing.tsx` | sm (640px) kırılımında yatay düzen açılıyor ve düğme grubu `shrink-0` + iki düğme yan yana (~320px). 640-~900px'te metin bloğuna 640-48-80(p-10)-24-320 ≈ 170px kalıyor: 'Zincir klinik veya kurum musunuz?' başlığı 4-5 satıra, açık… | c,d,g | Pricing.tsx 231: `sm:flex-row sm:justify-between sm:text-left` → `lg:flex-row lg:justify-between lg:text-left` (p-10 sm'de kalabilir); 239: `sm:flex-row` düğme grubunda kalsın (yan yana düğmeler metn… | W | dogru · Orta→Düşük — 640-900 px'te başlık 4-5 satıra kırılıyor — okunabilir, yalnız orantısız. |
| `site-9` | Düşük | `site/pages/Download.tsx` | max-w-5xl (1024px) kapsayıcıda lg'de 4 sütun: kart iç genişliği ≈ 229-56 = 173px. Birincil düğme 'Giriş yap ve indir' (ikon 16 + gap 8 + metin ~120 + padding 43 ≈ 187px) ve 'Windows için indir' düğmeleri iki satıra kırılıyor; alt… | d,e,g | Download.tsx 57: düğmeye `text-sm whitespace-nowrap` (Header ile aynı boyut → ~180px, 185'e sığar) ve kartı `p-5 xl:p-7`; 162'de `lg:grid-cols-4` → `xl:grid-cols-4` (lg'de 2×2) ile birlikte kullanınc… | W | kismen |

### Ampirik ölçüm (gerçek tarayıcı, 11 görünüm alanı) — 1 yüksek / 1 orta / 1 düşük

| Kimlik | Şiddet | Yer | Sorun | Cihaz | Öneri | Kök | 2. doğrulama |
|---|---|---|---|---|---|---|---|
| `ampirik-1` | Yüksek | `site/components/LauncherMock.tsx (kök neden) + site/pages/Home.tsx:16,51 ve Features.tsx:63 (yerleşim)` | LauncherMock'un üst şeridindeki `truncate` (white-space:nowrap) alt başlık 'Veteriner PEMF seans + yapay zekâ teşhis platformu' (229px) + logo 28 + sürüm çipi 61 + boşluklar, mock'un min-content genişliğini 371px'e çıkarıyor; moc… | a,b | Tek satırlık kesin çözüm: Home.tsx:51 ve Features.tsx:63 sarmalayıcısına `min-w-0` (`<div className="min-w-0 lg:pl-6">`). Grid öğesinin min-width'i 0 olunca track container genişliğine iner; Launcher… | W | dogru |
| `ampirik-4` | Orta | `screens/AuthScreen.tsx` | 'Şifremi unuttum?' ve 'Hesabın yok mu? Kayıt ol' bağlantıları yalnız metin yüksekliğinde dokunma hedefi: 320px'te 84×12px, 390px'te 92×14px, masaüstünde 109×16px (44px hedefin üçte biri). Sekmeler 'Giriş Yap / Kayıt Ol' 320'de 30… | a,b,i | Web+native ortak çözüm (RNW 0.21'de hitSlop garantisi yok, padding ikisinde de çalışır): :491 `forgotRow: { alignSelf:'flex-end', paddingVertical: spacing.sm, paddingHorizontal: spacing.sm, marginTop… | S3 | dogru |
| `ampirik-5` | Düşük | `screens/AuthScreen.tsx` | 320px (rs ölçeği 0.85) ile 12 giriş alanının yüksekliği 36px'e düşüyor (390'da 41px); Android'de 44-48px önerilen dokunma yüksekliğinin altında ve font-scale 1.3 ile metin alan içinde sıkışacak. Ayrıca uzun placeholder 'Ünvan (ör… | a,i | AuthScreen.tsx:494 `field`'a `minHeight: 44` ekleyin (rs'den bağımsız). :227 placeholder'ı 'Ünvan — opsiyonel' yapın (ipucunu :502 `sectionLabel` benzeri küçük bir yardımcı metinle verin). Font-scale… | S3 | kismen |

## 8. İkinci doğrulama (Claude — bulgular tek tek kaynak kodda)

İkinci doğrulamada (Claude, 153 bulgunun her biri kaynak kodda yeniden açıldı) 30 bulgu aynı sorunun ajanlar arası tekrarı olarak birleştirildi, 2 madde bulgu sayılmadı (ölçüm notu), 10 bulgunun şiddeti yeniden derecelendirildi; hiçbir bulgu tamamen çürütülmedi. Aşağıdaki tablolar ve sayılar BENZERSİZ bulguları gösterir; tekrarlar ve ölçüm notları burada listelenir.

**Şiddeti değişenler:**

- `ekranA-1` Yüksek → **Orta**: 768 dikey tablette hücre ~176 px: metrik değerleri SIĞIYOR (33 px bold '1000 Hz' ≈126 px), CoilCard alt metrikleri sıkışıyor — kırılma değil sıkışma.
- `ekranA-6` Orta → **Düşük**: Android'de KAV behavior=undefined DOĞRU; ancak Expo'nun edge-to-edge katmanı adjustResize davranışını korur — 'ScrollView kısalmaz' iddiası cihazda doğrulanmadan kabul edilemez.
- `ekranB-1` Yüksek → **Orta**: 182 px bobin kartı kullanışsız derecede dar ama parametre girişleri erişilebilir; 'iş yapılamıyor' eşiği aşılmıyor.
- `ekranC-4` Yüksek → **Orta**: Hasta adı 8 karaktere kırpılıyor ve sil/paylaş hedefleri küçük; detay ekranı bilgiye erişimi koruyor.
- `aihub-8` Orta → **Düşük**: 320 px'te başlık 3-4 satıra kırılıyor; içerik kaybı yok.
- `ilkel-3` Orta → **Düşük**: Kapat (X) küçük ama aynı modalda tam boy 'Reddet' düğmesi var; erteleme yolu kapalı değil.
- `ilkel-5` Orta → **Düşük**: 'Temizle' onay diyaloğuyla korunuyor; hedef küçük ama yıkıcı sonuç yok.
- `ilkel-7` Düşük → **Orta**: Kök neden (S3): rs(44) 320 px'te 38 px — dokunma hedefi minimumlarının ölçekle KÜÇÜLMESİ sistemik; tek başına düşük görünse de 20+ bulgunun kaynağı.
- `launcher-1` Orta → **Yüksek**: CDP ölçümüyle doğrulandı: varsayılan 880×600 pencerede bile profil-seçim başlığı üst çubuğun altında ve kaydırmayla ulaşılamıyor; 1366×768 @%150'de daha kötü.
- `site-7` Orta → **Düşük**: 640-900 px'te başlık 4-5 satıra kırılıyor — okunabilir, yalnız orantısız.

**Kısmen / şüpheli bırakılanlar:**

- `kabuk-2` (kismen): 700-767 px PC penceresi yalnız %200 DPI'lı 1366 px ekranda ya da elle küçültülmüş pencerede oluşur; kod doğru, olasılık düşük.
- `ekranC-8` (kismen): Dokunma hedefi kısmı doğru. PanResponder'ın yatay çip ScrollView'ini 'çalması' şüpheli: native ScrollView dokunuşta yanıtlayıcı olur, ebeveyn onMoveShouldSetPanResponder ancak çocuk bırakırsa alır; cihazda ölçülmeden kabul edilmez.

**Bulgu sayılmayanlar:**

- `ampirik-9`: Bulgu değil: launcher 320-640 px'te çalışmaz (üretim dışı sınıf) — ölçüm notu.
- `ampirik-10`: Bulgu değil: Android klavye/çentik/yazı ölçeği headless'ta ölçülemedi — cihaz testi gerekir.

**Birleştirilen tekrarlar (id → kanonik):** `kabuk-11`→`ekranB-3`, `ekranA-12`→`ampirik-4`, `ekranA-17`→`kabuk-3`, `ekranB-14`→`kabuk-6`, `ekranC-11`→`kabuk-7`, `ekranC-14`→`kabuk-1`, `aihub-12`→`ekranB-7`, `ilkel-1`→`kabuk-3`, `ilkel-2`→`ekranC-3`, `ilkel-6`→`kapsam-4`, `ilkel-8`→`kabuk-8`, `ilkel-9`→`ekranB-6`, `ilkel-10`→`ekranB-10`, `ilkel-13`→`kabuk-9`, `ilkel-17`→`kabuk-1`, `ilkel-19`→`ekranB-9`, `matris-2`→`kabuk-3`, `matris-3`→`kabuk-1`, `matris-4`→`kabuk-1`, `matris-5`→`kabuk-6`, `matris-6`→`ekranB-3`, `matris-7`→`kabuk-7`, `matris-10`→`launcher-2`, `matris-11`→`ekranA-4`, `matris-13`→`site-5`, `ampirik-2`→`launcher-1`, `ampirik-3`→`site-1`, `ampirik-6`→`site-5`, `ampirik-7`→`site-11`, `ampirik-8`→`kabuk-1`

## 9. Doğru yapılanlar (korunmalı)

**pf kabuk + tema + navigasyon**

- Kabuk (AppShell) useSafeAreaInsets ile üst inset'i root'a, alt inset'i bottom-nav'a ve 'Daha Fazla' sheet'ine, profil/bildirim menülerine uyguluyor; SafeAreaProvider _layout.tsx'te en dışta (pf/src/components/ui/AppShell.tsx:209, 402, 430, 471).
- GlobalEmergencyStop her rotada absolute + insets.bottom + bottomOffset(rs(76)) ile alt navigasyonun ÜSTÜNDE konumlanıyor; içerik ScrollView paddingBottom rs(160)+insets.bottom ile son satırı örtmüyor (AppShell.tsx:385-399; GlobalEmergencyStop.tsx:51). ESTOP m…
- useResponsive useWindowDimensions'a dayanıyor → döndürme ve pencere yeniden boyutlandırmada kabuk (sidebar ↔ bottom-nav) canlı geçiş yapıyor; AuroraBackground da useWindowDimensions ile tam-ekran kalıyor.
- Bottom-nav en fazla 4 rota + 'Daha Fazla' (5 slot) ile sınırlandırılmış; sidebar'da ScrollView var (kısa yükseklikte 11 öğe kaydırılabilir); nav öğeleri minHeight rs(44)/rs(56)/rs(48) ile dokunma hedefi ≥44pt; ikon-only düğmede iconBtn 44x44 (AppShell.tsx:593…
- Swipe-gezinme yalnız mobil (desktop=false) ve net yatay hareketle tetikleniyor; dikey scroll ve kart dokunuşlarını bloklamıyor (AppShell.tsx:175-206).
- Header sol blok flex:1 + minWidth:0 + numberOfLines; ResponsiveGrid hücreleri minWidth:0 → web'de flex-item taşması önlenmiş (AppShell.tsx:591; ResponsiveGrid.tsx:39).
- Web export'ta rn-web önerilen reset var: html/body height:100%, body overflow:hidden, #root flex → sayfa gövdesi yatay kaydırmaz, kaydırma ScrollView'de (pf/dist/index.html); viewport meta width=device-width, initial-scale=1 doğru; kullanıcı zoom'u engellenme…
- Hover'a bağımlı hiçbir işlev yok (onHoverIn/hovered/cursor grep boş); tüm Pressable'larda accessibilityRole=button + label → PC'de Tab ile odaklanabilir, Modal'lar onRequestClose ile Escape/geri tuşunu destekliyor.
- useReducedMotion sistem 'hareketi azalt' tercihini canlı dinliyor (WCAG 2.3.3).
- rs()/rf() ölçek fabrikası 320px telefonda 0.85'e kadar küçültüp içeriği sığdırıyor; rf yumuşak ölçekle metnin aşırı büyümesini frenliyor (tokens.ts:10-25).
- Modal kartları (profil menüsü, bildirim, operatör, güncelleme kapısı, toast) maxWidth rs(230-480) + width:100% ile geniş ekranda gerilmeden ortalanıyor.

**pf ekranlar A (Auth, Welcome, Dashboard, Settings)**

- tokens.ts rs()/rf(): ölçek KISA kenardan hesaplanıp 0.85–1.30 arasında clamp'leniyor → telefon döndürüldüğünde boyutlar zıplamıyor; PC'de sabit 1.3 (öngörülebilir).
- useResponsive + breakpoints.ts tek kaynak (compact/phone/tablet/desktop/wide) ve ResponsiveGrid Children.toArray ile hayalet hücreyi eliyor, hücrelerde minWidth:0 (web'de taşma önlemi).
- AppShell: paddingTop insets.top, bottomNav paddingBottom max(insets.bottom, sm), içerik paddingBottom rs(160)+insets.bottom (kayan ACİL DURDUR son satırı örtmüyor), başlık numberOfLines=1 + headerLeft minWidth:0, ikon düğmesi 44pt, bildirim sayfası maxWidth 4…
- GlobalEmergencyStop: absolute + insets.bottom, maxWidth rs(520) (geniş ekranda aşırı gerilmiyor), minHeight 52, adjustsFontSizeToFit.
- AuthScreen: ScrollView(flexGrow:1, ortalı) + KeyboardAvoidingView(iOS padding) + keyboardShouldPersistTaps; kart maxWidth rs(430) (PC/tablette form gerilmiyor); Ad/Soyad ve Şehir/İlçe satırı flexWrap + minWidth rs(150) ile dar telefonda tek sütuna düşüyor; gö…
- WelcomeScreen: <768'de kartlar sütun, üstünde flexWrap satır; cardsContainer maxWidth rs(1200); planRow flexWrap; e-posta numberOfLines=1 + flex:1; ScrollView bounces=false, flexGrow ortalama.
- DashboardScreen: container maxWidth rs(1200) + alignSelf center (2560px'te aşırı gerilme yok); statusRow flexWrap; heroGrid/bottomGrid flexWrap; CoilCard MiniMetric numberOfLines + adjustsFontSizeToFit; StatusPill numberOfLines=1 + hareketi-azalt desteği; Sys…
- SettingsScreen: container maxWidth rs(900) (PC'de form satırları okunabilir genişlikte); saklama süresi çipleri flexWrap; cihaz kimliği numberOfLines=1 + ellipsizeMode="middle" + flex:1; Info değerleri numberOfLines=2; web-only (dosya indirme) bölümleri Platf…
- Android: windowSoftInputMode=adjustResize, screenOrientation unspecified (yatay destek), configChanges ile döndürmede yeniden başlatma yok; kökte SafeAreaProvider; app.json supportsTablet + orientation default.
- fonts.ts: fontWeight→Inter dosya eşlemesi ve italik fallback koruması (Android'de sistem fontuna düşme yok).

**pf ekranlar B (Control, SensorMonitor, DemaSimulator)**

- SensorMonitorScreen grafik genişliğini sarmalayıcının GERÇEK genişliğinden onLayout ile ölçüyor ve 1200'de sınırlıyor (satır 111-120) — her yön/boyutta konteynere oturur.
- GlobalEmergencyStop: position:absolute + zIndex 10000 + insets.bottom + maxWidth rs(520) + adjustsFontSizeToFit; AppShell içerik ScrollView'i altına rs(160)+insets.bottom (mobil) / rs(84) (masaüstü) boşluk bırakıyor → kayan ACİL DURDUR son satırı örtmüyor (Ap…
- ControlScreen PatientGate'i `soft` kipte kullanıyor → hasta seçili değilken bile ACİL DURDUR gizlenmiyor (ControlScreen 460-465, PatientGate 49-54).
- ObservationNotesModal bobin çalışırken açılmıyor → tam-ekran modal ACİL DURDUR erişimini kapatmıyor (ControlScreen 742-746).
- ResponsiveGrid koşullu/falsy çocukları eliyor ve hücreye minWidth:0 veriyor (web'de içerik taşmasını önler); Control sekmeleri / hedef çipleri / bobin filtre satırları flexWrap ile sarıyor; ParamField flex:1 + minWidth rs(140) ile dar ekranda 2'li dizilime dü…
- Üç ekran da içeriği maxWidth ile ortalıyor (Control/Sim rs(1100), Sensor rs(1200)) → 1920-2560 PC'de sonsuz gerilme yok.
- tokens.ts rs()/rf() ölçeği 0.85-1.30 arasına clamp'li; sekme etiketleri, ACİL DURDUR, Durdur ve AI Pro toggle metinleri numberOfLines+adjustsFontSizeToFit ile kırpılmıyor; sayısal değerlerde tabular-nums.
- DemaSimulator native WebView: içerik yüksekliğini postMessage/ResizeObserver ile ölçüp WebView'i içeriğe büyütüyor + nestedScrollEnabled + device-width viewport enjeksiyonu → mobil simülatör kesilmiyor, dış ScrollView kilitlenmiyor.
- Android windowSoftInputMode=adjustResize + AppShell ScrollView keyboardShouldPersistTaps="handled"; ObservationNotesModal insets.bottom'u alt boşluğa ekliyor.
- RealtimeChart native tarafta react-native-svg ile çizim + 120 noktaya downsample; kapalı seride NaN eksen koruması; web'de yalnız veri değişince yeniden çizim.
- Bobin seçici, E-stop, per-coil Başlat/Durdur düğmelerinde accessibilityRole/Label/State mevcut; aşırı ısınma uyarısı live-region ile duyuruluyor.

**pf ekranlar C (Patient, TreatmentHistory, KpiDashboard, AiHistory)**

- ResponsiveGrid (ResponsiveGrid.tsx:19-26) Children.toArray ile falsy çocukları eler (hayalet hücre yok) ve hücreye minWidth:0 verir (web'de uzun içerik satır kaydırmaz).
- KpiDashboardScreen grafik genişliğini Dimensions yerine kartın gerçek iç genişliğinden onLayout ile ölçer (KpiDashboardScreen.tsx:99-102, 151, 167) → tek/çift kolon ve döndürmede grafik kart sınırına oturur.
- KPI bobin tablosu hücreleri flex:1 + minWidth rs(34) + numberOfLines=1 + adjustsFontSizeToFit + tabular-nums (KpiDashboardScreen.tsx:248-269, 312-319) → 6 sütun 320px'te kırpılmadan sığar.
- SessionDetailModal bobin tablosu sabit sütun genişlikleriyle yatay ScrollView içinde (SessionDetailModal.tsx:281-332, 625-629) → dar ekranda hücreler ezilmez, yatay kaydırılır; modal width 100% + maxWidth rs(900) + maxHeight 92% ile hem telefonda hem geniş PC…
- PatientScreen ikon-aksiyon düğmeleri minWidth/minHeight rs(44) (PatientScreen.tsx:394) ve isim sütunu minWidth:0 + numberOfLines=1 (305-306, 384) → dokunma hedefi ve metin kırpma doğru.
- Patient/History üst başlık satırları flexWrap (PatientScreen.tsx:367, TreatmentHistoryScreen.tsx:461-468; intro minWidth rs(200)) → dar ekranda düğmeler alt satıra iner.
- Hasta formu ResponsiveGrid minItemWidth={200} ile telefonda 1, tablette 2-3 sütun (PatientScreen.tsx:227-236).
- Dört ekran da width:100% + maxWidth rs(1100)/rs(1200) + alignSelf center kullanır (PatientScreen.tsx:361, TreatmentHistoryScreen.tsx:223, KpiDashboardScreen.tsx:281, AiHistoryScreen.tsx:404) → 1920-2560 PC'de içerik sınırsız gerilmez.
- AppShell içerik ScrollView'ı mobilde paddingBottom rs(160)+insets.bottom (AppShell.tsx:385-392) → kayan ACİL DURDUR + alt nav son satırı örtmez; keyboardShouldPersistTaps=handled.
- SessionCard sağ aksiyon kümesi flexShrink:1 + flexWrap (TreatmentHistoryScreen.tsx:381) ve Detail kutuları minWidth rs(100)+flex:1 (524-530) → 5 parametre karosu dar ekranda alt alta sarılır.
- AiHistory metaRow flexWrap (AiHistoryScreen.tsx:442), çip etiketi maxWidth rf(160)+numberOfLines=1 (435), kart başlığı flex:1 numberOfLines=1 (311, 440).
- Boş/hata/yükleniyor durumları dört ekranda da var ve 'Tekrar Dene' sunar (PatientScreen.tsx:284-295, TreatmentHistoryScreen.tsx:257-273, AiHistoryScreen.tsx:291-300); History boş durumu sayfalama bağlamını da açıklar.
- fmtDate (AiHistoryScreen.tsx:42-55) ve KPI etiket üretimi (120-133) tarih/sayı biçimini sabit uzunlukta tutar → hücre taşması yok; MetricCard tabular-nums.
- AppShell alt nav ve sheet'ler insets.bottom kullanır, üst bar insets.top (AppShell.tsx:209, 402, 430) → çentik/safe-area kabuk düzeyinde çözülmüş; ObservationNotesModal da insets.bottom ekliyor.

**pf AI Hub + AI modülleri**

- AiHubScreen içerik kolonu geniş ekranda sınırlı: styles.content = { width:'100%', maxWidth: rs(980), alignSelf:'center' } (AiHubScreen.tsx:3641) → 1920-2560 px'de kartlar aşırı gerilmiyor.
- Isı haritası sahnesi (XaiIsiHaritasi/xaiStage, AiHubScreen.tsx:814-827, 3672) ve Scratch galerisi (scStage:3761) AÇIK yükseklik rs(300) + resizeMode='contain' ile ebeveynden bağımsız; 2026-09-03 düzeltmesi tüm XAI görsellerinde (Vision/CatSound/KidneyCT/Histo…
- Görüntü/kamera modüllerinde buton satırı dar ekranda dikey diziliyor: `[styles.btnRow, isCompact && { flexDirection:'column' }]` (VisionModule 1493, Phantom 1891, Petri 2112, CatOrgan 3549) — useResponsive altyapısı gerçekten kullanılıyor.
- DiseaseModule vital girişleri ResponsiveGrid minItemWidth={150} ile (AiHubScreen.tsx:965) → telefonda 1, tablette 2, masaüstünde 3 sütun; boş/koşullu child hayalet hücre bırakmıyor.
- Yükleme öncesi görüntü küçültme SABİT 1500px (rs değil) → DPI/ölçekten bağımsız (AiHubScreen.tsx:47-60).
- Uzun etiketlerde numberOfLines koruması yaygın: modül kartı label/desc (322-323), ckdNumLabel (2437), soundBarLabel (2689), rnaFileName, soundFileName (maxWidth rs(220)); AiProPanel'de adjustsFontSizeToFit ile kritik buton metinleri (835, 852, 881).
- CKD form hücreleri width:'47%' + flexGrow:1 (ckdNumCell:3699) → 320 px'de bile iki sütun sığıyor, 14 sayısal alan sıkışmıyor; ckdCatBtn minWidth rs(56) ile Evet/Hayır düğmeleri sabit genişlikte.
- Kamera flip düğmesi (flipCameraBtn:3677) rs(44)×rs(44) → dokunma hedefi ≥44 px; modül ikon kutusu rs(44).
- AppShell içerik ScrollView'ı keyboardShouldPersistTaps='handled' ve altta rs(160)+insets.bottom dolgu (AppShell.tsx:385-392) → kayan ACİL DURDUR son satırı örtmüyor; üst safe-area insets.top ile alınıyor.
- Sabit rakamlar çoğunlukla rs()/rf() fabrikasından geçiyor (tokens.ts:11-25, 0.85-1.30 clamp) → 320 px telefonda orantılı küçülme; typography/spacing token'ları tek kaynak.

**pf UI ilkelleri + görsel bileşenler + modallar**

- tokens.ts rs()/rf() ölçek fabrikası 0.85-1.30 arası clamp'li; rf() yazıyı daha yumuşak (0.7 katsayı) büyütüyor → 320px'te yazılar aşırı küçülmüyor.
- ResponsiveGrid: Children.toArray ile hayalet hücre yok, cell minWidth:0 (web'de uzun içerik sarma), rowGap; useResponsive.columns'a bağlı.
- Button: minHeight (sm/md/lg), numberOfLines=1, çift-dokunuş koruması, haptik, useReducedMotion ile basış animasyonu atlanıyor; web'de overflow:hidden ile gradyan köşe kırpması, native'de gölge görünür.
- ToastProvider: pointerEvents='box-none' (başlık kontrollerini bloklamıyor), maxWidth rs(480) + alignSelf center (geniş ekranda gerilmiyor), numberOfLines=4, accessibilityRole='alert' + liveRegion; hata toast'ı düşük öncelikli toast'a ezdirilmiyor.
- GlobalEmergencyStop: useSafeAreaInsets ile alt çentik/gesture-bar payı, left/right spacing + maxWidth rs(520) (geniş PC'de orantılı), minHeight rs(52), adjustsFontSizeToFit, zIndex 10000; AppShell içerik paddingBottom'u butonu hesaba katıyor.
- SessionDetailModal: bobin tablosu yatay ScrollView içinde (dar ekranda kaybolmuyor), summaryGrid flexWrap + flexBasis rs(120), card width 100% + maxWidth rs(900) + maxHeight 92%, gövde ScrollView.
- ObservationNotesModal: bottom-sheet ScrollView + insets.bottom + keyboardShouldPersistTaps='handled', chips flexWrap, maxWidth rs(560) + alignSelf center (tablet/PC'de tam genişliğe yayılmıyor), Kaydet etiketinde adjustsFontSizeToFit.
- DevicePairingGuide: sheet maxHeight 88% + ScrollView, kapat düğmesinde hitSlop=10, metin satırlarında flex:1 + lineHeight, ikon+metin satırları alignItems flex-start (sarmada ikon üstte kalıyor).
- BackupPassphraseDialog / OperatorSwitcher: giriş ve düğmelerde minHeight rs(44), card width 100% + maxWidth rs(420-440), backdrop padding; PIN girişinde number-pad + maxLength.
- AuroraBackground useWindowDimensions ile boyutlanıyor (döndürme/pencere yeniden boyutlandırma güvenli); React.memo.
- Skeleton genişliği onLayout'tan ölçüyor (px tabanlı süpürme her boyutta doğru); StatusPill/FadeInView/Skeleton useReducedMotion'a saygılı.
- NotificationCenter başlık satırı flexWrap:'wrap' (dar ekranda eylemler alt satıra iniyor), mesaj numberOfLines=3, itemBody flex:1.
- SensorMonitorScreen RealtimeChart genişliğini onLayout'tan alıp Math.min(chartW, 1200) ile sınırlıyor; web canvas style width:100% height:auto.
- UpdateBanner metni flex:1 + numberOfLines=2; StatusPill etiketi numberOfLines=1; AppShell notifSheet width 100% + maxWidth rs(420).
- elevation() yardımcısı web'de boxShadow, native'de shadow* kullanıyor (renkli glow her platformda görünür).

**launcher istemci arayüzü (index.html)**

- Tek kaydırma bölgesi: body overflow:hidden + main overflow:auto (index.html 29-43, 96-97) — header/footer sabit kalır, yalnız sahne kayar.
- Satır uzunluğu geniş pencerede kontrollü: .stage max-width 560px; .lead/.progress/.dlmeta/#notice/#error max-width 460px (98, 105, 264, 270, 229, 296).
- Header kademeli daralma (381-401): .brand flex:1 1 auto + min-width:0 + ellipsis; 1180'de alt başlık, 1040'ta düğme etiketleri gizlenir, e-posta 190→120px kırpılır. Aksiyonlar hiç sarmaz (üst üste binme yok).
- İndirme kartı (.dlmeta 264-268): flex-wrap + gap 12/28 + tabular-nums; fmtBytes/fmtSpeed/fmtEta (1002-1009) kısa metin üretir → 3 sütun 460px'e tek satır sığar, sığmazsa düzgün sarar.
- .chips, .subactions, footer, .dep-notice flex-wrap ile sarar (118, 188, 303, 209) — uzun Türkçe etiketler taşmaz.
- Kılavuz modalı (318-321): max-height 88vh + .guide-body overflow-y:auto + overlay padding 24 → 700x540'ta tamamı kaydırılarak okunabilir.
- #error (295-300): max-height 150 + overflow:auto + user-select:text → uzun hata sahneyi ele geçirmez, destek için kopyalanabilir; .errdetail'de word-break var.
- Profil kartı açıklamaları sarar (.meta min-width:0, nowrap yok; 154-160) — 'Araştırma modelleri — petri, histopatoloji…' 560px'te 2 satıra iner, kesilmez.
- Giriş formu klavye: Enter ile giriş (2133), açılışta login-email odağı (2331/2344), pw-toggle ve bgbtn'de focus-visible halkası (207, 260), inputlarda user-select:text (198-199).
- Güncelleme kipi (html.gunc 101-104 + JS 2288-2296): header/footer gizli, 22px iç boşluk; 640x400 pencerede içerik (~225px) 356px alana rahat sığar; Rust min_size'ı kaldırıp 640x400'e küçültüyor (main.rs 2085-2088).
- [hidden]{display:none!important} koruması (27) — class kuralları gizli ekranları yanlışlıkla gösteremez.
- Tauri penceresi resizable + minWidth/minHeight + center (tauri.conf.json 13-19); 'app' penceresi maximized açılır (main.rs 415-418).

**web sitesi pemf-vet-web**

- Header: md altında hamburger menü var (Header.tsx 45-80), menü her NavLink/CTA tıklamasında kapanıyor; 320px'te logo (36px) + marka adı + 40px hamburger rahat sığıyor.
- Tüm sayfalar mobil-öncelikli Tailwind ızgaralarıyla kurulmuş (sm:grid-cols-2 / lg:grid-cols-3-4); kapsayıcılar max-w-6xl/5xl/3xl + px-5 sm:px-6 oluk ile sınırlı → 4K'da metin satırı aşırı uzamıyor, gövde asla yatay kaymıyor.
- App.tsx 33: kabuk `flex min-h-svh flex-col` + `main flex-1` → kısa sayfalarda footer alta yapışık, mobilde iOS adres çubuğu sorunu olmayan svh birimi kullanılmış (ErrorBoundary'de de aynı).
- Pricing karşılaştırma tablosu `overflow-x-auto` sarmalayıcıda (Pricing.tsx 159-160) → dar ekranda sayfa değil yalnız tablo kayıyor; sütunlar PLANS'tan türediği için yeni plan eklenince taşma yaratmıyor.
- AppScreenshots: snap-x kaydırmalı galeri, img'lere width/height (560×1116) + loading=lazy verilmiş → CLS yok; ok tuşları yalnız md+ (dokunmatikte parmakla kaydırma), mobilde '← kaydırın →' ipucu var.
- AuthModal: `fixed inset-0 p-4` + `max-h-[90vh] flex-col` + form `flex-1 overflow-y-auto` → uzun kayıt formu küçük ekranda kendi içinde kayıyor; role=dialog, odak hapsi, Esc ile kapanma mevcut.
- Formlar (Odeme, ResetPassword, AuthModal) tam genişlik `.input`/`w-full`, iki sütun yalnız sm+ (`sm:grid-cols-2`), gönder düğmeleri `w-full`; TC alanında inputMode=numeric → mobil klavye doğru.
- Görseller: LauncherMock saf CSS maket (ölçekle sorunsuz, başlık `min-w-0 truncate`), TR/EN rozeti sm altında gizleniyor; screenshot img'leri `w-full` ile kapsayıcıya sığıyor.
- Legal uzun metinler max-w-3xl + text-sm leading-relaxed → ~70 karakterlik okunabilir satır; tablo yok, taşacak uzun URL yok.
- Support SSS native <details>/<summary> ile — JS'siz, hover'a bağlı değil, dokunmatikte çalışıyor; summary py-4 ile dokunma hedefi yeterli.
- Hover etkileşimleri yalnız kozmetik (renk/gölge/translate); hover'a bağlı hiçbir işlev yok — dokunmatikte kayıp özellik olmuyor.
- Viewport meta doğru (`width=device-width, initial-scale=1`), maximum-scale/user-scalable kısıtı yok → yakınlaştırma erişilebilirliği korunuyor; Google Fonts isteği kaldırılıp sistem yazı tipi zinciri kullanılmış.
- ADDONS ızgarası kalem sayısına göre daralıyor (Pricing.tsx 214) → 2 kalemde boş üçüncü hücre yok; Footer md altında tek sütuna iniyor.
- Tüm boyutlar rem/em tabanlı (tokens `@theme`), sabit px genişlik yalnız bilinçli galeri figürlerinde (200/224px) → DPI %125-200'de içerik doğru ölçekleniyor.

**cihaz/host matrisi + yazı ölçeği + yön**

- KODDAN ÇIKARILAN HEDEF MATRİS — (1) Android telefon dikey+YATAY: app.json orientation="default", AndroidManifest screenOrientation="unspecified", edgeToEdgeEnabled=true, windowSoftInputMode=adjustResize; (2) iOS telefon+iPad: supportsTablet=true (iPad'de tüm …
- react-native-safe-area-context ~5.7 kurulu; SafeAreaProvider kökte (pf/app/_layout.tsx:32) ve AppShell (paddingTop insets.top, alt bar paddingBottom max(insets.bottom, sm)), GlobalEmergencyStop (bottom + insets.bottom), ObservationNotesModal insetleri kullanı…
- expo-status-bar style="light" kökte tek yerden (pf/app/_layout.tsx:34) — koyu tema ile tutarlı.
- useResponsive() gerçek useWindowDimensions üzerinden çalışır → PC'de pencere küçültme ve web'de yeniden boyutlandırma anında düzen değiştirir (kenar çubuğu ↔ alt bar).
- Tüm ekranlar geniş ekranda (f) içerik genişliğini sınırlayıp ortalıyor: Dashboard/Sensor/KPI maxWidth rs(1200), Control/Patient/History/AiHistory rs(1100), Settings rs(900), AiHub rs(980) → 2560 px'te aşırı gerilmiş satır yok.
- Dashboard/Sensor/History/Control/Settings/Patient satırları flexWrap+minWidth ile sarıyor; ResponsiveGrid boş child'ları eleyip flexBasis'i kolon sayısına göre veriyor; KPI grafik genişliği onLayout ile ölçülüyor (sabit Dimensions yok).
- AiHub modüllerinde isCompact'te buton satırı dikeye dönüyor (AiHubScreen.tsx:1493-1504, 1891, 2112, 3549) → dar telefonda buton metni kırpılmıyor.
- GlobalEmergencyStop metni adjustsFontSizeToFit + numberOfLines=1 → sistem yazı büyütmede (i) ACİL DURDUR düğmesi taşmaz; minHeight rs(52) dokunma hedefi yeterli.
- Hover'a bağlı hiçbir işlev yok (onHoverIn/:hover grep = 0) → dokunmatik tablet/telefon web'de kayıp işlev yok.
- Launcher HTML'i başlık çubuğunu 1180/1040/680 px kırılma noktalarında kademeli sadeleştiriyor (index.html:382-400); ana pencere min 700×540 ile CSS uyumlu.
- pemf-vet-web: Tailwind responsive sınıfları yaygın (110 kullanım), mobil menü (Header.tsx:46,55 md:hidden), Pricing tablosu overflow-x-auto sarmalında.
- AuthScreen KeyboardAvoidingView + keyboardShouldPersistTaps="handled"; AppShell ScrollView de keyboardShouldPersistTaps="handled".
- Android klavye: adjustResize + edge-to-edge → native tarafta klavye açılınca pencere daralır (klavye altında kalan giriş riski web'e göre düşük).
- Alt bar öğeleri minHeight rs(56), 'Daha Fazla' sheet satırları minHeight rs(48), header Ayarlar düğmesi 44×44 (a11y notlu) → ana gezinme dokunma hedefleri yeterli.

**AMPİRİK: gerçek tarayıcıda çoklu-viewport ekran görüntüleri**

- ÖLÇÜM YÖNTEMİ NOTU: Edge `--headless=new --window-size=W,H --screenshot` PNG'yi W×H üretiyor ama SAYFA DÜZENİ (window.innerWidth) 504×473 sabit kalıyor (probe.html ile kanıtlandı) → ilk tur görüntüler geçersizdi ve ATILDI. Tüm bulgular Chrome DevTools Protoco…
- pf AuthScreen (giriş kapısı): 11 viewport'un HİÇBİRİNDE yatay taşma yok (scrollWidth == innerWidth: 320, 360, 390, 640×360, 700×540, 768, 911×512, 1024, 1280, 1920, 2560). Kart `width:100%, maxWidth: rs(430), alignSelf:center` ile hem 320'de kenar boşluklarıy…
- pf AuthScreen: ScrollView + KeyboardAvoidingView + `keyboardShouldPersistTaps="handled"` → yatay telefon (640×360) ve küçük launcher penceresinde (700×540) form kaydırılarak tamamen erişilebilir; Giriş düğmesi kaybolmuyor (pf_gate_640x360.png, pf_gate_700x540…
- pf Kayıt Ol formu: `row: { flexDirection:'row', flexWrap:'wrap' }` + alan `minWidth: rs(150)` sayesinde Ad/Soyad ve Şehir/İlçe 320px'te alt alta (191px), 640px+ genişlikte yan yana (199–233px) diziliyor; hiçbir viewport'ta taşma yok (pf_register_320x568.png, …
- pf tokens.ts `rs()/rf()` ölçeği 0.85–1.30 arasında clamp'li: 320px'te içerik küçülüp sığıyor, tablette/masaüstünde aşırı büyümüyor (768×1024 ve 1024×768 görüntüleri dengeli).
- Launcher header (index.html 380-402): `flex-wrap:nowrap`, marka `overflow:hidden + ellipsis`, `@media (max-width:1180/1040/680px)` ile önce alt başlık sonra düğme etiketleri gizleniyor, e-posta çipi 120px'te kırpılıyor → 700×540 minimum pencerede header tek s…
- Launcher `.stage { max-width:560px }`, `.form { max-width:420px }`, `.guide-modal { max-width:780px; max-height:88vh }` → 1920 ve 2560'ta içerik ortalı, gerilmiyor; s-install (indirme) ve s-guncelleme (640×400 pencere) ekranları tüm pencere boyutlarında tamam…
- Launcher DPI: 911×512 mantıksal + deviceScaleFactor 1.5 (1366×768 @%150) render'ı dsf 1 ile piksel-eşdeğer düzen üretiyor; DPI'ya özgü ek kırılma yok (launcher_login_911x512_dsf1.5.png).
- pemf-vet-web: `mx-auto max-w-6xl` konteyner ile 1920/2560'ta içerik 1152px'te ortalanıyor, aşırı gerilme yok (web_home_2560x1440.png); `/download` ve `/pricing` 320/390'da hiç yatay taşma üretmiyor (scrollWidth==320/390); 768 tablette hero tek sütun, kartlar …
- pemf-vet-web /pricing karşılaştırma tablosu `min-w-[560px]` ama `overflow-x-auto` sarmalayıcı içinde (Pricing.tsx:159-160) → sayfa geneline taşma yok, tablo kendi içinde kaydırılıyor (ölçüm: sarmalayıcı w=350 sw=560, body sw=390).
- Web sitesi hero düğmeleri 320'de `flex-col` tam genişlik (44px+ yükseklik), 911px'te yan yana; dokunma hedefleri yeterli (web_home_320x568.png, web_home_911x512.png).

## 10. Kapsam notu

Kapsam turunda tamamlanan dosyalar: pf/src/components/domain/MobileUpdateBanner.tsx (hiç okunmamıştı — bu turda okundu); pf/src/components/domain/RecoveryCodeBanner.tsx (hiç okunmamıştı — bu turda okundu); pf/src/components/domain/SurumFarkiBanner.tsx (hiç okunmamıştı — bu turda okundu); pemf-vet-web/src/components/Icons.tsx (hiç okunmamıştı — bu turda okundu; yalnız classNam…; pf/src/components/domain/MobileUpdateGate.tsx (yalnız 'stil bölümü' okunmuştu — bu turda …; pf/src/components/UpgradeModal.tsx (yalnız 'stiller' okunmuştu — bu turda render dahil TA….

Kapsam taraması (find): pf/src/screens (12 ekran), pf/src/components (domain 20 / ui 14 / visual 1 / kök 1), pf/app (2), pemf-vet-web/src/pages (9) + components (12), launcher/app/ui (1 html). Test dosyaları (__tests__) ve saf mantık/context dosyaları kapsam dışı bırakıldı. Bulucu listesiyle kıyasta OKUNMAMIŞ 4 arayüz dosyası (MobileUpdateBanner, RecoveryCodeBanner, SurumFarkiBanner, web Icons.tsx) ve yalnız stil bölümü okunmuş 2 dosya (MobileUpdateGate, UpgradeModal) bulundu; hepsi bu turda tam okundu. Bulguların dayanağı: breakpoints.ts (compact<480<phone<768<tablet<1024<desktop<1440<wide), useResponsive (width/height/isCompact), tokens.ts rs/rf (SCALE = kısa kenar/375, 0.85-1.30 clamp; a…


---
*Üretim: `rapor_uret.py` — 153 ham / 121 benzersiz bulgu, ikinci doğrulama Claude, 10 alan, 22 ajan, 557 araç çağrısı.*

---

## Kapanış durumu — 2026-09-05

Plan (`docs/responsive-duzeltme-plani-2026-09-04.md`) sırayla uygulandı. 15 commit,
`production-hardening` dalında.

### Kapanan fazlar

| Faz | Kapsam | Durum |
|---|---|---|
| 0 | ekranB-2: ACİL DURDUR erişimi + STM belirsizliğinde gizlenmeme | kapandı |
| A1 | touch/layoutMax/MAX_FONT_SCALE token'ları, theme/layout.ts, ShellLayoutContext, useKeyboard, ScrollableModalCard | kapandı |
| A2 | Ölçek tavanı: büyük ekran %110, telefon değişmezliği | kapandı |
| B | İçerik-farkında kabuk (bottom/rail/sidebar), klavyede erişilebilir ACİL DURDUR | kapandı |
| C | S1, S2, S3, S4, S5, S6, S7 ekran düzeyi düzeltmeleri | kapandı (cihaz doğrulaması hariç) |
| D | Beş pytest kapısı + bir vitest kapısı + görünüm alanı kapısı CI'da | kapandı |
| E | Başlatıcı: dikey taşma, pencere boyutu, klavye erişimi | kapandı (yayın hariç) |
| F | Site: yatay taşma, dokunma hedefleri, tek koyu tema, iOS giriş alanları | kapandı (yayın hariç) |
| G | Yayın zinciri + cihaz test matrisi | **AÇIK — sahip onayı bekliyor** |

### Ampirik kanıt (headless Edge + CDP, `scripts/responsive_kapisi.py`)

| Hedef | Ölçüm | Denetimde | Şimdi |
|---|---|---|---|
| pf (web dışa aktarım) | 16 | 1 yüksek | **0** |
| launcher | 36 | 4 yüksek | **0** |
| site | 40 | 100 (yüksek/orta) | **0** |

### Regresyon kapıları

| Kapı | Ne ölçer | Kırmızı kanıtı |
|---|---|---|
| `tests/test_kabuk_ic_scrollview_kapisi.py` | Kabuk içi dikey kaydırıcı yasağı | 3/3 mutasyon |
| `tests/test_modal_kaydirilabilir_kapisi.py` | Her modal kısa ekranda kaydırılabilir | 3/3 mutasyon |
| `tests/test_dokunma_hedefi_kapisi.py` | Dokunma hedefi cırcırı (139 → 118, hedef 0) | 3/3 mutasyon |
| `tests/test_arayuz_yazi_olcegi_kapisi.py` | Yazı ölçeği tavanı + rf(9\|10) cırcırı (17 → 7) | 4/4 mutasyon |
| `tests/test_responsive_grafik_kapisi.py` | Grafik/kamera katmanı çıpaları | 7/7 mutasyon |
| `tests/test_launcher_responsive_kapisi.py` | Başlatıcı yerleşim/erişilebilirlik | 7/7 mutasyon |
| `tests/test_ai_kare_boyutu.py` | Backend kare boyutu alanları | 3/3 mutasyon |
| `pemf-vet-web/src/__tests__/responsive-sozlesmesi.test.ts` | Site responsive sözleşmesi | 6/6 mutasyon |
| `scripts/responsive_kapisi.py` (CI) | Gerçek tarayıcıda piksel ölçümü | CSS mutasyonu → exit 1 |

⚠️ Kapıların KENDİ zaafları da ölçülerek düzeltildi: yorum satırlarını ihlal sayma (3 kapı),
ham metinde konum karşılaştırması, `hitSlop`u boyut muafiyeti sayma, genel `createElement`
araması. Her biri commit mesajında belgeli.

### Açık kalanlar

1. **Faz G — yayın zinciri.** Sürüm artışları ve GitHub Release yayını sahip onayı bekliyor:
   backend 1.9.41 → OTA → APK 2.3.32 (vc39) → launcher 1.9.46 → site.
2. **Cihaz test matrisi.** Aşağıdakiler yalnız fiziksel cihazda ölçülebilir:
   · Klavye yerleşimi (Android 15 APK + iOS EAS) — S4 adım 8.
   · Kamera hizası / organ işareti çakışması — S7 adım 7 (A4 kâğıt + ArUco protokolü).
   · Yazı ölçeği 1,3 ve 0,85 turu — S6 adım 10.
   · iOS çentik (insets.left 44-59) yalnız EAS derlemesiyle.
3. ~~Pricing mobil kart görünümü.~~ **KAPANDI (2026-09-05, commit 382555e).** 1024 altında
   SATIR kartı görünümü (her kart bir özelliği tüm planlarda gösterir, aynı değeri veren planlar
   birleşir). ÖLÇÜLEN durum: 320 px'te tablonun 280 px'i gizliydi, 5 sütundan 2'si görünüyordu.
   Beraberinde iki şey daha kapandı: (a) `—` glifinin tabloda iki ZIT anlam taşıması — sözlük
   `Alınmıyor` (avantaj) / `Yok` (eksiklik) olarak ayrıldı ve masaüstü tablo da düzeldi;
   (b) tablo erişilebilirliği (`scope="row"`/`scope="col"`/`aria-labelledby`) — ekran okuyucu
   artık "₺990"un hangi satıra ait olduğunu söyleyebiliyor.
   FREE_MODE fiyat tutarsızlığı bölüm başına eklenen notla mobilde görünür kılındı; satış
   açıldığında COMPARE tarifesinin FREE_MODE'dan haberdar edilmesi hâlâ ayrı iş.
