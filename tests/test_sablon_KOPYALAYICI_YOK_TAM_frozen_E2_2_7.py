# -*- coding: utf-8 -*-
"""E2-2.7 (2-E incelemesi, A2) — KÖR KAPI: D2.34 kapısının "frozen benzetimi" YARIMDIR — `sys._MEIPASS`'i kurar ama `sys.frozen`'ı KURMAZ.

Ölçülen [amut.sh b k4 … k4_m1]: şablon kopya dalı, deponun KENDİ paket-kaynağı yardımcısı `path_utils.packaged_resource_path` ile
(`sys.frozen` → `_MEIPASS`) geri eklenince D2.34 kapısı **4 passed** kalır; oysa gerçek donmuş EXE'de (`frozen=True` + `_MEIPASS`) dal
paketteki BOŞ düz-metin şablonu veri köküne kopyalar (09-13 kaybının 3. yolu). 2-E'nin kendi m1'i `resource_path` (yalnız `_MEIPASS`'e
bakar) ile yazıldığı için kırmızıydı — kapı yardımcı seçimine bağlı.

Kapı: aynı ölçüm, donmuş EXE'nin İKİ işaretiyle (`sys.frozen=True` + `sys._MEIPASS`); gerçek `initialize_database`, sahte veri kökü.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_SABLONLAR = ("patients_template.db", "pemf_treatment_history_template.db")


def _isaretli_paket(kok: Path) -> Path:
    d = kok / "database"
    d.mkdir(parents=True)
    for ad in _SABLONLAR:
        c = sqlite3.connect(d / ad)
        c.execute("CREATE TABLE SABLON_ISARETI (x)")
        c.commit()
        c.close()
    return kok


def _tablolar(yol: Path) -> set[str]:
    c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    try:
        return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        c.close()


def test_KRITIK_TAM_frozen_benzetiminde_paket_sablonu_veri_kokune_KOPYALANMAZ_E2_2_7(tmp_path, monkeypatch):
    from utils import path_utils

    paket = _isaretli_paket(tmp_path / "paket")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(paket), raising=False)
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    # Pozitif kontrol: paket-kaynağı yardımcısı bu benzetimde İŞARETLİ pakete çözülür (yoksa kapı kör olurdu).
    assert path_utils.packaged_resource_path("database", _SABLONLAR[0]) == paket / "database" / _SABLONLAR[0]
    assert Path(path_utils.resource_path("database/" + _SABLONLAR[0])) == paket / "database" / _SABLONLAR[0]
    yollar = path_utils.initialize_database()
    kopyalanan = [ad for ad, yol in yollar.items() if Path(yol).exists() and "SABLON_ISARETI" in _tablolar(Path(yol))]
    assert not kopyalanan, f"donmuş EXE benzetiminde açılış paketteki BOŞ ŞABLONU veri köküne koydu: {kopyalanan}"
