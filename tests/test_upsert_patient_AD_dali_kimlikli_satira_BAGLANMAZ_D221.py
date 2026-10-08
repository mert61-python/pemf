# -*- coding: utf-8 -*-
"""D2.21 (B-3.65) — `upsert_patient`'in AD eşleme dalı yalnız KİMLİKSİZ (patient_uuid boş) ayna satırlarına bağlanır.

ÖLÇÜLEN KUSUR (DENETİM-03 B-3.65): kimliksiz (patient_id'siz) seans başlangıcı `upsert_patient({'name': 'Boncuk'})` ile
`name = ? AND owner_name IS NULL` dalına düşüp AYNI ADLI BAŞKA hastanın (kimlikli) ayna satırını buluyor, onu güncelliyor
(species/breed/age… NULL'lanıyor) ve seansı ona bağlıyordu → o hasta anonimleşince seans geri dönüşsüz [ANONIM], `/api/history`
başka sahibin e-postasını döndürüyordu. Erişim dar (bayat `snapshot.patient` penceresi, patient_id'siz API istemcisi).
Kapı: GERÇEK `TreatmentHistoryDB.upsert_patient` + GERÇEK `POST /api/session/start` (kimliksiz gövde). Satırlar SQL ile okunur.
"""

from __future__ import annotations

import pytest

U1 = "boncuk-kimlik-0001"


def _hasta(d, pid):
    with d._get_connection() as c:
        r = c.execute("SELECT patient_uuid, name, species, breed FROM patients WHERE id = ?", (pid,)).fetchone()
        return tuple(r) if r else None


def test_KRITIK_kimliksiz_upsert_ayni_adli_KIMLIKLI_satira_baglanmaz_alanlarini_NULLlamaz(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path / "g")
    id1 = d.upsert_patient({"name": "Boncuk", "patient_uuid": U1, "species": "Kedi", "breed": "Tekir"})
    id2 = d.upsert_patient({"name": "Boncuk"})
    assert id2 is not None and id2 != id1, "kimliksiz upsert AYNI ADLI kimlikli hastanın satırına bağlandı"
    assert _hasta(d, id1) == (U1, "Boncuk", "Kedi", "Tekir"), f"kimlikli satırın alanları ezildi: {_hasta(d, id1)}"


def test_KRITIK_sahip_adli_dal_da_KIMLIKLI_satira_baglanmaz(tmp_path):
    """Aynı kural `owner_name` verilen dalda (ad + sahip adı eşleşmesi)."""
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path / "g")
    id1 = d.upsert_patient(
        {"name": "Boncuk", "patient_uuid": U1, "owner_name": "Ali", "species": "Kedi", "breed": "Tekir"}
    )
    id2 = d.upsert_patient({"name": "Boncuk", "owner_name": "Ali"})
    assert id2 is not None and id2 != id1
    assert _hasta(d, id1) == (U1, "Boncuk", "Kedi", "Tekir")


def test_KARSIT_kimliksiz_upsert_KIMLIKSIZ_ayni_ad_satirini_yeniden_kullanir(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path / "g")
    a = d.upsert_patient({"name": "Pamuk"})
    assert d.upsert_patient({"name": "Pamuk"}) == a  # eski davranış: kimliksiz ayna tekrar kullanılır (çoğaltma yok)


def test_KARSIT_kimlikli_upsert_kimlikle_eslesir(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path / "g")
    a = d.upsert_patient({"name": "Boncuk", "patient_uuid": U1})
    assert d.upsert_patient({"name": "Boncuk (yeni ad)", "patient_uuid": U1}) == a


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = apa.kur(monkeypatch, tmp_path)
    o.lan = TestClient(o.api.app, client=("192.168.1.71", 51221), backend_options=dict(apa.ISTEMCI_SECENEKLERI))
    operator_tokens.temizle_hepsi()
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.lan.post("/api/session/stop")
    finally:
        o.geri()


def _seans_baslat(o, govde_ek: dict):
    r = o.lan.post(
        "/api/session/start",
        json={
            "coil_ids": [1],
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "duration_minutes": 5,
            "mode": "Manuel",
            **govde_ek,
        },
    )
    assert r.status_code == 200, r.text[:300]
    with o.db._get_connection() as c:
        satir = c.execute("SELECT patient_id FROM treatment_sessions ORDER BY id DESC LIMIT 1").fetchone()
    o.lan.post("/api/session/stop")
    return satir[0]


def test_KRITIK_GERCEK_uc_kimliksiz_seans_baslangici_baska_hastanin_satirina_YAZILMAZ(o):
    """A-01 LAN istemcisi (patient_id'siz eski gövde) — seans KİMLİKLİ Boncuk'un ayna satırına bağlanmamalı."""
    id1 = _seans_baslat(o, {"patient_name": "Boncuk", "patient_id": U1})
    assert _hasta(o.db, id1)[0] == U1, "ön koşul: kimlikli başlangıç kimlikli satıra bağlanmalı"
    id2 = _seans_baslat(o, {"patient_name": "Boncuk"})
    assert id2 != id1, "kimliksiz seans başka (kimlikli) hastanın satırına bağlandı"
    assert _hasta(o.db, id1)[0] == U1


def test_KARSIT_GERCEK_uc_kimlikli_seans_kendi_satirina(o):
    a = _seans_baslat(o, {"patient_name": "Boncuk", "patient_id": U1})
    assert _seans_baslat(o, {"patient_name": "Boncuk", "patient_id": U1}) == a
