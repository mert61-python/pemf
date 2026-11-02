# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/database/thdb_seans.py · sözleşmeler: kanıt-okunamadı sayacı yazılamazsa seans MÜHÜRLENMEZ (active kalır) ·
açılış kurtarması (yaş filtresi genç seansı atlar; tarihi bozuk seans yine kurtarılır; bobin koşuları kapatılamasa da seans kapanır;
seans tablosu okunamazsa 0 + uyarı) · olay saklama silmesi düşerse 0 · `end_session` (süre hesaplanamazsa 0 dk; pulse_duration_ms
sütuna; PII parametresi opt-in maskeyle) · geçmiş süzgeçleri (başlangıç / bitiş tarihi / kip) · okuma hatalarında: geçmiş /
ayrıntı / istatistik / not / silme / toplu silme YÜKSELTİR (silme ATOMİK: hiçbir şey gitmez), kimliksiz not eşlemesi yardımcıları
güvenli değer döner (None / 0 / belirsiz) · boş ad / boş kimlik / alan yok → hiçbir YAZIM yok · geçersiz kimlikler atlanır · toplu
silmede denetlenmiş küme dışı silinmez · kritik olay ayırmada bozuk / sözlük-dışı yük `_ham_yuk` olarak korunur · hasta adı yoksa
upsert atlanır · seans meta yazımı düşerse yükseltmez.

Sahte EN ALT katta: GERÇEK TreatmentHistoryDB (tmp_path, düz SQLite); DB arızası = şemadan tablo düşürme (gerçek `sqlite3.OperationalError`
"no such table" — seans tablosu / parametre / olay / sensör tablosu yok), bozuk satır = SQL ile `session_date` bozma / olay yükü bozma.
"Yazım yok" iddiası bağlantının `total_changes` sayacıyla. PII maskesi: `PEMF_MASK_HISTORY_PII=1` (monkeypatch.setenv).
"""

from __future__ import annotations

import json
import logging
import sqlite3

import pytest
from database.treatment_history_db import TreatmentHistoryDB

LOG = "database.treatment_history_db"


@pytest.fixture
def db(tmp_path):
    d = TreatmentHistoryDB(tmp_path)
    try:
        yield d
    finally:
        d.close()


def _seans(db, ad="Pamuk", kip="Manuel", email=None):
    return db.start_session(treatment_mode=kip, target_condition="kp", patient_name=ad, operator_email=email)


def _sql(db, sorgu, par=()):
    with db._get_connection() as c:
        c.execute(sorgu, par)
        c.commit()


def _tek(db, sorgu, par=()):
    with db._get_connection() as c:
        return c.execute(sorgu, par).fetchone()


def _degisim(db):
    with db._get_connection() as c:
        return c.total_changes


def _kayitlar(caplog, parca, seviye=None):
    return [r for r in caplog.records if parca in r.getMessage() and (seviye is None or r.levelno == seviye)]


# ── Açılış kurtarması ────────────────────────────────────────────────────────


def test_kanit_okunamadi_SAYACI_yazilamazsa_MUHURLENMEZ_seans_active_kalir(db, caplog):
    """session_events tablosu yok → `_kanit_okunamadi_isle` False + 'sayaci yazilamadi' hatası; seans 'active', süre NULL."""
    sid = _seans(db)
    _sql(db, "DROP TABLE session_events")
    with caplog.at_level(logging.ERROR, logger=LOG), db._get_connection() as c:
        assert db._kanit_okunamadi_isle(c.cursor(), sid) is False
    k = _kayitlar(caplog, "kanit-okunamadi sayaci yazilamadi", logging.ERROR)
    assert k and k[0].exc_info is not None
    assert tuple(_tek(db, "SELECT session_status, duration_minutes FROM treatment_sessions WHERE id=?", (sid,))) == (
        "active",
        None,
    )


def test_kurtarma_YAS_FILTRESI_geneci_atlar_TARIHI_BOZUK_seansi_kurtarir(db):
    """12 sa filtresi: az önce başlayan seans 'active' KALIR; tarihi ayrıştırılamayan seans yine kurtarılır (ABORTED_DUE_TO_POWER,
    kanıt yok → 0 dk, bitiş saati yazılır); dönüş 1."""
    genc = _seans(db, "Genc")
    bozuk = _seans(db, "Bozuk")
    _sql(db, "UPDATE treatment_sessions SET session_date = 'bozuk-tarih' WHERE id = ?", (bozuk,))
    assert db.recover_stale_active_sessions(max_age_hours=12) == 1
    assert _tek(db, "SELECT session_status FROM treatment_sessions WHERE id=?", (genc,))[0] == "active"
    durum, sure, bitis, sync = _tek(
        db,
        "SELECT session_status, duration_minutes, end_time, sync_status FROM treatment_sessions WHERE id=?",
        (bozuk,),
    )
    assert (durum, sure, sync) == ("ABORTED_DUE_TO_POWER", 0, 0)
    assert bitis


def test_kurtarma_BOBIN_KOSULARI_kapatilamasa_da_seans_KAPANIR_ve_uyari(db, caplog):
    """session_coil_runs tablosu yok (kanıt 'yok' sayılır) → koşu kapatma UPDATE'i düşer, uyarı; seans yine ABORTED_DUE_TO_POWER."""
    sid = _seans(db)
    _sql(db, "DROP TABLE session_coil_runs")
    with caplog.at_level(logging.WARNING, logger=LOG):
        assert db.recover_stale_active_sessions(max_age_hours=0) == 1
    assert _kayitlar(caplog, f"bobin calismalari kapatilamadi (seans {sid})", logging.WARNING)
    assert _tek(db, "SELECT session_status FROM treatment_sessions WHERE id=?", (sid,))[0] == "ABORTED_DUE_TO_POWER"


