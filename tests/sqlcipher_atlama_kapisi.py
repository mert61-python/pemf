# -*- coding: utf-8 -*-
"""A-46 YEREL İKİZİ — "sqlcipher" nedenli ATLAMA pytest koşusunu KIRMIZI bitirir (2-A inceleme · sahip isteği 2026-10-07).

CI'da `scripts/ci_sqlcipher_atlama_kapisi.py` junit dosyasından sayar ve işi düşürür (D2.07). Yerelde o betik koşmuyordu:
sqlcipher3'süz bir ortamda (yalnız `requirements-test.txt` kurulmuş bir makine) şifreleme / göç / karantina / kurtarma
kapılarının 66'sı ATLANIP 13'ü hiç TOPLANMADAN koşu YEŞİL bitiyordu (ölçüldü — CI-Windows eşdeğeri, 2-A incelemesi). Artık
aynı ölçüt (atlama nedeninde harf duyarsız "sqlcipher") HER pytest koşusunda uygulanır: test ya da modül toplama atlaması →
çıkış 1 + adlarıyla liste. Testler zaten düştüyse çıkış kodu değişmez; atlama yoksa kapı hiçbir şey yapmaz.

Bilinçli benzetim (CI-eşdeğeri atlama sayımı): `PEMF_SQLCIPHER_ATLAMA_SERBEST=1` — liste yine basılır, çıkış kodu değişmez.

Kurulum: `tests/conftest.py` `pytest_configure` içinde `kur(config)`; tek başına `-p sqlcipher_atlama_kapisi` ile de yüklenir.
Kapı: tests/test_sqlcipher_atlama_YEREL_kapi_A46.py."""

from __future__ import annotations

import os

import pytest

SERBEST = "PEMF_SQLCIPHER_ATLAMA_SERBEST"
#: Örneğin eklenti yöneticisindeki adı (modülün kendi adından FARKLI — `-p` ile yüklenince ikisi birlikte kayıtlı olur).
ORNEK_ADI = "sqlcipher-atlama-kapisi"


def _neden(report) -> str:
    lr = report.longrepr
    if isinstance(lr, tuple) and len(lr) == 3:  # (yol, satır, "Skipped: <neden>")
        return str(lr[2])
    return str(lr or "")


class _Kapi:
    def __init__(self) -> None:
        self.atlanan: list[tuple[str, str]] = []

    def _kaydet(self, report, ad: str) -> None:
        if report.skipped:
            neden = _neden(report)
            if "sqlcipher" in neden.lower():
                self.atlanan.append((ad, neden))

    def pytest_runtest_logreport(self, report) -> None:
        # Atlama kurulumda (`skipif` / fixture içinde `pytest.skip`) ya da test gövdesinde (`call`) olur.
        if report.when in ("setup", "call"):
            self._kaydet(report, report.nodeid)

    def pytest_collectreport(self, report) -> None:
        # Modül düzeyi `importorskip("sqlcipher3")` / `pytest.skip(..., allow_module_level=True)`: testler HİÇ toplanmaz.
        self._kaydet(report, f"{report.nodeid or '?'} (modül toplanmadı)")

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if self.atlanan and os.environ.get(SERBEST) != "1" and session.exitstatus == pytest.ExitCode.OK:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter) -> None:
        if not self.atlanan:
            return
        serbest = os.environ.get(SERBEST) == "1"
        tr = terminalreporter
        tr.section("A-46 sqlcipher atlama kapisi", sep="=", red=not serbest, bold=True)
        if serbest:
            tr.line(
                f"SERBEST ({SERBEST}=1, bilincli benzetim): {len(self.atlanan)} test/modul 'sqlcipher' nedeniyle ATLANDI."
            )
        else:
            tr.line(
                f"KIRMIZI (A-46): {len(self.atlanan)} test/modul 'sqlcipher' nedeniyle ATLANDI — kosu BASARISIZ sayildi."
            )
            tr.line(
                "sqlcipher3 kurun: pip install -r requirements-test.txt (sqlcipher3==0.6.2). Sifreleme / goc / karantina /"
            )
            tr.line("kurtarma kapilari sessizce atlanamaz (sahip karari A-46).")
        for ad, neden in self.atlanan[:40]:
            tr.line(f"  - {ad} :: {neden[:140]}")
        if len(self.atlanan) > 40:
            tr.line(f"  ... (+{len(self.atlanan) - 40})")


def kur(config) -> None:
    """Kapıyı bu oturumun eklenti yöneticisine BİR KEZ kaydeder (conftest + `-p` birlikte gelse de çift sayılmaz)."""
    if not config.pluginmanager.has_plugin(ORNEK_ADI):
        config.pluginmanager.register(_Kapi(), ORNEK_ADI)


def pytest_configure(config) -> None:  # `-p sqlcipher_atlama_kapisi` ile tek başına yüklendiğinde
    kur(config)
