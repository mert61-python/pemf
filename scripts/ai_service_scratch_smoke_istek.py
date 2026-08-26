# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ai_service SCRATCH smoke istegi — HOST'tan calisir (GPU imaj dogrulamasi).

GERCEK CONTROL-24H TIF'ini http://127.0.0.1:18100/infer/scratch'e explain=true
multipart POST eder; kapanma metriklerini SAHIP REFERANSLARIYLA toleransli
karsilastirir (2085 hucre / %29.3 / 428um) ve 6 gorselin gercek/boyutlu
oldugunu dogrular. Basari: 'SCRATCH-SMOKE-OK device=...'.
"""

import base64
import json
import sys
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
TIF = KOK / "ai_hub" / "PEMF_AI_Test_Girdileri" / "12b_YaraKapanma_24H.tif"
veri = TIF.read_bytes()

sinir = b"----pemfscratch"
govde = b""
for ad, deger in (("scratch_yonu", b"dikey"), ("pixel_mm", b"0.0016"), ("explain", b"true")):
    govde += b"--" + sinir + b"\r\n"
    govde += ('Content-Disposition: form-data; name="%s"\r\n\r\n' % ad).encode() + deger + b"\r\n"
govde += b"--" + sinir + b"\r\n"
govde += b'Content-Disposition: form-data; name="file"; filename="24h.tif"\r\n'
govde += b"Content-Type: image/tiff\r\n\r\n" + veri + b"\r\n"
govde += b"--" + sinir + b"--\r\n"

req = urllib.request.Request(
    "http://127.0.0.1:18100/infer/scratch",
    data=govde,
    headers={"Content-Type": "multipart/form-data; boundary=" + sinir.decode()},
)
with urllib.request.urlopen(req, timeout=300) as r:
    b = json.load(r)

assert b.get("status") == "success", b
c = b.get("closure") or {}
assert abs(b["n_cells"] - 2085) <= 2085 * 0.02, f"hucre sapti: {b['n_cells']}"
assert abs(c.get("closure_pct", 0) - 29.3) <= 0.5, f"kapanma sapti: {c}"
assert abs(c.get("mean_gap_um", 0) - 428.0) <= 428.0 * 0.05, f"gap sapti: {c}"
for alan in (
    "input_image_base64",
    "seg_image_base64",
    "overlay_image_base64",
    "analysis_image_base64",
    "closure_image_base64",
    "xai_image_base64",
):
    ham = b.get(alan)
    assert ham and len(base64.b64decode(ham)) > 5000, f"gorsel bos/eksik: {alan}"
print(
    "SCRATCH-SMOKE-OK device=",
    b.get("device"),
    " inference_ms=",
    b.get("inference_ms"),
    " hucre=",
    b["n_cells"],
    " kapanma=%",
    c.get("closure_pct"),
    " xai=",
    b.get("xai_method"),
)
sys.exit(0)
