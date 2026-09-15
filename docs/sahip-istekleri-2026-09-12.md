# Sahip İstekleri — 2026-09-12

**Durum:** Tamamlandı (kod + kapı testleri + mutasyon kanıtı) · **Yayın:** YAPILMADI (yayın durdurulmuş)

Sahibin bu turda tek tek bildirdiği 14 iş ve bunları yaparken **ölçerek bulunan 3 canlı hata**.

---

## İstenen işler

| # | İstek | Ne yapıldı | Kapı |
|---|---|---|---|
| 1 | "Exel/CSV indirin başına tamamını kelimesini ekle" | "Tümünü Excel/CSV İndir" | — (salt metin) |
| 2 | "csv de tamamlandı yazmalı, ingilizce yazıyor completed" | Durum sütunu `durum_etiketi()` ile Türkçe; sözlük **tek kaynak** (`utils/seans_durum.py`) ve TS haritasıyla kilitli | `test_seans_durum_etiketi.py` (5) |
| 3 | "kaydedilen pdf ler için karakter hatası, siyah kutucuk ı harflerine" | 4 yüzlü Unicode yazı tipi ailesi + stil sayfasındaki **her** Type1 metin stili çevrildi | `test_pdf_turkce_karakter.py` (6) |
| 4 | "paylaşım seçeneği ve pdf butonu aynı işi yapıyor, birini kaldır" | Paylaş ikonu kaldırıldı (mobilde işlev kaybı yok — tek düğme orada paylaşım sayfasını açar) | — |
| 5 | "toplu sil seçeneği eksik" + "hasta veri tabanında da" | İki ekranda seçim kipi + **atomik** toplu silme uçları | `test_toplu_silme.py` (14) · `useCokluSecim.test.tsx` (9) |
| 6 | "donanım eps kalmış ve bobin 8 görünüyor, 7 bobinli sistem" | Kaynak düzeltildi (aşağıda H3); eski kayıtlar **silinmedi**, "ESP (sökülü)" diye etiketlendi | `test_sahte_basarili_seans.py` §4 |
| 7 | "klinik ve benim ayrımı düzgün çalışıyor mu incele" | Denetim yapıldı → H1 bulundu ve düzeltildi; kopya kapsam mantığı tek kaynağa alındı | `test_kapsam_sahipligi.py` (8) |
| 8 | "ai modu ve otomatik mod aynı prensiple çalışıyor, otomatiği tut" | "AI Modu" sekmesi kaldırıldı (ölçüldü: **aynı uç, aynı kaynak**) | `dozKaynagiRozeti.test.tsx` (6) |
| 9 | "bildirim sığmayınca üç noktadan sonrasını okuyamıyor" | `GenisletilebilirMetin` — dokununca tam metin | `GenisletilebilirMetin.test.tsx` (9) |
| 10 | "sol altta çıkan acil durdurma kutusunu kaldır" | **Kısmen**: kendi durdurması olan ekranlarda (Kontrol · Ana Ekran) gizlendi; diğer 8 rotada bırakıldı (orada tek kontrol) | `globalAcilDurdurKapsami.test.tsx` (3) |
| 11 | "komut gitmemesine rağmen seans başlıyormuş gibi devam ediyor" | **En ağır iş** — aşağıda H2 | `test_sahte_basarili_seans.py` (15) |
| 12 | "bu grafiği daha belirgin ve güzel yap" | Ondalıklı eksen düzeltildi + çubuklar belirginleşti + değerler çubuk üstünde | `kpiGrafik.test.ts` (7) · `test_kpi_grafik_kapisi.py` (4) |
| 13 | "ai analiz detaylarında yine üç nokta sorunu" | İş 9 ile **aynı bileşen** (ayrı çözüm yazılmadı) | yukarıdaki |
| 14 | "evcil hayvan modunda ana ekran tabına gerek yok" | `pet_owner`dan kaldırıldı; açılış rotası **türetiliyor** (boş ekran tuzağı) | `access.test.ts` (13) |

---

## Ölçerek bulunan hatalar (istenmemişti)

