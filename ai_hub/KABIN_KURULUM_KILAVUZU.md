# PEMF Kabin + Kamera + QR Kurulum Kılavuzu

**Amaç:** Kamera fotoğrafı → ArUco (QR) marker ile **6-DOF poz** → tümör / petri kuyusu / kedi organının
**coil-frame'de 3B konumu (mm)** → coil array'in *nereyi hedefleyeceği*. Bu **hem donanım hem yazılım**:
donanım = kabin + kamera + basılı QR; yazılım = `cabin_config.yaml` + CV pipeline (zaten entegre).

3 pipeline ortak paterni kullanır: **cat_organ** (referans) · **em_fantom** · **petri_dish**.

---

## ✅ ONAYLANMIŞ GEOMETRİ (2026-07-15 — config'lerde canlı)

| Öğe | Değer (merkez = origin = coil merkezi = 0,0,0) |
|---|---|
| **Kabin iç boyut** | `[60, 43, 20]` cm — [uzunluk X(sağ), yükseklik Y, derinlik Z(ön−/arka+)] |
| **Kamera** | `[30, -21.5, -10]` = **sağ-alt-ön köşe** (kediyle aynı düzlem, alçak → yüzü görür), origin'e bakar |
| **QR marker** | Karşı köşe `[-30, +21.5, +10]` (kameranın **tam karşısı**), `qr_to_origin=[30,-21.5,-10]` |
| **Marker** | DICT_5X5_50 · ID 0 · **10×10 cm** (tek ortak) · yüzü kameraya |
| Şerit-metre | kamera→kedi(merkez) = **38.2 cm** · kamera→QR = **76.5 cm** |

> ⚠️ QR tam karşı köşe = kedinin arkasında; kedi kapatırsa (occlusion) QR'ı arka duvarda biraz yukarı kaydır → yazılım tek satırla güncellenir.
> Mod = **kamera-sabitli**: en kritik doğruluk **kamera konumu**; QR = ölçek + origin referansı.

---

## 1) SABİT KURALLAR (3 kabinde de AYNI — değişmez)

| Öğe | Kural |
|---|---|
| **Origin (0,0,0)** | Kabin merkezi = **coil array merkezi** |
| **Eksenler** | +X (uzunluk/lateral) · **+Y = yukarı (dorsal)** · **+Z = kamera tarafı** |
| **QR marker** | **TEK ortak marker** → `PEMF_ArUco_Marker_5X5_50_ID0_10cm.png` (Desktop'ta). `DICT_5X5_50`, ID `0`, **kenar = 10.0 cm** |
| **QR yeri** | **SOL duvar merkezine** yapıştır; **siyah yüzü kameraya (+Z) bakar** |
| **Kamera** | **origin'e (0,0,0) bakar**, "up" yönü = **+Y** |

> ⚠️ Marker'ı **tam 10×10 cm** bas (cetvelle ölç). Farklı basarsan 3 config'te `real_cm`'i o değere çek — yoksa ölçek (mm/px) yanlış olur.

---

## 2) SEN ÖLÇÜP VERECEĞİN DEĞERLER (her kabin için)

Kabini kurunca 3 şeyi cm cinsinden ölç, bana söyle → `cabin_config.yaml`'lara ben gireceğim:

1. **`cabin_extent_cm: [X, Y, Z]`** — kabinin iç boyutları [uzunluk, yükseklik, en].
2. **`camera.fixed_position_cm: [x, y, z]`** — kamera **lens'inin** origin'e göre konumu. (Genelde `[0, 0, +z]` — sağ tarafta, origin'e bakar. `z` = lens'in origin'e Z-mesafesi.)
3. **`geometry.qr_to_origin_cm: [x, y, z]`** — marker'dan origin'e vektör. Marker sol duvarda merkezdeyse `[0, 0, +Zwall]` (Zwall = en/2).

**Mevcut ÖRNEK değerler (referans — senin gerçek ölçülerinle değişecek):**

| | cabin_extent [X,Y,Z] | kamera pos [x,y,z] | qr→origin [x,y,z] |
|---|---|---|---|
| **cat_organ** | `[60, 40, 30]` | `[0, 0, +25]` (sağ duvardan 10cm dışarıda) | `[0, 0, +15]` |
| **em_fantom** | `[20, 20, 20]` | `[0, 0, +15]` (sağ duvarda) | `[0, 0, +10]` |
| **petri** | `[20, 20, 20]` | `[0, 0, +15]` | `[0, 0, +10]` |

---

## 3) DOĞRULAMA (kabin kurulunca — ±2 cm tolerans)

- `marker_pos = -qr_to_origin_cm`  (örn. qr→origin `[0,0,15]` ise marker `[0,0,-15]`)
- `to_origin_cm  == |camera.fixed_position_cm|`
- `to_marker_cm  == |camera.fixed_position_cm - marker_pos|`

*cat_organ örneği:* kamera `(0,0,25)`, marker `(0,0,-15)` → `|kamera|=25` ✓ `|kamera-marker|=40` ✓

---

## 4) MARKER BASIMI + YAPIŞTIRMA

1. `PEMF_ArUco_Marker_5X5_50_ID0_10cm.png`'i **%100 ölçekte** bas; siyah karenin kenarı **tam 10.0 cm** olsun (cetvelle doğrula).
2. Etrafındaki **beyaz kenar (sessiz-bölge) kalsın** — ArUco tespiti için ZORUNLU, kesme.
3. **Sol duvar merkezine düz** yapıştır (kırışık/eğri değil), **siyah yüz kameraya** baksın.
4. Işık: homojen, **parlama/yansıma yok** (marker üstünde ışık lekesi tespiti bozar).

---

## 5) KAMERA KALİBRASYONU (opsiyonel ama doğruluğu artırır)

Satranç-tahtası ile lens iç-parametrelerini çıkar → `camera.intrinsics_npz`:
```
python calibrate_camera.py --images chess/ --pattern 9x6 --square-cm 2.5
```
Yoksa: `intrinsics_npz: null` bırak → `to_marker_cm`'den yaklaşık türetilir (kabaca çalışır).

---

## 6) SONRAKİ ADIM

- **Sen:** kabini bu kurallara göre kur + 3 ölçüyü (§2) ver.
- **Ben:** gerçek değerleri `cabin_config.yaml`'lara girer, app'e bağlar, rebuild/deploy ederim.
  Böylece analiz artık **kalibrasyonsuz kanonik (açık-döngü)** yerine **gerçek ArUco 6-DOF (doğru hedefleme)** çalışır.

> **QR ZATEN HAZIR + STANDARDİZE:** 3 pipeline'ın hepsi `DICT_5X5_50 / ID 0 / 10cm` kullanıyor →
> **tek basılı marker yeter** (Hoca'nın dediği gibi). Kalan tek eksik: fiziksel kabin ölçüleri.
