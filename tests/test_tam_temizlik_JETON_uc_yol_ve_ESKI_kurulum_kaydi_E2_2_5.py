# -*- coding: utf-8 -*-
"""E2-2.5 (2-E incelemesi, A2) — KÖR KAPI: D2.E04 kapısı Y85 jeton defterinin ÜÇ footprint yolundan yalnız BİRİNİ
(`PEMF_System\\jeton_bekleyen.json`) ve iki launcher kurulum kökünden yalnız BİRİNİ (`PEMF Vet Client\\backup_dir.txt`) ölçer.

Ölçülen [amut.sh b d2e04k]: footprint'te `~\\.pemf\\jeton_bekleyen.json` `Kvkk=$false` yapılınca (sıradan kaldır-kur faturalanmamış tüketim
defterini SİLER — Y85 ihlali), staging defteri footprint'ten düşünce ve teardown eski `PEMFVetClient\\backup_dir.txt`'yi okumayınca
teardown/footprint kümesi (8 dosya) **105 passed** kalır. `servers/jeton.py:112`: `PEMF_DATA_DIR` yoksa defter `~\\.pemf`'tedir (launcher
makine veri kökünü yazamadığında); staging profili `PEMF_DATA_DIR=C:\\ProgramData\\PEMF_Staging`.

⛔ Gölge koşum: D2.E04'ün KANITLANMIŞ aparatı (`_APARAT`) DEĞİŞTİRİLMEDEN (kök pytest tmp_path altında); ağaca yalnız ek SENTETİK dosyalar.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_tam_temizlik_MAKINE_DISI_yedek_raporu_ve_jeton_defteri_D2E04 import (  # noqa: F401  (pytestmark: win32 + pwsh)
    _APARAT,
    _PWSH,
    TEARDOWN,
    _agac,
    pytestmark,
)

_JETONLAR = (
    Path("C/ProgramData/PEMF_System/jeton_bekleyen.json"),
    Path("C/ProgramData/PEMF_Staging/jeton_bekleyen.json"),
    Path("C/Users/denetim/.pemf/jeton_bekleyen.json"),
    Path("C/Windows/System32/config/systemprofile/.pemf/jeton_bekleyen.json"),
)
_ESKI_KURULUM = Path("C/Users/denetim/AppData/Local/PEMFVetClient")


def _kos(tmp_path: Path, hasta: bool) -> dict:
    kok = tmp_path / "kok"
    _agac(kok)
    for j in _JETONLAR:
        (kok / j).parent.mkdir(parents=True, exist_ok=True)
        (kok / j).write_bytes(b'{"bekleyen": []}')
    eski_hedef = kok / "H" / "Yedek_eski_kurulum"
    eski_hedef.mkdir(parents=True)
    for ad in ("pemf_patients_20261001_0300.db", "kurtarma-zarfi.enc"):
        (eski_hedef / ad).write_bytes(b"SENTETIK")
    (kok / _ESKI_KURULUM).mkdir(parents=True, exist_ok=True)
    (kok / _ESKI_KURULUM / "backup_dir.txt").write_bytes(str(eski_hedef).encode("utf-8"))
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    kayit_dosyasi, cikti = tmp_path / "golge.jsonl", tmp_path / "cikti.json"
    arg = [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat), "-Kok", str(kok),
           "-Betik", str(TEARDOWN), "-Kayit", str(kayit_dosyasi), "-Cikti", str(cikti)]  # fmt: skip
    if hasta:
        arg.append("-IncludePatientData")
    p = subprocess.run(arg, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}"
    )
    s = json.loads(cikti.read_text(encoding="utf-8-sig"))
    s["kayitlar"] = [json.loads(ln) for ln in kayit_dosyasi.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    s["engel"] = [r for r in s["kayitlar"] if r["olay"].startswith("ENGEL")]
    s["kok"], s["eski_hedef"] = kok, eski_hedef
    return s


@pytest.mark.parametrize("hasta", [True, False], ids=["tam", "sade"])
def test_KRITIK_Y85_jeton_defteri_UC_yolun_HEPSINDE_yalniz_tam_temizlikte_silinir_E2_2_5(tmp_path, hasta):
    s = _kos(tmp_path, hasta)
    assert not s["engel"], s["engel"]
    for j in _JETONLAR:
        yol = s["kok"] / j
        if hasta:
            assert not yol.exists(), f"tam temizlik jeton defterini bıraktı (Y85): {j}"
            assert [ln for ln in s["log"] if "silindi (HASTA-VERİSİ)" in ln and ln.endswith(str(yol))], (
                f"jeton defterinin silindiği DOĞRULANARAK raporlanmadı: {j}"
            )
        else:
            assert yol.exists(), f"sıradan kaldırma faturalanmamış tüketim defterini SİLDİ (Y85): {j}"


@pytest.mark.parametrize("hasta", [True, False], ids=["tam", "sade"])
def test_KRITIK_eski_PEMFVetClient_kaydindaki_makine_disi_hedef_RAPORLANIR_E2_2_5(tmp_path, hasta):
    s = _kos(tmp_path, hasta)
    satir = [ln for ln in s["log"] if str(s["eski_hedef"]) in ln]
    assert len(satir) == 1 and "DURUYOR" in satir[0] and "kurtarma-zarfi.enc VAR" in satir[0], (
        "eski kurulum kökündeki (PEMFVetClient) backup_dir.txt hedefi raporda yok:\n" + "\n".join(s["log"])
    )
    assert s["eski_hedef"].exists() and len(list(s["eski_hedef"].iterdir())) == 2, "makine dışı hedefe dokunuldu (A-45)"
