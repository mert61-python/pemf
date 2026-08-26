# Author: mertaygn, cglrgrkn
# =============================================================================
# ai_service XAI SMOKE — cu128 IMAJ-ICI dogrulama (GPU makinesinde, YAYIN ONCESI)
# -----------------------------------------------------------------------------
# NEDEN: grad-cam/timm/captum pinleri torch 2.1.2+cpu ile OLCULDU; ai_service imaji
# torch cu128 kosuyor (Dockerfile.ai). Bu betik imaji build edip explain ucunu GERCEK
# istekle dogrular (xai-entegrasyon-plani.md §5).
#
# ON-KOSULLAR: Docker (WSL2 backend) + NVIDIA suruculeri. PT ikizleri release_assets
# altinda (mount'a girer). Testi HOST python'u atar (docker-exec heredoc YOK —
# 2026-08-26: ilk surumdeki bash-heredoc PowerShell'de gecersizdi, duzeltildi).
# KULLANIM:  powershell -File scripts\ai_service_xai_smoke.ps1
# =============================================================================
$ErrorActionPreference = "Stop"
$KOK = Split-Path -Parent $PSScriptRoot
$MODELS = Join-Path $KOK "release_assets\ai_models"
$IMAJ = "pemf-ai:xai-smoke"
$PY = Join-Path (Split-Path -Parent $KOK) "python.exe"
if (-not (Test-Path $PY)) { $PY = "python" }
$DOCKER = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
if (-not (Test-Path $DOCKER)) { $DOCKER = "docker" }

Write-Host "== 1/4 imaj build (Dockerfile.ai) =="
& $DOCKER build -f (Join-Path $KOK "docker\Dockerfile.ai") -t $IMAJ $KOK
if ($LASTEXITCODE -ne 0) { throw "imaj build BASARISIZ" }

Write-Host "== 2/4 konteyner baslat (GPU + /models mount) =="
& $DOCKER rm -f pemf-ai-xai-smoke 2>$null | Out-Null
& $DOCKER run -d --name pemf-ai-xai-smoke --gpus all -p 18100:8100 `
    -e PEMF_AI_MODELS_DIR=/models -v "${MODELS}:/models:ro" $IMAJ
if ($LASTEXITCODE -ne 0) { throw "konteyner baslatilamadi (--gpus destegini kontrol edin)" }
Start-Sleep -Seconds 30

Write-Host "== 3/4 saglik + XAI import + cift-cv2 kontrolu (imaj ICI) =="
$h = Invoke-RestMethod "http://127.0.0.1:18100/health" -TimeoutSec 60
Write-Host ("health: " + ($h | ConvertTo-Json -Compress -Depth 3))
& $DOCKER exec pemf-ai-xai-smoke python3 -c "import cv2, pytorch_grad_cam, timm, captum, torch; print('cv2', cv2.__version__, '| torch', torch.__version__, '| cuda:', torch.cuda.is_available(), '| xai importlari OK')"
if ($LASTEXITCODE -ne 0) { throw "imaj-ici XAI importlari BASARISIZ (cift-cv2 / pin uyumsuzlugu?)" }

Write-Host "== 4/4 explain smoke (termal Grad-CAM, GERCEK PT — HOST'tan istek) =="
# Istek kodu AYRI dosyada (ai_service_xai_smoke_istek.py): ps1-ici here-string PS5.1'de
# LF-satirsonlu dosyada parse edilemiyordu (2026-08-26 olcumu).
$smokePy = Join-Path $PSScriptRoot "ai_service_xai_smoke_istek.py"
$sonuc = & $PY $smokePy 2>&1
Write-Host $sonuc
if ($sonuc -notmatch "SMOKE-OK") { & $DOCKER logs --tail 40 pemf-ai-xai-smoke; throw "XAI smoke BASARISIZ" }

Write-Host "== TAMAM — konteyner temizleniyor =="
& $DOCKER rm -f pemf-ai-xai-smoke | Out-Null
Write-Host "cu128 XAI smoke GECTI (yayina hazir)"
