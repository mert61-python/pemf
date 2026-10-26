# -*- coding: utf-8 -*-
"""D5 (TEST APARATININ SIZMASI · ortam sızıntısı envanteri): conftest `_pemf_ortami_dosyadan_sizmaz` gözcüsünün KENDİ kapısı.

ÖLÇÜLEN KUSUR (D5 tam süit envanteri, D1B gözcü eklentisi): üç dosya `PEMF_*` ortamını değiştirip bırakıyordu —
`test_jeton_kullandikca_ode` (`PEMF_JETON_ENFORCED=1`, `PEMF_JETON_BORC_TAVANI`), `test_jeton_yoneticisi` (`PEMF_JETON_ENFORCED`),
`test_kesif_gercek_port` (`PEMF_API_PORT`). Sonraki dosyalar ücretlendirme açık / farklı port kipinde koşuyordu; hiçbir kapı görmüyordu.

Gözcü dosya sonunda çalışır (modül söküm) → aynı dosyadan sınanamaz. Kanıt ALT SÜREÇTE: GERÇEK `tests/conftest.py` köprü conftest'le
yüklenir, geçici dizindeki iki sentetik dosya koşar — biri `os.environ`a doğrudan yazar (KIRMIZI + adı söylenir +
değer yazılmaz + sonraki dosyaya SIZMAZ), diğeri `monkeypatch.setenv` kullanır (yeşil). Ortam: `betik_alt_sureci.yalitik_ortam`."""

from __future__ import annotations

from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam

_TESTLER = Path(__file__).resolve().parent
_DEGER = "d5-gizli-deger-9137"

_SIZDIRAN = f'''
import os


def test_a_dogrudan_yazar():
    os.environ["PEMF_D5_GOZCU_DENEME"] = "{_DEGER}"
'''

# Gömülü Python (`._pth`) PYTHONPATH'i yok sayar → `-p conftest` modülü bulamaz. Köprü: GERÇEK conftest dosya yolundan yüklenir ve
# fikstür / kancaları bu dizinin conftest'ine aktarılır (pytest onları buradan toplar).
_KOPRU = '''
import importlib.util
import sys

sys.path.insert(0, {dizin!r})
_spec = importlib.util.spec_from_file_location("pemf_tests_conftest", {yol!r})
_m = importlib.util.module_from_spec(_spec)
sys.modules["pemf_tests_conftest"] = _m
_spec.loader.exec_module(_m)
globals().update({{k: v for k, v in vars(_m).items() if not k.startswith("__")}})
'''

_SONRAKI = '''
import os


def test_b_sonraki_dosya_temiz_baslar():
    assert "PEMF_D5_GOZCU_DENEME" not in os.environ, "gözcü sızıntıyı GERİ ALMADI"


def test_c_monkeypatch_ile_yazan_temizdir(monkeypatch):
    monkeypatch.setenv("PEMF_D5_GOZCU_TEMIZ", "1")
'''


def _kos(tmp_path: Path, dosyalar: dict):
    d = tmp_path / "sentetik"
    d.mkdir()
    for ad, metin in dosyalar.items():
        (d / ad).write_text(metin, encoding="utf-8")
    (d / "conftest.py").write_text(
        _KOPRU.format(dizin=str(_TESTLER), yol=str(_TESTLER / "conftest.py")), encoding="utf-8"
    )
    env = yalitik_ortam(tmp_path / "ev")
    p = kostur(
        ["-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", "--rootdir", str(d), str(d)],
        cwd=d,
        env=env,
    )
    return p, p.stdout + p.stderr


def test_KRITIK_dogrudan_yazan_dosya_KIRMIZI_adi_soylenir_deger_yazilmaz_ve_SIZMAZ(tmp_path):
    p, cikti = _kos(tmp_path, {"test_a_sizdiran.py": _SIZDIRAN, "test_b_sonraki.py": _SONRAKI})
    assert "PEMF_D5_GOZCU_DENEME" in cikti and "BIRAKTI" in cikti, f"gözcü sızıntıyı söylemedi:\n{cikti[-1500:]}"
    assert "1 error" in cikti and "3 passed" in cikti, (
        f"beklenen: sızdıran dosyada söküm HATASI, diğerleri yeşil:\n{cikti[-1500:]}"
    )
    assert "ERROR test_a_sizdiran.py::test_a_dogrudan_yazar" in cikti, cikti[-1500:]
    assert _DEGER not in cikti, "gözcü ortam DEĞERİNİ yazdı (sır olabilir)"
    assert p.returncode != 0


def test_KARSIT_monkeypatch_ile_yazan_dosyalar_YESIL(tmp_path):
    p, cikti = _kos(tmp_path, {"test_b_sonraki.py": _SONRAKI})
    assert p.returncode == 0 and "2 passed" in cikti and "error" not in cikti.lower(), cikti[-1500:]