### H1 — Otonom seanslar SAHİPSİZ kaydediliyordu
`start_ai_session` DB satırını `operator_email` yazmadan açıyordu. Arayüzün kuralı
"sahipsiz = benim" olduğu için **her AI seansı kliniğin HER hekimine** "Benim Seanslarım"da
görünüyordu — yani sahibin sorduğu ayrım AI tarafında fiilen yoktu.

Sahip artık AI Pro'da **onay mühründen** (öneriyi onaylayan hekim), AI (Auto)'da
sunucuda çözümlenmiş kimlikten gelir.

### H2 — `/session/start`, `update_coil`'in dönüşünü HİÇ okumuyordu
Sahibin bildirdiği CRC vakası bunun **özel bir hâliydi**. Genel hâli: hiçbir bobin komutu
kabul etmese bile (kart kopuk · firmware uyuşmaz · parametre geçersiz) seans "başladı"
sayılıyor, sayaç işliyor, koşu satırları TAM SÜREYLE yazılıyor ve geçmişe **"Tamamlandı"**
düşüyordu. Tıbbi kayıt, hiç uygulanmamış bir tedaviyi uygulanmış olarak belgeliyordu.

Tekil bobin yolu bunu 2026-08-20'de zaten düzeltmişti; **seans yolu dışarıda kalmıştı**
("kısmi düzeltme, düzeltilmemiş demektir").

Düzeltme üç katmanlı:
1. Kabul edilen bobin sayılır; hiçbiri kabul etmezse seans **geri alınır** ve
   `HARDWARE_REJECTED` ("Donanım Reddetti") diye mühürlenir — "Tamamlandı" DEĞİL.
2. Kart sistematik reddediyorken (ard arda ≥3 NACK, arada kabul yok) seans **hiç başlamaz**;
   operatöre reflash talimatı verilir.
3. Seans ortasında red başlarsa seans **durdurulur** (`watchdog_timeout` dalıyla aynı ilke).

⚠️ Tek NACK hat gürültüsü sayılır ve seansı engellemez — aksi, sağlam kartta tedaviyi
bloke etmek olurdu (karşıt kanıt testi mevcut).

### H3 — Her seans HAYALET bir bobin-8 / ESP kaydı yazıyordu
`_mqtt_publish` ESP kapalıyken hiç yayınlamıyordu (doğru), ama seans yolundaki ESP döngüsü
`_begin_coil_run`'ı **koşulsuz** çağırıyordu. Bobin kimliği verilmeyen seans `range(1, 9)`'a
düştüğü için bu **varsayılan** yoldu: her seans, ortada o donanım yokken geçmişe
"46 sn · 100 Hz · ESP" satırı bırakıyordu. Sahibin gördüğü "bobin 8" satırlarının kaynağı budur.

ESP kodu **silinmedi**, yalnız kapılandı: `PEMF_ESP_ENABLED=1` ile eski davranış bütünüyle döner.

---

## Bilerek alınan ödünçler

- **İş 10:** Kontrol ekranındaki durdurma düğmeleri sayfa içindedir; uzun listede aşağı
  kaydırınca ekrandan çıkabilir. Kayan düğme tam da bunu çözmek için eklenmişti. Sahibin
  isteği fazlalığı gidermek olduğu için ödünç alındı. Kaydırınca da erişim istenirse çözüm,
  Kontrol ekranındaki düğmeyi sabitlemektir.
- **İş 6:** Eski ESP/bobin-8 kayıtları **gizlenmedi**. Tedavi geçmişi tıbbi kayıttır;
  geriye dönük silmek/saklamak "dün 8 satır vardı, bugün 7" durumunu üretirdi. Bunun yerine
  satır soluklaştırıldı, "ESP (sökülü)" etiketlendi ve seansın altına bir kez açıklama konuldu.

---

## Yayın notu

Yayın **DURDURULMUŞ** durumda (sahada tek makine). Bu turda manifest/release koşturulmadı.

---

## Süit etkisi (dürüst kayıt)

Sahte-başarılı seans düzeltmesi **16 mevcut testi kırdı**. Sebep ölçüldü: o testler
STM donanımı gerektirmesin diye **ESP-only bobinlerle** (6-8) seans açıyordu. ESP alt sistemi
kapalı olduğundan `/session/start` artık o bobinleri kapsamdan çıkarıyor ve "hiçbir bobin
sürülmedi" diye reddediyor.

