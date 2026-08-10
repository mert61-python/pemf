# Ultralytics AGPL-3.0 — durum tespiti ve karar notu

**Tarih:** 2026-08-09 · **Durum:** AÇIK (karar bekliyor) · **Kim:** sahip + hukuk

> Bu dosya bir karar VERMEZ; kararı verebilmek için gereken **ölçülmüş** gerçekleri toplar.
> Yazılım tarafında yapılan tek değişiklik, yüzeyin sessizce büyümesini engelleyen bir test
> kapısıdır (`tests/test_license_surface.py`).

---

## 1. Ölçülen durum

`pemf-app-packages/base-deps.zip` (yayındaki paket) içinde:

| Bulgu | Değer |
|---|---|
| `ultralytics` dosya sayısı | **321** |
| Sürüm | `8.4.47` |
| Lisans (dist-info METADATA) | **AGPL-3.0** |
| `dist-info` taşıyan diğer paketler | 24 — **hepsi izin verici** (MIT / BSD / Apache-2.0 / ISC / MPL-2.0) |

Yani **tüm kopyleft yüzeyi tek bir pakettir**. Bu, sorunu çözülebilir kılan en önemli bulgu.

> ⚠️ Bu envanter `dist-info` bırakan paketleri kapsar; PyInstaller çoğu metadata'yı ayıklar.
> Tam envanter için `build_tools/myenv-requirements.txt` esas alınmalıdır.

## 2. Neden sorun

Ürün: kapalı kaynak, `.pyd` ile tersine mühendisliğe karşı korunmuş, ücretli abonelikle satılan
bir yazılım. AGPL-3.0 ise türev çalışmanın kaynağının **alıcıya açılmasını** şart koşar. Paket
kliniklere fiilen dağıtıldığı için bu teorik değil, **gerçekleşmiş** bir durumdur. Telif sahibinin
talebi ürünün sahadan çekilmesine yol açabilir.

Ayrıca asgari **atıf (NOTICE)** dosyası da yoktu — o eksik bu notla birlikte kapatıldı
(`THIRD_PARTY_LICENSES.md`).

## 3. Kullanım haritası (nerede, ne kadar)

| Modül | Model dosyası | Üretim yolunda? | Not |
|---|---|---|---|
| `inference_petri_dish/petri_cv/petri_detector.py` | `yolo11m-seg.pt` | **EVET** | `ai_router` çağırıyor |
| `inference_human_kidney_ct` | ultralytics + cv2 | **EVET** | `ai_router` çağırıyor |
| `cat_segmentation` | `yolov8m-seg.pt` | hayır | yalnız CLI/demo bloğu |
| `feline_reticulocytes` | `yolov8s.pt` | hayır | yalnız CLI/demo bloğu |
| `cat_landmark` | `yolo26m-pose.onnx` | evet | **zaten ONNX** |
| `inference_cat_organ` | `.onnx` | evet | **zaten onnxruntime** |

> ⚠️ Denetim raporunda *"modeller zaten `.onnx`"* deniyordu; **bu yalnız 1/4 için doğru**.
> Üç model hâlâ `.pt` (Ultralytics native) ve ONNX'e taşınmak için önce dışa aktarılmalı.

## 4. Seçenekler ve gerçek maliyetleri

**(a) Ticari lisans (Ultralytics Enterprise)** — en az kod riski. Yıllık ücret; ürünü olduğu gibi
bırakır. Karar: bütçe.

**(b) ONNX Runtime'a taşı** — üretim yolundaki **iki** modül (petri, kidney_ct) taşınmalı.
`onnxruntime` zaten pakette ve başka modüllerde kullanılıyor, yani altyapı hazır. İş yükü:
`.pt → .onnx` dışa aktarım + ön/son işlemenin (letterbox, NMS, segmentasyon mask prototipleri,
pose çözümleme) elle yazılması. Bunlar bugün Ultralytics'in yaptığı işlerdir ve **teşhis
çıktısını** etkiler → `ai_hub/PEMF_AI_Test_Girdileri/` ile çıktı karşılaştırması ZORUNLU.

> ⚠️ **BU SEÇENEK SORUNU ÇÖZMEYEBİLİR.** Ultralytics **önceden eğitilmiş ağırlıkları da** AGPL ile
> lisanslar. Modelleriniz o ağırlıklardan ince-ayarla türetildiyse, kütüphaneyi kaldırmak ağırlık
> lisansını değiştirmez; `.onnx`'e dönüştürmek de türev olma durumunu ortadan kaldırmaz.
> **Bu, avukata sorulması gereken asıl sorudur** ve (b)'ye başlamadan önce netleşmelidir.
> Modeller sıfırdan (Ultralytics ağırlığı kullanılmadan) eğitildiyse tablo tamamen değişir.

**(c) Ürünü AGPL altında yayınla** — mevcut ticari modelle ve `.pyd` kod korumasıyla çelişir
(bkz. `docs/` kod koruması notları). Pratikte seçenek değil.

**(d) Yüzeyi küçült (kısmi)** — üretimde kullanılmayan iki modülü (`cat_segmentation`,
`feline_reticulocytes`) ve onların `.pt` dosyalarını paketten çıkarmak, dağıtılan AGPL yüzeyini
azaltır ama **kaldırmaz** (petri + kidney_ct kalır). Tek başına uyum sağlamaz.

## 5. Yazılım tarafında şu an yapılanlar

- `THIRD_PARTY_LICENSES.md` — atıf/NOTICE dosyası (paketle birlikte dağıtılmalı).
- `tests/test_license_surface.py` — **regresyon kapısı**: pakete YENİ bir kopyleft bağımlılık
  girerse test düşer. Bugünkü tek istisna (`ultralytics`) açıkça listelenmiştir; yani sorun
  "bilinen ve izlenen" hâle gelir, sessizce büyümez.

> ⚠️ **NOTICE dosyası AGPL uyumu SAĞLAMAZ.** Atıf yükümlülüğünü karşılar; kaynak açma
> yükümlülüğü sürer. Bu not, o yanılgıya düşülmesin diye buradadır.

## 6. Sonraki adım

Karar sırası: **önce hukuk** (ağırlık lisansı sorusu), sonra bütçe (a) ya da mühendislik (b).
Karar verilince bu dosya güncellenmeli ve `tests/test_license_surface.py`'deki istisna listesi
buna göre değiştirilmelidir.
