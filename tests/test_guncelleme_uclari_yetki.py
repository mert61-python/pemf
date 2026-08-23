# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GUNCELLEME UCLARI YETKI KAPISI TASIR (denetim 2026-08-23, bulgu O2).

OLCULEN DURUM: `/api/update/apply` ve `/api/update/rollback` handler'lari `Request` parametresi
bile ALMIYOR ve hicbir yetki kapisi tasimiyordu. Global middleware ise LAN'i auth-MUAF sayiyor
(`api_server.py::is_local_request`). Sonuc: `PEMF_LEGACY_EXE_UPDATE=1` ile kurulan (launcher'siz,
yalniz-backend) bir dagitimda, klinik hotspot'undaki HERHANGI bir cihaz — hotspot parolasi pakette
dagitiliyor — token'siz bir POST ile:

  · tibbi cihazda SESSIZ installer kosturabilir (servis yeniden baslar, cihaz kisa sure kullanilamaz),
  · `rollback` ile cihazi onceki surume DUSUREBILIR, yani yayinlanmis bir DUZELTMEYI kimliksiz
    geri alabilir (bobin-guvenligi yamasi dahil).

⚠️ Kod arbitrari DEGIL (SHA256 + Authenticode dogrulaniyor, aktif tedavide reddediliyor) — bu
yuzden P0 degil. Ama deponun KENDI standardi bunu zaten sart kosuyor: `_enforce_privileged`
"yikici/PII ucu kapisi — LAN muafiyeti YOK" diyor ve 2026-08-09 denetiminde tam bu sinif icin
konmus. Bu iki uc listeye alinmamis.

⚠️ ESKI KANAL VARSAYILAN KAPALI olsa da uclar HER ZAMAN monteli: bayragin acilmasi bir yapilandirma
karari, kapinin varligi ise bir kod degismezidir. "Bugun kapali" bir yetki bosluğunu mesru kilmaz.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_ROUTER = _KOK / "servers" / "update_router.py"

# Kurulum/geri-alma tetikleyen YIKICI uclar. (`/api/update/status` salt-okunur → kapisiz mesru.)
_YIKICI_UCLAR = ["/api/update/apply", "/api/update/rollback"]


@pytest.fixture(scope="module")
def kaynak() -> str:
    return _ROUTER.read_text(encoding="utf-8", errors="replace")


def _handler(kaynak: str, yol: str) -> str:
    """Verilen yolun handler govdesi (bir sonraki dekoratore kadar)."""
    m = re.search(rf'@router\.post\("{re.escape(yol)}"\)\s*\n(.*?)(?=\n@router\.|\Z)', kaynak, re.S)
    assert m, f"`{yol}` handler'i bulunamadi — update_router.py bicimi degismis olabilir"
    return m.group(1)


@pytest.mark.parametrize("yol", _YIKICI_UCLAR)
def test_KRITIK_yikici_guncelleme_ucu_YETKI_ISTER(kaynak, yol):
    g = _handler(kaynak, yol)
    # ⚠️ IKI HALKA birden olculur: handler kapiyi CAGIRMALI ve o kapi gercekten
    # `enforce_privileged`e VARMALI. Yalniz birine bakmak, sarmalayicisi bosaltilmis bir kapiyi
    # (ya da cagrilmayan bir sarmalayiciyi) yesil gosterirdi. Desen `api_server::_enforce_privileged`
    # ile ayni.
    assert "_yetki_kapisi(request)" in g, (
        f"`{yol}` yetki kapisini CAGIRMIYOR — LAN auth-muaf oldugu icin klinik hotspot'undaki her "
        "cihaz kimliksiz kurulum/geri-alma tetikleyebilir (bulgu O2)"
    )
    m = re.search(r"def _yetki_kapisi\(request: Request\) -> None:(.*?)(?=\n@router\.|\ndef )", kaynak, re.S)
    assert m, "_yetki_kapisi tanimi bulunamadi"
    assert "enforce_privileged(request)" in m.group(1), (
        "_yetki_kapisi BOSALTILMIS — cagriliyor ama hicbir yetki denetimi yapmiyor"
    )


@pytest.mark.parametrize("yol", _YIKICI_UCLAR)
def test_KRITIK_handler_Request_ALIR(kaynak, yol):
    """Kapi `Request` olmadan uygulanamaz; imza degisikligi sessizce unutulmasin."""
    g = _handler(kaynak, yol)
    assert re.search(r"request:\s*Request", g), f"`{yol}` handler'i `Request` almiyor — yetki kapisi cagrilamaz"


def test_KARSIT_KANIT_salt_okunur_durum_ucu_KAPILANMAZ(kaynak):
    """`/api/update/status` yalnizca durum okur; kapilamak arayuzun guncelleme rozetini
    kimliksiz cihazlarda bozardı. Kapi asiri genislemesin."""
    m = re.search(r'@router\.get\("/api/update/status"\)\s*\n(.*?)(?=\n@router\.|\Z)', kaynak, re.S)
    assert m, "status ucu bulunamadi"
    assert "enforce_privileged" not in m.group(1), "salt-okunur durum ucu yetki istiyor — kapi asiri genis"
