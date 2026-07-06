"""audit B-8.2: history keyset (cursor) pagination — `before_id` ile sayfalar ÖRTÜŞMEZ, atlama YOK,
tüm satırları kapsar, id DESC sırada. Keyset'in offset'e üstünlüğü: sayfalar arasında yeni kayıt
girse bile sayfa kaymaz (offset'te tekrar/atlama olurdu)."""


def _db(temp_app_data):
    from database.treatment_history_db import TreatmentHistoryDB
    return TreatmentHistoryDB(temp_app_data)


def test_cursor_pagination_covers_all_without_overlap(temp_app_data):
    db = _db(temp_app_data)
    ids = [db.start_session("Manuel", patient_name=f"P{i}") for i in range(5)]
    assert ids == sorted(ids), "id'ler monoton artan olmalı (AUTOINCREMENT)"
    desc = sorted(ids, reverse=True)  # id DESC = beklenen sıra (yeni önce)

    p1 = db.get_session_history(limit=2)
    assert [r["id"] for r in p1] == desc[0:2]

    p2 = db.get_session_history(limit=2, before_id=p1[-1]["id"])
    assert [r["id"] for r in p2] == desc[2:4]

    p3 = db.get_session_history(limit=2, before_id=p2[-1]["id"])
    assert [r["id"] for r in p3] == desc[4:5]

    # Son sayfa limit'ten az → "daha fazla yok" sinyali
    assert len(p3) < 2

    seen = [r["id"] for r in p1 + p2 + p3]
    assert sorted(seen) == sorted(ids), "tüm seanslar tam olarak bir kez kapsanmalı"
    assert len(seen) == len(set(seen)), "hiçbir seans iki sayfada tekrar etmemeli"


def test_cursor_stable_when_new_row_inserted_between_pages(temp_app_data):
    """Keyset AVANTAJI: sayfa 1 ile 2 arasında yeni seans eklenirse offset (LIMIT/OFFSET) bir satırı
    kaydırıp tekrar/atlama üretirdi; cursor (id < before_id) DEĞİŞMEZ."""
    db = _db(temp_app_data)
    ids = [db.start_session("Manuel", patient_name=f"P{i}") for i in range(4)]
    desc = sorted(ids, reverse=True)

    p1 = db.get_session_history(limit=2)
    assert [r["id"] for r in p1] == desc[0:2]

    # ARAYA yeni seans gir (en yüksek id). offset=2 olsaydı sayfa 2 kayardı.
    db.start_session("Manuel", patient_name="YENI")

    p2 = db.get_session_history(limit=2, before_id=p1[-1]["id"])
    assert [r["id"] for r in p2] == desc[2:4], "yeni kayıt sayfa 2'yi kaydırmamalı (tekrar/atlama YOK)"


def test_no_cursor_returns_latest_backward_compat(temp_app_data):
    """Geriye uyumlu: cursor'suz çağrı en yeni `limit` seansı id DESC döndürür (eski istemci davranışı)."""
    db = _db(temp_app_data)
    ids = [db.start_session("Manuel", patient_name=f"P{i}") for i in range(3)]
    rows = db.get_session_history(limit=10)
    assert [r["id"] for r in rows] == sorted(ids, reverse=True)
