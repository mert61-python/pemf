# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: AI analiz GEÇMİŞİ — eski düz-metin `ai_diagnoses.jsonl` taşıması
(geçerli satırlar şifreli tabloya `legacy` işaretiyle girer, bozuk satır atlanır, dosya `.migrated` olur; okunamayan dosya
taşınmaz ve günlüğe yazılır; kilit beklerken başka iş parçacığı taşıdıysa ikinci kez EKLENMEZ), ad→kimlik taşıması (kilit
beklerken başka iş parçacığı bitirdiyse hasta defteri okunmaz; adı ya da kimliği boş hasta haritaya girmez), kimlikten hasta adı
(defter okunamazsa ""), uçlar: değerlendirme / liste / tek kayıt / PDF / tekil silme / toplu silme — tedavi DB'si yoksa ürünün
kendi durum kodu + metni; liste yürütücüsü kapalıysa `status: error` + boş liste; PDF üreticisi disk hatası verirse 500
`raporOlusmadi`; toplu silme DB'de düşerse 500 `temizlenemedi` + `ai_log.delete_all` / `hata` denetim izi.

Sahte EN ALT katta: tedavi DB'si GERÇEK (`TreatmentHistoryDB`, tmp); arızalar bağlantı (`_get_connection` → OperationalError),
hasta defteri (`database.patient_database.get_patient_database`), PDF üreticisi (`utils.pdf_report_generator.get_pdf_generator`
→ OSError ENOSPC), olay döngüsü yürütücüsü (`asyncio.to_thread` → "cannot schedule new futures after shutdown"), kilit (bekleme
sırasında öteki iş parçacığının işi bitirmesi: `__enter__` kancası).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

CIHAZ = ("127.0.0.1", 50141)


def _tr(anahtar, **k):
    from utils import ceviri

    return ceviri.t(anahtar, dil="tr", **k)


def _log(caplog):
    return [r.getMessage() for r in caplog.records]


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as a

    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *x, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    (tmp_path / "gecmis").mkdir()
    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(a, "_ai_kimlik_tasindi", False)
    monkeypatch.setattr(a, "_RL_REMOTE_MAX", 0)
    try:
        yield SimpleNamespace(a=a, db=db, tmp=tmp_path)
    finally:
        try:
            db._reset_thread_conn()
        except Exception:
            pass


class _KancaliKilit:
    """Gerçek kilide yönlendirir; `__enter__`ta, kilit alınmadan HEMEN önce `kanca` koşar (bekleme sırasında öteki iş
    parçacığının işini bitirmesi)."""

    def __init__(self, gercek, kanca):
        self.gercek, self.kanca, self.giris = gercek, kanca, 0

    def __enter__(self):
        self.giris += 1
        self.kanca()
        return self.gercek.__enter__()

    def __exit__(self, *e):
        return self.gercek.__exit__(*e)


def _jsonl(o, satirlar) -> object:
    p = o.a._app_data_dir() / "ai_diagnoses.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    return p


# ── _migrate_ai_jsonl_once ─────────────────────────────────────────────────────────────────────────────────────────────────────


def test_JSONL_TASIMA_gecerli_satirlar_legacy_kayit_bozuk_satir_atlanir_dosya_migrated(o):
    """2 geçerli + 1 bozuk satır → 2 kayıt (modül etiketi / hasta / özet, `result_detail.legacy` True + özgün zaman damgası);
    dosya `ai_diagnoses.jsonl.migrated` adına taşınır, özgün ad kalmaz."""
    p = _jsonl(
        o,
        [
            json.dumps(
                {"module": "Deri", "patient_name": "Mia", "summary": "egzama", "timestamp": "2026-01-02T10:00:00"}
            ),
            "{bozuk satir",
            json.dumps(
                {"module": "Göz", "patient_name": "Pamuk", "summary": "temiz", "timestamp": "2026-01-03T11:00:00"}
            ),
        ],
    )
    o.a._migrate_ai_jsonl_once(o.db)
    kayit = sorted(o.db.get_ai_analyses(10), key=lambda k: k["id"])
    assert [(k["module_label"], k["patient_name"], k["result_summary"]) for k in kayit] == [
        ("Deri", "Mia", "egzama"),
        ("Göz", "Pamuk", "temiz"),
    ]
    detay = [
        k["result_detail"] if isinstance(k["result_detail"], dict) else json.loads(k["result_detail"]) for k in kayit
    ]
    assert detay == [
        {"legacy": True, "timestamp": "2026-01-02T10:00:00"},
        {"legacy": True, "timestamp": "2026-01-03T11:00:00"},
    ]
    assert not p.exists() and p.with_name("ai_diagnoses.jsonl.migrated").exists()


