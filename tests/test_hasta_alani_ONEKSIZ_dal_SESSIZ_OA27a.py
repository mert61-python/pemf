# -*- coding: utf-8 -*-
"""O-A2-7.a (2-A incelemesi) — D2.26'nın "ÖNEKSİZ dalda sessiz" niyeti KAPILANIR.

D2.26 (B-3.108) öneksiz eski alanları da birincil → legacy anahtar zinciriyle çözer; değer düz-metin de olabileceği için
başarısızlık ERROR DEĞİLDİR (`_decrypt_value(…, sessiz=True)`). 2-A incelemesi: `sessiz=True`'yu kaldıran mutant 30/30 YEŞİL —
yalnız "Decryption failed" ERROR gürültüsü üretiyordu (her hasta listelemesinde, düz-metin eski kayıt başına bir ERROR →
gerçek arızalar gürültüde kaybolur). Kapı günlüğü ölçer: öneksiz, base64'e benzeyen DÜZ-METİN bir alan okunurken
`pemf_gui.config` ERROR basmaz; karşıt — `enc:` önekli (şifreli OLDUĞU bilinen) çözülemeyen alan ERROR basar.
GERÇEK `PatientDatabase` + GERÇEK yapılandırma şifreleyicisi; alan SQL ile yazılır (eski kayıt benzetimi).
"""

from __future__ import annotations

import logging

import pytest

# base64 URL-güvenli çözülebilir ama Fernet belirteci DEĞİL (gAAAAA ile başlamaz) → düz-metin eski değer gibi görünür.
DUZ_ESKI = "QWxpVmVsaVlpbG1heg=="  # "AliVeliYilmaz" — eski sürümün düz-metin sahip adı benzetimi


@pytest.fixture
def hasta_db(temp_app_data, monkeypatch):
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    return pdb.PatientDatabase(str(temp_app_data / "patients.db"))


def _sahip_alanini_yaz(hasta_db, deger: str) -> str:
    pid = hasta_db.add_patient({"name": "Boncuk", "owner": "x", "species": "Kedi"})
    with hasta_db._get_connection() as c:
        c.execute("UPDATE patients SET owner = ? WHERE id = ?", (deger, pid))
        c.commit()
    hasta_db._reset_thread_conn()
    return pid


def _hata_kayitlari(caplog):
    return [r for r in caplog.records if r.levelno >= logging.ERROR and "Decryption failed" in r.getMessage()]


def test_KRITIK_ONEKSIZ_duz_metin_alan_okunurken_ERROR_basilmaz(hasta_db, caplog):
    pid = _sahip_alanini_yaz(hasta_db, DUZ_ESKI)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        hasta = hasta_db.get_patient(pid)
    assert hasta is not None and hasta.get("owner") == DUZ_ESKI, (
        f"ön koşul: düz-metin eski değer aynen dönmeli ({hasta})"
    )
    assert _hata_kayitlari(caplog) == [], "öneksiz düz-metin alan için 'Decryption failed' ERROR basıldı (gürültü)"


def test_KARSIT_ENC_onekli_cozulemeyen_alan_ERROR_basar(hasta_db, caplog):
    pid = _sahip_alanini_yaz(hasta_db, "enc:" + DUZ_ESKI)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        hasta_db.get_patient(pid)
    assert _hata_kayitlari(caplog), (
        "şifreli OLDUĞU bilinen (enc:) çözülemeyen alan sessiz kaldı — gerçek arıza görünmez"
    )
