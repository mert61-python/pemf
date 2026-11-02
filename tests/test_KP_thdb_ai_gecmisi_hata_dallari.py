# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/database/thdb_ai_gecmisi.py · sözleşmeler: hekim değerlendirmesi (geçersiz durum, bozuk geçmiş, kilitli
DB), tekil / toplu silme hata dalları, operatörsüz cihazda "her sahip sahipsiz" kapsamı, silme sonrası denetim noktası ve
ertelenmiş KVKK VACUUM işareti (yazılamaz / okunamaz / VACUUM kilitli), Türkçe katlayıcı yokken kimlik taşıması, liste
süzgeci + bozuk JSON alanları + okunamayan DB.

GERÇEK `TreatmentHistoryDB` (tmp_path). Sahte EN ALT katta: sqlite3 bağlantısı — gerçek bağlantıyı saran ve seçilen SQL
deyiminde gerçek arıza biçimiyle (`sqlite3.OperationalError: database is locked`) yükselen sarmalayıcı (`_create_connection`
üretir; havuz önce kapatılır); içe aktarma (`builtins.__import__`, yalnız `utils.turkce_metin`). `vacuum_bekliyor_mu`nun
okuma hatası dalı, karışımın (mixin) beyan ettiği ana-sınıf arayüzü (`_get_system_setting`) yükselen asgari bir evsahibiyle
sınanır — gerçek `_get_system_setting` kendi hatasını yuttuğu için o dal gerçek sınıfta tetiklenemez.
"""

from __future__ import annotations

import builtins
import json
import logging
import sqlite3

import pytest
from database.thdb_ai_gecmisi import AiGecmisiKarisimi

_GUNLUKCU = "database.treatment_history_db"


class _KilitliImlec:
    def __init__(self, gercek, kilitli):
        self._g = gercek
        self._k = kilitli

    def execute(self, sql, *a):
        if self._k(sql):
            raise sqlite3.OperationalError("database is locked")
        self._g.execute(sql, *a)
        return self

    def __getattr__(self, ad):
        return getattr(self._g, ad)


class _KilitliBaglanti:
    """Gerçek sqlite3 bağlantısı; `kilitli(sql)` doğru olan deyimde 'database is locked' verir, gerisi aynen geçer."""

    def __init__(self, gercek, kilitli):
        self._g = gercek
        self._k = kilitli

    def execute(self, sql, *a):
        if self._k(sql):
            raise sqlite3.OperationalError("database is locked")
        return self._g.execute(sql, *a)

    def cursor(self):
        return _KilitliImlec(self._g.cursor(), self._k)

    def __getattr__(self, ad):
        return getattr(self._g, ad)


@pytest.fixture
def db(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def _kilitle(monkeypatch, db, kosul):
    """Havuzu kapatır; bundan sonra açılan her bağlantı `kosul(sql)` doğru olan deyimde kilitli DB hatası verir."""
    gercek = db._create_connection
    db.close_connections()
    monkeypatch.setattr(db, "_kp_gercek_baglanti", gercek, raising=False)
    monkeypatch.setattr(db, "_create_connection", lambda: _KilitliBaglanti(gercek(), kosul))


def _kilidi_ac(monkeypatch, db):
    """Kilitli bağlantıları kapatır, gerçek bağlantı üreticisini geri koyar (yalnız bu yama; diğer yamalar sürer)."""
    db.close_connections()
    monkeypatch.setattr(db, "_create_connection", db._kp_gercek_baglanti)


def _ham_guncelle(db, sql, *param):
    with db._get_connection() as c:
        c.execute(sql, param)
        c.commit()


def _kayit(db, **k):
    alan = {
        "module_id": "kedi_organ",
        "patient_name": "Pamuk",
        "result_summary": "ozet",
        "operator_email": "dr.a@klinik.com",
    }
    alan.update(k)
    aid = db.add_ai_analysis(**alan)
    assert isinstance(aid, int)
    return aid


def _satir(db, aid):
    return {d["id"]: d for d in db.get_ai_analyses(limit=500)}.get(aid)


# ───────────────────────────── hekim değerlendirmesi ─────────────────────────────


def test_degerlendirme_GECERSIZ_durum_ValueError_kayit_DEGISMEZ(db):
    """status 'onaylandi' (izinli üçlünün dışı) → ValueError('Geçersiz değerlendirme durumu: onaylandi'); kayıt değerlendirmesiz."""
    aid = _kayit(db)
    with pytest.raises(ValueError, match="Geçersiz değerlendirme durumu: onaylandi"):
        db.set_ai_review(aid, "onaylandi", "not", "dr.a")
    assert _satir(db, aid)["review_status"] == ""


def test_degerlendirme_BOZUK_gecmis_JSONu_yeni_liste_baslatir_onceki_karar_KORUNUR(db, caplog):
    """Önceki 'rejected' kararı varken geçmiş alanı bozuk JSON → uyarı + liste baştan; yeni 'approved' yazılır ve geçmişte
    YALNIZ önceki karar (metniyle) durur."""
    aid = _kayit(db)
    assert db.set_ai_review(aid, "rejected", "bulgu uyusmuyor", "dr.a") is True
    _ham_guncelle(db, "UPDATE ai_analyses SET review_history = ? WHERE id = ?", "{bozuk", aid)
    with caplog.at_level(logging.WARNING, logger=_GUNLUKCU):
        assert db.set_ai_review(aid, "approved", "tekrar bakildi", "dr.b") is True
    s = _satir(db, aid)
    assert (s["review_status"], s["review_note"], s["reviewed_by"]) == ("approved", "tekrar bakildi", "dr.b")
    assert [(g["status"], g["note"], g["reviewed_by"]) for g in s["review_history"]] == [
        ("rejected", "bulgu uyusmuyor", "dr.a")
    ]
    assert any(f"AI değerlendirme geçmişi okunamadı (id={aid})" in r.getMessage() for r in caplog.records)


def test_degerlendirme_DB_KILITLI_ise_False_kayit_DEGISMEZ(db, monkeypatch, caplog):
    """Değerlendirme UPDATE'i 'database is locked' → False + 'AI değerlendirmesi yazılamadı' uyarısı; kilit kalkınca kayıt
    değerlendirmesiz (yarım yazım yok)."""
    aid = _kayit(db)
    _kilitle(monkeypatch, db, lambda s: s.lstrip().startswith("UPDATE ai_analyses SET review_status"))
    with caplog.at_level(logging.WARNING, logger=_GUNLUKCU):
        assert db.set_ai_review(aid, "approved", "x", "dr.a") is False
    assert any("AI değerlendirmesi yazılamadı: database is locked" in r.getMessage() for r in caplog.records)
    _kilidi_ac(monkeypatch, db)
    assert _satir(db, aid)["review_status"] == ""


# ───────────────────────────── silme ─────────────────────────────


def test_tekil_silme_DB_KILITLI_ise_False_kayit_DURUR(db, monkeypatch, caplog):
    """DELETE 'database is locked' → False + istisna günlüğü; kayıt yerinde kalır."""
    aid = _kayit(db)
    _kilitle(monkeypatch, db, lambda s: s.lstrip().startswith("DELETE FROM ai_analyses"))
    with caplog.at_level(logging.ERROR, logger=_GUNLUKCU):
        assert db.delete_ai_analysis(aid) is False
    kayit = [r for r in caplog.records if r.getMessage() == f"AI analiz kaydı silinemedi (id={aid})."]
    assert len(kayit) == 1 and kayit[0].exc_info[0] is sqlite3.OperationalError
    _kilidi_ac(monkeypatch, db)
    assert _satir(db, aid) is not None


def test_toplu_silme_OPERATORSUZ_cihazda_HER_sahip_sahipsiz_sayilir(db):
    """sahipsiz_dahil + kayıtlı e-posta kümesi boş (yalnız boşluk) → kapsam '1 = 1': kendi + sahipsiz + BAŞKA hekimin kaydı
    silinir (3). Karşıt: kayıtlı küme {dr.b} → dr.b'nin kaydı kalır (2 silinir)."""
    _kayit(db, operator_email="dr.a@klinik.com")
    _kayit(db, operator_email="dr.b@klinik.com")
    _kayit(db, operator_email="")
    assert db.clear_ai_analyses("dr.a@klinik.com", sahipsiz_dahil=True, kayitli_epostalar=["dr.b@klinik.com"]) == 2
    assert [d["operator_email"] for d in db.get_ai_analyses()] == ["dr.b@klinik.com"]
    _kayit(db, operator_email="dr.a@klinik.com")
    _kayit(db, operator_email="")
    assert db.clear_ai_analyses("DR.A@klinik.com ", sahipsiz_dahil=True, kayitli_epostalar=["  ", ""]) == 3
    assert db.get_ai_analyses() == []