def test_JSONL_TASIMA_okunamayan_dosya_TASINMAZ_gunluge_yazilir(o, caplog):
    """Dosya UTF-8 değil (okuma UnicodeDecodeError) → kayıt eklenmez, dosya YERİNDE kalır, "ai jsonl migrate failed" yazılır."""
    p = o.a._app_data_dir() / "ai_diagnoses.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\xff\xfe\x00bozuk")
    caplog.set_level(logging.ERROR)
    o.a._migrate_ai_jsonl_once(o.db)
    assert o.db.get_ai_analyses(10) == []
    assert p.exists() and not p.with_name("ai_diagnoses.jsonl.migrated").exists()
    assert "ai jsonl migrate failed" in _log(caplog)


def test_JSONL_TASIMA_kilit_beklerken_OTEKI_is_parcacigi_tasidiysa_IKINCI_kez_eklenmez(o, monkeypatch, caplog):
    """Hızlı yolda dosya var; kilit beklenirken öteki iş parçacığı dosyayı taşıdı → kilit altındaki yeniden denetim SESSİZCE
    döner: kayıt EKLENMEZ (çift kayıt yok), "ai jsonl migrate failed" YAZILMAZ (olmayan dosya okunmaya çalışılmaz)."""
    p = _jsonl(o, [json.dumps({"module": "Deri", "patient_name": "Mia", "summary": "x"})])
    kilit = _KancaliKilit(o.a._ai_migrate_lock, lambda: p.rename(p.with_name("ai_diagnoses.jsonl.migrated")))
    monkeypatch.setattr(o.a, "_ai_migrate_lock", kilit)
    caplog.set_level(logging.ERROR)
    o.a._migrate_ai_jsonl_once(o.db)
    assert kilit.giris == 1
    assert o.db.get_ai_analyses(10) == []
    assert "ai jsonl migrate failed" not in _log(caplog)


# ── _ai_hasta_kimliklerini_tasi_bir_kez · _hasta_adi_kimlikten ─────────────────────────────────────────────────────────────────


def test_KIMLIK_TASIMA_kilit_beklerken_OTEKI_bitirdiyse_defter_OKUNMAZ(o, monkeypatch):
    """Süreç bayrağı kapalıyken girildi; kilit beklenirken öteki iş parçacığı taşımayı bitirdi (bayrak açık) → {} döner, hasta
    defteri hiç açılmaz, DB'ye kimlik yazılmaz."""
    from database import patient_database as pdbm

    acilan: list = []
    monkeypatch.setattr(pdbm, "get_patient_database", lambda *x, **k: acilan.append(1))
    yazilan: list = []
    monkeypatch.setattr(o.db, "ai_analiz_kimliklerini_doldur", lambda h: yazilan.append(h) or {})
    kilit = _KancaliKilit(o.a._ai_kimlik_tasima_lock, lambda: setattr(o.a, "_ai_kimlik_tasindi", True))
    monkeypatch.setattr(o.a, "_ai_kimlik_tasima_lock", kilit)
    assert o.a._ai_hasta_kimliklerini_tasi_bir_kez(o.db) == {}
    assert (kilit.giris, acilan, yazilan) == (1, [], [])


