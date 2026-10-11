# -*- coding: utf-8 -*-
"""D4.28 (B-10.93) — headless import bekçisi (`scripts/check_headless_imports.py`, build'in ilk kapısı) GUI importunun
kör biçimlerini görür; spec'in EXE'den ÇIKARDIĞI bir modülü açık import eden backend kodu derlemeyi DURDURUR.

ARIZA: bekçi yalnız modül düzeyi `import PyQt6` biçimini görüyordu. Sınıf gövdesinde, `except` / `else` dalında, `raise`
ile yeniden fırlatan bir `except`in altında, `importlib.import_module` / `__import__` ile, `qtpy` üzerinden, `tkinter`
ya da matplotlib Qt backend'i olarak gelen GUI importları ÇIKIŞ 0 (YEŞİL) veriyordu. "[X] EXE EXCLUDE RISKI" yalnız
yazdırılıyor, çıkış kodunu etkilemiyordu; listesi ({windows, pemf_gui, styles, threads}) spec'in gerçek `excludes`'undan
ayrışmıştı (spec tkinter + mpl Qt backend'lerini çıkarıyor, pemf_gui'yi ÇIKARMIYOR). Bekçinin hiçbir pytest kapısı yoktu.

Ölçüm: bekçinin GERÇEK dosyası sahte bir köke (`<kok>/scripts/`) kopyalanır → `ROOT` o kök olur; GERÇEK `main()` alt
süreçte koşar ve çıkış kodu ölçülür. Kökte GERÇEK spec'in kopyası, `apps/backend/backend_service.py` (vaka gövdesi),
`apps/backend/servers/api_server.py` ve `pemf_gui/config.py` durur. Ayrıca gerçek depo ağacı bugün YEŞİL kalmalı.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BEKCI = KOK / "scripts" / "check_headless_imports.py"
SPEC = KOK / "build_tools" / "PEMF_Backend_onedir.spec"


def _kok_kur(tmp_path: Path, govde: str, spec: bool = True) -> Path:
    kok = tmp_path / "kok"
    (kok / "scripts").mkdir(parents=True)
    shutil.copy2(BEKCI, kok / "scripts" / BEKCI.name)
    if spec:
        (kok / "build_tools").mkdir()
        shutil.copy2(SPEC, kok / "build_tools" / SPEC.name)
    be = kok / "apps" / "backend"
    (be / "servers").mkdir(parents=True)
    (be / "servers" / "__init__.py").write_text("", encoding="utf-8")
    (be / "servers" / "api_server.py").write_text("import json\n", encoding="utf-8")
    (be / "backend_service.py").write_text(textwrap.dedent(govde).lstrip("\n"), encoding="utf-8")
    (kok / "pemf_gui").mkdir()
    (kok / "pemf_gui" / "__init__.py").write_text("", encoding="utf-8")
    (kok / "pemf_gui" / "config.py").write_text("AYAR = 1\n", encoding="utf-8")
    return kok


def _kos(kok: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(kok / "scripts" / BEKCI.name)],
        cwd=str(kok),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


#: Bekçinin YEŞİL geçirdiği kör biçimler — her biri donmuş EXE'de açılışta ya da özellik yolunda ModuleNotFoundError.
KOR_BICIMLER = {
    "sinif_govdesi": """
        class Pencere:
            from PyQt6 import QtCore
        """,
    "except_dali": """
        try:
            import json
        except ImportError:
            import PyQt6.QtCore
        """,
    "try_else_dali": """
        try:
            import json
        except ImportError:
            json = None
        else:
            from PyQt6 import QtWidgets
        """,
    "yeniden_firlatan_except": """
        try:
            import PySide6
        except ImportError:
            raise
        """,
    "importlib_dinamik": """
        import importlib
        QtCore = importlib.import_module("PyQt6.QtCore")
        """,
    "dunder_import": """
        Qt = __import__("PySide6")
        """,
    "qtpy": """
        from qtpy import QtWidgets
        """,
    "tkinter_ust_duzey": """
        import tkinter
        """,
    "mpl_qt_backend_import": """
        from matplotlib.backends import backend_qtagg
        """,
    "mpl_use_qt": """
        import matplotlib as mpl
        mpl.use("QtAgg")
        """,
    "spec_disi_paket_LAZY_acik": """
        def grafik_penceresi():
            import tkinter
            return tkinter.Tk()
        """,
}


@pytest.mark.parametrize("vaka", sorted(KOR_BICIMLER))
def test_KRITIK_kor_bicimdeki_GUI_importu_bekciyi_KIRMIZI_yapar_B10_93(tmp_path, vaka):
    r = _kos(_kok_kur(tmp_path, KOR_BICIMLER[vaka]))
    assert "Headless import taramasi" in r.stdout, (
        f"bekçi taramaya başlamadı (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    )
    assert r.returncode == 1, (
        f"[{vaka}] backend_service'te GUI/spec-dışı import var ama bekçi çıkış {r.returncode} verdi "
        f"(build guard'ı YEŞİL geçer, donmuş EXE ModuleNotFoundError ile ölür):\n{r.stdout[-1500:]}"
    )


def test_KRITIK_EXE_EXCLUDE_RISKI_cikis_kodunu_etkiler_ve_spec_ten_okunur(tmp_path):
    """`IPython` GUI değil ama spec onu EXE'den çıkarıyor: açık import → özellik donmuş EXE'de ölür."""
    r = _kos(_kok_kur(tmp_path, "def kabuk():\n    import IPython\n"))
    assert r.returncode == 1 and "EXE EXCLUDE RISKI" in r.stdout, f"rc={r.returncode}\n{r.stdout[-1500:]}"


def test_KRITIK_spec_okunamazsa_bekci_YESIL_VERMEZ(tmp_path):
    """Exclude listesinin tek kaynağı spec; okunamazsa yarım-kapsamlı yeşil yerine hata (çıkış 2)."""
    r = _kos(_kok_kur(tmp_path, "import json\n", spec=False))
    assert r.returncode == 2, f"spec yokken bekçi çıkış {r.returncode} verdi:\n{r.stdout[-1200:]}"


#: Meşru biçimler — bekçi YEŞİL kalmalı (yanlış kırmızı build'i boş yere durdurur).
MESRU_BICIMLER = {
    "temiz": "import json\n",
    "korunan_qt": """
        try:
            import PyQt6
        except ImportError:
            PyQt6 = None
        """,
    "korunan_ic_ice_if": """
        try:
            if True:
                from PyQt6 import QtCore
        except Exception:
            QtCore = None
        """,
    "pemf_gui_korunan": """
        try:
            from pemf_gui import config as _cfg
        except ImportError:
            _cfg = None
        """,
    "pemf_gui_acik": "from pemf_gui import config\n",
    "mpl_agg": """
        import matplotlib
        matplotlib.use("Agg")
        """,
    "importlib_gui_disi": """
        import importlib
        j = importlib.import_module("json")
        """,
    "lazy_qt_kok_modulde": """
        def eski_pencere():
            import PyQt6
        """,
}


@pytest.mark.parametrize("vaka", sorted(MESRU_BICIMLER))
def test_KARSIT_mesru_bicimler_YESIL(tmp_path, vaka):
    r = _kos(_kok_kur(tmp_path, MESRU_BICIMLER[vaka]))
    assert r.returncode == 0, f"[{vaka}] meşru biçim KIRMIZI (yanlış alarm build'i durdurur):\n{r.stdout[-1500:]}"


def test_KARSIT_gercek_depo_agaci_bugun_YESIL():
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(BEKCI)],
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert r.returncode == 0 and "HARD BREAK YOK" in r.stdout, (
        f"rc={r.returncode}\n{r.stdout[-2000:]}\n{r.stderr[-800:]}"
    )