⚠️ **Davranış geri alınmadı.** Testler, deponun kendi kuralına göre düzeltildi: ESP kodu
silinmez, testler `PEMF_ESP_ENABLED=1` ile koşmaya devam eder
(bkz. `test_internetsiz_ve_esp_kapali.py::test_KRITIK_bayrakla_ESP_GERI_GELIR`).
Bayrak şu dosyaların kurulumuna eklendi:

- `test_esp_freq_clamp.py` · `test_nack_gorunurlugu.py` · `test_kalan_regression_gaps.py`
- `test_session_lifecycle.py` · `test_operator_identity_server_side.py` · `test_treatment_persistence.py`

Ayrıca geçen turun tam-ekran yazımından kalan **iki bayat kırmızı** bu turda bulundu ve
kapatıldı (o turda backend süiti yeniden koşulmamıştı):

- `test_ai_gorsel_sahne_capalari.py` — `kameraKutusu(` sayacı 1 → 2 (tam ekran AYRI bir çizim
  yüzeyi; işaret kayması riski `ustKatman?.( == 1` kapısıyla karşılanıyor)
- `test_modal_kaydirilabilir_kapisi.py` — tam-ekran görüntüleyici için üçüncü sözleşme
  (kaydırma yerine pan/zoom + SABİT kapat denetimi), bedeli iki kapıyla ödendi

## Kapı sayıları

| Dosya | Test | Mutasyon |
|---|---|---|
| `test_seans_durum_etiketi.py` | 5 | 5/5 KIRMIZI |
| `test_pdf_turkce_karakter.py` | 6 | 4/4 |
| `test_toplu_silme.py` | 14 | 8/8 |
| `test_sahte_basarili_seans.py` | 15 | 13/13 |
| `test_kapsam_sahipligi.py` | 8 | 8/8 |
| `test_kpi_grafik_kapisi.py` | 4 | 4/4 |
| `useCokluSecim.test.tsx` | 9 | 4/4 |
| `GenisletilebilirMetin.test.tsx` | 9 | 6/6 |
| `globalAcilDurdurKapsami.test.tsx` | 3 | 3/3 |
| `kpiGrafik.test.ts` | 7 | 3/3 |
| `dozKaynagiRozeti.test.tsx` (+3) | 6 | 4/4 |
| `access.test.ts` (+3) | 13 | 3/3 |

## Yerel kurulum notu

⚠️ **PAKET DOĞRULAMASINDA HAM ARAMA YAPMAYIN.** Paketleyici Türkçe harfleri KARIŞIK yazıyor:
aynı dosyada bazı dizgiler ham UTF-8, bazıları `\uXXXX`, bazıları `\xNN`
(ölçüldü: `ESP (s\xf6k\xfcl\xfc)` ile `sens\xf6r\xfc` yan yana). Tek biçimde arama SAHTE "YOK"
üretir — geçen turda da aynı tuzağa düşüldü. Doğrulayıcı: `scratchpad/paket_dogrula.py`
(iki kaçış biçimini de çözer).

---

## Test ederken ne göreceksiniz

**Seans Geçmişi**
- Başlıkta "Seç" düğmesi → kartlarda onay kutusu, üstte "N kayıt seçildi · Tümünü Seç · Sil"
- Seçtikten sonra aramayı/kapsamı değiştirirseniz, ekrandan çıkan kayıtlar seçimden DÜŞER
  (göremediğiniz bir kayıt silinemez)
- Kart başına tek "PDF" düğmesi (paylaş ikonu kalktı)
- "Tümünü Excel/CSV İndir" → Durum sütunu Türkçe

**Hastalar**
- "Seç" düğmesi → `User` ikonunun yerine onay kutusu geçer (satır kaymaz)
- "Tümünü Sil" (yalnız veteriner) ile karıştırmayın: toplu sil YALNIZ seçtiklerinizi siler