def test_KIMLIK_TASIMA_adi_ya_da_kimligi_BOS_hasta_haritaya_GIRMEZ(o, monkeypatch):
    """Defter: Mia (u-1), adsız (u-3), kimliksiz Boncuk → yalnız {"mia": "u-1"} DB'ye verilir; Mia'nın eski analizi u-1'e bağlanır,
    Boncuk'unki kimliksiz kalır; taşıma işareti konur."""
    from database import patient_database as pdbm

    defter = SimpleNamespace(
        get_all_patients=lambda kati=False: [
            {"id": "u-1", "name": "Mia"},
            {"id": "u-3", "name": ""},
            {"id": "", "name": "Boncuk"},
        ]
    )
    monkeypatch.setattr(pdbm, "get_patient_database", lambda *x, **k: defter)
    o.db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="a")
    o.db.add_ai_analysis(module_id="m", patient_name="Boncuk", result_summary="b")
    gercek = o.db.ai_analiz_kimliklerini_doldur
    verilen: list = []
    monkeypatch.setattr(o.db, "ai_analiz_kimliklerini_doldur", lambda h: verilen.append(dict(h)) or gercek(h))
    o.a._ai_hasta_kimliklerini_tasi_bir_kez(o.db)
    assert verilen == [{"mia": "u-1"}]
    kimlik = {k["patient_name"]: (k.get("patient_uuid") or "") for k in o.db.get_ai_analyses(10)}
    assert kimlik == {"Mia": "u-1", "Boncuk": ""}
    assert o.a._ai_kimlik_tasindi is True


def test_HASTA_ADI_kimlikten_defter_OKUNAMAZSA_bos_ve_uyari(o, monkeypatch, caplog):
    """Defter `get_patient` DatabaseError → "" (ad uydurulmaz) + uyarı "AI kaydi: hasta adi kimlikten okunamadi"; okunursa kırpılmış ad."""
    from database import patient_database as pdbm

    def _bozuk(_k):
        raise sqlite3.DatabaseError("file is not a database")

    monkeypatch.setattr(pdbm, "get_patient_database", lambda *x, **k: SimpleNamespace(get_patient=_bozuk))
    caplog.set_level(logging.WARNING)
    assert o.a._hasta_adi_kimlikten("u-1") == ""
    assert "AI kaydi: hasta adi kimlikten okunamadi (ad bos kaldi)." in _log(caplog)
    monkeypatch.setattr(
        pdbm, "get_patient_database", lambda *x, **k: SimpleNamespace(get_patient=lambda _k: {"name": "  Mia "})
    )
    assert o.a._hasta_adi_kimlikten("u-1") == "Mia"


# ── uçlar: tedavi DB'si YOK ────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("yontem", "yol", "govde", "kod", "anahtar"),
    [
        ("POST", "/api/ai/log/review", {"analysis_id": 1, "status": "approved"}, 503, "ai.hata.kayitDbKullanilamiyor"),
        ("GET", "/api/ai/log/7", None, 503, "ai.hata.kayitDbAcilamadi"),
        ("GET", "/api/ai/log/7/pdf", None, 503, "ai.hata.kayitDbAcilamadi"),
        ("POST", "/api/ai/log/delete", {"id": 7}, 500, "gecmis.hata.dbHazirDegil"),
        (
            "POST",
            "/api/ai/log/delete_all",
            {"confirm": "DELETE_ALL", "all_operators": True},
            500,
            "gecmis.hata.dbHazirDegil",
        ),
    ],
)
def test_AI_UCLARI_tedavi_DB_YOKSA_urun_kodu_ve_metni(o, monkeypatch, yontem, yol, govde, kod, anahtar):
    """Tedavi DB'si yok (`_get_treatment_db` None) → her uç kendi durum kodu + ürün metni (TR)."""
    monkeypatch.setattr(o.a, "_get_treatment_db", lambda: None)
    with TestClient(o.a.app, client=CIHAZ) as c:
        r = c.request(yontem, yol, json=govde)
    assert (r.status_code, r.json()["detail"]) == (kod, _tr(anahtar))


