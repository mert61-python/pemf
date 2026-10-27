# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.45 (B-10.45) KAPISI — `row_factory` geri yüklemesi ŞİFRELİ (sqlcipher3) `TreatmentHistoryDB` havuzunda da doğru.

ARIZA (DENETİM-10 B-10.45): `tests/test_row_factory_havuz_kirlenmesi.py` yalnız DÜZ SQLite kökünde koşuyor. Orada havuz
bağlantısının fabrikası `sqlite3.Row` olduğu için `sqlcipher_util` geri yüklemesinde `onceki` yerine SABİT `sqlite3.Row`
yazan mutant YEŞİL kalıyordu (21/21) — oysa at-rest şifreli kurulumda (sahadaki varsayılan) havuz `sqlcipher3.dbapi2.Row`
kullanır; sabit `sqlite3.Row` o bağlantıda `row["kolon"]` erişimlerini `TypeError`a çevirir (KVKK sayımı / dışa aktarma /
geçmiş). `tests/sahte_sqlcipher.py`nin `Row`u da `sqlite3.Row` olduğu için sahte bağlayıcı bu farkı GÖSTEREMEZ → GERÇEK
sqlcipher3 şart.

A-46 (sahip): sqlcipher3 YOKKEN bu kapı SESSİZCE ATLANMAZ — atlama nedeni "sqlcipher3" içerir ve `sqlcipher_atlama_kapisi`
(conftest) koşuyu KIRMIZI bitirir (yalnız bilinçli benzetimde `PEMF_SQLCIPHER_ATLAMA_SERBEST=1`). CI-eşdeğeri:
`sys.modules["sqlcipher3"] = None` (koşucu `D2A_SQLCIPHER_YOK=1`).

KAPI: gerçek sqlcipher3 + anahtarlı geçici `TreatmentHistoryDB`; havuz fabrikası sqlcipher `Row`; `denetim_oku` SONRASI
aynı thread'de (1) fabrika AYNI nesne, (2) geçmiş sorgusu `TypeError`suz ve kolon adıyla erişilebilir, (3) KVKK redaksiyon
sayımı sıfır-olmayan değeri korur.
MUTASYON: `sqlcipher_util` geri yüklemesinde `conn.row_factory = onceki` → `conn.row_factory = sqlite3.Row` → KIRMIZI.
"""

from __future__ import annotations

import pytest
import sahte_sqlcipher

_ANAHTAR = "D545-sifreli-havuz-anahtari"


@pytest.fixture()
def sifreli_db(temp_app_data, monkeypatch):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    gercek = sahte_sqlcipher.baglayici_kur(
        "gercek", monkeypatch
    )  # yoksa "sqlcipher3 yok" ile atlar → A-46 koşuyu düşürür
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: _ANAHTAR)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = thdb.TreatmentHistoryDB(temp_app_data)
    try:
        yield db, gercek
    finally:
        db.close()


def test_KRITIK_D545_SIFRELI_havuzda_denetim_oku_row_factoryi_AYNEN_geri_yukler(sifreli_db):
    db, gercek = sifreli_db
    assert getattr(db, "_use_sqlcipher", None) is not False, "aparat: DB şifreli açılmadı"
    sid = db.start_session("Manuel", operator_name="Dr. D545", patient_name="Pamuk")
    assert sid, "aparat: seans yazılamadı"
    with db._get_connection() as conn:
        onceki = conn.row_factory
        conn.execute("UPDATE treatment_sessions SET session_date = date('now', '-730 day') WHERE id = ?", (sid,))
        conn.commit()
    assert onceki is gercek.Row, (
        f"aparat: şifreli havuz bağlantısının fabrikası sqlcipher Row değil ({onceki!r}) — kapı düz SQLite'ı ölçüyor olurdu"
    )
    assert onceki is not __import__("sqlite3").Row, "aparat: sqlcipher Row ile sqlite3.Row ayırt edilemiyor"
    bekleyen = db.redaksiyon_bekleyen_sayisi(365)
    assert bekleyen > 0, "aparat: bekleyen redaksiyon sıfır (kirlenme görünmezdi)"
    assert db.denetim_yaz("d545_olay", operator_email="a@b.c", scope="test") is True

    kayitlar = db.denetim_oku(10)
    assert kayitlar and isinstance(kayitlar[0], dict), "denetim_oku sözleşmesi bozuldu (dict değil)"

    with db._get_connection() as conn:
        assert conn.row_factory is onceki, (
            f"denetim_oku ŞİFRELİ havuz bağlantısının fabrikasını DEĞİŞTİRDİ ({conn.row_factory!r} ≠ {onceki!r}) — "
            "süreç ömrü boyunca row['kolon'] erişimleri TypeError verir"
        )
    gecmis = db.get_session_history(limit=10)  # aynı thread, aynı havuz bağlantısı
    assert gecmis and gecmis[0]["patient_name"] == "Pamuk", f"geçmiş sorgusu kolon adıyla okunamadı: {gecmis[:1]}"
    assert db.redaksiyon_bekleyen_sayisi(365) == bekleyen, (
        "denetim_oku sonrası KVKK sayımı değişti (onay bloğu kaybolur)"
    )
