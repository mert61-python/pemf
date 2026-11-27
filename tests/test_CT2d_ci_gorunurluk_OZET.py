# -*- coding: utf-8 -*-
"""CT2 d (istem 66 · Y326 katman 7) — GÖRÜNÜRLÜK: junit özeti iş sayfasında, kapsam raporu eser, dal / commit başına TEK özet.

`scripts/ci_junit_ozet.py` (üçüncü parti eylem YOK): junit → sayılar + kırmızılar + atlananlar (neden · defter sınıfı); kart ikilisi
boyutu; `toJSON(needs)` → iş tablosu (kırmızı varsa çıkış 1). İş akışı: özet / eser adımları `if: always()` (kırmızıda da).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ci_junit_ozet_ct2d", KOK / "scripts" / "ci_junit_ozet.py")
oz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oz)

JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_a" name="test_gecer"/>
<testcase classname="tests.test_a" name="test_duser"><failure message="AssertionError: 1 != 2&#10;ayrinti">tb</failure></testcase>
<testcase classname="tests.test_b" name="test_hata"><error message="fixture yok"/></testcase>
<testcase classname="tests.test_ag_yalitimi" name="test_SONDA_provizyon_yolunda_dosya_uretir"><skipped message="alt sureçte kosar"/></testcase>
<testcase classname="tests.test_c" name="test_atla"><skipped message="eser yok"/></testcase>
</testsuite></testsuites>"""


def test_KRITIK_junit_ozeti_SAYILAR_KIRMIZILAR_ATLANANLAR(tmp_path):
    j = tmp_path / "j.xml"
    j.write_text(JUNIT, encoding="utf-8")
    md = oz.junit_ozet(j, "backend · tam kip")
    assert "**1 geçti · 2 kırmızı · 2 atlandı** (toplam 5)" in md
    assert "`tests.test_a::test_duser` | failure | AssertionError: 1 != 2 |" in md
    assert "`tests.test_b::test_hata` | error | fixture yok |" in md
    assert "| 1 | P · alt sureçte kosar |" in md, "defterdeki atlamanın sınıfı yazılmadı"
    assert "| 1 | DEFTER DIŞI · eser yok |" in md


def test_junit_YOKSA_not_ve_cikis_0(tmp_path, capsys):
    assert oz.main([str(tmp_path / "yok.xml")]) == 0
    assert "junit raporu yok" in capsys.readouterr().out


def test_KRITIK_isler_tablosu_KIRMIZIDA_cikis_1(monkeypatch, tmp_path):
    cikti = tmp_path / "ozet.md"
    monkeypatch.setenv("DAL", "duzeltme/x")
    monkeypatch.setenv("SNC", json.dumps({"backend": {"result": "success"}, "launcher": {"result": "failure"}}))
    assert oz.main(["--isler-env", "SNC", "--cikti", str(cikti)]) == 1
    t = cikti.read_text(encoding="utf-8")
    assert "| launcher | ❌ failure |" in t and "**KIRMIZI:** launcher" in t and "`duzeltme/x`" in t
    monkeypatch.setenv("SNC", json.dumps({"backend": {"result": "success"}}))
    assert oz.main(["--isler-env", "SNC", "--cikti", str(cikti)]) == 0


def test_fw_boyut_bin_ozeti(tmp_path, monkeypatch):
    assert "pemf.elf` yok" in oz.fw_boyut(tmp_path)
    (tmp_path / "pemf.elf").write_bytes(b"\x7fELF")
    (tmp_path / "pemf.bin").write_bytes(b"abc")
    monkeypatch.setattr(oz.shutil, "which", lambda a: None)
    md = oz.fw_boyut(tmp_path)
    assert "`pemf.bin` 3 bayt" in md and "ba7816bf" in md


def _isler() -> dict:
    return yaml.safe_load((KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))["jobs"]


def test_KRITIK_is_akisinda_ozet_ve_ESER_adimlari_kirmizida_da_kosar():
    b = _isler()["backend"]["steps"]
    oz_ = [s for s in b if "scripts/ci_junit_ozet.py pytest-junit.xml" in str(s.get("run", ""))]
    assert oz_ and oz_[0]["if"] == "always()" and "$GITHUB_STEP_SUMMARY" in oz_[0]["run"]
    eser = [s for s in b if "coverage.json" in str((s.get("with") or {}).get("path", ""))]
    assert eser and eser[0]["if"] == "always()", "kapsam raporu eser olarak (kırmızıda da) yüklenmiyor"
    ozet = _isler()["ozet"]
    assert set(ozet["needs"]) == {"backend", "sir-taramasi", "launcher", "firmware"} and ozet["if"] == "always()"
    assert "toJSON(needs)" in str(ozet["steps"][-1]["env"]["SONUCLAR"])