def test_AI_LISTE_tedavi_DB_YOKSA_basari_ve_BOS_liste(o, monkeypatch):
    """GET /api/ai/log + DB yok → 200 {"status": "success", "data": []} (liste ekranı hata göstermez)."""
    monkeypatch.setattr(o.a, "_get_treatment_db", lambda: None)
    with TestClient(o.a.app, client=CIHAZ) as c:
        r = c.get("/api/ai/log")
    assert (r.status_code, r.json()) == (200, {"status": "success", "data": []})


class _YurutucuKapali:
    """Gerçek `asyncio`ya yönlendirir; `to_thread` kapanmış varsayılan yürütücü gibi düşer."""

    def __init__(self, gercek):
        self._gercek = gercek

    def __getattr__(self, ad):
        return getattr(self._gercek, ad)

    async def to_thread(self, fn, *a, **k):
        raise RuntimeError("cannot schedule new futures after shutdown")


def test_AI_LISTE_okuma_yurutucusu_KAPALIYSA_hata_durumu_bos_liste(o, monkeypatch, caplog):
    """`to_thread` RuntimeError (yürütücü kapandı) → 200 {"status": "error", "detail": `ai.hata.logOkunamadi`, "data": []},
    günlükte "get_ai_log failed"."""
    o.db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="a")
    monkeypatch.setattr(o.a, "asyncio", _YurutucuKapali(asyncio))
    caplog.set_level(logging.ERROR)
    with TestClient(o.a.app, client=CIHAZ) as c:
        r = c.get("/api/ai/log")
    assert (r.status_code, r.json()) == (200, {"status": "error", "detail": _tr("ai.hata.logOkunamadi"), "data": []})
    assert "get_ai_log failed" in _log(caplog)


def test_AI_PDF_uretici_DISK_hatasi_500_rapor_olusmadi(o, monkeypatch, caplog):
    """Kayıt var; PDF üreticisi OSError(ENOSPC) → 500 `ai.hata.raporOlusmadi`, günlükte "ai_analiz_pdf failed"."""
    import errno

    from utils import pdf_report_generator as prg

    rid = o.db.add_ai_analysis(module_id="m", module_label="Deri", patient_name="Mia", result_summary="egzama")

    class _DoluDisk:
        def generate_xai_report(self, *a, **k):
            raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(prg, "get_pdf_generator", lambda *a, **k: _DoluDisk())
    caplog.set_level(logging.ERROR)
    with TestClient(o.a.app, client=CIHAZ) as c:
        r = c.get(f"/api/ai/log/{rid}/pdf")
    assert (r.status_code, r.json()["detail"]) == (500, _tr("ai.hata.raporOlusmadi"))
    assert "ai_analiz_pdf failed" in _log(caplog)


def test_AI_TOPLU_SILME_DB_de_DUSERSE_500_ve_HATA_izi(o, monkeypatch):
    """Operatörsüz klinik, cihazdan "Tüm Klinik" silme; silme sırasında DB bağlantısı kilitli (`clear_ai_analyses` → -1) → 500
    `gecmis.hata.temizlenemedi`; kayıt SİLİNMEZ; denetim izine `ai_log.delete_all` / `hata` / `TUM_KLINIK` / 0 yazılır."""
    o.db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="a")
    gercek_temizle, gercek_baglanti = o.db.clear_ai_analyses, o.db._get_connection

    def _kilitli_baglanti(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    def _kilitliyken_temizle(*a, **k):
        o.db._get_connection = _kilitli_baglanti
        try:
            return gercek_temizle(*a, **k)
        finally:
            o.db._get_connection = gercek_baglanti

    monkeypatch.setattr(o.db, "clear_ai_analyses", _kilitliyken_temizle)
    with TestClient(o.a.app, client=CIHAZ) as c:
        r = c.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.temizlenemedi"))
    assert len(o.db.get_ai_analyses(10)) == 1
    iz: list = []
    for _ in range(40):  # iz döngü dışı yazıcıda tamamlanabilir (≤ 0,25 sn bekleme sözleşmesi)
        iz = o.db.denetim_oku(event_type="ai_log.delete_all")
        if iz:
            break
        time.sleep(0.05)
    assert [(s["outcome"], s["scope"], s["item_count"]) for s in iz] == [("hata", "TUM_KLINIK", 0)]
