# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DENETİM İZİ — geri dönüşsüz işlemler izsiz olamaz (2026-08-09 denetimi, Tier 3).

ARIZA: toplu silme, dışa/içe aktarma, operatör ekleme-çıkarma ve geri dönüşsüz PII maskelemesi
için tek iz, 60 MB'lık **dönen** bir metin log'unda **kimliksiz** tek bir satırdı. "Hasta
kayıtlarım kayboldu" denildiğinde kimin, ne zaman, nereden ve kaç kaydı sildiğini gösterecek
hiçbir şey yoktu; log dönünce o satır da yok oluyordu.

ÇÖZÜM: şifreli DB içinde **ekleme-only** `audit_events` tablosu (SQLite tetikleyicileriyle
mühürlü) + `servers/audit_log.py` üzerinden istek bağlamı (IP + KANITLANMIŞ operatör).

Kilitlenen değişmezler:
  1) İz DEĞİŞTİRİLEMEZ ve SİLİNEMEZ — "hepsini sil" bile silme kaydını silemez.
  2) Kanıtsız beyan, denetim izine o hekimin adıyla GİRMEZ (iz iftiraya dönüşemez).
  3) İz, sildiği verinin ikinci kopyası DEĞİLDİR — hasta adı/not/analiz metni yazılmaz.
  4) Denetim yazımı işlemi ENGELLEMEZ (dolu disk veteriner'i kilitlemesin).
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path)
    yield d
    d.close_connections()


# ── ekleme-only mühür ───────────────────────────────────────────────────────


def test_KRITIK_denetim_izi_DEGISTIRILEMEZ(db):
    db.denetim_yaz("test.olay", item_count=3)
    with pytest.raises(Exception) as e:
        with db._get_connection() as c:
            c.execute("UPDATE audit_events SET item_count = 0")
            c.commit()
    assert "ekleme-only" in str(e.value), f"beklenmeyen hata: {e.value}"


def test_KRITIK_denetim_izi_SILINEMEZ(db):
    db.denetim_yaz("test.olay")
    with pytest.raises(Exception) as e:
        with db._get_connection() as c:
            c.execute("DELETE FROM audit_events")
            c.commit()
    assert "ekleme-only" in str(e.value)


def test_KRITIK_saklama_politikasi_denetim_izine_DOKUNMAZ(db):
    """Saklama politikası her şeyi süpürürken izi de süpürseydi, iz bir yıl sonra yok olurdu."""
    db.denetim_yaz("test.olay")
    once = db.denetim_sayisi()
    db.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=0, dose_retain_days=0
    )
    assert db.denetim_sayisi() == once, "saklama politikasi denetim izini sildi"


# ── içerik ─────────────────────────────────────────────────────────────────


def test_kayit_ISTEK_baglamini_tasir(db):
    db.denetim_yaz("x.y", operator_email="a@k.com", client_ip="10.0.0.5", scope="hepsi", item_count=12, detail={"z": 1})
    k = db.denetim_oku(1)[0]
    assert (k["event_type"], k["operator_email"], k["client_ip"], k["scope"], k["item_count"]) == (
        "x.y",
        "a@k.com",
        "10.0.0.5",
        "hepsi",
        12,
    )
    assert k["ts_utc"] and k["app_version"], "zaman/surum kaydedilmemis"


def test_KRITIK_yazim_HATASI_cagirani_PATLATMAZ(db, monkeypatch):
    """Dolu disk / kilitli DB yüzünden veterinerin veri dışa aktaramaz hâle gelmesi, iz
    kaybından KÖTÜDÜR. Yazamama sessiz değildir (ERROR log) ama istisna da atmaz."""
    monkeypatch.setattr(db, "_get_connection", lambda: (_ for _ in ()).throw(RuntimeError("disk dolu")))
    assert db.denetim_yaz("x.y") is False


def test_detail_asiri_buyukse_KIRPILIR(db):
    db.denetim_yaz("x.y", detail={"buyuk": "A" * 20000})
    assert len(db.denetim_oku(1)[0]["detail"]) <= 4000


