# -*- coding: utf-8 -*-
"""Y312 · YGH (istem 59, sahip 20-11 "CI paraleli de zincire") — GitHub CI backend testleri Y30 gibi PARALEL koşar:
`pytest tests -n auto --dist loadgroup` (YS1b · Y320: yalnız Windows ürün hattı — `ubuntu-latest` kopyası kalktı).

NEDEN `--dist loadgroup` ŞART: `tests/conftest.py` `pytest_xdist_make_scheduler` depo zamanlayıcısını YALNIZ loadgroup'ta döndürür
(`tests/xdist_grup.py`: dosya birimi + `xdist_group("seri")` tek işçide). Yalnız `-n` (= `--dist load`) bir dosyanın testlerini
işçilere BÖLER → dosya içi sıraya dayanan iki kollu kapılar ve modül fikstürleri bozulur.

KAPI:
  · iş akışı: her işletim sisteminin TEK `pytest tests` adımı `-n auto` + `--dist loadgroup` taşır, `-p no:xdist` yok; `-rfEs`, junit ve
    (Windows) `--cov` yerinde (ayrıntıları kendi kapıları kilitler) · pytest-xdist + execnet test bağımlılıklarında SABİT sürümle ve CI
    bunları pytest adımından ÖNCE kurar · backend iş zaman aşımı ≥ 60 dk (25 dk ~790 testlik süitten kalmaydı).
  · uçtan uca (gerçek xdist + pytest-cov, 2 işçi, depo zamanlayıcısıyla): iki dosya farklı işçide koşar; işçilerde yürüyen kod kapsamda
    BİRLEŞİR (%100); paralel koşunun junit'ini `scripts/ci_sqlcipher_atlama_kapisi.py` OKUR ("sqlcipher" nedenli atlama → 1; o test
    çıkarılınca → 0).
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import capraz
import yaml

KOK = Path(__file__).resolve().parents[1]
TESTLER = KOK / "tests"
IS_AKISI = KOK / ".github" / "workflows" / "tests.yml"
ATLAMA_KAPISI = KOK / "scripts" / "ci_sqlcipher_atlama_kapisi.py"
#: matrix `os` → `runner.os`
_ISLETIM = {"ubuntu-latest": "Linux", "windows-latest": "Windows"}


def _backend() -> dict:
    return yaml.safe_load(IS_AKISI.read_text(encoding="utf-8"))["jobs"]["backend"]


def _kapsar(adim: dict, isletim: str) -> bool:
    """Adımın `if:` koşulu bu işletim sisteminde koşar mı? (Yalnız iş akışındaki basit biçimler.)"""
    kosul = str(adim.get("if", "")).strip()
    # YS1g: junit eseri adımı `if: always()` — her işletim sisteminde (kırmızıda da) koşar.
    if not kosul or kosul in ("always()", "${{ always() }}"):
        return True
    # CT2 c: kip / alan koşulları (`env.CI_KIP == 'tam'` …) işletim sisteminden BAĞIMSIZ — OS kısmı ayrıca değerlendirilir.
    kosul = re.sub(r"\s*&&\s*env\.CI_(?:KIP|ALAN)\s*(?:==|!=)\s*'\w+'\s*$", "", kosul)
    if re.fullmatch(r"env\.CI_(?:KIP|ALAN)\s*(?:==|!=)\s*'\w+'", kosul):
        return True
    m = re.fullmatch(r"runner\.os\s*(==|!=)\s*'(\w+)'", kosul)
    assert m, f"tanınmayan adım koşulu (kapı genişletilmeli): {kosul!r}"
    return (m.group(2) == isletim) == (m.group(1) == "==")


def _deger(argumanlar: list[str], bayrak: str) -> str | None:
    """`-n auto` / `-n=auto` / `--dist loadgroup` / `--dist=loadgroup` biçimlerinden bayrağın değeri (yoksa None)."""
    for i, a in enumerate(argumanlar):
        if a == bayrak and i + 1 < len(argumanlar):
            return argumanlar[i + 1]
        if a.startswith(bayrak + "="):
            return a.split("=", 1)[1]
    return None


#: YS1i: süit UAC-süzgeçli belirteçle koşar (scripts/ci_kisitli_belirtec.py) — bu önek pytest argümanlarının ÖNÜNDE; kapı pytest kısmını
#: ölçer (önekin varlığını tests/test_ci_kisitli_belirtec_YS1i.py kilitler).
_KISITLI_ONEK = ["python", "scripts/ci_kisitli_belirtec.py"]


def _oneksiz(a: list[str]) -> list[str]:
    return a[len(_KISITLI_ONEK) :] if a[: len(_KISITLI_ONEK)] == _KISITLI_ONEK else a


def _pytest_adimlari() -> dict[str, list[str]]:
    is_ = _backend()
    sonuc: dict[str, list[str]] = {}
    for os_adi in is_["strategy"]["matrix"]["os"]:
        isletim = _ISLETIM[os_adi]
        adimlar = [a for a in is_["steps"] if _kapsar(a, isletim) and "pytest tests" in str(a.get("run", ""))]
        assert len(adimlar) == 1, f"{isletim}: tam olarak bir `pytest tests` adımı bekleniyordu, bulunan {len(adimlar)}"
        sonuc[isletim] = _oneksiz(shlex.split(str(adimlar[0]["run"])))
    return sonuc


def test_KRITIK_CI_pytest_adimi_PARALEL_loadgroup_YALNIZ_windowsta_Y320():
    """MUTASYON: `-n auto`yu silmek · `--dist loadgroup` → `load` · `-p no:xdist` eklemek · matrise `ubuntu-latest`i geri koymak
    (Y320: CI yalnız Windows ürün hattı) → KIRMIZI."""
    adimlar = _pytest_adimlari()
    assert set(adimlar) == {"Windows"}, f"backend matrisi yalnız windows-latest olmalı (Y320): {sorted(adimlar)}"
    for isletim, a in adimlar.items():
        assert a[:2] == ["pytest", "tests"], f"{isletim}: {a[:4]}"
        assert _deger(a, "-n") == "auto", f"{isletim}: `-n auto` yok — CI SERİ koşar (YGH)"
        assert _deger(a, "--dist") == "loadgroup", (
            f"{isletim}: `--dist loadgroup` değil ({_deger(a, '--dist')!r}) — depo zamanlayıcısı (dosya birimi + seri grubu, "
            "tests/xdist_grup.py) DEVREYE GİRMEZ, dosyalar işçilere bölünür"
        )
        assert not any(x == "no:xdist" or x.endswith("no:xdist") for x in a), f"{isletim}: xdist kapatılmış"
        assert "-rfEs" in a and any(x.startswith("--junitxml") for x in a), f"{isletim}: -rfEs / junit kayboldu"
    assert "--cov" in adimlar["Windows"], "Windows adımında kapsam ratcheti (--cov) kayboldu"


def test_KRITIK_backend_isi_ZAMAN_ASIMI_tam_suite_yeter():
    """25 dk (10-08, ~790 test) bugünkü ~12 800 testlik kapsamlı Windows adımına paralelde de yetmez → iş zaman aşımıyla düşerdi."""
    dakika = int(_backend()["timeout-minutes"])
    assert dakika >= 60, f"backend iş zaman aşımı {dakika} dk — tam süit (paralel, 4 çekirdekli koşucu, --cov) sığmaz"


def test_KRITIK_xdist_ve_execnet_SABIT_surumle_ve_CI_pytestten_ONCE_kurar():
    req = (KOK / "requirements-test.txt").read_text(encoding="utf-8")
    assert re.search(r"^pytest-xdist==\d", req, re.M), "pytest-xdist test bağımlılıklarında SABİT değil"
    assert re.search(r"^execnet==\d", req, re.M), "execnet (xdist süreç köprüsü) test bağımlılıklarında SABİT değil"
    adimlar = _backend()["steps"]
    kur = [i for i, a in enumerate(adimlar) if "pip install -r requirements-test.txt" in str(a.get("run", ""))]
    pyt = [i for i, a in enumerate(adimlar) if "pytest tests" in str(a.get("run", ""))]
    assert kur and pyt, f"kurulum {kur} / pytest {pyt} adımı bulunamadı"
    assert max(kur) < min(pyt), "test bağımlılıkları (xdist) pytest adımından SONRA kuruluyor"


_MODUL = """\
def a():
    return 1


