# -*- coding: utf-8 -*-
"""Y312 (PX, istem 60) — paralel süitte (`pytest -n <işçi> --dist loadgroup`) bir dosyanın testleri AYNI işçide, dosya sırasıyla koşar;
`xdist_group("seri")` işaretli testler farklı dosyalarda olsalar da TEK işçide toplanır; işaretsiz testin düğüm kimliği DEĞİŞMEZ.

ÖLÇÜLEN (xdist 3.8.0 `scheduler/loadgroup.py::_split_scope`): `loadgroup` işaretsiz testi kendi düğüm kimliğiyle TEK BAŞINA birim yapar →
`load` gibi dağıtır (PX: gerçek conftest + `-n 3 --dist loadgroup`, `test_gzip_sikistirma` 3 işçiye bölündü). İşaretsiz teste grup
işareti vermek düğüm kimliğine `@grup` ekler → düğüm kimliğine bakan iki kollu meta kapılar (OA24, C2_3_5) kırmızı (PX'te ölçüldü).
DÜZELTME: `tests/xdist_grup.py` zamanlayıcısı + `tests/conftest.py` `pytest_xdist_make_scheduler` (optionalhook, tryfirst).

KAPI:
  · birim: `kapsam()` — işaretsiz → dosya, `@grup` → grup, parametredeki '@' grup sayılmaz; `zamanlayici()` yalnız loadgroup'ta;
  · gerçek conftest bağlantısı: kanca optionalhook + tryfirst ve depo zamanlayıcısını döndürür;
  · uçtan uca (gerçek xdist, 3 işçi): iki dosyanın 6'şar testi tek işçide sırayla; iki dosyaya yayılmış "seri" grubu tek işçide;
    işaretsiz düğüm kimliği soneksiz. KARŞIT: kanca yokken aynı koşu dosyaları BÖLER (kapının boş geçmediği).
  · YGH ağır model grubu (guii Y30 RAM tepesi %99,0 → ağır model dosyaları tek işçide): listedeki her dosya VAR ve `AGIR` birimine düşer,
    açık `xdist_group` işareti listeden önce gelir, liste dışı dosya kendi biriminde kalır; uçtan uca (gerçek xdist, 3 işçi, listedeki iki
    gerçek dosya adıyla): iki ağır dosya AYNI işçide dosya dosya sırayla, hafif dosya başka işçide.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import capraz
import pytest
import xdist_grup

TESTLER = Path(__file__).resolve().parent


@pytest.mark.parametrize(
    ("nodeid", "beklenen"),
    [
        ("tests/test_a.py::test_1", "tests/test_a.py"),
        ("tests/test_a.py::Sinif::test_2[x-y]", "tests/test_a.py"),
        ("tests/test_a.py::test_3[e@posta]", "tests/test_a.py"),
        ("tests/test_b.py::test_1@seri", "seri"),
        ("tests/test_b.py::test_2[e@posta]@seri", "seri"),
    ],
)
def test_KRITIK_kapsam_isaretsiz_DOSYA_isaretli_GRUP(nodeid, beklenen):
    assert xdist_grup.kapsam(nodeid) == beklenen


class _Config:
    def __init__(self, dist: str) -> None:
        self.degerler = {"dist": dist, "tx": ["3*popen"]}

    def getvalue(self, ad):
        return self.degerler[ad]


def test_KRITIK_zamanlayici_yalniz_LOADGROUPta_dosya_birimli():
    capraz.paket_yoksa_atla("xdist", sebep="pytest-xdist (requirements-test.txt) — paralel Y30")
    z = xdist_grup.zamanlayici(_Config("loadgroup"), None)
    assert z is not None and z.numnodes == 3
    assert z._split_scope("tests/test_a.py::test_1") == "tests/test_a.py"
    assert z._split_scope("tests/test_b.py::test_1@seri") == "seri"


@pytest.mark.parametrize("dist", ["no", "load", "loadfile", "loadscope", "worksteal", "each"])
def test_KRITIK_baska_kiplerde_zamanlayici_YOK_xdist_varsayilani(dist):
    assert xdist_grup.zamanlayici(_Config(dist), None) is None


def test_KRITIK_gercek_conftest_kancasi_OPTIONAL_TRYFIRST_ve_depo_zamanlayicisi(request):
    capraz.paket_yoksa_atla("xdist", sebep="pytest-xdist (requirements-test.txt) — paralel Y30")
    conftest = next(
        p
        for p in request.config.pluginmanager.get_plugins()
        if Path(getattr(p, "__file__", "") or ".").resolve() == TESTLER / "conftest.py"
    )
    kanca = conftest.pytest_xdist_make_scheduler
    secenek = getattr(kanca, "pytest_impl", {})
    assert secenek.get("optionalhook") is True, "xdist'siz ortamda (CI eski kurulum) bilinmeyen kanca toplamayı DÜŞÜRÜR"
    assert secenek.get("tryfirst") is True, "xdist'in kendi loadgroup zamanlayıcısı önce dönebilir (firstresult)"
    z = kanca(config=_Config("loadgroup"), log=None)
    assert type(z).__name__ == "DosyaGrubuZamanlayici" and z._split_scope("tests/x.py::t") == "tests/x.py"
    assert kanca(config=_Config("no"), log=None) is None


_DOSYA = """\
import os
import pytest
{isaret}

