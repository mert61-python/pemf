#!/usr/bin/env python3
"""
training.py — YOLO Feline Reticulocytes Detection Benchmark
================================================================
9 YOLO models: v8, v11, v26 (nano, small, medium)
Dataset: feline_reticulocytes (923 train, 163 val, 160 test)
Task: Object Detection (3 classes: erythrocyte, punctate reticulocyte, aggregate reticulocyte)

Output: /home/user02/dr/models/models_feline_reticulocytes/
"""

import os
import sys
import time
import json
import shutil
import numpy as np
import pandas as pd
from tabulate import tabulate

# ============================================================
# CONFIG
# ============================================================
DATASET_YAML = "/home/user02/dr/dataset/feline_reticulocytes_yolo/data.yaml"
MODELS_DIR = "/home/user02/dr/models/models_feline_reticulocytes"
RESULTS_CSV = os.path.join(MODELS_DIR, "model_feline_ret_karsilastirma.csv")
DEVICE = 0  # GPU 0
SEED = 42
IMGSZ = 640
WORKERS = 4

# 9 YOLO detection models: v8, v11, v26 (nano, small, medium)
MODELS = {
    # YOLOv8
    "yolov8n": {"epochs": 300, "batch": 32},
    "yolov8s": {"epochs": 300, "batch": 32},
    "yolov8m": {"epochs": 300, "batch": 16},
    # YOLO11
    "yolo11n": {"epochs": 300, "batch": 32},
    "yolo11s": {"epochs": 300, "batch": 32},
    "yolo11m": {"epochs": 300, "batch": 16},
    # YOLO26
    "yolo26n": {"epochs": 300, "batch": 32},
    "yolo26s": {"epochs": 300, "batch": 32},
    "yolo26m": {"epochs": 300, "batch": 16},
}

CSV_COLS = [
    "Model", "mAP50", "mAP50_95",
    "Precision", "Recall", "F1",
    "Params_M", "GFLOPs", "ModelSize_MB",
    "Train_Time_s", "Inference_ms", "FPS",
    "Epochs", "Best_Epoch", "Imgsz",
]

os.makedirs(MODELS_DIR, exist_ok=True)

