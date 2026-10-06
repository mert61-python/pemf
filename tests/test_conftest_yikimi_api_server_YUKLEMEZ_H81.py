# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""H-8.1 (1-H incelemesi; 1-H raporu §8 #11) — conftest'in YIKIM fikstürleri `servers.api_server`'ı İÇE AKTARMAZ.

ÖLÇÜLEN (inceleme `kayit/h81_asama_sonda.txt`, alt süreç, boş test): `servers.api_server` testin kurulumundan ÖNCE yok,
test gövdesinde VAR — modülü oturum kurulumunda BİLEREK yükleyen `_lifespan_yan_etkilerini_engelle` (oturum kapsamlı,
lifespan yan etkilerini kapatır; dokunulmadı). 1-H'nin teşhisi ("O-3.1 yıkımı yükler") bu yüzden eksikti; ama yıkımdaki
try/except'li `from servers import api_server` (O-3.1 sondası durdurma + ack bekçisi temizliği — İKİ fikstür) "yüklü değilse
geç" gibi okunup modülü YÜKLER: oturum fikstürü değişir ya da içe aktarma başarısız olursa her testin yıkımı modülü (FastAPI
uygulaması + durum) yeniden içe aktarmayı dener.

KAPI (ALT SÜREÇTE): GERÇEK `tests/conftest.py` eklenti olarak yüklenir; `servers.api_server` içe aktarması evreye göre
KAYDEDİLİP ENGELLENİR (sys.meta_path); YALNIZ boş bir test koşulur. Yıkım evresinde içe aktarma denemesi OLMAMALI.
Karşıt: oturum fikstürünün kurulumdaki denemesi görülür (ölçüm kör değil). Çocukta ağ bekçisi; ortam izin listeli.
"""

from __future__ import annotations

import re
from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent

_SURUCU = r"""
import importlib.abc
import importlib.util
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag

EVRE = {{"ad": "oturum"}}
DENEME = []


class _Engel(importlib.abc.MetaPathFinder):
    def find_spec(self, ad, yol=None, hedef=None):
        if ad == "servers.api_server":
            DENEME.append(EVRE["ad"])
            raise ImportError("H-8.1 kapisi: servers.api_server ice aktarmasi ENGELLI (" + EVRE["ad"] + ")")
        return None


sys.meta_path.insert(0, _Engel())
spec = importlib.util.spec_from_file_location("conftest_h81", {conftest!r})
conftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conftest)
import pytest


class _Evre:
    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item):
        EVRE["ad"] = "kurulum"

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_call(self, item):
        EVRE["ad"] = "govde"

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_teardown(self, item, nextitem):
        EVRE["ad"] = "yikim"


rc = pytest.main([{bos!r}, "-q", "-p", "no:cacheprovider", "-p", "no:randomly"], plugins=[conftest, _Evre()])
print("\nDENEME=" + (",".join(DENEME) or "-") + " RC=" + str(int(rc)) + " AG=" + str(_ag.ENGELLENEN), flush=True)
"""


def _kos(tmp_path: Path) -> dict:
    bos = tmp_path / "test_h81_bos.py"
    bos.write_text("def test_bos():\n    pass\n", encoding="utf-8")
    kod = _SURUCU.format(testler=str(TESTLER), conftest=str(TESTLER / "conftest.py"), bos=str(bos))
    (tmp_path / "surucu.py").write_text(kod, encoding="utf-8")
    p = kostur([str(tmp_path / "surucu.py")], cwd=tmp_path, env=yalitik_ortam(tmp_path / "ev"), sure=240)
    sonuc = dict(re.findall(r"(DENEME|RC|AG)=(\S+)", p.stdout))
    assert sonuc.get("RC") == "0" and sonuc.get("AG") == "[]", f"aparat: çocuk pytest {sonuc} — {p.stderr[-1500:]}"
    return sonuc


def test_KRITIK_H81_yikim_fiksturleri_api_server_ICE_AKTARMAZ(tmp_path):
    s = _kos(tmp_path)
    denemeler = s["DENEME"].split(",")
    # Karşıt (aynı koşu): oturum fikstürü `_lifespan_yan_etkilerini_engelle` kurulumda içe aktarmayı DENER — ölçüm kör değil.
    assert "kurulum" in denemeler, f"aparat: içe aktarma kaydı hiçbir evrede görülmedi (kapı kör): {s}"
    assert "yikim" not in denemeler, (
        f"conftest YIKIM fikstürü `servers.api_server`'ı içe aktarmaya çalışıyor (yüklü değilse YÜKLER): {s} — "
        "temizlik yalnız sys.modules.get ile yapılmalı"
    )
