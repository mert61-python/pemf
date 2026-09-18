# PEMF Vet — Metin Kılavuzu (site + masaüstü uygulaması)

> **Kapsam:** Bu kılavuz `pemf-vet-web` (tanıtım sitesi) ve `launcher/app/ui/index.html`
> (hekimin her gün kullandığı masaüstü arayüzü) için birlikte geçerlidir — aynı kişi ikisini de
> okuyor, iki yüzeyin dili ayrışmamalı. Masaüstü tarafının kapısı:
> `tests/test_client_arayuz_sade_dil.py` (TR **ve** EN birlikte kilitli).

Hedef kitle **veteriner hekim / klinik sahibi**; yazılımcı değil. Bir metni yazarken ölçüt şu:
*kliniğe ilk kez giren bir hekim bu cümleyi okuyup ne yapacağını biliyor mu?*

Bu kılavuzun maddeleri `src/__tests__/sade-dil.test.ts` ve `src/__tests__/metin-guveni.test.ts`
ile **testle kilitlidir** — biri geri gelirse süit kırmızı yanar.

## 1. Ürünün adı

| Bağlam | Kullan | Kullanma |
|---|---|---|
| Buton, başlık, menü | **PEMF Vet** ("PEMF Vet'i İndir") | Client · İstemci · Launcher |
| Süreci anlatan yer (kurulum adımları, SSS) | **başlatıcı** (tek ad, küçük harf) | client · launcher · setup |
| SSS'te dosya adı sorulursa | `PEMFVetClient-Setup-…exe` | — |

