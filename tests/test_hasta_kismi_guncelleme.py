# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""HASTA KISMİ GÜNCELLEME (field-merge) — eşzamanlılık denetimi 2026-08-30.

`update_patient` YALNIZ `patient_info`'da gelen alanları yazar; gönderilmeyen alanı KORUR. Bu,
backend'in lost-update'e karşı tek yapısal savunmasıdır (saha 4.3: "diğer alanlar kaybolmaz").

⚠️ NEDEN KRİTİK: frontend hasta düzenlemede TÜM formu gönderiyor (`pf/src/screens/PatientScreen`
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
