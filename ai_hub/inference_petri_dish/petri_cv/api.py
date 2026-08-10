# Author: mertaygn, cglrgrkn
"""api.py — FastAPI REST endpoint.

Calistir:
  uvicorn petri_cv.api:app --host 0.0.0.0 --port 8765

Veya config'den okuyarak:
  python -m petri_cv.api --config config.yaml

Endpoint'ler:
  GET  /health                     -> {"status": "ok"}
  GET  /config                     -> aktif yapilandirma
  POST /detect/file                -> {image_path} -> PipelineResult
  POST /detect/upload              -> multipart image -> PipelineResult
  POST /detect/camera              -> /dev/video0'dan tek frame -> PipelineResult
"""
from __future__ import annotations
import io
import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from fastapi import FastAPI, File, HTTPException, UploadFile
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except ImportError:        # pragma: no cover
    raise SystemExit(
        "FastAPI eksik. Yukle: pip install 'fastapi[all]' uvicorn"
    )

from .pipeline import PetriCvPipeline


_CONFIG_ENV = "PHANTOM_CV_CONFIG"
app = FastAPI(title="petri_cv", version="0.1.0")
_pipeline: PetriCvPipeline | None = None


def get_pipeline() -> PetriCvPipeline:
    global _pipeline
    if _pipeline is None:
        cfg_path = os.environ.get(_CONFIG_ENV)
        _pipeline = PetriCvPipeline(cfg_path)
    return _pipeline


class DetectFileRequest(BaseModel):
    image_path: str
    achieved_B: float | None = None
    duty_sum: float | None = None


class DetectCameraRequest(BaseModel):
    device_index: int = 0
    warmup_frames: int = 5
    achieved_B: float | None = None
    duty_sum: float | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "petri_cv"}


@app.get("/config")
def get_config() -> dict[str, Any]:
    pl = get_pipeline()
    intr = pl.intrinsics
    return {
        "cabin_id": pl.cfg.cabin_id,
        "source_path": pl.cfg.source_path,
        "summary": pl.cfg.summary(),
        "aruco": {"dict": pl.cfg.aruco.dict,
                  "real_cm": pl.cfg.aruco.real_cm,
                  "normal_axis": pl.cfg.aruco.normal_axis_in_cabin},
        "geometry": {"qr_to_origin_cm": pl.cfg.geometry.qr_to_origin_cm,
                     "cabin_extent_cm": pl.cfg.geometry.cabin_extent_cm,
                     "axes": pl.cfg.geometry.axes},
        "camera": {"fixed_position_cm": pl.cfg.camera.fixed_position_cm,
                   "to_marker_cm": pl.cfg.camera.to_marker_cm,
                   "to_origin_cm": pl.cfg.camera.to_origin_cm,
                   "intrinsics_loaded": intr is not None,
                   "rms": (intr.rms if intr is not None else None)},
    }


@app.post("/detect/file")
def detect_file(req: DetectFileRequest) -> JSONResponse:
    pl = get_pipeline()
    if not Path(req.image_path).exists():
        raise HTTPException(status_code=404,
                            detail=f"image_not_found: {req.image_path}")
    result, _ = pl.process_file(
        req.image_path,
        achieved_B=req.achieved_B, duty_sum=req.duty_sum,
    )
    return JSONResponse(content=result.to_dict())


@app.post("/detect/upload")
async def detect_upload(file: UploadFile = File(...)) -> JSONResponse:
    pl = get_pipeline()
    data = await file.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="image_decode_fail")
    result, _ = pl.process_image(img)
    return JSONResponse(content=result.to_dict())


@app.post("/detect/camera")
def detect_camera(req: DetectCameraRequest) -> JSONResponse:
    pl = get_pipeline()
    cap = cv2.VideoCapture(req.device_index)
    if not cap.isOpened():
        raise HTTPException(status_code=503,
                            detail=f"camera_open_fail: {req.device_index}")
    try:
        for _ in range(max(0, req.warmup_frames)):
            cap.read()
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok:
        raise HTTPException(status_code=503, detail="camera_read_fail")
    result, _ = pl.process_image(
        frame, achieved_B=req.achieved_B, duty_sum=req.duty_sum,
    )
    return JSONResponse(content=result.to_dict())


def main():
    import argparse
    import uvicorn
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    args = p.parse_args()

    if args.config:
        os.environ[_CONFIG_ENV] = args.config

    pl = get_pipeline()
    host = args.host or pl.cfg.output.fastapi_host
    port = args.port or pl.cfg.output.fastapi_port
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
