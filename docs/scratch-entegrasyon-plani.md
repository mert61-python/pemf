# paper_dilek_hoca (Scratch/Wound-Healing) Entegrasyon Planı — v2

**Tarih:** 2026-08-26 · **Kaynak paket:** `C:\Users\merta\Desktop\entegre` (984 MB) · **Durum:** ✅ FAZ 1-4.5 GERÇEKLEŞTİ (2026-08-27)

> **KAPANIŞ ÖZETİ:** Faz 1-3 (modül+uçlar+UI; 40 backend + 5 jest kilidi) → cell/ teslimi
> (26.08 23:12, cell.zip) → **GERÇEK-MODEL doğrulaması** (CPU ~18 sn/görüntü; 0H:
> 1495/%4.29/1053.5µm, 24H: 2083/%29.36/428.0µm — sahip referanslarıyla neredeyse birebir)
> → **GPU smoke** `SCRATCH-SMOKE-OK cuda:0 9.8sn 2086 %29.32 eigencam` → **Faz 4.5
> launcher 1.9.39 çoklu-model-zip** (`model_parts`; cargo 223 `--locked`; research-2.zip
> **1.81 GB, sha 10e177b8…** üretildi; make_manifest + BUILD.md runbook AYNI commit'te).
> İki düşman-doğrulama turu 10+ hakem-onaylı bulguyu yayına çıkmadan kapattı.
> **Kalan tek iş:** bir sonraki yayında research-2.zip asset yüklemesi (BUILD.md §6 kuralı).
**Keşif:** 5 paralel okuyucu · **Denetim:** 5 bağımsız denetçi (v1'de 18 eksik bulundu, bu sürümde kapatıldı)

---

## 1) Ne geldi — model ve yetenekleri

| | |
|---|---|
| **Model** | CPN (Contour Proposal Network, `celldetection`) — ResNeXt-101 + UNet |
| **Ağırlık** | `ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt` — **872 MB**, pakette mevcut |
| **Görev** | Hücre instance segmentasyonu + **TScratch-benzeri yara-kapanma metrikleri** — PEMF çalışmasının **primary endpoint**'i |
| **Lisans** | celldetection **Apache-2.0** (doğrulandı — AGPL sorunu YOK) |
| **Referans** | CONTROL-0H → 1494 hücre, closure %4.3 · CONTROL-24H → 2085 hücre, %29.3 (24 saatte +25 puan) |

**Tek girdiden üretilen çıktılar:** segmentasyon · overlay · analiz (yatay/dikey ROI) · kapanma · XAI overlay · XAI 3-panel · metrik seti (n_cells, coverage, closure_pct, mean/max gap µm, gap_area mm²). **Vertical/Horizontal:** analiz ROI'si yaraya **dik** seçilir; ⚠️ closure metrikleri HER ZAMAN dikey-yara varsayımlı (kolon-bazlı gap).

---

## 2) Ölçülen kritik bulgular

### Paket/kod bulguları
1. 🔴 **BLOKER — `cell/` kırık POSIX symlink** (her iki teslimde). CpnInterface + `multi_norm("cstm-mix")` sahibin `training/paper_dilek_hoca/cell/`'inde; pip `celldetection` bunları export ETMİYOR (ölçüldü). `multi_norm` tahminle yazılmaz → **sahibinden istenir**. 872 MB .pt ise pakette GERÇEKTEN var.
2. 🔴 **Global `torch.load` monkey-patch** (süreç-geneli weights_only=False — Audit P3 sınıfı) → kapsamlı contextmanager'a daraltılır, finally ile geri alınır (yapısal testli).
3. 🔴 **`sys.path.insert(0, parent)`** → paket-nitelikli importlar.
4. 🟠 **872 MB PT → 2 GiB dersi** (renal 858 MB emsali, HTTP 422 ölçülmüştü). PT hiçbir model-zip'ine giremez → `release_assets` tek-kaynak + GPU `/models` mount. Sahaya iniş launcher çoklu-model-zip backlog'una bağlı.
5. 🟠 **celldetection frozen EXE'ye GİRMEZ** (deps 6. değişim + CPU'da CPN dakikalar) → mikroservis-öncelikli (§3).
6. 🟡 `_labels/_binary/contours` JSON'a girmez; yanıt = özet metrik + base64 görseller.
7. 🟡 **EigenCAM kaba-bölgeseldir**; UI "bölgesel model ilgisi" der. Fonksiyon default'u `gradcam++` ≠ CLI default'u `eigencam` → servis metodu AÇIKÇA geçer.
8. 🟡 Kod tuhaflıkları korunur ama **UI'ya sızanlar ele alınır** (§5): analysis görseli içindeki "Total cells: 114" (binary sayımı) ile metrik kartındaki n_cells=2085 (CPN instance) AYNI ekranda çelişir — görsel altına tek satır açıklama; `"No cancer"` metni ve tamsayı-bölme görsel içinde kalır (Çağlar'ın v4 davranışı).
9. 🟢 guii `ai_hub/xai_utils` upstream'le birebir uyumlu — XAI için yeni bağımlılık yok.

