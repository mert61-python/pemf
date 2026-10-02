# Author: mertaygn, cglrgrkn
"""
PEMF çekirdek → AI mikroservisi HTTP istemcisi (mikroservis Faz 3).

`PEMF_AI_SERVICE_URL` AYARLIYSA → AI inference'ı ayrı `pemf-ai` servisine (GPU) HTTP
ile devreder. YOKSA → çekirdek in-process çalışır (GERİYE UYUM: Mac/CPU demo, tek-EXE
klinik kurulumu, mevcut davranış HİÇ bozulmaz). Tek bayrakla monolit ↔ mikroservis.
"""

import asyncio
import base64
import logging
import os
import threading

import httpx

logger = logging.getLogger("ai_client")

AI_SERVICE_URL = os.environ.get("PEMF_AI_SERVICE_URL", "").rstrip("/")
# ⚠️ D1.14 (B-2.17): BOZUK değer (ör. 'yuzseksen') eskiden modül içe aktarımında ValueError atıyordu
# → `ai_router` → `api_server` ölüyor, backend (dolayısıyla ACİL DURDUR ucu) HİÇ açılmıyordu.
try:
    _TIMEOUT = float(os.environ.get("PEMF_AI_SERVICE_TIMEOUT", "180").strip() or "180")
except ValueError:
    logger.warning(
        "Gecersiz PEMF_AI_SERVICE_TIMEOUT=%r -> varsayilan 180 sn", os.environ.get("PEMF_AI_SERVICE_TIMEOUT")
    )
    _TIMEOUT = 180.0


def ai_service_enabled() -> bool:
    """PEMF_AI_SERVICE_URL tanımlıysa AI çağrıları mikroservise devredilir."""
    return bool(AI_SERVICE_URL)


# ── İG-5.29: TOPLAM süre sınırı. httpx'in zaman aşımı OKUMA BAŞINADIR: yanıtı damla damla (ör. 2 sn'de 1 bayt)
#    veren servis her okumada sayacı sıfırlar ve istek SINIRSIZ sürer. Ölçüldü: AI Pro döngüsü 20 sn+ tek turda
#    kaldı, bobinler bu sürede eski dozla (keep-alive) sürdü. Artık bir istek (bağlantı + gönderim + başlık +
#    gövde) en çok `_TIMEOUT` sn sürer; aşınca `httpx.ReadTimeout` (çağıranların zaten ele aldığı tür).
def _toplam_sure_asildi(url: str) -> httpx.ReadTimeout:
    return httpx.ReadTimeout(f"AI servisi {_TIMEOUT:g} sn toplam süre sınırını aştı, yanıt kesildi ({url})")


def _post_sync(url: str, **kw):
    """Toplam süre sınırlı SENKRON POST → JSON. Süre dolunca istemci zamanlayıcı iş parçacığından kapatılır;
    bloklu okuma soket kapandığı için hata verir. (İş parçacığında olay döngüsü AÇILMAZ: py3.10 Proactor
    döngüsünü istek başına açıp kapatmak GC'de çökme riski taşır.)"""
    doldu = threading.Event()
    with httpx.Client(timeout=_TIMEOUT) as client:

        def _kes():
            doldu.set()
            client.close()

        zamanlayici = threading.Timer(_TIMEOUT, _kes)
        zamanlayici.daemon = True
        zamanlayici.start()
        try:
            resp = client.post(url, **kw)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if doldu.is_set() and not isinstance(e, httpx.HTTPStatusError):
                raise _toplam_sure_asildi(url) from e
            raise
        finally:
            zamanlayici.cancel()


async def _post_async(url: str, **kw):
    """Toplam süre sınırlı ASYNC POST → JSON (`asyncio.wait_for` isteği iptal eder)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await asyncio.wait_for(client.post(url, **kw), _TIMEOUT)
        except asyncio.TimeoutError as e:
            raise _toplam_sure_asildi(url) from e
        resp.raise_for_status()
        return resp.json()


async def delegate_infer(
    name: str, file=None, image_base64: str = None, audio_base64: str = None, csv_base64: str = None, data: dict = None
):
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
    return await _post_async(url, files={"file": (filename, content)}, data=form)


async def delegate_json(name: str, payload: dict):
    """JSON gövdeli AI ucunu (disease|kidney_disease) pemf-ai `/infer/<name>`'e devret → JSON."""
    url = f"{AI_SERVICE_URL}/infer/{name}"
    return await _post_async(url, json=payload)


# ── SENKRON varyantlar: AI Pro closed-loop (cat_organ + em_kedi) SENKRON fonksiyonlardan
#    (_localize_organ/_predict_and_drive, to_thread ile thread'de) çağrılır → httpx.Client (bloklayan).
#    Böylece AI Pro'nun AĞIR inference'ı da GPU servisine devredilir (Hoca yönü). Bkz ai_router. ──
def delegate_infer_sync(name: str, content: bytes, filename: str = "input.jpg", data: dict = None):
    """SENKRON multipart görüntü devri (pemf-ai `/infer/<name>` → JSON). content=ham bayt.
    YALNIZCA ai_service_enabled() True iken çağır; çağıran zaten thread'de (to_thread)."""
    form = {k: str(v) for k, v in (data or {}).items() if v is not None}
    url = f"{AI_SERVICE_URL}/infer/{name}"
    return _post_sync(url, files={"file": (filename, content)}, data=form)


def delegate_json_sync(name: str, payload: dict):
    """SENKRON JSON devri (pemf-ai `/infer/<name>` → JSON). AI Pro em_kedi sürüşü için."""
    url = f"{AI_SERVICE_URL}/infer/{name}"
    return _post_sync(url, json=payload)
