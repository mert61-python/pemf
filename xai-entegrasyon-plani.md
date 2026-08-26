# XAI Entegrasyon Planı — PEMF Ekosistemi (2026-08-26)

> **DURUM (2026-08-26): FAZ 1 ✅ + FAZ 2 ÇEKİRDEĞİ ✅** — Faz 1 kalem 1-6 (commit 762e8be→4ab9872,
> +de0726a CKD-CI uyarlaması). **Faz 2 (896bed8+d6414c9):** ses+termal Grad-CAM ısı haritaları —
> `explain=true` → `xai_image_base64`; weights_only=True; tek-iş kilidi; sessizlik kapısı XAI'den
> önce; PT ikizleri release_assets'te (21+15MB, downloader yerel çözer); grad-cam 1.5.7 + timm
> 1.0.28 dört yüzeyde (⚠️ çift-cv2 tuzağı notlu); UI opt-in "🔍 Isı haritası" anahtarı (termal+ses,
> canlı döngüye asla). Backend süit 1827, frontend 578/578.
> **GÜNCELLEME (2026-08-26 gece — 6-denetçili eksik-denetimi, tam teslim `Desktop\entegre` ile):**
> Üstteki "KALAN" satırları BAYATTI — gerçek durum:
> ✅ **YAPILDI (1.9.25/1.9.26 + sonrası):** feline+kidney_ct EigenCAM · RNA IG (captum üç yüzeyde)
> · renal HiRes-CAM ×3 ensemble + disagreement · cu128 imaj-içi smoke (RTX 4070, `SMOKE-OK
> device=cuda 17.5ms`) · pt_coz tek yol çözücüsü. Süitler: backend **1873**, frontend **583/583**.
> ✅ **paper_dilek_hoca artık ATLANMADI** → aynı gün AYRI planla ENTEGRE EDİLDİ:
> **`scratch-entegrasyon-plani.md`** (8 sahip kararı KESİN; `/api/ai/vision/scratch` + `/infer/scratch`
> + "Yara Kapanma (Scratch)" UI + 27 backend + 5 jest testi; cell/ paketi sahibinden bekleniyor).
> 🔴 **HÂLÂ AÇIK — LAUNCHER ÇOKLU-MODEL-ZIP (1.9.39):** launcher 1.9.38'de iş yok (ölçüldü);
> artık İKİ PT'nin (renal 859MB + scratch 872MB) saha ön-koşulu — scratch planında **Faz 4.5**.
>
> **DENETİMİN BULDUĞU GERÇEK EKSİKLER (kod-kanıtlı) — aşağıda §KALAN-2026-08-26:**
> (A) UI explain düğmesi 4 modülde yok (CT/histopat/retikülosit/RNA — backend hazır, buton yok);
> Faz 1.5 UI kalıntıları (cat_organ mirror/anatomik rozetleri, petri N≥30 gerekçe satırı,
> landmark p5-p95 bandı); EM canlı xaiSensitivity yalnız em_kedi'de (fantom/petri uçları eklemiyor).
> (B) **Mod-2 batch/rapor katmanı HİÇBİR modülde taşınmadı:** explain_*.py scriptleri, CLI --xai
> bayrakları, report.html/index.html/summary.csv/CSV+PNG çıktıları — `report_html.build_report`,
> `overlay.side_by_side`, `feature_ranking` şu an yalnız scratch+testlerden çağrılan vendored kod.
> WebView rapor modalı + PDF-XAI (Faz 3) buna bağlı. **SAHİP KARARI GEREKİYOR** (retrospektif/audit
> akışı istenirse Faz 5 olarak planlanır; karar #3 "anlık gösterim" tekil analiz içindi).
> (C) Küçükler: RNA signed-CSV + SHAP-Deep yolu · histopat backbone-başına CAM'ler · CAM-yöntemi
> parametresi termal/ses uçlarında dışa kapalı · retikülosit test-girdisi PEMF_AI_Test_Girdileri'nde
> HİÇ yok · cat_organ calibrate_camera.py aracı · segmentation help-metin düzeltmesi.

**Kaynak:** `C:\Users\merta\Downloads\inference (1)\inference\` (XAI Faz 0-10 sprint çıktısı: 10 modüle Grad-CAM/EigenCAM/SHAP/IG/sensitivity + `xai_utils` + `xai_tabular` + `XAI_INTEGRATION.md`).
**Hedef:** Bu XAI yeteneğini PEMF ekosistemine (guii backend + ai_service :8100 + pf frontend + AI geçmişi) regresyonsuz entegre etmek.
**Keşif yöntemi:** 7 paralel derin-okuma ajanı — tüm XAI kodu satır-satır + guii yüzeyi (ai_router/ai_hub/ai_service/pf/paketleme) + 15 ortak modülün dosya-dosya diff'i. Bulguların tamamı koddan doğrulandı; ölçülemeyenler "tahmin" olarak işaretlidir.

---

## 0. Yönetici Özeti

- **En kritik kural: dosya kopyalama YASAK.** İki kod ağacı ayrışmış — XAI paketi guii'nin sertleştirmelerini içermiyor. Birebir kopyalama şu regresyonları üretir: `weights_only=True` P3 pickle-RCE düzeltmesi geri açılır (cat_sound), `sys.exit→RuntimeError` P3 geri açılır (renal), `em_kedi.predict()` default argümanları kaybolur → **canlı AI Pro seans akışı kırılır** (ai_router 4-arg çağırıyor), `CatThermalPredictor.__init__(model_path, providers)` mikroservis imzası kaybolur → ai_service kırılır, `model_downloader` blokları + CPU provider'lar silinir. **Doğru yön: XAI fonksiyonlarını (`_run_xai*`) guii dosyalarına yamamak.**
- **İyi haber:** torch 2.1.2+cpu ve matplotlib(Agg) frozen deps katmanında **zaten var**; ai_service Docker'da torch 2.7.1 cu128 **zaten var**. Eklenecekler görece küçük: `shap`, `captum`, `grad-cam`, `timm`.
- **PT'siz XAI mümkün ve ilk faz bu:** EM üçlüsü (sensitivity+SHAP, ONNX yeter), cat_disease (SHAP TreeExplainer — `XGBoost.pkl` guii'de zaten ana model), CKD (KernelExplainer over ONNX). Gradient tabanlı XAI (Grad-CAM ailesi) PT ağırlığı ister ve doğal evi **:8100 GPU mikroservisi** (CPU'da 10-30 sn vs GPU 200-500 ms).
- **Gizli hazine:** cat_organ zaten zengin açıklayıcı veri üretiyor (reliability bileşenleri, bootstrap std, mirror_warning, anatomic_consistency, fitted-vs-gözlenen keypoint) ama guii **yalnız reliability + koordinat + overlay** kullanıyor — geri kalanı üretilip atılıyor. AI Pro güven açıklaması için **model değişikliksiz** en yüksek getirili iş.
- **Kritik matematik hatası (canlı yol):** EM modüllerinde tek-örnek XAI **dejenere** — std ve SHAP background verilen X'ten türetildiği için N=1'de sensitivity ≈ 0 ve SHAP ≈ 0 çıkar. Canlı em_kedi "bu dozu neden önerdi" açıklaması için **eğitim-dağılımı istatistikleri sabit varlık olarak paketlenmeli** (küçük ama zorunlu kod değişikliği).

---

## 1. Envanter ve Sınıflama (diff hükümlerine göre)

### A — Mekanik patch (XAI ekleri additive; guii farkı ~yalnız Author satırı)
| Modül | XAI tekniği | PT gerekir mi | Not |
|---|---|---|---|
| em_fantom | sensitivity + kernel-SHAP (`run_em_xai`) | HAYIR (ONNX) | downloader + CPU-provider satırları korunacak |
| em_petri | aynı | HAYIR | BaggingRegressor.pkl (346MB) ve .pth **dağıtıma girmesin** — ölü ağırlık |
| feline_reticulocytes | YoloEigenCAM | EVET (yolov8s.pt ~22,5MB) | en temiz taşıma; ama XAI fonksiyonu yok, inline → fonksiyona çıkarılacak; klinik doğrulaması YOK |
| human_kidney_ct | YoloEigenCAM | EVET (yolov8s.pt ~21,5MB) | ⚠️ AGPL yüzeyi (bkz. Faz 0 karar #4) |
| human_kidney_disease | SHAP KernelExplainer **ONNX üzerinde** | HAYIR | `_run_xai` zaten programatik (CLI'siz) — en kolay backend entegrasyonu |

### B — Patch + guii-özel satırlar MUTLAKA korunacak
| Modül | Korunacak guii satırı | XAI tekniği |
|---|---|---|
| em_kedi | `predict()` default argları (ai_router ~798 4-arg çağırıyor) | sensitivity + kernel-SHAP (ONNX yeter) |
| cat_thermal | `__init__(model_name, model_path=None, providers=None)` (ai_service kullanıyor) + model_downloader | Grad-CAM++ (GhostNetV2.pt ~21MB gerekir; timm) |
| cat_sound | `torch.load(weights_only=True)` — **Audit P3 pickle-RCE** | Grad-CAM++ mel üzerinde (EfficientNet_Lite0.pt ~15MB; timm; runtime='pt' zorunlu) |
| renal_histopath_kmc | `sys.exit → RuntimeError` — **Audit P3** | HiRes-CAM ×3 backbone + disagreement (PT ~859MB!) |

### C — Ayrışmış: cerrahi port
| Modül | Durum |
|---|---|
| cat_disease | guii çekirdeği pkl+`predict_proba`, XAI tarafı ONNX'e migre etmiş. **Avantaj:** `_run_xai` SHAP TreeExplainer'ı zaten pkl üzerinde koşuyor ve pkl guii'de ana model — `_run_xai` taşınır, çağrı noktalarındaki `session.run` → `model.predict_proba`'ya çevrilir. XGBoost.onnx guii'ye GEREKMEZ. ⚠️ Doğrulanmış bug: `explain_cat_disease.py` summary.csv `top_feature` hep boş (sample_id str/int64 uyuşmazlığı) — port öncesi düzelt. |
| human_kidney_rna | guii'nin `KidneyRnaPredictor` + `_outs_to_proba`'sı XAI tarafında yok ve backend bunları import ediyor — dokunulmaz; `_build_mlp_medium`/`_load_pytorch_model`/`_run_xai` (Captum IG) eklenir. mlp_medium_kirc.pt yalnız 1,2MB. captum yeni bağımlılık. |

### D — XAI bilinçli eklenmedi → **sunum-katmanı fırsatları** (model değişikliksiz)
| Modül | Zaten üretilen ama gösterilmeyen açıklama verisi |
|---|---|
| cat_organ | reliability bileşenleri (rel_base/rel_mask/rel_unc — pipeline.py ~234), bootstrap position_std (px/cm/3D), in_body_mask, pnp_fit tanı bloğu (mirror_warning, residual_px, occluded/imputed/outside-mask kp listeleri), anatomic_consistency ihlalleri, fitted_keypoints_2d — **guii bunların HİÇBİRİNİ surfaced etmiyor** (grep 0 hit) |
| cat_landmark | FGS AU başına skor + metin + 14 ham ölçüm + kalibre p5-p95 eşikleri → "ölçülen değer vs normal bant" paneli |
| petri_cv | kuyucuk başına n_cancer_pixels + eşik(30) + reliability=conf×solidity → "neden KANSER" gerekçe satırı |
| cat_segmentation | yalnız conf gösterimi (soft mask kaydedilmiyor — kapsam dışı) |

**Not:** XAI_INTEGRATION.md Bölüm 2/4 cat_organ'ı Grad-CAM kullanıcısı gibi listeler — kodda hiçbir XAI izi yok; **Bölüm 5 + kod gerçeği esas alınmalı.**

### E — guii'de hiç yok (ayrı kapsam kararı)
- **inference_paper_dilek_hoca:** teslimat ÇALIŞTIRILAMAZ — 872MB CPN ağırlığı ve `cell/` kütüphanesi kırık Linux symlink metinleri. Ayrıca `torch.load` monkey-patch'i süreç-global `weights_only=False` yapıyor — alınırsa izole edilmeli.
- **inference_cat_llm:** Ollama daemon + gemma4:e4b (GB'larca) + Gradio — PEMF dağıtım modeline yabancı; ayrıca THINK bloğu üretilip gizleniyor (ileride "açıklama" kanalı olabilir).

---

## 2. Mimari Karar: XAI nereye iner

**Çift-taşıma paritesi (2026-08-17 dersi):** guii her AI ucunu iki taşımayla koşuyor — in-process (frozen EXE, ONNX/CPU) veya `PEMF_AI_SERVICE_URL` ile :8100 GPU devri. Kapı-paritesi vakasının tekrarı olmaması için **XAI mantığı ai_hub ortak modülünde yaşar, iki taşıma aynı fonksiyonları çağırır.**

```
ai_hub/
├── xai_utils/      ← vendor (439 satır) — ⚠️ import'u torch ister → YALNIZ ai_service + PT'li yollar
├── xai_tabular/    ← vendor (560 satır) — import'u numpy-only → backend'e de güvenle girer
└── <modül>/inference_*.py  ← _run_xai* fonksiyonları guii sürümlerine yamalanır
```

**Yöntem-taşıma matrisi:**

| Yöntem | Frozen client (CPU) | ai_service (:8100 GPU) |
|---|---|---|
| EM sensitivity + kernel-SHAP (ONNX) | ✅ uygun (~1-2 sn resident) | ✅ |
| SHAP TreeExplainer (cat_disease pkl) | ✅ hızlı | ✅ |
| SHAP KernelExplainer (CKD ONNX) | ⚠️ yavaş (sn'ler-dk) → async | ✅ |
| Grad-CAM ailesi / IG (PT + gradient) | ❌ CPU 10-30 sn + PT ağırlık yükü | ✅ **doğal ev** (200-500 ms) |
| EigenCAM (gradient'siz ama PT-YOLO ister) | ⚠️ mümkün ama yavaş | ✅ |
| Sunum-katmanı (cat_organ/landmark/petri) | ✅ sıfır ek maliyet | ✅ |

**API deseni:** mevcut tel-sözleşmeyi taklit et — analiz uçlarına opsiyonel `explain=true` parametresi (hafif yöntemler, senkron) + ağır yöntemler için `POST /api/ai/xai/<modul>` (async iş: başlat → poll/status → sonuç). Yanıtta `xai_image_base64` (mevcut `image_base64` deseninin ikizi) + `xai_top_features` JSON listesi. `report.html` yalnız istenirse üretilir.

**Eşzamanlılık:** grad-cam hook'ları + pyplot thread-safe DEĞİL → XAI istekleri için model-başına tek-iş kuyruğu (asyncio semaphore=1); ai_service'in mevcut 4'lü inference semaforundan AYRI.

---

## 3. Faz 0 — Sahip Kararları ✅ KARARLAŞTIRILDI (2026-08-26)

| # | Konu | KARAR |
|---|---|---|
| 1 | Kapsam | **Klinik önce** (Faz 1: EM + cat_disease + AI Pro güven dökümü), araştırma Faz 2+ |
| 2 | PT ağırlık dağıtımı | **Klinik makinelerde DE kullanılabilir** — mekanizma: `release_assets/ai_models` + model_downloader (ilk kullanımda iner, tıpkı bugünkü 858MB histopat ONNX gibi → OTA katmanları BÜYÜMEZ) + ai_service /models mount. CPU'da gradient-XAI 10-30 sn → **async "açıklama hazırlanıyor" UI deseni zorunlu**; GPU'lu kurulumda :8100'den 200-500 ms |
| 3 | Kalıcılık | **(b) Anlık gösterim** — görsel kaydedilmez (bugünkü overlay davranışı); top-özellik METNİ `result_detail`e (şifreli) yazılır. KVKK'da yeni yüzey yok |
| 4 | AGPL / CT-XAI | **ONAY** — araştırma fazında EigenCAM eklenir (mevcut AGPL kararının devamı; ultralytics zaten kullanımda). yolov8s.pt (21,5MB) dağıtılır |
| 5 | Büyük kalemler | Histopat 859MB PT: **klinik makinelerde de** (karar #2 mekanizmasıyla ilk kullanımda iner). paper_dilek_hoca: ~~ATLANDI~~ → **2026-08-26 gece ENTEGRE EDİLDİ** (bkz. `scratch-entegrasyon-plani.md` — closure metrikli yeni teslimle sahip kararı tazelendi). cat_llm: kapsam dışı |
| 6 | Jeton | **XAI = analizin parçası, ek jeton YOK** — 1 jeton = 1 analiz kuralı korunur; yeni XAI uçları jeton TAM-YOL listesine "serbest" olarak bilinçli eklenir (otomatik "goruntu"ya düşmesin) |

---

## 4. Faz 1 — PT'siz Hızlı Kazanımlar (CPU/ONNX; yalnız `shap` eklenir)

**1.1 Ortak paketlerin vendoring'i + sertleştirme** (`ai_hub/xai_tabular`, `ai_hub/xai_utils`):
- `sys.path.insert` deseni → paket-göreli import (`from ai_hub.xai_tabular import ...`).
- **matplotlib fix:** `overlay.py` `matplotlib.cm.get_cmap` → guii'nin 3.10.9'unda ÖLÇÜLDÜ: deprecated ama hâlâ çalışıyor, **3.11'de kaldırılacak** (deprecation mesajı birebir). Vendoring sırasında `matplotlib.colormaps[...]`e çevrilir (gelecek-koruma; "anında kırık" değil — ilk analizde yanlış alarm verilmesin).
- `shap_wrapper` 2 sessiz `except` → logla; deep-yolu CPU-tensor varsayımına "CUDA model desteklenmez" guard'ı; RNG seed sabitle (klinik tekrarlanabilirlik).
- `build_report`: HTML-escape (PII/XSS) + boyut tavanı; `embed=False` yolu kullanılmayacak.
- `em_sensitivity` docstring/kod uyumu (`delta_abs_std` vaadi) düzelt.
- pyplot çağrılarını Figure-API'ye çevir veya lock'la.

**1.2 EM üçlüsü (em_kedi → em_fantom → em_petri):**
- `_predict_raw_output` + `_run_xai_em` guii dosyalarına patch (B/A sınıfı kurallarıyla).
- **Tek-örnek dejenerasyon fixi:** eğitim-dağılımı istatistikleri (feature std + background seti, ~KB'lık `.npz`) modül varlığı olarak paketlenir; `run_em_xai`'ye `ref_stats=` parametresi eklenir. Bunsuz canlı açıklama "her şey 0" gösterir.
- **Canlı yol:** AI Pro kapalı-döngüye XAI SOKULMAZ. Öneri onay ekranına (propose→approve arası) **hafif sensitivity** (7 ONNX forward, sabit-std, PNG'siz JSON) eklenebilir — "bu dozu en çok duty_sum ve achieved_B belirledi" satırı. SHAP yalnız seans-sonrası/batch.
- **SHAP agregasyonu:** `output_agg='mean'` 22/23 heterojen çıktıyı sulandırıyor → D1-D7 (duty) kanallarına hedeflenmiş agregasyon varyantı eklenir; organ_id kategorik-perturbasyon artefaktı raporda dipnotlanır.
- Seans-sonrası rapor: seansın loglanmış (x,y,z,organ_id,B,duty) noktaları → Mod 2 akışıyla ~200KB self-contained paket (bugün çalışır durumda).

**1.3 cat_disease SHAP (en kolay kazanım):** `_run_xai` portu (pkl-tabanlı TreeExplainer, hızlı, GPU'suz; `XGBoost.pkl` zaten staged) + summary.csv sample_id bug fixi + `/api/ai/disease` yanıtına `xai_top_features`.

**1.4 CKD KernelExplainer:** `_run_xai` programatik — `/api/ai/disease/kidney` yanıtına opsiyonel `explain=true` (async; `nsamples=60`; `AI_TIMEOUT_MS` bütçesi içinde kalmıyorsa iş-kuyruğu). Mevcut `filled/imputed/low_evidence` şeffaflık alanlarının yanına `top_features` (htn>hemo>ane... klinik örtüşme doğrulanmış).

**1.5 Sunum-katmanı XAI (model değişikliksiz, en yüksek getiri/maliyet):**
- **cat_organ → AI Pro:** `reliability_components` (rel_base/rel_mask/rel_unc) entry'ye yaz (~1 satır) + ai_router yanıtına + AiProPanel'de "Güven %62 = poz güveni × derinlik × maske-dışı cezası" dökümü; mirror_warning/anatomic_consistency rozetleri; opsiyonel std belirsizlik halkası overlay'e.
- **cat_landmark:** FGS "ölçülen vs p25-p75 bandı" paneli ("ağrı skorunun NEDENİ").
- **petri_cv:** "W3: KANSER (mavi piksel 1245 ≥ 30)" gerekçe satırı.

---

## 5. Faz 2 — GPU Mikroservis Gradient-XAI (:8100)

- `requirements-ai.txt` += `grad-cam`, `shap`, `captum`, `timm` (cu128/torch 2.7.1 ile uyum testi).
- PT ağırlıkları /models mount'una: EfficientNet_Lite0.pt (15MB) + GhostNetV2.pt (21MB) + yolov8s.pt (22,5MB, AGPL kararına bağlı) — release_assets/ai_models tek-kaynağına eklenir, model_downloader manifest'i güncellenir.
- Yeni `/explain/<modul>` uçları REGISTRY deseniyle; **kapılar utils ortak modülünden** (sessizlik kapısı ARKASINDA — sessiz kayda duygu ısı-haritası üretilmemeli; modalite kapıları aynen).
- Tek-iş XAI kuyruğu (semaphore=1/model) + grad-enabled ayrı forward yolu (mevcut inference no_grad ise) + `GradCAMExplainer`/`YoloEigenCAM`'in model mutasyonu (eval, device taşıma, kalıcı hook) nedeniyle **XAI için ayrı model instance** cache'i.
- cat_sound XAI'si: guii'nin `weights_only=True` + backend sessizlik kapısı korunarak; `--xai`nin "runtime'ı pt'ye zorla" davranışı yalnız XAI-yolu instance'ında.
- Router tarafı: `_kapili_devret` benzeri `_explain_devret`; ai_service kapalıysa (klinik tek-EXE) hafif yöntemlere düş veya "GPU servisi gerekli" yanıtı.

---

## 6. Faz 3 — UI + Geçmiş + Rapor

- **AiHubScreen:** analiz kartına "Açıkla" düğmesi/sekmesi → `xai_image_base64` mevcut base64-Image deseniyle (yeni kabiliyet gerekmez); tabular modüllerde top-N özellik tablosu.
- **report.html:** react-native-webview emsali (DemaSimulatorScreen) ile modal gösterim; yalnız istek üzerine üretim.
- **AiProPanel:** Faz 1.5 güven dökümü + öneri ekranında hafif sensitivity satırı.
- **AI geçmişi:** Faz 0 karar #3'e göre — (b) seçilirse `result_detail`e top-features metni (şifreli, küçük); (a) seçilirse şifreli blob kolonu + AiHistoryScreen'e görsel.
- **PDF raporu:** mevcut pdf_report_generator'a opsiyonel XAI görseli (temp_reports "gönder-ve-sil" felsefesiyle uyumlu).

---

## 7. Faz 4 — Araştırma Genişletmeleri (ayrı kararlarla)

- human_kidney_rna IG (captum; PT 1,2MB — tek istisna olarak frozen'a bile girebilir) — `KidneyRnaPredictor` korunarak.
- renal_histopath ensemble HiRes-CAM + disagreement haritası (859MB PT — yalnız ai_service; disagreement klinik "model kararsızlığı" göstergesi olarak değerli).
- human_kidney_ct EigenCAM — **ONAYLI** (Faz 0 karar #4).
- renal histopat PT — **klinik makinelerde de** (karar #2/#5 mekanizması: downloader ile ilk kullanımda iner).
- paper_dilek_hoca: ~~ATLANDI~~ → **ENTEGRE (2026-08-26 gece, ayrı plan: `scratch-entegrasyon-plani.md`)** — closure metrikli yeni teslim sahip kararını tazeledi; 872MB PT release_assets'te, cell/ paketi sahibinden bekleniyor (Faz 4).
- cat_llm: kapsam dışı (Ollama daemon dağıtım modeline yabancı).

---

## 8. Sertleştirme Kontrol Listesi (port sırasında)

**Korunacak guii satırları:** `weights_only=True` (cat_sound) · `sys.exit→RuntimeError` (renal) · `em_kedi.predict()` default argları · `CatThermalPredictor.__init__(model_path, providers)` · tüm `model_downloader` blokları · `providers=['CPUExecutionProvider']` (client tarafı) · `KidneyRnaPredictor`/`_outs_to_proba` · sessizlik/modalite/plausibility/asgari-girdi kapıları · 60MB CSV sınırı.

**XAI koduna yapılacak düzeltmeler:** matplotlib `get_cmap` → `colormaps[]` (guii matplotlib 3.10.9 ile KIRIK) · explain_cat_disease sample_id tip bugı · EM ref-stats parametresi · HTML-escape + boyut tavanı · sessiz except'lere log · seed sabitleme · IG `internal_batch_size` · feline inline-XAI'nin fonksiyona çıkarılması.

**Paketleme:** bağımlılıklar ÜÇ yüzeye (requirements.txt, build_tools/myenv-requirements.txt, ai_service/requirements-ai.txt) + PyInstaller spec hiddenimports · torch 2.1.2+cpu + numpy<2 pin uyumu doğrulaması (torch yükseltmesi bilinçli erteli — XAI kütüphaneleri 2.1.2 ile test edilmeli) · deps katman sha belirlenimciliği (PEMF_PKG_OUT) bilinçli yönetim · yeni .py'ler compile_pyd kapsamına (lazy-import/`__file__` desenleri derlenemeyebilir → şifreleme yoluna düşer, sahada import+çağrı testi zorunlu) · .pth/346MB pkl ölü ağırlıklar dağıtıma GİRMESİN.

**Test disiplini (proje standardı):** her XAI iş kalemi için ayrı test, önce KIRMIZI, iki-yönlü mutasyon; PT↔ONNX parity testleri; XAI hatası ana analizi ASLA düşürmez (try/except + "açıklama üretilemedi" zarif düşüşü); süre benchmark'ı hedef donanımda (tahminler çağrı-sayısı temelli, ölçülmedi).

---

## 9. Riskler (özet)

| Risk | Etki | Önlem |
|---|---|---|
| Dosya kopyalama → 4 bilinen regresyon | Güvenlik + canlı seans kırılması | Patch-only strateji + tam süit |
| matplotlib 3.10.9 × `get_cmap` | heatmap üretimi anında kırık | vendoring sırasında tek satır fix |
| EM tek-örnek dejenerasyonu | canlı açıklama "hepsi 0" — yanıltıcı | ref-stats varlığı zorunlu, bunsuz canlı XAI açılmaz |
| SHAP Kernel yavaşlığı × AI_TIMEOUT_MS=120sn | timeout/UI donması | async iş kuyruğu + hafif yöntem varsayılan |
| grad-cam hook + pyplot thread-unsafe | bozuk/karışık heatmap | model-başına tek-iş kuyruğu + ayrı XAI instance |
| PT ağırlık dağıtımı | OTA/paket boyutu | ✅ karar: downloader ile ilk-kullanımda iner (OTA katmanı büyümez); CPU süresi → async UI |
| Jeton sınıfı belirsiz | ücretlendirme sürprizi | ✅ karar: analizin parçası, "serbest" TAM-YOL kaydı |
| AGPL (ultralytics PT) | lisans | ✅ karar: onaylı (mevcut AGPL kararının devamı) |
| Kalıcı görsel + KVKK | şifreleme baypası | Faz 0 #3; dosya-sistemi çözümü önerilmez |
| Nondeterminizm (seed'siz SHAP) | aynı girdiye farklı açıklama | seed sabitleme (1.1) |

---

## 10. Önerilen Sıra ve Kaba Efor

| # | İş | Bağımlılık | Efor |
|---|---|---|---|
| 0 | Faz 0 sahip kararları (6 karar) | — | toplantı |
| 1 | Vendoring + sertleştirme (1.1) | — | 1 gün |
| 2 | cat_organ sunum-katmanı → AI Pro güven dökümü (1.5) | — | 0,5-1 gün |
| 3 | cat_disease SHAP (1.3) | 1 | 0,5 gün |
| 4 | EM üçlüsü + ref-stats + öneri-ekranı sensitivity (1.2) | 1 | 1,5-2 gün |
| 5 | CKD KernelExplainer async (1.4) | 1 | 1 gün |
| 6 | UI: AiHub "Açıkla" + WebView rapor (Faz 3) | 3-5 | 1-1,5 gün |
| 7 | ai_service gradient-XAI (sound/thermal[/ct]) (Faz 2) | 0#2, 0#4 | 2-3 gün |
| 8 | Geçmiş kalıcılığı (0#3'e göre) | 0#3 | 0,5-1,5 gün |
| 9 | Araştırma genişletmeleri (Faz 4) | ayrı kararlar | ayrı |

Efor tahminleri kod-okuma temellidir; her kalem proje test disipliniyle (RED→GREEN→mutasyon) kapatılır.

---

## §KALAN-2026-08-26 — Eksik-denetimi sonuç tablosu (6 denetçi, tam teslim `Desktop\entegre`)

> **KAPANIŞ 2026-08-27 (gece emri "cat_llm dışında hepsi bitsin"):** A1-A7 ✅ + B ✅ + C ✅
> tamamlandı. Kilitler: `tests/test_xai_kalan_a_grubu.py` (19) + `tests/test_xai_batch_rapor.py`
> (5) + `pf/src/screens/__tests__/xaiKalanA.test.tsx` (7). B kararı: kullanıcı "hepsi bitsin"
> dediği için Faz-5 beklemeden `scripts/xai_batch_rapor.py` TEK-CLI olarak yapıldı (görüntü/ses
> CAM · RNA IG işaretli-CSV · EM sensitivity+SHAP; summary.csv + index.html + `--pdf`
> → `PDFReportGenerator.generate_xai_report`; çıktı-dizini-girdi-dışında bekçisi bulgu-19'a karşı).
> Kalan tek bilinçli-borç: D bölümü (kapsam-dışı) + cat_llm (sabah tartışması).
>
> **DÜŞMAN-DOĞRULAMA TURU (2026-08-27 gece, 4 denetçi + çürütme ajanları — 25 ham → 17
> doğrulanmış bulgu, TAMAMI KAPATILDI):** ⚠️ P1'ler: `xai_ref_stats.npz` frozen EXE'ye hiç
> paketlenmiyordu (spec `.npz` tuple'da yoktu — canlı EM XAI üretimde sessiz ölüydü, 1.9.25'ten
> beri!); FGS band-paneli anahtar uyuşmazlığı (bant `ear_angle` ↔ ölçüm `ear_angle_avg` — 4/8
> satır hiç basılmıyordu → `OLCUM_KAYNAK` eşlemesi); ai_service landmark/cat_organ yanıtları
> A2/A4 alanlarını taşımıyordu (GPU profilinde rozetler+panel ölü → parite + `fgs_bantlari()`
> TEK-KAYNAK modül fonksiyonu); batch ses yolu sessizlik kapısını BAYPAS ediyordu (değişmez
> ihlali → `_ses_kapili_explain` ffmpeg+RMS kapısı); özyinelemeli taramada aynı-stem çakışması
> (görsel yanlış girdiye → yol-tabanlı benzersiz ad); EM sample_id ham dosya-adına (sanitize).
> P2'ler: XAI baz-noktası (0,0)≠pipeline cfg-default'u (8/8 noktada top-3 farklıydı → cfg
> ikamesi 4 sitede); ai_service termal/ses allowlist yoktu (422 paritesi); bekçi tek-dosya
> yanlış-pozitifi + symlink deliği; CSV/embed/URL-encode/PDF-önvalidasyon sertleştirmeleri;
> `batch_xai` SHAP artık 'duty'-agregasyonlu (A7 gerçek wiring). Test-kalitesi bulguları:
> `**_xai_meta` yanıt-wiring kilidi, PDF `/Image` kanıtı, bekçi main()-wiring testi eklendi.
> **Bilinçli-borç (düşük):** A6 yöntem-ulaşımı uçtan-uca testi (model yüklemeli), EM
> sahte-predictor baz-nokta mutasyon körlüğü, petri 'eşik ≥30' metninin sabit oluşu, A1
> jest'inin yalnız CT yüzeyini ölçmesi, RNA mock-sözleşme testi.

### A) Canlı-ürün eksikleri — ✅ TAMAMI KAPANDI (2026-08-27)
| # | Eksik | Kanıt | İş |
|---|---|---|---|
| A1 | ✅ CT/histopat/RNA/retikülosit explain UI | CT+histopat ısı-haritası toggle'ı (histopat ÇİFT: konsensus + kararsızlık), RNA "Sürükleyen genler ↑/↓" satırı, retikülosit `explainDestegi` | jest: xaiKalanA A1 ×2 |
| A2 | ✅ cat_organ mirror/anatomik rozetleri | AiHubScreen resultBox başı — ⚠️ anahtar `passed` ("ok" DEĞİL; validation.py dönüşü ölçüldü) | jest A2 ×2 |
| A3 | ✅ petri gerekçe satırı | kuyu satırında "gerekçe: N mavi piksel (eşik ≥30)" — yalnız kanser kuyusunda | jest A3 |
| A4 | ✅ landmark p5-p95 bandı | router `fgs_bantlari` (thresholds_calibrated.json, modül-cache `_fgs_bantlari()`) + UI "Ölçümler · popülasyon bandı" paneli (bant-dışı işaretli; bantlar yoksa panel gizli) | pytest ×3 + jest ×2 |
| A5 | ✅ EM xaiSensitivity fantom/petri | modül sarmalayıcıları + router meta (to_thread, zarif) + **ai_service app.py paritesi** (kapı-paritesi dersi) | pytest ×4 |
| A6 | ✅ termal/ses `xai_method` allowlist | router + ai_service Form paramı; geçersiz → 422 | pytest ×10 |
| A7 | ✅ `output_agg="duty"` varyantı | shap_kernel_em ilk n_duty kolon ortalaması; geçersiz agg → ValueError | pytest ×2 (mühendislenmiş karşıt-kanıtlı) |

### B) Mod-2 batch/rapor katmanı — ✅ YAPILDI (`scripts/xai_batch_rapor.py`, 2026-08-27)
Tek CLI: `--modul {ct,histopat,termal,retikulosit,ses,rna,em_fantom,em_petri,em_kedi}`
`--girdi <dosya|klasör> --cikti <dizin>` (+`--limit/--xai-method/--top-n/--no-shap/--embed/--pdf`).
Çıktılar: XAI PNG/JPG'ler + `summary.csv` + `index.html` (galeri; `report_html._esc` tek-kaynak
kaçırma) + opsiyonel `rapor.pdf` (`PDFReportGenerator.generate_xai_report` — yeni, bozuk görüntü
raporu düşürmez). RNA yolu C-kalemindeki **işaretli CSV**'yi üretir (`rna_top_genler.csv`:
patient_id/sıra/gene/attribution/yön ↑↓). EM yolu modülün `_run_xai_em` tam paketini çağırır
(sample_id'li). Bulgu-19 tuzağına karşı **çıktı-girdi-dışında bekçisi** (SystemExit). Duman:
em_fantom 4 nokta 0.87s · RNA 2 hasta IG 4.2s · retikülosit 2 görüntü. Not: cp1254 konsolda
UnicodeEncodeError ölçüldü → stdout/stderr UTF-8 reconfigure. Aşağıdaki eski karar-notu TARİHSEL:

**(eski not — SAHİP KARARI BEKLİYOR (öneri: Faz 5))**
Hiçbir modülde taşınmadı: `explain_*.py` batch scriptleri, CLI `--xai` bayrakları, `report.html`
+ `index.html` + `summary.csv` + hasta/görüntü-başına CSV/PNG çıktıları. `report_html.build_report`,
`overlay.side_by_side`, `feature_ranking.bar_plot/top_features_csv` şu an ölü-vendored (yalnız
scratch + testler çağırıyor). Buna bağlı Faz-3 kalanları: WebView rapor modalı, PDF'e XAI görseli,
AI-geçmişi #8 kaleminin rapor-paketi kısmı. Karar #3 ("anlık gösterim") TEKİL analiz içindi —
retrospektif/audit akışı isteniyorsa bu katman ayrı fazdır; istenmiyorsa ölü util'ler not düşülerek
bilinçli-bekletmede kalır. ⚠️ Ölçülen batch tuzağı scratch planı bulgu-19'da (recursive kendi-çıktısı).

### C) Küçük teknik kalanlar — ✅ KAPANDI (2026-08-27)
RNA işaretli-CSV → batch CLI'da (üstte) · retikülosit test görselleri → `04a/04b_Retikulosit.jpg`
(entegre'den; repo `ai_hub/PEMF_AI_Test_Girdileri` = tek-kaynak, Desktop kopyası aynalandı; ayrıca
03a/03b termal + 11b gerçek-format RNA + 90_Batch_XAI/points.csv örnekleri) · `calibrate_camera.py`
→ `ai_hub/inference_cat_organ/` (cabin_config_example.yaml 84. satır referansı artık çözülüyor) ·
segmentation help-metni 0.5/0.5 düzeltildi. Bilinçli-dışı: histopat backbone-başına CAM (ensemble+
kararsızlık yeterli — sahip isterse ayrı iş) · SHAP-Deep RNA yolu (IG tek-kaynak kaldı).
Aşağıdaki metin TARİHSEL:
RNA: işaretli `ig_top_genes_signed.csv` + SHAP-Deep yolu yok · histopat: backbone-başına CAM'ler
dönmüyor (yalnız ensemble+disagreement) · retikülosit: PEMF_AI_Test_Girdileri'nde kan-yayması test
görseli HİÇ yok (gerçek-girdi E2E kör noktası) · cat_organ: `calibrate_camera.py` üretici aracı
guii'de yok (CLI `--camera-intrinsics-npz` tüketiyor) · segmentation: help-metin default'ları yanlış
(0.25/0.7 yazıyor, gerçek 0.5/0.5 — entegre'de düzeltilmiş) · EM/CT/RNA/histopat `test_data/` +
`xai_out_mod2/` örnekleri taşınmadı.

### D) Bilinçli kapsam-dışı (eksik DEĞİL)
cat_llm (Ollama; scratch planı §7 notu) · landmark/segmentation XAI (dokümanın kendisi "gerekmez"
diyor) · cat_organ ölü yardımcıları (estimate_sy_scale_hint, cross_photo_consistency — entegre'de de
çağıran yok) · Mod-2'nin subprocess deseni (kopyalama-yasak kuralı gereği patch/API tercih edildi).

### Sıradaki tek kırmızı ön-koşul — ✅ YAPILDI
**Launcher çoklu-model-zip (1.9.39)** — Faz 4.5 gerçekleşti (research-2.zip 1.81GB, manifest
`model_parts`, launcher parça-döngüsü + ETA); ayrıntı: `scratch-entegrasyon-plani.md` Faz 4.5.
Yayın zinciri bu gece koşuluyor (app 1.9.27 · launcher 1.9.39 · mobil 2.3.25).
