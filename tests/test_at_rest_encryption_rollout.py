# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AT-REST ŞİFRELEME AÇILIŞI — launcher yolunda KAPALIYDI (2026-08-08 denetim bulgusu).

ARIZA: `launcher/core/src/install.rs::backend_env()` backend'e YALNIZ 4 değişken veriyordu
(model dizini, port, auth, health nonce). `PEMF_ENCRYPT_AT_REST` YOKTU → siteden indirip kuran
HER klinik hasta verisini DÜZ METİN yazıyordu (PII maskeleme de sahip kararıyla varsayılan
kapalı). Site ise üç yerde "cihazda şifreli (SQLCipher)" diye beyan ediyor.

GERÇEK ARTEFAKTLA ÖLÇÜLDÜ (frozen EXE, izole veri dizini):
    bayraksız → atRestEncrypted=False   |   PEMF_ENCRYPT_AT_REST=1 → atRestEncrypted=True
    düz-metin klinik + bayrak açılışı   → göç etti, kayıt KORUNDU, hard-fail YOK
Bayrağın kendisi `install.rs`'te sözleşme testiyle kilitli (backend_env_at_rest_sifrelemeyi_*).

BU DOSYA göç KOD YOLUNU kilitler: bayrak açılınca sahadaki düz-metin DB'nin veri kaybetmeden
şifrelenmesi ve korumasız kopyanın diskte kalmaması.

⚠️ TEST ORTAMI NOTU: burada şifreleme FIRSATÇI davranır (anahtar + binding varsa bayraksız da
devreye girer), frozen build'de ise bayrak gerekir. Bu yüzden "eski klinik" durumunu bayrağı
kaldırarak DEĞİL, sqlcipher binding'ini geçici olarak yok göstererek kuruyoruz — düz-metin
başlangıcı ancak böyle güvenilir biçimde üretilebiliyor.
"""

import sqlite3

import pytest

pytest.importorskip("sqlcipher3", reason="at-rest testleri sqlcipher3 ister")


@pytest.fixture(autouse=True)
def _sir_onbellegini_izole_et():
    """⚠️ SÜREÇ-GENELİ SIR ÖNBELLEĞİNİ TEMİZLE — testler arası sızıntıyı keser.

     modül düzeyinde tutulur (üretimde doğru: tek süreç, tek veri
    dizini). Testte ise bir testin ürettiği SQLCipher anahtarı sonraki testlerin BAŞKA temp
    dizinine taşınır → onların DÜZ-METİN patients.db'si şifreli sanılıp "file is not a database"
    ile patlar. Bu fixture olmadan bu dosya 12 ilgisiz testi düşürüyordu.
    """
    import utils.secrets_manager as sm

    sm._cache = None
    yield
    sm._cache = None


def _db(app_data):
    from database.treatment_history_db import TreatmentHistoryDB

    return TreatmentHistoryDB(app_data)


def _duz_metin_klinik_kur(app_data, monkeypatch, hasta):
    """Şifrelemeden ÖNCE kurulmuş bir kliniği taklit et: düz-metin DB + gerçek hasta verisi.

    Bayrak KAPALI + binding yok gibi → sahadaki eski launcher kurulumunun tam durumu.
    """
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    db = TreatmentHistoryDB(app_data)
    assert db.at_rest_encrypted is False, "on kosul: bu klinik SIFRESIZ baslamis olmali"
    db.start_session("Manuel", patient_name=hasta)
    db.add_ai_analysis(
        module_id="cat_disease", patient_name=hasta, result_summary="ozet", operator_email="vet@example.com"
    )
    # ⚠️ Bağlantıyı KAPAT: göç dosyayı taşır (shutil.move) ve açık tutamaç Windows'ta
    # PermissionError verir. Sahada da aynı kural geçerli — göç açılışta, tek süreçte olur.
    db.close_connections()


def _yukselt(monkeypatch):
    """Launcher düzeltmesinin taklidi: binding geri gelir (frozen'da bundle'lı) + bayrak AÇILIR."""
    monkeypatch.undo()
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")


def test_on_kosul_duz_metin_gercekten_okunabilir(temp_app_data, monkeypatch):
    """Sorunun VAR olduğunu kanıtla: şifresiz DB'de hasta adı diskte okunabilir."""
    _duz_metin_klinik_kur(temp_app_data, monkeypatch, "OkunabilirHasta")
    with sqlite3.connect(temp_app_data / "pemf_treatment_history.db") as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        adlar = [r[0] for r in c.execute("SELECT patient_name FROM treatment_sessions")]
    assert "OkunabilirHasta" in adlar, "on kosul kurulamadi"


