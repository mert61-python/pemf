# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CİHAZ TAŞIMA + KVKK SİLME — API kapıları (2026-08-08).

Bu testler UÇ NOKTA davranışını kilitler; veri katmanı ayrıca `test_data_export.py` ve
`test_ai_log_delete.py`'de test edilir. Buradaki asıl risk KAPILAR:
  * onaysız toplu silme (yanlış tık → tüm geçmiş gider),
  * dolu bir cihaza sessiz geri yükleme (klinik geçmişi çoğalır/karışır),
  * yanlış parolanın sessizce "başarılı" görünmesi.
"""

import base64
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest

# ⚠️ 2026-08-09 (Tier 1): yedek parolası asgari politikaya tabi (>=12 karakter, tekrar değil) —
# bu dosya İŞLEVİ test eder, politikayı değil (o `tests/test_data_export.py`de).
PAROLA = "klinik-yedek-2026"
PAROLA2 = "baska-bir-parola-2026"
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """⚠️ 2026-08-09: dışa/içe aktarma ve silme uçları AYRICALIKLI (loopback veya geçerli token) —
    LAN muafiyeti kaldırıldı. TestClient'ın varsayılan `testclient` host'u IP bile değil, fail-closed
    reddedilir. Bu dosya İŞLEVİ test eder; erişim kapısı `test_privileged_endpoints.py`'de."""
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51234))


def _analiz_ekle(client, ad="Minnos") -> int:
    r = client.post(
        "/api/ai/log",
        json={
            "patient_name": ad,
            "module": "Hastalık",
            "module_id": "disease",
            "summary": "ozet",
            "mode": "veterinarian",
            "input_type": "clinical",
            "result_detail": {"top": "X"},
            "confidence": 0.8,
        },
    )
    assert r.status_code == 200, r.text[:200]
    return int(r.json()["id"])


# ── KVKK silme kapıları ──────────────────────────────────────────────────────


def test_KRITIK_onaysiz_toplu_silme_REDDEDILIR(client):
    _analiz_ekle(client)
    r = client.post("/api/ai/log/delete_all", json={})
    assert r.status_code == 400, "onaysiz toplu silme gecti — yanlis tik tum gecmisi silerdi"
    assert client.get("/api/ai/log?limit=5").json()["data"], "kayit silinmis olmamali"


def test_yanlis_onay_metni_REDDEDILIR(client):
    r = client.post("/api/ai/log/delete_all", json={"confirm": "evet"})
    assert r.status_code == 400


def test_tekil_silme_calisir(client):
    i = _analiz_ekle(client, "SilinecekHasta")
    r = client.post("/api/ai/log/delete", json={"id": i})
    assert r.status_code == 200 and r.json()["deleted"] == 1
    kalan = [x["id"] for x in client.get("/api/ai/log?limit=50").json()["data"]]
    assert i not in kalan


def test_olmayan_kaydi_silmek_404(client):
    r = client.post("/api/ai/log/delete", json={"id": 99999999})
    assert r.status_code == 404


def test_onayli_toplu_silme_calisir(client):
    """⚠️ 2026-08-09: klinik-geneli silme artık `all_operators: true` ile AÇIKÇA istenir.
    Eski hâli yalnız `confirm` gönderiyordu ve boş `operator_email` "hepsini sil" sayılıyordu —
    yani istemcideki bir kimlik kaybı sessizce kliniğin tüm AI geçmişini siliyordu. Kapsam
    kapısının kendisi `tests/test_ai_log_delete_scope.py`'de test edilir."""
    _analiz_ekle(client)
    r = client.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})
    assert r.status_code == 200
    assert client.get("/api/ai/log?limit=5").json()["data"] == []


# ── cihaz taşıma kapıları ────────────────────────────────────────────────────


def test_disa_aktarma_parolasiz_REDDEDILIR(client):
    r = client.post("/api/data/export", json={"passphrase": "  "})
    assert r.status_code == 400, "sifresiz tibbi veri dosyasi uretildi"


def test_KRITIK_KISA_parola_REDDEDILIR(client):
    """⚠️ 2026-08-09 (Tier 1): eskiden tek kural "boş olmasın"dı — tek karakterlik parola kabul
    ediliyordu. Bu dosya kliniğin TÜM hasta geçmişini taşır ve kopyası off-site'a gider."""
    r = client.post("/api/data/export", json={"passphrase": "kisa"})
    assert r.status_code == 400, "kisa parolayla tibbi veri dosyasi uretildi"


def test_disa_aktarilan_dosya_SIFRELI(client):
    _analiz_ekle(client, "GizliHasta")
    r = client.post("/api/data/export", json={"passphrase": PAROLA})
    assert r.status_code == 200
    blob = base64.b64decode(r.json()["data_b64"])
    assert blob.startswith(b"PEMFDATA1")
    assert b"GizliHasta" not in blob, "hasta adi dosyada duz metin"


def test_KRITIK_dolu_cihaza_onaysiz_geri_yukleme_409(client):
    _analiz_ekle(client, "MevcutHasta")
    blob = base64.b64decode(client.post("/api/data/export", json={"passphrase": PAROLA}).json()["data_b64"])
    r = client.post("/api/data/import", json={"passphrase": PAROLA, "blob_b64": base64.b64encode(blob).decode()})
    assert r.status_code == 409, "dolu cihaza sessiz geri yukleme — klinik gecmisi cogalirdi"
    assert "REPLACE_ALL" in r.json()["detail"]


def test_yanlis_parola_400_ve_ANLASILIR(client):
    blob = base64.b64decode(client.post("/api/data/export", json={"passphrase": PAROLA}).json()["data_b64"])
    r = client.post(
        "/api/data/import",
        json={"passphrase": PAROLA2, "blob_b64": base64.b64encode(blob).decode(), "confirm": "REPLACE_ALL"},
    )
    assert r.status_code == 400
    assert "Parola" in r.json()["detail"]


def test_bozuk_dosya_400(client):
    r = client.post(
        "/api/data/import",
        json={"passphrase": PAROLA, "blob_b64": base64.b64encode(b"cop").decode(), "confirm": "REPLACE_ALL"},
    )
    assert r.status_code == 400


def test_gecersiz_base64_400(client):
    r = client.post("/api/data/import", json={"passphrase": PAROLA, "blob_b64": "!!!bu-base64-degil!!!"})
    assert r.status_code == 400