# Fix data.yaml paths
def fix_data_yaml():
    """Fix data.yaml to use absolute paths."""
    import yaml
    with open(DATASET_YAML) as f:
        data = yaml.safe_load(f)

    base = os.path.dirname(DATASET_YAML)
    changed = False
    for key in ['train', 'val', 'test']:
        if key in data and not os.path.isabs(data[key]):
            data[key] = os.path.abspath(os.path.join(base, data[key]))
            changed = True

    if changed:
        with open(DATASET_YAML, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
        print(f"data.yaml paths fixed (absolute)")

fix_data_yaml()

print("=" * 80)
print("YOLO26 CAT SEGMENTATION BENCHMARK")
print(f"Dataset: {DATASET_YAML}")
print(f"Models: {list(MODELS.keys())}")
print(f"Device: cuda:{DEVICE}")
print(f"Image size: {IMGSZ}")
print("=" * 80)


# ============================================================
# TRAINING
# ============================================================
from ultralytics import YOLO

results_list = []

for i, (model_name, cfg) in enumerate(MODELS.items(), 1):
    print(f"\n{'='*80}")
    print(f"[{i}/{len(MODELS)}] {model_name}")
    print(f"  Epochs: {cfg['epochs']}, Batch: {cfg['batch']}")
    print(f"{'='*80}\n")

    run_dir = os.path.join(MODELS_DIR, model_name)
    best_pt = os.path.join(run_dir, "weights", "best.pt")

    last_pt = os.path.join(run_dir, "weights", "last.pt")

    # Skip if already trained (best.pt exists)
    if os.path.exists(best_pt):
        print(f"  Mevcut model: {best_pt}, skip training...")
        model = YOLO(best_pt)
    else:
        # Resume from last.pt if exists (yarida kalmis egitim)
        if os.path.exists(last_pt):
            print(f"  RESUME: {last_pt} bulundu, kaldigi yerden devam...")
            model = YOLO(last_pt)
        else:
            # Load pretrained
            model = YOLO(f"{model_name}.pt")

        # Train (resume=True if last.pt exists)
        t0 = time.time()
        train_results = model.train(
            resume=os.path.exists(last_pt),
            data=DATASET_YAML,
            epochs=cfg["epochs"],
            imgsz=IMGSZ,
            batch=cfg["batch"],
            device=DEVICE,
            workers=WORKERS,
            seed=SEED,
            project=MODELS_DIR,
            name=model_name,
            exist_ok=True,
            verbose=True,
            save=True,
            save_period=10,
            patience=10,        # early stopping: 10 epoch iyilesme yoksa dur
        )
        train_time = time.time() - t0
        print(f"\n  Train time: {train_time:.1f}s")

        # Load best model
        model = YOLO(best_pt)

    # ---- Evaluate on val (plots=True -> gorselleri uretir) ----
    print(f"\n  Validating...")
    val_results = model.val(
        data=DATASET_YAML,
        imgsz=IMGSZ,
        batch=cfg["batch"],
        device=DEVICE,
        split="val",
    )

    # Extract metrics (detection only — no mask)
    map50 = float(val_results.box.map50) if hasattr(val_results, 'box') else 0.0
    map50_95 = float(val_results.box.map) if hasattr(val_results, 'box') else 0.0
    precision = float(val_results.box.mp) if hasattr(val_results, 'box') else 0.0
    recall = float(val_results.box.mr) if hasattr(val_results, 'box') else 0.0
    f1 = 2 * precision * recall / (precision + recall + 1e-8)

    # Model info
    params_m = sum(p.numel() for p in model.model.parameters()) / 1e6
    model_size_mb = os.path.getsize(best_pt) / (1024 * 1024) if os.path.exists(best_pt) else 0

    # GFLOPs
    try:
        gflops = float(model.info(verbose=False)[1])
    except:
        gflops = 0.0

    # Inference speed
    # Simple inference timing (benchmark() kaldirildi — TensorRT GPU memory dolduruyor)
    print(f"\n  Inference timing...")
    import glob
    test_images = glob.glob(os.path.join(os.path.dirname(DATASET_YAML), "test_microcam", "images", "*.jpg"))[:20]
    if test_images:
        for _ in range(3):  # warmup
            model.predict(test_images[0], verbose=False, device=DEVICE)
        times = []
        for img in test_images:
            t0 = time.time()
            model.predict(img, verbose=False, device=DEVICE)
            times.append((time.time() - t0) * 1000)
        inference_ms = float(np.mean(times))
        fps = 1000.0 / inference_ms if inference_ms > 0 else 0
    else:
        inference_ms = 0
        fps = 0

    # Best epoch
    best_epoch = 0
    results_csv_path = os.path.join(run_dir, "results.csv")
    if os.path.exists(results_csv_path):
        try:
            rdf = pd.read_csv(results_csv_path)
            rdf.columns = [c.strip() for c in rdf.columns]
            # Find box mAP50 column
            map_col = [c for c in rdf.columns if 'map50' in c.lower() and '95' not in c.lower() and 'mask' not in c.lower()]
            if map_col:
                best_epoch = int(rdf[map_col[0]].idxmax()) + 1
            else:
                best_epoch = len(rdf)
        except:
            best_epoch = 0

    # Train time
    if not os.path.exists(best_pt) or 'train_time' not in dir():
        train_time = 0.0

    row = {
        "Model": model_name,
        "mAP50": map50,
        "mAP50_95": map50_95,
        "Precision": precision,
        "Recall": recall,
        "F1": f1,
        "Params_M": round(params_m, 1),
        "GFLOPs": round(gflops, 1),
        "ModelSize_MB": round(model_size_mb, 1),
        "Train_Time_s": round(train_time, 1),
        "Inference_ms": round(inference_ms, 1),
        "FPS": round(fps, 1),
        "Epochs": cfg["epochs"],
        "Best_Epoch": best_epoch,
        "Imgsz": IMGSZ,
    }
    results_list.append(row)

    print(f"\n  Results:")
    print(f"    mAP50: {map50:.4f} | mAP50-95: {map50_95:.4f} | P: {precision:.4f} | R: {recall:.4f} | F1: {f1:.4f}")
    print(f"    Speed: {inference_ms:.1f}ms ({fps:.0f} FPS) | Params: {params_m:.1f}M | Size: {model_size_mb:.1f}MB")

    # Save incremental (merge with existing CSV)
    _new = pd.DataFrame(results_list)
    if os.path.exists(RESULTS_CSV):
        _old = pd.read_csv(RESULTS_CSV)
        _keep = _old[~_old['Model'].isin(_new['Model'].values)]
        _merged = pd.concat([_keep, _new], ignore_index=True)
        _merged.to_csv(RESULTS_CSV, index=False)
    else:
        _new.to_csv(RESULTS_CSV, index=False)
    print(f"  -> {RESULTS_CSV}")

    # Cleanup
    del model
    import torch
    torch.cuda.empty_cache()
    import gc
    gc.collect()


# ============================================================
# FINAL TABLE
# ============================================================
print(f"\n\n{'='*80}")
print("SONUC TABLOSU")
print(f"{'='*80}")

df = pd.DataFrame(results_list)
# Merge with existing CSV (don't overwrite)
if os.path.exists(RESULTS_CSV):
    _old = pd.read_csv(RESULTS_CSV)
    _keep = _old[~_old['Model'].isin(df['Model'].values)]
    df = pd.concat([_keep, df], ignore_index=True)
df = df.sort_values("mAP50_95", ascending=False).reset_index(drop=True)
df.to_csv(RESULTS_CSV, index=False)

td = [[r["Model"],
       f"{r['mAP50']:.4f}", f"{r['mAP50_95']:.4f}",
       f"{r['F1']:.4f}",
       f"{r['Params_M']}M", f"{r['Inference_ms']:.1f}ms",
       f"{r['FPS']:.0f}"]
      for _, r in df.iterrows()]

print(tabulate(td, headers=["Model", "mAP50", "mAP50-95", "F1",
                              "Params", "Infer", "FPS"],
               tablefmt="simple_grid", stralign="right"))

best = df.iloc[0]
print(f"\nEN IYI -> {best['Model']} | mAP50-95: {best['mAP50_95']:.4f}")


# ============================================================
# EXPORT BEST MODEL TO ONNX
# ============================================================
print(f"\n{'='*80}")
print("ONNX EXPORT (en iyi model)")
print(f"{'='*80}")

best_name = best["Model"]
best_pt = os.path.join(MODELS_DIR, best_name, "weights", "best.pt")
if os.path.exists(best_pt):
    model = YOLO(best_pt)
    onnx_path = model.export(format="onnx", imgsz=IMGSZ, device=DEVICE)
    # Copy to inference dir
    inf_dir = "/home/user02/dr/inference/inference_feline_reticulocytes"
    if onnx_path and os.path.exists(onnx_path):
        shutil.copy(onnx_path, os.path.join(inf_dir, f"{best_name}.onnx"))
        shutil.copy(best_pt, os.path.join(inf_dir, f"{best_name}.pt"))
        print(f"  -> {inf_dir}/{best_name}.onnx")
        print(f"  -> {inf_dir}/{best_name}.pt")


# ============================================================
# PREDICTIONS ON TEST SET (top model)
# ============================================================
print(f"\n{'='*80}")
print("TEST SET PREDICTION (en iyi model)")
print(f"{'='*80}")

import glob
test_dir = os.path.join(os.path.dirname(DATASET_YAML), "test", "images")
test_images = sorted(glob.glob(os.path.join(test_dir, "*.jpg")))

if test_images and os.path.exists(best_pt):
    model = YOLO(best_pt)
    pred_dir = os.path.join(MODELS_DIR, "test_predictions")
    os.makedirs(pred_dir, exist_ok=True)

    results = model.predict(
        source=test_dir,
        imgsz=IMGSZ,
        device=DEVICE,
        save=True,
        save_txt=True,
        project=MODELS_DIR,
        name="test_predictions",
        exist_ok=True,
    )
    print(f"  {len(test_images)} test goruntu tahmin edildi -> {pred_dir}")


# ============================================================
# EXPERIMENT CONFIG
# ============================================================
config = {
    "task": "instance_segmentation",
    "dataset": DATASET_YAML,
    "models": list(MODELS.keys()),
    "device": f"cuda:{DEVICE}",
    "imgsz": IMGSZ,
    "seed": SEED,
    "framework": "ultralytics",
    "results_csv": RESULTS_CSV,
}
with open(os.path.join(MODELS_DIR, "experiment_config.json"), "w") as f:
    json.dump(config, f, indent=2)

print(f"\n{'='*80}")
print(f"TUM EGITIM TAMAMLANDI -> {RESULTS_CSV}")
print(f"{'='*80}")