def b():
    return 2
"""
_TEST_1 = """\
import pemf_y312_cov


def test_a1():
    assert pemf_y312_cov.a() == 1


def test_a2():
    assert pemf_y312_cov.a() == 1
"""
_TEST_2 = """\
import pytest
import pemf_y312_cov


def test_b():
    assert pemf_y312_cov.b() == 2


def test_sqlcipher_kolu():
    pytest.skip("sqlcipher3 yok - gercek baglayici kolu")
"""
_CONFTEST = """\
import sys
import pytest
sys.path.insert(0, {testler!r})
import xdist_grup


@pytest.hookimpl(optionalhook=True, tryfirst=True)
def pytest_xdist_make_scheduler(config, log):
    return xdist_grup.zamanlayici(config, log)
"""


def _atlama_kapisi():
    spec = importlib.util.spec_from_file_location("ci_sqlcipher_atlama_kapisi", ATLAMA_KAPISI)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_KRITIK_UCTAN_UCA_paralel_kapsam_BIRLESIR_ve_junit_atlama_kapisinca_OKUNUR(tmp_path, capsys):
    capraz.paket_yoksa_atla("xdist", sebep="pytest-xdist (requirements-test.txt) — paralel CI")
    capraz.paket_yoksa_atla("pytest_cov", sebep="pytest-cov (requirements-test.txt) — CI kapsam adımı")
    d = tmp_path / "proje"
    d.mkdir()
    (d / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (d / "conftest.py").write_text(_CONFTEST.format(testler=str(TESTLER)), encoding="utf-8")
    (d / "pemf_y312_cov.py").write_text(_MODUL, encoding="utf-8")
    (d / "test_1.py").write_text(_TEST_1, encoding="utf-8")
    (d / "test_2.py").write_text(_TEST_2, encoding="utf-8")
    junit = tmp_path / "junit.xml"
    # Dış koşunun pytest / kapsam değişkenleri iç koşuya SIZMASIN (CI Windows adımı --cov altında koşar; COVERAGE_FILE ortak veri dosyası).
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "COV_CORE_", "COVERAGE_"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-n", "2", "--dist", "loadgroup", "-v", "-rfEs", "-p", "no:cacheprovider",
         "--cov=pemf_y312_cov", "--cov-report=term", f"--junitxml={junit}"],
        cwd=d, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )  # fmt: skip
    cikti = r.stdout + r.stderr
    assert r.returncode == 0 and re.search(r"\b3 passed, 1 skipped\b", cikti), f"rc={r.returncode}\n{cikti[-2500:]}"
    isci = {
        ad: m.group(1)
        for ad in ("test_1.py::test_a1", "test_2.py::test_b")
        if (m := re.search(r"\[(gw\d+)\] \[\s*\d+%\] PASSED " + re.escape(ad) + r"\b", cikti))
    }
    assert len(isci) == 2 and isci["test_1.py::test_a1"] != isci["test_2.py::test_b"], (
        f"iki dosya FARKLI işçide koşmadı — kapsam birleşimi kanıtlanamaz: {isci}\n{cikti[-2500:]}"
    )
    toplam = re.search(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%", cikti, re.M)
    assert toplam and toplam.group(2) == "0" and toplam.group(3) == "100", (
        f"işçi kapsamları BİRLEŞMEDİ (a() ve b() ayrı işçilerde koştu): {toplam and toplam.group(0)}\n{cikti[-2500:]}"
    )
    kapi = _atlama_kapisi()
    sayi, atlananlar = kapi.sqlcipher_atlamalari(str(junit))
    assert sayi == 4 and len(atlananlar) == 1 and "test_sqlcipher_kolu" in atlananlar[0], (sayi, atlananlar)
    assert kapi.main([str(junit)]) == 1
    # KARŞIT: o test çıkarılınca aynı paralel junit 0 verir (1'i başka bir öğe üretmiyor).
    agac = ET.parse(junit)
    for ebeveyn in agac.getroot().iter():
        for tc in [c for c in ebeveyn if c.tag == "testcase" and c.get("name") == "test_sqlcipher_kolu"]:
            ebeveyn.remove(tc)
    temiz = tmp_path / "junit_temiz.xml"
    agac.write(temiz, encoding="utf-8")
    assert kapi.main([str(temiz)]) == 0
    capsys.readouterr()
