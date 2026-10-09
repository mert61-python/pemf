# -*- coding: utf-8 -*-
"""A3 · D2-3.6 — makine dışı hedefte `OKU-KURTARMA.txt` (felaket günü okunacak TEK talimat) YAZILAMAZSA günlük yalnız DEBUG düzeyinde
iz bırakıyor (`headless_db_maintenance._copy_offsite`: `logger.debug("off-machine kurtarma notu yazilamadi")`) — aynı turda INFO
"… KURTARMA KODU ile baska makinede geri yuklenebilir" yazılmış oluyor. Hedefte ESKİ bir not varsa güncel olmayan talimat (ör. D2.51
öncesi dosya listesi: hesap / ayar yedeklerini ve `--hesap-yedegi` adımını bilmez) sessizce kalır; hiç yoksa yedeklerin yanında talimat yoktur.
ARIZA EN ALT KATTA, GERÇEK BİÇİMİYLE: hedefte `OKU-KURTARMA.txt` adında bir DİZİN var → `write_text` işletim sisteminden PermissionError
(Windows) / IsADirectoryError alır (ACL değiştirilmez). Aparat 2-D D2.12 kapısıyla aynı (gerçek TreatmentHistoryDB yedeği + zarf baytları).
Depo yeri: tests/test_kurtarma_notu_YAZILAMAZSA_SESSIZ_DEGIL_D236.py
"""

from __future__ import annotations

import logging
import threading

import pytest

ZARF = "kurtarma-zarfi.enc"
NOT = "OKU-KURTARMA.txt"


@pytest.fixture
def o(temp_app_data, tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from services.headless_db_maintenance import HeadlessDBMaintenance

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = TreatmentHistoryDB(temp_app_data)
    tdb.start_session(treatment_mode="Manuel", patient_name="D236Hasta")
    nas = tmp_path / "NAS"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))
    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = temp_app_data, tdb, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, 14
    w._stop, w._thread = threading.Event(), None
    bdir = temp_app_data / "backups"
    bdir.mkdir(exist_ok=True)
    yedek = bdir / "pemf_treatment_history_20261009_080000.db"
    assert tdb.create_backup(str(yedek))
    zarf = bdir / ZARF
    zarf.write_bytes(b'{"tur": "kurtarma-zarfi", "v": 1, "aparat": "D236"}')
    try:
        yield type("O", (), {"w": w, "nas": nas, "yedek": yedek, "zarf": zarf})
    finally:
        tdb.close()


def _kayitlar(caplog):
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "services.headless_db_maintenance"]


def test_KRITIK_D236_kurtarma_notu_YAZILAMAZSA_WARNING_ve_neden(o, caplog):
    (o.nas / NOT).mkdir(parents=True)  # hedefte aynı adlı dizin → gerçek OS hatası
    with caplog.at_level(logging.DEBUG, logger="services.headless_db_maintenance"):
        o.w._copy_offsite([o.yedek, o.zarf])
    k = _kayitlar(caplog)
    assert any(lv == logging.INFO and "geri yuklenebilir" in m for lv, m in k), (
        f"aparat: kopya özeti beklenen gibi değil: {k}"
    )
    uyari = [m for lv, m in k if lv >= logging.WARNING and "kurtarma notu" in m.lower()]
    assert uyari, (
        f"makine dışı hedefe {NOT} YAZILAMADI ama günlükte WARNING+ yok (yalnız DEBUG) — felaket günü talimat eksik/eski: "
        f"{[(logging.getLevelName(lv), m[:90]) for lv, m in k]}"
    )


def test_KARSIT_D236_not_yazilinca_uyari_yok_ve_metin_yerinde(o, caplog):
    with caplog.at_level(logging.DEBUG, logger="services.headless_db_maintenance"):
        o.w._copy_offsite([o.yedek, o.zarf])
    assert (o.nas / NOT).is_file() and "NASIL GERI YUKLENIR" in (o.nas / NOT).read_text(encoding="utf-8")
    assert not [m for lv, m in _kayitlar(caplog) if lv >= logging.WARNING and "kurtarma notu" in m.lower()]
