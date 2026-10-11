# -*- coding: utf-8 -*-
"""4A-1.9 (A1 incelemesi) — `tests/gitleaks_ikili.bul()` pre-commit önbelleğinde rev'e değil mtime'a bakıyor.

ÖLÇÜLEN (A1, 2026-10-11; `_inceleme/kayit/k4_onbellek_secimi.txt`): sahte PRE_COMMIT_HOME'da `repoESKI` (`.pre-commit-config.yaml` rev'i
v8.24.0; pre-commit'in kendi eşlemesi `db.db repos(repo, ref, path)` onu gösteriyor) + `repoYENI` (başka bir rev / başka ikili, mtime
daha YENİ) → `bul()` `repoYENI`yi seçti. Bulucu docstring'i "Sürüm: .pre-commit-config.yaml rev" diyor ve açık yolda "yanlış sürüm
ölçülmesin" diye başka ikiliye düşmüyor; önbellekte ise yapılandırılmış sürümü hiç doğrulamıyor. Bu makinede bugün tek rev var (risk:
`pre-commit autoupdate` / rev geri alma sonrası iki rev'li geliştirici önbelleği). CI taze önbellekle tek rev kurar.

Kapı: db.db yapılandırılmış rev'i gösteriyorsa O seçilir; db.db var ama yapılandırılmış rev kurulu değilse yanlış sürüm SEÇİLMEZ (None);
db.db yoksa eski davranış (en yeni) — 4-A'nın pozitif kontrolü (sahte evde db'siz önbellek) korunur.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path

import gitleaks_ikili
import pytest

_REPO = "https://github.com/gitleaks/gitleaks"


def _rev() -> str:
    cfg = (Path(__file__).resolve().parents[1] / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    return re.search(r"repo:\s*https://github\.com/gitleaks/gitleaks\s+rev:\s*(\S+)", cfg).group(1)


def _onbellek(tmp_path: Path, db_satirlari):
    pc = tmp_path / "pc"
    yollar = {}
    for ad, gecmis in (("repoESKI", 86400), ("repoYENI", 0)):
        b = pc / ad / "golangenv-default" / "bin" / "gitleaks.exe"
        b.parent.mkdir(parents=True)
        b.write_bytes(b"")
        t = time.time() - gecmis
        os.utime(b, (t, t))
        yollar[ad] = b
    if db_satirlari is not None:
        con = sqlite3.connect(pc / "db.db")
        con.execute(
            "CREATE TABLE repos (repo TEXT NOT NULL, ref TEXT NOT NULL, path TEXT NOT NULL, PRIMARY KEY (repo, ref))"
        )
        for ref, ad in db_satirlari:
            con.execute("INSERT INTO repos VALUES (?,?,?)", (_REPO, ref, str(pc / ad)))
        con.commit()
        con.close()
    return pc, yollar


@pytest.fixture()
def ortam(monkeypatch, tmp_path):
    for k in ("PEMF_GITLEAKS", "XDG_CACHE_HOME"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "bos_path"))
    monkeypatch.setattr(gitleaks_ikili.Path, "home", classmethod(lambda cls: tmp_path / "ev_yok"))
    return monkeypatch


def test_KRITIK_db_yapilandirilmis_revi_gosteriyorsa_O_SECILIR(tmp_path, ortam):
    pc, yollar = _onbellek(tmp_path, [(_rev(), "repoESKI"), ("v0.0.1-baska", "repoYENI")])
    ortam.setenv("PRE_COMMIT_HOME", str(pc))
    assert gitleaks_ikili.bul() == str(yollar["repoESKI"]), (
        f"bulucu yapılandırılmış rev ({_rev()}) yerine mtime'ı en yeni ikiliyi seçti: {gitleaks_ikili.bul()}"
    )


def test_KRITIK_db_var_ama_yapilandirilmis_rev_KURULU_DEGILSE_yanlis_surum_SECILMEZ(tmp_path, ortam):
    pc, _ = _onbellek(tmp_path, [("v0.0.1-baska", "repoYENI")])
    ortam.setenv("PRE_COMMIT_HOME", str(pc))
    assert gitleaks_ikili.bul() is None, f"yapılandırılmamış sürüm seçildi: {gitleaks_ikili.bul()}"


def test_KARSIT_db_YOKSA_en_yeni_secilir(tmp_path, ortam):
    pc, yollar = _onbellek(tmp_path, None)
    ortam.setenv("PRE_COMMIT_HOME", str(pc))
    assert gitleaks_ikili.bul() == str(yollar["repoYENI"])
