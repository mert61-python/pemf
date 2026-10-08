# -*- coding: utf-8 -*-
"""S-A2.5 (a) [ÖNERİLEN UYGULANDI — Y123] (2-C incelemesi, A2) — `*_FIKSTUR_YAZ=1` yenilemesi yalnız tamamen yeşil koşuda kalıcı.

ÖLÇÜLEN (A2 `kayit/k8f_fikstur_kilitlenme.txt`, HEAD 1cd770c): backend mutantı altında `D215_FIKSTUR_YAZ=1 … -k fiksturu` yanlış
yanıtı fikstüre yazdı, tazelik kapısı sonraki koşuda YEŞİL kaldı (fikstür kendini doğruluyordu).
Kapı GERÇEK eklenti nesnesini (`fikstur_yenileme_kapisi._Kapi`) geçici bir `__fixtures__` kökünde, pytest kancalarını sahte
rapor/oturum nesneleriyle çağırarak sürer (oturumun KENDİ eklenti yöneticisine kayıt yapılmaz — aksi hâlde bu koşunun sonunda
gerçek fikstürlere dokunurdu). Bağlantı: `conftest.pytest_configure` `kur(config)`'u çağırır (AST).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import fikstur_yenileme_kapisi as fk  # noqa: E402

ESKI = b'{"durum": 503}\n'
YENI = b'{"durum": 200, "govde": {"status": "success"}}\n'


@pytest.fixture
def kok(tmp_path):
    d = tmp_path / "src" / "screens" / "__tests__" / "__fixtures__"
    d.mkdir(parents=True)
    (d / "gozlemNotu.D215.json").write_bytes(ESKI)
    return tmp_path / "src"


def _yenile(kok):
    """Fikstür testinin yenileme kipinde yaptığı yazım (içerik değişir + yeni dosya)."""
    d = kok / "screens" / "__tests__" / "__fixtures__"
    (d / "gozlemNotu.D215.json").write_bytes(YENI)
    (d / "yeni.D999.json").write_bytes(b"{}\n")


def _oturum():
    return SimpleNamespace(exitstatus=pytest.ExitCode.OK)


def _rapor(**k):
    return SimpleNamespace(failed=k.get("failed", False), skipped=k.get("skipped", False))


@pytest.mark.parametrize("ariza", ["secilmeyen_k", "basarisiz_kapi", "atlanan_kapi"])
def test_KRITIK_kosu_tamamen_yesil_DEGILSE_yenilenen_fikstur_GERI_ALINIR_kosu_KIRMIZI(kok, ariza):
    kapi = fk._Kapi(["D215_FIKSTUR_YAZ"], kok)
    _yenile(kok)
    if ariza == "secilmeyen_k":
        kapi.pytest_deselected([object(), object()])
    elif ariza == "basarisiz_kapi":
        kapi.pytest_runtest_logreport(_rapor(failed=True))
    else:
        kapi.pytest_runtest_logreport(_rapor(skipped=True))
    kapi.pytest_runtest_logreport(_rapor())  # fikstür testi geçti
    oturum = _oturum()
    kapi.pytest_sessionfinish(oturum, 0)
    d = kok / "screens" / "__tests__" / "__fixtures__"
    assert (d / "gozlemNotu.D215.json").read_bytes() == ESKI, f"{ariza}: yanlış/denetimsiz yenileme fikstürde KALDI"
    assert not (d / "yeni.D999.json").exists(), f"{ariza}: yenilemede oluşan fikstür silinmedi"
    assert oturum.exitstatus == pytest.ExitCode.TESTS_FAILED, f"{ariza}: geri alınan yenileme koşusu YEŞİL bitti"


def test_KARSIT_tamamen_yesil_kosuda_yenileme_KALICI(kok):
    kapi = fk._Kapi(["D215_FIKSTUR_YAZ"], kok)
    _yenile(kok)
    for _ in range(3):
        kapi.pytest_runtest_logreport(_rapor())
    oturum = _oturum()
    kapi.pytest_sessionfinish(oturum, 0)
    d = kok / "screens" / "__tests__" / "__fixtures__"
    assert (d / "gozlemNotu.D215.json").read_bytes() == YENI and (d / "yeni.D999.json").exists()
    assert oturum.exitstatus == pytest.ExitCode.OK


def test_KARSIT_yenileme_ISTENMEZSE_kapi_KURULMAZ_istenirse_BIR_KEZ(monkeypatch):
    kayit: list = []

    class _Yonetici:
        def has_plugin(self, ad):
            return any(a == ad for a, _ in kayit)

        def register(self, eklenti, ad):
            kayit.append((ad, eklenti))

    cfg = SimpleNamespace(pluginmanager=_Yonetici())
    for k in [k for k in list(__import__("os").environ) if k.upper().endswith("_FIKSTUR_YAZ")]:
        monkeypatch.delenv(k)
    fk.kur(cfg)
    assert kayit == [], "yenileme istenmeyen koşuda kapı kuruldu"
    monkeypatch.setenv("D215_FIKSTUR_YAZ", "1")
    fk.kur(cfg)
    fk.kur(cfg)
    assert [a for a, _ in kayit] == [fk.ORNEK_ADI]


def test_YAPI_conftest_pytest_configure_kapiyi_KURAR():
    agac = ast.parse((_TESTS / "conftest.py").read_text(encoding="utf-8"))
    fn = next(n for n in agac.body if isinstance(n, ast.FunctionDef) and n.name == "pytest_configure")
    cagrilar = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "kur"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "fikstur_yenileme_kapisi"
    ]
    assert cagrilar, "conftest.pytest_configure fikstur_yenileme_kapisi.kur(config) çağırmıyor — kapı hiç kurulmaz"
