# PEMF Kabin + Kamera + QR Kurulum Kılavuzu

**Amaç:** Kamera fotoğrafı → ArUco (QR) marker ile **6-DOF poz** → tümör / petri kuyusu / kedi organının
**coil-frame'de 3B konumu (mm)** → coil array'in *nereyi hedefleyeceği*. Bu **hem donanım hem yazılım**:
donanım = kabin + kamera + basılı QR; yazılım = `cabin_config_example.yaml` + CV pipeline (entegre).

3 pipeline ortak paterni kullanır: **cat_organ** (referans) · **em_fantom** · **petri_dish**.

---

## ✅ KABİN (2026-10-23 — TEZGÂH-2B, sahip şerit metre + ArUco; Oturum 13'ün 57 × 34 × 32 / arka duvar düzeni ESKİ)

> Kamera (Pusat "FHD Camera", 1920×1080) tavan camının 2 cm üstünde, tepeden bakar; işaret TABAN camının üstünde.
> Kamera ya da işaret kaydırılırsa `qr_to_origin_cm`, `fixed_position_cm`, `to_marker_cm`, `to_origin_cm` yeniden ölçülür.

| Öğe | Değer (origin = kabin merkezi = coil merkezi = 0,0,0) |
|---|---|
| **Eksen kuralı** | **+X = ÖNDEN BAKANIN SOLU** (kedinin kafa yönü) · **+Y = yukarı** · **+Z = arkaya** — kodla ölçüldü (TEZGAH-OTURUM-13 §F2). 2026-10-14'e kadar bu kılavuz ve YAML açıklamaları "sağ-alt-ÖN = +X" diyordu: **AYNAYDI** |
| **Kabin iç boyut** | `cabin_extent_cm: [55.5, 35, 40.5]` — [X sol↔sağ cam, Y alt↔üst cam, Z ön↔arka cam] |
| **Duvarlar** | X = ±27.75 (**sol +27.75, sağ −27.75**) · Y = ±17.5 (taban camı −17.5, tavan camı +17.5) · Z = ±20.25 (ön −20.25, arka +20.25) |
| **Kamera lensi** | `fixed_position_cm: [2.75, 19.5, -12.25]` = **sol camdan 25 · ön camdan 8 · taban camından 37 cm** (tavan camının 2 cm üstü), tepeden bakar |
| **QR marker merkezi** | **TABAN camının üstü (Y=−17.5)**: siyah kare sol kenarı sol camdan 31 · ön kenarı ön camdan 14,5 cm → `[-8.25, -17.5, -0.75]` |
| **qr_to_origin_cm** | origin − marker = `[8.25, 17.5, 0.75]` |
| **Marker** | DICT_5X5_50 · ID 0 · **10×10 cm** (cetvel) · siyah yüz **yukarı** (tavandaki kameraya, `normal_axis "+Y"`) · "▲ ÜST" **arka duvara** (`up_cabin [0, 0, 1]`) |
| **Şerit-metre** | kamera→origin = **23.2 cm** · kamera→marker merkezi = **40.3 cm** |
| **Hedef düzlemi** | `hedef_duzlem_cm: -17.2` — 24'lük plaka taban camının üstünde, kuyu tabanı camdan ~0,3 cm |
| **Plaka deney yeri** | T2B ölçüsü `a1 [161.7, -172.0, -14.1]` mm — YAML'a **yazılmadı** (`a1_cabin_mm: null`): dolu iken işaretsiz her plaka fotoğrafı bu kabinin deney yerinde sayılıyordu (T2B B7, T3 ölçtü). Konum yalnız kabin işaretinden (ArUco) |

> ⚠️ **Ters işaret:** 2026-10-14'te kâğıt 180° TERS bulundu ve çevrildi. Kod artık bunu `rvec`'ten görür: analiz sonucunda
> `marker_upside_down` — "Kabin işareti ters takılmış görünüyor — üst kenar tavana bakacak şekilde çevirin" — ve sonuç
> bobine sürülmez (PEMF kapısı ENGELLEYİCİ). Ters kâğıtla kabin X / Y aynalanır (ölçüldü: her hedef "kabin dışında").
> ⚠️ **Hedef düzlemi:** fantom / petri `hedef_duzlem_cm: -20` bu kabinde **tabanın ALTINDA** (Y ±17) → ArUco kipinde
> konum üretilmez (fail-closed); yeni lens tabandan yalnız 2 cm olduğu için taban düzlemine neredeyse yatay bakar.
> Kamera yeniden yerleşince plaka düzlemi ölçülüp yazılacak (§0.5, sahibe).
> (Tarihçe, 65×50×50 düzeni) Kamera→marker ışını kediyi kesebiliyordu; marker **tavana** taşınırsa
> `normal_axis_in_cabin: "-Y"` ile birlikte **`camera.up_cabin` ZORUNLUDUR** — işaretin ÜST kenarının baktığı kabin
> ekseni (ör. `[0, 0, -1]`); verilmezse yükleme REDDEDER (eskiden dönüşüm sessizce TEKİL kuruluyordu).
> Mod = **kamera-sabitli**: en kritik doğruluk **kamera lensinin konumu**; QR = ölçek + origin referansı.

