# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KD madde 0 (istem 44 · sahip bildirimi 2026-11-10) — kabin kamerası AÇILIŞI: MSMF donanım dönüşümleri giriş noktasında, cv2'den ÖNCE kapalı.

SAHİP BİLDİRİMİ: "Kameraları tara" LattePanda'da ve bu makinede "İşlem zaman aşımına uğradı … model yüklemesi"; Canlı Kamera / Fotoğraf
Çek 30–40 sn. ÖLÇÜLDÜ (KD, bu makine, OpenCV 4.11 = paketteki, MSMF, dahili HP kamera, soğuk süreç): taban kodla tarama 25,1 sn
(istemcinin 8 sn'si), Fotoğraf Çek 23,6 sn, Canlı Kamera ilk kare 23,1 sn; `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0` İLE açılış
0,27 sn + istek ~0 sn. Değişken cv2 İÇE AKTARILDIKTAN SONRA kurulursa ETKİSİZ (ölçüldü: açılış 7,8 sn + istek 23,9 sn) → yalnız
giriş noktasında, her üçüncü taraf içe aktarmadan önce. Ürünün TEK giriş noktası `apps/backend/backend_service.py` (PyInstaller
`Analysis` girdisi; `api_server` alt-girişi P2'de kaldırıldı).

KAPI: (1) yapısal — giriş dosyasında `setdefault` deyiminden ÖNCE yalnız stdlib içe aktarması var; (2) davranışsal — ÇOCUK süreç
gerçek giriş modülünü içe aktarır, `cv2` içe aktarıldığı ANDA değişkenin değeri kaydedilir ("0" olmalı); kullanıcının / kurulumun AÇIK
değeri (ör. "1") EZİLMEZ.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
GIRIS = KOK / "apps" / "backend" / "backend_service.py"
DEGISKEN = "OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"
#: Değişkenden önce izin verilen içe aktarmalar (stdlib — hiçbiri cv2 / numpy yüklemez). Kapı sabiti test İÇİNDE (mutant kaynaktan okunmaz).
_ONCE_IZINLI = {"__future__", "argparse", "logging", "logging.handlers", "os", "signal", "sys", "threading", "pathlib"}


def _setdefault_mi(d: ast.stmt) -> bool:
    if not (isinstance(d, ast.Expr) and isinstance(d.value, ast.Call)):
        return False
    f = d.value.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr == "setdefault"
        and ast.unparse(f.value) == "os.environ"
        and [ast.literal_eval(a) for a in d.value.args] == [DEGISKEN, "0"]
    )


def test_KRITIK_giris_noktasi_degiskeni_HER_ucuncu_taraf_ice_aktarmadan_ONCE_setdefault_ile_kurar():
    govde = ast.parse(GIRIS.read_text(encoding="utf-8")).body
    for d in govde:
        if _setdefault_mi(d):
            break
        if isinstance(d, ast.Import):
            adlar = [a.name for a in d.names]
        elif isinstance(d, ast.ImportFrom):
            adlar = [d.module or ""]
        elif isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant):
            continue  # modül açıklaması
        else:
            pytest.fail(f"değişkenden ÖNCE başka deyim koşuyor: {ast.unparse(d)[:160]}")
        disarida = [a for a in adlar if a not in _ONCE_IZINLI]
        assert not disarida, f"değişken kurulmadan ÖNCE stdlib DIŞI içe aktarma (cv2'yi yükleyebilir): {disarida}"
    else:
        pytest.fail(f"giriş noktasında `os.environ.setdefault({DEGISKEN!r}, '0')` YOK")


_COCUK = r'''
import importlib.abc, json, os, sys
KOK, CIKTI, DEGISKEN = sys.argv[1], sys.argv[2], sys.argv[3]
kayit = {}


class _Izle(importlib.abc.MetaPathFinder):
    """cv2 içe aktarıldığı ANDA değişkenin değeri (kim içe aktarırsa aktarsın)."""

    def find_spec(self, ad, yol=None, hedef=None):
        if ad == "cv2" and "an" not in kayit:
            kayit["an"] = os.environ.get(DEGISKEN)
        return None


sys.meta_path.insert(0, _Izle())
sys.path[:0] = [os.path.join(KOK, "apps", "backend"), KOK]
import backend_service  # noqa: F401  GERÇEK giriş noktası
import cv2  # noqa: F401  giriş noktası cv2'yi henüz yüklemediyse ilk içe aktarma burada — değer yine kaydedilir

json.dump({"cv2_aninda": kayit.get("an"), "cv2_onceden_yuklu": "an" not in kayit}, open(CIKTI, "w"))
'''


def _cocuk(tmp_path: Path, deger: str | None) -> dict:
    betik, cikti = tmp_path / "kd_m0_cocuk.py", tmp_path / "kd_m0.json"
    betik.write_text(_COCUK, encoding="utf-8")
    ortam = {k: v for k, v in os.environ.items() if k not in (DEGISKEN, "PYTEST_CURRENT_TEST")}
    if deger is not None:
        ortam[DEGISKEN] = deger
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(betik), str(KOK), str(cikti), DEGISKEN],
        env=ortam,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        cwd=str(tmp_path),
    )
    assert r.returncode == 0 and cikti.exists(), (
        f"çocuk süreç düştü (rc={r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-3000:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8"))


def test_KRITIK_giris_modulu_icinde_cv2_yuklendigi_AN_degisken_0(tmp_path):
    s = _cocuk(tmp_path, None)
    assert s["cv2_onceden_yuklu"] is False, f"cv2 izleyiciden ÖNCE yüklenmiş — kapı KÖR: {s}"
    assert s["cv2_aninda"] == "0", f"cv2 içe aktarıldığında {DEGISKEN} kurulu değil (kamera açılışı 8–25 sn): {s}"


def test_KARSIT_kullanicinin_ACIK_degeri_EZILMEZ(tmp_path):
    s = _cocuk(tmp_path, "1")
    assert s["cv2_aninda"] == "1", f"kullanıcının / kurulumun açık değeri ezildi: {s}"