### Denetimde ÖLÇÜLEN yeni bulgular (v2)
10. 🔴 **Yanıt boyutu**: gerçek örnekte `cam_side_by_side.png` **7,25 MB**, `input.png` 3,75 MB, overlay 3,04 MB; `report.html` **19,0 MB** (v1'deki "0.5-3 MB" yanlıştı). 4-6 ham PNG'nin base64'ü ~15-20 MB → **sunucu-tarafı küçültme ŞART**: her çıktı görseli maks ~1280px + JPEG q85 (cat_organ emsali `ai_router.py:2753`), 3-panel ayrıca sınırlı → toplam ~<1 MB.
11. 🔴 **TIF gerçekliği (frontend)**: native picker/codec TIFF desteklemez (expo-image-picker `Images`), RN `Image` .tif RENDER EDEMEZ, `shrinkForUpload` TIFF decode edemez ve zaten **1500px JPEG %70'e küçültür — pixel_mm/gap-µm ölçümü için kabul edilemez**. → scratch **shrink'i BYPASS eder, HAM dosyayı file-part gönderir** (web'de çalışan tek yol bu; 25 MB router sınırı yeterli); base64 form-part yolu Starlette 1 MB sınırına takılır → **base64 yalnız JSON gövdesinde, multipart'ta yalnız gerçek file part** kuralı. Önizleme: .tif seçiminde placeholder; yanıt `input_image_base64` (sunucuda JPEG) döner → galeriye **[Orijinal]** sekmesi.
12. 🔴 **`predictors.get()` TEK GLOBAL kilitle yükler** (`ai_service/predictors.py:153-159`): CPN'in 15-30 sn ilk yüklemesi sırasında TÜM /infer uçları (AI Pro kapalı-döngü dahil) bekler → **per-key kilit YA DA konteyner açılışında scratch warmup** (Faz 4 kararı; öneri: warmup — basit ve ölçülebilir).
13. 🟠 **VRAM bütçesi ölçülmemiş**: 872 MB model + tile 1664 aktivasyonları + renal 859 MB aynı GPU'da (RTX 4070 8 GB) + app.py eşzamanlılık=4 → Faz 4 smoke'una eş-zamanlı-yük testi; gerekirse scratch'e semafor=1.
14. 🟠 **Timeout bütçesi**: sınırı frontend koyar (AI_TIMEOUT_MS=120 sn < backend 180 sn). CPN soğuk başlatma + tiled inference + XAI üst üste 120 sn'de riskli → scratch **modül-lokal** daha uzun timeout (global sabite DOKUNULMAZ — 13 modülü etkiler) + mevcut `longLoading` ipucu deseni + scratch'e özgü "büyük model — ilk çalıştırma dakika sürebilir" metni.
15. 🟡 `_decode_image` uzantı filtresiz, cv2 TIFF çözer (25 MB/50 MP yeterli); ama cv2'nin çözemediği TIF varyantı (BigTIFF/32-bit float) kapıda "Geçersiz görüntü" alır — gerçek .tif fixture testi eklenir. 16-bit TIF kapıda 8-bit'e iner, mikroservise ORİJİNAL baytlar gider (doğru davranış — mevcut kod).
16. 🟡 **Bekçi kör noktası**: `ai_hub` bağımlılık-bekçisinin `_URETIM` taramasında değil → modül top-level'ına yanlışlıkla celldetection importu girerse CI ancak dolaylı düşer → Faz 1'e "top-level importlar yalnız numpy/cv2" AST testi.
17. 🟡 torch.load-kapsam testi CI'da torch'suz koşabilmeli → sahte-torch stub'ı (`sys.modules`) ile "her yerde"; gerçek torch'la ikinci varyant skipif.
18. 🟡 Referans eşitliği kırılgan (Linux/farklı GPU'dan geliyor) → gerçek-model smoke **toleranslı**: hücre ±%2, closure ±0.5 puan.
19. 🟡 Batch backlog notu: `_collect_from_dir` RECURSIVE ve ölçülen tuzak — örnek `preds_v2.csv`'de script KENDİ çıktı PNG'lerini analiz etmiş (analysis.png → 1674 "hücre"). Batch eklenirse çıktı dizini girdinin DIŞINDA olmalı.

---

## 3) Mimari öneri: mikroservis-öncelikli

```
[pf UI] ──/api/ai/vision/scratch──> [router]
   (ham dosya file-part,               │ ai_service_enabled?
    shrink BYPASS)            EVET ────┤──── HAYIR
                                       ▼            ▼
                          _kapili_devret("scratch")  zarif 503:
                          → :8100 /infer/scratch     "Bu modül GPU AI
                          (Docker cu128, /models       servisi gerektirir"
                           mount'ta 872MB PT)
```

> ⚠️ **KARAR 0.1 (sahip, 2026-08-26): frozen'a celldetection DA eklenir** — yukarıdaki şema geçerli kalır ama "zarif 503" dalı yerini GERÇEK gömülü CPU yoluna bırakır (model dosyası varsa). Deps 6. kez değişir (bilinçli kabul); CPU'da dakikalar sürer → bekleme UX'i (§5.d); ağırlık sahaya ancak launcher çoklu-model-zip'le iner (Faz 4.5).

**Router-seviyesi kapılar OTOMATİK uygulanır** (`ai_router.py:60`): `_allow_large_upload` (base64-part 50 MB — yeterli), `ai_queue_gate` (scratch bypass listesinde değil → doğru şekilde kuyruklanır) ve `jeton_gate` → **jeton sınıfı sahip kararı** (§4/0.6).

---

## 4) Faz planı

### Faz 0 — Sahip kararları ✅ KESİN (2026-08-26, AskUserQuestion ile alındı)
| # | Karar | ✅ KESİN |
|---|---|---|
| 0.1 | Mimari | **FROZEN'A CELLDETECTION EKLENİR** (sahip, öneriden farklı seçti — mikroservis de kalır, gömülü yol GERÇEK çalışır). **Sonuçları:** (a) celldetection dört yüzeye girer: requirements.txt + myenv-requirements.txt + spec hiddenimports (+requirements-ai zaten) + çift-cv2 kontrolü CPU tarafında da; (b) **deps 6. kez DEĞİŞİR** (1.19 GB katman yeniden yüklenir — v2'deki "deps değişmez" vaadi düşer, bilinçli); (c) CPU'da CPN dakikalar sürer → UI bekleme UX'i kritik + backend süreç belleği +~2 GB (872 MB model in-process); (d) ⚠️ **ağırlık dağıtımı çözülmüş OLMAZ**: PT 2 GiB nedeniyle research.zip'e giremez → **launcher çoklu-model-zip (1.9.39) bu modülün sahaya inişinin ÖN KOŞULU oldu — backlog'dan Faz 4.5'e çekildi** |
| 0.2 | Profil | **Yalnız researcher** (UI modes + require_research; kapı bugün uykuda — fiili gizleme UI'da) |
| 0.3 | Girdi kapısı | **Kapısız + n_cells==0 yapılandırılmış uyarısı** |
| 0.4 | UI adı | **"Yara Kapanma (Scratch)"** |
| 0.5 | XAI ücreti | **Analizin parçası, ek jeton yok** — TAM-YOL 'serbest' kaydı Faz 2'de |
| 0.6 | Jeton sınıfı | **3 jeton (ağır araştırma)** — `_AGIR_UCLAR` + pemf-vet-web `config.ts::JETON.maliyet` paritesi + test kilidi |
| 0.7 | Veri sınıfı | **Araştırma kaydı + serbest etiket** ("0H", "24H-PEMF") — hasta bağlamsız, KVKK maskeleme dışı |
| 0.8 | Karşılaştırma | **v1'e hafif Karşılaştır modu** (iki analiz yan yana + Δ kartı, saf frontend); klasör-batch v2 backlog |

### Faz 1 — Backend çekirdeği (cell'siz yapılabilir)
- Modül vendor + sertleştirme (bulgu 2-3-6; pt_coz; tek-iş kilidi; `scratch_analiz()`: metrikler + **küçültülmüş** base64 görseller (bulgu 10: maks 1280px JPEG q85) + `input_image_base64`).
- **n_cells==0 → yapılandırılmış uyarı** yanıtı ("hücre tespit edilemedi — görüntüyü/objektifi kontrol edin"), closure alanları null.
- Post-proc testleri: sentetik dikey-yara maskesi → **kesin** closure değerleri (SCRATCH_ROI_RATIO=0.30 pinli); ROI yön piksel testleri; RED→GREEN→iki-yönlü mutasyon.
- Yapısal testler: global torch.load patch YOK (sahte-torch stub — bulgu 17); **top-level import AST testi** (bulgu 16); kilit-içi çağrı; pt_coz.
- **Modül README** (32-README düzeni; cell/ bekleyen-teslim notu) + vendor notundan makine-yolu temizliği.

### Faz 2 — Uçlar + sözleşme (mock'lu)
- Router `/api/ai/vision/scratch`: ham file-part (+base64 yalnız JSON); `scratch_yonu`, `pixel_mm`, `explain`, `xai_method`; `require_research`; `_kapili_devret` (STRING data); zarif 503; `xai_error`.
- **ai_service imzaları AÇIK** (delegate `str()` + None-atlar): `scratch_yonu: str = Form("dikey")`, `pixel_mm: float = Form(None)`, `explain: str = Form(None)` → `=="true"`, `xai_method: str = Form(None)` + **ALLOWLIST** {eigencam, gradcam, gradcam++} (istek alanı olarak depoda İLK — doğrulanmadan CAM sınıfına gitmez).
- predictors kaydı + **warmup/per-key-kilit kararının uygulaması** (bulgu 12) + `app.py` "torch YOK" başlığının güncellenmesi.
- Route-contract 96→97 (İKİ yer) + **jeton TAM-YOL 'serbest' + sınıf kaydı** (0.5/0.6) + testleri.
- **Girdi tavanı**: mevcut 25 MB/50 MP yeterli — .tif **gerçek fixture** testi (router `_decode_image`'dan geçer, cell'siz koşar).
- Scratch'e **modül-lokal timeout** (bulgu 14).

### Faz 3 — UI (§5 tasarım)
- `AiModule` union + `ALL_MODULES` (modes:["researcher"]) + ScratchModule; "researcher → 6 model" yorumu → 7; **UpgradeModal metnine "yara kapanma (scratch)"**.
- **Picker**: DocumentPicker (RNA deseni) ya da web-input `accept`'e `image/tiff`; **shrink BYPASS + ham file-part**; .tif seçiminde önizleme placeholder; sonuçta **[Orijinal]** sekmesi (`input_image_base64`).
- Butonlu galeri: **Chip bileşeni components/ui'a taşınır** (AiHistoryScreen segment-kontrol deseni — AiHubScreen'de seçilebilir chip yok, ölçüldü).
- Bekleme UX: buton içi spinner + 8 sn `longLoading` ipucu + scratch'e özgü ilk-istek metni.
- Kalıcılık: visionCache — **cache anahtarı = (görüntü, scratch_yonu, pixel_mm)**; hasta/profil temizliği deseni; **base64 alanları TOP-LEVEL** kuralı (cleanDetail depth≥2 iç-nesne sızıntısı ölçüldü) + `DETAIL_LABELS`'a Türkçe metrik etiketleri (closure_pct→"Kapanma (%)" vb.).
- **Karşılaştır modu (0.8)**: iki tamamlanmış analiz yan yana + Δclosure/Δgap kartı.
- Analysis görseli altına tek satır: "Görsel içi sayımlar ROI bandına aittir; toplam hücre sayısı üstteki karttadır."
- Jest: render, buton geçişleri, koşullu XAI butonları, karşılaştır modu, TIF placeholder.
- ⚠️ **Sahaya iniş bağı**: pf PYZ'ye gömülü → UI ancak app YAYINIYLA sahaya iner (Faz 4'e bağlı).

### Faz 4 — Dağıtım + yayın runbook (kısmen cell/ bekler)
- PT → `release_assets/ai_models/ai_hub/inference_paper_dilek_hoca/` (tek-kaynak; zip-bekçi testi — renal deseni).
- **Karar 0.1 kalemleri (frozen):** celldetection dört yüzeye (`requirements.txt` + `myenv-requirements.txt` + spec hiddenimports + `requirements-ai.txt`) + çift-cv2 kontrolü CPU tarafında da + **deps 6. değişim** yayın notuna + backend süreç belleği +~2 GB notu (872 MB model in-process; lazy yükleme, sadece ilk scratch isteğinde).
- `requirements-ai.txt` += celldetection pin + **transitif kontrol**: çift-cv2 tuzağı (grad-cam dersi) + torch 2.7.1+cu128'in EZİLMEDİĞİ imaj-içi doğrulama.
- **Dockerfile.ai-full kararı**: `COPY ai_models /models` → full-imaj ~872 MB büyür (~3 GB, Mac offline paketi) — öneri: kabul (offline paket zaten büyük), notu düşülür.
- **İmaj yenileme sırası**: rebuild → tag → çalışan container restart → **mevcut uçların regresyon smoke'u** (thermal/renal) → scratch smoke.
- cell/ gelince: gerçek-model smoke (**toleranslı** — bulgu 18) + **VRAM eş-zamanlı-yük ölçümü** (bulgu 13) + Docker GPU smoke (`scripts/ai_service_xai_smoke.ps1` genişletme).
- **Yayın runbook**: versions.json + **CHANGELOG kanal başlığı** (pre-commit `check_changelog_surum` kapısı) + manifest ÜÇ yer + **deps-sha DEĞİŞMEDİ kanıtı** (planın ana vaadi — ölçülerek doğrulanır) + rollout.
- Kapanış: `docs/xai-entegrasyon-plani.md`'deki "paper_dilek_hoca ATLANDI" notunun güncellenmesi + memory kaydı.

### Faz 4.5 — Launcher çoklu-model-zip (karar 0.1'in ÖN KOŞULU)
Sahip frozen yolu seçtiği için 872 MB PT'nin klinik/CPU makinelere inişi ancak research paketinin bölünmesiyle mümkün (2 GiB sınırı). Backlog'daki 1.9.39 işi bu modülün saha kapsamına ALINDI: launcher manifest'te `research` profilinin ÇOKLU zip beyanını desteklemeli (`research.zip` + `research-2.zip` …); eski launcher'lar tek-zip'i okumaya devam eder (geriye-uyumlu). Bu iş bitene kadar: GPU/geliştirme makineleri (release_assets ya da /models mount) TAM çalışır; kliniklerde model dosyası yoksa "model kurulmamış" zarif mesajı.

### Geri alma stratejisi
Router+contract değişikliği **tek commit'te izole** (revert = sayaç 97→96 dahil tek geri alım); ai_service imajı tag'li → önceki tag'e dönüş; PT release_assets'te kalabilir (zararsız yetim). Frontend PYZ-gömülü olduğundan UI geri alımı = app sürüm geri alımı (mevcut rollout mekanizması).

---

## 5) UI tasarımı — tek girdi, çok görsel, butonlu ⭐ (sahip: "aşırı önemli")

> **🔬 TIKLANABİLİR PROTOTİP (gerçek CONTROL-0H/24H çıktılarıyla):**
> https://claude.ai/code/artifact/c6e6a343-b324-4902-9b02-2b30c423d29b
> Yön butonları Analiz görselini gerçekten değiştirir (yatay↔dikey ROI); XAI kutusu [XAI]/[3'lü] sekmelerini açar; Karşılaştır 0H↔24H Δ kartını gösterir.

### 5.a Durum makinesi
```
boş ──dosya seç──> hazır ──▶ Analiz Et──> yükleniyor ──ok──> sonuç
                     ▲                        │  8sn: "model hazırlanıyor" ipucu
                     │                        │  hata──> toast + hazır (girdi korunur)
                     └──parametre değişti─────┘          (xai_error AYRI: sonuç kalır,
                        ("yeniden analiz gerekir"          XAI sekmeleri yerine tek satır)
                         rozeti, sonuç SOLUK kalır)
```

### 5.b API → UI eşleme tablosu (sözleşme)
| Yanıt alanı | UI öğesi | Koşul |
|---|---|---|
| `closure.closure_pct` | Büyük metrik kartı **Kapanma** (vurgulu) | closure varsa |
| `closure.mean_gap_um` / `max_gap_um` | Metrik kartları | closure varsa |
| `n_cells` | Metrik kartı **Hücre** | her zaman |
| `closure.gap_area_mm2` + `coverage_ratio` + `score_mean` + `device` | Alt bilgi satırı | her zaman |
| `closure_image_base64` | Galeri **[Kapanma]** (varsayılan seçili) | varsa |
| `analysis_image_base64` | Galeri **[Analiz]** | varsa |
| `seg_image_base64` | Galeri **[Segmentasyon]** | varsa |
| `overlay_image_base64` | Galeri **[Overlay]** | varsa |
| `input_image_base64` | Galeri **[Orijinal]** (TIF'in tek gösterim yolu) | varsa |
| `xai_image_base64` | Galeri **[XAI]** | explain + başarı |
| `xai_side_by_side_base64` | Galeri **[3'lü panel]** | explain + başarı |
| `xai_error` | Galeri altında tek satır uyarı (sekme YOK) | explain + hata |
| `closure_uyari` | Sarı uyarı bandı | yatay yara |
| `uyari` (n_cells==0) | Boş-durum kartı: "Hücre tespit edilemedi — görüntüyü/objektifi kontrol edin" | n_cells==0 |

### 5.c Görünüm



```
┌─ 🧫 Yara Kapanma (Scratch) ──────────────────────────── ▼ ─┐
│  [ Dosya Seç (.tif/.png/.jpg) ]   ← DocumentPicker,        │
│  ┌ önizleme / "TIF seçildi" placeholder ┐   shrink YOK     │
│                                                            │
│  Yara yönü:   ( ● Dikey )  ( ○ Yatay )                     │
│  Objektif:    ( 4× ● )( 10× )( 20× )( 40× )   ← pixel_mm   │
│  ☐ 🔍 Isı haritası (XAI — bölgesel model ilgisi)           │
│                                                            │
│  [ ▶ Analiz Et ]   (8sn+: "Büyük model — ilk çalıştırma    │
│                     dakika sürebilir")                     │
│  ────────────────────────────────────────────────────────  │
│  ┌─────────┬─────────┬──────────┬──────────┐               │
│  │ Kapanma │ Ort.gap │ Maks gap │ Hücre    │               │
│  │ %29.3   │ 428 µm  │ 1278 µm  │ 2085     │               │
│  └─────────┴─────────┴──────────┴──────────┘               │
│  Gap alanı: 1.042 mm² · coverage 0.47 · skor 0.61          │
│                                                            │
│  [Kapanma]* [Analiz] [Segment.] [Overlay] [Orijinal]       │
│  [XAI] [3'lü]        ← son ikisi yalnız yanıtta varsa      │
│  ┌──────────────────────────────────────────┐              │
│  │      (seçili görsel — rs(300))           │              │
│  └──────────────────────────────────────────┘              │
│  ℹ Görsel içi sayımlar ROI bandına aittir; toplam hücre    │
│    sayısı üstteki karttadır.                               │
│  ⚠ Yatay yara: closure dikey varsayımla — yaklaşık.        │
│                                                            │
│  [ ⇄ Karşılaştır ] → iki analiz yan yana + Δ kartı:        │
│     0H %4.3 → 24H %29.3  ·  Δ = +25.0 puan                 │
└────────────────────────────────────────────────────────────┘
```

### 5.d Tasarım kararları
- **Butonlu galeri** (istif değil): 7'ye kadar chip-sekme tek görseli değiştirir; varsayılan **Kapanma** (primary endpoint). Chip bileşeni `components/ui`'a taşınır (AiHistoryScreen segment-kontrol deseni). Dar ekranda chip satırı sarar (flexWrap); görsel `rs(300)` açık yükseklik + `resizeMode="contain"`.
- **Karşılaştır modu (0.8) akışı:** modül kendi oturumunda tamamlanan analizleri (görüntü adı + closure metrikleri + kapanma görseli) listede tutar; **[⇄ Karşılaştır]** son ikisini yan yana açar, listeden değiştirilebilir; Δ kartı = closure farkı (puan) + gap değişimi. Etiket alanı (0.7) buradan doldurulur ("0H", "24H-PEMF"). Saf frontend — backend'e ek yük yok.
- **Erişilebilirlik:** yön/objektif `radiogroup`, XAI `switch`, galeri `tablist`; her chip'e focus halkası; renk tek başına anlam taşımaz (Δ kartında işaret + metin).
- **Bekleme UX'i:** buton içi spinner → 8 sn'de "model hazırlanıyor" ipucu → scratch'e özgü metin "büyük model — ilk çalıştırma dakika sürebilir" (0.1 frozen kararıyla CPU'da bu SIK yaşanacak). Modül-lokal timeout (CPU yolu için 300 sn önerisi; global sabite dokunulmaz).
- CAM-method dropdown'u ve `--no-closure` **bilinçle atlandı** (sadelik; method ALLOWLIST'te hazır, istenirse tek satır).
- Canlı döngü yok; cache anahtarı = (görüntü, scratch_yonu, pixel_mm); hasta/profil temizliği deseni; base64 alanları TOP-LEVEL.

---

## 6) Test & regresyon disiplini

| Katman | Test | Koşul |
|---|---|---|
| Closure matematiği | Sentetik maske → kesin değerler (ROI oranı pinli) + 2-yönlü mutasyon | her yerde |
| Analiz yönü | Yatay/dikey ROI piksel-yön doğrulaması | her yerde |
| torch.load kapsamı | Sahte-torch stub: import→değişmedi · kapsam-içi→değişti · sonra→geri | her yerde |
| Top-level import | AST: modül top-level'ı yalnız numpy/cv2 (bekçi kör noktası) | her yerde |
| n_cells==0 | Yapılandırılmış uyarı yanıtı + closure null | her yerde |
| .tif kabulü | Gerçek TIF fixture `_decode_image`'dan geçer | her yerde |
| Endpoint wiring | Mock analiz; param geçişi (yön/pixel_mm/explain STRING/xai_method allowlist); zarif 503; xai_error | her yerde |
| Yanıt boyutu | 6 görselli yanıt toplam < ~1.5 MB (küçültme bekçisi) | her yerde |
| Route-contract + jeton | GOLDEN_ROUTES + 97; TAM-YOL 'serbest' + sınıf | her yerde |
| Zip bekçisi | Scratch PT hiçbir profilde yok + gerekçe | her yerde |
| Gerçek model | test_data TIF → hücre ±%2, closure ±0.5 puan | cell/+PT varsa (skipif) |
| VRAM/eşzamanlılık | Scratch + renal + thermal eş-zamanlı — OOM yok | cell/ sonrası, GPU |
| GPU smoke | Docker cu128 `/infer/scratch` explain=true | cell/ sonrası |
| Frontend | Jest: render, galeri geçişi, koşullu butonlar, karşılaştır, TIF placeholder, cache anahtarı | her yerde |

---

## 7) Açık sorular / sahipten istenenler

1. **`cell/` paketi** — `training/paper_dilek_hoca/cell/` (cpn.py, prep.py; birkaç KB). Faz 1-3'ü bloklamıyor.
2. **Faz-0 kararları** (§4 — 8 madde, hepsi önerili; itiraz yoksa öneriyle gidilir). Özellikle YENİ üçü: jeton sınıfı (0.6), veri sınıfı (0.7), Karşılaştır kapsamı (0.8).
3. celldetection pin: Çağlar Hoca'nın ortamındaki `pip show celldetection` çıktısı idealdir; yoksa 0.4.9 pinlenir, toleranslı smoke doğrular.

*Not: Faz 1 modül taslağı hazırlık olarak yazıldı (commit edilmedi); v2 bulguları (küçültme, input_image_base64, n_cells==0) taslağa uygulanacak.*
