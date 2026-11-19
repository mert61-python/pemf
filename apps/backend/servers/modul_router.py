# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B1 — `/api/moduller/...` uçları (Kontrol sekmesi modül seçicisi + `useModul` araç takımı).

Yetki `/api/hardware/*` ile AYNI (auth MUAF DEĞİL). Modüller varsayılan GİZLİ (Y299): görünürlük kapalıyken seçim / komut REDDEDİLİR
(liste boş döner); ACİL DURDUR yayılımı görünürlükten BAĞIMSIZDIR (`api_server._emergency_stop_all`). Hata gövdesi `{"kod", "alan"}` —
arayüz `kontrol.modul.hata.<kod>` ile iki dilde eylem söyler. Senkron uçlar FastAPI iş parçacığı havuzunda koşar (olay döngüsünü
bloklamaz); her sürücü çağrısı zaman aşımlıdır.
D5 basit-POST envanteri (OYZ, zincir 56 AŞAMA 3): modülü SEÇEN / BAŞLATAN uçlar yalnız `application/json` isteği yürütür (Sıfırla emsali;
415 `jsonGerekli`) — LAN'da / cihazda açılan çapraz kökenli bir sayfa basit POST'la modül kartını sürdüremez. Arayüz `apiPost(…, {})` ile
JSON gönderir. `durdur` / `birak` (modülü DURDURUR) basit POST'la da çalışır: STOP yalnız güvenliği artırır (Ö.4-Y8).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from servers import modul_kayit, modul_yonetici
from servers.modul_kayit import ModulHatasi

router = APIRouter(prefix="/api/moduller", tags=["moduller"])

_DURUM_KODU = {
    "gizli": 403,
    "modulYok": 404,
    "etkinModulYok": 409,
    "baglanamadi": 502,
    "surucuOldu": 502,
    "surucuYanitsiz": 504,
    "surucuHatasi": 502,
}


def _hata(e: ModulHatasi) -> HTTPException:
    return HTTPException(status_code=_DURUM_KODU.get(e.kod, 400), detail={"kod": e.kod, "alan": e.alan})


class GorunurlukModel(BaseModel):
    gorunur: bool


class AyarModel(BaseModel):
    ayar: dict


@router.get("")
def moduller_listesi():
    gorunur = modul_kayit.gorunur_mu()
    y = modul_yonetici.varsa()
    return {
        "gorunur": gorunur,
        "moduller": modul_kayit.liste() if gorunur else [],
        **(y.ozet() if y is not None else {"etkin": None, "canli": False, "hata": None}),
    }


@router.post("/gorunurluk")
def gorunurluk(govde: GorunurlukModel):
    """Ayarlar → "Geliştirici modülleri". Kapatınca etkin modül BIRAKILIR (sürücü durdurulur, süreç kapanır)."""
    try:
        g = modul_kayit.gorunur_yaz(govde.gorunur)
    except OSError:
        raise HTTPException(status_code=503, detail={"kod": "ayarYazilamadi", "alan": ""}) from None
    if not g and modul_yonetici.varsa() is not None:
        modul_yonetici.yonetici().birak()
    return {"gorunur": g}


def _calistir(islev, *a):
    try:
        return islev(*a)
    except ModulHatasi as e:
        raise _hata(e) from None


@router.post("/birak")
def birak():
    return _calistir(modul_yonetici.yonetici().birak)


@router.post("/uygula")
def uygula(govde: AyarModel):
    if not modul_kayit.gorunur_mu():
        raise _hata(ModulHatasi("gizli"))
    return _calistir(modul_yonetici.yonetici().uygula, govde.ayar)


@router.post("/baslat")
def baslat(request: Request):
    if "application/json" not in (request.headers.get("content-type") or "").lower():
        raise HTTPException(status_code=415, detail={"kod": "jsonGerekli", "alan": ""})
    if not modul_kayit.gorunur_mu():
        raise _hata(ModulHatasi("gizli"))
    return _calistir(modul_yonetici.yonetici().baslat)


@router.post("/durdur")
def durdur():
    """Görünürlükten BAĞIMSIZ (durdurma hiçbir koşula bağlanmaz)."""
    return _calistir(modul_yonetici.yonetici().durdur)


@router.get("/durum")
def durum():
    return _calistir(modul_yonetici.yonetici().durum)


@router.post("/{kimlik}/sec")
def sec(kimlik: str, request: Request):
    if "application/json" not in (request.headers.get("content-type") or "").lower():
        raise HTTPException(status_code=415, detail={"kod": "jsonGerekli", "alan": ""})
    return _calistir(modul_yonetici.yonetici().sec, kimlik)
