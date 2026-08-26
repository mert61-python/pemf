# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ai_service XAI smoke istegi — HOST tarafindan calisir (bkz. ai_service_xai_smoke.ps1).

Sentetik sicak-merkezli 'termal' goruntu uretir, http://127.0.0.1:18100/infer/thermal'e
explain=true multipart POST atar; xai_image_base64'un GERCEK/tekduze-olmayan bir gorsel
oldugunu dogrular. Basari cikti: 'SMOKE-OK device=...'.
(2026-08-26: ps1-ici here-string PS5.1'de LF dosyada parse edilemedi -> ayri dosya.)
"""

import base64
import json
import urllib.request

import cv2
import numpy as np

yy, xx = np.mgrid[0:224, 0:224].astype(np.float32)
s = np.exp(-(((yy - 112) ** 2 + (xx - 112) ** 2) / (2 * 40.0**2)))
img = np.stack([(1 - s) * 180, s * 120, s * 255], axis=-1).astype(np.uint8)
ok, buf = cv2.imencode(".jpg", img)
assert ok

sinir = b"----pemfsmoke"
govde = b"--" + sinir + b"\r\n"
govde += b'Content-Disposition: form-data; name="file"; filename="t.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
govde += buf.tobytes() + b"\r\n--" + sinir + b"\r\n"
govde += b'Content-Disposition: form-data; name="explain"\r\n\r\ntrue\r\n'
govde += b"--" + sinir + b"--\r\n"

req = urllib.request.Request(
    "http://127.0.0.1:18100/infer/thermal",
    data=govde,
    headers={"Content-Type": "multipart/form-data; boundary=" + sinir.decode()},
)
with urllib.request.urlopen(req, timeout=180) as r:
    b = json.load(r)

assert b.get("status") == "success", b
assert b.get("xai_image_base64"), f"xai alani yok: {list(b)}"
ov = cv2.imdecode(np.frombuffer(base64.b64decode(b["xai_image_base64"]), np.uint8), cv2.IMREAD_COLOR)
assert ov is not None and float(ov.std()) > 1.0, "isi haritasi bos/tekduze"
print("SMOKE-OK device=", b.get("device"), " inference_ms=", b.get("inference_ms"), " method=", b.get("xai_method"))
