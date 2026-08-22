# Saha Test Listesi — elle koşulacak senaryolar

Otomatik süitler (pytest ~1080 · jest 431 · vitest 52 · cargo) **mutlu yolu** ve kod
düzeyindeki değişmezleri koruyor. Bu liste onların yapısal olarak göremediği sınıfı hedefler:
gerçek donanım, gerçek işletim sistemi, gerçek kullanıcı davranışı.

> Bunun neden gerektiğinin kanıtı: 2026-08-17'de sahada yakalanan "indirme bitince paylaşım
> ekranı açılıyor" hatası. Kod okununca kurulum açılıyormuş gibi duruyordu; kullanılan API'nin
> o ekranı **hiçbir zaman** sunamayacağı ancak cihazda görülünce anlaşıldı. Hiçbir statik
> denetim bunu bulamazdı.

**Nasıl kullanılır:** Kademe 1 her yayında koşulur. Kademe 2 güncelleme/kurulum kodu her
değiştiğinde. Kademe 3–5 sürüm turlarında ya da ilgili alan değiştiğinde.
Her satırda **beklenen** yazıyor; farklı bir şey olursa o bir bulgudur.

---

## Kademe 1 — HASTA GÜVENLİĞİ (her yayında, istisnasız)

Bu bölümdeki her başarısızlık yayını durdurur.

| # | Senaryo | Beklenen |
|---|---|---|
| 1.1 | Seans sürerken uygulamayı normal yoldan kapat | Bobinler **kapanmadan önce** durur; kayıt tutarlı kapanır |
| 1.2 | Seans sürerken client'ı Görev Yöneticisi'nden **öldür** | Bobinler durur (kill öncesi durdurma yolu çalışır) |
| 1.3 | Seans sürerken makinenin **fişini çek**, tekrar aç | Açılışta bobinler kapalı başlar; yarım seans "kesildi" olarak görünür, geçmişi bozmaz |
| 1.4 | Seans sürerken STM/USB kablosunu çek | Arayüz bağlantı kaybını **söyler**; sahte "çalışıyor" göstergesi kalmaz |
| 1.5 | Seans sürerken makineyi uyku moduna al, uyandır | Ya seans güvenli durdurulmuş ya da tutarlı sürüyor; "hayalet seans" olmaz |
| 1.6 | Mobilden **ACİL DURDUR** — cihazla aynı Wi-Fi'da | Bobinler durur, telefon onayı görür |
| 1.7 | Mobilden ACİL DURDUR — telefon **uçak modunda** | Komut gönderilemediği **açıkça** yazılır; "durduruldu" yalanı YOK |
| 1.8 | ACİL DURDUR sonrası yeni seans başlat | Temiz başlar; önceki seansın parametreleri sızmaz |
| 1.9 | Seans sürerken mobilde güncelleme çıksın (manifest'i geçici yükselt) | Güncelleme bandı **gösterilmez**; operatörün ekranı bölünmez |
| 1.10 | Seans sürerken profil değiştirmeyi / çıkış yapmayı dene | Önce onay + durdurma istenir; sessizce kesilmez |

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

### 4B. AI

| # | Senaryo | Beklenen |
|---|---|---|
| 4.7 | **Boş/sessiz** ses kaydı analiz et | Reddedilir ve sebebi yazılır (sonuç uydurmaz) |
| 4.8 | Kedi olmayan ses (müzik, insan konuşması, gürültü) | Ya reddeder ya **düşük güven** uyarısı verir |
| 4.9 | Çok kısa (1 sn) kayıt | Anlaşılır ret |
| 4.10 | Kamera izni reddedilmişken analiz | İzin isteğine yönlendirir; çökmez |
| 4.11 | Karanlık / çok bulanık fotoğraf | Düşük güven ya da ret; kesin sonuç iddiası yok |
| 4.12 | AI servisi kapalıyken analiz | Zaman aşımı mesajı; sonsuz bekleme yok |
| 4.13 | Analiz sürerken ekrandan çık, geri gel | Ya sonuç durur ya temiz sıfırlanır; yarım sonuç gösterilmez |

### 4C. Profiller

| # | Senaryo | Beklenen |
|---|---|---|
| 4.14 | Üç profille de aç, kapalı rotalara URL/gezinme ile gitmeye çalış | Erişilemeyen rota panoya düşer |
| 4.15 | Ev sahibi (pet_owner) profiliyle tedavi başlatmayı dene | Mümkün olmaz (yalnız analiz) |
| 4.16 | Operatör değiştir, hareketsiz bekle (kilit süresi) | Seans sürerken kilit **ertelenir**; seans yokken kilitlenir |

---

## Kademe 5 — DAYANIKLILIK (sürüm turlarında)

| # | Senaryo | Beklenen |
|---|---|---|
| 5.1 | Arka arkaya 10 seans (mola vermeden) | Bellek/handle sızıntısı yok; 10. seans 1. kadar hızlı |
| 5.2 | Azami süreli tek seans, sonuna kadar | Otomatik kapanır, kayıt tam |
| 5.3 | Client 72 saat açık | Bellek şişmez, bağlantı canlı, güncelleme kontrolü çalışıyor |
| 5.4 | Mobil uygulamayı 24 saat arka planda bırak, geri dön | Yeniden bağlanır; bayat veriyi canlı gibi göstermez |
| 5.5 | Bobinlerin bir kısmını fiziksel olarak çıkar, seans dene | Eksik bobin **söylenir**; sessizce eksik tedavi verilmez |

---

## Bulgu kaydı

Bir senaryo beklenenden saparsa şunları yaz — düzeltme bunlar olmadan tahmine dönüşür:

- **Senaryo no** ve tam adımlar (kaçıncı denemede oldu, her seferinde mi?)
- **Ne bekliyordun / ne oldu**
- **Ekran görüntüsü / video** (özellikle mobil — 2026-08-17 hatası ekran görüntüsüyle çözüldü)
- **Sürümler**: client, mobil (Ayarlar → sürüm), backend
- **Ortam**: hangi ağ, hangi telefon/Android sürümü, donanım bağlı mıydı
- **Log**: client log dosyası, `adb logcat` (mobil), backend konsolu