def test_toplu_silme_DB_KILITLI_ise_EKSI_1_kayitlar_DURUR(db, monkeypatch, caplog):
    """Toplu DELETE 'database is locked' → -1 ('temizlenemedi') + istisna günlüğü; kayıtlar yerinde."""
    _kayit(db)
    _kayit(db, operator_email="")
    _kilitle(monkeypatch, db, lambda s: s.lstrip().startswith("DELETE FROM ai_analyses"))
    with caplog.at_level(logging.ERROR, logger=_GUNLUKCU):
        assert db.clear_ai_analyses() == -1
    assert any(r.getMessage() == "AI analiz geçmişi temizlenemedi." for r in caplog.records)
    _kilidi_ac(monkeypatch, db)
    assert len(db.get_ai_analyses()) == 2


# ───────────────────────────── denetim noktası / ertelenmiş VACUUM ─────────────────────────────


def test_denetim_noktasi_KILITLI_ise_False_ve_VACUUM_bekliyor_isareti_KALICI(db, caplog):
    """WAL denetim noktası 'database is locked' → False + uyarı; kalıcı 'VACUUM bekliyor' işareti yazılır (bakım yeniden dener);
    denetim noktası KISA beklemeyle (`DENETIM_NOKTASI_BEKLEME_MS`) denenir ve hata sonrası bağlantının `busy_timeout`u ÇAĞRIDAN
    ÖNCEKİ değerine döner (finally — 0'a / sabite DEĞİL: 0 = kilitte beklemeden düşer, A-07 · F2-4.3). TUR 2 · KP1-IB.3."""
    assert db.vacuum_bekliyor_mu() is False
    ONCEKI = 4321  # bağlantının kendi değeri, sabit bekleme süresi ve 0'dan AYIRT edilebilir
    with db._get_connection() as c:
        varsayilan = c.execute("PRAGMA busy_timeout").fetchone()[0]
        assert ONCEKI not in (0, varsayilan, db.DENETIM_NOKTASI_BEKLEME_MS)
        c.execute(f"PRAGMA busy_timeout={ONCEKI}")
        denemede = []

        def _kilitli(sql):
            if "wal_checkpoint" in sql:
                denemede.append(c.execute("PRAGMA busy_timeout").fetchone()[0])
                return True
            return False

        sarili = _KilitliBaglanti(c, _kilitli)
        try:
            with caplog.at_level(logging.WARNING, logger=_GUNLUKCU):
                assert db._silme_sonrasi_denetim_noktasi(sarili, "KP deneme") is False
            assert denemede == [db.DENETIM_NOKTASI_BEKLEME_MS]
            # bekleme süresi ÇAĞRIDAN ÖNCEKİ değerine döndü (finally)
            assert c.execute("PRAGMA busy_timeout").fetchone()[0] == ONCEKI
        finally:
            c.execute(f"PRAGMA busy_timeout={int(varsayilan)}")  # havuzdaki bağlantı kendi değerine
    assert any(r.getMessage() == "KP deneme: silme sonrasi denetim noktasi yapilamadi." for r in caplog.records)
    assert db.vacuum_bekliyor_mu() is True