Bu değerler **3 kabin yaml'ında canlı**: `inference_cat_organ/cabin_config_example.yaml`,
`inference_em_fantom/phantom_cv_v3/cabin_config_v3.yaml`, `inference_petri_dish/petri_cv_v2/cabin_config_v2.yaml`
(AI-2, 2026-10-12: hocanın fantom v3 / petri v2'si; v1 `phantom_cv` / `petri_cv` emekli).
Kurulu makineye **yayınla** (app katmanı) gider; yayın sonrası backend yeniden başlar.

---

## 0.5) FANTOM / PETRİ YERLEŞİMİ ve HEDEF DÜZLEMİ (2026-09-09, sahip kararı #6)

> ℹ️ Bu bölüm 65×50×50 düzeneğinin ölçümleridir (TARİHÇE); güncel kabin yukarıda. Sonuç değişmedi: alçak lensle
> taban düzlemi sayısal olarak dayanıksız — 2026-10-14 kabininde lens tabandan 2 cm, `-20` düzlemi tabanın altında.

> ⚠️ **BU DEĞERLER GEÇİCİ — sahip notu (2026-09-09): "kamera ile fantom ve petri konumları için
> sahada tekrar düzeltme yapacağım".** Aşağıdaki işaret kenarı (15 cm), köşe yerleşimi (11/11 cm),
> hedef düzlemi (tabandan 5 cm) ve kamera konumu (`fixed_position_cm`) SAHADA ölçülüp
> güncellenecektir. Yazılım tarafında yapılacak tek iş yaml'daki sayıları değiştirmektir; kod
> değişikliği GEREKMEZ. Ölçüm bitene kadar `PEMF_ARASTIRMA_AIPRO` **0** kalır.

**Sahip kararı:** fantom ve petri plakası kabinde **YATAY** duruyor, **doğrudan tabanın üzerinde**
(0-2 cm). Kabin işareti henüz yapıştırılmadı → "düz ve kenarları kabinle paralel" hedeflenecek.

**Kodda ne değişti:** kesişim düzlemi artık yapılandırılabilir (`phantom_plate.hedef_duzlem_eksen`
+ `hedef_duzlem_cm`) ve marker→kabin **rotasyonu** uygulanıyor (eskiden hiç uygulanmıyordu).

**⚠️ ÖLÇÜM — yatay düzlem mevcut KAMERA konumuyla dayanıksız.** `06b_PetriKuyu_aruco.jpg` ile:

| Rotasyon | Hedef düzlemi | Bulunan kuyu konumu | Kabin içinde? |
|---|---|---|---|
| var | `Y = -24,0` cm (taban + 1 cm) | (−97,3 · −24,0 · **+1095,9**) cm | ❌ |
| var | `Z = 0` cm (eski) | (−2,3 · +7,7 · 0,0) cm | ✅ |
| yok (eski kod) | `Y = -24,0` cm | (73,3 · −24,0 · **−872,5**) cm | ❌ |

**2026-09-09 ikinci ölçüm — sahip ölçüsüyle (işaret 15 cm, merkez 11/11 cm), AYNI fotoğraf:**

| Hedef düzlemi | Bulunan kuyu konumu | Kabin içinde? |
|---|---|---|
| `Z = 0` cm (eski davranış) | (12,0 · +0,1 · 0,0) cm | ✅ |
| `Y = -24,0` (taban + 1 cm) | (−60,3 · −24,0 · **+534,1**) cm | ❌ |
| **`Y = -20,0` (taban + 5 cm — SAHİP ÖLÇÜSÜ)** | (−48,3 · −20,0 · **+445,4**) cm | ❌ |
| `Y = 0` (kabin ortası) | (11,7 · 0,0 · +2,0) cm | ✅ |

> ⚠️ **Tabandan 5 cm de YETMİYOR.** Sahip ölçüsü yapılandırmaya yazıldı (`hedef_duzlem_eksen: "Y"`,
> `hedef_duzlem_cm: -20.0`) ama ölçüm, kamera lensi taban hizasındayken (Y = −25) 5 cm'lik
> yüksekliğin ışın-düzlem kesişimini hâlâ **kötü koşullandırdığını** gösteriyor: kesişim kabinin
> ~4,5 m ötesine düşüyor. Kabin ortası (Y = 0) ve eski dikey düzlem sağlam çalışıyor.
> Bu yüzden `PEMF_ARASTIRMA_AIPRO` **0 kalıyor**. Tezgâhta iki seçenekten biri gerekiyor:
> **(a)** hedefi kabin ortası yüksekliğine bir platforma al (fantom modelinin eğitim aralığıyla da
> uyuşur), **(b)** kamerayı üst köşeye/tavana taşı ve `fixed_position_cm`i yeniden ölç (kedi akışı
> yeniden doğrulanmalı).
> ⚠️ Bu ölçüm KABİN DOĞRULUĞU değil, DÜZLEM SEÇİMİNİN SAYISAL DAYANIKLILIĞI hakkındadır:
> fotoğraf gerçek kabinde 15 cm'lik işaretle çekilmedi, mesafeler ölçek farkı taşır.

**Neden:** kamera lensi **taban hizasında** (`fixed_position_cm: [32.5, -25, -25]`, yani Y = −25 cm)
ve yatay hedef düzlemi onun yalnız **1 cm** üstünde. Işın bu düzlemi çok **sığ** bir açıyla keser;
birkaç piksellik hata metrelere dönüşür. Kamera bu konumda kediyi (dikey hacim) görmek için
seçilmişti — tabanda yatay duran bir plakayı 3B ölçmek için uygun değil.

⚠️ **YAML'DA SAHİP ÖLÇÜSÜ YAZILI — eski davranışa DÖNÜLMEDİ (ölçüldü 2026-09-22):**
`ai_hub/inference_em_fantom/phantom_cv_v3/cabin_config_v3.yaml:112-113` ve
`ai_hub/inference_petri_dish/petri_cv_v2/cabin_config_v2.yaml:123-124` →
`hedef_duzlem_eksen: "Y"` + `hedef_duzlem_cm: -20.0`. Yukarıdaki tablo bu değerin kuyuyu kabinin
~4,45 m dışına koyduğunu gösteriyor: **fantom/petri tek-foto 3B koordinatları bu yapılandırmayla
GÜVENİLİR DEĞİLDİR** (araştırma AI Pro sürüşü `PEMF_ARASTIRMA_AIPRO=0` ile kapalı, ama AI Hub
tek-foto analizi kapalı DEĞİL). Kedi akışı etkilenmez: `inference_cat_organ` yaml'ında bu anahtar
YOK → kod varsayılanı `Z` / 0 cm (`ai_hub/cv_ortak/cabin_config.py:117`). Eski davranışa dönmek
için iki yaml'da eksen `"Z"` / `0.0` yapın. **Hangisinin doğru olduğu SAHİP KARARIDIR — önce o
netleşmeli.**

**KARAR BEKLİYOR — iki uygulanabilir seçenek:**

1. **Hedefi yükselt (önerilen):** fantom/petri'yi kabin **orta yüksekliğine** (Y ≈ 0 cm) bir
   platforma al. Kamera 25 cm aşağıdan bakar → açı makul. Ayrıca **fantom modelinin eğitim
   aralığıyla uyuşur**: fantom verisi y ∈ [−6,0; +6,1] cm, z ∈ [−3,6; +4,0] cm, x ∈ [−5,7; −3,1] cm
   (yani fantom kabin merkezinde, hafif solda duruyordu). Yaml: `hedef_duzlem_eksen: "Y"`,
   `hedef_duzlem_cm: <platform yüksekliği>`.
2. **Kamerayı yükselt:** lensi üst köşeye/tavana taşı ve `fixed_position_cm` + `to_origin_cm` +
   `to_marker_cm`'i yeniden ölç. Taban düzlemine bakış açısı dikleşir. ⚠️ Kedi akışının görüş
   alanı da değişir — kedi tarafı yeniden doğrulanmalı.

**Eğitim aralığı karşılaştırması (referans örnekleminden ölçüldü, 2026-09-09):**

| Model | x [cm] | y [cm] | z [cm] | Tabanda (y ≈ −24 cm) geçerli? |
|---|---|---|---|---|
| fantom | −5,7 … −3,1 | −6,0 … +6,1 | −3,6 … +4,0 | ❌ (hiç görmediği bölge) |
| petri | −20,2 … +28,8 | −32,0 … +31,0 | −28,8 … +14,2 | ✅ |
| kedi | −21,2 … +20,8 | −30,0 … +26,0 | −23,8 … +7,2 | ✅ |

**YERLEŞİM KONTROL LİSTESİ (her deneyden önce):**

1. **Tepsi:** hedef her seferinde AYNI yerde dursun — tepsinin kabin içindeki konumunu işaretle
   (bant/çentik). Konum değişirse `hedef_duzlem_cm` yeniden ölçülmelidir.
2. **Kalınlık:** ölçülecek düzlem hedefin **üst yüzeyi** değil, modelin baktığı **merkez**
   yüksekliğidir: petri plakasında sıvı yüzeyi, fantomda tümör odaklarının gömülü olduğu düzlem.
   Tepsi yüksekliğine hedefin yarım kalınlığını ekleyerek yaz.
3. **İşaret ve hedef AYNI karede:** kabin işareti (arka duvar) kadrajdan çıkarsa konum
   ölçülemez; arayüz "kabin işareti görünmüyor" der ve **öneri üretmez** (karar #4).
4. **Parlama:** işaret üzerinde yansıma olmasın; kabin ışığını hedefin üstüne, işaretin yüzüne
   değil doğrult.
5. **⚠️ TELEFON KAMERASI KULLANILMAZ** (karar #15): konum kabin çerçevesinde ölçülür, telefon o
   çerçevenin dışındadır. Araştırma AI Pro yalnız kabin bilgisayarındaki Kontrol → AI Pro
   ekranında çalışır; telefonda kartlar "masaüstü kabin kamerası ister" der.

**Marker yapıştırma kontrolü:** sayfayı arka duvara **düz** yapıştır, kenarları kabin kenarlarına **paralel**
olsun, "▲ ÜST" oku tavana baksın. Kod bu varsayımla marker→kabin dönüşümünü diag(−1, +1, −1) olarak kurar.
**Ters** (180°) yapıştırılırsa analiz `marker_upside_down` der ve sürmez (TD4); **eğik** yapıştırılırsa bu yetmez —
tam rotasyonun `rvec`ten türetilmesi gerekir (ayrı iş). Yapıştırdıktan sonra bir gönye ile iki kenarı kontrol et.

---

## 1) SABİT KURALLAR (3 kabinde de AYNI — değişmez)

| Öğe | Kural |
|---|---|
| **Origin (0,0,0)** | Kabin merkezi = **coil array merkezi** |
| **Eksenler** | **+X = önden bakanın SOLU** (genişlik/kafa yönü) · **+Y = yukarı (dorsal)** · **+Z = arka (derinlik)** |
| **QR marker** | **TEK ortak marker**: `ai_hub/PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf`. `DICT_5X5_50`, ID `0`, **kenar = 10.0 cm** (saha ölçüsü 2026-10-14, cetvel) |
| **QR yeri** | **TABAN camının üstü** (2026-10-23: merkez `[-8.25, -17.5, -0.75]`; sessiz bölge camlara sığmalı: merkez camdan ≥ 5 + 2 cm); **siyah yüz yukarı (kameraya) bakar**, "▲ ÜST" arka duvara. Tavan / taban işaretinde `camera.up_cabin` ZORUNLU. ⚠️ Taban işaretinde ters / döndürülmüş kâğıdı kod ANLAMAZ — yeri ve yönü camda bantla işaretli kalır |
| **Kamera** | tavan camının üstünde, tepeden bakar; konum camlardan: X = 27.75 − (sol camdan), Y = −17.5 + (taban camından), Z = −20.25 + (ön camdan) |

> ⚠️ Marker'ı **tam 10×10 cm** bas (sayfadaki 10 cm cetvel çubuğunu cetvelle doğrula). Farklı basarsan
> 3 config'te `real_cm`'i o değere çek — yoksa ölçek (mm/px) ve 3B konum yanlış olur.

---

## 2) ÖLÇÜLER (TEZGÂH-2B — 2026-10-23)

| | cabin_extent [X,Y,Z] | kamera lens [x,y,z] | marker merkezi | qr→origin [x,y,z] |
|---|---|---|---|---|
| **cat_organ** | `[55.5, 35, 40.5]` | `[2.75, 19.5, -12.25]` | `[-8.25, -17.5, -0.75]` | `[8.25, 17.5, 0.75]` |
| **em_fantom** | `[55.5, 35, 40.5]` | `[2.75, 19.5, -12.25]` | `[-8.25, -17.5, -0.75]` | `[8.25, 17.5, 0.75]` |
| **petri** | `[55.5, 35, 40.5]` | `[2.75, 19.5, -12.25]` | `[-8.25, -17.5, -0.75]` | `[8.25, 17.5, 0.75]` |

Kamera lensi köşeye tam oturmuyorsa (gövde/tripod payı) **gerçek lens konumunu** ölç ve `fixed_position_cm`'e
yaz; `to_origin_cm` / `to_marker_cm`'i §3'teki formülle yeniden hesapla. Kamera-sabitli modda tek kritik sayı budur.

---

## 3) DOĞRULAMA (kabin kurulunca — ±2 cm tolerans)

- `marker_pos = -qr_to_origin_cm` → `[-8.25, -17.5, -0.75]` ✓
- `to_origin_cm  == |camera.fixed_position_cm|` → `|(2.75, 19.5, -12.25)| = √(7.5625+380.25+150.0625) = 23.2` ✓
- `to_marker_cm  == |camera.fixed_position_cm - marker_pos|` → `|(11, 37, -11.5)| = √(121+1369+132.25) = 40.3` ✓

Şerit metreyle: lens→kabin merkezi **23,2 cm**, lens→marker merkezi **40,3 cm** okunmalı.

---

## 4) MARKER BASIMI + YAPIŞTIRMA

1. `PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf`'i **%100 / "gerçek boyut"** bas ("sayfaya sığdır" ve
   "ölçekle" KAPALI, mat kâğıt). Sayfadaki **10 cm cetvel çubuğu** cetvelde tam 10,0 cm ise marker doğru.
2. Kesik çizgiden kes (**14×14 cm**). Etrafındaki **beyaz kenar (sessiz bölge) kalsın** — ArUco için ZORUNLU.
3. **Taban camının üstü**: **düz**, köşelerinden bantlı (kırışık/eğri değil), **siyah yüz yukarı**, "▲ ÜST" **arka duvara**;
   yeri ve yönü camda bantla işaretlensin (taban işaretinde ters / döndürülmüş kâğıdı kod anlamaz, konumlar yanlış çıkar).
   ⚠️ **YAPIŞTIRDIKTAN SONRA CETVELLE ÖLÇ** (merkezin sol cama `a`, ön cama `c` uzaklığı, cm) ve yaml'ı yaz:
   `qr_to_origin_cm = [a - 27.75, 17.5, 20.25 - c]` (+X = önden bakanın SOLU; 2026-10-23: a = 36, c = 19,5 → `[8.25, 17.5, 0.75]`)
   ve `to_marker_cm`i yeniden hesapla. 1 cm'lik sapma 3B konumda ~1 cm hata demektir.
4. Işık: homojen, **parlama/yansıma yok** (marker üstünde ışık lekesi tespiti bozar).
5. Yeniden üretmek için: `python scripts/kabin_marker_a4.py --masaustu` (300 DPI, kendi kendini doğrular).

---

## 5) KAMERA KALİBRASYONU (opsiyonel ama doğruluğu artırır)

Satranç-tahtası ile lens iç-parametrelerini çıkar → `camera.intrinsics_npz`:
```
python calibrate_camera.py --images chess/ --pattern 9x6 --square-cm 2.5
```
Yoksa: `intrinsics_npz: null` bırak → `to_marker_cm`'den yaklaşık türetilir (kabaca çalışır).
Yol YAML'a göreli olabilir (`.npz` YAML'ın yanına). Kalibrasyon çözünürlüğü kareden farklıysa K kareye ölçeklenir
(fantom v3 + petri v2 — TD4'te ölçüldü: fantom v3 ölçeklemiyordu, işaret mesafesi çözünürlük oranı kadar sapıyordu).

---

## 6) SONRAKİ ADIM

- **Sen:** kabini bu kurallara göre kur (marker + kamera), lens tam köşede değilse gerçek konumu ölçüp ver.
- **Ben:** gerekiyorsa `fixed_position_cm`/mesafeleri günceller, yayınlarım.
  Böylece analiz **kalibrasyonsuz kanonik (açık-döngü)** yerine **gerçek ArUco 6-DOF (doğru hedefleme)** çalışır.

> **QR STANDARDİZE:** 3 pipeline'ın hepsi `DICT_5X5_50 / ID 0 / 10 cm` kullanıyor
> (`real_cm: 10.0`; basılı sayfa: `ai_hub/PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf`) →
> **tek basılı marker yeter**. ⚠️ 2026-09-09 – 10-14 arasında **15 cm** sayfa üretildi; sahadaki kâğıt 10 cm çıktı.
> Kullandığın kâğıdın kenarını cetvelle ölçüp `real_cm`'e yaz — yanlış kenar sessiz ölçek hatasıdır
> (10/15 → 3B konumda 1,5× sapma; ekranda hiçbir hata görünmez).
> Kalan tek iş: fiziksel montaj + ölçü doğrulaması (§3).