def test_KRITIK_mevcut_duz_metin_klinik_GOCER_ve_veri_KORUNUR(temp_app_data, monkeypatch):
    """Sahadaki asıl senaryo. Göç etmezse klinik TÜM geçmişine erişemez — düzeltmenin
    kendisinden çok daha kötü bir arıza olurdu."""
    _duz_metin_klinik_kur(temp_app_data, monkeypatch, "GocenHasta")
    _yukselt(monkeypatch)

    db2 = _db(temp_app_data)  # yükseltme açılışı
    assert db2.at_rest_encrypted is True, "goc olmadi — sifreli acilmadi"
    assert [s["patient_name"] for s in db2.get_session_history(limit=10)] == ["GocenHasta"], (
        "goc sirasinda SEANS kayboldu"
    )
    analiz = db2.get_ai_analyses(limit=10)
    assert [a["patient_name"] for a in analiz] == ["GocenHasta"], "goc sirasinda ANALIZ kayboldu"
    assert analiz[0]["operator_email"] == "vet@example.com", "operator sahipligi kayboldu"


def test_KRITIK_goc_sonrasi_dosya_DUZ_SQLITE_ile_ACILMAZ(temp_app_data, monkeypatch):
    """`at_rest_encrypted=True` bayrağına GÜVENME — dosyanın gerçekten şifreli olduğunu kanıtla."""
    _duz_metin_klinik_kur(temp_app_data, monkeypatch, "GizliHasta")
    _yukselt(monkeypatch)
    _db(temp_app_data)

    yol = temp_app_data / "pemf_treatment_history.db"
    with pytest.raises(sqlite3.DatabaseError):
        with sqlite3.connect(yol) as c:
            c.execute("SELECT count(*) FROM sqlite_master").fetchone()
    assert b"GizliHasta" not in yol.read_bytes(), "hasta adi sifreli dosyada DUZ METIN"


def test_KRITIK_korumasiz_duz_metin_ARTIK_diskte_KALMAZ(temp_app_data, monkeypatch):
    """Göç eski dosyayı yedekler; o yedek korumasız kalırsa şifreleme ANLAMSIZ olur."""
    _duz_metin_klinik_kur(temp_app_data, monkeypatch, "YedekHasta")
    _yukselt(monkeypatch)
    _db(temp_app_data)

    for p in temp_app_data.rglob("*"):
        if p.is_file() and p.name != "pemf_treatment_history.db":
            assert b"YedekHasta" not in p.read_bytes(), f"korumasiz duz-metin artik: {p.name}"


def test_ikinci_acilis_yeniden_GOCMEZ(temp_app_data, monkeypatch):
    """Göç bir kez olmalı; her açılışta tekrarlarsa yavaşlar ve artık dosya birikir."""
    _duz_metin_klinik_kur(temp_app_data, monkeypatch, "TekrarHasta")
    _yukselt(monkeypatch)
    _db(temp_app_data)
    db3 = _db(temp_app_data)
    assert db3.at_rest_encrypted is True
    assert [s["patient_name"] for s in db3.get_session_history(limit=5)] == ["TekrarHasta"]


def test_taze_kurulum_dogrudan_SIFRELI_baslar(temp_app_data, monkeypatch):
    """Yeni klinik: hiç düz-metin evresi olmadan şifreli başlamalı."""
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    db = _db(temp_app_data)
    db.add_ai_analysis(module_id="m", patient_name="TazeHasta", result_summary="s")
    assert db.at_rest_encrypted is True
    assert b"TazeHasta" not in (temp_app_data / "pemf_treatment_history.db").read_bytes()


def test_escrow_ISTENIRSE_hala_saklanir(temp_app_data, monkeypatch):
    """Geriye uyum: eski davranışı isteyen `PEMF_KEEP_PLAIN_BAK=1` ile escrow'u geri alabilmeli."""
    _duz_metin_klinik_kur(temp_app_data, monkeypatch, "EscrowHasta")
    _yukselt(monkeypatch)
    monkeypatch.setenv("PEMF_KEEP_PLAIN_BAK", "1")
    _db(temp_app_data)
    assert (temp_app_data / "pemf_treatment_history.db.plain.bak").exists(), "escrow acikca istendi ama saklanmadi"


def test_KRITIK_guvenli_silme_icerigi_UZERINE_YAZAR(temp_app_data, monkeypatch):
    """Yalnız `unlink` içeriği diskte bırakır. Yedek dosyası silinmeden ÖNCE üzerine yazılmalı.

    Dosya silindiği için doğrudan bakamayız; bunun yerine silme yolunun `os.remove`'a gelmeden
    ÖNCE dosyayı rastgele veriyle doldurduğunu, remove'u yakalayıp içeriği okuyarak kanıtlıyoruz.
    """
    import os as _os

    _duz_metin_klinik_kur(temp_app_data, monkeypatch, "UzerineYazHasta")
    _yukselt(monkeypatch)

    goruldu = {}
    _gercek_remove = _os.remove

    def _casus(path, *a, **k):
        p = str(path)
        if p.endswith(".plain.bak") and _os.path.exists(p):
            with open(p, "rb") as f:
                goruldu["icerik"] = f.read()
        return _gercek_remove(path, *a, **k)

    monkeypatch.setattr(_os, "remove", _casus)
    _db(temp_app_data)

    assert "icerik" in goruldu, "guvenli-silme yolu hic calismadi"
    assert b"UzerineYazHasta" not in goruldu["icerik"], (
        "yedek SILINMEDEN once uzerine yazilmamis — icerik diskte kurtarilabilir kalir"
    )