> ⚠️ `CLIENT` **kod tanımlayıcısı** (config export'u) ve Windows'taki `PEMF Vet Client` kurulum
> adı DEĞİŞMEZ: kaldırma kayıt anahtarı, `AppData\Local\PEMF Vet Client` klasörü ve indirme
> adresleri ona bağlı. Değişen yalnız **ekranda görünen** metindir.

## 2. Jargon sözlüğü

| Yazma | Yaz |
|---|---|
| Real-time | Gerçek zamanlı / anında |
| işlem önceliği · kuyruk · kuyruksuz | yapay zekâ analiz hızı · kısa bekleme · anında |
| DB · KPI | hasta kayıtları · klinik istatistikleri |
| SLA | garantili yanıt süresi |
| kapalı-döngü | ölçümlere göre kendini ayarlayan |
| watchdog · güven-geçidi | otomatik süre sınırı · hedef kontrolü |
| SHA-256 doğrulanır | bütünlüğü otomatik doğrulanır |
| Dashboard | izleme paneli |
| next-next · setup | birkaç tıkla kurulur |
| delta güncelleme | yalnız değişen parçalar iner |
| SQLCipher · tünel | şifreli · şifreli bağlantı |
| lokalizasyon | konum |
| Ev Sahibi | **Evcil Hayvan Sahibi** (Türkçede "ev sahibi" = mülk sahibi) |
| AI (tek başına) | yapay zekâ (ürün adı `AI Pro` hariç) |

**Kısaltmalar:** bilimsel olanlar (FGS, KIRC, CKD, mT) kalabilir ama **aynı satırda Türkçe
açıklaması** bulunmalı — "Kedide yüz ifadesinden ağrı skoru (FGS)".

## 3. Tek terim kuralı

Aynı şeyi her sayfada aynı sözcükle anlat:

- satın alınan şey → **plan** (seviye · üyelik · lisans · katman ❌)
- kurulumda seçilen şey → **kurulum profili** (modül · mod · paket ❌)
- giriş bilgisi → **şifre** (parola ❌)
- yapay zekâ bölümü → **Yapay Zekâ Merkezi** (AI Hub · AI Tanı Modülleri ❌)

## 4. Hata mesajları

- Ham sağlayıcı metni (Supabase/iyzico) **asla** ekrana basılmaz → `src/lib/authHatalari.ts`.
- Mesaj **ne olduğunu + ne yapılacağını** söyler: "E-posta veya şifre hatalı. Şifrenizi
  hatırlamıyorsanız 'Şifremi unuttum' bağlantısını kullanın."
- Ortam değişkeni, alan kodu, HTTP durumu, yığın izi kullanıcıya **gösterilmez**.
- Tanınmayan hata **yutulmaz**: genel ama Türkçe bir karşılık + destek adresi.

## 5. Yolculuk kuralları

- **Her çıkmaz sokakta bir kapı olsun.** "Bize yazın / tekrar deneyin / yeniden başlatın" diyen
  her metin **tıklanabilir** bir bağlantı taşır (`mailto:` ya da `Link`). Kilit:
  `src/__tests__/yolculuk.test.ts`.
- **Buton, gittiği yeri söyler.** "İletişime Geçin" iletişime gider (SSS'e değil).
- **Karar sorusunun cevabı sitede olmalı.** Plan farkı, AI Pro'nun ne yaptığı, deneme sonu,
  iptal/iade, Araştırma profilinin kime gerektiği, telefon uygulamasının rolü → SSS'te.
- **Sayı verirken neyin sayısı olduğunu söyle.** İndirme kartında kurulum dosyası boyutu,
  disk gereksiniminde "profil sayısına göre değişir" notu.
- **Klinik riski olan özellik açıklanır.** AI Pro maddesi, seansı hekimin başlatıp durdurduğunu
  ve güvenlik kesmelerinin önceliğini açıkça yazar.

## 6. Diyalog ve veri dürüstlüğü

- **Tarayıcının `confirm`/`alert` kutuları kullanılmaz.** Para/abonelik gibi kritik adımlarda
  sitenin kendi diyalogu kullanılır; onay metni sonucu açıkça söyler.
- **Olmayan veri gösterilmez.** Abonelik yenileme tarihi (`current_period_end`) bu depoda hiçbir
  yol tarafından yazılmıyor → hesap menüsünde tarih/fatura gösterilmez. Satış açıldığında gerçek
  "Hesabım" sayfası ayrı iştir.
- **Sistemin gerçek çıktısı metinden silinmez.** KVKK belgesindeki `[REDACTED]` ibaresi yazılımın
  kayda birebir yazdığı değerdir; silmek belgeyi yanlış yapar — yapılacak şey açıklamaktır.
- **Kişisel veri istenen her alanın gerekçesi yazılır** (ör. TC Kimlik No → fatura/vergi mevzuatı).

## 7. Olgu kuralı (en önemlisi)

**Bir cümle güzel olabilir ama YANLIŞSA kusurdur.** Ürün hakkında bir iddia yazmadan önce koda
bakın; kod ile metin çelişirse kazanan koddur.

- **Sınır iddia etmeden önce ölçün.** "Telefon cihazı süremez" diye yazılmıştı; oysa mobil
  uygulama seans başlatıyor ve bobin ayarlıyor (`pf/src/screens/ControlScreen.tsx`,
  `components/domain/CoilParameterPanel.tsx`, `hooks/useSessionControl.ts`).
- **Tutulamayacak vaat verilmez.** "İptalden sonra dönem sonuna kadar erişim" vaadi
  `api/cancel.ts` ölçümüyle çürük (`current_period_end` hiç yazılmıyor).
- **İndirilemeyen platform "destekleniyor" diye listelenmez** (`ready:false` → "yakında").
- **Metinden çıkarılan iddia SİMGEDE de durmaz** (Bluetooth logosu ↔ üründe BLE yok).
- **Kaldırılan iddianın ALANINI da kaldırın.** "İşlem önceliği / kuyrukta bekleme" vaadi
  `config.ts`ten silinmişti ama `Plan.realtime` ve `Plan.queue` ALANLARI kalmıştı; sayfalar onları
  yeniden vaade çevirdi (fiyat sayfası hero'su, ana sayfa plan kutusu, ödeme sayfası rozeti —
  **üçü birden** nüksetti). Veri modelinde duran bir kavram, metinden silinse bile geri gelir.
- **Aynı sayıyı iki yere yazmayın.** Fiyat/eşik/sınır tek kaynaktan gelmeli; SSS'deki "ayda 340
  analizden sonra Pro ucuz" cümlesi bile **hesaplanarak** test ediliyor (₺990 ÷ ₺2,90), elle
  yazılmıyor. Karşılaştırma tablosunun sütunları `PLANS`ten türer — gömülü dizi değil.
- **Aylık ücret VARSAYMAYIN.** `monthly ?? 0` kalıbı, aylık ücreti olmayan planı "₺0/ay" gösterir.
  Fiyat metni tek yerden: `src/lib/planFiyat.ts`.
- Kilit: `src/__tests__/dogruluk.test.ts`, `src/__tests__/kullandikca-ode.test.ts`.

## 8. Yayın öncesi kontrol

- [ ] `npm test` (metin kapıları dahil) yeşil
- [ ] Yasal sayfalarda iç/taslak notu yok
- [ ] Fiyat gösterimi `FREE_MODE` ile tutarlı (ücretsiz dönemde fiyat yazılmaz)
- [ ] Sürüm numaraları tek şema; telefon uygulamasının ayrı numarası açıklanmış
- [ ] Yeni metinde Türkçe karakterler tam (ASCII yazım yok)
- [ ] Yeni plan eklendiyse: `COMPARE` her satırda o tier'e değer veriyor (derleyici zorlar),
      kart ızgarası sütun sayısı yetiyor, `planFiyatGorunumu` "₺0" üretmiyor
- [ ] ⚠️ `FREE_MODE=true` ve `PEMF_JETON_ENFORCED` kapalı — **satışı açma kararı sahibindir**
      (sahip 2026-08-20: "henüz aktif etme, altyapı hazır şekilde kalsın")