def test_kurtarma_SEANS_TABLOSU_okunamazsa_0_ve_uyari(db, caplog):
    """treatment_sessions yok → istisna sızmaz, 0 döner, 'Stale session recovery uyarısı'."""
    _sql(db, "DROP TABLE treatment_sessions")
    with caplog.at_level(logging.WARNING, logger=LOG):
        assert db.recover_stale_active_sessions(max_age_hours=0) == 0
    assert _kayitlar(caplog, "Stale session recovery uyarısı", logging.WARNING)


def test_olay_saklama_silmesi_TABLO_YOKSA_0_ve_uyari(db, caplog):
    """session_events yok → purge_old_session_events 0 (yarım iz yok) + 'retention temizleme uyarısı'."""
    _sql(db, "DROP TABLE session_events")
    with caplog.at_level(logging.WARNING, logger=LOG):
        assert db.purge_old_session_events(retain_days=30) == 0
    assert _kayitlar(caplog, "Session event retention temizleme uyarısı", logging.WARNING)


# ── end_session ──────────────────────────────────────────────────────────────


def test_end_session_SURE_HESAPLANAMAZSA_0_dk_ve_uyari(db, caplog):
    """session_date bozuk + süre verilmedi → seans 'completed', duration 0 (kapanış düşmez) + 'Sure hesaplanamadi' uyarısı."""
    sid = _seans(db)
    _sql(db, "UPDATE treatment_sessions SET session_date = 'bozuk' WHERE id = ?", (sid,))
    with caplog.at_level(logging.WARNING, logger=LOG):
        db.end_session(sid)
    assert tuple(_tek(db, "SELECT session_status, duration_minutes FROM treatment_sessions WHERE id=?", (sid,))) == (
        "completed",
        0,
    )
    assert _kayitlar(caplog, "Sure hesaplanamadi", logging.WARNING)


