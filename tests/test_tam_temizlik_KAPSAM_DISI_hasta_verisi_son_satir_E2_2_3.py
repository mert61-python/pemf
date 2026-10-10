# -*- coding: utf-8 -*-
"""E2-2.3 (2-E incelemesi, A2) — `-IncludePatientData` son satırı "HASTA VERİSİ BU MAKİNEDEN SİLİNDİ (tam temizlik)" der ama KAPSAM
(`-Scope`) dışında kalan KVKK yolları DİSKTE DURUR ve raporda HİÇ geçmez (A-44: rapor yalnız doğrulananı "silindi" der).

Sahadaki yol: Inno kaldırması "hasta verisini de sil = EVET" → `setup_services.ps1 -Uninstall -PurgeData` →
`Invoke-PemfTeardown -Scope backend -IncludePatientData`. Footprint'te `~\\.pemf_gui` (Kvkk, Owner 'gui') backend kapsamında DEĞİL; oysa
backend de oraya yazar (`pemf_gui/config.py` PEMF_DATA_DIR yoksa config + eski anahtar dosyaları; `patient_database.get_patient_database`,
`pdf_report_generator` geri düşüşü — LocalSystem servisinde `systemprofile\\.pemf_gui`). `-Scope client` ise ana hasta DB'sini
(`PEMF_System\\PEMF_GUI`, Owner 'shared') bile bırakır ve aynı satırı yazar.

⛔ Gölge koşum: D2.E04'ün KANITLANMIŞ aparatı (`_APARAT`) DEĞİŞTİRİLMEDEN (kök pytest tmp_path altında; ARAÇ kolu aynı koşuda önce).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_tam_temizlik_MAKINE_DISI_yedek_raporu_ve_jeton_defteri_D2E04 import (  # noqa: F401  (pytestmark: win32 + pwsh)
    _APARAT,
    _PWSH,
    TEARDOWN,
    _agac,
    pytestmark,
)

_SISTEM_PEMF_GUI = Path("C/Windows/System32/config/systemprofile/.pemf_gui")


def _kos(tmp_path: Path, scope: str, hasta: bool = True) -> dict:
    kok = tmp_path / "kok"
    y = _agac(kok)
    eski = kok / _SISTEM_PEMF_GUI
    eski.mkdir(parents=True, exist_ok=True)
    (eski / "config.json").write_bytes(b'{"SENTETIK": 1}')
    (eski / ".pemf_key").write_bytes(b"SENTETIK")
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    kayit_dosyasi, cikti = tmp_path / "golge.jsonl", tmp_path / "cikti.json"
    arg = [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat), "-Kok", str(kok),
           "-Betik", str(TEARDOWN), "-Kayit", str(kayit_dosyasi), "-Cikti", str(cikti), "-Scope", scope]  # fmt: skip
    if hasta:
        arg.append("-IncludePatientData")
    p = subprocess.run(arg, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}"
    )
    s = json.loads(cikti.read_text(encoding="utf-8-sig"))
    s["kayitlar"] = [json.loads(ln) for ln in kayit_dosyasi.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    s["engel"] = [r for r in s["kayitlar"] if r["olay"].startswith("ENGEL")]
    s["agac"], s["eski"] = y, eski
    return s


def _son_satir_dogru(s: dict, duran: list[Path]) -> None:
    log, son = s["log"], s["log"][-1]
    assert not s["engel"], f"gölge koşumda kök dışı işlem denendi: {s['engel']}"
    assert all(d.exists() for d in duran), "aparat: kapsam dışı KVKK yolu silinmiş, kol anlamsız"
    for d in duran:
        satir = [ln for ln in log if str(d) in ln]
        assert satir and all("DURUYOR" in ln for ln in satir), (
            f"kapsam dışında DURAN hasta verisi raporda YOK: {d}\n" + "\n".join(log)
        )
    assert "BU MAKİNEDEN SİLİNDİ (tam temizlik)" not in son, (
        f"son satır 'BU MAKİNEDEN SİLİNDİ (tam temizlik)' diyor ama kapsam dışı hasta verisi diskte DURUYOR (A-44): {son!r}"
    )


def test_KRITIK_inno_PurgeData_scope_backend_pemf_gui_DURURKEN_son_satir_TAM_TEMIZLIK_demez_E2_2_3(tmp_path):
    s = _kos(tmp_path, "backend")
    _son_satir_dogru(s, [s["eski"]])
    assert not s["agac"]["hasta_db"].exists(), "karşıt: backend kapsamındaki ana hasta DB'si silinmeliydi"


def test_KRITIK_scope_client_ana_hasta_DBsi_DURURKEN_son_satir_TAM_TEMIZLIK_demez_E2_2_3(tmp_path):
    s = _kos(tmp_path, "client")
    _son_satir_dogru(s, [s["agac"]["hasta_db"].parent])


def test_KARSIT_scope_all_her_seyi_siler_son_satir_TAM_TEMIZLIK_E2_2_3(tmp_path):
    s = _kos(tmp_path, "all")
    assert not s["engel"]
    assert not s["eski"].exists() and not s["agac"]["hasta_db"].exists()
    assert "BU MAKİNEDEN SİLİNDİ (tam temizlik)" in s["log"][-1], s["log"][-1]
    assert not [ln for ln in s["log"] if "KAPSAM DIŞI" in ln], s["log"]


def test_KARSIT_sade_kaldirma_kapsam_disi_satiri_YAZMAZ_E2_2_3(tmp_path):
    s = _kos(tmp_path, "backend", hasta=False)
    assert "KORUNDU" in s["log"][-1] and not [ln for ln in s["log"] if "KAPSAM DIŞI" in ln], s["log"]
