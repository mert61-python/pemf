# -*- coding: utf-8 -*-
"""4B-1.3 — headless bekçisi (build'in ilk kapısı) startup kapanışındaki SÖZDİZİMİ HATALI birinci-taraf modülü SESSİZCE boş
sayıyordu (`analyze` → `except SyntaxError: return _empty()`), çıkış 0 (YEŞİL). 4-B bunu "PyInstaller derlemesi zaten düşer"
diye bilinçli bıraktı — ÖLÇÜLDÜ YANLIŞ: PyInstaller 6.20 yalnız Analysis kuru koşumunda iki sözdizimi hatalı modülü (biri
top-level, biri delayed import) `a.pure`'dan SESSİZCE düşürdü, yalnız `warn-*.txt`'e "invalid module named …" yazdı ve
derleme sürdü (sonda `_inceleme/sonda/k1_pyi_analiz.py`). Build betiği warn dosyasını okumuyor → modül EXE'de YOK; lazy import
edilen özellik sahada ModuleNotFoundError ile ölür. Bekçinin KENDİ ilkesi (çözülemeyen kök → çıkış 2): "yarım kapsamlı yeşil,
kırmızıdan tehlikelidir".

Ölçüm: bekçinin GERÇEK dosyası sahte köke (D4.28 testinin `_kok_kur`'u), GERÇEK `main()` alt süreçte."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_YOL = Path(__file__).with_name("test_headless_bekcisi_KOR_BICIMLERI_gorur_D428.py")
_spec = importlib.util.spec_from_file_location("zz_d428_bekci_4b13", _YOL)
d428 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d428)

_BOZUK = "import json\ndef f(:\n    pass\n"


def _kur(tmp_path: Path, govde: str, bozuk_ad: str) -> Path:
    kok = d428._kok_kur(tmp_path, govde)
    (kok / "apps" / "backend" / "servers" / f"{bozuk_ad}.py").write_text(_BOZUK, encoding="utf-8")
    return kok


def test_KRITIK_startupta_EAGER_import_edilen_modul_ayristirilamazsa_bekci_DURUR(tmp_path):
    r = d428._kos(_kur(tmp_path, "from servers import bozuk_eager\n", "bozuk_eager"))
    assert r.returncode != 0, (
        "startup kapanışındaki modül AYRIŞTIRILAMIYOR ama bekçi YEŞİL (çıkış 0) — PyInstaller onu pakete almadan sürer:\n"
        + r.stdout[-1200:]
    )
    assert "bozuk_eager" in r.stdout, "ileti ayrıştırılamayan modülü adıyla söylemiyor"


def test_KRITIK_LAZY_import_edilen_modul_ayristirilamazsa_bekci_DURUR(tmp_path):
    govde = "def ozellik():\n    from servers import bozuk_lazy\n    return bozuk_lazy\n"
    r = d428._kos(_kur(tmp_path, govde, "bozuk_lazy"))
    assert r.returncode != 0, f"lazy yoldaki ayrıştırılamayan modül sessizce boş sayıldı:\n{r.stdout[-1200:]}"


def test_KARSIT_ulasilmayan_ayristirilamaz_dosya_bekciyi_DURDURMAZ(tmp_path):
    r = d428._kos(_kur(tmp_path, "import json\n", "kimse_import_etmiyor"))
    assert r.returncode == 0, f"startup'tan ulaşılmayan dosya bekçiyi düşürdü:\n{r.stdout[-1200:]}"
