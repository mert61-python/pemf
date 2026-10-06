# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""HASTA KISMİ GÜNCELLEME (field-merge) — eşzamanlılık denetimi 2026-08-30.

`update_patient` YALNIZ `patient_info`'da gelen alanları yazar; gönderilmeyen alanı KORUR. Bu,
backend'in lost-update'e karşı tek yapısal savunmasıdır (saha 4.3: "diğer alanlar kaybolmaz").

⚠️ NEDEN KRİTİK: frontend hasta düzenlemede TÜM formu gönderiyor (`apps/ui/src/screens/PatientScreen`
→ `payload = {...normalized, id}`). İki cihaz aynı hastayı açıp farklı alan değiştirirse, birinin
formundaki BAYAT değer diğerinin yeni değerini ezebilir. Backend field-merge, EN AZINDAN
gönderilmeyen alanı korur; eğer biri bunu "her alanı her zaman yaz" (full-row replace) yaparsa
lost-update KESİNLEŞİR. Bu kapı o değişmezi kilitler.

⚠️ Bu test GERÇEK PatientDatabase ile çalışır; izole tmp DB, klinik verisine dokunmaz.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def hasta_db(temp_app_data, monkeypatch):
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    return pdb.PatientDatabase(str(temp_app_data / "patients.db"))


def _hasta(db, pid):
    for p in db.get_all_patients():
        if p.get("id") == pid:
            return p
    return None


def test_KRITIK_gonderilmeyen_alan_KORUNUR(hasta_db):
    """⚠️ LOST-UPDATE SAVUNMASI: yalnız 'owner' güncellenirse 'name' AYNEN kalmalı.

    Full-row replace olsaydı, gönderilmeyen 'name' NULL/boş olur → hasta kimliği kaybolur."""
    pid = hasta_db.add_patient({"name": "Boncuk", "owner": "Ali", "species": "Kedi", "breed": "Tekir"})

    # Yalnız owner değiştir — name/species/breed GÖNDERİLMİYOR
    assert hasta_db.update_patient(pid, {"owner": "Veli"}) is True

    p = _hasta(hasta_db, pid)
    assert p["owner"] == "Veli", "owner güncellenmedi"
    assert p["name"] == "Boncuk", "gönderilmeyen 'name' KAYBOLDU → full-row replace (lost-update)"
    assert p["species"] == "Kedi", "gönderilmeyen 'species' kayboldu"
    assert p["breed"] == "Tekir", "gönderilmeyen 'breed' kayboldu"


def test_KRITIK_iki_ardisik_FARKLI_alan_ikisi_de_kalir(hasta_db):
    """Saha 4.3 çekirdeği: iki güncelleme farklı alanları değiştirir → İKİSİ de korunmalı.

    (Backend `with self.lock` ile serialize eder; bu test mantıksal sonucu — birinin diğerini
    ezmemesi — doğrular.)"""
    pid = hasta_db.add_patient({"name": "Boncuk", "owner": "Ali", "species": "Kedi"})

    hasta_db.update_patient(pid, {"name": "Pamuk"})  # cihaz A: adı değiştirir
    hasta_db.update_patient(pid, {"owner": "Veli"})  # cihaz B: sahibi değiştirir

    p = _hasta(hasta_db, pid)
    assert p["name"] == "Pamuk", "A'nın ad değişikliği kayboldu"
    assert p["owner"] == "Veli", "B'nin sahip değişikliği kayboldu"
    assert p["species"] == "Kedi", "dokunulmayan alan bozuldu"


def test_bos_deger_GERCEK_temizleme(hasta_db):
    """Karşıt-kanıt: alan AÇIKÇA boş gönderilirse temizlenmeli (silme meşru).

    field-merge 'gönderilmeyeni koru' der; ama GÖNDERİLEN boş değer = kasıtlı silme, yazılmalı."""
    pid = hasta_db.add_patient({"name": "Boncuk", "owner": "Ali", "vet_contact": "0555"})
    hasta_db.update_patient(pid, {"vet_contact": ""})
    p = _hasta(hasta_db, pid)
    assert (p.get("vet_contact") or "") == "", "açıkça boşaltılan alan temizlenmedi"
    assert p["name"] == "Boncuk", "boşaltma başka alanı etkiledi"


# ═══════════════════════════════════════════════════════════════════════════════════════
# D2.27 (B-3.111) — DÖNÜŞ, UPDATE'İN KENDİ SONUCUNDAN
# ═══════════════════════════════════════════════════════════════════════════════════════
# `update_patient` dönüşünü `cursor.rowcount`tan, ama arama indeksi tazelemesinden SONRA okuyordu. Tazeleme aynı
# imleçte DELETE (+ varsa INSERT) koşar → rowcount SON ifadenin sayısıdır. Aranabilir alanları (ad/tür/ırk/sahip/yaş/
# kilo) boş bir hastada token yok: DELETE 0 satır → dönüş False → uç "error", arayüz "hata oluştu" der; OYSA yazım
# commit edilmiştir (kayıt-durum dürüstlüğü — ölçüldü).


def test_KRITIK_D227_aranabilir_alanlari_BOS_hastada_guncelleme_BASARI_doner(hasta_db):
    """MUTASYON: dönüşü yeniden indeks tazelemesinden sonraki `cursor.rowcount`tan okumak → KIRMIZI."""
    pid = hasta_db.add_patient({"name": "", "species": "", "owner": ""})
    assert hasta_db.update_patient(pid, {"vet_contact": "Dr. X"}) is True, (
        "yazım COMMIT edildiği hâlde update_patient False döndü → uç 'error', arayüz 'hata oluştu' der"
    )
    assert (_hasta(hasta_db, pid) or {}).get("vet_contact") == "Dr. X", "güncelleme yazılmadı"


def test_KRITIK_D227_guncelleme_UCU_yazilan_kayitta_SUCCESS_der(hasta_db, monkeypatch):
    """Ürünün gerçek ucu (`POST /api/patients` + `id` → `update_patient`): yazılan kayıtta 'success'."""
    from database import patient_database as pdb
    from fastapi.testclient import TestClient
    from servers import api_server
    from servers import patient_router as pr

    monkeypatch.setattr(pdb, "get_patient_database", lambda *a, **k: hasta_db)
    monkeypatch.setattr(pr, "get_patient_database", lambda *a, **k: hasta_db)
    pid = hasta_db.add_patient({"name": "", "species": ""})
    with TestClient(api_server.app) as c:
        r = c.post("/api/patients", json={"id": pid, "vet_contact": "Dr. Y"})
    assert r.status_code == 200 and r.json().get("status") == "success", (
        f"yazılan kayıtta uç: {r.status_code} {r.json()}"
    )
    assert (_hasta(hasta_db, pid) or {}).get("vet_contact") == "Dr. Y"


def test_KARSIT_D227_OLMAYAN_hasta_guncellemesi_BASARISIZ_doner(hasta_db):
    """Dönüş "her zaman True"ya kaymasın: hiç satır güncellenmediyse False. MUTASYON: `return True` → KIRMIZI."""
    hasta_db.add_patient({"name": "Var", "species": "Kedi"})
    assert hasta_db.update_patient("olmayan-kimlik", {"vet_contact": "X"}) is False
