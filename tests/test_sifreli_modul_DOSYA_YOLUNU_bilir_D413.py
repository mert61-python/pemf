# -*- coding: utf-8 -*-
"""D4.13 (B-3.95) — şifreli (`.pyenc`) olarak sevk edilen bir ai_hub modülü `__file__`'ı TANIMLI yüklenir.

ARIZA: `utils/encrypted_import.EncryptedFinder` spec'i `spec_from_loader(..., origin=...)` ile kuruyordu → `has_location`
False, içe aktarma düzeneği `__file__`'ı ATAMIYOR. ai_hub modüllerinin çoğu yan dosyalarını `Path(__file__).parent`
ile bulur → Cython'da düşüp `.pyenc` yedek katmanına giren bir modül import anında `NameError: __file__` ile ölür:
build'in AI hazırlık kapısı KIRMIZI yanar (envanterdeki modül), envanter dışı lazy import edilen bir yardımcı ise sahaya
kaçar. Bugün sevk ağacında 0 `.pyenc` → tetik yok; katman `build_backend_exe.ps1`'de .pyd derlenemeyince devreye girer.

Ölçüm: GERÇEK `build_tools/encrypt_sources.py` (alt süreç, test parolası `PEMF_SOURCE_KEY`) sentetik bir
`dist/PEMF_Backend/_internal/ai_hub` ağacını şifreler (düz `.py` silinir, `__init__.py` düz kalır); ardından TEMİZ bir alt
süreçte GERÇEK `utils.encrypted_import.install()` (üretimdeki gibi `sys.meta_path` SONUNA) kurulur ve modül içe aktarılır.
Modül, modül düzeyinde `Path(__file__)` ile yan veri dosyasını okur ve göreli import yapar.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SIFRELEYICI = KOK / "build_tools" / "encrypt_sources.py"
BACKEND = KOK / "apps" / "backend"
PAROLA = "d413-test-parolasi"

_YOL_MODULU = """
from pathlib import Path

from . import yardimci

KOK = Path(__file__).resolve().parent
VERI = (KOK / "esik_degerleri.txt").read_text(encoding="utf-8").strip()
YARDIMCI = yardimci.AD
"""

_ICE_AKTAR = """
import json, sys
internal, backend, cikti = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path[:0] = [internal, backend]
from utils import encrypted_import as ei
kurulu = ei.install()
sonuc = {"kurulu": kurulu}
try:
    import ai_hub.yol_paketi.yol_modulu as m
    sonuc.update(file=m.__file__, kok=str(m.KOK), veri=m.VERI, yardimci=m.YARDIMCI,
                 has_location=m.__spec__.has_location, origin=m.__spec__.origin,
                 yardimci_file=getattr(sys.modules["ai_hub.yol_paketi.yardimci"], "__file__", None))
except Exception as e:
    sonuc["hata"] = f"{type(e).__name__}: {e}"
json.dump(sonuc, open(cikti, "w", encoding="utf-8"), ensure_ascii=False)
"""


def _sifreli_dist(tmp_path: Path) -> Path:
    paket = tmp_path / "dist" / "PEMF_Backend" / "_internal" / "ai_hub" / "yol_paketi"
    paket.mkdir(parents=True)
    (paket.parent / "__init__.py").write_text("", encoding="utf-8")
    (paket / "__init__.py").write_text("", encoding="utf-8")
    (paket / "yol_modulu.py").write_text(textwrap.dedent(_YOL_MODULU).lstrip(), encoding="utf-8")
    (paket / "yardimci.py").write_text("AD = 'yardimci-sifreli'\n", encoding="utf-8")
    (paket / "esik_degerleri.txt").write_text("0.42\n", encoding="utf-8")
    ortam = {**os.environ, "PEMF_SOURCE_KEY": PAROLA, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(
        [sys.executable, str(SIFRELEYICI), "--dist", str(tmp_path / "dist" / "PEMF_Backend"), "--verify"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ortam,
        timeout=300,
    )
    assert r.returncode == 0, f"encrypt_sources düştü:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}"
    assert sorted(p.name for p in paket.iterdir()) == [
        "__init__.py",
        "esik_degerleri.txt",
        "yardimci.pyenc",
        "yol_modulu.pyenc",
    ], f"şifreleme beklenen ağacı üretmedi: {sorted(p.name for p in paket.iterdir())}"
    return paket


def _ice_aktar(tmp_path: Path, paket: Path) -> dict:
    surucu, cikti = tmp_path / "ice_aktar.py", tmp_path / "sonuc.json"
    surucu.write_text(_ICE_AKTAR, encoding="utf-8")
    ortam = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PEMF_SOURCE_KEY")}
    ortam["PEMF_SOURCE_KEY"] = PAROLA
    r = subprocess.run(
        [sys.executable, "-B", str(surucu), str(paket.parents[1]), str(BACKEND), str(cikti)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ortam,
        timeout=300,
    )
    assert cikti.exists(), f"içe aktarma sürücüsü sonuç yazmadı (rc={r.returncode}):\n{r.stderr[-1500:]}"
    return json.loads(cikti.read_text(encoding="utf-8"))


def test_KRITIK_sifreli_modul___file___ile_YAN_DOSYASINI_bulur_B3_95(tmp_path):
    paket = _sifreli_dist(tmp_path)
    s = _ice_aktar(tmp_path, paket)
    assert s.get("kurulu") is True, f"şifreli yükleyici kurulmadı: {s}"
    assert "hata" not in s, (
        f"Path(__file__) kullanan şifreli modül import'ta öldü ({s.get('hata')}) — Cython'da düşüp .pyenc katmanına giren "
        "bir ai_hub modülü sahada/AI kapısında ölü doğar"
    )
    assert s["veri"] == "0.42" and s["yardimci"] == "yardimci-sifreli", s


def test_KRITIK___file___diskteki_pyenc_dosyasini_gosterir(tmp_path):
    paket = _sifreli_dist(tmp_path)
    s = _ice_aktar(tmp_path, paket)
    assert "hata" not in s, s.get("hata")
    dosya = Path(s["file"])
    assert dosya.suffix == ".pyenc" and dosya.is_file(), f"__file__ diskte var olan .pyenc'i göstermiyor: {s['file']!r}"
    assert dosya.resolve() == (paket / "yol_modulu.pyenc").resolve()
    assert Path(s["kok"]) == paket.resolve()
    assert s["has_location"] is True and s["origin"] == s["file"], s
    assert s["yardimci_file"] and Path(s["yardimci_file"]).name == "yardimci.pyenc", s
