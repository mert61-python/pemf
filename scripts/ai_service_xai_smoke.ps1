# Author: mertaygn, cglrgrkn
# =============================================================================
# ai_service XAI SMOKE — cu128 IMAJ-ICI dogrulama (GPU makinesinde, YAYIN ONCESI)
# -----------------------------------------------------------------------------
# NEDEN: grad-cam/timm/captum pinleri torch 2.1.2+cpu ile OLCULDU; ai_service imaji
# torch 2.7.1+cu128 kosuyor (Dockerfile.ai). Saf-Python/torch-API katmani olduklarindan
# uyumsuzluk beklenmiyor AMA OLCULMEDI — bu betik imaji build edip explain uclarini
# GERCEK istekle dogrular (xai-entegrasyon-plani.md §5 kalan is).
#
# ON-KOSULLAR (GPU makinesi): Docker + NVIDIA Container Toolkit; PT ikizleri
# release_assets/ai_models altinda (PEMF_AI_MODELS_DIR mount'una girer).
# KULLANIM:  powershell -File scripts\ai_service_xai_smoke.ps1
# =============================================================================
$ErrorActionPreference = "Stop"
$KOK = Split-Path -Parent $PSScriptRoot
$MODELS = Join-Path $KOK "release_assets\ai_models"
$IMAJ = "pemf-ai:xai-smoke"

Write-Host "== 1/4 imaj build (Dockerfile.ai) =="
docker build -f (Join-Path $KOK "docker\Dockerfile.ai") -t $IMAJ $KOK

Write-Host "== 2/4 konteyner baslat (GPU + /models mount) =="
docker rm -f pemf-ai-xai-smoke 2>$null | Out-Null
docker run -d --name pemf-ai-xai-smoke --gpus all -p 18100:8100 `
    -e PEMF_AI_MODELS_DIR=/models -v "${MODELS}:/models:ro" $IMAJ
Start-Sleep -Seconds 25

Write-Host "== 3/4 saglik + cift-cv2 kontrolu =="
$h = Invoke-RestMethod "http://127.0.0.1:18100/health" -TimeoutSec 30
Write-Host ("health: " + ($h | ConvertTo-Json -Compress))
docker exec pemf-ai-xai-smoke python -c "import cv2, pytorch_grad_cam, timm, captum; print('cv2', cv2.__version__, '| xai importlari OK')"

Write-Host "== 4/4 explain smoke (termal Grad-CAM, GERCEK PT + GPU) =="
$tmp = Join-Path $env:TEMP "xai_smoke_termal.jpg"
docker exec pemf-ai-xai-smoke python - <<'PY'
import numpy as np, cv2
yy, xx = np.mgrid[0:224, 0:224].astype(np.float32)
s = np.exp(-(((yy-112)**2 + (xx-112)**2) / (2*40.0**2)))
img = np.stack([(1-s)*180, s*120, s*255], axis=-1).astype(np.uint8)
cv2.imwrite("/tmp/t.jpg", img)
PY
$json = docker exec pemf-ai-xai-smoke python - <<'PY'
import requests
r = requests.post("http://127.0.0.1:8100/infer/thermal",
                  files={"file": ("t.jpg", open("/tmp/t.jpg","rb"), "image/jpeg")},
                  data={"explain": "true"}, timeout=120)
b = r.json()
assert r.status_code == 200 and b.get("status") == "success", b
assert b.get("xai_image_base64"), f"xai alani yok: {list(b)}"
print("SMOKE-OK device=", b.get("device"), " inference_ms=", b.get("inference_ms"))
PY
Write-Host $json
if ($json -notmatch "SMOKE-OK") { throw "XAI smoke BASARISIZ" }

Write-Host "== TAMAM — konteyner temizleniyor =="
docker rm -f pemf-ai-xai-smoke | Out-Null
Write-Host "cu128 XAI smoke GECTI ✅ (yayina hazir)"
