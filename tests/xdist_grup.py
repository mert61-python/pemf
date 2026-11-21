# -*- coding: utf-8 -*-
"""Y312 (sahip 20-11: "tam testlerde süreler kısalsın" · "xdist kur") — pytest-xdist `--dist loadgroup` altında İŞARETSİZ testler kendi
DOSYALARININ biriminde (`loadfile` gibi), `xdist_group("seri")` işaretliler farklı dosyalarda olsalar da TEK işçide koşar.

Neden: xdist'in `loadgroup` zamanlayıcısı işaretsiz testi TEK BAŞINA birim yapar (`load` gibi; 3.8 `scheduler/loadgroup._split_scope`)
→ bir dosyanın testleri işçilere bölünür. Süit dosya içi sıraya göre yazılmıştır (modül fikstürleri, iki kollu meta kapılar: 1. kol
kirletir, 2. kol temiz görmeli). İşaretsiz teste `xdist_group` vermek de çözüm DEĞİL: xdist işaretli testin düğüm kimliğine `@grup`
soneki ekler ve düğüm kimliğine bakan kapılar (OA24, C2_3_5) bozulur (PX'te ölçüldü). Bu yüzden düğüm kimliğine DOKUNULMAZ; yalnız
zamanlayıcının birim seçimi değişir: denetleyicide `pytest_xdist_make_scheduler` (tests/conftest.py) bu zamanlayıcıyı döndürür.
Seri koşuda ve başka dağıtım kiplerinde HİÇBİR şey yapmaz (None → xdist varsayılanı). Kapı: tests/test_xdist_dosya_grubu_Y312.py
"""

from __future__ import annotations

SERI = "seri"


def kapsam(nodeid: str) -> str:
    """Zamanlama birimi: `xdist_group` işaretli test → grup adı (xdist'in `@grup` soneki), işaretsiz → dosya yolu."""
    if nodeid.rfind("@") > nodeid.rfind("]"):  # parametre kimliğindeki '@' grup soneki sayılmaz (xdist ile aynı ölçüt)
        return nodeid.split("@")[-1]
    return nodeid.split("::", 1)[0]


def zamanlayici(config, log):
    """`--dist loadgroup` ise dosya birimli grup zamanlayıcısı; değilse None (xdist kendi varsayılanını seçer)."""
    if config.getvalue("dist") != "loadgroup":
        return None
    from xdist.scheduler import LoadGroupScheduling

    class DosyaGrubuZamanlayici(LoadGroupScheduling):
        def _split_scope(self, nodeid: str) -> str:
            return kapsam(nodeid)

    return DosyaGrubuZamanlayici(config, log)
