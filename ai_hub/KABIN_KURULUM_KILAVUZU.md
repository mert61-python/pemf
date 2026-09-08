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
| **QR marker merkezi** | **ARKA duvar (Z=+25), sol-üst**: sol duvardan 8 cm, tavandan 8 cm → `[-24.5, +17, +25]` |
| **qr_to_origin_cm** | origin − marker = `[24.5, -17, -25]` |
| **Marker** | DICT_5X5_50 · ID 0 · **10×10 cm** (3 pipeline'da tek ortak) · siyah yüz kameraya (öne, `normal_axis "-Z"`) |
| **Şerit-metre** | kamera→origin = **48.0 cm** · kamera→marker merkezi = **86.7 cm** |

> ⚠️ Kamera→marker ışını origin'in ~4 cm altından geçer: kedi origin'de yatarken marker'ı **kapatabilir**.
> Kapatırsa marker'ı **tavana** taşı: merkez `[0, +25, -10]` → `qr_to_origin_cm: [0, -25, +10]`,
> `to_marker_cm: 61.5`, `normal_axis_in_cabin: "-Y"` (3 yaml'da tek satır).
> Mod = **kamera-sabitli**: en kritik doğruluk **kamera lensinin konumu**; QR = ölçek + origin referansı.

Bu değerler **3 örnek yaml'da canlı**: `inference_cat_organ/cabin_config_example.yaml`,
`inference_em_fantom/phantom_cv/cabin_config_example.yaml`, `inference_petri_dish/petri_cv/cabin_config_example.yaml`.
Kurulu makineye **yayınla** (app katmanı) gider; yayın sonrası backend yeniden başlar.

---

## 1) SABİT KURALLAR (3 kabinde de AYNI — değişmez)

| Öğe | Kural |
|---|---|
| **Origin (0,0,0)** | Kabin merkezi = **coil array merkezi** |
| **Eksenler** | +X (genişlik/kafa yönü) · **+Y = yukarı (dorsal)** · **+Z = arka (derinlik)** |
| **QR marker** | **TEK ortak marker**: `ai_hub/PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf` (Masaüstü'nde kopyası). `DICT_5X5_50`, ID `0`, **kenar = 10.0 cm** |
| **QR yeri** | **ARKA duvar sol-üst köşe** (merkez sol duvardan 8 cm, tavandan 8 cm); **siyah yüz kameraya (öne) bakar**, "▲ ÜST" tavana |
| **Kamera** | Sağ-alt-ön köşe, **origin'e (0,0,0) bakar**, "up" yönü = **+Y** |

> ⚠️ Marker'ı **tam 10×10 cm** bas (sayfadaki 10 cm cetvel çubuğunu cetvelle doğrula). Farklı basarsan
> 3 config'te `real_cm`'i o değere çek — yoksa ölçek (mm/px) ve 3B konum yanlış olur.

---

## 2) ÖLÇÜLER (verildi — 2026-09-08)

| | cabin_extent [X,Y,Z] | kamera lens [x,y,z] | marker merkezi | qr→origin [x,y,z] |
|---|---|---|---|---|
| **cat_organ** | `[65, 50, 50]` | `[32.5, -25, -25]` | `[-24.5, +17, +25]` | `[24.5, -17, -25]` |
| **em_fantom** | `[65, 50, 50]` | `[32.5, -25, -25]` | `[-24.5, +17, +25]` | `[24.5, -17, -25]` |
| **petri** | `[65, 50, 50]` | `[32.5, -25, -25]` | `[-24.5, +17, +25]` | `[24.5, -17, -25]` |

Kamera lensi köşeye tam oturmuyorsa (gövde/tripod payı) **gerçek lens konumunu** ölç ve `fixed_position_cm`'e
yaz; `to_origin_cm` / `to_marker_cm`'i §3'teki formülle yeniden hesapla. Kamera-sabitli modda tek kritik sayı budur.

---

## 3) DOĞRULAMA (kabin kurulunca — ±2 cm tolerans)

- `marker_pos = -qr_to_origin_cm` → `[-24.5, +17, +25]` ✓
- `to_origin_cm  == |camera.fixed_position_cm|` → `|(32.5, -25, -25)| = √(1056.25+625+625) = 48.0` ✓
- `to_marker_cm  == |camera.fixed_position_cm - marker_pos|` → `|(57, -42, -50)| = √(3249+1764+2500) = 86.7` ✓

Şerit metreyle: lens→kabin merkezi **48 cm**, lens→marker merkezi **87 cm** okunmalı.

---

## 4) MARKER BASIMI + YAPIŞTIRMA

1. `PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf`'i **%100 / "gerçek boyut"** bas ("sayfaya sığdır" ve
   "ölçekle" KAPALI, mat kâğıt). Sayfadaki **10 cm cetvel çubuğu** cetvelde tam 10,0 cm ise marker doğru.
2. Kesik çizgiden kes (**14×14 cm**). Etrafındaki **beyaz kenar (sessiz bölge) kalsın** — ArUco için ZORUNLU.
3. **Arka duvar sol-üst**: marker merkezi sol duvardan 8 cm, tavandan 8 cm (siyah karenin kenarı duvardan/tavandan
   3 cm'de başlar). **Düz** yapıştır (kırışık/eğri değil), **siyah yüz kameraya**, "▲ ÜST" tavana.
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