**Kontrol**
- "AI Modu" sekmesi YOK. Otomatik'te hedefe tıklayın → literatür önerisi alanlara yazılır,
  isterseniz üzerine yazın → "Otomatik Seansı Başlat"
- Sol alttaki kayan ACİL DURDUR kutusu Kontrol ve Ana Ekran'da GÖRÜNMEZ; Akıllı Teşhis,
  Ayarlar, Geçmiş gibi ekranlarda görünmeye DEVAM EDER (oralarda tek durdurma kontrolü)

**Firmware uyuşmazlığı denemesi (İş 11)**
- Kart CRC reddediyorken "Başlat" → seans BAŞLAMAZ, ekranda reflash talimatı çıkar
- Seans sırasında red başlarsa seans durdurulur ve geçmişe **"Donanım Reddetti"** yazılır
  (eskiden "Tamamlandı" yazıyordu)

**Bildirimler / AI detayları**
- Uzun metinlerde "▾ Tümünü gör" → dokununca tamamı açılır, "▴ Daha az" ile kapanır

**Raporlar**
- "Son 7 Gün" grafiğinde y ekseni TAM SAYI, çubuklar kalın ve değerler çubuk üstünde,
  başlıkta "Toplam N" rozeti

**Evcil hayvan modu**
- "Ana Ekran" sekmesi YOK; uygulama doğrudan Akıllı Teşhis ile açılır

---

# İKİNCİ GEÇİŞ — denetim + ev sahibi eklentileri (aynı gün)

Sahip: "14 işin hepsini tekrar kontrol et. eksik veya hata varsa düzeltmelerinde bul ve düzelt.
2. olarak 4 öneri) hepsini yap pet owner için. yayın durdurmaya devam yapmicaz yayın."

## Denetimde bulunan 3 hata (kendi düzeltmelerimde)

### D1 — "Tümünü Excel/CSV İndir" YALAN SÖYLÜYORDU
Sahibin istediği "tamamını" öneki eklendi ama varsayılan kapsam **"Benim Seanslarım"**
olduğundan düğme aslında yalnız GÖRÜNENLERİ indiriyordu. (Aynı yanlış "Tümünü PDF İndir"de
zaten vardı — kod yorumu bile "EKRANDA GÖRÜNEN kayıtları verir" diyor.) 200 seanslık bir
klinikte operatör "Tümünü" yazan düğmeye basıp 12 kayıtlık dosya alıyor ve fark etmiyordu.

Etiket artık kapsamı izler: `kapsamDaraltilmis ? "Görünenleri" : "Tümünü"` — ve kural
`downloadCsv` içindekiyle AYNI KAYNAKTAN gelir (ayrışırsa etiket bir şey der, indirme başka
şey yapar). Düzeltme PDF düğmesine de uygulandı.

### D2 — Kapsam kuralının ÜÇÜNCÜ kopyası
İlk turda `PatientScreen`in kopyası tek kaynağa alınmıştı; `AiHistoryScreen`deki **üçüncü
kopya** atlanmıştı. O da `patientScope.inScope`a bağlandı ve kapı artık üç yüzeyi de ölçüyor.

### D3 — AI yolları da sahte "başarılı" seans üretiyordu
İş 11 manuel seans yolunu düzeltmişti; **AI (Auto)** yolu `start_all_coils`in dönüşünü
okumuyordu (STM kopukken `False` döner). Seans `_active_session`a yazılıyor, DB satırı
açılıyor, "AI (Auto)" canlı durumu yayınlanıyordu — hiçbir bobin enerjilenmemişken.
Artık red hâlinde seans geri alınır. Ayrıca **AI Pro** başlatmaya da firmware-reddi kapısı
eklendi (manuel yolla aynı 409 + reflash mesajı).

## Küçük iyileştirmeler
- **İş 5:** "Tümünü Seç" yalnız EKRANDAKİLERİ seçer (doğru — görmediğin kayıt silinemez), ama
  adı yanıltıyordu. Şerit artık "N kayıt ekranda değil — seçilmez" diyor.
- **İş 9/13:** genişletilebilir metin iki yere daha uygulandı — **seans detayı özet değerleri**
  ve **Ayarlar'daki bilgi değerleri** (dosya yolları, cihaz kimliği: kesilen kısım tam da
  işe yarayan kısımdı).

