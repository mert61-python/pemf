# -*- coding: utf-8 -*-
"""SON-A1.5 (22-SON A1a §6b · C13 conftest `_pemf_ortami_dosyadan_sizmaz` kapı gücü) — gözcü VAR OLAN bir `PEMF_*` değişkeninin
DEĞERİNİ doğrudan değiştirip bırakan dosyayı da yakalar ve değeri geri yükler.

ÖLÇÜLEN ZAYIFLIK (uç 8b002fc0): gözcünün kapısı (`test_PEMF_ortami_dosyadan_SIZMAZ_gozcusu_D5.py`) yalnız YENİ bir değişken ekleyen dosyayı
sınar. Gözcünün karşılaştırmasını `set(sonra) == set(once)` (yalnız ADLAR) yapan mutant o kapıda YEŞİL kaldı. Sahibin terminalinde
`PEMF_JETON_ENFORCED=0` VAR: ölçülmüş sızıntı `test_jeton_kullandikca_ode` (`PEMF_JETON_ENFORCED=1`) orada bir DEĞER değişimidir, ekleme değil.
Kanıt ALT SÜREÇTE (gerçek conftest köprüsü, gözcü kapısıyla aynı düzen); değişken alt süreç ortamında baştan "onceki" değeriyle VAR.
"""

from __future__ import annotations

from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam
from test_PEMF_ortami_dosyadan_SIZMAZ_gozcusu_D5 import _KOPRU

_TESTLER = Path(__file__).resolve().parent
_AD = "PEMF_D5_GOZCU_VAROLAN"
_YENI = "son-a15-gizli-deger-4471"

_DEGISTIREN = f'''
import os


def test_a_var_olani_dogrudan_degistirir():
    assert os.environ.get("{_AD}") == "onceki", "aparat: değişken baştan yok"
    os.environ["{_AD}"] = "{_YENI}"
'''

_SONRAKI = f'''
import os


def test_b_sonraki_dosya_ESKI_degeri_gorur():
    assert os.environ.get("{_AD}") == "onceki", "gözcü DEĞER değişimini geri ALMADI"
'''


def test_KRITIK_var_olan_PEMF_degiskeninin_DEGERINI_degistiren_dosya_KIRMIZI_ve_SIZMAZ(tmp_path):
    d = tmp_path / "sentetik"
    d.mkdir()
    (d / "test_a_degistiren.py").write_text(_DEGISTIREN, encoding="utf-8")
    (d / "test_b_sonraki.py").write_text(_SONRAKI, encoding="utf-8")
    (d / "conftest.py").write_text(
        _KOPRU.format(dizin=str(_TESTLER), yol=str(_TESTLER / "conftest.py")), encoding="utf-8"
    )
    env = yalitik_ortam(tmp_path / "ev")
    env[_AD] = "onceki"
    p = kostur(
        ["-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", "-p", "no:randomly", "--rootdir", str(d), str(d)],
        cwd=d,
        env=env,
    )
    cikti = p.stdout + p.stderr
    assert "ERROR test_a_degistiren.py::test_a_var_olani_dogrudan_degistirir" in cikti and _AD in cikti, (
        f"gözcü VAR OLAN değişkenin DEĞER değişimini yakalamadı:\n{cikti[-1500:]}"
    )
    assert "FAILED test_b_sonraki" not in cikti and "2 passed" in cikti, (
        f"değer değişimi sonraki dosyaya SIZDI (geri yüklenmedi):\n{cikti[-1500:]}"
    )
    assert _YENI not in cikti, "gözcü ortam DEĞERİNİ yazdı (sır olabilir)"
    assert p.returncode != 0
