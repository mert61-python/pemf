# -*- coding: utf-8 -*-
"""D4.04 · B-10.83 — İZLENEN ağaca (`firmware/`, `apps/ui/`) bakan kapılar ZORUNLU kipte DÜŞER, varsayılan kipte ATLAR.

🔴 ÖLÇÜLEN DURUM (2026-10-10, 4-A): ESP portal STA kilidi, status buffer, 8266 termal eşik (+ S3 asimetrisi), IRAM veri,
MAG yön raporu ve ACİL DURDUR erişimi kapıları modül düzeyinde düz `pytest.mark.skipif(not <yol>.exists())` taşıyordu.
Klonda `firmware/esp8266_pemf_coil`, `firmware/esps3_pemf_coil` ve `ControlScreen.tsx` yeniden adlandırılıp altı dosya
`PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` ile koşulunca sonuç **28 skipped** — yayın makinesinin "sessizce atlandı"yı imkânsız kılan
bayrağı bu kapıları göremiyordu (09-18 `pf`→`apps/ui` taşıması gibi bir klasör taşıması güvenlik kapılarını susturur).
Artık kapılar `capraz.atla_yoksa(..., izlenen=True)` autouse fikstürüyle kapılı: ZORUNLU=1'de DÜŞER.

KAPI (davranış, yapı değil): her dosya `firmware/` ve `apps/ui/` OLMAYAN geçici bir köke (yalnız `tests/<dosya>` +
yardımcılar) kopyalanır ve AYRI süreçte iki kipte koşulur — ZORUNLU=1: hepsi düşer (fikstürdeki `pytest.fail` → ERROR,
çıkış 1), 0 passed/skipped; varsayılan: hepsi
SKIPPED ("izlenen kaynak yok"), 0 failed. Ölçücünün eski deseni ayırt ettiği KARŞIT kolunda gösterilir.
⚠️ Dış koşucu `PEMF_CAPRAZ_KAYNAK_ZORUNLU`'yu zaten verse bile iki kol alt sürece AÇIKÇA kurulur (koşucu maskelemesin).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

#: D4.04'ün kapsadığı (B-10.83) izlenen-ağaç kapıları.
KAPILAR = (
    "test_esp8266_portal_sta_kilidi.py",
    "test_esp8266_status_buffer_boyutu.py",
    "test_esp8266_termal_esik.py",
    "test_esp_iram_veri_kapisi.py",
    "test_esp_mag_yon_raporu.py",
    "test_estop_erisimi_2026_09_04.py",
)
YARDIMCILAR = ("capraz.py", "c_soyucu.py")
_OZET = re.compile(r"^(?:=+ )?((?:\d+ [a-z]+(?:, )?)+) in [\d.]+s", re.M)


def _kos(kok: Path, dosya_adi: str, zorunlu: bool) -> tuple[int, dict[str, int], str]:
    """Geçici kökte `tests/<dosya_adi>`yı ayrı süreçte koşar → (rc, {passed/failed/skipped/error}, çıktı)."""
    env = {k: v for k, v in os.environ.items() if k != "PEMF_CAPRAZ_KAYNAK_ZORUNLU"}
    if zorunlu:
        env["PEMF_CAPRAZ_KAYNAK_ZORUNLU"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    komut = [sys.executable, "-m", "pytest", str(kok / "tests" / dosya_adi), "-q", "-rs", "-p", "no:cacheprovider"]
    komut += ["-p", "no:randomly", "--rootdir", str(kok), "-c", str(kok / "pytest.ini")]
    r = subprocess.run(
        komut, cwd=kok, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
    )
    cikti = r.stdout + r.stderr
    eslesme = _OZET.findall(cikti)
    sayilar = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    if eslesme:
        for parca in eslesme[-1].split(", "):
            n, tur = parca.split(" ", 1)
            sayilar[tur.rstrip("s") if tur in ("errors",) else tur] = int(n)
    return r.returncode, sayilar, cikti


def _gecici_kok(tmp_path: Path, ad: str, dosyalar: dict[str, str | Path]) -> Path:
    kok = tmp_path / ad
    (kok / "tests").mkdir(parents=True)
    for hedef, kaynak in dosyalar.items():
        if isinstance(kaynak, Path):
            shutil.copy2(kaynak, kok / "tests" / hedef)
        else:
            (kok / "tests" / hedef).write_text(kaynak, encoding="utf-8")
    (kok / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    assert not (kok / "firmware").exists() and not (kok / "apps").exists()
    return kok


@pytest.mark.parametrize("dosya_adi", KAPILAR)
def test_KRITIK_izlenen_agac_YOKKEN_zorunlu_kipte_DUSER_varsayilanda_ATLAR(tmp_path, dosya_adi):
    kaynaklar = {dosya_adi: TESTS / dosya_adi, **{y: TESTS / y for y in YARDIMCILAR}}
    rc_z, z, cikti_z = _kos(_gecici_kok(tmp_path, "z", kaynaklar), dosya_adi, zorunlu=True)
    rc_v, v, cikti_v = _kos(_gecici_kok(tmp_path, "v", kaynaklar), dosya_adi, zorunlu=False)
    # autouse fikstüründeki `pytest.fail` pytest'te ERROR (kurulum hatası) sayılır — çıkış kodu yine 1 (kırmızı).
    dusen = z["failed"] + z["error"]
    assert dusen > 0, f"ZORUNLU=1 kolu: hiç FAILED/ERROR yok — kapı yine sessizce atlanıyor: {z}\n{cikti_z[-1500:]}"
    assert (z["passed"], z["skipped"], rc_z) == (0, 0, 1), f"ZORUNLU=1 kolu: {z} rc={rc_z}\n{cikti_z[-1500:]}"
    assert "PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 ama izlenen kaynak yok" in cikti_z
    assert v["skipped"] == dusen, f"varsayılan kip: {v} (ZORUNLU'da {dusen} düştü)\n{cikti_v[-1500:]}"
    assert (v["passed"], v["failed"], v["error"], rc_v) == (0, 0, 0, 0), (
        f"varsayılan kip: {v} rc={rc_v}\n{cikti_v[-1500:]}"
    )
    assert "izlenen kaynak yok" in cikti_v


def test_KARSIT_KANIT_olcucu_duz_skipif_i_AYIRT_EDER(tmp_path):
    """Ölçücü körse yukarıdaki kapı anlamsızdır: ESKİ desen (düz skipif) aynı koşumda ZORUNLU=1'de de ATLANIR."""
    eski = (
        "from pathlib import Path\nimport pytest\n"
        "KOK = Path(__file__).resolve().parents[1]\n"
        'pytestmark = pytest.mark.skipif(not (KOK / "firmware" / "x").exists(), reason="firmware/ kaynak agaci yok")\n'
        "def test_a():\n    assert True\n"
        "def test_b():\n    assert True\n"
    )
    kok = _gecici_kok(tmp_path, "eski", {"test_eski_desen.py": eski, **{y: TESTS / y for y in YARDIMCILAR}})
    rc, z, cikti = _kos(kok, "test_eski_desen.py", zorunlu=True)
    assert (z["skipped"], z["failed"], rc) == (2, 0, 0), (
        f"ölçücü eski deseni ayırt etmiyor: {z} rc={rc}\n{cikti[-800:]}"
    )
