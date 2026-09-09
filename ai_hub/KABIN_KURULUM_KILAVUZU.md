# PEMF Kabin + Kamera + QR Kurulum Kılavuzu

**Amaç:** Kamera fotoğrafı → ArUco (QR) marker ile **6-DOF poz** → tümör / petri kuyusu / kedi organının
**coil-frame'de 3B konumu (mm)** → coil array'in *nereyi hedefleyeceği*. Bu **hem donanım hem yazılım**:
donanım = kabin + kamera + basılı QR; yazılım = `cabin_config_example.yaml` + CV pipeline (entegre).

3 pipeline ortak paterni kullanır: **cat_organ** (referans) · **em_fantom** · **petri_dish**.

---

## ✅ ONAYLANMIŞ GEOMETRİ (2026-09-08 — sahip ölçüsü: genişlik 65 · derinlik 50 · yükseklik 50 cm)

| Öğe | Değer (origin = kabin merkezi = coil merkezi = 0,0,0) |
|---|---|
| **Kabin iç boyut** | `cabin_extent_cm: [65, 50, 50]` — [X genişlik (kedinin kafa yönü), Y yükseklik, Z derinlik (ön −/arka +)] |
| **Duvarlar** | X = ±32.5 · Y = ±25 (taban −25, tavan +25) · Z = ±25 (ön −25, arka +25) |
| **Kamera lensi** | `fixed_position_cm: [32.5, -25, -25]` = **sağ-alt-ÖN köşe** (alçak → kedinin yüzünü görür), **origin'e bakar** |
| **QR marker merkezi** | **ARKA duvar (Z=+25), sol-üst**: sol duvardan 11 cm, tavandan 11 cm → `[-21.5, +14, +25]` |
| **qr_to_origin_cm** | origin − marker = `[21.5, -14, -25]` |
| **Marker** | DICT_5X5_50 · ID 0 · **15×15 cm** (3 pipeline'da tek ortak) · siyah yüz kameraya (öne, `normal_axis "-Z"`) |
| **Şerit-metre** | kamera→origin = **48.0 cm** · kamera→marker merkezi = **83.3 cm** |

> ⚠️ Kamera→marker ışını origin'in ~4 cm altından geçer: kedi origin'de yatarken marker'ı **kapatabilir**.
> Kapatırsa marker'ı **tavana** taşı: merkez `[0, +25, -10]` → `qr_to_origin_cm: [0, -25, +10]`,
> `to_marker_cm: 61.5`, `normal_axis_in_cabin: "-Y"` (3 yaml'da tek satır).
> Mod = **kamera-sabitli**: en kritik doğruluk **kamera lensinin konumu**; QR = ölçek + origin referansı.

Bu değerler **3 örnek yaml'da canlı**: `inference_cat_organ/cabin_config_example.yaml`,
`inference_em_fantom/phantom_cv/cabin_config_example.yaml`, `inference_petri_dish/petri_cv/cabin_config_example.yaml`.
Kurulu makineye **yayınla** (app katmanı) gider; yayın sonrası backend yeniden başlar.

---

## 0.5) FANTOM / PETRİ YERLEŞİMİ ve HEDEF DÜZLEMİ (2026-09-09, sahip kararı #6)

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

**Bu yüzden yaml şu an ESKİ davranışta** (`hedef_duzlem_eksen: "Z"`, 0 cm): AI Hub tek-foto
analizi bozulmasın. Karar gelene kadar araştırma AI Pro sürüşü `PEMF_ARASTIRMA_AIPRO` bayrağıyla
kapalı kalır.

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

**Marker yapıştırma kontrolü (henüz yapılmadı):** sayfayı arka duvara **düz** yapıştır, kenarları
kabin kenarlarına **paralel** olsun, "▲ ÜST" oku tavana baksın. Kod bu varsayımla marker→kabin
dönüşümünü diag(−1, +1, −1) olarak kurar. **Eğik yapıştırılırsa** bu yetmez; tam rotasyonun
`rvec`ten türetilmesi gerekir (ayrı iş). Yapıştırdıktan sonra bir gönye ile iki kenarı kontrol et.

---

## 1) SABİT KURALLAR (3 kabinde de AYNI — değişmez)

| Öğe | Kural |
|---|---|
| **Origin (0,0,0)** | Kabin merkezi = **coil array merkezi** |
| **Eksenler** | +X (genişlik/kafa yönü) · **+Y = yukarı (dorsal)** · **+Z = arka (derinlik)** |
| **QR marker** | **TEK ortak marker**: `ai_hub/PEMF_ArUco_Marker_5X5_50_ID0_15cm_A4.pdf` (Masaüstü'nde kopyası). `DICT_5X5_50`, ID `0`, **kenar = 15.0 cm** (sahip ölçüsü 2026-09-09) |
| **QR yeri** | **ARKA duvar sol-üst köşe** (merkez sol duvardan 11 cm, tavandan 11 cm — 15 cm işaretin yarısı 7,5 + 2 cm sessiz bölge duvara sığsın diye); **siyah yüz kameraya (öne) bakar**, "▲ ÜST" tavana |
| **Kamera** | Sağ-alt-ön köşe, **origin'e (0,0,0) bakar**, "up" yönü = **+Y** |

> ⚠️ Marker'ı **tam 15×15 cm** bas (sayfadaki 15 cm cetvel çubuğunu cetvelle doğrula). Farklı basarsan
> 3 config'te `real_cm`'i o değere çek — yoksa ölçek (mm/px) ve 3B konum yanlış olur.

---

## 2) ÖLÇÜLER (verildi — 2026-09-08)

| | cabin_extent [X,Y,Z] | kamera lens [x,y,z] | marker merkezi | qr→origin [x,y,z] |
|---|---|---|---|---|
| **cat_organ** | `[65, 50, 50]` | `[32.5, -25, -25]` | `[-21.5, +14, +25]` | `[21.5, -14, -25]` |
| **em_fantom** | `[65, 50, 50]` | `[32.5, -25, -25]` | `[-21.5, +14, +25]` | `[21.5, -14, -25]` |
| **petri** | `[65, 50, 50]` | `[32.5, -25, -25]` | `[-21.5, +14, +25]` | `[21.5, -14, -25]` |

Kamera lensi köşeye tam oturmuyorsa (gövde/tripod payı) **gerçek lens konumunu** ölç ve `fixed_position_cm`'e
yaz; `to_origin_cm` / `to_marker_cm`'i §3'teki formülle yeniden hesapla. Kamera-sabitli modda tek kritik sayı budur.

---

## 3) DOĞRULAMA (kabin kurulunca — ±2 cm tolerans)

- `marker_pos = -qr_to_origin_cm` → `[-21.5, +14, +25]` ✓
- `to_origin_cm  == |camera.fixed_position_cm|` → `|(32.5, -25, -25)| = √(1056.25+625+625) = 48.0` ✓
- `to_marker_cm  == |camera.fixed_position_cm - marker_pos|` → `|(54, -39, -50)| = √(2916+1521+2500) = 83.3` ✓

Şerit metreyle: lens→kabin merkezi **48 cm**, lens→marker merkezi **83 cm** okunmalı.

---

## 4) MARKER BASIMI + YAPIŞTIRMA

1. `PEMF_ArUco_Marker_5X5_50_ID0_15cm_A4.pdf`'i **%100 / "gerçek boyut"** bas ("sayfaya sığdır" ve
   "ölçekle" KAPALI, mat kâğıt). Sayfadaki **15 cm cetvel çubuğu** cetvelde tam 15,0 cm ise marker doğru.
2. Kesik çizgiden kes (**19×19 cm**). Etrafındaki **beyaz kenar (sessiz bölge) kalsın** — ArUco için ZORUNLU.
3. **Arka duvar sol-üst**: marker merkezi sol duvardan 11 cm, tavandan 11 cm (siyah karenin kenarı
   duvardan/tavandan 3,5 cm'de başlar). **Düz** yapıştır (kırışık/eğri değil), **siyah yüz kameraya**,
   "▲ ÜST" tavana.
   ⚠️ **YAPIŞTIRDIKTAN SONRA CETVELLE ÖLÇ.** Gerçek mesafeler 11/11 değilse yaml'ı düzelt:
   `qr_to_origin_cm = [32.5 - a, -(25 - b), -25]` (a = sol duvardan cm, b = tavandan cm) ve
   `to_marker_cm`i yeniden hesapla. 1 cm'lik sapma 3B konumda ~1 cm hata demektir.
4. Işık: homojen, **parlama/yansıma yok** (marker üstünde ışık lekesi tespiti bozar).
5. Yeniden üretmek için: `python scripts/kabin_marker_a4.py --masaustu` (300 DPI, kendi kendini doğrular).

---

## 5) KAMERA KALİBRASYONU (opsiyonel ama doğruluğu artırır)

Satranç-tahtası ile lens iç-parametrelerini çıkar → `camera.intrinsics_npz`:
```
python calibrate_camera.py --images chess/ --pattern 9x6 --square-cm 2.5
```
Yoksa: `intrinsics_npz: null` bırak → `to_marker_cm`'den yaklaşık türetilir (kabaca çalışır).

---

## 6) SONRAKİ ADIM

- **Sen:** kabini bu kurallara göre kur (marker + kamera), lens tam köşede değilse gerçek konumu ölçüp ver.
- **Ben:** gerekiyorsa `fixed_position_cm`/mesafeleri günceller, yayınlarım.
  Böylece analiz **kalibrasyonsuz kanonik (açık-döngü)** yerine **gerçek ArUco 6-DOF (doğru hedefleme)** çalışır.

> **QR ZATEN HAZIR + STANDARDİZE:** 3 pipeline'ın hepsi `DICT_5X5_50 / ID 0 / 10cm` kullanıyor →
> **tek basılı marker yeter**. Kalan tek iş: fiziksel montaj + ölçü doğrulaması (§3).
