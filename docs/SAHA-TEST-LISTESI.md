# Saha Test Listesi — elle koşulacak senaryolar

Otomatik süitler (pytest **2945** · jest **1041** · vitest · cargo) **mutlu yolu** ve kod
düzeyindeki değişmezleri koruyor. Bu liste onların yapısal olarak göremediği sınıfı hedefler:
gerçek donanım, gerçek işletim sistemi, gerçek kullanıcı davranışı.

> Bunun neden gerektiğinin kanıtı: 2026-08-17'de sahada yakalanan "indirme bitince paylaşım
> ekranı açılıyor" hatası. Kod okununca kurulum açılıyormuş gibi duruyordu; kullanılan API'nin
> o ekranı **hiçbir zaman** sunamayacağı ancak cihazda görülünce anlaşıldı. Hiçbir statik
> denetim bunu bulamazdı.
>
> İkinci kanıt (2026-09-12, sahibin ekran görüntüsü): makinede internet VARKEN uygulama
> "İnternet yok" diyordu, aynı ekranın alt kartı ise "İnternet Bağlantısı: Aktif". İki ölçüm
> birbirini yalanlıyordu ve **ikisi de yanlıştı**. Süitler yeşildi.

**Nasıl kullanılır:** Kademe 1 her yayında koşulur. Kademe 2 güncelleme/kurulum kodu her
değiştiğinde. Kademe 6 (mobil) APK her değiştiğinde. Kademe 7 bu turun regresyonudur —
bir kez tamamen koşulmalı. Kademe 3–5 ve 8 sürüm turlarında ya da ilgili alan değiştiğinde.
Her satırda **beklenen** yazıyor; farklı bir şey olursa o bir bulgudur.

> **İşaretlemeli sürüm:** [`saha-test-listesi.html`](saha-test-listesi.html) — aynı liste,
> telefonda/tablette dokunarak ✓/✕ işaretlenir, işaretler tarayıcıda saklanır. O dosya **bu
> belgeden üretilir** (`scripts/saha_test_html_uret.py`); senaryo eklerken YALNIZ burayı
> düzenle, sonra betiği koştur.

---

## Kademe 1 — HASTA GÜVENLİĞİ (her yayında, istisnasız)

Bu bölümdeki her başarısızlık yayını durdurur.

