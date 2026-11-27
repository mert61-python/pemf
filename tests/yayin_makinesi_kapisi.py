# -*- coding: utf-8 -*-
"""YAYIN MAKİNESİ KAPISI (CT1 c · istem 66 · Y324) — Y sınıfı testler yayından önce MUTLAKA koşar.

Y sınıfı = yalnız yayın makinesinde bulunan esere bağlı test (kurucu EXE, APK, `base-deps.zip`, sevk ağacı, Tauri NSIS şablonu,
gömülü derleme Python'u, depo dışı TR tabanı). CI'da bu eserler yok → test GEREKÇELİ atlar (`tests/ci_atlanan_defteri.json`, sınıf Y).
Y30 (`scripts/yayin_oncesi_suit.ps1`, yayın makinesi) `PEMF_YAYIN_MAKINESI=1` verir: bu kipte `yalniz_yayin_makinesi` işaretli bir
test — ya da işaretli modülün toplaması — ATLARSA sonuç BAŞARISIZLIĞA çevrilir (eser eksik yayın makinesi yayın YAPMAZ).
Kapı: tests/test_CT1c_ci_atlanan_defteri_KAPI.py"""

from __future__ import annotations

import os

import pytest

ISARET = "yalniz_yayin_makinesi"
ORTAM = "PEMF_YAYIN_MAKINESI"


def yayin_makinesi_mi() -> bool:
    return os.environ.get(ORTAM) == "1"


def _neden(rapor) -> str:
    lr = rapor.longrepr
    return str(lr[2]) if isinstance(lr, tuple) and len(lr) == 3 else str(lr)


def _ileti(neden: str) -> str:
    return f"{ORTAM}=1 (Y30 · yayın makinesi) ama Y sınıfı test ATLADI — yayından önce mutlaka koşmalı: {neden}"


class _Eklenti:
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        sonuc = yield
        rapor = sonuc.get_result()
        if rapor.skipped and yayin_makinesi_mi() and item.get_closest_marker(ISARET) is not None:
            rapor.outcome = "failed"
            rapor.longrepr = _ileti(_neden(rapor))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_make_collect_report(self, collector):
        sonuc = yield
        rapor = sonuc.get_result()
        if (
            rapor.skipped
            and yayin_makinesi_mi()
            and isinstance(collector, pytest.Module)
            and ISARET in collector.path.read_text(encoding="utf-8", errors="replace")
        ):
            rapor.outcome = "failed"
            rapor.longrepr = _ileti(_neden(rapor))


def kur(config) -> None:
    config.addinivalue_line(
        "markers",
        f"{ISARET}: Y sınıfı — yalnız yayın makinesinde bulunan esere bağlı (CI'da gerekçeli atlar, Y30'da atlarsa kırmızı)",
    )
    if not config.pluginmanager.has_plugin("yayin_makinesi_kapisi_eklenti"):
        config.pluginmanager.register(_Eklenti(), "yayin_makinesi_kapisi_eklenti")
