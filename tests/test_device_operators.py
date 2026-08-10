# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CİHAZ OPERATÖRLERİ — tek makine, çoklu veteriner (2026-08-08 sahip isteği).

BAĞLAM: bir kliniği 3-4 veteriner paylaşıyor ama uygulamaya TEK e-postayla giriliyordu → her
kayda AYNI `operator_email` yazılıyor ve "Benim Hastalarım / Tüm Klinik" ayrımı ANLAMSIZ
kalıyordu. Veri modeli çoklu operatörü zaten destekliyordu; eksik olan kimlik katmanıydı.

TASARIM: kimlik bir kez Supabase ile doğrulanır, sonraki geçişler yerel PIN ile ÇEVRİMDIŞI
yapılır (internetsiz klinikte de operatör değişebilmeli).

⚠️ PIN uzayı küçüktür (10^6). Bu testlerin ASIL işi, onu koruyan üç katmanın (PBKDF2, ACL,
KİLİTLENME) gerçekten çalıştığını kanıtlamak. Kilitlenme olmadan yerel kaba kuvvet dakikalar sürer.
"""

import time

import pytest


def _db(temp_app_data):
    from database.auth_db import AuthDB

    return AuthDB(temp_app_data)


def _kayit(db, eposta="vet@klinik.com", ad="Dr. Ayşe", pin="123456"):
    ok, err = db.enroll_operator(eposta, ad, pin)
    assert ok, f"kayit basarisiz: {err}"
    return eposta


# ── kayıt ────────────────────────────────────────────────────────────────────


def test_operator_kaydi_ve_listeleme(temp_app_data):
    db = _db(temp_app_data)
    _kayit(db, "a@x.com", "Dr. Ayşe", "111111")
    _kayit(db, "b@x.com", "Dr. Mehmet", "222222")
    liste = db.list_operators()
    assert {o["email"] for o in liste} == {"a@x.com", "b@x.com"}
    assert {o["display_name"] for o in liste} == {"Dr. Ayşe", "Dr. Mehmet"}


def test_KRITIK_liste_SIR_SIZDIRMAZ(temp_app_data):
    """Liste istemciye gider; hash/salt sızarsa PIN çevrimdışı kırılabilir."""
    db = _db(temp_app_data)
    _kayit(db)
    for o in db.list_operators():
        assert "pin_hash" not in o and "pin_salt" not in o, f"sir sizdi: {o}"


def test_gecersiz_pin_REDDEDILIR(temp_app_data):
    db = _db(temp_app_data)
    for kotu in ("", "123", "12345", "1234567", "abcdef", "12 456", None):
        ok, err = db.enroll_operator("v@x.com", "V", kotu)
        assert not ok and err == "invalid_pin", f"kabul edildi: {kotu!r}"


def test_gecersiz_eposta_REDDEDILIR(temp_app_data):
    db = _db(temp_app_data)
    ok, err = db.enroll_operator("eposta-degil", "V", "123456")
    assert not ok and err == "invalid_email"


def test_yeniden_kayit_PIN_gunceller(temp_app_data):
    """⚠️ 2026-08-09: PIN değiştirmek artık ESKİ PIN ister. Bu test eskiden eski-PİN'siz
    güncelleme yapıyordu — yani kapatılan açığın ta kendisini sözleşme sayıyordu."""
    db = _db(temp_app_data)
    e = _kayit(db, pin="111111")
    assert db.verify_pin(e, "111111")[0]
    ok, err = db.enroll_operator(e, "Dr. Ayşe", "999999", eski_pin="111111")
    assert ok, f"sahibi kendi PIN'ini degistiremedi: {err}"
    assert db.verify_pin(e, "999999")[0]
    assert not db.verify_pin(e, "111111")[0], "eski PIN hala gecerli"


# ── doğrulama ────────────────────────────────────────────────────────────────


def test_dogru_pin_gecer_yanlis_pin_gecmez(temp_app_data):
    db = _db(temp_app_data)
    e = _kayit(db, pin="424242")
    assert db.verify_pin(e, "424242") == (True, None)
    assert db.verify_pin(e, "424243")[0] is False


def test_kayitsiz_operator_no_operator_doner(temp_app_data):
    db = _db(temp_app_data)
    ok, err = db.verify_pin("yok@x.com", "123456")
    assert ok is False and err == "no_operator"


def test_KRITIK_pin_diskte_DUZ_METIN_DEGIL(temp_app_data):
    """PIN saklanıyorsa cihazı eline geçiren herkes başkasının adına işlem yapabilir."""
    db = _db(temp_app_data)
    _kayit(db, pin="864213")
    ham = (temp_app_data / "auth_users.db").read_bytes()
    assert b"864213" not in ham, "PIN diskte DUZ METIN"


def test_KRITIK_ayni_pin_FARKLI_hash_uretir(temp_app_data):
    """Tuz sabit olsaydı aynı PIN'i kullanan iki veteriner hash'ten anlaşılırdı."""
    db = _db(temp_app_data)
    _kayit(db, "a@x.com", "A", "555555")
    _kayit(db, "b@x.com", "B", "555555")
    import sqlite3

    with sqlite3.connect(temp_app_data / "auth_users.db") as c:
        h = [r[0] for r in c.execute("SELECT pin_hash FROM device_operators")]
    assert len(set(h)) == 2, "ayni PIN ayni hash uretti — tuz kullanilmiyor"


# ── kilitlenme (PIN'in ASIL koruması) ────────────────────────────────────────


def test_KRITIK_art_arda_hata_KILITLER(temp_app_data):
    """Kilitlenme olmadan 10^6 uzaylı bir PIN yerel olarak kaba kuvvetle kırılır."""
    db = _db(temp_app_data)
    e = _kayit(db, pin="777777")
    for _ in range(db._PIN_MAX_FAIL):
        db.verify_pin(e, "000000")
    ok, err = db.verify_pin(e, "000000")
    assert ok is False and err == "locked", "kilit devreye girmedi"
    # Kilitliyken DOĞRU PIN bile geçmemeli (yoksa kilit anlamsız).
    assert db.verify_pin(e, "777777") == (False, "locked"), "kilitliyken dogru PIN gecti"


def test_kilit_listede_GORUNUR(temp_app_data):
    db = _db(temp_app_data)
    e = _kayit(db, pin="777777")
    for _ in range(db._PIN_MAX_FAIL + 1):
        db.verify_pin(e, "000000")
    assert [o for o in db.list_operators() if o["email"] == e][0]["locked"] is True


def test_basarili_giris_sayaci_SIFIRLAR(temp_app_data):
    """Sayaç sıfırlanmazsa gün içinde biriken hatalar doğru PIN'i kilitler (kullanılamaz olur)."""
    db = _db(temp_app_data)
    e = _kayit(db, pin="333333")
    for _ in range(db._PIN_MAX_FAIL - 1):
        db.verify_pin(e, "000000")
    assert db.verify_pin(e, "333333")[0], "dogru PIN gecmedi"
    for _ in range(db._PIN_MAX_FAIL - 1):
        db.verify_pin(e, "000000")
    assert db.verify_pin(e, "333333")[0], "sayac sifirlanmamis — kilit erken geldi"


