# -*- coding: utf-8 -*-
"""D4.02 · B-10.6 · B-10.7 — kapsam ölçümünün `source` kümesi ürün kodunun TAMAMINI kapsar.

🔴 ÖLÇÜLEN DURUM (2026-10-10, 4-A): `[tool.coverage.run] source = ["servers", "database", "controllers", "utils"]` idi.
F4 taşımasıyla (2026-09-18) `apps/backend/` altına giren `services/` paketi (Mosquitto / ağ durumu / UDP keşif
süpervizörleri, cihaz kimlik bilgileri, DB bakımı) ve üst düzey `backend_service` (açılış FİRMWARE zinciri, ACİL DURDUR
açılış yolu), `headless_core` (STM telemetri ayrıştırıcı) ve `event_bus` modülleri ÖLÇÜLMÜYORDU: bu yüzeylerde kapsam
düşse de ratchet kıpırdamıyordu. Ayrıca eşik, ölçülen değerin 17–21 puan altındaydı (büyük gerilemeyi sessizce geçirir).

KAPI: `source` = (pyproject `[tool.setuptools.package-dir]`'de `apps/backend/` altına eşlenen ürün paketleri) ∪
(`apps/backend/` altındaki İZLENEN üst düzey `.py` modülleri) — TAM eşitlik: eksik ad = ölçülmeyen ürün kodu; fazla ad =
var olmayan kaynak (coverage yalnız "never imported" UYARISI verir, düşmez). Küme kaynaktan TÜRETİLİR, elle yazılmaz.

⚠️ Kapsam sınırı (4-A inc. S-A2.3): "ürün kodu" burada `apps/backend` ağacıdır. `ai_service/` ayrı süreçtir (bilinçli dışarıda);
depo kökündeki `ai/` ve `pemf_gui/` backend sürecinde içe aktarılır ama bu kapının türettiği kümede DEĞİL — açık karar S-4A.3.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

try:  # tomllib yalnız 3.11+; depo 3.10'a kilitli (bkz. test_paket_sinirlari)
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover
    import tomli as _toml

KOK = Path(__file__).resolve().parents[1]
BACKEND = "apps/backend"


def _pyproject() -> dict:
    return _toml.loads((KOK / "pyproject.toml").read_text(encoding="utf-8"))


def urun_kumesi(t: dict) -> set[str]:
    """Ürün paketleri (package-dir → apps/backend/…) ∪ apps/backend üst düzey izlenen modüller."""
    paket_dizini = t["tool"]["setuptools"]["package-dir"]
    paketler = {ad for ad, yol in paket_dizini.items() if yol.replace("\\", "/").startswith(BACKEND + "/")}
    ls = subprocess.run(["git", "ls-files", "-z", "--", BACKEND], cwd=KOK, capture_output=True, timeout=120)
    assert ls.returncode == 0, f"git ls-files düştü: {ls.stderr[:200]!r}"
    moduller = set()
    for yol in (x.decode("utf-8") for x in ls.stdout.split(b"\x00") if x):
        parca = yol.split("/")
        if len(parca) == 3 and parca[2].endswith(".py") and parca[2] != "__init__.py":
            moduller.add(parca[2][:-3])
        # 4-A inc. 4A-2.12: `package-dir`'e eklenmeden gelen alt paket de ürün kodudur (çalışma anında apps/backend sys.path'te).
        if len(parca) == 4 and parca[3] == "__init__.py":
            moduller.add(parca[2])
    return paketler | moduller


def _urun_dosyalari() -> list[str]:
    ls = subprocess.run(["git", "ls-files", "-z", "--", BACKEND], cwd=KOK, capture_output=True, timeout=120)
    assert ls.returncode == 0, f"git ls-files düştü: {ls.stderr[:200]!r}"
    return [x.decode("utf-8") for x in ls.stdout.split(b"\x00") if x and x.endswith(b".py")]


def test_KRITIK_kapsam_source_URUN_KODUNA_esit():
    t = _pyproject()
    urun = urun_kumesi(t)
    assert len(urun) >= 8, f"VAKUM: ürün kümesi yalnız {sorted(urun)} — türetme bozuk (paket-dir / git ls-files)"
    assert {"services", "backend_service"} <= urun, f"türetme ürün kodunu görmüyor: {sorted(urun)}"
    source = set(t["tool"]["coverage"]["run"]["source"])
    eksik, fazla = sorted(urun - source), sorted(source - urun)
    assert not eksik, f"kapsam ÖLÇMÜYOR (ratchet bu kodda kördür): {eksik}"
    assert not fazla, f"kapsam source'unda var olmayan ürün adı (coverage yalnız uyarır): {fazla}"
    # 4-A inc. 4A-2.12: `omit` ürün dosyasını ölçümden çıkarmamalı (coverage göreli deseni cwd'ye göre mutlaklaştırır).
    import fnmatch

    desenler = [
        d if d.startswith("*") or Path(d).is_absolute() else (KOK / d).as_posix()
        for d in t["tool"]["coverage"]["run"].get("omit", [])
    ]
    disarida = sorted(y for y in _urun_dosyalari() if any(fnmatch.fnmatch((KOK / y).as_posix(), d) for d in desenler))
    assert not disarida, f"[tool.coverage.run] omit ürün kodunu ölçümden ÇIKARIYOR: {disarida[:10]}"


def test_KARSIT_KANIT_turetme_paket_disi_ve_test_dizinini_ALMAZ():
    """Türetme `scripts`/`build_tools` (kurulum paketi ama ürün çalışma kodu değil) ve `tests`i ürün saymaz."""
    urun = urun_kumesi(_pyproject())
    assert not {"scripts", "build_tools", "tests", "ai_hub", "__init__"} & urun, sorted(urun)
