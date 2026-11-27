# -*- coding: utf-8 -*-
"""YS1j (GitHub windows-latest 4c3c10ee): koşucunun TEMP'i alt öğelerine ACE MİRAS VERMİYOR → orada doğan dosya belirtecin varsayılan
DACL'ini AÇIK ACE olarak alır; "başka hesabın kilidi" benzetimi (`/inheritance:r /grant:r *S-1-5-19:(F)`) kullanıcının açık ACE'ini
kaldırmaz, dosya OKUNUR (22 kırmızı + 3 hata). `scripts/ci_temp_acl.py` TEMP'i olağan profil biçimine getirir.

KAPI: (1) miras vermeyen dizinde benzetim KÖR (aparat kanıtı) → olağanlaştırma sonrası yeni dosyada GERÇEK ret; (2) miras veren dizine
DOKUNULMAZ (DACL aynı, sonda artığı yok); (3) olağanlaştırma işe yaramazsa / icacls düşerse ÇIKIŞ 1; (4) yol verilmezse YALNIZ
`GITHUB_ACTIONS=true` iken TEMP hedeflenir (geliştiricinin TEMP'ine dokunulmaz); (5) CI'da pytest'ten ÖNCE koşar.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "ci_temp_acl.py"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="NTFS ACL (icacls) yalnız Windows")


@pytest.fixture()
def mod():
    spec = importlib.util.spec_from_file_location("ci_temp_acl_ys1j", BETIK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _icacls(*arg) -> subprocess.CompletedProcess:
    return subprocess.run(["icacls", *[str(a) for a in arg]], capture_output=True, text=True, timeout=60)


def _okunur_mu(p: Path) -> bool:
    try:
        p.read_bytes()
        return True
    except PermissionError:
        return False


@pytest.fixture()
def mirassiz(tmp_path, mod):
    """GitHub koşucusu TEMP'i gibi: açık ACE'ler var, hiçbiri alt öğelere miras GEÇMEZ. `finally`: /reset (artık bırakmaz)."""
    d = tmp_path / "mirassiz"
    d.mkdir()
    sid = mod.surec_sid()
    r = _icacls(d, "/inheritance:r", "/grant:r", "*S-1-5-18:F", "/grant:r", "*S-1-5-32-544:F", "/grant:r", f"*{sid}:F")
    assert r.returncode == 0, f"aparat: miras vermeyen dizin kurulamadı: {r.stdout}{r.stderr}"
    try:
        yield d
    finally:
        _icacls(d, "/reset", "/T", "/C")


def _baska_hesap_kilidi(f: Path) -> None:
    r = _icacls(f, "/inheritance:r", "/grant:r", "*S-1-5-19:(F)")
    assert r.returncode == 0, f"aparat: kilit kurulamadı: {r.stdout}{r.stderr}"


def test_KRITIK_mirassiz_TEMPte_benzetim_KOR_olaganlastirma_sonrasi_GERCEK_ret_YS1j(mod, mirassiz, capsys):
    once = mirassiz / "once.txt"
    once.write_text("x", encoding="utf-8")
    _baska_hesap_kilidi(once)
    assert _okunur_mu(once), "aparat: CI belirtisi kurulamadı (miras vermeyen dizinde kilit dosyayı zaten kapattı)"
    assert mod.main(["--dizin", str(mirassiz)]) == 0, capsys.readouterr()
    assert "olağan profil biçimine getirildi" in capsys.readouterr().out
    alt = mirassiz / "pytest-of-x" / "t0"
    alt.mkdir(parents=True)
    f = alt / "pemf_secrets.json"
    f.write_text("{}", encoding="utf-8")
    _baska_hesap_kilidi(f)
    assert not _okunur_mu(f), (
        "olağanlaştırma sonrası 'başka hesabın kilidi' yeni dosyayı yine KAPATMIYOR (açık ACE kaldı)"
    )


def test_KARSIT_miras_veren_dizine_DOKUNULMAZ_sonda_artigi_YOK_YS1j(mod, tmp_path, capsys):
    d = tmp_path / "olagan"
    d.mkdir()
    once = mod.sddl(str(d))
    assert mod.main(["--dizin", str(d)]) == 0
    assert "dokunulmadı" in capsys.readouterr().out
    assert mod.sddl(str(d)) == once, "miras veren dizinin DACL'i değişti"
    assert not list(d.iterdir()), "sonda artığı kaldı"


def test_KRITIK_olaganlastirma_ISE_YARAMAZSA_cikis_1_suit_bosuna_kosmaz_YS1j(mod, mirassiz, monkeypatch, capsys):
    monkeypatch.setattr(mod, "olaganlastir", lambda dizin, sid: subprocess.CompletedProcess([], 0, "", ""))
    assert mod.main(["--dizin", str(mirassiz)]) == 1
    assert "ölçülemez" in capsys.readouterr().err


def test_icacls_dusunce_cikis_1(mod, mirassiz, monkeypatch, capsys):
    monkeypatch.setattr(
        mod, "olaganlastir", lambda dizin, sid: subprocess.CompletedProcess([], 5, "", "Access is denied.")
    )
    assert mod.main(["--dizin", str(mirassiz)]) == 1
    assert "icacls rc=5" in capsys.readouterr().err


def test_KRITIK_yol_verilmezse_YALNIZ_CIde_TEMP_hedeflenir_YS1j(mod, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert mod.main([]) == 2 and "kullanım" in capsys.readouterr().err
    assert mod.main(["--dizin"]) == 2
    hedef = []
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(mod.tempfile, "gettempdir", lambda: "C:\\sahte\\temp")
    monkeypatch.setattr(mod, "sonda", lambda d: hedef.append(d) or (True, "D:(A;ID;FA;;;SY)"))
    monkeypatch.setattr(mod, "sddl", lambda d: "D:")
    assert mod.main([]) == 0 and hedef == ["C:\\sahte\\temp"]


def test_acik_ace_ayristirma(mod):
    assert mod.acik_aceler("D:PAI(A;OICIID;FA;;;SY)(A;;FA;;;LA)(A;OICI;FA;;;BA)") == ["A;;FA;;;LA", "A;OICI;FA;;;BA"]
    assert mod.acik_aceler("D:AI(A;ID;FA;;;SY)(A;OICIIOID;FA;;;CO)") == []
    assert mod.aceler("O:BAG:SY") == []


def test_surec_sid_okunamazsa_HATA(mod, monkeypatch):
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "hata"))
    with pytest.raises(RuntimeError, match="SID"):
        mod.surec_sid()


def test_komut_satiri_cp1252_konsolda_DUSMEZ(tmp_path):
    d = tmp_path / "k"
    d.mkdir()
    r = subprocess.run(
        [sys.executable, str(BETIK), "--dizin", str(d)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert r.returncode == 0 and "dokunulmadı" in r.stdout, (r.stdout, r.stderr)


def test_KRITIK_CI_TEMP_olaganlastirma_PYTESTTEN_ONCE_kosar_YS1j():
    is_ = yaml.safe_load((KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))["jobs"]["backend"]
    adimlar = [str(a.get("run", "")) for a in is_["steps"]]
    acl = [i for i, r in enumerate(adimlar) if r.strip().startswith("python scripts/ci_temp_acl.py")]
    pt = [i for i, r in enumerate(adimlar) if "pytest tests" in r]
    assert len(acl) == 1 and len(pt) == 1 and acl[0] < pt[0], (acl, pt)
    adim = is_["steps"][acl[0]]
    assert adim.get("if") == "runner.os == 'Windows'" and not adim.get("continue-on-error"), adim
