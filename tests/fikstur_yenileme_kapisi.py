# -*- coding: utf-8 -*-
"""S-A2.5 (a) [ÖNERİLEN UYGULANDI — Y123] (2-C incelemesi, A2) — gerçek-backend arayüz fikstürü YALNIZ koşunun TÜM kapıları
yeşilken yenilenir.

NEDEN [ölçüldü — A2 `kayit/k8f_fikstur_kilitlenme.txt`]: `*_FIKSTUR_YAZ=1` fikstürü koşulsuz yazıyor, tazelik kapısı ise
yazılanı kendisiyle karşılaştırıyordu. Backend mutantı (D2.15: `update_session_finalized_extras` hatayı yutar) altında
`D215_FIKSTUR_YAZ=1 … -k fiksturu` YANLIŞ yanıtı (`200 success`) fikstüre işledi; sonraki koşuda tazelik kapısı YEŞİL kaldı.
Savunma yalnız kardeş KRİTİK kapılar ve jest'in sabit beklentileriydi.

KURAL: ortamda herhangi bir `*_FIKSTUR_YAZ=1` varsa oturum başında `apps/ui/src/**/__fixtures__/` altındaki dosyaların fotoğrafı
alınır. Oturum sonunda koşuda BAŞARISIZ / HATA / ATLANAN ya da SEÇİLMEYEN (`-k`, `--deselect`) test varsa yazılan fikstürler
fotoğraftaki hâline GERİ DÖNER (yeni oluşanlar silinir) ve koşu KIRMIZI biter. Böylece yenileme ancak dosyanın tamamı (ya da
seçilen dosyaların tamamı) yeşilken kalıcı olur. Yenileme istenmeyen koşuda hiçbir şey yapmaz.

Kurulum: `tests/conftest.py` `pytest_configure` içinde `kur(config)`. Kapı: tests/test_fikstur_yenilemesi_YALNIZ_yesil_kosuda_SA25.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ORNEK_ADI = "fikstur-yenileme-kapisi"
_KOK = Path(__file__).resolve().parents[1]
FIKSTUR_KOKU = _KOK / "apps" / "ui" / "src"


def yenileme_istendi(ortam=None) -> list[str]:
    """Ortamda `=1` olan `*_FIKSTUR_YAZ` değişkenlerinin adları."""
    ortam = os.environ if ortam is None else ortam
    return sorted(k for k, v in ortam.items() if k.upper().endswith("_FIKSTUR_YAZ") and str(v) == "1")


def fotograf(kok: Path) -> dict[Path, bytes]:
    """`kok` altındaki tüm `__fixtures__` dizinlerindeki dosyaların içerikleri."""
    foto: dict[Path, bytes] = {}
    for d in kok.rglob("__fixtures__"):
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file():
                    foto[f] = f.read_bytes()
    return foto


def geri_al(foto: dict[Path, bytes], kok: Path) -> list[str]:
    """Fikstürleri fotoğraftaki hâline döndürür; değişen / oluşan dosyaların adlarını döner."""
    geri: list[str] = []
    for f, icerik in foto.items():
        if not f.is_file() or f.read_bytes() != icerik:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(icerik)
            geri.append(str(f))
    for f in fotograf(kok):
        if f not in foto:
            f.unlink()
            geri.append(f"{f} (yeni — silindi)")
    return geri


def degerlendir(
    foto: dict[Path, bytes], kok: Path, basarisiz: int, atlanan: int, secilmeyen: int
) -> tuple[bool, list[str]]:
    """(yenileme kalıcı mı, geri alınan dosyalar). Koşu tamamen yeşil değilse fikstürler GERİ alınır."""
    if basarisiz or atlanan or secilmeyen:
        return False, geri_al(foto, kok)
    return True, []


class _Kapi:
    def __init__(self, istenen: list[str], kok: Path) -> None:
        self.istenen = istenen
        self.kok = kok
        self.foto = fotograf(kok)
        self.basarisiz = 0
        self.atlanan = 0
        self.secilmeyen = 0
        self.sonuc: tuple[bool, list[str]] | None = None

    def pytest_deselected(self, items) -> None:
        self.secilmeyen += len(items)

    def pytest_runtest_logreport(self, report) -> None:
        if report.failed:
            self.basarisiz += 1
        elif report.skipped:
            self.atlanan += 1

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self.basarisiz += 1

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        self.sonuc = degerlendir(self.foto, self.kok, self.basarisiz, self.atlanan, self.secilmeyen)
        if not self.sonuc[0] and session.exitstatus == pytest.ExitCode.OK:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter) -> None:
        if self.sonuc is None:
            return
        tr = terminalreporter
        kalici, geri = self.sonuc
        tr.section("S-A2.5 fikstur yenileme kapisi", sep="=", red=not kalici, bold=True)
        if kalici:
            tr.line(f"{', '.join(self.istenen)}: kosu tamamen YESIL — yazilan fiksturler KALICI.")
            return
        tr.line(
            f"{', '.join(self.istenen)}: kosu tamamen yesil DEGIL (basarisiz {self.basarisiz}, atlanan {self.atlanan}, "
            f"secilmeyen {self.secilmeyen}) — fiksturler GERI ALINDI, kosu BASARISIZ sayildi."
        )
        tr.line("Yenilemeyi dosyanin TAMAMIYLA (-k olmadan) ve tum kapilar yesilken kosun.")
        for g in geri[:40]:
            tr.line(f"  - {g}")


def kur(config) -> None:
    """Yenileme isteniyorsa kapıyı bu oturuma BİR KEZ kaydeder; istenmiyorsa hiçbir şey yapmaz."""
    istenen = yenileme_istendi()
    if istenen and not config.pluginmanager.has_plugin(ORNEK_ADI):
        config.pluginmanager.register(_Kapi(istenen, FIKSTUR_KOKU), ORNEK_ADI)
