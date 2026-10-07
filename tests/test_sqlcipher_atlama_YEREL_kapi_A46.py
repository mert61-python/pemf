# -*- coding: utf-8 -*-
"""A-46 YEREL İKİZİ (2-A inceleme · sahip isteği 2026-10-07) — "sqlcipher" nedenli ATLAMA her pytest koşusunu KIRMIZI bitirir.

ÖLÇÜLEN AÇIK. CI'daki junit sayacı (`scripts/ci_sqlcipher_atlama_kapisi.py`, D2.07) yalnız CI'da koşuyordu; sqlcipher3 bu
makinede kuruluyken sorun görünmüyordu, ama sqlcipher3'süz bir ortamda (CI-Windows eşdeğeri, 2-A incelemesi) 66 şifreleme /
göç / karantina / kurtarma kapısı ATLANDI, 13'ü hiç TOPLANMADI ve koşu yalnız ilgisiz README kırmızılarıyla bitti.

KAPI: `tests/sqlcipher_atlama_kapisi.py` (conftest `pytest_configure` → `kur`). Nedeninde harf duyarsız "sqlcipher" geçen
test (kurulum ya da gövde) ve modül toplama atlaması koşuyu çıkış 1 ile bitirir ve adlarıyla listelenir; ilgisiz atlama
dokunulmaz; bilinçli benzetimde `PEMF_SQLCIPHER_ATLAMA_SERBEST=1` (liste yine basılır). Sentetik test dosyaları ALT SÜREÇTE
gerçek pytest ile (`-p sqlcipher_atlama_kapisi`) koşturulur; süitin conftest'inin kapıyı kaydettiği ayrıca ölçülür.
"""

from __future__ import annotations

from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam

TESTLER = Path(__file__).resolve().parent
SERBEST = "PEMF_SQLCIPHER_ATLAMA_SERBEST"

_SURUCU = (
    "import sys\n"
    "sys.path.insert(0, {testler!r})\n"
    "import pytest\n"
    "sys.exit(int(pytest.main([{dizin!r}, '-q', '-rs', '-p', 'no:cacheprovider', '-p', 'no:randomly',"
    " '-p', 'sqlcipher_atlama_kapisi'])))\n"
)

_GECEN = "def test_gecer():\n    assert True\n"


def _kos(tmp_path: Path, dosyalar: dict, serbest: bool = False):
    dizin = tmp_path / "ornek"
    dizin.mkdir()
    for ad, govde in dosyalar.items():
        (dizin / ad).write_text(govde, encoding="utf-8")
    surucu = tmp_path / "surucu.py"
    surucu.write_text(_SURUCU.format(testler=str(TESTLER), dizin=str(dizin)), encoding="utf-8")
    env = yalitik_ortam(tmp_path / "ev")
    env.pop(SERBEST, None)
    if serbest:
        env[SERBEST] = "1"
    p = kostur([str(surucu)], cwd=dizin, env=env, sure=180)
    return p.returncode, p.stdout + p.stderr


def test_KRITIK_sqlcipher_nedenli_test_ATLAMASI_kosuyu_KIRMIZI_bitirir(tmp_path):
    """İşaretle (kurulumda) ve gövdede atlama; büyük harfli "SQLCipher" de sayılır.
    MUTASYON: çıkış kodunu değiştirmemek · harf duyarlı eşleşme · yalnız gövde atlamasını saymak → KIRMIZI."""
    rc, cikti = _kos(
        tmp_path,
        {
            "test_ornek.py": "import pytest\n\n"
            + _GECEN
            + "\n\n@pytest.mark.skip(reason='sqlcipher3 yok — gercek baglayici kolu (sahte kol yine kosar)')\n"
            "def test_isaretle_atlanir():\n    pass\n\n\n"
            "def test_govdede_atlanir():\n    pytest.skip('at-rest goc davranisi SQLCipher ister')\n"
        },
    )
    assert rc == 1, (
        f"'sqlcipher' nedenli atlama varken koşu BAŞARILI bitti (rc={rc}) -> kapılar sessizce atlanır:\n{cikti[-1500:]}"
    )
    assert "KIRMIZI (A-46): 2 test/modul" in cikti, f"iki atlama da sayılmadı:\n{cikti[-1500:]}"
    assert "test_isaretle_atlanir" in cikti and "test_govdede_atlanir" in cikti, cikti[-1500:]


def test_KRITIK_modul_duzeyi_sqlcipher_atlamasi_da_KIRMIZI(tmp_path):
    """Modül düzeyi `importorskip("sqlcipher3")` testleri HİÇ toplamaz (junit'te tek satır) — o da sayılır.
    MUTASYON: toplama raporunu dinlememek → KIRMIZI."""
    rc, cikti = _kos(
        tmp_path,
        {
            "test_gecen.py": _GECEN,
            "test_modul.py": "import pytest\n\npytest.skip('sqlcipher3 yok - modul toplanamaz', allow_module_level=True)\n\n\n"
            + _GECEN.replace("test_gecer", "test_hic_kosmaz"),
        },
    )
    assert rc == 1, f"modül düzeyi sqlcipher atlaması varken koşu BAŞARILI bitti (rc={rc}):\n{cikti[-1500:]}"
    assert "test_modul.py (modül toplanmadı)" in cikti, f"toplanmayan modül listelenmedi:\n{cikti[-1500:]}"


def test_KARSIT_ilgisiz_atlama_kosuyu_DUSURMEZ(tmp_path):
    """Kapı yalnız sqlcipher atlamasını sayar; platform/ortam atlamaları koşuyu düşürmez."""
    rc, cikti = _kos(
        tmp_path,
        {
            "test_ornek.py": "import pytest\n\n"
            + _GECEN
            + "\n\n@pytest.mark.skip(reason='yalniz Windows (icacls)')\ndef test_ilgisiz():\n    pass\n"
        },
    )
    assert rc == 0 and "A-46" not in cikti, f"ilgisiz atlama koşuyu düşürdü (rc={rc}):\n{cikti[-1500:]}"


def test_KARSIT_SERBEST_bayragiyla_benzetim_KOSAR_liste_yine_BASILIR(tmp_path):
    """CI-eşdeğeri atlama sayımı (bilinçli benzetim) yapılabilmeli — ama sessiz değil: liste basılır.
    MUTASYON: bayrağı yok saymak → KIRMIZI."""
    rc, cikti = _kos(
        tmp_path,
        {
            "test_ornek.py": "import pytest\n\n"
            + _GECEN
            + "\n\n@pytest.mark.skip(reason='sqlcipher3 yok')\ndef test_atlanir():\n    pass\n"
        },
        serbest=True,
    )
    assert rc == 0, f"{SERBEST}=1 iken koşu düştü (rc={rc}):\n{cikti[-1500:]}"
    assert "SERBEST" in cikti and "test_atlanir" in cikti, f"benzetimde atlama listesi BASILMADI:\n{cikti[-1500:]}"


def test_KRITIK_suitin_conftesti_kapiyi_KAYDEDER(request):
    """Kapı yalnız `-p` ile değil, süitin her koşusunda (conftest) etkin olmalı. MUTASYON: conftest kaydını silmek → KIRMIZI."""
    assert request.config.pluginmanager.has_plugin("sqlcipher-atlama-kapisi"), (
        "süitin conftest'i sqlcipher atlama kapısını KAYDETMİYOR -> sqlcipher3'süz yerel koşu yine YEŞİL biter"
    )
