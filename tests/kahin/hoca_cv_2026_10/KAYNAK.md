# Kâhin verisi — Çağlar Hoca Petri v2 / Fantom v3 (AI-2, 2026-10-12)

Kaynak: `Desktop\Yeni klasör\degisenler.zip` — SHA-256 `0285b1d969f85164b976eee704b42fbad020f638a5572f1b0f7c57d81715d420`
(plan `DENETIM\AI-ENTEGRASYON-PLANI.md` §0; adlar cp437 → UTF-8 düzeltilerek açıldı). Dosyalar DEĞİŞTİRİLMEDİ.

| Bu dizin | Zipteki yol |
|---|---|
| `petri/WhatsApp Image 2026-10-02 at *.jpeg` (6) | `inference/inference_petri_dish/petri/` |
| `petri/real_petri.jpg` | `inference/inference_petri_dish/petri_cv_v2/test_img/real_petri.jpg` (= guii `PEMF_AI_Test_Girdileri/06_PetriKuyu.jpg`, bayt-aynı) |
| `fantom/WhatsApp Image 2026-10-02 at *.jpeg` (9) | `inference/inference_em_fantom/phantom_cv/phantom/` |
| `fantom_eski/WhatsApp Image 2026-06-09 at *.jpeg` (4) | `inference/inference_em_fantom/phantom_cv_v3/test_img/` (eski dağınık-leke fantomu; hoca: "2/2" v1 kipine düşer) |
| `beklenen_petri/summary.csv`, `wells.csv` | `inference/inference_petri_dish/beklenen_sonuclar/` (hoca: Python 3.12.3, OpenCV 4.13.0, petri YOLO `.pt` GPU) |
| `beklenen_fantom/summary.csv`, `tumors.csv` | `inference/inference_em_fantom/beklenen_sonuclar/` |

`run_info.json` dosyaları ALINMADI (hocanın yerel yollarını içerir). Kabul ölçütü hocanın `smoke_test.py`'si: petri 6/6'da 24 kuyucuk;
fantom 9/9'da T1–T5 + `reliable` + kabin koordinatı ≤ 0,5 mm. guii petri YOLO'su ONNX (640 sabit) — fark ve uyarlama
`ai_hub/inference_petri_dish/petri_cv_v2/plate_grid.py::aday_imgsz` ve `DENETIM\DUZELTME-AI2.md` §0.2.

SHA-256:

```
409410e1b0c9e11b9475b5af26e793eda3a3bc6643646e9ef4d5b123068b055e  beklenen_fantom/summary.csv
0f00502db270b549ed68a2167d72a4b79c8e56fcbd9016004c7e1ee28f354e65  beklenen_fantom/tumors.csv
65057c50d12f6efba3a7d734c8375828a25842cdcfe7fc78aeb09c13eb2517b4  beklenen_petri/summary.csv
2951d447d30eddc22f85ea3a85ebd4c6a81ee715277f4c37ed576b48e1d247ce  beklenen_petri/wells.csv
2040944017826859b0093675e24abb6956a0135153116522bb862082674bbc0a  fantom/WhatsApp Image 2026-10-02 at 19.40.11.jpeg
6f3d18848040e0d26e36a8ece8bb0bbe1cb6153c2a01e7ba16a5e11930c43549  fantom/WhatsApp Image 2026-10-02 at 19.40.15(1).jpeg
7923df9b3e5669dc2fd512370cd14f90b3b5970df02f2e03e440a440f16dbf37  fantom/WhatsApp Image 2026-10-02 at 19.40.15.jpeg
49dc793c4f2d5f94f40eb227a4b142a98339963ec1a8b601bc358600f287e418  fantom/WhatsApp Image 2026-10-02 at 19.40.16(1).jpeg
3bbf477973e1b16be83151bd42a5f70da82bcefcb2e317b177ba0b874fc10a7b  fantom/WhatsApp Image 2026-10-02 at 19.40.16(2).jpeg
8c0e158883584c965a51e32b059135e20f3243c1445372b1a34c4d268ab278de  fantom/WhatsApp Image 2026-10-02 at 19.40.16(3).jpeg
8db8abaade4738b556462dae086cbd33bc7a03d9197b1a360e675aecc0096e09  fantom/WhatsApp Image 2026-10-02 at 19.40.16.jpeg
c3dae924ede3989bc91004d39cf98186a5b249464ad8820411d4e501f5563093  fantom/WhatsApp Image 2026-10-02 at 19.40.17(4).jpeg
18be60fb0048c92554fda5e6d8a2867796ce2a0b4e67f83375e678cdff17050b  fantom/WhatsApp Image 2026-10-02 at 19.40.17.jpeg
a387e4f809586ed1584d69c165afbf4b5e37c799580cee2143f9702701921c60  fantom_eski/WhatsApp Image 2026-06-09 at 19.09.31(1).jpeg
1c1e1948d3ffef64d514f05fe28b81a9e4327bce5ea7ebb111088e5847e8befe  fantom_eski/WhatsApp Image 2026-06-09 at 19.09.31.jpeg
74c7eace547ff3cf9bdc143d1a5c80ca074e58536311cddfa7b1ab8ce58ced2c  fantom_eski/WhatsApp Image 2026-06-09 at 19.09.32(1).jpeg
c0c703dae4eef823efec9b5e72b061796cdbc4473b45e3140f374358493a5278  fantom_eski/WhatsApp Image 2026-06-09 at 19.09.32.jpeg
299e997d638fe40de64478076dfbe5c677965222df07bb314e09d8c1e89a8fc2  petri/real_petri.jpg
fa624ea8576af882908095f1e1971e550eb2227ba8112b9a79eb7b00255f8abc  petri/WhatsApp Image 2026-10-02 at 19.40.15(2).jpeg
c9c01d3c1960f331ca9b59a22c024a26a37a2eaf8bee83443a778c29753b5a7a  petri/WhatsApp Image 2026-10-02 at 19.40.15(3).jpeg
e36fac1914c573e07924366eb209d9d4b35fd6b18243b9c2a4caad8eadeab7cf  petri/WhatsApp Image 2026-10-02 at 19.40.15(4).jpeg
f7fe5c61a9af53ed8da9ab114aacc9a99762b054240dd2511c2b22fd4c470678  petri/WhatsApp Image 2026-10-02 at 19.40.17(1).jpeg
994a2114fa1969c8c455d8e90399a3f2866b2b79d3b3eb85d91fe76f114f4a80  petri/WhatsApp Image 2026-10-02 at 19.40.17(2).jpeg
c120759393c29e6efd93f037b16aee3a9056a7990557f4362e5e1fe1d2accf3e  petri/WhatsApp Image 2026-10-02 at 19.40.17(3).jpeg
```
