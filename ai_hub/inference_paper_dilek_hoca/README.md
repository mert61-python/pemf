# inference_paper_dilek_hoca — Yara Kapanma (Scratch) Analizi

CPN (Contour Proposal Network, `celldetection`, Apache-2.0) ResNeXt-101 UNet ile
hücre instance segmentasyonu + TScratch-benzeri **wound-closure metrikleri**
(closure %, ort/maks gap µm, gap alanı mm²) — PEMF çalışmasının primary endpoint'i.

Plan ve sahip kararları: `guii/scratch-entegrasyon-plani.md` (v3, kararlar KESİN).

## 📦 TESLİM BEKLENİYOR — Çağlar Hoca'dan istenenler (2026-08-26)

> **1) `cell/` klasörü (ZORUNLU — bunsuz model çalışmaz).**
> Eğitim deposundaki **`training/paper_dilek_hoca/cell/`** klasörünün kendisi
> (içerik: `cpn.py`, `prep.py`, varsa `__init__.py` — toplam birkaç KB).
>
> **Neden:** Teslim paketindeki `cell` girdisi gerçek klasör değil, **kırık POSIX
> symlink** — içinde yalnız şu yol yazıyor:
> `/home/caglargurkan/Projects/Doktora/.../training/paper_dilek_hoca/cell`
> Windows'a kopyalanınca içi boş geldi (her iki teslimde de aynı). İçindeki iki
> parça olmadan 872 MB'lık model koşamaz:
> - `CpnInterface` — modeli yükleyip tile'lı (1664/384) inference süren sarmalayıcı,
> - `multi_norm(img, "cstm-mix")` — modelin **eğitimde kullandığı** normalizasyon.
>
> pip `celldetection` bu ikisini **içermiyor** (ölçüldü — export listesinde yoklar).
> `multi_norm`'u tahminle yeniden yazmak sessiz-yanlış hücre sayısı üretir; bu
> yüzden bilerek beklenildi.
>
> **GÜNCELLEME (2026-08-26 23:00, sahip yanıtı):** Hoca üç dosyayı adlandırdı —
> **`cpn.py`, `prep.py`, `util.py`** — ve iskelet klasör HAZIRLANDI:
> `ai_hub/inference_paper_dilek_hoca/cell/` (boş `__init__.py` ile). Üç dosya
> geldiğinde AYNEN bu klasöre bırakılır, başka değişiklik gerekmez (hazır-olma
> denetimleri alt-modüle, `cell/cpn.py`'ye bakar).
>
> **2) celldetection sürümü — ✅ ÇÖZÜLDÜ.** Sahip onayı: **0.4.9** ("pin'le
> sabitlemen lazım"). Dört yüzeyde zaten `celldetection==0.4.9` pinli — birebir.
>
> **Geldiğinde yapılacak (her şey hazır bekliyor):** klasörü koy → gerçek-model
> smoke (paketteki referanslarla toleranslı doğrulama: CONTROL-0H 1494 hücre /
> %4.3, CONTROL-24H 2085 / %29.3) → Docker cu128 GPU smoke → yayın.

## Durum
- ⚠️ **`cell/` alt paketi HENÜZ YOK** (yukarıdaki teslim bekleniyor). Gelene kadar
  `CellSegmentationPredictor` açık `RuntimeError` verir; endpoint zarif 503 döner.
- Ağırlık: `ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt` (~872 MB) —
  `release_assets/ai_models/ai_hub/inference_paper_dilek_hoca/` tek-kaynağında;
  **hiçbir model-zip'ine girmez** (GitHub 2 GiB sınırı — renal emsali).
  Çözüm sırası: modül dizini → `pt_coz` (PEMF_AI_MODELS_DIR → model_downloader).

## Servis yüzü
`scratch_analiz(image_path, scratch_yonu="dikey"|"yatay", pixel_mm, explain,
xai_method)` — TEK girdiden çoklu görsel çıktı, bellek-içi base64 (disk yok),
tek-iş kilidi. Çıktı görselleri 1280px'e (3-panel 1920px) küçültülür (ham
örnekler 3-7 MB ölçüldü). `input_image_base64` her yanıtta döner (TIF UI'da
başka türlü gösterilemez). `n_cells==0` → yapılandırılmış `uyari` (kapı yok,
karar 0.3). Yatay yara → `closure_uyari` (closure dikey-yara varsayımlıdır).

## Sertleştirmeler (gelen koddan farklar)
- Global `torch.load` monkey-patch → `_cpn_yukleme_kapsami()` ile KAPSAMLI
  (yalnız ckpt yüklemesi; finally ile geri alınır) — Audit P3.
- `sys.path.insert` yok; paket-nitelikli importlar.
- Top-level import yalnız stdlib+numpy+cv2 (AST-testli — bekçi ai_hub'ı taramaz).

## Testler
`tests/test_scratch_postproc.py` — closure KESİN-değer + ROI yön + torch.load
kapsamı (sahte-stub) + AST + kilit + n_cells==0 + küçültme bekçisi; mutasyonlu.
Gerçek-model testleri cell/+PT gelince eklenir (toleranslı: hücre ±%2).