---

## Ev sahibi eklentileri (4 öneri — hepsi yapıldı)

| # | Öneri | Nerede | Kapı |
|---|---|---|---|
| 1 | Hasta kartında **son analiz** özeti | Hastalar | `petOwnerEklentileri.test.ts` |
| 2 | **"Kaldığın yerden"** şeridi | Akıllı Teşhis (ev sahibi) | aynı dosya (aynı hesap) |
| 3 | Analiz sonucunu **PDF olarak paylaş** | AI Geçmişi + yeni uç | `test_ai_analiz_pdf.py` (15) |
| 4 | **Takip grafiği** (aynı hayvan, zaman içinde) | AI Geçmişi | `petOwnerEklentileri.test.ts` |

**Yeni uç:** `GET /api/ai/log/{analiz_id}/pdf` — seans raporlarıyla AYNI desen
(`kaydet=1` masaüstüne yazar, geçici PII PDF'i silinir).

⚠️ **Tasarım kararları:**
- **Yeni backend YOK** (3 hariç): `/api/ai/log` zaten hasta adı + tarih + özet döndürüyordu.
- **Takip grafiği yalnız TEK MODÜL + TEK ÖLÇÜT:** "yara kapanma %42" ile "böbrek sınıfı 3"ü
  aynı eksene dizmek bilgi değil gürültü olurdu. Dışarıda kalanlar SAYILARAK söylenir.
- **Tek nokta çizilmez:** iki ölçümden azı "eğilim" değildir.
- **Grafik SVG değil düz `View`:** yalnız bir mini-eğilim için grafik kütüphanesi çekmek
  bu kartın hak ettiğinden fazlasıydı.
- **PDF'e base64 görseller girmez:** 40 KB'lık dizgiyi "açıklama" diye yazdırmak raporu
  doğduğu anda kullanılamaz kılardı.

⚠️ **BİLİNEN SINIRLAMA:** son-analiz eşlemesi hasta **ADIYLA** yapılır — `ai_analyses`
tablosunda hasta KİMLİĞİ yok. Aynı adlı iki hayvanda analizler karışır. Kimliğe geçmek
backend + migrasyon işidir.

## Kendi kodumda testin yakaladığı hata
`adAnahtari` ilk sürümünde Türkçe katlamayı KENDİM yazdım (`toLocaleUpperCase("tr")`).
Test "mia"/"MIA" beklentimin yanlış olduğunu gösterdi: Türkçe'de "MIA" → "mıa" (noktasız),
**farklı bir isimdir**. Kod deponun tek-kaynak katlayıcısına (`aramaNormalize`) bağlandı ve
kapı artık çıktıyı onunla BİREBİR kıyaslıyor — kendi başına yazılmış başka bir katlama
(mutasyonla ölçüldü: yukarıdaki eşitlikleri O DA sağlıyordu) artık kırmızı verir.

---

# ÜÇÜNCÜ GEÇİŞ — AI analizi ↔ hasta KİMLİĞİ bağı

Sahip: "al." (bir önceki turda bildirilen sınırlamayı sıradaki iş olarak almak)

## Ne bozuktu

`ai_analyses` hastaya **yalnız ADLA** bağlıydı. Üç ayrı kırılganlığı vardı:

1. **Aynı adlı iki hayvan** — "Mia" adlı iki kedinin analizleri karışıyordu.
2. **Ad değişikliği** — hasta kaydında ad düzeltilince eski analizler kopuyordu.
3. **PII maskelemesi** — `PEMF_MASK_HISTORY_PII=1` açıkken ad `[SIFRELENMEMIS-DB]` yazılır →
   TÜM analizler aynı "ada" düşer ve eşleme **bütünüyle** çöker. (Bu üçüncüsü denetim
   sırasında bulundu; ilk iki maddeden daha sessiz ve daha yıkıcı.)

`patient_uuid` PII **değildir** (opak kimlik) → maskelenmez, şifrelemeden bağımsız çalışır.

## Ne yapıldı

| Katman | Değişiklik |
|---|---|
| Şema | `ai_analyses.patient_uuid` kolonu + indeks (idempotent `_safe_add_column`) |
| Yazma | `add_ai_analysis(..., patient_uuid=)` — maskelenmez |
| Okuma | `get_ai_analyses(..., patient_uuid=)`; ad ile **VEYA** bağlanır |
| Uç | `GET /api/ai/log?patient_id=…` · `POST /api/ai/log` gövdesinde `patient_id` |
| Taşıma | `ai_analiz_kimliklerini_doldur(ad_kimlik)` + tek-seferlik tetikleyici |
| Arayüz | `logAiResult` kimliği gönderir; eşleme **önce kimlik, sonra ad** |

## ⚠️ Taşımanın asıl kuralı — belirsiz adı TAHMİN ETME

Geri doldurma **yalnız adı TEK bir hastaya çözülen** kayıtlara kimlik yazar. Aynı ada sahip
iki hayvan varsa o ad haritaya hiç konmaz; analizler kimliksiz kalır ve eskisi gibi ada
bağlı çalışır.

Yanlış kimlik yazmak, taşımanın çözmeye çalıştığı sorunu **kalıcı** hâle getirirdi: bir
hayvanın analizi başka bir hayvanın kaydına gömülür ve ad belirsizliğinin aksine bu geri
alınamazdı (ad hâlâ orada ama kimlik artık "kesin" görünür).

## ⚠️ Geriye uyumluluk — ad yedeği KALDIRILAMAZ

- Kimlik göndermeyen eski istemcide kayıt **düşmez**, ada bağlı çalışır.
- Sorgu kimlik **VE** adı VEYA ile bağlar → taşıma günü geçmiş ikiye bölünmüş görünmez.
- Eşlemede ad yedeği kaldırılırsa, taşımanın bilerek kimliksiz bıraktığı kayıtlar
  ekrandan **sessizce kaybolur**. Kapı bunu kilitler.

## Dürüst not — mutasyonda yeşil kalan bir koruma

`UPDATE ... AND COALESCE(patient_uuid,'') = ''` koşulu tek başına ölçülemiyor: yukarıdaki
`SELECT` zaten yalnız boş kimlikli satırları getiriyor. Koşul yine duruyor çünkü **iki
backend süreci** aynı DB'yi paylaşırsa (süreç-içi kilit onları kapsamaz) araya giren bir
yazıcının kimliğini ezmek, elle yapılmış bir düzeltmeyi geri almak olurdu. Kodda bu
açıkça yazılı.

## Kapılar

| Dosya | Test | Mutasyon |
|---|---|---|
| `tests/test_ai_analiz_hasta_kimligi.py` | 13 | 9/9 KIRMIZI |
| `petOwnerEklentileri.test.ts` (+5) | 16 | 4/4 KIRMIZI |

## Çalışan üründen doğrulama (son adım)

Derleme çıkış kodlarına güvenilmedi ([[pemf-build-dll-kilidi-ve-sahte-cikis-kodu]]);
kurulu EXE ayağa kaldırılıp uçlara **gerçekten soruldu** (port 8081):

| Kapı | Sonuç |
|---|---|
| `/api/history/delete_bulk` + onaysız reddi | HTTP 400 |
| `/api/patients/delete_bulk` + onaysız reddi | HTTP 400 |
| CSV Durum sütunu Türkçe | `Tamamlandı`, `Donanım Reddetti` |
| Hiçbir bobin sürülemezken seans reddi | HTTP 503 |
| Hata mesajı EYLEM söylüyor | firmware/reflash geçiyor |
| PDF metninde Türkçe | `PEMF TEDAVİ RAPORU` (kutucuk yok) |
| `GET /api/ai/log/{id}/pdf` | HTTP 404 (olmayan kayıt) |
| K1 `POST /api/ai/log` `patient_id` kabulü | HTTP 200 |
| K2 `GET /api/ai/log?patient_id=` süzgeci | 1 kayıt |
| K3 `patient_uuid` yanıtta dönüyor | evet |
| OpenAPI: üç yeni uç kayıtlı | evet |

**15/15 GEÇTİ.** Doğrulamadan sonra test süreci kapatıldı.