def test_VACUUM_bekleme_isareti_YAZILAMAZSA_yukselmez_isaret_YOK(db, monkeypatch, caplog):
    """system_settings yazımı 'database is locked' → `_vacuum_beklet` yükselmez, hata günlüğü (nedenle); işaret yazılmamıştır."""
    _kilitle(monkeypatch, db, lambda s: "INSERT INTO system_settings" in s)
    with caplog.at_level(logging.ERROR, logger=_GUNLUKCU):
        db._vacuum_beklet("KP neden")
    kayit = [r for r in caplog.records if r.getMessage() == "KVKK VACUUM bekleme isareti YAZILAMADI (KP neden)"]
    assert len(kayit) == 1 and kayit[0].exc_info[0] is sqlite3.OperationalError
    assert db.vacuum_bekliyor_mu() is False


class _AyarOkuyamayanEv(AiGecmisiKarisimi):
    """Karışımın beyan ettiği ana-sınıf arayüzü: ayar okuyucu yükselir (ör. bozuk DB dosyası)."""

    logger = logging.getLogger("kp.ai_gecmisi_ev")

    def __init__(self):
        self.vacuum = 0

    def _get_system_setting(self, anahtar):
        raise sqlite3.DatabaseError("file is not a database")

    def _get_connection(self):  # çağrılmamalı: ayar okunamazken VACUUM denenmez
        self.vacuum += 1
        raise AssertionError("ayar okunamazken VACUUM'a geçilmemeli")


