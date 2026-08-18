#!/usr/bin/env python3
"""
training_cat_landmark.py — YOLO Cat Facial Landmark Detection
=============================================================
48 keypoint detection on cat faces using YOLO pose models.
Dataset: CatFLW (2079 images, 48 landmarks per face)
Models: YOLOv8, YOLO11, YOLO26 (nano, small, medium) pose variants

Output: /home/user02/dr/models/models_cat_landmark/
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
DATASET_YAML = "/home/user02/dr/dataset/cat_landmark/yolo_pose/data.yaml"
MODELS_DIR = "/home/user02/dr/models/models_cat_landmark"
RESULTS_CSV = os.path.join(MODELS_DIR, "model_cat_landmark_karsilastirma.csv")
DEVICE = 0
SEED = 42
IMGSZ = 640
WORKERS = 4

# 9 YOLO pose models
MODELS = {
    "yolov8n-pose": {"epochs": 300, "batch": 16},
    "yolov8s-pose": {"epochs": 300, "batch": 16},
    "yolov8m-pose": {"epochs": 300, "batch": 8},
    "yolo11n-pose": {"epochs": 300, "batch": 16},
    "yolo11s-pose": {"epochs": 300, "batch": 16},
    "yolo11m-pose": {"epochs": 300, "batch": 8},
    "yolo26n-pose": {"epochs": 300, "batch": 16},
    "yolo26s-pose": {"epochs": 300, "batch": 16},
    "yolo26m-pose": {"epochs": 300, "batch": 8},
}

CSV_COLS = [
    "Model", "mAP50_box", "mAP50_95_box", "mAP50_pose", "mAP50_95_pose",
    "Precision_box", "Recall_box",
    "Params_M", "GFLOPs", "ModelSize_MB",
    "Train_Time_s", "Inference_ms", "FPS",
    "Epochs", "Best_Epoch", "Imgsz",
]

os.makedirs(MODELS_DIR, exist_ok=True)

print("=" * 80)
print("YOLO CAT FACIAL LANDMARK DETECTION")
print(f"Dataset: {DATASET_YAML}")
print(f"48 keypoints | {len(MODELS)} models")
print(f"Device: cuda:{DEVICE}")
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

    if os.path.exists(best_pt):
        print(f"  Mevcut model: {best_pt}, skip training...")
        model = YOLO(best_pt)
    else:
        if os.path.exists(last_pt):
            print(f"  RESUME: {last_pt}")
            model = YOLO(last_pt)
        else:
            model = YOLO(f"{model_name}.pt")

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
            patience=10,
        )
        train_time = time.time() - t0
        print(f"\n  Train time: {train_time:.1f}s")
        model = YOLO(best_pt)

    # ---- Evaluate ----
    print(f"\n  Validating...")
    val_results = model.val(
        data=DATASET_YAML,
        imgsz=IMGSZ,
        batch=cfg["batch"],
        device=DEVICE,
        split="val",
    )

    # Box metrics
    box_map50 = float(val_results.box.map50) if hasattr(val_results, 'box') else 0.0
    box_map50_95 = float(val_results.box.map) if hasattr(val_results, 'box') else 0.0
    box_precision = float(val_results.box.mp) if hasattr(val_results, 'box') else 0.0
    box_recall = float(val_results.box.mr) if hasattr(val_results, 'box') else 0.0

    # Pose/keypoint metrics
    pose_map50 = float(val_results.pose.map50) if hasattr(val_results, 'pose') else 0.0
    pose_map50_95 = float(val_results.pose.map) if hasattr(val_results, 'pose') else 0.0

    # Model info
    params_m = sum(p.numel() for p in model.model.parameters()) / 1e6
    model_size_mb = os.path.getsize(best_pt) / (1024 * 1024) if os.path.exists(best_pt) else 0

    try:
        gflops = float(model.info(verbose=False)[1])
    except:
        gflops = 0.0

    # Inference speed
    print(f"\n  Inference benchmark...")
    try:
        import glob
        test_images = glob.glob(os.path.join(os.path.dirname(DATASET_YAML), "test", "images", "*.png"))[:20]
        if test_images:
            times = []
            for _ in range(3):
                model.predict(test_images[0], verbose=False, device=DEVICE)
            for img in test_images:
                t0 = time.time()
                model.predict(img, verbose=False, device=DEVICE)
                times.append((time.time() - t0) * 1000)
            inference_ms = float(np.mean(times))
            fps = 1000.0 / inference_ms if inference_ms > 0 else 0
        else:
            inference_ms = 0
            fps = 0
    except:
        inference_ms = 0
        fps = 0

    # Best epoch
    best_epoch = 0
    results_csv_path = os.path.join(run_dir, "results.csv")
    if os.path.exists(results_csv_path):
        try:
            rdf = pd.read_csv(results_csv_path)
            rdf.columns = [c.strip() for c in rdf.columns]
            pose_col = [c for c in rdf.columns if 'pose' in c.lower() and 'map50' in c.lower()]
            if pose_col:
                best_epoch = int(rdf[pose_col[0]].idxmax()) + 1
            else:
                best_epoch = len(rdf)
        except:
            best_epoch = 0

    if 'train_time' not in dir():
        train_time = 0.0

    row = {
        "Model": model_name,
        "mAP50_box": box_map50,
        "mAP50_95_box": box_map50_95,
        "mAP50_pose": pose_map50,
        "mAP50_95_pose": pose_map50_95,
        "Precision_box": box_precision,
        "Recall_box": box_recall,
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
    print(f"    Box  — mAP50: {box_map50:.4f} | mAP50-95: {box_map50_95:.4f}")
    print(f"    Pose — mAP50: {pose_map50:.4f} | mAP50-95: {pose_map50_95:.4f}")
    print(f"    Speed: {inference_ms:.1f}ms ({fps:.0f} FPS) | Params: {params_m:.1f}M")

    # Save incremental (merge)
    _new = pd.DataFrame(results_list)
    if os.path.exists(RESULTS_CSV):
        _old = pd.read_csv(RESULTS_CSV)
        _keep = _old[~_old['Model'].isin(_new['Model'].values)]
        _merged = pd.concat([_keep, _new], ignore_index=True)
        _merged.to_csv(RESULTS_CSV, index=False)
    else:
        _new.to_csv(RESULTS_CSV, index=False)

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
if os.path.exists(RESULTS_CSV):
    _old = pd.read_csv(RESULTS_CSV)
    _keep = _old[~_old['Model'].isin(df['Model'].values)]
    df = pd.concat([_keep, df], ignore_index=True)
df = df.sort_values("mAP50_95_pose", ascending=False)
df.to_csv(RESULTS_CSV, index=False)

td = [[r["Model"],
       f"{r['mAP50_box']:.4f}", f"{r['mAP50_95_box']:.4f}",
       f"{r['mAP50_pose']:.4f}", f"{r['mAP50_95_pose']:.4f}",
       f"{r['Params_M']}M", f"{r['Inference_ms']:.1f}ms", f"{r['FPS']:.0f}"]
      for _, r in df.iterrows()]

print(tabulate(td, headers=["Model", "mAP50_box", "mAP50-95_box",
                              "mAP50_pose", "mAP50-95_pose",
                              "Params", "Infer", "FPS"],
               tablefmt="simple_grid", stralign="right"))

best = df.iloc[0]
print(f"\nEN IYI -> {best['Model']} | Pose mAP50-95: {best['mAP50_95_pose']:.4f}")


# ============================================================
# EXPORT BEST + COPY TO INFERENCE
# ============================================================
print(f"\n{'='*80}")
print("EN IYI MODEL -> inference")
print(f"{'='*80}")

best_name = best["Model"]
best_pt = os.path.join(MODELS_DIR, best_name, "weights", "best.pt")
inf_dir = "/home/user02/dr/inference/inference_cat_landmark"

if os.path.exists(best_pt):
    shutil.copy(best_pt, os.path.join(inf_dir, f"{best_name}.pt"))
    print(f"  -> {inf_dir}/{best_name}.pt")

# Experiment config
config = {
    "task": "keypoint_detection",
    "dataset": DATASET_YAML,
    "keypoints": 48,
    "models": list(MODELS.keys()),
    "device": f"cuda:{DEVICE}",
    "imgsz": IMGSZ,
    "best_model": best_name,
}
with open(os.path.join(MODELS_DIR, "experiment_config.json"), "w") as f:
    json.dump(config, f, indent=2)

print(f"\n{'='*80}")
print(f"TAMAMLANDI -> {RESULTS_CSV}")
print(f"{'='*80}")