def test_kilit_suresi_dolunca_ACILIR(temp_app_data, monkeypatch):
    db = _db(temp_app_data)
    e = _kayit(db, pin="888888")
    for _ in range(db._PIN_MAX_FAIL + 1):
        db.verify_pin(e, "000000")
    assert db.verify_pin(e, "888888")[1] == "locked"
    ileri = time.time() + db._PIN_LOCK_SECONDS + 10
    monkeypatch.setattr(time, "time", lambda: ileri)
    assert db.verify_pin(e, "888888")[0], "sure dolduktan sonra da kilitli kaldi"


def test_kilit_operatore_OZEL(temp_app_data):
    """Bir veterinerin PIN'ini yanlış girmesi DİĞERLERİNİ kilitlememeli (klinik durur)."""
    db = _db(temp_app_data)
    a = _kayit(db, "a@x.com", "A", "111111")
    b = _kayit(db, "b@x.com", "B", "222222")
    for _ in range(db._PIN_MAX_FAIL + 1):
        db.verify_pin(a, "000000")
    assert db.verify_pin(a, "111111")[1] == "locked"
    assert db.verify_pin(b, "222222")[0], "baska operator de kilitlendi"


# ── çıkarma ──────────────────────────────────────────────────────────────────


def test_operator_cikarma(temp_app_data):
    db = _db(temp_app_data)
    e = _kayit(db)
    assert db.remove_operator(e) is True
    assert db.list_operators() == []
    assert db.verify_pin(e, "123456")[1] == "no_operator"
    assert db.remove_operator(e) is False


