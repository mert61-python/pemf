# -*- coding: utf-8 -*-
"""4A-1.4 (A1 incelemesi) — D4.11'de kaldırılan `GUVENLIK_YOLLARI` hâlâ "garanti/taşıyıcı" diye anılıyor mu? (BAYAT BELGE)

ÖLÇÜLEN (A1, 2026-10-11): `launcher/core/src/install.rs:155-156` (jeton bayrağının doc-yorumu): "SEANS / ACIL DURDUR / SENSOR
IZLEME HICBIR KOSULDA KAPILANMAZ — bu, jeton modulunun kendi `GUVENLIK_YOLLARI` listesiyle garanti altinda". Liste D4.11'de
silindi (zaten üretimde hiç eşleşmiyordu); bayrağı açacak kişiye YANLIŞ taşıyıcıyı gösterir. 4-A belge düzeltmesi yalnız
Python/Markdown/device.env'e baktı (`.rs` atlandı).

Kapı: izlenen her dosyada `GUVENLIK_YOLLARI` geçişi YALNIZ geçmiş-anlatımı yapan bilinen dosyalarda olabilir (tarihli anlık
görüntü `docs/acik-isler-2026-09-12.md` dahil). Başka her geçiş KIRMIZI. `git ls-files` kümesinde okunur (temiz ağaç ölçümü).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_GECMIS_ANLATAN = {
    "apps/backend/servers/jeton.py",
    "docs/JETON-SISTEMI.md",
    "docs/acik-isler-2026-09-12.md",  # tarihli anlık görüntü (4-A açık #9)
    "tests/test_jeton_bakiye_gorunurlugu.py",
    "tests/test_jeton_kapisi_TUM_ROTALARDA_guvenlik_uclari_SERBEST_D411.py",
    "tests/test_jeton_yoneticisi.py",
    "tests/test_GUVENLIK_YOLLARI_tasiyici_diye_ANILMAZ_4A14.py",  # bu kapının kendisi
}


def _gecen_dosyalar() -> set[str]:
    r = subprocess.run(
        ["git", "-c", "core.quotepath=off", "grep", "-l", "GUVENLIK_YOLLARI"],
        cwd=KOK,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert r.returncode in (0, 1), r.stderr
    return {s.strip() for s in r.stdout.splitlines() if s.strip() and not Path(s.strip()).name.startswith("test_zz_")}


def test_KRITIK_kaldirilan_GUVENLIK_YOLLARI_baska_dosyada_TASIYICI_diye_anilmaz():
    fazla = sorted(_gecen_dosyalar() - _GECMIS_ANLATAN)
    assert not fazla, (
        f"kaldırılan `GUVENLIK_YOLLARI` şu dosyalarda hâlâ anılıyor: {fazla} — tedavi/E-stop serbestliğinin taşıyıcısı "
        "`servers/jeton.py::_islem_turu` + `_SERBEST_AI_UCLARI` (D4.11)"
    )


def test_KARSIT_olcucu_KOR_degil_jeton_py_gecmis_notu_bulunur():
    assert "apps/backend/servers/jeton.py" in _gecen_dosyalar()
