# -*- coding: utf-8 -*-
"""YS1j → YS1l (GitHub windows-latest): `scripts/ci_temp_acl.py` ACL benzetimlerinin ("başka hesabın kilidi") ÖLÇÜLEBİLDİĞİ bir TEMP
sağlar. YS1l tanısı (uç 21b5be65): koşucunun profil TEMP'inde `icacls /inheritance:r` kalıtımlı ACE'leri SİLMİYOR (açık ACE'ye
çeviriyor) → kilitten sonra süreç hesabı erişimini korur; 19 kırmızı + 3 hata. YS1j'nin ACE-bayrağı sondası bunu göremedi
(`GetNamedSecurityInfoW` `ID`'yi ebeveynle karşılaştırıp HESAPLAR) — ölçüm artık İŞLEVSEL.

KAPI: (1) GERÇEK: olağanlaştırma dizini KORUMALI + yalnız üç kalıtımlı `(OI)(CI)F` ACE bırakır, ardından sonda kilidi ÖLÇER;
(2) GERÇEK: ölçülebilen dizine DOKUNULMAZ (DACL aynı, sonda artığı yok); (3) sonda kilitten sonra FAZLADAN ACE kalırsa "ölçülmez" der;
(4) akış: yerinde düzelir → 0 · düzelmez (`--dizin`) → 1 · icacls düşer → 1 · CI'da YEDEK (`$RUNNER_TEMP/pemf-tmp`) ölçülürse
`TEMP` / `TMP` `$GITHUB_ENV`'e yazılır → 0 · yedek de ölçülmezse / RUNNER_TEMP yoksa → 1 (ortam dosyasına YAZILMAZ); (5) yol
verilmezse YALNIZ `GITHUB_ACTIONS=true` iken TEMP; (6) CI'da pytest'ten ÖNCE, Windows'ta, hata yutulmadan koşar.
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


def _sifirla(d: Path) -> None:
    subprocess.run(["icacls", str(d), "/reset", "/T", "/C", "/Q"], capture_output=True, timeout=60)


def test_KRITIK_olaganlastirma_KORUMALI_uc_kalitimli_ACE_sonra_kilit_OLCULUR_YS1l(mod, tmp_path):
    from acl_sddl import sid_metni

    d = tmp_path / "olagan"
    d.mkdir()
    sid = mod.surec_sid()
    try:
        r = mod.olaganlastir(str(d), sid)
        assert r.returncode == 0, r.stdout + r.stderr
        s = mod.sddl(str(d))
        assert s.startswith("D:P"), f"olağanlaştırılan dizin KORUMALI değil (eski tip ebeveyne bağlı kalır): {s}"
        aceler = mod.aceler(s)
        assert len(aceler) == 3 and all(a.startswith("A;OICI;FA;;;") for a in aceler), aceler
        assert {sid_metni(a.rsplit(";", 1)[1]) for a in aceler} == {"S-1-5-18", "S-1-5-32-544", sid}, aceler
        olculur, kilitli = mod.sonda(str(d))
        assert olculur and mod.aceler(kilitli) == [mod.KILIT_ACE], kilitli
        assert not list(d.iterdir()), "sonda artığı kaldı"
    finally:
        _sifirla(d)


@pytest.fixture()
def mirassiz(tmp_path, mod):
    """Alt öğelerine HİÇ kalıtımlı ACE vermeyen dizin: orada doğan dosya belirtecin varsayılan DACL'ini AÇIK ACE olarak alır → kilit
    sonrası açık ACE'ler kalır (yerelde ölçüldü). `finally`: /reset."""
    d = tmp_path / "mirassiz"
    d.mkdir()
    r = subprocess.run(
        ["icacls", str(d), "/inheritance:r", "/grant:r", "*S-1-5-18:F", "/grant:r", "*S-1-5-32-544:F"]
        + ["/grant:r", f"*{mod.surec_sid()}:F"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, f"aparat: miras vermeyen dizin kurulamadı: {r.stdout}{r.stderr}"
    try:
        yield d
    finally:
        _sifirla(d)


def test_KRITIK_miras_vermeyen_dizin_GERCEK_olaganlastirilir_SONDA_ARTIGI_birakmaz(mod, mirassiz, capsys):
    assert mod.main(["--dizin", str(mirassiz)]) == 0, capsys.readouterr()
    assert mod.sonda(str(mirassiz))[0], "olağanlaştırma sonrası kilit ölçülmüyor"
    assert not list(mirassiz.iterdir()), f"sonda artığı kaldı: {list(mirassiz.iterdir())}"


def test_sonda_silinemezse_SAHIP_olarak_erisim_verip_yeniden_siler(mod, tmp_path, monkeypatch):
    d = tmp_path / "s"
    d.mkdir()
    asil = mod.shutil.rmtree
    cagri = []

    def ilk_kez_birak(yol, ignore_errors=False):
        cagri.append(yol)
        if len(cagri) > 1:
            asil(yol, ignore_errors=ignore_errors)

    monkeypatch.setattr(mod.shutil, "rmtree", ilk_kez_birak)
    mod.sonda(str(d))
    assert len(cagri) == 2 and not list(d.iterdir()), cagri


def test_KARSIT_olculebilen_dizine_DOKUNULMAZ_sonda_artigi_YOK_YS1j(mod, tmp_path, capsys):
    d = tmp_path / "olagan"
    d.mkdir()
    once = mod.sddl(str(d))
    assert mod.main(["--dizin", str(d)]) == 0
    assert "dokunulmadı" in capsys.readouterr().out
    assert mod.sddl(str(d)) == once, "ölçülebilen dizinin DACL'i değişti"
    assert not list(d.iterdir()), "sonda artığı kaldı"


def test_KRITIK_kilitten_sonra_FAZLADAN_ACE_kalirsa_OLCULMEZ_der_YS1l(mod, tmp_path, monkeypatch):
    """CI belirtisi: `/inheritance:r` kalıtımlı ACE'leri açığa çevirdi → kilitte süreç hesabı kaldı."""
    d = tmp_path / "s"
    d.mkdir()
    monkeypatch.setattr(mod, "sddl", lambda yol: "D:PAI(A;;FA;;;LS)(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;LA)")
    olculur, s = mod.sonda(str(d))
    assert not olculur, s
    monkeypatch.setattr(mod, "sddl", lambda yol: "D:PAI(A;;FA;;;LS)")
    assert mod.sonda(str(d))[0]
    assert not list(d.iterdir()), "sonda artığı kaldı"


class _Sahne:
    """`sonda` sonuçlarını sırayla verir; `olaganlastir` çağrılarını kaydeder (gerçek ACL'e dokunmadan akış ölçümü)."""

    def __init__(self, mod, monkeypatch, sonuclar, icacls_rc=0):
        self.sondalar, self.olaganlar = [], []
        sonuclar = list(sonuclar)

        def sonda(dizin):
            self.sondalar.append(dizin)
            return sonuclar.pop(0), "D:PAI(A;;FA;;;LS)"

        def olaganlastir(dizin, sid):
            self.olaganlar.append(dizin)
            return subprocess.CompletedProcess([], icacls_rc, "", "Access is denied." if icacls_rc else "")

        monkeypatch.setattr(mod, "sonda", sonda)
        monkeypatch.setattr(mod, "olaganlastir", olaganlastir)
        monkeypatch.setattr(mod, "sddl", lambda d: "D:")
        monkeypatch.setattr(mod, "surec_sid", lambda: "S-1-5-21-1-2-3-500")


def test_KRITIK_olculmeyen_dizin_YERINDE_olaganlastirilir_ve_yeniden_olculur(mod, tmp_path, monkeypatch, capsys):
    s = _Sahne(mod, monkeypatch, [False, True])
    assert mod.main(["--dizin", str(tmp_path)]) == 0
    assert s.olaganlar == [str(tmp_path)] and s.sondalar == [str(tmp_path)] * 2
    assert "olağan profil biçimine getirildi" in capsys.readouterr().out


def test_KRITIK_olaganlastirma_ISE_YARAMAZSA_cikis_1_suit_bosuna_kosmaz_YS1j(mod, tmp_path, monkeypatch, capsys):
    ortam = tmp_path / "github_env"
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_ENV", str(ortam))
    _Sahne(mod, monkeypatch, [False, False, True])  # 3. sonuç: yedeğe geçilseydi ölçülürdü → yanlış kol 0 döner
    assert mod.main(["--dizin", str(tmp_path)]) == 1
    assert "ölçülemez" in capsys.readouterr().err
    assert not ortam.exists(), "--dizin kipinde yedeğe geçildi"


def test_icacls_dusunce_cikis_1(mod, tmp_path, monkeypatch, capsys):
    _Sahne(mod, monkeypatch, [False], icacls_rc=5)
    assert mod.main(["--dizin", str(tmp_path)]) == 1
    assert "icacls rc=5" in capsys.readouterr().err


def test_KRITIK_CIde_TEMP_duzelmezse_YEDEK_TEMP_olculur_ve_GITHUB_ENVe_yazilir_YS1l(mod, tmp_path, monkeypatch, capsys):
    temp, rt, ortam = tmp_path / "temp", tmp_path / "rt", tmp_path / "github_env"
    temp.mkdir()
    rt.mkdir()
    ortam.write_text("ONCEKI=1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(rt))
    monkeypatch.setenv("GITHUB_ENV", str(ortam))
    monkeypatch.setattr(mod.tempfile, "gettempdir", lambda: str(temp))
    s = _Sahne(mod, monkeypatch, [False, False, False, True])
    assert mod.main([]) == 0, capsys.readouterr()
    yedek = str(rt / "pemf-tmp")
    assert Path(yedek).is_dir() and s.olaganlar == [str(temp), yedek], s.olaganlar
    assert ortam.read_text(encoding="utf-8") == f"ONCEKI=1\nTEMP={yedek}\nTMP={yedek}\n"
    assert "YEDEK" in capsys.readouterr().out


@pytest.mark.parametrize("eksik", ["yedek_olculmez", "RUNNER_TEMP", "GITHUB_ENV"])
def test_KRITIK_CIde_yedek_de_olmazsa_cikis_1_ortam_dosyasina_YAZILMAZ_YS1l(mod, tmp_path, monkeypatch, capsys, eksik):
    temp, rt, ortam = tmp_path / "temp", tmp_path / "rt", tmp_path / "github_env"
    temp.mkdir()
    rt.mkdir()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(rt))
    monkeypatch.setenv("GITHUB_ENV", str(ortam))
    if eksik != "yedek_olculmez":
        monkeypatch.delenv(eksik)
    monkeypatch.setattr(mod.tempfile, "gettempdir", lambda: str(temp))
    _Sahne(mod, monkeypatch, [False, False, False, False])
    assert mod.main([]) == 1
    assert "HATA" in capsys.readouterr().err
    assert not ortam.exists(), "başarısız yedek ortam dosyasına yazıldı"


def test_KRITIK_yol_verilmezse_YALNIZ_CIde_TEMP_hedeflenir_YS1j(mod, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert mod.main([]) == 2 and "kullanım" in capsys.readouterr().err
    assert mod.main(["--dizin"]) == 2
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(mod.tempfile, "gettempdir", lambda: "C:\\sahte\\temp")
    s = _Sahne(mod, monkeypatch, [True])
    assert mod.main([]) == 0 and s.sondalar == ["C:\\sahte\\temp"] and not s.olaganlar


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