def test_end_session_PULSE_sutuna_PII_parametresi_OPT_IN_maskeyle_yazilir(db, monkeypatch):
    """parametreler: pulse_duration_ms → sütun; patient_owner (PII) + PEMF_MASK_HISTORY_PII=1 (düz DB) → '[SIFRELENMEMIS-DB]';
    PII olmayan parametre AYNEN."""
    assert db.at_rest_encrypted is False
    monkeypatch.setenv("PEMF_MASK_HISTORY_PII", "1")
    sid = _seans(db)
    db.end_session(
        sid, parameters={"pulse_duration_ms": 12.5, "patient_owner": "Ayse Yilmaz", "kp_param": 3}, duration_minutes=4
    )
    assert _tek(db, "SELECT pulse_duration_ms FROM treatment_sessions WHERE id=?", (sid,))[0] == 12.5
    p = dict(_tek_tum(db, "SELECT parameter_name, parameter_value FROM session_parameters WHERE session_id=?", (sid,)))
    assert p["patient_owner"] == TreatmentHistoryDB._PII_REDACTION
    assert p["kp_param"] == "3"
    assert "pulse_duration_ms" not in p


def _tek_tum(db, sorgu, par=()):
    with db._get_connection() as c:
        return [tuple(r) for r in c.execute(sorgu, par).fetchall()]


# ── Geçmiş / ayrıntı / istatistik ────────────────────────────────────────────


def test_gecmis_TARIH_ve_KIP_suzgecleri(db):
    """3 seans (2026-01-10 Manuel, 2026-02-15 Otomatik, 2026-03-20 Manuel): başlangıç ≥ 02-01 → 2; bitiş ≤ 02-28 → 2; kip Manuel → 2;
    üçü birlikte (02-01..03-31, Manuel) → yalnız 03-20."""
    ids = {}
    for tarih, kip in (("2026-01-10", "Manuel"), ("2026-02-15", "Otomatik"), ("2026-03-20", "Manuel")):
        sid = _seans(db, kip=kip)
        _sql(db, "UPDATE treatment_sessions SET session_date = ? WHERE id = ?", (tarih, sid))
        ids[tarih] = sid

    def _ids(**k):
        return sorted(s["id"] for s in db.get_session_history(**k))

    assert _ids(start_date="2026-02-01") == sorted([ids["2026-02-15"], ids["2026-03-20"]])
    assert _ids(end_date="2026-02-28") == sorted([ids["2026-01-10"], ids["2026-02-15"]])
    assert _ids(treatment_mode="Manuel") == sorted([ids["2026-01-10"], ids["2026-03-20"]])
    assert _ids(start_date="2026-02-01", end_date="2026-03-31", treatment_mode="Manuel") == [ids["2026-03-20"]]


@pytest.mark.parametrize(
    "tablo,cagri",
    [
        ("session_parameters", lambda d, s: d.get_session_history()),
        ("session_parameters", lambda d, s: d.get_session_details(s)),
        ("treatment_sessions", lambda d, s: d.get_statistics()),
        ("treatment_sessions", lambda d, s: d.update_session_notes(s, "not")),
    ],
    ids=["gecmis", "ayrinti", "istatistik", "not"],
)
def test_okuma_yazma_DB_HATASI_YUKSELTILIR_ve_gunlukte(db, caplog, tablo, cagri):
    """tablo yok → sqlite3.OperationalError ÇAĞIRANA yükselir (boş liste / sessiz başarı YOK) + hata günlükte."""
    sid = _seans(db)
    _sql(db, f"DROP TABLE {tablo}")
    with caplog.at_level(logging.ERROR, logger=LOG), pytest.raises(sqlite3.OperationalError, match="no such table"):
        cagri(db, sid)
    assert [r for r in caplog.records if r.levelno == logging.ERROR and "no such table" in r.getMessage()]


# ── Kimliksiz not eşleme yardımcıları ────────────────────────────────────────


def test_not_esleme_BOS_AD_guvenli_degerler():
    """boş / yalnız boşluk ad → kimlik None, aday 0, belirsiz değil (DB'ye gitmeden)."""
    d = TreatmentHistoryDB.__new__(TreatmentHistoryDB)  # DB'siz: boş adda bağlantı AÇILMAMALI
    assert d.son_biten_seans_kimligi("   ") is None
    assert d.son_biten_seans_aday_sayisi("") == 0
    assert d.son_biten_seans_belirsiz_mi(None) is False


