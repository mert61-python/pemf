# -*- coding: utf-8 -*-
"""D2.59 (B-3.83) — (uykudaki) SessionManager'ın yaşam döngüsü yükü hasta/operatör adını `_redact_pii`'den geçirir; anonimleştirme
`session_events` ve outbox yüklerine de ulaşır (outbox SİLİNMEZ).

ÖLÇÜLEN KUSUR: `SessionManager.start_session` `session_events` ve `outbox_messages` yüküne hasta ve operatör adını HAM yazıyordu — tedavi
satırı aynı adı `_redact_pii`'den geçirirken (opt-in `PEMF_MASK_HISTORY_PII=1`, şifresiz DB) yük maskelenmiyordu. Seans hastaya da
BAĞLANMIYORDU (`patient_id` yok) → 5 yıl inaktif hastanın anonimleştirmesi (`anonymize_patients_by_uuid`) bu seanslara, olay ve outbox
yüklerine hiç ulaşamıyordu: ad süresiz kalırdı. Bugün üründe çağıranı yok (uykuda); yeniden bağlanırsa kusur canlanır.

⚠️ Sözleşmeler (geri eklenmeyecekler / sahip kararları): maskeleme OPT-IN kalır — bayrak yokken yükte gerçek ad DURUR (KARŞIT kol);
outbox SİLİNMEZ (karar #21/#28 drain-only) — yalnız yükteki ad anonimleşir; A-27 — HEKİM ATFI (operatör adı) anonimleştirmede KALIR.
"""

from __future__ import annotations

import json

import pytest

HASTA = "Pamuk Yasam-8842"
HEKIM = "Dr Hekim-8842"
KIMLIK = "uuid-sm-8842"


@pytest.fixture
def sm(tmp_path, monkeypatch):
    from database import session_manager as smod
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(smod, "get_treatment_db", lambda *_a, **_k: db)
    try:
        yield smod.SessionManager(tmp_path), db
    finally:
        db.close_connections()


def _seans(m) -> int:
    sid = m.start_session("Manuel", operator_name=HEKIM, patient_name=HASTA, patient_uuid=KIMLIK)
    assert sid, "aparat: seans açılmadı"
    assert m.end_session(actual_duration=5.0)
    return int(sid)


def _yukler(db, sid: int) -> list:
    with db._get_connection() as c:
        olay = [r[0] for r in c.execute("SELECT payload FROM session_events WHERE session_id=?", (sid,)).fetchall()]
        kutu = [
            r[0]
            for r in c.execute("SELECT payload FROM outbox_messages WHERE correlation_id=?", (str(sid),)).fetchall()
        ]
    assert len(olay) == 2 and len(kutu) == 2, (
        f"aparat: başlama + bitiş yükü beklenir (olay {len(olay)}, outbox {len(kutu)})"
    )
    return olay + kutu


def _tum_tablolarda(db, metin: str) -> list:
    kac = json.dumps(metin)[1:-1]  # ensure_ascii kaçışlı biçim (sızıntı denetimi json.dumps'ta kör kalmasın)
    bulunan = []
    with db._get_connection() as c:
        tablolar = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for t in tablolar:
            imlec = c.execute(f'SELECT * FROM "{t}"')
            kolonlar = [k[0] for k in imlec.description]
            for satir in imlec.fetchall():
                for kol, deger in zip(kolonlar, tuple(satir)):
                    if isinstance(deger, str) and (metin in deger or kac in deger):
                        bulunan.append(f"{t}.{kol}")
    return sorted(set(bulunan))


def test_KRITIK_maske_ACIKken_olay_ve_outbox_yukunde_HAM_ad_YOK(sm, monkeypatch):
    """MUTASYON: yaşam döngüsü yükü yeniden ham `patient_name` / `operator_name` ile kurulur → KIRMIZI."""
    m, db = sm
    monkeypatch.setenv("PEMF_MASK_HISTORY_PII", "1")
    sid = _seans(m)
    for yuk in _yukler(db, sid):
        assert HASTA not in yuk and HEKIM not in yuk, f"opt-in maske AÇIKKEN yaşam döngüsü yükü ham ad taşıyor: {yuk}"


def test_KARSIT_maske_KAPALIyken_yukte_gercek_ad_DURUR(sm):
    """Opt-in sözleşmesi (Ö.4 — varsayılan-açık maske geri eklenmez): bayrak yokken yükte gerçek ad yazılır."""
    m, db = sm
    sid = _seans(m)
    baslama = json.loads(_yukler(db, sid)[0])
    assert (baslama["patient_name"], baslama["operator_name"]) == (HASTA, HEKIM), baslama


def test_KRITIK_anonimlestirme_olay_ve_outbox_yuklerine_ULASIR_outbox_SILINMEZ_hekim_atfi_KALIR(sm):
    """MUTASYON: anonimleştirmeden yük temizliği silinir / seans hastaya bağlanmaz / outbox satırı silinir → KIRMIZI."""
    m, db = sm
    sid = _seans(m)
    assert "session_events.payload" in _tum_tablolarda(db, HASTA), "aparat: ad yüke yazılmadı (kapı kör)"
    with db._get_connection() as c:
        kutu_once = c.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0]
    db.anonymize_patients_by_uuid([KIMLIK])
    assert _tum_tablolarda(db, HASTA) == [], f"anonimleştirmeden sonra hasta adı duruyor: {_tum_tablolarda(db, HASTA)}"
    with db._get_connection() as c:
        kutu_sonra = c.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0]
    assert kutu_sonra == kutu_once == 2, f"outbox SİLİNMEZ (drain-only): önce {kutu_once}, sonra {kutu_sonra}"
    baslama = json.loads(_yukler(db, sid)[0])
    assert baslama["patient_name"] == "[ANONIM]", baslama
    assert baslama["operator_name"] == HEKIM, f"A-27: hekim atfı anonimleştirmede KALMALI: {baslama}"


def test_KARSIT_baska_hastanin_yukune_DOKUNULMAZ(sm):
    m, db = sm
    _seans(m)
    diger = m.start_session(
        "Manuel", operator_name=HEKIM, patient_name="Boncuk Diger-8842", patient_uuid="uuid-diger-8842"
    )
    m.end_session(actual_duration=5.0)
    db.anonymize_patients_by_uuid([KIMLIK])
    assert "Boncuk Diger-8842" in json.loads(_yukler(db, int(diger))[0])["patient_name"]
