# inference_paper_dilek_hoca — Yara Kapanma (Scratch) Analizi

CPN (Contour Proposal Network, `celldetection`, Apache-2.0) ResNeXt-101 UNet ile
hücre instance segmentasyonu + TScratch-benzeri **wound-closure metrikleri**
(closure %, ort/maks gap µm, gap alanı mm²) — PEMF çalışmasının primary endpoint'i.

Plan ve sahip kararları: `guii/scratch-entegrasyon-plani.md` (v3, kararlar KESİN).

## Durum
- ⚠️ **`cell/` alt paketi HENÜZ YOK** — teslim paketinde kırık POSIX symlink'ti
  (CpnInterface + `multi_norm` sahibin eğitim deposunda). Gelene kadar
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
