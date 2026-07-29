"""
PEMF çekirdek → AI mikroservisi HTTP istemcisi (mikroservis Faz 3).

`PEMF_AI_SERVICE_URL` AYARLIYSA → AI inference'ı ayrı `pemf-ai` servisine (GPU) HTTP
ile devreder. YOKSA → çekirdek in-process çalışır (GERİYE UYUM: Mac/CPU demo, tek-EXE
klinik kurulumu, mevcut davranış HİÇ bozulmaz). Tek bayrakla monolit ↔ mikroservis.
"""
import os
import base64
import logging

import httpx

logger = logging.getLogger("ai_client")

AI_SERVICE_URL = os.environ.get("PEMF_AI_SERVICE_URL", "").rstrip("/")
_TIMEOUT = float(os.environ.get("PEMF_AI_SERVICE_TIMEOUT", "180"))


def ai_service_enabled() -> bool:
    """PEMF_AI_SERVICE_URL tanımlıysa AI çağrıları mikroservise devredilir."""
    return bool(AI_SERVICE_URL)


async def delegate_infer(name: str, file=None, image_base64: str = None,
                         audio_base64: str = None, csv_base64: str = None, data: dict = None):
    """Girdiyi (UploadFile veya base64) pemf-ai `/infer/<name>`'e multipart devret → JSON.

    name: pemf-ai uç adı (histopath|sound|kidney_ct|segmentation|landmark|thermal|cat_organ|
          rna|reticulocytes|em_fantom|em_petri).
    data: ek form alanları (ör. phantom_length_cm) — None değerler atlanır.
    Çağıran YALNIZCA ai_service_enabled() True iken çağırmalı.
    """
    b64 = image_base64 or audio_base64 or csv_base64
    if b64:
        content = base64.b64decode(b64)
        filename = "input.bin"
    elif file is not None:
        content = await file.read()
        filename = getattr(file, "filename", None) or "input.bin"
    else:
        raise ValueError("girdi yok (dosya/base64)")

    form = {k: str(v) for k, v in (data or {}).items() if v is not None}
    url = f"{AI_SERVICE_URL}/infer/{name}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, files={"file": (filename, content)}, data=form)
        resp.raise_for_status()
        return resp.json()


async def delegate_json(name: str, payload: dict):
    """JSON gövdeli AI ucunu (disease|kidney_disease) pemf-ai `/infer/<name>`'e devret → JSON."""
    url = f"{AI_SERVICE_URL}/infer/{name}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


# ── SENKRON varyantlar: AI Pro closed-loop (cat_organ + em_kedi) SENKRON fonksiyonlardan
#    (_localize_organ/_predict_and_drive, to_thread ile thread'de) çağrılır → httpx.Client (bloklayan).
#    Böylece AI Pro'nun AĞIR inference'ı da GPU servisine devredilir (Hoca yönü). Bkz ai_router. ──
def delegate_infer_sync(name: str, content: bytes, filename: str = "input.jpg", data: dict = None):
    """SENKRON multipart görüntü devri (pemf-ai `/infer/<name>` → JSON). content=ham bayt.
    YALNIZCA ai_service_enabled() True iken çağır; çağıran zaten thread'de (to_thread)."""
    form = {k: str(v) for k, v in (data or {}).items() if v is not None}
    url = f"{AI_SERVICE_URL}/infer/{name}"
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(url, files={"file": (filename, content)}, data=form)
        resp.raise_for_status()
        return resp.json()


def delegate_json_sync(name: str, payload: dict):
    """SENKRON JSON devri (pemf-ai `/infer/<name>` → JSON). AI Pro em_kedi sürüşü için."""
    url = f"{AI_SERVICE_URL}/infer/{name}"
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
