# -*- coding: utf-8 -*-
"""KP (Y236 · kapsam) — `database/thdb_outbox.py` outbox YAŞAM DÖNGÜSÜ (enqueue → in_flight → failed / dead → requeue → sent → budama).

Outbox "drain-only" ve bugün üretimde enqueue çağıranı yok (D6.60) ama MEKANİZMA SİLİNMEZ (sahip kararı) — o hâlde davranışı da
kilitli olmalı: bu dosyadan önce `enqueue` dışındaki geçişlerin hiçbiri hiçbir testte koşmuyordu (%34). GERÇEK: TreatmentHistoryDB (tmp).
Hata kolları: bağlantı en alt katta (`_get_connection`) düşürülür → her metot güvenli varsayılana döner, istisna yukarı SIZMAZ.
"""

from __future__ import annotations

import time

import pytest

SAAT = 3600.0


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    for ad in ("PEMF_RETAIN_PII_DAYS", "PEMF_MASK_HISTORY_PII", "PEMF_RETAIN_EVENT_DAYS", "PEMF_RETAIN_SENSOR_DAYS"):
        monkeypatch.delenv(ad, raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def _satir(db, mid):
    with db._get_connection() as c:
        return dict(c.execute("SELECT * FROM outbox_messages WHERE id = ?", (mid,)).fetchone())


def test_KRITIK_yasam_dongusu_pending_inflight_failed_dead_sent(db):
    a = db.enqueue_outbox_message("pemf/a", '{"x":1}', qos=1, retain=True, source="t", correlation_id="k1")
    b = db.enqueue_outbox_message("pemf/b", "{}")
    gelecek = db.enqueue_outbox_message("pemf/c", "{}", available_at=time.time() + SAAT)
    bekleyen = db.get_pending_outbox_messages()
    assert [m["id"] for m in bekleyen] == [a, b], "gelecekte hazır olan ileti erken verildi ya da sıra bozuk"
    assert bekleyen[0]["qos"] == 1 and bekleyen[0]["retain"] == 1 and bekleyen[0]["correlation_id"] == "k1"
    assert db.get_pending_outbox_messages(limit=1)[0]["id"] == a
    assert db.get_pending_outbox_count() == 3

    db.mark_outbox_inflight([a])
    assert _satir(db, a)["status"] == "in_flight" and [m["id"] for m in db.get_pending_outbox_messages()] == [b]
    db.mark_outbox_inflight([a])  # yalnız pending → in_flight; tekrar çağrı durumu bozmaz
    assert _satir(db, a)["status"] == "in_flight"

    once = time.time()
    assert db.mark_outbox_failed(a, "ag yok", retry_count=3, max_retry_count=5) is False
    s = _satir(db, a)
    assert (s["status"], s["retry_count"], s["last_error"]) == ("pending", 3, "ag yok")
    assert s["available_at"] >= once + 8 - 1, "geri çekilme 2^3 sn uygulanmadı"
    assert db.mark_outbox_failed(a, "son", retry_count=5, max_retry_count=5) is True
    assert _satir(db, a)["status"] == "dead"

    db.mark_outbox_sent([b])
    s = _satir(db, b)
    assert s["status"] == "sent" and s["sent_at"] and s["last_error"] is None
    assert db.get_outbox_status_counts() == {"pending": 1, "in_flight": 0, "sent": 1, "dead": 1}
    assert db.get_pending_outbox_count() == 1 and gelecek


def test_bos_liste_ile_isaretleme_HICBIR_sey_yapmaz(db):
    m = db.enqueue_outbox_message("pemf/a", "{}")
    db.mark_outbox_sent([])
    db.mark_outbox_inflight([])
    assert _satir(db, m)["status"] == "pending"


def test_KRITIK_idempotency_anahtari_AYNI_kaydi_doner_konuyla_birlikte_ayrisir(db):
    ilk = db.enqueue_outbox_message("pemf/a", "{}", idempotency_key="seans-1-bitti")
    assert db.enqueue_outbox_message("pemf/a", "{}", idempotency_key="seans-1-bitti") == ilk, (
        "aynı ileti iki kez kuyruğa girdi"
    )
    assert db.get_pending_outbox_count() == 1
    baska = db.enqueue_outbox_message("pemf/b", "{}", idempotency_key="seans-1-bitti")
    assert baska and baska != ilk, "anahtar konudan bağımsız → farklı konudaki ileti yutuldu"
    anahtar = _satir(db, ilk)["idempotency_key"]
    assert anahtar != "seans-1-bitti" and len(anahtar) == 64, "anahtar ham saklanıyor (sha256 türetilmeli)"


def test_bayat_in_flight_yeniden_kuyruga_alinir_tazesi_alinmaz(db):
    eski, taze = db.enqueue_outbox_message("pemf/a", "{}"), db.enqueue_outbox_message("pemf/b", "{}")
    db.mark_outbox_inflight([eski, taze])
    with db._get_connection() as c:
        c.execute("UPDATE outbox_messages SET available_at = ? WHERE id = ?", (time.time() - 600, eski))
        c.commit()
    assert db.requeue_stale_inflight(stale_seconds=120) == 1
    s = _satir(db, eski)
    assert s["status"] == "pending" and s["last_error"] == "requeued stale in_flight"
    assert _satir(db, taze)["status"] == "in_flight"
    assert db.requeue_stale_inflight(stale_seconds=0) >= 0  # 0 → en az 1 sn (max(1, …)); hata vermez


def test_eski_sent_ve_olu_kayitlar_budanir_digerleri_kalir(db):
    eski, yeni, olu = (db.enqueue_outbox_message(f"pemf/{i}", "{}") for i in range(3))
    db.mark_outbox_sent([eski, yeni])
    with db._get_connection() as c:
        c.execute("UPDATE outbox_messages SET sent_at = ? WHERE id = ?", (time.time() - 100 * SAAT, eski))
        c.execute(
            "UPDATE outbox_messages SET status = 'dead', available_at = ? WHERE id = ?",
            (time.time() - 40 * 24 * SAAT, olu),
        )
        c.commit()
    db.purge_sent_outbox(older_than_hours=72)
    assert db.get_outbox_status_counts()["sent"] == 1 and _satir(db, yeni)["status"] == "sent"
    assert db.purge_old_dead_outbox(retain_days=30) == 1
    assert db.get_outbox_status_counts()["dead"] == 0


def test_bekleyenleri_temizle_yalniz_pending_ve_in_flight_siler(db):
    p, i, s = (db.enqueue_outbox_message(f"pemf/{n}", "{}") for n in range(3))
    db.mark_outbox_inflight([i])
    db.mark_outbox_sent([s])
    db.clear_pending_outbox()
    assert db.get_outbox_status_counts() == {"pending": 0, "in_flight": 0, "sent": 1, "dead": 0}
    assert p and i


def test_KRITIK_baglanti_DUSERSE_her_metot_guvenli_varsayilana_doner(db, monkeypatch, caplog):
    m = db.enqueue_outbox_message("pemf/a", "{}")

    def _dus():
        raise OSError("disk yok")

    monkeypatch.setattr(db, "_get_connection", _dus)
    assert db.enqueue_outbox_message("pemf/a", "{}") is None
    assert db.get_pending_outbox_messages() == []
    db.mark_outbox_sent([m])
    db.mark_outbox_inflight([m])
    assert db.mark_outbox_failed(m, "x", 1) is False
    assert db.requeue_stale_inflight() == 0
    assert db.get_pending_outbox_count() == 0
    assert db.get_outbox_status_counts() == {"pending": 0, "in_flight": 0, "sent": 0, "dead": 0}
    db.purge_sent_outbox()
    assert db.purge_old_dead_outbox(30) == 0
    db.clear_pending_outbox()
    mesajlar = " ".join(r.getMessage() for r in caplog.records)
    for parca in (
        "Outbox enqueue hatası",
        "Pending outbox okuma hatası",
        "Outbox sent işaretleme hatası",
        "Outbox in_flight işaretleme hatası",
        "Outbox failed işaretleme hatası",
        "Stale in_flight requeue uyarısı",
        "Outbox temizleme uyarısı",
        "Dead outbox retention temizleme uyarısı",
        "Pending outbox temizleme uyarısı",
    ):
        assert parca in mesajlar, f"hata kolu günlüğe yazmadı: {parca}"


def test_idempotency_cakismasinda_ikinci_okuma_da_duserse_None(db, monkeypatch):
    db.enqueue_outbox_message("pemf/a", "{}", idempotency_key="k")
    gercek = db._get_connection
    sayac = {"n": 0}

    def _ikincide_dus():
        sayac["n"] += 1
        if sayac["n"] >= 2:
            raise OSError("okuma düştü")
        return gercek()

    monkeypatch.setattr(db, "_get_connection", _ikincide_dus)
    assert db.enqueue_outbox_message("pemf/a", "{}", idempotency_key="k") is None
    monkeypatch.setattr(db, "_get_connection", gercek)
    from database.db_hatalari import _DB_INTEGRITY

    hata = _DB_INTEGRITY[0] if isinstance(_DB_INTEGRITY, tuple) else _DB_INTEGRITY

    def _butunluk():
        raise hata("UNIQUE")

    monkeypatch.setattr(db, "_get_connection", _butunluk)
    assert db.enqueue_outbox_message("pemf/a", "{}") is None, (
        "anahtarsız bütünlük hatası None dönmeli (tekrar ekleme yok)"
    )
