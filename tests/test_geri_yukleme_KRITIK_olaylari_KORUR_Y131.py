# -*- coding: utf-8 -*-
"""Y131 (S-F2-1.4, sahip — D3 devri → D5): "Tümünü değiştir" (REPLACE_ALL) geri yüklemesi yedekten SONRA kaydedilmiş KRİTİK olayları
(ACİL DURDUR, mandal sıfırlama, hekim onay / ret izi, servis kapanışı ve önemi critical / warning olan her olay) SİLMEZ: mevcut DB'deki
kritik olaylar yeni DB'ye taşınır; `data.import` izi korunan / silinen sayıyı yazar (`import_rows` dönüşü izin `detail`ine `**n` ile girer).

Ölçülen önce (HEAD `5bc99be1`): `import_rows(replace=True)` `session_events`in TAMAMINI siliyordu → yedekten sonraki ACİL DURDUR izi
geri yüklemeyle kayboluyordu (A-07: kritik olaylar süresiz saklanır). Kritik küme `thdb_seans.KRITIK_OLAY_ONEMLERI` / `KRITIK_OLAY_TURLERI`
(D2.50 saklama kuralıyla AYNI tek kaynak).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def tdb(temp_app_data, monkeypatch):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = thdb.TreatmentHistoryDB(temp_app_data)
    try:
        yield db
    finally:
        db.close()


def _olaylar(db):
    with db._get_connection() as c:
        return {
            r[0]: (r[1], r[2], r[3])
            for r in c.execute("SELECT event_uuid, session_id, event_type, severity FROM session_events").fetchall()
        }


def _uuid(db, olay_id):
    with db._get_connection() as c:
        return c.execute("SELECT event_uuid FROM session_events WHERE id = ?", (olay_id,)).fetchone()[0]


def _seans_uuid(db, sid):
    with db._get_connection() as c:
        return c.execute("SELECT session_uuid FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]


def test_KRITIK_REPLACE_ALL_yedekten_sonraki_KRITIK_olaylari_KORUR(tdb):
    s1 = tdb.start_session(treatment_mode="Manuel", patient_name="Y131-a")
    assert _seans_uuid(tdb, s1), "aparat: seansın session_uuid'i yok — yeniden bağlama ölçülemez"
    y_info = _uuid(tdb, tdb.record_session_event(s1, "session_note", {"x": 1}, "info"))
    y_estop = _uuid(tdb, tdb.record_session_event(s1, "emergency_stop", {"neden": "yedekten once"}, "critical"))
    paket = tdb.export_rows()  # ← YEDEK (an T0)

    s2 = tdb.start_session(treatment_mode="Manuel", patient_name="Y131-b")  # yedekte YOK
    s_estop2 = _uuid(tdb, tdb.record_session_event(s2, "emergency_stop", {"neden": "yedekten sonra"}, "critical"))
    s_info2 = _uuid(tdb, tdb.record_session_event(s2, "session_note", {"x": 2}, "info"))
    s_onay = _uuid(
        tdb, tdb.record_session_event(None, "ai_proposal_approved", {"spec": 1}, "info")
    )  # önemi info, TÜRÜ kritik
    s_mandal1 = _uuid(tdb, tdb.record_session_event(s1, "estop_mandali_sifirlandi", {}, "info"))  # seansı yedekte VAR
    s_uyari = _uuid(
        tdb, tdb.record_session_event(s2, "coil_overtemp_visual", {}, "warning")
    )  # önemi kritik, türü listede yok

    sonuc = tdb.import_rows(paket, replace=True)
    sonra = _olaylar(tdb)

    korunmasi_gereken = {s_estop2, s_onay, s_mandal1, s_uyari}
    eksik = korunmasi_gereken - set(sonra)
    assert not eksik, (
        f"REPLACE_ALL yedekten SONRAKİ kritik olayları SİLDİ (Y131): {len(eksik)} / {len(korunmasi_gereken)}"
    )
    assert s_info2 not in sonra, "kritik OLMAYAN olay da korundu (REPLACE_ALL kritik olmayanı yedeğe göre değiştirmeli)"
    assert y_info in sonra and y_estop in sonra, "yedekteki olaylar geri yüklenmedi"
    assert list(sonra).count(y_estop) == 1

    # İlişki: seansı yedekte olan (aynı session_uuid) korunan olay YENİ seans kimliğine bağlanır; yedekte olmayan seansın olayı seanssız kalır.
    with tdb._get_connection() as c:
        yeni_s1 = c.execute(
            "SELECT id FROM treatment_sessions WHERE session_uuid = ?",
            (paket["treatment_sessions"][0]["session_uuid"],),
        ).fetchone()[0]
    assert sonra[s_mandal1][0] == yeni_s1, (sonra[s_mandal1], yeni_s1)
    assert sonra[s_estop2][0] is None and sonra[s_uyari][0] is None

    # Sayaçlar (izin `detail`ine `**n` ile girer): 4 korundu, yedekteki ACİL DURDUR çiftlenmedi, kritik olmayan 1 olay silindi.
    assert sonuc["kritik_olay_korunan"] == 4, sonuc
    assert sonuc["kritik_olay_yedekte_vardi"] == 1, sonuc
    assert sonuc["olay_silinen"] == 2, sonuc  # y_info + s_info2 (yedekteki y_info geri yüklendi)


def test_KARSIT_ekleme_kipinde_KORUMA_adimi_KOSMAZ(tdb):
    """replace=False (boş cihaz) silme yapmaz → koruma sayacı 0; olaylar çoğalmaz (yalnız yedeğinkiler eklenir)."""
    s1 = tdb.start_session(treatment_mode="Manuel", patient_name="Y131-c")
    tdb.record_session_event(s1, "emergency_stop", {}, "critical")
    paket = tdb.export_rows()
    sonuc = tdb.import_rows(paket, replace=False)
    assert sonuc["kritik_olay_korunan"] == 0 and sonuc["olay_silinen"] == 0, sonuc
