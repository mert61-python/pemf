# -*- coding: utf-8 -*-
"""CT1 f-3 (istem 66 · Y311 / Y325): FARK KAPSAMI KAPISI — `scripts/fark_kapsami.py`. Geçici git deposunda: taban commit'i + değişen
dosya + sahte kapsam raporu (cobertura / lcov). Önce-KIRMIZI: testsiz yeni satır → çıkış 1 (dosya:satır yazılır); koşmuş satır → 0;
etiketli istisna (rapora girmeyen satır) sayılmaz; kısmi dal AÇIK sayılır; rapor / taban yoksa kör → 2."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("fark_kapsami_ct1f", KOK / "scripts" / "fark_kapsami.py")
fk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fk)


def _g(d: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=d, capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def depo(tmp_path):
    d = tmp_path / "depo"
    (d / "paket").mkdir(parents=True)
    _g(d, "init", "-q", "-b", "ana")
    _g(d, "config", "user.email", "t@t.invalid")
    _g(d, "config", "user.name", "t")
    _g(d, "config", "core.autocrlf", "false")
    (d / "paket" / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    (d / "notlar.md").write_text("bir\n", encoding="utf-8")
    _g(d, "add", "-A")
    _g(d, "commit", "-q", "-m", "taban")
    _g(d, "branch", "taban")
    # dal: a.py'ye 3 satır eklenir (3, 4, 5), ölçülmeyen belge değişir
    (d / "paket" / "a.py").write_text("x = 1\ny = 2\nif x:\n    z = 3\n# pragma: no cover\n", encoding="utf-8")
    (d / "notlar.md").write_text("bir\niki\n", encoding="utf-8")
    _g(d, "commit", "-qam", "degisiklik")
    return d


def _cobertura(d: Path, satirlar: dict[int, int], dal: dict[int, str] | None = None) -> Path:
    dal = dal or {}
    s = []
    for n, h in satirlar.items():
        ek = f' branch="true" condition-coverage="{dal[n]}"' if n in dal else ""
        s.append(f'<line number="{n}" hits="{h}"{ek}/>')
    x = (
        f'<?xml version="1.0" ?><coverage><sources><source>{d}</source></sources><packages><package name="p"><classes>'
        f'<class name="a.py" filename="paket/a.py"><lines>{"".join(s)}</lines></class></classes></package></packages></coverage>'
    )
    p = d.parent / "coverage.xml"
    p.write_text(x, encoding="utf-8")
    return p


def test_KRITIK_testsiz_YENI_satir_KIRMIZI_dosya_satir_yazilir(depo, capsys):
    rap = _cobertura(depo, {1: 1, 2: 1, 3: 1, 4: 0})
    assert fk.denetle("taban", [str(rap)], [], depo) == 1
    o = capsys.readouterr().out
    assert "paket/a.py: 4" in o and "açık 1" in o and "değişen ölçülen satır 2" in o


def test_kosmus_satirlar_YESIL_etiketli_ve_olculmeyen_SAYILMAZ(depo, capsys):
    rap = _cobertura(depo, {1: 1, 2: 1, 3: 1, 4: 1})  # 5 (pragma) raporda YOK → sayılmaz; notlar.md ölçülmez
    assert fk.denetle("taban", [str(rap)], [], depo) == 0
    assert "%100.00" in capsys.readouterr().out


def test_KRITIK_kismi_DAL_acik_sayilir(depo, capsys):
    rap = _cobertura(depo, {1: 1, 2: 1, 3: 1, 4: 1}, dal={3: "50% (1/2)"})
    assert fk.denetle("taban", [str(rap)], [], depo) == 1
    assert "paket/a.py: 3" in capsys.readouterr().out


def test_KRITIK_lcov_DA_ve_BRDA_ve_birden_cok_rapor_BIRLESIR(depo, capsys):
    l1 = depo.parent / "a.info"
    l1.write_text("SF:paket/a.py\nBRDA:3,0,0,1\nBRDA:3,0,1,0\nDA:3,2\nDA:4,0\nend_of_record\n", encoding="utf-8")
    assert fk.denetle("taban", [], [f"{l1}:{depo}"], depo) == 1
    assert "paket/a.py: 3–4" in capsys.readouterr().out
    l2 = depo.parent / "b.info"  # ikinci rapor 4'ü ve 3'ün öteki dalını koşturur → birleşik YEŞİL
    l2.write_text(
        f"SF:{depo / 'paket' / 'a.py'}\nDA:3,1\nDA:4,5\nend_of_record\nSF:baska.py\nDA:1,0\nend_of_record\n",
        encoding="utf-8",
    )
    assert fk.denetle("taban", [], [f"{l1}:{depo}", str(l2)], depo) == 0


def test_KRITIK_kor_kapi_taban_ya_da_rapor_YOK_cikis_2(depo, capsys, tmp_path):
    rap = _cobertura(depo, {4: 1})
    assert fk.denetle("olmayan-dal", [str(rap)], [], depo) == 2
    assert fk.denetle("taban", [str(tmp_path / "yok.xml")], [], depo) == 2
    bos = tmp_path / "bos.info"
    bos.write_text("", encoding="utf-8")
    assert fk.denetle("taban", [], [str(bos)], depo) == 2
    assert "kör" in capsys.readouterr().out


def test_taban_adaylari_sirayla_denenir(depo, monkeypatch):
    monkeypatch.setattr(fk, "TABAN_ADAYLARI", ("yok-1", "taban"))
    assert fk.birlesme_tabani(None, depo) == _g(depo, "rev-parse", "taban").strip()
    monkeypatch.setattr(fk, "TABAN_ADAYLARI", ("yok-1",))
    assert fk.birlesme_tabani(None, depo) is None


def test_silinen_dosya_ve_calisma_agaci_degisikligi(depo, capsys):
    (depo / "notlar.md").unlink()
    (depo / "paket" / "a.py").write_text(
        "x = 1\ny = 2\nif x:\n    z = 3\n# pragma: no cover\nw = 9\n", encoding="utf-8"
    )
    rap = _cobertura(depo, {3: 1, 4: 1, 6: 0})
    assert fk.denetle("taban", [str(rap)], [], depo) == 1, "commit'lenmemiş (çalışma ağacı) satır görülmedi"
    assert "paket/a.py: 6" in capsys.readouterr().out


def test_rapor_argumani_ve_araliklar():
    assert fk._rapor(r"C:\a\cov.xml:C:\kok") == (Path(r"C:\a\cov.xml"), Path(r"C:\kok"))
    assert fk._rapor("apps/ui/coverage/lcov.info:apps/ui") == (Path("apps/ui/coverage/lcov.info"), Path("apps/ui"))
    assert fk._rapor("cov.xml") == (Path("cov.xml"), fk.KOK)
    with pytest.raises(ValueError):
        fk._rapor("a.xml::b")
    assert fk._araliklar([1, 2, 3, 7, 9, 10]) == "1–3, 7, 9–10"


def test_main_ve_konsol(depo, monkeypatch, capsys):
    asil = fk._konsol_utf8
    monkeypatch.setattr(fk, "_konsol_utf8", lambda: None)
    assert fk.main([]) == 2
    monkeypatch.setattr(fk, "KOK", depo)
    monkeypatch.setattr(
        fk,
        "denetle",
        lambda t, c, l, covjson=(): 7 if (t, c, l, covjson) == ("taban", ["r.xml"], ["l.info"], ["c.json"]) else 0,
    )
    assert fk.main(["--taban", "taban", "--cobertura", "r.xml", "--lcov", "l.info", "--covjson", "c.json"]) == 7

    class _A:
        ayar = None

        def reconfigure(self, **k):
            self.ayar = k

    a = _A()
    asil([a, object()])
    assert a.ayar == {"encoding": "utf-8", "errors": "replace"}


def test_depo_disi_yol_YOK_sayilir(depo, tmp_path):
    l = tmp_path / "d.info"
    l.write_text(f"SF:{tmp_path.parent / 'baska' / 'x.py'}\nDA:1,0\nend_of_record\n", encoding="utf-8")
    assert fk.lcov_oku(l, depo, depo) == {}


def test_KRITIK_covjson_kosan_kosmayan_ve_KISMI_dal_ayni_adli_dosyalar_KARISMAZ(depo, capsys):
    # coverage.py JSON: yollar köke göre TEK anlamlı (Cobertura'da `__init__.py` gibi adlar paketler arası çakışır)
    (depo / "baska").mkdir()
    (depo / "baska" / "a.py").write_text("q = 0\n", encoding="utf-8")
    veri = {
        "files": {
            "paket/a.py": {"executed_lines": [1, 2, 3, 4], "missing_lines": [], "missing_branches": [[3, 5]]},
            "baska/a.py": {"executed_lines": [], "missing_lines": [1]},
        }
    }
    j = depo.parent / "cov.json"
    j.write_text(__import__("json").dumps(veri), encoding="utf-8")
    assert fk.denetle("taban", [], [], depo, covjson=[f"{j}:{depo}"]) == 1
    o = capsys.readouterr().out
    assert "paket/a.py: 3" in o and "baska/a.py" not in o, "kısmi dal açık sayılmadı ya da değişmeyen dosya karıştı"
    veri["files"]["paket/a.py"]["missing_branches"] = []
    j.write_text(__import__("json").dumps(veri), encoding="utf-8")
    assert fk.denetle("taban", [], [], depo, covjson=[f"{j}:{depo}"]) == 0
    assert fk.main(["--taban", "taban", "--covjson", f"{j}:{depo}"]) in (0, 2)


def test_kapsam_disi_yollar_ATLANIR_cobertura_ve_covjson(depo, tmp_path):
    # Cobertura: hiçbir kaynakta bulunmayan dosya adı · coverage JSON: depo dışındaki yol → ölçüme girmez (çökme yok)
    x = tmp_path / "c.xml"
    x.write_text(
        f'<?xml version="1.0" ?><coverage><sources><source>{depo}</source></sources><packages><package name="p"><classes>'
        '<class name="y.py" filename="yok/y.py"><lines><line number="1" hits="0"/></lines></class></classes></package>'
        "</packages></coverage>",
        encoding="utf-8",
    )
    assert fk.cobertura_oku(x, depo, depo) == {}
    j = tmp_path / "c.json"
    j.write_text(
        '{"files": {"' + (tmp_path.parent / "dis" / "z.py").as_posix() + '": {"executed_lines": [1]}}}',
        encoding="utf-8",
    )
    assert fk.covjson_oku(j, depo, depo) == {}