| # | Senaryo | Beklenen |
|---|---|---|
| 1.1 | Seans sürerken uygulamayı normal yoldan kapat | Bobinler **kapanmadan önce** durur; kayıt tutarlı kapanır |
| 1.2 | Seans sürerken client'ı Görev Yöneticisi'nden **öldür** | Bobinler durur (kill öncesi durdurma yolu çalışır) |
| 1.3 | Seans sürerken makinenin **fişini çek**, tekrar aç | Açılışta bobinler kapalı başlar; yarım seans "Elektrik Kesintisi" olarak görünür, geçmişi bozmaz |
| 1.4 | Seans sürerken STM/USB kablosunu çek | Arayüz bağlantı kaybını **söyler**; sahte "çalışıyor" göstergesi kalmaz |
| 1.5 | Seans sürerken makineyi uyku moduna al, uyandır | Ya seans güvenli durdurulmuş ya da tutarlı sürüyor; "hayalet seans" olmaz |
| 1.6 | Mobilden **ACİL DURDUR** — cihazla aynı Wi-Fi'da | Bobinler durur, telefon onayı görür |
| 1.7 | Mobilden ACİL DURDUR — telefon **uçak modunda** | Komut gönderilemediği **açıkça** yazılır; "durduruldu" yalanı YOK |
| 1.8 | ACİL DURDUR sonrası yeni seans başlat | Temiz başlar; önceki seansın parametreleri sızmaz |
| 1.9 | Seans sürerken mobilde güncelleme çıksın (manifest'i geçici yükselt) | Güncelleme bandı **gösterilmez**; operatörün ekranı bölünmez |
| 1.10 | Seans sürerken profil değiştirmeyi / çıkış yapmayı dene | Önce onay + durdurma istenir; sessizce kesilmez |
| 1.11 | **Firmware sürümü uyumsuzken seans başlat** (eski firmware'li STM tak) | Seans **BAŞLAMAZ** — 503 + "hiçbir bobin komutu kabul etmedi"; sahte ilerleme çubuğu YOK. Geçmişte kayıt "Donanım Reddetti" olur |
| 1.12 | 1.11'in karşıtı: firmware doğruyken aynı seansı başlat | Normal başlar — kapı her seansı engellemiyor |
| 1.13 | Seans ortasında STM komutları reddetmeye başlasın (kabloyu gevşet) | Arayüz **durdurur** ve söyler; ekranda "sürüyor" kalmaz |
| 1.14 | Seans sürerken ACİL DURDUR'a bas, **hemen** ardından geç bir telemetri paketi gelsin | Bobin yeniden "çalışıyor" görünmez (yapışkan E-stop) |
| 1.15 | AI Pro / Otomatik seans sürerken uygulamayı kapat | Bobinler durur; otonom seans "sahipsiz" kayıt bırakmaz |
| 1.16 | Bobin 6-7 uzun süre çalıştır, sıcaklığı elle izle | ⚠️ **Cihazda termal kesme YOK** (sahip kararı). Sıcaklık ekranda **görünür**; durdurma operatörün işidir. Görünmüyorsa bu bir bulgudur |

---

## Kademe 2 — GÜNCELLEME VE KURULUM (en taze kod, en yüksek risk)

### 2A. Mobil açılış kapısı ve APK kurulumu

| # | Senaryo | Beklenen |
|---|---|---|
| 2.1 | Uygulamayı **uçak modunda** aç | Kapı beklemez; uygulama hemen açılır |
| 2.2 | Yeni sürüm varken aç | Uygulama yerine güncelleme ekranı gelir |
| 2.3 | Güncelleme ekranında **"Şimdilik devam et"** | Uygulama açılır; içerideki bant aynı sürümü **hemen yeniden dayatmaz** |
| 2.4 | 2.3'ten sonra uygulamayı tamamen kapat, tekrar aç | Kapı **yeniden sorar** (erteleme kalıcı değil) |
| 2.5 | Kontrol takılsın (çok yavaş ağ / kaynağı engelle) | 2,5 sn'de "Atla" çıkar, en geç 7 sn'de kapı kendiliğinden açılır |
| 2.6 | İndirmeyi başlat, **%40'ta uygulamayı kapat**, tekrar aç ve devam et | Kaldığı yerden sürer, **%0'a dönmez** |
| 2.7 | İndirme bitince | **Doğrudan kurulum ekranı** açılır — paylaşım sayfası DEĞİL |
| 2.8 | Kurulumu reddet, geri dön, düğmeye tekrar bas | Yeniden **indirmez**; kurulum anında açılır ("Kurulumu tekrar aç") |
| 2.9 | Ayarlardan "bilinmeyen kaynak" iznini **kapat**, güncelle | İzin ekranına götürür ve ne yapılacağını yazar; anlaşılmaz ret vermez |
| 2.10 | Kapıda indirmeye başla → "Şimdilik devam et" → banttan "Güncelle" | Bant **kaldığı yüzdeden** devam eder; ikinci indirme başlamaz |
| 2.11 | İndirme sırasında mobil veri ↔ Wi-Fi geçişi yap | İndirme ya sürer ya kaldığı yerden toparlar; bozuk paket kurulmaya çalışılmaz |
| 2.12 | İndirme sırasında telefonu kilitle, 5 dk bekle, aç | İndirme durmaz (arka planda tamamlanır) |
| 2.13 | Telefonun deposunu neredeyse doldur, güncelle | Anlaşılır hata; yarım paket kurulmaya çalışılmaz |
| 2.14 | Kurulum bitince uygulamayı aç | Yeni sürüm numarası görünür; oturum ve ayarlar korunur |

### 2B. Windows client

| # | Senaryo | Beklenen |
|---|---|---|
| 2.15 | İnternetsiz makinede client'ı aç | "Hazır!" ekranı **anında** çizilir, "Başlat" hemen açılır |
| 2.16 | Güncelleme varken aç | "Başlat" beklemede kalır, üstünde "Güncelleme kontrol ediliyor…" yazar; kurulum bitince açılır |
| 2.17 | Client'ı **24 saatten uzun** açık bırak (klinik gerçeği) | Periyodik tur yeni sürümü fark eder ve bildirir; seansı kesmez |
| 2.18 | Güncelleme kurulurken **elektriği kes**, tekrar aç | Eski sürüm sağlam açılır (atomik takas + geri alma); tuğlalaşma yok |
| 2.19 | Client açıkken ikinci bir kopyasını başlat | İkinci pencere aynı ağaca yazmaya çalışmaz |
| 2.20 | Diski neredeyse doldur, güncelleme al | Disk kapısı uyarır; yarım indirme ağacı bozmaz |
| 2.21 | **Kur → kaldır → tekrar kur** (aynı makine) | Kalıntı süreç kalmaz (mosquitto/cloudflared), ikinci kurulum sorunsuz |
| 2.22 | Kaldırma sonrası hasta verisi | **Duruyor** (kasıtlı: kaldırma tıbbi veriyi silmez) |
| 2.23 | Seans sürerken uygulamayı **kaldırmayı** dene | Kaldırma önce bobinleri güvene alır (E-stop), sonra devam eder |

---

## Kademe 3 — AĞ VE BAĞLANTI (klinik gerçeği)

| # | Senaryo | Beklenen |
|---|---|---|
| 3.1 | Wi-Fi'yi kapat, 30 sn bekle, aç | Bağlantı kendiliğinden toparlar; elle yeniden başlatma gerekmez |
| 3.2 | Modemi yeniden başlat | Cihaz bulma (mDNS) tekrar çalışır |
| 3.3 | Modemde **istemci izolasyonu (AP Isolation)** açık | Mobil bunu tespit edip **sebebini** yazar; genel "bağlanamadı" demez |
| 3.4 | Telefonu farklı bir ağa al, **eşleştirme kodu** ile bağlan | Bağlanır; kod süresi dolmuşsa açıkça söyler |
| 3.5 | Uzaktan erişim tüneli koparken kullan | Durum "çevrimdışı" olur; sahte canlı değer gösterilmez |
| 3.6 | **İki telefon** aynı anda bağlan | İkisi de canlı veri görür; komutlar çakışmaz |
| 3.7 | Bilgisayarda birden fazla ağ arayüzü açıkken (Ethernet + Wi-Fi + hotspot) | Cihaz yine bulunur (çok-homed multicast) |
| 3.8 | Backend'i kapat, mobili kullanmayı dene | Anlaşılır hata; sonsuz dönen çark yok |
| 3.9 | Çok yavaş ağ (throttle) altında liste/geçmiş aç | Zaman aşımı mesajı gelir; ekran donmaz |
| 3.10 | **İnterneti kes, uygulamayı açık bırak** | Ana ekranda "İnternet yok — uzaktan erişim kapalı" rozeti **çıkar**; cihaz ağı/donanım **kırmızı olmaz** |
| 3.11 | 3.10'un devamı: interneti **geri ver**, ekranı izle | Rozet en geç ~1 dk içinde **kendiliğinden kaybolur**. ⚠️ Kalıyorsa bu 2026-09-12'de düzeltilen donmuş rozet hatasının nüksüdür |
| 3.12 | İnternet KAPALIYKEN "Sistem Durumu" kartına bak | "İnternet Bağlantısı" satırı **Kapalı** der. ⚠️ Yeşil "Aktif" diyorsa yalan-yeşil hatası geri gelmiştir |
| 3.13 | İnterneti kes ama hotspot açık kalsın | "Cihaz Köprüsü" Aktif kalır — internet yokluğu cihaz ağını düşürmez |
| 3.14 | Uygulamayı internet YOKKEN aç (baştan) | Rozet doğru (yok) başlar; internet gelince düzelir |
| 3.15 | Uygulamayı internet VARKEN aç (baştan) | Rozet **hiç çıkmaz**; yanlış alarm yok |
| 3.16 | Hotspot'u (PEMF-Gateway) kapat | "Kablosuz Bağlantı" Kapalı der; başka satırlar bundan etkilenmez |
| 3.17 | Backend ile arayüz arasındaki WS bağlantısını kes (backend'i 10 sn durdur) | Tüm durum satırları "Bilinmiyor"a düşer — **bayat yeşil kalmaz** |

---

## Kademe 4 — VERİ, AI, YETKİ

### 4A. Hasta verisi

| # | Senaryo | Beklenen |
|---|---|---|
| 4.1 | Hasta adında Türkçe karakter (`İhsan`, `Işık`, `Çağla`, `Ğ`) ara/kaydet/raporla | Arama ve sıralama doğru; kayıt bozulmaz |
| 4.2 | Çok uzun ad / not (500+ karakter), emoji | Kesilirse **belirtilir**; kayıt bozulmaz |
| 4.3 | Aynı hastayı iki cihazdan aynı anda düzenle | Son yazan kazanır ama diğer alanlar **kaybolmaz** |
| 4.4 | Makinenin saatini 1 gün geri al, seans yap, saati düzelt | Geçmiş sıralaması tutarlı kalır; kayıt kaybolmaz |
| 4.5 | Yaz saati geçişi civarında süre hesabı | Seans süresi doğru; negatif/atlamalı süre yok |
| 4.6 | Kurtarma kodu ile yedeği başka makinede aç | Açılır; kod yanlışsa anlaşılır hata |
| 4.7 | `mia` ve `MIA` adlı iki ayrı hasta oluştur | **Ayrı** hastalar olarak durur — Türkçe katlama ikisini birleştirmez |
| 4.8 | Hasta adını değiştir (ör. `Mia` → `MİA`), AI geçmişine bak | Eski analizler **kaybolmaz** (kimlik bağı; ad yedeği) |

### 4B. Toplu silme (yeni)

| # | Senaryo | Beklenen |
|---|---|---|
| 4.9 | Seans Geçmişi'nde birkaç kayıt seç, "Seçilenleri Sil" | Onay ister; yalnız seçilenler silinir |
| 4.10 | Seçim yaptıktan sonra **filtreyi değiştir** (seçili kayıtlar ekrandan çıksın), sil | Ekranda olmayan kayıt **silinmez**; "N kayıt ekranda değil" uyarısı çıkar |
| 4.11 | Hasta veritabanında toplu sil | Aynı davranış; hasta + arama dizini birlikte temizlenir |
| 4.12 | Toplu silme onayını iptal et | Hiçbir şey silinmez |
| 4.13 | Çok sayıda (100+) kayıt seçip sil | Ya hepsi silinir ya hiçbiri (yarım kalmaz); sınır aşılırsa açıkça söyler |

### 4C. Dışa aktarma ve rapor

| # | Senaryo | Beklenen |
|---|---|---|
| 4.14 | Seans geçmişini CSV indir, Excel'de aç | "Durum" sütunu **Türkçe** ("Tamamlandı", "Acil Durduruldu", "Donanım Reddetti") — İngilizce `completed` YOK |
| 4.15 | Türkçe karakterli hasta için seans PDF'i indir, aç | `ı ş ğ İ Ş Ğ` harfleri **doğru** basılır — siyah kutucuk YOK. Başlıklar/kalın yazılar dahil kontrol et |
| 4.16 | Kapsam "Benim Seanslarım" iken dışa aktar | Düğme "**Görünenleri** Excel/CSV İndir" der ve gerçekten yalnız görünenleri indirir |
| 4.17 | Kapsam "Tüm Klinik" iken dışa aktar | Düğme "**Tümünü** Excel/CSV İndir" der |
| 4.18 | AI analizi detayından "Sonucu paylaş (PDF)" | PDF açılır; sayısal detaylar ve hasta adı içinde |
| 4.19 | Masaüstünde indirme düğmesine bas | Dosya gerçekten kaydedilir ve **nereye kaydedildiği söylenir** — sessiz ölüm yok |

### 4D. AI

| # | Senaryo | Beklenen |
|---|---|---|
| 4.20 | **Boş/sessiz** ses kaydı analiz et | Reddedilir ve sebebi yazılır (sonuç uydurmaz) |
| 4.21 | Kedi olmayan ses (müzik, insan konuşması, gürültü) | Ya reddeder ya **düşük güven** uyarısı verir |
| 4.22 | Çok kısa (1 sn) kayıt | Anlaşılır ret |
| 4.23 | Kamera izni reddedilmişken analiz | İzin isteğine yönlendirir; çökmez |
| 4.24 | Karanlık / çok bulanık fotoğraf | Düşük güven ya da ret; kesin sonuç iddiası yok |
| 4.25 | AI servisi kapalıyken analiz | Zaman aşımı mesajı; sonsuz bekleme yok |
| 4.26 | Analiz sürerken ekrandan çık, geri gel | Ya sonuç durur ya temiz sıfırlanır; yarım sonuç gösterilmez |
| 4.27 | Analiz sonucunda **uzun bir metin** (kapanma metrikleri vb.) | Üç noktayla kesilen metne **dokun** → tamamı açılır, tekrar dokun → kapanır |
| 4.28 | Girdi fotoğrafını yükle, analiz et | Girdi fotoğrafı **kaybolmaz**; ileri/geri ile sonuç ve girdi arasında gezinilir |
| 4.29 | Sonuç görselini büyüt (zoom) | Yakınlaşır, okunur; tam ekranda da kapatma düğmesi hep görünür |
| 4.30 | Otomatik Mod ile seans öner | Literatürden öneri gelir; parametreler **düzenlenebilir**; "AI Modu" diye ikinci bir sekme YOK |

### 4E. Profiller ve sahiplik

| # | Senaryo | Beklenen |
|---|---|---|
| 4.31 | Üç profille de aç, kapalı rotalara URL/gezinme ile gitmeye çalış | Erişilemeyen rota panoya düşer |
| 4.32 | Ev sahibi (pet_owner) profiliyle tedavi başlatmayı dene | Mümkün olmaz (yalnız analiz) |
| 4.33 | Ev sahibi profiliyle aç | **"Ana Ekran" sekmesi YOK**; uygulama AI ekranında açılır (boş/erişilemez rotaya düşmez) |
| 4.34 | Operatör değiştir, hareketsiz bekle (kilit süresi) | Seans sürerken kilit **ertelenir**; seans yokken kilitlenir |
| 4.35 | **İki farklı e-posta** ile seans yap, sonra "Benim Seanslarım" filtresi | Her hekim yalnız kendi seanslarını görür |
| 4.36 | 4.35'in devamı: "Tüm Klinik" seç | İkisinin de seansları görünür |
| 4.37 | Otomatik (AI) seans yap, "Benim Seanslarım"a bak | Otonom seans da **sahipli** kaydedilir — herkesin listesinde çıkmaz |
| 4.38 | Ev sahibi profiliyle AI geçmişine bak | Yalnız **kendi** analizleri; başka hekimin analiz özeti görünmez |
| 4.39 | Hasta kartına bak | "Son analiz: …" özeti doğru hastaya ait |

---

## Kademe 5 — DAYANIKLILIK (sürüm turlarında)

| # | Senaryo | Beklenen |
|---|---|---|
| 5.1 | Arka arkaya 10 seans (mola vermeden) | Bellek/handle sızıntısı yok; 10. seans 1. kadar hızlı |
| 5.2 | Azami süreli tek seans, sonuna kadar | Otomatik kapanır, kayıt tam |
| 5.3 | Client 72 saat açık | Bellek şişmez, bağlantı canlı, güncelleme kontrolü çalışıyor |
| 5.4 | Mobil uygulamayı 24 saat arka planda bırak, geri dön | Yeniden bağlanır; bayat veriyi canlı gibi göstermez |
| 5.5 | Bobinlerin bir kısmını fiziksel olarak çıkar, seans dene | Eksik bobin **söylenir**; sessizce eksik tedavi verilmez |
| 5.6 | 500+ seans biriktikten sonra geçmiş/KPI ekranlarını aç | Liste ve grafikler makul sürede açılır; donma yok |
| 5.7 | Aynı anda 20+ AI analizi kuyruğa at | Ya sıraya alır ya sınırı söyler; çökmez |
| 5.8 | Uygulamayı 1 hafta hiç kapatmadan kullan (klinik gerçeği) | Oturum, bağlantı ve bildirimler sağlam kalır |

---

## Kademe 6 — MOBİL (ayrı ve geniş — bu katman en az bakılan)

> ⚠️ Mobil, masaüstüyle **aynı arayüz kodunu** çalıştırır ama kabuğu, izinleri, dosya yolu,
> klavyesi ve ağı farklıdır. Masaüstünde geçen bir senaryo burada geçmeyebilir; 2026-08-17
> hatası tam olarak böyle kaçmıştı. **iOS bugün EAS bulut derlemesiyle üretiliyor — elinizde
> iOS kurulumu yoksa 6.x'i Android'de koşun ve bunu bulguya yazın.**

### 6A. Kurulum, açılış, sürüm

| # | Senaryo | Beklenen |
|---|---|---|
| 6.1 | APK'yı temiz telefona kur, ilk açılış | Açılır; hangi izinleri neden istediği anlaşılır |
| 6.2 | Ayarlar → sürüm numarasına bak | Kurduğun APK'nın sürümüyle **aynı** |
| 6.3 | Uygulamayı kapat-aç 5 kez üst üste | Her seferinde aynı ekrana açılır; rastgele beyaz ekran yok |
| 6.4 | Telefonu yeniden başlat, uygulamayı aç | Oturum korunur (yeniden giriş istemez) |
| 6.5 | Uygulamayı **arka plandan öldür**, hemen aç | Bağlantı yeniden kurulur; "bağlanıyor" sonsuza kadar dönmez |

### 6B. Cihaz bulma ve eşleştirme

| # | Senaryo | Beklenen |
|---|---|---|
| 6.6 | Telefon ve cihaz **aynı Wi-Fi'da**, uygulamayı aç | Cihaz otomatik bulunur (elle IP girmek gerekmez) |
| 6.7 | Telefonu **PEMF-Gateway hotspot'una** bağla | Cihaz bulunur |
| 6.8 | Telefonu **mobil veriye** al (cihazla farklı ağ) | Eşleştirme kodu istenir; "bulunamadı" belirsizliği değil, **sebep** yazar |
| 6.9 | Yanlış eşleştirme kodu gir | "Kod yanlış" der — "cihaz kapalı" demez (sebepler karışmaz) |
| 6.10 | Süresi dolmuş kod gir | "Kodun süresi doldu" der |
| 6.11 | Cihaz kapalıyken doğru kod gir | "Cihaz çevrimdışı" der — "kod yanlış" demez |
| 6.12 | Bağlandıktan sonra telefonu uçak moduna al, 1 dk sonra geri getir | Kendiliğinden yeniden bağlanır |
| 6.13 | Cihazın IP'si değişsin (modemi yeniden başlat) | Uygulama yeni IP'yi bulur; elle müdahale gerekmez |

### 6C. Canlı veri ve güvenlik

| # | Senaryo | Beklenen |
|---|---|---|
| 6.14 | Masaüstünde seans başlat, telefonda izle | Süre/frekans/yoğunluk canlı akar; masaüstüyle **aynı** değerler |
| 6.15 | Telefonu 30 sn kilitle, aç | Değerler tazelenir; kilitlenmeden önceki donmuş değer "canlı" gösterilmez |
| 6.16 | Backend'i kapat, telefonda ekranı izle | "Çevrimdışı" olur; son değerler canlı gibi durmaz |
| 6.17 | Telefondan ACİL DURDUR (seans sürerken) | Bobinler durur; telefonda **onay** görünür |
| 6.18 | Telefondan ACİL DURDUR, ağ tam o anda kopsun | Başarısızlık **açıkça** yazılır; "durduruldu" yalanı YOK |
| 6.19 | İki telefondan aynı anda ACİL DURDUR | İkisi de çalışır; çakışma hatası yok |
| 6.20 | Telefondan seans başlatmayı dene (yetkili profil) | Ya başlar ya neden başlamadığını söyler |

### 6D. Ekran, klavye, erişilebilirlik

| # | Senaryo | Beklenen |
|---|---|---|
| 6.21 | Dar telefonda (≤375 px) her ekranı gez | Yatay kaydırma YOK; yazılar kesilmez |
| 6.22 | Telefonu **yatay** çevir | Kabuk ikon rayına geçer; alt bar ekranı yemez |
| 6.23 | Tablette dikey ve yatay | Düzen sığar; kartlar üst üste binmez |
| 6.24 | Sistem yazı tipi ölçeğini **en büyüğe** al | Yazılar büyür ama düzen bozulmaz (tavan %120) |
| 6.25 | Bir form alanına dokun (klavye açılsın) | **ACİL DURDUR klavyenin üstüne taşınır**, gizlenmez |
| 6.26 | Klavye açıkken "Kaydet"e bas | **Tek** dokunuşta çalışır (iki dokunuş gerekiyorsa bulgudur) |
| 6.27 | Çentikli telefonda üst/alt kenar | İçerik çentiğin altında kalmaz |
| 6.28 | Karanlık/aydınlık tema değiştir | Okunurluk her ikisinde de korunur |
| 6.29 | Küçük dokunma hedeflerini dene (ikon düğmeler) | Parmakla rahat basılır; yanlış düğmeye basılmaz |

### 6E. Mobilde dosya, kamera, mikrofon

| # | Senaryo | Beklenen |
|---|---|---|
| 6.30 | Telefonda CSV/PDF indir | **Paylaşım menüsü** açılır ve dosya gerçekten kaydedilebilir/gönderilebilir |
| 6.31 | 6.30'daki PDF'i telefonda aç | Türkçe harfler doğru; siyah kutucuk yok |
| 6.32 | Kamera iznini **reddet**, sonra analiz dene | İzin ekranına yönlendirir; çökmez |
| 6.33 | Kamerayla fotoğraf çek → analiz | Fotoğraf yüklenir, sonuç gelir, **girdi fotoğrafı kaybolmaz** |
| 6.34 | Galeriden çok büyük (12 MP+) fotoğraf seç | Yüklenir veya anlaşılır sınır mesajı; sessiz başarısızlık yok |
| 6.35 | Mikrofon iznini reddet, ses analizi dene | İzin isteğine yönlendirir; çökmez |
| 6.36 | Ses kaydı sırasında telefona çağrı gelsin | Kayıt temiz durur; bozuk dosya analize gitmez |
| 6.37 | Analiz sürerken uygulamayı arka plana at, geri gel | Sonuç ya durur ya temiz sıfırlanır; yarım sonuç gösterilmez |

### 6F. Mobil profil ve yetki

| # | Senaryo | Beklenen |
|---|---|---|
| 6.38 | Ev sahibi (pet_owner) profiliyle mobilde aç | "Ana Ekran" sekmesi YOK; AI ekranı açılır |
| 6.39 | Ev sahibi profiliyle kontrol/tedavi ekranına gitmeye zorla | Erişemez; rota panoya düşer, boş/yarım ekran açılmaz |
| 6.40 | Mobilde "Tüm Klinik" kapsamını seç (ev sahibi) | Kilitli/gizli — kendi verisi dışına çıkamaz |
| 6.41 | Mobilde çıkış yap | Yalnız **bu cihazın** oturumu kapanır; masaüstü oturumu düşmez |
| 6.42 | Mobilde bildirime dokun (uzun metinli) | Metnin tamamı açılır; "…" ile kesik kalmaz |

---

## Kademe 7 — BU TURUN DEĞİŞİKLİKLERİ (regresyon — bir kez tamamen koş)

> 2026-09-12'de kapatılan 14 sahip işi + 4 ev sahibi eklentisi + aynı gün ölçülerek bulunan
> 6 canlı hata. Bu bölüm "yeni bir şey bozuldu mu?" değil, **"istenen şey gerçekten oldu mu?"**
> sorusunu ölçer.

| # | Senaryo | Beklenen |
|---|---|---|
| 7.1 | Seans detayını aç | "Donanım: ESP" **yazmaz** (sökülü olduğu belirtilir); hayalet bobin 8 kaydı yok |
| 7.2 | Ana ekranda bobin sayacına bak | **7 bobin** üzerinden sayar (`x / 7`); sökülü ESP slotu kart olarak çizilmez |
| 7.3 | 7.2'nin karşıtı: ESP geri takılırsa | Slot 8 görünür olur ve payda kendiliğinden 8'e çıkar |
| 7.4 | Seans başlat, sol alt köşeye bak | Ayrı "ACİL DURDUR" kutusu **çıkmaz** (kontrol ekranının kendi düğmesi zaten var) |
| 7.5 | Kontrol ekranı ve Ana Ekran dışındaki bir sekmede seans sürerken | Global ACİL DURDUR **görünür** (kendi düğmesi olmayan ekranlarda korunmuş) |
| 7.6 | "Son 7 Gün" grafiğine bak | Eksen etiketleri tam sayı; değerler barların üstünde; toplam rozeti var |
| 7.7 | Ayarlar'da uzun bir bilgi değerine dokun | Tamamı açılır |
| 7.8 | AI Hub'da "kaldığın yerden devam" şeridine bak | Son analiz doğru hastayla eşleşir |
| 7.9 | AI geçmişinde takip grafiğine bak | Aynı modül + aynı metrik, ≥2 nokta; grafiğe alınmayanlar **söylenir** |
| 7.10 | Otomatik Mod'u kullan | Öneri gelir, parametre değiştirilebilir; "AI Modu" sekmesi yok |
| 7.11 | Seans başına paylaşım düğmesine bak | Tek düğme kaldı (PDF); ikiz "Raporu Paylaş" yok |
| 7.12 | Türkçe karakterli hasta için PDF üret (7.15 ile birlikte) | Kutucuk yok — **kalın ve italik** başlıklar dahil |

---

## Kademe 8 — BİLİNEN AÇIKLAR (bunlar "bulgu" değil; **doğrulanmış davranış** olmalı)

> Bu satırlar bilinçli sahip kararlarını ya da henüz kapanmamış işleri ölçer. Beklenen sonuç
> "sorun yok" değil, **"belgelenen davranışın aynısı"**. Farklıysa belge yanlıştır — o da bir bulgudur.

| # | Senaryo | Beklenen (belgelenen davranış) |
|---|---|---|
| 8.1 | Bobin 1-5'i uzun süre yüksek duty'de sür, sıcaklığı ölç | **Cihazda termal kesme YOK** (NTC derleme-kapılı). Yalnız süre sınırı ve operatör keser. ⚠️ Canlı üzerinde denemeyin — fantom/boş bobin |
| 8.2 | Bobin 6-7 sıcaklığına bak | Ölçülür ve **gösterilir**; otomatik kesme yok (sahip kararı) |
| 8.3 | Bobin 6-7 akım değerine bak | `0.0` gösterir — ACS712 taşınmadı (bilinçli). Sahte bir değer üretiliyorsa bulgudur |
| 8.4 | Ödeme/abonelik ekranlarını dene | Satış **kapalı** (FREE_MODE); jeton kapısı uykuda. Ücret istiyorsa bulgudur |
| 8.5 | Uzaktan erişim (tünel) ile bağlan | Çalışır; ⚠️ `resolve_device` tazelik SQL'i canlı Supabase'e uygulanmadıysa bayat cihaz görünebilir |
| 8.6 | Araştırma AI Pro (fantom/petri) sürüşünü dene | **Bayrak kapalı** — sürüş yok, yalnız görüntüleme. Bobin sürüyorsa bulgudur |
| 8.7 | Güncelleme/sürüm bandına bak | Yayın **donduruldu**: yeni sürüm gelmemeli |

---

## Bulgu kaydı

Bir senaryo beklenenden saparsa şunları yaz — düzeltme bunlar olmadan tahmine dönüşür:

- **Senaryo no** ve tam adımlar (kaçıncı denemede oldu, her seferinde mi?)
- **Ne bekliyordun / ne oldu**
- **Ekran görüntüsü / video** (özellikle mobil — 2026-08-17 hatası ekran görüntüsüyle çözüldü)
- **Sürümler**: client, mobil (Ayarlar → sürüm), backend
- **Ortam**: hangi ağ, hangi telefon/Android sürümü, donanım bağlı mıydı
- **Log**: client log dosyası, `adb logcat` (mobil), backend konsolu
