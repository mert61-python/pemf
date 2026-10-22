# Author: mertaygn, cglrgrkn
"""LN L10 · ortak build kimliği (DUZELTME-D4B-İNCELEME §9 #7 — "make_manifest iki katmanın aynı build'den geldiğini ölçemez").

`build_tools/make_base_zip.py` iki katmanı yayın dizinine yerleştirip doğruladıktan sonra `base-katman-seti.json`'a ikisinin sha'sını
yazar (katmanların İÇİNE değil — deps sha'sı paket belirlenimciliği gereği sabit kalmalı). `scripts/make_manifest.py` yerelde win-x64
app + deps birlikte varsa kaydı okur; sha'lar TUTMAZSA (karma set: elle kopyalanmış eski deps / yeni app) manifest YAZILMAZ.
Kimlik YOKSA (bu değişiklikten önceki çıktı dizini) yüksek sesli UYARI — karar S-LN.6.

Betik KOŞTURULMAZ (ORTAK §1): yalnız saf denetim fonksiyonu sahte zip'lerle çağrılır; `main()`'in onu mühürlemeden ÖNCE çağırdığı yapısal ölçülür.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "make_manifest.py"


@pytest.fixture(scope="module")
def mm():
    spec = importlib.util.spec_from_file_location("make_manifest_l10", BETIK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # yalnız tanımlar; `main()` ÇAĞRILMAZ
    return m


def _zip(yol: Path, isaret: bytes) -> str:
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_STORED) as z:
        z.writestr(zipfile.ZipInfo("PEMF_Backend/x.bin", date_time=(1980, 1, 1, 0, 0, 0)), isaret)
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _kimlik(d: Path, app: str, deps: str) -> None:
    (d / "base-katman-seti.json").write_text(
        json.dumps({"app": {"sha256": app}, "deps": {"sha256": deps}}), encoding="utf-8"
    )


def test_KRITIK_ayni_kosunun_katmanlari_TUTARLI(mm, tmp_path):
    a, d = _zip(tmp_path / "base-app.zip", b"APP-N"), _zip(tmp_path / "base-deps.zip", b"DEPS-N")
    _kimlik(tmp_path, a, d)
    assert mm.katman_seti_tutarsizligi(tmp_path) is None


@pytest.mark.parametrize("karma", ["deps", "app"])
def test_KRITIK_KARMA_set_REDDEDILIR(mm, tmp_path, karma):
    """Son make_base_zip koşusunun kimliği var; bir katman başka koşudan (elle kopyalanmış) → RED."""
    a, d = _zip(tmp_path / "base-app.zip", b"APP-N"), _zip(tmp_path / "base-deps.zip", b"DEPS-N")
    _kimlik(tmp_path, a, d)
    _zip(tmp_path / f"base-{karma}.zip", b"ESKI-KOSU")
    neden = mm.katman_seti_tutarsizligi(tmp_path)
    assert neden and "KARMA" in neden and karma in neden, neden


def test_KARSIT_kimlik_YOKSA_UYARI_ve_engel_DEGIL(mm, tmp_path, capsys):
    """S-LN.6: bu değişiklikten önceki çıktı dizini — yüksek sesli uyarı, ret değil."""
    _zip(tmp_path / "base-app.zip", b"A"), _zip(tmp_path / "base-deps.zip", b"D")
    assert mm.katman_seti_tutarsizligi(tmp_path) is None
    assert "DENETLENEMEDI" in capsys.readouterr().err


def test_KARSIT_tek_katman_ya_da_hic_yoksa_DENETIM_YOK(mm, tmp_path):
    assert mm.katman_seti_tutarsizligi(tmp_path) is None
    _zip(tmp_path / "base-app.zip", b"A")
    _kimlik(tmp_path, "0" * 64, "0" * 64)
    assert mm.katman_seti_tutarsizligi(tmp_path) is None, "tek katman: taşıma kuralı geçerli, bu denetim değil"


def test_KRITIK_bozuk_kimlik_REDDEDILIR(mm, tmp_path):
    _zip(tmp_path / "base-app.zip", b"A"), _zip(tmp_path / "base-deps.zip", b"D")
    (tmp_path / "base-katman-seti.json").write_text("{bozuk", encoding="utf-8")
    assert "okunamadi" in (mm.katman_seti_tutarsizligi(tmp_path) or "")
    (tmp_path / "base-katman-seti.json").write_text("[1, 2]", encoding="utf-8")
    assert "bozuk" in (mm.katman_seti_tutarsizligi(tmp_path) or "")


def test_KRITIK_main_MUHURLEMEDEN_once_denetler_ve_REDDE_yazmaz():
    kaynak = BETIK.read_text(encoding="utf-8")
    g = kaynak[kaynak.index("def main() -> int:") :]
    i = g.index("_karma = katman_seti_tutarsizligi(args.dir)")
    j = g.index('base_url = f"https://github.com/')
    k = g.index("json.dumps(manifest") if "json.dumps(manifest" in g else g.index("out_path.write_text")
    assert i < j < k, "denetim mühürlemeden (sha / URL / yazım) ÖNCE değil"
    blok = g[i : g.index("\n\n", g.index("if _karma:", i))]
    assert re.search(r"if _karma:.*return 1", blok, re.S), "karma sette çıkış 1 değil"