def test_not_esleme_DB_HATASINDA_guvenli_degerler_ve_gunluk(db, caplog):
    """treatment_sessions yok → kimlik None, aday 0, seans özeti None (yükseltmez) + her biri için hata kaydı."""
    _sql(db, "DROP TABLE treatment_sessions")
    with caplog.at_level(logging.ERROR, logger=LOG):
        assert db.son_biten_seans_kimligi("Pamuk") is None
        assert db.son_biten_seans_aday_sayisi("Pamuk") == 0
        assert db.seans_ozeti(1) is None
    for parca in ("son_biten_seans_kimligi hatası", "son_biten_seans_aday_sayisi hatası", "seans_ozeti hatası"):
        assert _kayitlar(caplog, parca, logging.ERROR), parca


# ── Yazım yok kolları ────────────────────────────────────────────────────────


def test_KIMLIKSIZ_ya_da_ALANSIZ_cagrilar_HICBIR_SEY_yazmaz(db, caplog):
    """update_session_finalized_extras(0) · set_session_meta(alan yok) · set_session_parameter(kimlik/ad yok) → yazım YOK
    (total_changes değişmez); set_session_parameter False döner. Bu çağrılar olağan "yapacak iş yok" kollarıdır → HATA KAYDI
    BIRAKMAZLAR ('set_session_meta hatası' ERROR kaydı yok; boş SET'li UPDATE denenmez). Aynı kaydın caplog'a düştüğü
    test_set_session_meta_DB_HATASI_yukseltmez_gunlukte ile kanıtlı."""
    sid = _seans(db)
    once = _degisim(db)
    with caplog.at_level(logging.ERROR, logger=LOG):
        assert db.update_session_finalized_extras(0, notes="x") is None
        assert db.set_session_meta(sid) is None
        assert db.set_session_parameter(None, "patient_owner_email", "a@b.c") is False
        assert db.set_session_parameter(sid, "", "deger") is False
    assert _degisim(db) == once
    assert _kayitlar(caplog, "set_session_meta hatası") == []
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_set_session_meta_DB_HATASI_yukseltmez_gunlukte(db, caplog):
    """treatment_sessions yok → set_session_meta istisna ATMAZ (best-effort) + 'set_session_meta hatası'."""
    sid = _seans(db)
    _sql(db, "DROP TABLE treatment_sessions")
    with caplog.at_level(logging.ERROR, logger=LOG):
        assert db.set_session_meta(sid, frequency_hz=7.0) is None
    assert _kayitlar(caplog, "set_session_meta hatası", logging.ERROR)


def test_upsert_patient_AD_YOKSA_atlanir_None_ve_uyari(db, caplog):
    """{'name': ''} → None, patients tablosuna satır eklenmez + 'name zorunlu' uyarısı."""
    once = _tek(db, "SELECT COUNT(*) FROM patients")[0]
    with caplog.at_level(logging.WARNING, logger=LOG):
        assert db.upsert_patient({"name": "", "owner_name": "x"}) is None
    assert _tek(db, "SELECT COUNT(*) FROM patients")[0] == once
    assert _kayitlar(caplog, "'name' zorunlu", logging.WARNING)


# ── Sahiplik / silme ─────────────────────────────────────────────────────────


def test_seans_sahipleri_GECERSIZ_kimlikler_atlanir(db):
    """['x', None, ''] / None → {} (DB'ye gitmeden: bağlantıda HİÇ SQL koşmaz — SQLite motorunun iz geri çağrısıyla ölçülür);
    ['x', sid, None, str(sid2)] → yalnız geçerli ikisi, e-postalarıyla (karşıt: bu çağrının SELECT'i izde görünür)."""
    s1 = _seans(db, email="a@klinik.tr")
    s2 = _seans(db, email=None)
    sorgular: list = []
    with db._get_connection() as c:  # iş parçacığına bağlı havuz bağlantısı — ürünün aynı iş parçacığında kullanacağı
        c.set_trace_callback(sorgular.append)
    try:
        assert db.seans_sahipleri(["x", None, ""]) == {}
        assert db.seans_sahipleri(None) == {}
        assert sorgular == [], sorgular
        assert db.seans_sahipleri(["x", s1, None, str(s2)]) == {s1: "a@klinik.tr", s2: ""}
        assert any("FROM treatment_sessions WHERE id IN" in s for s in sorgular), sorgular
    finally:
        with db._get_connection() as c:
            c.set_trace_callback(None)