# ── HTTP: uçlar gerçekten yazıyor mu ────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch, db):
    from servers import api_server

    monkeypatch.setattr(api_server, "_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: db)
    from database import treatment_history_db as thm

    monkeypatch.setattr(thm, "get_treatment_db", lambda _d: db)
    return TestClient(api_server.app, client=("127.0.0.1", 51234))


def _turler(db):
    return [k["event_type"] for k in db.denetim_oku(50)]


def test_KRITIK_AI_toplu_silme_IZ_birakir(client, db):
    r = client.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})
    assert r.status_code == 200, r.text[:200]
    assert "ai_log.delete_all" in _turler(db), "toplu silme izsiz gecti"


def test_KRITIK_toplu_silme_KENDI_izini_silemez(client, db):
    """En kritik değişmez: "hepsini sil" komutu, silmenin olduğunu gösteren kaydı silerse
    denetim izinin hiçbir anlamı kalmaz."""
    client.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})
    client.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})
    assert _turler(db).count("ai_log.delete_all") == 2, "silme kendi izini de sildi"


def test_REDDEDILEN_silme_de_iz_birakir(client, db):
    """Başkasının kaydını silmeye çalışmak, başarılı silme kadar önemli bir sinyaldir."""
    r = client.post("/api/ai/log/delete", json={"id": 999999, "operator_email": "x@k.com"})
    assert r.status_code == 404
    k = [e for e in db.denetim_oku(20) if e["event_type"] == "ai_log.delete"]
    assert k and k[0]["outcome"] == "reddedildi", "reddedilen silme izsiz gecti"


def test_saklama_ONAYI_iz_birakir(client, db):
    assert client.post("/api/settings/retention", json={"acknowledge": True}).status_code == 200
    assert "retention.onay" in _turler(db), "geri donussuz maskeleme onayi izsiz"


def test_KRITIK_kanitsiz_beyan_HEKIMI_TAKLIT_EDEMEZ(client, db):
    """İz, kanıtlanmamış bir beyanı o hekimin adına yazarsa delil olmaktan çıkar ve iftira
    aracına döner. Kayıtlı bir hekimi beyan eden jetonsuz istek SAHİPSİZ yazılmalı; beyan
    yalnız `detail` içinde saklanır."""
    from servers import operator_tokens

    operator_tokens.temizle_hepsi()
    e = "gercek@klinik.com"
    assert (
        client.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"}).status_code == 200
    )

    client.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "operator_email": e})
    kayit = next(k for k in db.denetim_oku(50) if k["event_type"] == "ai_log.delete_all")
    assert kayit["operator_email"] != e, "kanitsiz beyan denetim izine hekim adiyla girdi"
    assert e in (kayit["detail"] or ""), "kanitsiz beyan hic kaydedilmemis (sinyal kayboldu)"
    operator_tokens.temizle_hepsi()


def test_operator_ekleme_cikarma_IZ_birakir(client, db):
    from servers import operator_tokens

    operator_tokens.temizle_hepsi()
    e = "yeni@klinik.com"
    client.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "654321"})
    client.post("/api/operators/remove", json={"email": e})
    t = _turler(db)
    assert "operator.enroll" in t and "operator.remove" in t
    operator_tokens.temizle_hepsi()


# ── okuma ucu ───────────────────────────────────────────────────────────────


def test_okuma_ucu_calisir(client, db):
    db.denetim_yaz("x.y", item_count=1)
    r = client.get("/api/audit/events?limit=5")
    assert r.status_code == 200, r.text[:200]
    g = r.json()
    assert g["total"] >= 1 and g["events"], g


def test_okuma_ucu_TURE_gore_suzer(client, db):
    db.denetim_yaz("a.a")
    db.denetim_yaz("b.b")
    g = client.get("/api/audit/events?event_type=b.b").json()
    assert {e["event_type"] for e in g["events"]} == {"b.b"}


def test_KRITIK_okuma_ucu_LANdan_kimliksiz_REDDEDILIR():
    """İz kimin ne sildiğini gösterir — klinik ağındaki rastgele bir cihaz okuyamamalı."""
    from servers import api_server

    lan = TestClient(api_server.app, client=("192.168.1.77", 51234))
    assert lan.get("/api/audit/events").status_code == 403


def test_okuma_ucu_limit_TAVANLI(client, db):
    assert client.get("/api/audit/events?limit=999999").status_code == 200