def test_operator_cikarmak_KAYITLARI_SILMEZ(temp_app_data):
    """Operatör cihazdan çıkarılınca tıbbi kayıtları KALIR (yasal saklama + klinik sürekliliği)."""
    from database.treatment_history_db import TreatmentHistoryDB

    th = TreatmentHistoryDB(temp_app_data)
    th.add_ai_analysis(module_id="m", patient_name="Pamuk", result_summary="s", operator_email="ayrilan@x.com")
    db = _db(temp_app_data)
    _kayit(db, "ayrilan@x.com", "Ayrılan", "123456")
    db.remove_operator("ayrilan@x.com")
    assert [a["operator_email"] for a in th.get_ai_analyses(limit=5)] == ["ayrilan@x.com"]


# ───────── KAYIT KAPISI (2026-08-09 denetimi, ENGEL) ─────────
# ARIZA: `enroll_operator` mevcut kaydı ezerken `fail_count=0, locked_until=0` yapıyordu →
# bu ucu çağırabilen herkes BAŞKA bir hekimin PIN'ini ezip kilidini sıfırlayabiliyordu.
# PBKDF2 + üstel kilitlenme korumasının TAMAMI tek çağrıyla baypas ediliyordu.


def test_KRITIK_mevcut_kayit_ESKI_PIN_olmadan_EZILEMEZ(temp_app_data):
    db = _db(temp_app_data)
    e = _kayit(db, pin="111111")
    ok, err = db.enroll_operator(e, "Saldirgan", "999999")  # eski PIN YOK
    assert ok is False and err == "wrong_old_pin", "baskasinin PIN'i ezildi"
    assert db.verify_pin(e, "111111")[0], "orijinal PIN bozuldu"
    assert not db.verify_pin(e, "999999")[0], "saldirganin PIN'i gecerli oldu"


def test_mevcut_kayit_DOGRU_eski_PIN_ile_guncellenir(temp_app_data):
    db = _db(temp_app_data)
    e = _kayit(db, pin="111111")
    ok, err = db.enroll_operator(e, "Dr. Ayşe", "222222", eski_pin="111111")
    assert ok, f"sahibi kendi PIN'ini degistiremedi: {err}"
    assert db.verify_pin(e, "222222")[0]
    assert not db.verify_pin(e, "111111")[0]


def test_KRITIK_kayit_ucu_KILIDI_SIFIRLAYAMAZ(temp_app_data):
    """Kilitli bir operatörün kilidi 'yeniden kaydol' ile açılamamalı — açılırsa kilitlenme
    korumasının hiçbir anlamı kalmaz (saldırgan her 5 denemede bir kaydolur)."""
    db = _db(temp_app_data)
    e = _kayit(db, pin="777777")
    for _ in range(db._PIN_MAX_FAIL + 1):
        db.verify_pin(e, "000000")
    assert db.verify_pin(e, "777777")[1] == "locked"

    ok, err = db.enroll_operator(e, "X", "888888", eski_pin="777777")  # DOĞRU eski PIN bile
    assert ok is False and err == "locked", "kilit kayit ucuyla sifirlandi"
    assert db.verify_pin(e, "777777")[1] == "locked", "kilit hala durmali"


def test_yeni_kayit_eski_PIN_ISTEMEZ(temp_app_data):
    """Geriye uyum: ilk kez kaydolan kişiden eski PIN istenmemeli."""
    db = _db(temp_app_data)
    ok, err = db.enroll_operator("yeni@klinik.com", "Yeni", "123456")
    assert ok, f"ilk kayit engellendi: {err}"


def test_operator_exists_dogru_calisir(temp_app_data):
    db = _db(temp_app_data)
    assert db.operator_exists("yok@x.com") is False
    _kayit(db, "var@x.com")
    assert db.operator_exists("var@x.com") is True
    assert db.operator_exists("VAR@X.COM") is True  # normalize