@pytest.mark.parametrize("i", range({adet}))
def test_sira(i):
    isci = os.environ.get("PYTEST_XDIST_WORKER", "-")
    # her işçi KENDİ dosyasına yazar: süreçler arası "a" kipi eklemesi Windows'ta atomik değil (PX'te boş / kayıp satır ölçüldü)
    with open(os.path.join(os.environ["Y312_KAYIT"], isci + ".txt"), "a", encoding="utf-8") as f:
        f.write(f"{{isci}} {ad} {{i}}\\n")
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


def _uctan_uca(tmp_path: Path, kanca: bool) -> tuple[dict[str, list[tuple[str, int]]], str]:
    capraz.paket_yoksa_atla("xdist", sebep="pytest-xdist (requirements-test.txt) — paralel Y30")
    d = tmp_path / ("kancali" if kanca else "kancasiz")
    d.mkdir()
    (d / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    if kanca:
        (d / "conftest.py").write_text(_CONFTEST.format(testler=str(TESTLER)), encoding="utf-8")
    for ad, adet, isaret in (("a", 6, ""), ("b", 6, ""), ("s1", 3, "seri"), ("s2", 3, "seri")):
        satir = f'pytestmark = pytest.mark.xdist_group("{isaret}")' if isaret else ""
        (d / f"test_{ad}.py").write_text(_DOSYA.format(isaret=satir, adet=adet, ad=ad), encoding="utf-8")
    kayit = tmp_path / ("kayit_kancali" if kanca else "kayit_kancasiz")
    kayit.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env.update(Y312_KAYIT=str(kayit), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-n", "3", "--dist", "loadgroup", "-p", "no:cacheprovider", "-v"],
        cwd=d, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )  # fmt: skip
    assert r.returncode == 0 and "18 passed" in r.stdout, f"rc={r.returncode}\n{(r.stdout + r.stderr)[-2500:]}"
    sonuc: dict[str, list[tuple[str, int]]] = {}
    for dosya in sorted(kayit.glob("*.txt")):
        for satir in dosya.read_text(encoding="utf-8").splitlines():
            isci, ad, i = satir.split()
            sonuc.setdefault(ad, []).append((isci, int(i)))
    assert sum(len(v) for v in sonuc.values()) == 18, sonuc
    return sonuc, r.stdout


def test_KRITIK_UCTAN_UCA_dosya_tek_iscide_SIRAYLA_seri_grubu_tek_iscide_kimlik_SONEKSIZ(tmp_path):
    s, cikti = _uctan_uca(tmp_path, kanca=True)
    for ad in ("a", "b"):
        assert len({isci for isci, _ in s[ad]}) == 1, f"test_{ad}.py işçilere BÖLÜNDÜ: {s[ad]}"
        assert [i for _, i in s[ad]] == list(range(6)), f"test_{ad}.py dosya sırası bozuldu: {s[ad]}"
        assert all(isci.startswith("gw") for isci, _ in s[ad]), f"test_{ad}.py xdist işçisinde koşmadı: {s[ad]}"
    seri = s["s1"] + s["s2"]
    assert len({isci for isci, _ in seri}) == 1, f"'seri' grubu tek işçide DEĞİL: {seri}"
    assert re.search(r"PASSED test_a\.py::test_sira\[0\]\s*$", cikti, re.M), (
        "işaretsiz düğüm kimliği DEĞİŞTİ (sonek eklendi)"
    )


def test_KARSIT_kanca_YOKKEN_loadgroup_dosyalari_BOLER(tmp_path):
    s, _ = _uctan_uca(tmp_path, kanca=False)
    bolunen = [ad for ad in ("a", "b") if len({isci for isci, _ in s[ad]}) > 1]
    assert bolunen, f"kancasız loadgroup dosyaları bölmedi — uçtan uca kapı ayırt edemiyor: {s}"


KOK = TESTLER.parent


def test_KRITIK_AGIR_MODEL_dosyalari_VAR_ve_TEK_birimde_digerleri_kendi_dosyasinda():
    liste = sorted(xdist_grup.AGIR_MODEL_DOSYALARI)
    assert len(liste) >= 2, "ağır model listesi boş — Y30 RAM tepesi geri döner (YGH)"
    for yol in liste:
        assert yol.startswith("tests/test_") and yol.endswith(".py"), yol
        assert (KOK / yol).is_file(), (
            f"ağır model listesinde OLMAYAN dosya: {yol} (silindi / taşındı → listeden çıkar ya da güncelle)"
        )
        assert xdist_grup.kapsam(f"{yol}::test_x") == xdist_grup.AGIR, yol
        assert xdist_grup.kapsam(f"{yol}::Sinif::test_y[e@posta]") == xdist_grup.AGIR, yol
        assert xdist_grup.kapsam(f"{yol}::test_z@seri") == xdist_grup.SERI, (
            "açık xdist_group işareti listeden ÖNCE gelmeli"
        )
    assert xdist_grup.AGIR not in {xdist_grup.kapsam(f"tests/test_hafif_{i}.py::t") for i in range(3)}
    assert xdist_grup.kapsam("tests/test_hafif.py::t") == "tests/test_hafif.py"
    # Listenin dosya ADI eşleşmesi: aynı adlı başka dizindeki dosya ağır gruba düşmez (yol tam eşleşir).
    assert xdist_grup.kapsam("tests/alt/" + liste[0].split("/", 1)[1] + "::t") != xdist_grup.AGIR


_AGIR_DOSYA = """\
import os
import pytest


@pytest.mark.parametrize("i", range(4))
def test_sira(i):
    isci = os.environ.get("PYTEST_XDIST_WORKER", "-")
    with open(os.path.join(os.environ["Y312_KAYIT"], isci + ".txt"), "a", encoding="utf-8") as f:
        f.write(f"{{isci}} {ad} {{i}}\\n")
"""


def test_KRITIK_UCTAN_UCA_AGIR_MODEL_dosyalari_AYNI_iscide_dosya_dosya_SIRAYLA(tmp_path):
    capraz.paket_yoksa_atla("xdist", sebep="pytest-xdist (requirements-test.txt) — paralel Y30")
    agir = sorted(xdist_grup.AGIR_MODEL_DOSYALARI)[:2]
    d = tmp_path / "proje"
    (d / "tests").mkdir(parents=True)
    (d / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (d / "conftest.py").write_text(_CONFTEST.format(testler=str(TESTLER)), encoding="utf-8")
    adlar = {"A1": agir[0], "A2": agir[1], "H1": "tests/test_hafif_y312_1.py", "H2": "tests/test_hafif_y312_2.py"}
    for ad, yol in adlar.items():
        (d / yol).write_text(_AGIR_DOSYA.format(ad=ad), encoding="utf-8")
    kayit = tmp_path / "kayit"
    kayit.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env.update(Y312_KAYIT=str(kayit), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-n", "3", "--dist", "loadgroup", "-p", "no:cacheprovider", "-v"],
        cwd=d, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )  # fmt: skip
    assert r.returncode == 0 and "16 passed" in r.stdout, f"rc={r.returncode}\n{(r.stdout + r.stderr)[-2500:]}"
    s: dict[str, list[tuple[str, int]]] = {}
    for dosya in sorted(kayit.glob("*.txt")):
        for satir in dosya.read_text(encoding="utf-8").splitlines():
            isci, ad, i = satir.split()
            s.setdefault(ad, []).append((isci, int(i)))
    agir_isci = {isci for ad in ("A1", "A2") for isci, _ in s[ad]}
    assert len(agir_isci) == 1 and next(iter(agir_isci)).startswith("gw"), f"ağır model dosyaları işçilere BÖLÜNDÜ: {s}"
    for ad in ("A1", "A2"):
        assert [i for _, i in s[ad]] == list(range(4)), f"{adlar[ad]} dosya sırası bozuldu: {s[ad]}"
    # Aynı işçide ağır dosyalar art arda (grup tek birim): işçinin kendi kaydında A1'ler bitmeden A2 başlamaz ya da tersi.
    sira = [
        satir.split()[1]
        for satir in (kayit / (next(iter(agir_isci)) + ".txt")).read_text(encoding="utf-8").splitlines()
    ]
    agir_sira = [a for a in sira if a in ("A1", "A2")]
    assert agir_sira in (["A1"] * 4 + ["A2"] * 4, ["A2"] * 4 + ["A1"] * 4), f"ağır dosyalar iç içe geçti: {sira}"
    hafif_isci = {isci for ad in ("H1", "H2") for isci, _ in s[ad]}
    assert hafif_isci - agir_isci, f"hafif dosyalar da ağır işçide — grup diğerlerini ayırmıyor: {s}"
    assert re.search(r"PASSED " + re.escape(agir[0]) + r"::test_sira\[0\]\s*$", r.stdout, re.M), (
        "ağır dosyanın düğüm kimliği DEĞİŞTİ (sonek eklendi)"
    )