def test_seans_silme_DB_HATASINDA_ATOMIK_hicbir_sey_gitmez(db, caplog):
    """sensor_samples tablosu yok → delete_session yükseltir; seans ve parametresi YERİNDE (işlem geri alındı)."""
    sid = _seans(db)
    db.set_session_parameter(sid, "kp", "1")
    _sql(db, "DROP TABLE sensor_samples")
    with caplog.at_level(logging.ERROR, logger=LOG), pytest.raises(sqlite3.OperationalError):
        db.delete_session(sid)
    assert _tek(db, "SELECT COUNT(*) FROM treatment_sessions WHERE id=?", (sid,))[0] == 1
    assert _tek(db, "SELECT COUNT(*) FROM session_parameters WHERE session_id=?", (sid,))[0] == 1
    assert _kayitlar(caplog, "Seans silme hatası", logging.ERROR)


def test_toplu_silme_GECERSIZLER_atlanir_DENETLENMEMIS_silinmez(db):
    """geçersizler atlanır: ['x', None, s1, str(s2)] → 2 silinir; yalnız geçersiz → 0; denetlenmiş küme dışı kimlik → 0, seans yerinde."""
    s1, s2, s3 = _seans(db), _seans(db), _seans(db)
    assert db.delete_sessions_bulk(["x", None]) == 0
    assert db.delete_sessions_bulk([s3], yalniz={999999}) == 0
    assert _tek(db, "SELECT COUNT(*) FROM treatment_sessions WHERE id=?", (s3,))[0] == 1
    assert db.delete_sessions_bulk(["x", None, s1, str(s2)]) == 2
    kalan = [r[0] for r in _tek_tum(db, "SELECT id FROM treatment_sessions ORDER BY id")]
    assert kalan == [s3]


def test_toplu_silme_DB_HATASINDA_ATOMIK_ve_yukseltir(db, caplog):
    """sensor_samples yok → delete_sessions_bulk yükseltir; iki seans da YERİNDE."""
    s1, s2 = _seans(db), _seans(db)
    _sql(db, "DROP TABLE sensor_samples")
    with caplog.at_level(logging.ERROR, logger=LOG), pytest.raises(sqlite3.OperationalError):
        db.delete_sessions_bulk([s1, s2])
    assert _tek(db, "SELECT COUNT(*) FROM treatment_sessions WHERE id IN (?, ?)", (s1, s2))[0] == 2
    assert _kayitlar(caplog, "Toplu seans silme hatası", logging.ERROR)


def test_kritik_olay_ayirma_BOZUK_ve_SOZLUK_DISI_yuk_HAM_korunur(db):
    """seans silinirken kritik olayların yükü bozuk JSON → {'_ham_yuk': '<metin>'}, JSON liste → {'_ham_yuk': [..]}; ikisine de
    'silinen_seans_id' eklenir, session_id NULL, olaylar SİLİNMEZ. Boş kimlik listesi → 0 (dokunulmaz)."""
    sid = _seans(db)
    e1 = db.record_session_event(sid, "emergency_stop", {"neden": "x"}, severity="critical")
    e2 = db.record_session_event(sid, "kp_uyari", {"a": 1}, severity="warning")
    _sql(db, "UPDATE session_events SET payload = ? WHERE id = ?", ("bozuk{", e1))
    _sql(db, "UPDATE session_events SET payload = ? WHERE id = ?", ("[1, 2]", e2))
    with db._get_connection() as c:
        assert db._kritik_olaylari_seanstan_ayir(c.cursor(), []) == 0
    db.delete_session(sid)
    satirlar = {
        r[0]: (r[1], json.loads(r[2])) for r in _tek_tum(db, "SELECT id, session_id, payload FROM session_events")
    }
    assert satirlar[e1] == (None, {"_ham_yuk": "bozuk{", "silinen_seans_id": sid})
    assert satirlar[e2] == (None, {"_ham_yuk": [1, 2], "silinen_seans_id": sid})
