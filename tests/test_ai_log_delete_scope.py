# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI GEÇMİŞİ SİLME KAPSAMI — kimlik yokluğu "hepsini sil" DEĞİLDİR (2026-08-09, Tier 1).

ARIZA: `/api/ai/log/delete_all` sözleşmesi "boş `operator_email` → TÜM klinik geçmişi" idi.
Bu, kimliğin kaybolduğu HER durumu sessizce klinik-geneli silmeye çeviriyordu. Somut yol:
çoklu-operatör kipinde kimse seçilmemişse istemcinin `operatorEmail`i BİLEREK "" döner
(yanlış kişiye kayıt yazmamak için) → veteriner "kendi kayıtlarımı sil" der, kliniğin TÜM
AI geçmişi VACUUM'lanarak geri dönülemez biçimde silinir.

Kimlik YOKLUĞU ile "hepsini sil" NİYETİ artık ayrı: klinik-geneli silme `all_operators: true`
ile AÇIKÇA istenir. Yıkıcı bir işlemin varsayılanı asla "en geniş kapsam" olamaz.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app, client=("127.0.0.1", 51234))


@pytest.fixture
def dolu_gecmis(api, tmp_path, monkeypatch):
    """İki hekimin analizleri + sahipsiz bir eski kayıt."""
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(tmp_path)
    db.add_ai_analysis(module_id="m", patient_name="Pamuk", result_summary="A-analiz", operator_email="a@klinik.com")
    db.add_ai_analysis(module_id="m", patient_name="Boncuk", result_summary="B-analiz", operator_email="b@klinik.com")
    db.add_ai_analysis(module_id="m", patient_name="Eski", result_summary="sahipsiz")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    yield db
    db.close_connections()


def _ozetler(db):
    return sorted(a["result_summary"] for a in db.get_ai_analyses(limit=50))


# ── toplu silme: fail-closed ────────────────────────────────────────────────


def test_KRITIK_kimliksiz_ve_bayraksiz_toplu_silme_REDDEDILIR(client, dolu_gecmis):
    r = client.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL"})
    assert r.status_code == 400, f"kimliksiz istek TUM gecmisi sildi ({r.status_code})"
    assert "kapsam" in r.json()["detail"].lower()
    assert len(_ozetler(dolu_gecmis)) == 3, "reddedilen istek yine de sildi"


def test_KRITIK_bos_operator_email_HEPSINI_SILMEZ(client, dolu_gecmis):
    """İstemcideki kimlik kaybının tam modeli: alan var ama boş."""
    r = client.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "operator_email": "   "})
    assert r.status_code == 400
    assert len(_ozetler(dolu_gecmis)) == 3


def test_klinik_geneli_silme_ACIK_bayrakla_calisir(client, dolu_gecmis):
    r = client.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["deleted"] == 3
    assert _ozetler(dolu_gecmis) == []


def test_kendi_kayitlarini_silme_SADECE_kendisini_ve_sahipsizi_siler(client, dolu_gecmis):
    r = client.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "operator_email": "a@klinik.com"})
    assert r.status_code == 200, r.text[:300]
    kalan = _ozetler(dolu_gecmis)
    assert kalan == ["B-analiz"], f"baska hekimin kaydi etkilendi: {kalan}"


def test_confirm_kapisi_KORUNUR(client, dolu_gecmis):
    """Regresyon: `confirm` olmadan hiçbir şey silinmemeli."""
    r = client.post("/api/ai/log/delete_all", json={"all_operators": True})
    assert r.status_code == 400 and "onay" in r.json()["detail"].lower()
    assert len(_ozetler(dolu_gecmis)) == 3


def test_bayrak_kimlikle_birlikte_gelirse_KIMLIK_kazanir(client, dolu_gecmis):
    """Çelişkili istek en DAR kapsamda yorumlanmalı — yıkıcı işlemde geniş olan kazanamaz."""
    r = client.post(
        "/api/ai/log/delete_all",
        json={"confirm": "DELETE_ALL", "operator_email": "a@klinik.com", "all_operators": True},
    )
    assert r.status_code == 200, r.text[:300]
    assert _ozetler(dolu_gecmis) == ["B-analiz"], "celiskili istekte GENIS kapsam uygulandi"


# ── tekil silme: sahiplik ───────────────────────────────────────────────────


def test_KRITIK_baskasinin_kaydi_SILINEMEZ(client, dolu_gecmis):
    hedef = [a for a in dolu_gecmis.get_ai_analyses(limit=50) if a["result_summary"] == "B-analiz"][0]
    r = client.post("/api/ai/log/delete", json={"id": hedef["id"], "operator_email": "a@klinik.com"})
    assert r.status_code == 404, "baskasinin kaydi silindi"
    assert "B-analiz" in _ozetler(dolu_gecmis)


def test_kendi_kaydini_silebilir(client, dolu_gecmis):
    hedef = [a for a in dolu_gecmis.get_ai_analyses(limit=50) if a["result_summary"] == "A-analiz"][0]
    r = client.post("/api/ai/log/delete", json={"id": hedef["id"], "operator_email": "a@klinik.com"})
    assert r.status_code == 200, r.text[:300]
    assert "A-analiz" not in _ozetler(dolu_gecmis)
