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
| `dist-info` taşıyan diğer paketler | ~~24 — **hepsi izin verici** (MIT / BSD / Apache-2.0 / ISC / MPL-2.0)~~ **99** (D6.43 ölçümü 2026-10-28: `base-deps.zip`'te 100 METADATA) — çoğu izin verici; **zayıf kopyleft (LGPL)**: `pi-heif` (LGPLv3 sınıflandırıcısı — aynı METADATA `License: BSD-3-Clause` der, paket kendi içinde çelişir), `soxr` (LGPL-2.1-or-later); ayrıca METADATA'sı pakette olmayan `zeroconf` (LGPL-2.1, doğrulanmış sabit tablo). Kopyleft kapısı LGPL'yi bilinçli dışarıda tutar (dinamik bağlama) |

Yani **tüm GÜÇLÜ kopyleft (AGPL/GPL) yüzeyi tek bir pakettir** (LGPL bileşenler yukarıda — kaynak açma yükümlülüğü doğurmaz, dinamik bağlama koşuluyla). Bu, sorunu çözülebilir kılan en önemli bulgu.

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
| `inference_petri_dish/petri_cv_v2/petri_detector.py` (+ `plate_grid.py` aday ipucu) | `yolo11m-seg.onnx` (ultralytics ile) | **EVET** | `ai_router` çağırıyor (AI-2, 2026-10-12: v1 `petri_cv/` + `.pt` varsayılanı emekli) |
| `inference_human_kidney_ct` | ultralytics + cv2 | **EVET** | `ai_router` çağırıyor |
| `cat_segmentation` | `yolov8m-seg.pt` | **EVET** | `ai_router` çağırıyor (`ai_router.py:2496`, `/api/ai/vision/segmentation`) |
| `feline_reticulocytes` | `yolov8s.pt` | **EVET** | `ai_router` çağırıyor (`ai_router.py:2649`, `:2702`) |
| `cat_landmark` | `yolo26m-pose.onnx` | evet | **zaten ONNX** — ⚠️ ama dosya `from ultralytics import YOLO` içerir (`inference_cat_landmark.py:673`) |
| `inference_cat_organ` | `.onnx` | evet | **zaten onnxruntime** — ⚠️ YOLO segmentasyonu `lib/runners.py:70` `from ultralytics import YOLO` ile yüklenir |

> ⚠️ Denetim raporunda *"modeller zaten `.onnx`"* deniyordu; **bu yalnız 1/4 için doğru**.
> ~~Üç model hâlâ `.pt` (Ultralytics native) ve ONNX'e taşınmak için önce dışa aktarılmalı.~~
>
> ⚠️ **D6.43 ölçümü (2026-10-28, AST — `import ultralytics` / `from ultralytics …` düğümleri):** ultralytics'i içe aktaran `ai_hub` modülü: **7** —
> `cat_landmark`, `cat_segmentation`, `feline_reticulocytes`, `inference_cat_organ` (`lib/runners.py`), `inference_human_kidney_ct`,
> `inference_petri_dish` (+ `petri_cv_v2/petri_detector.py`), `xai_utils` (`yolo_cam.py`, EigenCAM yardımcısı). Kütüphane bağımlılığı
> ağırlık BİÇİMİNDEN bağımsızdır: `.onnx` ağırlık da `ultralytics.YOLO(...)` ile yükleniyorsa AGPL kodu çalışır — "zaten ONNX"
> ultralytics'siz demek DEĞİLDİR. Kapı: `tests/test_notice_lisans_hucresi_LISANS_ADI_D6_43.py` (sayı koddan ölçülür).

## 4. Seçenekler ve gerçek maliyetleri

**(a) Ticari lisans (Ultralytics Enterprise)** — en az kod riski. Yıllık ücret; ürünü olduğu gibi
bırakır. Karar: bütçe.

**(b) ONNX Runtime'a taşı** — ~~üretim yolundaki **iki** modül (petri, kidney_ct) taşınmalı~~ ultralytics'i içe aktaran **yedi** `ai_hub` modülünün (§3 sonundaki ölçüm) ultralytics çağrıları kaldırılmalı.
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

**(d) Yüzeyi küçült (kısmi)** — ⛔ **UYGULANAMAZ (ölçüldü):** bu seçenek `cat_segmentation` ve
`feline_reticulocytes` modüllerinin "üretimde kullanılmadığı" varsayımına dayanıyordu; ikisi de
CANLI teşhis ucudur (`ai_router.py:2496` ve `:2649`/`:2702`). Paketten çıkarmak `/api/ai/hazirlik`
kapsamını düşürür (`_AI_MODUL_ENVANTERI`, `ai_router.py:3790`, `:3807`; kapı
`tests/test_ai_hazirlik_envanteri.py`) ve iki ucu kırar. AGPL yüzeyi bu yolla küçültülemez.

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
