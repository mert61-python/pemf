# -*- coding: utf-8 -*-
"""CT1 (istem 66 · Y311 fark kapsamı): CI'ın KOMUT SATIRINDAN çağırdığı betiklerin giriş noktası (`python scripts/<betik>.py …`) gerçekten
`main()`'i çağırıp ÇIKIŞ KODUNU süreç çıkışına taşır — iş akışı adımı bu koda bakar (0 = yeşil). `runpy` ile `__main__` olarak koşar
(süreç içi: ölçülür); konsol akışları geçici nesneye bağlanır (betikler UTF-8'e yeniden yapılandırır)."""

from __future__ import annotations

import io
import runpy
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "betik,argumanlar,beklenen",
    [
        ("ci_atlanan_kapisi.py", ["yok-junit.xml"], 2),
        ("fark_kapsami.py", [], 2),
        ("kapsam_tabani_kapisi.py", ["--veri", "yok.coverage"], 2),
        ("firmware_kapsam.py", ["--kok", "."], 2),
        ("ci_modelleri.py", ["paketle"], 2),
    ],
)
def test_KRITIK_betik_giris_noktasi_main_cikis_kodunu_TASIR(betik, argumanlar, beklenen, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [betik, *argumanlar])
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(KOK / "scripts" / betik), run_name="__main__")
    assert e.value.code == beklenen