def test_VACUUM_bekliyor_mu_AYAR_OKUNAMAZSA_False_ve_VACUUM_DENENMEZ():
    """Ayar okuyucu yükselir → vacuum_bekliyor_mu False (yükselmez); bekleyen_vacuum_calistir False ve bağlantı AÇILMAZ."""
    ev = _AyarOkuyamayanEv()
    assert ev.vacuum_bekliyor_mu() is False
    assert ev.bekleyen_vacuum_calistir() is False
    assert ev.vacuum == 0


def test_bekleyen_VACUUM_kilitliyse_False_isaret_KALIR(db, monkeypatch, caplog):
    """İşaret '1' + VACUUM 'database is locked' → False + uyarı; işaret '1' KALIR (sonraki bakım yeniden dener)."""
    db._vacuum_beklet("KP")
    assert db.vacuum_bekliyor_mu() is True
    _kilitle(monkeypatch, db, lambda s: s.strip().upper() == "VACUUM")
    with caplog.at_level(logging.WARNING, logger=_GUNLUKCU):
        assert db.bekleyen_vacuum_calistir() is False
    assert any("Ertelenmis KVKK VACUUM'u yine yapilamadi" in r.getMessage() for r in caplog.records)
    _kilidi_ac(monkeypatch, db)
    assert db.vacuum_bekliyor_mu() is True


# ───────────────────────────── kimlik taşıması ─────────────────────────────


def test_kimlik_tasimasi_TURKCE_KATLAYICI_yoksa_ATLANIR_kayitlar_DEGISMEZ(db, monkeypatch, caplog):
    """`utils.turkce_metin` içe aktarılamaz → sonuç {0,0,0} (hata anahtarı yok), uyarı; kimliksiz kayıt kimliksiz kalır."""
    aid = _kayit(db, patient_name="Pamuk")
    gercek = builtins.__import__

    def _ice_aktar(ad, *a, **k):
        if ad == "utils.turkce_metin":
            raise ModuleNotFoundError("No module named 'utils.turkce_metin'", name=ad)
        return gercek(ad, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _ice_aktar)
    with caplog.at_level(logging.WARNING, logger=_GUNLUKCU):
        sonuc = db.ai_analiz_kimliklerini_doldur({"pamuk": "uuid-1"})
    monkeypatch.setattr(builtins, "__import__", gercek)
    assert sonuc == {"guncellenen": 0, "kimliksiz_kalan": 0, "atlanmis_ad": 0}
    assert any("Turkce katlayici yok" in r.getMessage() for r in caplog.records)
    assert _satir(db, aid)["patient_uuid"] == ""


# ───────────────────────────── liste ─────────────────────────────


def test_liste_MODUL_suzgeci_yalniz_o_modulun_kayitlari(db):
    """module_id 'petri' → yalnız petri kayıtları (yeni önce); süzgeçsiz → hepsi."""
    a = _kayit(db, module_id="kedi_organ")
    b = _kayit(db, module_id="petri")
    c = _kayit(db, module_id="petri")
    assert [d["id"] for d in db.get_ai_analyses(module_id="petri")] == [c, b]
    assert [d["id"] for d in db.get_ai_analyses()] == [c, b, a]


def test_liste_BOZUK_JSON_alanlari_bos_degere_duser(db):
    """result_detail ve review_history bozuk JSON → {} ve []; sağlam kaydın alanları çözülür."""
    bozuk = _kayit(db, result_detail={"a": 1})
    saglam = _kayit(db, result_detail={"b": 2})
    _ham_guncelle(
        db, "UPDATE ai_analyses SET result_detail = ?, review_history = ? WHERE id = ?", "{x", "[bozuk", bozuk
    )
    s = {d["id"]: d for d in db.get_ai_analyses()}
    assert s[bozuk]["result_detail"] == {} and s[bozuk]["review_history"] == []
    assert s[saglam]["result_detail"] == {"b": 2} and s[saglam]["review_history"] == []


def test_liste_DB_OKUNAMAZSA_bos_liste_ve_uyari(db, monkeypatch, caplog):
    """Liste SELECT'i 'database is locked' → [] + 'AI analiz geçmişi okunamadı' uyarısı (yükselmez)."""
    _kayit(db)
    _kilitle(monkeypatch, db, lambda s: "FROM ai_analyses" in s and s.lstrip().startswith("SELECT id, created_at"))
    with caplog.at_level(logging.WARNING, logger=_GUNLUKCU):
        assert db.get_ai_analyses() == []
    assert any("AI analiz geçmişi okunamadı: database is locked" in r.getMessage() for r in caplog.records)
    _kilidi_ac(monkeypatch, db)
    assert len(db.get_ai_analyses()) == 1
