# -*- coding: utf-8 -*-
"""D2.26 (B-3.108) — ÖNEKSİZ ESKİ-ŞİFRELİ HASTA ALANI LEGACY ANAHTARLA DA ÇÖZÜLÜR.

KUSUR. `PatientDatabase._decrypt_field` iki biçim okur: `enc:` önekli (2026-06-27 sonrası) ve ÖNEKSİZ (öncesi).
`enc:` dalı `config._decrypt_value` zincirini (birincil → legacy MAC-türevli anahtar) kullanıyordu; öneksiz dal
YALNIZ birincil anahtarı deniyordu. Legacy anahtarla şifrelenmiş öneksiz alan `[okunamayan kayıt]` görünüyor ve
cihaz taşımada (dışa aktarma `get_all_patients` → içe aktarma `add_patient`) yer-tutucu hedefe KALICI yazılıyordu =
veri kaybı (anahtar elde olduğu hâlde).

SÖZLEŞME: öneksiz dal `enc:` dalıyla AYNI zinciri kullanır; çözülemeyen Fernet benzeri değer yine yer-tutucu
(ham şifreli metin kullanıcıya gösterilmez), Fernet olmayan düz-metin eski değer olduğu gibi döner.
sqlcipher3 GEREKTİRMEZ (alan şifrelemesi Fernet; DB düz-metin kipte).
"""

from __future__ import annotations

import base64

import pytest


@pytest.fixture
def hasta_db(temp_app_data, monkeypatch):
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    return pdb.PatientDatabase(str(temp_app_data / "patients.db"))


@pytest.fixture
def eski_anahtar(hasta_db, monkeypatch):
    """Belirlenimci bir LEGACY anahtar (birincilden FARKLI) — makinenin MAC-türevli anahtarına bağlı kalmasın."""
    from cryptography.fernet import Fernet

    eski = Fernet(Fernet.generate_key())
    monkeypatch.setattr(hasta_db.config_manager, "_legacy_cipher", eski)
    return eski


def _oneksiz(cipher, duz: str) -> str:
    """2026-06-27 öncesi biçim: `_encrypt_value` çıktısı, `enc:` öneki YOK."""
    return base64.urlsafe_b64encode(cipher.encrypt(duz.encode("utf-8"))).decode("ascii")


def _ham_yaz(db, hid: str, alan: str, deger: str) -> None:
    with db._get_connection() as c:
        c.execute(f"UPDATE patients SET {alan} = ? WHERE id = ?", (deger, hid))
        c.commit()


def test_KRITIK_oneksiz_LEGACY_sifreli_alan_COZULUR(hasta_db, eski_anahtar):
    """MUTASYON: öneksiz dalı yeniden yalnız birincil anahtarla (`config_manager._cipher`) çözmek → KIRMIZI."""
    hid = hasta_db.add_patient({"name": "Gecici", "owner": "T", "species": "Kedi"})
    _ham_yaz(hasta_db, hid, "name", _oneksiz(eski_anahtar, "EskiAnahtarHasta"))
    _ham_yaz(hasta_db, hid, "owner", _oneksiz(eski_anahtar, "EskiSahip"))

    h = hasta_db.get_patient(hid) or {}
    assert h.get("name") == "EskiAnahtarHasta", f"legacy anahtarla şifreli öneksiz ad ÇÖZÜLMEDİ: {h.get('name')!r}"
    assert h.get("owner") == "EskiSahip", f"legacy anahtarla şifreli öneksiz sahip ÇÖZÜLMEDİ: {h.get('owner')!r}"


def test_KRITIK_cihaz_tasimada_oneksiz_legacy_alan_YER_TUTUCU_olarak_yazilmaz(hasta_db, eski_anahtar, temp_app_data):
    """Ürünün taşıma yolu (api_server `export_clinic_data` → `get_all_patients`; `import_clinic_data` →
    `add_patient(h, id)`) ile aynı adımlar: kaynakta çözülemeyen alan hedefe '[okunamayan kayıt]' olarak YAZILIRSA
    anahtar sonradan bulunsa bile veri KALICI kaybolur."""
    import database.patient_database as pdb

    hid = hasta_db.add_patient({"name": "Gecici", "owner": "T", "species": "Kedi"})
    _ham_yaz(hasta_db, hid, "name", _oneksiz(eski_anahtar, "TasinanHasta"))

    paket = hasta_db.get_all_patients()
    hedef_kok = temp_app_data / "hedef"
    hedef_kok.mkdir()
    hedef = pdb.PatientDatabase(str(hedef_kok / "patients.db"))
    for h in paket:
        hedef.add_patient(h, h.get("id"))

    tasinan = hedef.get_patient(hid) or {}
    assert tasinan.get("name") == "TasinanHasta", (
        f"taşıma hedefinde ad {tasinan.get('name')!r} — yer-tutucu KALICI yazıldı (anahtar elde olduğu hâlde veri kaybı)"
    )


def test_KARSIT_bilinmeyen_anahtarli_oneksiz_alan_YER_TUTUCU_duz_metin_AYNEN(hasta_db, eski_anahtar):
    """Zincir genişlerken iki sınır korunur: hiçbir anahtarın açamadığı Fernet değeri ham şifreli metin olarak
    GÖSTERİLMEZ (yer-tutucu); Fernet olmayan eski düz-metin değer olduğu gibi döner.
    MUTASYON: yer-tutucu dalını kaldırmak (ham değeri döndürmek) → KIRMIZI."""
    from cryptography.fernet import Fernet
    from database.patient_database import _UNREADABLE_PLACEHOLDER

    hid = hasta_db.add_patient({"name": "Gecici", "owner": "T", "species": "Kedi"})
    _ham_yaz(hasta_db, hid, "name", _oneksiz(Fernet(Fernet.generate_key()), "KimseninAnahtariDegil"))
    _ham_yaz(hasta_db, hid, "owner", "DuzMetinEskiSahip")

    h = hasta_db.get_patient(hid) or {}
    assert h.get("name") == _UNREADABLE_PLACEHOLDER, f"çözülemeyen değer kullanıcıya ham gösterildi: {h.get('name')!r}"
    assert h.get("owner") == "DuzMetinEskiSahip", f"düz-metin eski değer bozuldu: {h.get('owner')!r}"
