# -*- coding: utf-8 -*-
"""CT1 c (istem 66 · Y324): SESSİZ ATLAMA BİTER — CI'da atlanan her test `tests/ci_atlanan_defteri.json`'da gerekçeli olmalı.

Sınıflar: (Y) yalnız yayın makinesinde bulunan eser (kurucu EXE, APK, `base-deps.zip`, sevk ağacı, Tauri NSIS şablonu, gömülü derleme
Python'u, depo dışı TR tabanı) → CI'da gerekçeli atlar, Y30'da (`PEMF_YAYIN_MAKINESI=1`) ATLARSA KIRMIZI · (P) platform / ortam (CI
koşucusunda var olamayan: donanım, oturum belirteci, SYSTEM kasası, alt-süreç tasarımı) → gerekçeli atlama kalır. (M) model / test
girdisi ve (D) diğer deftere GİREMEZ — defter kırmızıyı saklamak için kullanılamaz.

Kapı (`scripts/ci_atlanan_kapisi.py <junit>`): defterde olmayan atlama → KIRMIZI · defterde M / D / bilinmeyen sınıf ya da gerekçesiz
kayıt → KIRMIZI · atlama nedeni model / eser yokluğu olan defter kaydı (M kılıklı Y / P) → KIRMIZI · koşuda ATLAMAYAN (geçen / yok) kayıt
→ KIRMIZI (bayat; `--kismi` yalnız koşuda olmayanı affeder). Y30 kipi: `tests/yayin_makinesi_kapisi.py` eklentisi `yalniz_yayin_makinesi`
işaretli testin (ya da modülün) atlamasını BAŞARISIZLIĞA çevirir; `capraz.atla(…, yalniz_yayin=True)` CI ZORUNLU kipinde düşmez, atlar."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
DEFTER = KOK / "tests" / "ci_atlanan_defteri.json"
_spec = importlib.util.spec_from_file_location("ci_atlanan_kapisi_ct1c", KOK / "scripts" / "ci_atlanan_kapisi.py")
kapi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kapi)


def _junit(tmp_path: Path, vakalar: list[tuple[str, str, str | None]], ad: str = "junit.xml") -> Path:
    """vakalar: (classname, name, atlama_nedeni | None=geçti)."""
    s = ['<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">']
    for c, n, neden in vakalar:
        ic = f'<skipped type="pytest.skip" message="{neden}">x</skipped>' if neden is not None else ""
        s.append(f'<testcase classname="{c}" name="{n}" time="0.1">{ic}</testcase>')
    s.append("</testsuite></testsuites>")
    p = tmp_path / ad
    p.write_text("".join(s), encoding="utf-8")
    return p


def _defter(tmp_path: Path, kayitlar: list[dict]) -> Path:
    p = tmp_path / "defter.json"
    p.write_text(json.dumps({"kayitlar": kayitlar}, ensure_ascii=False), encoding="utf-8")
    return p


GEREKCE = "kurucu EXE yalnız yayın makinesinde üretilir; Y30 orada koşar ve atlarsa kırmızı"
Y_KAYIT = {"test": "tests.test_a::test_exe", "sinif": "Y", "gerekce": GEREKCE}
P_KAYIT = {
    "test": "tests.test_b::test_osiloskop",
    "sinif": "P",
    "gerekce": "tezgâh osiloskobu barındırılan koşucuda yok — donanım",
}


def test_KRITIK_defterde_OLMAYAN_atlama_KIRMIZI(tmp_path, capsys):
    j = _junit(
        tmp_path, [("tests.test_a", "test_exe", "setup EXE yok"), ("tests.test_c", "test_sessiz", "bir şey yok")]
    )
    assert kapi.denetle(j, _defter(tmp_path, [Y_KAYIT])) == 1
    assert "defterde OLMAYAN atlama" in capsys.readouterr().out


def test_defterle_TAM_uyusan_kosu_YESIL(tmp_path, capsys):
    j = _junit(
        tmp_path,
        [
            ("tests.test_a", "test_exe", "setup EXE yok"),
            ("tests.test_b", "test_osiloskop", "TEZGÂH"),
            ("tests.test_c", "test_gecer", None),
        ],
    )
    assert kapi.denetle(j, _defter(tmp_path, [Y_KAYIT, P_KAYIT])) == 0
    assert "Y=1 P=1" in capsys.readouterr().out


@pytest.mark.parametrize("sinif", ["M", "D", "", "X"])
def test_KRITIK_M_D_ya_da_bilinmeyen_SINIF_deftere_GIREMEZ(tmp_path, capsys, sinif):
    j = _junit(tmp_path, [("tests.test_a", "test_exe", "setup EXE yok")])
    assert kapi.denetle(j, _defter(tmp_path, [{**Y_KAYIT, "sinif": sinif}])) == 1
    assert "sınıf" in capsys.readouterr().out


def test_KRITIK_GEREKCESIZ_kayit_KIRMIZI(tmp_path, capsys):
    j = _junit(tmp_path, [("tests.test_a", "test_exe", "setup EXE yok")])
    assert kapi.denetle(j, _defter(tmp_path, [{**Y_KAYIT, "gerekce": "yok"}])) == 1
    assert "gerekçe" in capsys.readouterr().out


@pytest.mark.parametrize(
    "neden",
    [
        "em_kedi ağırlığı yok",
        "kardeş kaynak yok: ai_hub/PEMF_AI_Test_Girdileri/07a_BobrekCT_tas.jpg",
        "gerçek ağırlık kökü yok (PEMF_AI_MODELS_DIR / ürün kökleri: release_assets/ai_models)",
        "fantom EM ağırlığı ürün çözücüsünde yok (ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx)",
    ],
)
def test_KRITIK_M_KILIKLI_Y_kaydi_kirmiziyi_SAKLAYAMAZ(tmp_path, capsys, neden):
    j = _junit(tmp_path, [("tests.test_a", "test_exe", neden)])
    assert kapi.denetle(j, _defter(tmp_path, [Y_KAYIT])) == 1
    assert "M sınıfı" in capsys.readouterr().out


def test_KRITIK_ATLAMAYAN_kayit_BAYAT_kismi_kip_yalniz_YOKLUGU_affeder(tmp_path, capsys):
    gecti = _junit(tmp_path, [("tests.test_a", "test_exe", None)])
    assert kapi.denetle(gecti, _defter(tmp_path, [Y_KAYIT])) == 1
    assert "BAYAT" in capsys.readouterr().out
    yok = _junit(tmp_path, [("tests.test_z", "test_baska", None)], ad="yok.xml")
    assert kapi.denetle(yok, _defter(tmp_path, [Y_KAYIT])) == 1
    assert kapi.denetle(yok, _defter(tmp_path, [Y_KAYIT]), kismi=True) == 0
    assert kapi.denetle(gecti, _defter(tmp_path, [Y_KAYIT]), kismi=True) == 1, "kısmi kip GEÇEN kaydı affetti"
    ortam = {**P_KAYIT, "test": "tests.test_a::test_exe", "ortamda_kosabilir": True}
    assert kapi.denetle(gecti, _defter(tmp_path, [ortam])) == 0, "ortamda koşabilen P kaydı bayat sayıldı"


def test_konsol_utf8_reconfigure_olan_akisi_cevirir_olmayani_atlar():
    class _A:
        ayar = None

        def reconfigure(self, **k):
            self.ayar = k

    a = _A()
    kapi._konsol_utf8([a, object()])
    assert a.ayar == {"encoding": "utf-8", "errors": "replace"}


def test_kor_junit_ve_main(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(kapi, "_konsol_utf8", lambda: None)
    bos = tmp_path / "bos.xml"
    bos.write_text("<testsuites/>", encoding="utf-8")
    assert kapi.denetle(bos, _defter(tmp_path, [Y_KAYIT])) == 2
    assert kapi.denetle(tmp_path / "yok.xml", _defter(tmp_path, [Y_KAYIT])) == 2
    j = _junit(tmp_path, [("tests.test_a", "test_exe", "setup EXE yok")])
    assert kapi.main([str(j), "--defter", str(_defter(tmp_path, [Y_KAYIT]))]) == 0
    assert kapi.main([str(j), "--defter", str(_defter(tmp_path, [])), "--kismi"]) == 1
    bozuk = tmp_path / "bozuk.json"
    bozuk.write_text("{", encoding="utf-8")
    assert kapi.main([str(j), "--defter", str(bozuk)]) == 2


# ---- depodaki defter + işaret ----


def _defter_kayitlari() -> list[dict]:
    return json.loads(DEFTER.read_text(encoding="utf-8"))["kayitlar"]


def test_KRITIK_depodaki_defter_GECERLI_yalniz_Y_P_gerekceli_tekil():
    k = _defter_kayitlari()
    assert k, "defter boş"
    assert {d["sinif"] for d in k} <= {"Y", "P"}
    assert all(len(d["gerekce"].strip()) >= 20 for d in k)
    assert len({d["test"] for d in k}) == len(k), "çift kayıt"


def _isaretli_mi(modul: Path, test_adi: str) -> bool:
    agac = ast.parse(modul.read_text(encoding="utf-8"))

    def _isaret(dek) -> bool:
        return "yalniz_yayin_makinesi" in ast.unparse(dek)

    for d in agac.body:
        if (
            isinstance(d, ast.Assign)
            and any(getattr(t, "id", "") == "pytestmark" for t in d.targets)
            and _isaret(d.value)
        ):
            return True
    ad = test_adi.split("[")[0]
    for d in ast.walk(agac):
        if (
            isinstance(d, (ast.FunctionDef, ast.ClassDef))
            and d.name == ad
            and any(_isaret(x) for x in d.decorator_list)
        ):
            return True
    return False


def test_KRITIK_defterdeki_HER_Y_testi_yalniz_yayin_makinesi_ISARETLI():
    eksik = []
    for d in _defter_kayitlari():
        if d["sinif"] != "Y":
            continue
        modul, _, ad = d["test"].partition("::")
        yol = KOK / (modul.replace(".", "/") + ".py")
        if not yol.is_file() or not _isaretli_mi(yol, ad or ""):
            eksik.append(d["test"])
    assert not eksik, f"Y kaydı ama işaretsiz (Y30'da atlarsa kırmızı OLMAZ): {eksik}"


# ---- Y30 kipi: eklenti + capraz ----

_AYAR = '''import sys
sys.path.insert(0, {tests!r})
import yayin_makinesi_kapisi
def pytest_configure(config):
    yayin_makinesi_kapisi.kur(config)
'''
_TESTLER = '''import pytest
import capraz
@pytest.mark.yalniz_yayin_makinesi
def test_y_duz_atlar():
    pytest.skip("setup EXE yok")
@pytest.mark.yalniz_yayin_makinesi
def test_y_capraz_atlar():
    capraz.atla("APK yok", yalniz_yayin=True)
@pytest.mark.yalniz_yayin_makinesi
@pytest.mark.skipif(True, reason="NSIS şablon dizini yok")
def test_y_skipif():
    pass
def test_isaretsiz_atlar():
    pytest.skip("platform")
'''
_MODUL = '''import pytest
import capraz
pytestmark = pytest.mark.yalniz_yayin_makinesi
capraz.atla("TR tabanı yok", yalniz_yayin=True)
def test_hic():
    pass
'''


def _kos(tmp_path: Path, ortam: dict) -> subprocess.CompletedProcess:
    (tmp_path / "conftest.py").write_text(_AYAR.format(tests=str(KOK / "tests")), encoding="utf-8")
    (tmp_path / "test_y.py").write_text(_TESTLER, encoding="utf-8")
    (tmp_path / "test_ymodul.py").write_text(_MODUL, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("PEMF_YAYIN_MAKINESI", "PEMF_CAPRAZ_KAYNAK_ZORUNLU")}
    env.update(ortam)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-rfEs",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:randomly",
            "--continue-on-collection-errors",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=300,
    )


def test_KRITIK_CI_ZORUNLU_kipinde_Y_testleri_GEREKCELI_atlar_DUSMEZ(tmp_path):
    c = _kos(tmp_path, {"PEMF_CAPRAZ_KAYNAK_ZORUNLU": "1"})
    assert c.returncode == 0, c.stdout[-3000:]
    assert re.search(r"\b5 skipped\b", c.stdout), c.stdout[-2000:]
    assert "[Y — yalnız yayın makinesi]" in c.stdout


def test_KRITIK_Y30_kipinde_Y_testi_ATLARSA_KIRMIZI_isaretsiz_atlama_ETKILENMEZ(tmp_path):
    c = _kos(tmp_path, {"PEMF_CAPRAZ_KAYNAK_ZORUNLU": "1", "PEMF_YAYIN_MAKINESI": "1"})
    assert c.returncode != 0
    o = c.stdout
    for ad in ("test_y_duz_atlar", "test_y_capraz_atlar", "test_y_skipif"):
        assert re.search(rf"(FAILED|ERROR) .*{ad}", o), (ad, o[-3000:])
    assert re.search(r"ERROR .*test_ymodul", o), o[-3000:]
    assert "Y sınıfı test ATLADI" in o
    assert not re.search(r"(FAILED|ERROR) .*test_isaretsiz_atlar", o)


def test_Y30_kipi_ZORUNLU_olmasa_da_isaretli_atlamayi_KIRMIZI_yapar(tmp_path):
    c = _kos(tmp_path, {"PEMF_YAYIN_MAKINESI": "1"})
    assert c.returncode != 0 and "Y sınıfı test ATLADI" in c.stdout
    # ZORUNLU yokken modül düzeyi atlamayı YALNIZ eklentinin toplama kancası kırmızıya çevirir (capraz düşürmez)
    assert re.search(r"ERROR .*test_ymodul", c.stdout), c.stdout[-2000:]
    assert re.search(r"FAILED .*test_y_skipif", c.stdout) or re.search(r"ERROR .*test_y_skipif", c.stdout)


# ---- iş akışı + Y30 betiği ----


def _backend_isi() -> str:
    yml = (KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    bas = yml.index("  backend:\n")
    return yml[bas : yml.index("\n  sir-taramasi:", bas)]


def test_KRITIK_CI_atlanan_kapisi_testlerden_SONRA_ve_CI_yayin_makinesi_DEGIL():
    is_ = _backend_isi()
    adim = re.search(r"- name: Atlanan defteri kapısı[^\n]*\n(?:\s{8}.*\n)+", is_)
    assert adim and "python scripts/ci_atlanan_kapisi.py pytest-junit.xml" in adim.group(0)
    assert "continue-on-error" not in adim.group(0) and "--kismi" not in adim.group(0)
    assert is_.index("- name: Kritik-yol testleri") < is_.index("- name: Atlanan defteri kapısı")
    assert "PEMF_YAYIN_MAKINESI" not in is_, "CI yayın makinesi kipinde koşarsa Y testleri kırmızı olur"


def test_KRITIK_Y30_betigi_yayin_makinesi_kipini_ve_Y_eserlerini_VERIR():
    ps = (KOK / "scripts" / "yayin_oncesi_suit.ps1").read_text(encoding="utf-8-sig")
    assert "$env:PEMF_YAYIN_MAKINESI = '1'" in ps
    assert re.search(r"PEMF_SEVK_AGACI.*PEMF_BUILD", ps, re.S) and re.search(r"PEMF_TAURI_NSIS_DIZINI.*nsis", ps, re.S)
    assert ps.index("$env:PEMF_YAYIN_MAKINESI = '1'") < ps.index("& $komut @argumanlar")
