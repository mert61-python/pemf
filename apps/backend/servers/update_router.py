# Author: mertaygn, cglrgrkn
"""Sürüm / OTA güncelleme uçları (audit B-2.2: api_server.py'den ayrıldı — modüler router).
Yalnız `update_manager`'a bağlı; paylaşılan donanım/seans/live-state'i KULLANMAZ → temiz ayrım.
Yollar birebir korunur (/api/update/status|apply|rollback) → istemci sözleşmesi değişmez."""

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["update"])
logger = logging.getLogger("update_router")


def _yetki_kapisi(request: Request) -> None:
    """Yıkıcı güncelleme uçlarının yetki kapısı — LAN muafiyeti YOK.

    ⚠️ DENETİM 2026-08-23 (O2): bu iki uç `Request` bile almıyordu ve hiçbir kapı taşımıyordu.
    Global middleware LAN'ı auth-MUAF sayar (`api_server::is_local_request`), yani
    `PEMF_LEGACY_EXE_UPDATE=1` ile kurulan bir dağıtımda klinik hotspot'undaki HERHANGİ bir cihaz
    — hotspot parolası pakette dağıtılıyor — token'sız bir POST ile tıbbi cihazda sessiz installer
    koşturabilir ya da `rollback` ile yayınlanmış bir düzeltmeyi geri alabilirdi.

    Kod arbitrari değil (SHA256 + Authenticode doğrulanıyor, aktif tedavide reddediliyor) — ama
    deponun kendi standardı (`api_server::_enforce_privileged`, 2026-08-09) yıkıcı uçlar için bu
    kapıyı zaten şart koşuyor; bu ikisi listeye alınmamıştı.
    """
    from servers.auth import enforce_privileged

    enforce_privileged(request)


@router.get("/api/update/status")
async def update_status():
    """Kurulu sürüm vs GitHub 'exe' branch latest.json — UI bildirimi için (rollback hedefi dahil)."""
    try:
        from servers.update_manager import get_status

        return get_status()
    except Exception:
        logger.exception("update status hatasi")
        return {"checked": False, "available": False, "error": "update_manager yok"}


@router.post("/api/update/apply")
async def update_apply(request: Request):
    """Operatör ONAYI → installer indir + SHA256 doğrula + AKTİF TEDAVİ YOKKEN sessiz kur (blocking → thread)."""
    _yetki_kapisi(request)
    try:
        from servers.update_manager import apply_update

        return await asyncio.to_thread(apply_update)
    except Exception:
        logger.exception("update apply hatasi")
        return JSONResponse(status_code=500, content={"detail": "guncelleme uygulanamadi"})


@router.post("/api/update/rollback")
async def update_rollback(request: Request):
    """Operatör: önceki KARARLI sürüme geri dön (audit B-9.2) — kötü güncelleme sahada sorun çıkarırsa.
    previousStable installer'ı indir + SHA256 doğrula + AKTİF TEDAVİ YOKKEN sessiz kur."""
    _yetki_kapisi(request)
    try:
        from servers.update_manager import rollback

        return await asyncio.to_thread(rollback)
    except Exception:
        logger.exception("update rollback hatasi")
        return JSONResponse(status_code=500, content={"detail": "rollback uygulanamadi"})
