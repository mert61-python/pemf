# -*- coding: utf-8 -*-
"""F2-2.3 (2-F incelemesi A2) — Y13 / D2.29 / S-F.3 ilkesi ÖTEKİ silme ve değiştirme yollarında: şifresiz kurulumda silinen ya da
anonimleştirilen / maskelenen metin işlemden SONRA `.db` + `-wal` HAM BAYTLARINDA kalmaz.

ÖLÇÜLEN (sonda `_inceleme/K2/sonda_silme_kalintisi.py`): D2.29 (tekil AI silme) ve S-F.3 (AI toplu silme) işlemden hemen sonra 0; ama
seans tekil / toplu silme, KVKK anonimleştirme (A-06 — "geri dönüşsüz"), PII maskeleme, olay saklama silmesi ve REPLACE_ALL içe aktarma
sonrası SQL'de 0 (canlı yok) iken ana dosyada 1-7 kopya duruyor; 50 küçük yazımdan sonra da duruyor, ancak ~1500 yazım (oto denetim
noktası, 1000 sayfa) sonra gidiyor — sakin klinikte günler/haftalar. `secure_delete` yeni sayfa sürümünü sıfırlar ama WAL kipinde ESKİ
sayfa denetim noktasına kadar ana dosyada kalır (2-F'nin kendi dersi; §5 açık #4 yalnız seans silmeyi anmıştı).
Ölçüm: belirteç işlemden ÖNCE dosyada VAR (pozitif kontrol: araç görüyor) ve SQL'de canlı; işlemden sonra SQL'de canlı 0 → ham bayt 0
olmalı. Veri "eskiden yazılmış" (denetim noktası ile ana dosyada) — sahadaki gibi.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

AD = "Pamuk Sonda-7731"
SAHIP = "Sahip Sonda-7731"
NOT_ = "Gizli not Sonda-7731"
EPOSTA = "s7731@ornek.com"
OLAY = "Olay-yuku-7731"


def _varyant(m):
    return {x.encode("utf-8") for x in (m, m.upper(), m.lower(), json.dumps(m)[1:-1])}


def _bayt(db, belirtecler) -> int:
    n = 0
    for ek in ("", "-wal"):
        f = Path(str(db.db_path) + ek)
        if f.exists():
            b = f.read_bytes()
            n += sum(b.count(v) for m in belirtecler for v in _varyant(m))
    return n


def _canli(db, belirtecler) -> int:
    n = 0
    with db._get_connection() as c:
        for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for satir in c.execute(f'SELECT * FROM "{t}"').fetchall():
                n += sum(
                    1 for v in tuple(satir) if isinstance(v, str) and any(m.lower() in v.lower() for m in belirtecler)
                )
    return n


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    db = TreatmentHistoryDB(tmp_path / "gecmis")
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    try:
        yield type("O", (), {"db": db, "pdb": pdb})
    finally:
        db.close_connections()


def _seans(db, eski_gun=0, pid=None):
    hp = db.upsert_patient({"name": AD, "patient_uuid": pid, "owner_name": SAHIP})
    sid = int(db.start_session(treatment_mode="Manuel", patient_name=AD, operator_name="Dr Hekim"))
    db.set_session_meta(sid, patient_id=hp)
    db.set_session_parameter(sid, "patient_owner_email", EPOSTA, "")
    db.record_session_event(sid, "bilgi", payload={"patient_name": AD, "not": OLAY}, severity="info")
    db.end_session(sid, patient_notes=NOT_, duration_minutes=5)
    if eski_gun:
        eski = datetime.now() - timedelta(days=eski_gun)
        with db._get_connection() as c:
            c.execute("UPDATE treatment_sessions SET session_date=? WHERE id=?", (eski.strftime("%Y-%m-%d"), sid))
            c.execute("UPDATE session_events SET created_at=? WHERE session_id=?", (eski.timestamp(), sid))
            c.commit()
    return sid


def _anonim_kur(o):
    from services import kvkk_anonimlestirme as kv

    pid = o.pdb.add_patient({"name": AD, "owner": SAHIP, "owner_email": EPOSTA})
    with o.pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=2200)).isoformat(), pid),
        )
        c.commit()
    _seans(o.db, pid=pid)
    o.db.add_ai_analysis(module_id="kalca", patient_name=AD, result_summary=f"{AD} kalca bulgusu", patient_uuid=pid)
    o.db.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim="")


def _anonim(o):
    from services import kvkk_anonimlestirme as kv

    assert kv.tur(o.pdb, o.db)["anonimlestirilen"] == 1


YOLLAR = {
    # ad: (kurulum, işlem, belirteçler — işlemden sonra HİÇBİR yerde canlı olmaması gerekenler)
    "seans_tekil_silme": (
        lambda o: setattr(o, "sid", _seans(o.db)),
        lambda o: o.db.delete_session(o.sid),
        [NOT_, EPOSTA, OLAY],
    ),
    "seans_toplu_silme": (
        lambda o: setattr(o, "sid", _seans(o.db)),
        lambda o: o.db.delete_sessions_bulk([o.sid]),
        [NOT_, EPOSTA, OLAY],
    ),
    "kvkk_anonimlestirme": (_anonim_kur, _anonim, [AD, SAHIP]),
    "pii_maskeleme": (
        lambda o: (_seans(o.db, eski_gun=500), o.db.pii_onayla(gun=365, sayi=1, kim="")),
        lambda o: o.db.redact_old_session_pii(365),
        [NOT_, EPOSTA],
    ),
    "olay_saklama_silmesi": (
        lambda o: _seans(o.db, eski_gun=500),
        lambda o: o.db.purge_old_session_events(365),
        [OLAY],
    ),
    "replace_all_ice_aktarma": (
        lambda o: _seans(o.db),
        lambda o: o.db.import_rows({"treatment_sessions": [], "ai_analyses": []}, replace=True),
        [AD, NOT_],
    ),
}


@pytest.mark.parametrize("yol", sorted(YOLLAR))
def test_KRITIK_islemden_sonra_silinen_metin_DB_ve_WAL_baytlarinda_YOK(o, yol):
    """MUTASYON: yolun işlem sonrası denetim noktası kaldırılır → o yol KIRMIZI."""
    kur, islem, belirtecler = YOLLAR[yol]
    kur(o)
    with o.db._get_connection() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # veri eskiden yazılmış: ana dosyada
    assert _canli(o.db, belirtecler) > 0 and _bayt(o.db, belirtecler) > 0, "aparat: belirteç işlemden önce görünmüyor"
    islem(o)
    assert _canli(o.db, belirtecler) == 0, f"aparat: {yol} canlı kaydı temizlemedi"
    kalan = _bayt(o.db, belirtecler)
    assert kalan == 0, (
        f"{yol}: SQL'de silinmiş/değişmiş metin dosya baytlarında {kalan} kez KALDI (Y13; denetim noktası yok)"
    )


def test_KARSIT_D229_tekil_AI_silme_ZATEN_kalintisiz(o):
    """Araç kör değil + karşılaştırma: D2.29'un denetim noktalı yolu işlemden hemen sonra 0."""
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary=f"AI ozet {OLAY}")
    with o.db._get_connection() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert _bayt(o.db, [OLAY]) > 0
    assert o.db.delete_ai_analysis(aid)
    assert _bayt(o.db, [OLAY]) == 0
