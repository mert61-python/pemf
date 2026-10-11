# -*- coding: utf-8 -*-
"""4B-2.13 (4-B incelemesi A2) — D4.20'nin ÇEKİRDEK düzeltmesi (bağlamı çözülemeyen Dockerfile `continue` ile ATLANMAZ, `baglamsiz` kolu)
hiçbir testte ölçülmüyordu: 4-B'nin m6'sı (`baglamsiz.append(rel)` silinip yalnız `continue`) "bugün eşdeğer" kaldı — depodaki her Dockerfile
bugün çözüldüğü için. m6 + `COMPOSE_DISI_BAGLAM = {}` (m8) birlikte de 116 test YEŞİL: `Dockerfile.ai-full`'un COPY kaynakları sessizce
denetim DIŞINA düşer. Bu kapı GERÇEK COPY kapısını (`test_betikler_ACILIYOR.test_KRITIK_dockerfile_COPY_kaynaklari_DISKTE_VAR`) eşdeğerliği
KALDIRAN iki girdiyle koşturur: (1) tablodan düşen gerçek Dockerfile, (2) compose'da da tabloda da olmayan YENİ bir Dockerfile (tmp_path).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))

import test_betikler_ACILIYOR as acil  # noqa: E402


def test_KRITIK_tablodan_dusen_compose_disi_Dockerfile_COPY_kapisini_KIRMIZI_yapar(monkeypatch):
    assert "docker/Dockerfile.ai-full" in acil.COMPOSE_DISI_BAGLAM, "VAKUM: tablo değişti — kapıyı güncelle"
    monkeypatch.setattr(acil, "COMPOSE_DISI_BAGLAM", {})
    with pytest.raises(AssertionError, match=r"ÇÖZÜLEMEYEN Dockerfile.*Dockerfile\.ai-full"):
        acil.test_KRITIK_dockerfile_COPY_kaynaklari_DISKTE_VAR()


def test_KRITIK_compose_ve_tabloda_OLMAYAN_yeni_Dockerfile_ATLANMAZ(monkeypatch, tmp_path):
    yeni = tmp_path / "Dockerfile.yeni_servis"
    yeni.write_text("FROM scratch\nCOPY olmayan_kaynak /x\n", encoding="utf-8")
    orj = acil._takipli

    def _takipli(desenler: list[str]) -> list[str]:
        return orj(desenler) + ([str(yeni)] if desenler == ["**/Dockerfile*"] else [])

    monkeypatch.setattr(acil, "_takipli", _takipli)
    with pytest.raises(AssertionError, match=r"ÇÖZÜLEMEYEN Dockerfile.*Dockerfile\.yeni_servis"):
        acil.test_KRITIK_dockerfile_COPY_kaynaklari_DISKTE_VAR()
