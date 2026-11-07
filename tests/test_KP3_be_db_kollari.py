# -*- coding: utf-8 -*-
"""KP-3 C · veritabanı katmanının kapsanmayan hata kolları — her test bir DAVRANIŞ iddiası:

- `auth_db.AuthDB`: ACL kilidi uygulanamazsa açılış düşmez (uyarı); bağlantı açılamazken (kilitli / bozuk DB) operatör kaydı `db_error`,
  varlık / liste / silme / e-posta / doğrulama güvenli değer (False / [] / False / False / False), kayıt ve sıfırlama okunur (çevrilmiş)
  hata iletisi döner — hiçbiri istisna sızdırmaz (yalnız `kati=True` sızdırır).
- `DenetimKarisimi`: sürüm okunamazsa / ayrıntı JSON'a çevrilemezse iz YİNE yazılır (boş sürüm, ayrıntısız); okuma / sayma hatası → [] / 0.
- `PiiKarisimi`: bozuk onay günü → onay YOK; bozuk süre → ayarlanmamış; bozuk anonimleştirme onayı → onay YOK (fail-closed);
  maskeleme hatası rapora sıfır + uyarı; yüklerde ayrıştırılamayan JSON / başka seansın outbox yükü DEĞİŞTİRİLMEZ.

Sahte EN ALT katta: bağlantı fabrikası (`_conn` / `_get_connection`), ACL yardımcısı, sürüm okuyucu; tablolar gerçek in-memory SQLite.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading

import pytest
from database import auth_db as adb
from database.thdb_denetim import DenetimKarisimi
from database.thdb_pii import PiiKarisimi
from utils import ceviri


def _kilitli(*a, **k):
    raise sqlite3.OperationalError("database is locked")


@pytest.fixture
def kimlik_db(tmp_path):
    return adb.AuthDB(tmp_path)


def test_acl_kilidi_uygulanamazsa_acilis_dusmez(monkeypatch, tmp_path, caplog):
    from utils import file_acl

    def _icacls_patla(*a, **k):
        raise OSError("icacls bulunamadı")

    monkeypatch.setattr(file_acl, "lock_down_file", _icacls_patla)
    with caplog.at_level(logging.WARNING, logger=adb.logger.name):
        db = adb.AuthDB(tmp_path)
    assert db.register("vet@klinik.test", "Parola123")[0] is True, "ACL hatası sonrası DB kullanılamıyor"
    assert any("ACL kilidi uygulanamadi" in r.getMessage() for r in caplog.records)


def test_baglanti_acilamazken_kimlik_islemleri_guvenli_deger_doner(kimlik_db, monkeypatch, caplog):
    assert kimlik_db.register("vet@klinik.test", "Parola123") == (True, "")
    monkeypatch.setattr(kimlik_db, "_conn", _kilitli)
    with caplog.at_level(logging.ERROR, logger=adb.logger.name):
        assert kimlik_db.enroll_operator("dr@klinik.test", "Dr. Ayşe", "123456") == (False, "db_error")
        assert kimlik_db.operator_exists("dr@klinik.test") is False
        assert kimlik_db.list_operators() == []
        assert kimlik_db.remove_operator("dr@klinik.test") is False
        assert kimlik_db.email_exists("vet@klinik.test") is False
        assert kimlik_db.register("yeni@klinik.test", "Parola123") == (False, ceviri.t("kimlik.hata.kayitSunucuHatasi"))
        assert kimlik_db.reset_password("vet@klinik.test", "Yeni12345") == (
            False,
            ceviri.t("kimlik.hata.sifirlamaSunucuHatasi"),
        )
        assert kimlik_db.verify("vet@klinik.test", "Parola123") is False
    monkeypatch.setattr(kimlik_db, "_kati_oku", _kilitli)  # katı kip AYRI okuma yolu (B2B2-1) — hatayı YUTMAZ
    with pytest.raises(sqlite3.OperationalError):
        kimlik_db.operator_exists("dr@klinik.test", kati=True)
    with pytest.raises(sqlite3.OperationalError):
        kimlik_db.list_operators(kati=True)
    mesajlar = " | ".join(r.getMessage() for r in caplog.records)
    for beklenen in (
        "operator kaydi basarisiz",
        "operator silinemedi",
        "email_exists hatası",
        "kullanıcı kaydı hatası",
    ):
        assert beklenen in mesajlar


# ── DenetimKarisimi ───────────────────────────────────────────────────────────────────────────────────────────────────
class _DenetimDb(DenetimKarisimi):
    def __init__(self, baglanti_hatasi: Exception | None = None):
        self._lock = threading.RLock()
        self.logger = logging.getLogger("kp3.denetim")
        self.baglanti_hatasi = baglanti_hatasi
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE audit_events (id INTEGER PRIMARY KEY, ts_utc TEXT, event_type TEXT, operator_email TEXT, client_ip TEXT,"
            " scope TEXT, item_count INTEGER, outcome TEXT, detail TEXT, app_version TEXT, build_id TEXT)"
        )

    def _get_connection(self):
        if self.baglanti_hatasi:
            raise self.baglanti_hatasi
        return contextlib.nullcontext(self.conn)


def test_denetim_izi_surum_ve_ayrinti_cozulemese_de_yazilir(monkeypatch):
    from utils import path_utils

    def _patla():
        raise OSError("VERSION okunamadı")

    monkeypatch.setattr(path_utils, "get_app_version", _patla)
    db = _DenetimDb()
    assert db.denetim_yaz("patient.delete", detail={"nesne": object()}, outcome="ok") is True
    satir = dict(db.conn.execute("SELECT * FROM audit_events").fetchone())
    assert satir["event_type"] == "patient.delete" and satir["app_version"] == "" and satir["build_id"] == ""
    assert satir["detail"] is None, "JSON'a çevrilemeyen ayrıntı yazıldı"


def test_denetim_okuma_ve_sayma_hatasi_bos_ve_sifir(caplog):
    db = _DenetimDb(baglanti_hatasi=sqlite3.DatabaseError("file is not a database"))
    with caplog.at_level(logging.ERROR, logger="kp3.denetim"):
        assert db.denetim_oku() == []
    assert any("Denetim izi okunamadi" in r.getMessage() for r in caplog.records)
    assert db.denetim_sayisi() == 0


# ── PiiKarisimi ───────────────────────────────────────────────────────────────────────────────────────────────────────
class _PiiDb(PiiKarisimi):
    PII_SURE_ANAHTARI = "pii_sure"

    def __init__(self, ayarlar=None, onay=None, baglanti_hatasi=None):
        self.ayarlar = dict(ayarlar or {})
        self.onay = onay
        self.baglanti_hatasi = baglanti_hatasi
        self.logger = logging.getLogger("kp3.pii")

    def _get_system_setting(self, k):
        return self.ayarlar.get(k)

    def pii_onayi_oku(self):
        return self.onay

    def pii_kapsam_imzasi(self):
        return "kapsam-1"

    def _get_connection(self):
        raise self.baglanti_hatasi


def test_bozuk_pii_ayarlari_onay_yok_sayar():
    assert _PiiDb(onay={"gun": "otuz", "kapsam": "kapsam-1"}).pii_onayi_var_mi(30) is False
    assert _PiiDb(onay={"gun": "30", "kapsam": "kapsam-1"}).pii_onayi_var_mi(30) is True
    assert _PiiDb({"pii_sure": "yarim-yil"}).pii_suresi_oku() is None
    assert _PiiDb({"pii_sure": "90"}).pii_suresi_oku() == 90
    assert _PiiDb({_PiiDb.ANONIM_ONAY_ANAHTARI: "{bozuk"}).anonim_onayi_oku() is None


def test_maskeleme_hatasi_rapora_sifir_ve_uyari(caplog):
    db = _PiiDb(baglanti_hatasi=sqlite3.OperationalError("database is locked"))
    with caplog.at_level(logging.WARNING, logger="kp3.pii"):
        assert db.redact_old_session_pii(30) == {"sessions_redacted": 0, "parameters_redacted": 0, "events_redacted": 0}
    assert any("PII redaction uyarısı" in r.getMessage() for r in caplog.records)


def test_yuk_anonimlestirme_bozuk_json_ve_baska_seans_outbox_dokunulmaz():
    c = sqlite3.connect(":memory:").cursor()
    c.execute("CREATE TABLE session_events (id INTEGER PRIMARY KEY, session_id INTEGER, payload TEXT)")
    c.execute("CREATE TABLE outbox_messages (id INTEGER PRIMARY KEY, correlation_id TEXT, payload TEXT)")
    c.execute("INSERT INTO session_events (session_id, payload) VALUES (7, '{bozuk')")
    c.execute(
        "INSERT INTO session_events (session_id, payload) VALUES (7, ?)", (json.dumps({"patient_name": "Pamuk"}),)
    )
    baska = json.dumps({"patient_name": "Boncuk", "session_id": 99})
    c.execute("INSERT INTO outbox_messages (correlation_id, payload) VALUES ('7', ?)", (baska,))
    assert _PiiDb()._yuklerden_hasta_adini_anonimlestir(c, [7]) == 1
    yukler = [r[0] for r in c.execute("SELECT payload FROM session_events ORDER BY id")]
    assert yukler[0] == "{bozuk" and json.loads(yukler[1])["patient_name"] == "[ANONIM]"
    assert c.execute("SELECT payload FROM outbox_messages").fetchone()[0] == baska, "başka seansın outbox yükü değişti"
