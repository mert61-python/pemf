# -*- coding: utf-8 -*-
"""Y308 (sahip 19-11: "konum kaydını da al yayına ama sensör serbest de gezdirilebilsin konum bilgisi olmadan; kullanıcı hangisini
isterse") — KABİN SENSÖRÜ (MLX) KONUMU, İSTEĞE BAĞLI.
SÖZLEŞME:
  · VARSAYILAN serbest: hiç giriş yoksa seans detayı yanıtı, CSV ve PDF bugünküyle BİREBİR;
  · konumlu: zaman damgalı girişler (sol / ön çıkıntıdan + tabandan cm, not) ya da serbest giriş; seans sırasında (canlı uç, sunucu
    saati) ya da sonra (başlangıç saati seçerek, seans aralığında) girilir / düzeltilir / silinir;
  · dilimler: ilk girişten önce serbest dilim; dilim başına konum, süre, kabin sensörünün ort / tepe mT'si (dakika ortalamaları), konumlu
    dilimde aynı noktada aynı sürüşle ODAK modelinin TAHMİNİ (canlı alan haritasıyla AYNI fizik) + fark %; serbestte tahmin YOK;
  · konum çevirisi Doğrula'nın kabin kalibrasyonu kuralıyla AYNI (`sabit_duzlem.kabin_noktasi_mm`);
  · VERİ: AYRI tablo `sensor_konumlari`, mevcut tablolara ALTER yok; göç idempotent; yarıda kesilen göç veri kaybettirmez; yeni DB'yi
    eski sürüm açarsa bozulmaz; seans silinince girişler de silinir; yedek tabloyu kapsar; buluta senkron (outbox) YOK;
  · yetki Y107 deseni (kayıtlı operatörlü klinikte kimliksiz 428), geçersiz girdi 422, seans yoksa 404 / canlıda 409.
GERÇEK: geçici kökte gerçek şema (düz kip — CH3 düzeneği), history_router uçları, sensor_konumu, PDF üreticisi, canlı alan aparatı."""

from __future__ import annotations

import csv
import io
import math
import sqlite3
import time

import numpy as np
import pytest
from starlette.requests import Request


def _istek() -> Request:
    return Request(
        {"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1), "query_string": b""}
    )


@pytest.fixture
def kok(tmp_path, monkeypatch):
    import utils.secrets_manager as sm
    from database.treatment_history_db import TreatmentHistoryDB

    sm._cache = None
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    yield tmp_path / "veri"
    sm._cache = None


@pytest.fixture
def db(kok):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(kok)
    yield d
    d.close_connections()


def _seans(db, bas=1000.0, bit=1600.0) -> int:
    with db._get_connection() as c:
        cur = c.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, session_status, treatment_mode, started_epoch, ended_epoch) "
            "VALUES ('2026-11-19', '18:07:00', 'stopped', 'AI Pro · Petri Kuyu', ?, ?)",
            (bas, bit),
        )
        c.commit()
        return int(cur.lastrowid)


def _tablo_var(yol) -> bool:
    c = sqlite3.connect(str(yol))
    try:
        return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sensor_konumlari'").fetchone())
    finally:
        c.close()


# ── veri / göç ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_ESKI_semali_DB_acilir_tablo_EKLENIR_eski_seanslar_AYNEN(kok):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(kok)
    sid = _seans(d)
    with d._get_connection() as c:
        c.execute("DROP TABLE sensor_konumlari")  # eski sürümün şeması
        c.commit()
    yol = d.db_path
    d.close_connections()
    assert not _tablo_var(yol)
    d2 = TreatmentHistoryDB(kok)
    try:
        assert _tablo_var(yol)
        assert d2.get_session_details(sid)["treatment_mode"] == "AI Pro · Petri Kuyu"
        assert d2.sensor_konumlari(sid) == []
    finally:
        d2.close_connections()


def test_iki_kez_acilis_IDEMPOTENT_girisler_korunur(kok):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(kok)
    sid = _seans(d)
    d.sensor_konumu_ekle(sid, 1100.0, serbest=False, sol_cm=10, on_cm=20, yukseklik_cm=3, not_metni="A1 yanı")
    d.close_connections()
    for _ in range(2):
        d = TreatmentHistoryDB(kok)
        assert [k["not_metni"] for k in d.sensor_konumlari(sid)] == ["A1 yanı"]
        d.close_connections()


def test_KRITIK_YARIDA_kesilen_gocte_veri_KAYBOLMAZ(kok, monkeypatch):
    from database import thdb_sema
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(kok)
    sid = _seans(d)
    with d._get_connection() as c:
        c.execute("DROP TABLE sensor_konumlari")
        c.commit()
    d.close_connections()

    def _patla(self, cursor):
        raise sqlite3.OperationalError("göç yarıda kesildi (benzetim)")

    with monkeypatch.context() as m:
        m.setattr(thdb_sema.SemaKarisimi, "_create_vet_indexes", _patla)
        try:
            TreatmentHistoryDB(kok).close_connections()
        except Exception:
            pass  # açılış düşebilir — önemli olan veri
    d2 = TreatmentHistoryDB(kok)
    try:
        assert d2.get_session_details(sid)["treatment_mode"] == "AI Pro · Petri Kuyu", "yarım göç seansı kaybettirdi"
        assert d2.sensor_konumlari(sid) == []
        d2.sensor_konumu_ekle(sid, 1100.0, serbest=True)
        assert len(d2.sensor_konumlari(sid)) == 1
    finally:
        d2.close_connections()


def test_KRITIK_yeni_DB_yi_ESKI_surum_acarsa_BOZULMAZ_tablo_yok_sayilir(kok, monkeypatch):
    from database import thdb_sensor_konumu
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(kok)
    sid = _seans(d)
    d.sensor_konumu_ekle(sid, 1100.0, serbest=False, sol_cm=1, on_cm=2, yukseklik_cm=3)
    d.close_connections()
    monkeypatch.setattr(thdb_sensor_konumu, "SEMA", "SELECT 1")  # eski sürüm: tabloyu tanımaz, oluşturmaz
    monkeypatch.setattr(thdb_sensor_konumu, "DIZIN", "SELECT 1")
    eski = TreatmentHistoryDB(kok)
    try:
        assert eski.get_session_details(sid)["treatment_mode"] == "AI Pro · Petri Kuyu"
        with eski._get_connection() as c:
            assert c.execute("SELECT COUNT(*) FROM sensor_konumlari").fetchone()[0] == 1, (
                "eski açılış yeni tabloya dokundu"
            )
    finally:
        eski.close_connections()


def test_KRITIK_seans_SILININCE_girisler_silinir_tekil_ve_toplu(db):
    a, b, c = _seans(db), _seans(db), _seans(db)
    for s in (a, b, c):
        db.sensor_konumu_ekle(s, 1100.0, serbest=True)
    db.delete_session(a)
    assert db.sensor_konumlari(a) == []
    silici = getattr(db, "delete_sessions_bulk", None) or getattr(db, "delete_sessions", None)
    assert callable(silici), "toplu silme yöntemi bulunamadı"
    silici([b])
    assert db.sensor_konumlari(b) == [] and len(db.sensor_konumlari(c)) == 1


def test_YEDEK_tabloyu_KAPSAR_ve_BULUT_outbox_a_YAZILMAZ(db, tmp_path):
    sid = _seans(db)
    with db._get_connection() as c:
        outbox_once = c.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0]
    db.sensor_konumu_ekle(sid, 1100.0, serbest=False, sol_cm=12.5, on_cm=8, yukseklik_cm=4, not_metni="yedek")
    with db._get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0] == outbox_once, (
            "konum buluta senkron kuyruğuna girdi"
        )
    yedek = tmp_path / "yedek.db"
    assert db.create_backup(str(yedek))
    k = sqlite3.connect(str(yedek))
    try:
        assert k.execute("SELECT not_metni, sol_cm FROM sensor_konumlari").fetchall() == [("yedek", 12.5)]
    finally:
        k.close()


def test_karisim_GUNCELLE_SIL_yalniz_o_seansin_kaydi(db):
    a, b = _seans(db), _seans(db)
    k = db.sensor_konumu_ekle(a, 1100.0, serbest=False, sol_cm=1, on_cm=2, yukseklik_cm=3, not_metni="x")
    assert db.sensor_konumu_guncelle(k, b, 1200.0, serbest=True) is False, "başka seansın kaydı güncellendi"
    assert db.sensor_konumu_guncelle(k, a, 1200.0, serbest=True, not_metni="serbest oldu") is True
    assert db.sensor_konumlari(a) == [
        {
            "id": k,
            "session_id": a,
            "zaman_epoch": 1200.0,
            "serbest": True,
            "sol_cm": None,
            "on_cm": None,
            "yukseklik_cm": None,
            "not_metni": "serbest oldu",
        }
    ]
    assert db.sensor_konumu_sil(k, b) is False and db.sensor_konumu_sil(k, a) is True and db.sensor_konumlari(a) == []


# ── dilimler + model tahmini ───────────────────────────────────────────────────────────────────────────────────────────────
def _ornek(ts, mt, kanal="6"):
    return {"coil_id": kanal, "sample_ts": ts, "magnetic_field_mt": mt}


def test_KRITIK_dilimler_SERBEST_ilk_dilim_KONUMLU_tahmin_fark_ve_SERBEST_giris():
    from servers import sensor_konumu as sk

    konumlar = [
        {
            "id": 1,
            "zaman_epoch": 1200.0,
            "serbest": False,
            "sol_cm": 10.0,
            "on_cm": 20.0,
            "yukseklik_cm": 3.0,
            "not_metni": "A1",
        },
        {
            "id": 2,
            "zaman_epoch": 1400.0,
            "serbest": True,
            "sol_cm": None,
            "on_cm": None,
            "yukseklik_cm": None,
            "not_metni": "",
        },
    ]
    ornek = [_ornek(1060, 1.0), _ornek(1260, 1.2), _ornek(1320, 1.4), _ornek(1260, 9.9, kanal="1"), _ornek(1460, 0.5)]
    kosular = [
        {
            "coil_id": 1,
            "started_epoch": 1000.0,
            "ended_epoch": 1600.0,
            "frequency_hz": 100,
            "duty_percent": 50,
            "phase": 0,
        },
        {
            "coil_id": 2,
            "started_epoch": 1500.0,
            "ended_epoch": 1600.0,
            "frequency_hz": 100,
            "duty_percent": 40,
            "phase": 90,
        },
    ]
    cagri = []

    def tahmin(P, bobinler):
        cagri.append((P, bobinler))
        return 1.25

    d = sk.dilimler(konumlar, 1000.0, 1600.0, ornek, kosular, nokta=lambda s, o, y: [s, o, y], tahmin=tahmin)
    assert [(x["baslangic_epoch"], x["bitis_epoch"], x["serbest"]) for x in d] == [
        (1000.0, 1200.0, True),
        (1200.0, 1400.0, False),
        (1400.0, 1600.0, True),
    ]
    assert d[0]["ortalama_mt"] == 1.0 and d[0]["tahmin_mt"] is None and d[0]["kayit_id"] is None
    assert d[1]["ortalama_mt"] == 1.3 and d[1]["tepe_mt"] == 1.4 and d[1]["olcum_sayisi"] == 2, (
        "kabin dışı kanal sayıldı"
    )
    assert d[1]["tahmin_mt"] == 1.25 and d[1]["fark_yuzde"] == 4.0 and d[1]["not"] == "A1" and d[1]["sure_sn"] == 200.0
    assert cagri == [([10.0, 20.0, 3.0], [(1, 100.0, 0.5, 0.0)])], (
        "dilimle örtüşmeyen koşu sürüşe katıldı / konum çevrilmedi"
    )
    assert d[2]["tahmin_mt"] is None and d[2]["fark_yuzde"] is None and d[2]["ortalama_mt"] == 0.5
    assert sk.dilimler([], 1000.0, 1600.0, ornek, kosular) == [], "giriş yokken dilim üretildi (çıktı birebir olmalı)"
    # serbest giriş koordinat taşısa bile (eski / bozuk satır) tahmin YOK — kural "serbest dilimde model tahmini yok"
    kirli = [
        {
            "id": 3,
            "zaman_epoch": 1000.0,
            "serbest": True,
            "sol_cm": 5.0,
            "on_cm": 5.0,
            "yukseklik_cm": 5.0,
            "not_metni": "",
        }
    ]
    d3 = sk.dilimler(kirli, 1000.0, 1600.0, ornek, kosular, nokta=lambda s, o, y: [s, o, y], tahmin=lambda *a: 9.0)
    assert [(x["serbest"], x["tahmin_mt"], x["sol_cm"]) for x in d3] == [(True, None, None)]


def test_dilimler_bitis_BILINMIYORSA_son_ornek_ve_uc_durumlar():
    from servers import sensor_konumu as sk

    k = [
        {
            "id": 1,
            "zaman_epoch": 900.0,
            "serbest": False,
            "sol_cm": 1.0,
            "on_cm": 2.0,
            "yukseklik_cm": 3.0,
            "not_metni": "",
        }
    ]
    d = sk.dilimler(k, 1000.0, None, [_ornek(1100, 2.0)], [], nokta=lambda *a: None, tahmin=lambda *a: 1.0)
    assert (
        len(d) == 1 and d[0]["baslangic_epoch"] == 1000.0 and d[0]["bitis_epoch"] == 1100.0
    )  # giriş seanstan önce → başlangıca kırpılır
    assert d[0]["tahmin_mt"] is None  # kalibrasyon yok (nokta None) → tahmin yok
    d2 = sk.dilimler(k, None, None, [], [], nokta=lambda *a: [0, 0, 0], tahmin=lambda *a: 0.0)
    assert d2 == [] or d2[0]["fark_yuzde"] is None


def test_surus_DILIMLE_EN_COK_ortusen_kosu_ve_gecersizler_atlanir():
    from servers import sensor_konumu as sk

    kosular = [
        {"coil_id": 1, "started_epoch": 0.0, "ended_epoch": 50.0, "frequency_hz": 100, "duty_percent": 10, "phase": 0},
        {
            "coil_id": 1,
            "started_epoch": 50.0,
            "ended_epoch": None,
            "frequency_hz": 100,
            "duty_percent": 30,
            "phase": 45,
        },
        {"coil_id": 2, "started_epoch": 0.0, "ended_epoch": 100.0, "frequency_hz": 100, "duty_percent": 0, "phase": 0},
        {"coil_id": None, "started_epoch": 0.0, "ended_epoch": 100.0, "frequency_hz": 100, "duty_percent": 30},
        {"coil_id": 3, "started_epoch": 0.0, "ended_epoch": 100.0, "frequency_hz": None, "duty_percent": 30},
        {"coil_id": 4, "started_epoch": 200.0, "ended_epoch": 300.0, "frequency_hz": 100, "duty_percent": 30},
    ]
    assert sk._surus(kosular, 40.0, 100.0) == [(1, 100.0, 0.3, 45.0)]


def test_KRITIK_nokta_tahmini_CANLI_ALAN_haritasiyla_AYNI_fizik():
    import canli_alan_aparati as ap
    from servers import sensor_konumu as sk

    T, K = ap.tablo(), ap.kalibrasyon()
    onb = {}

    def saglayici(f):
        if f not in onb:
            onb[f] = ap.model(f, K=K, T=T)
        return onb[f]

    A = saglayici(100.0)
    P = [10.0, -150.0, 20.0]
    bobinler = [(1, 100.0, 0.5, 0.0), (3, 100.0, 0.25, 180.0), (7, 100.0, 0.4, 90.0)]
    beklenen = A.td_tepe_faz(
        A.alan(np.array([P])), np.array([0.5, 0, 0.25, 0, 0, 0, 0.4]), np.array([0, 0, 180.0, 0, 0, 0, 90.0])
    )[0]
    assert sk.nokta_tahmini(P, bobinler, saglayici) == pytest.approx(float(beklenen), abs=1e-4)
    assert sk.nokta_tahmini(P, [], saglayici) is None
    assert sk.nokta_tahmini([0.0, 900.0, 0.0], bobinler, saglayici) is None  # tablo dışı
    assert sk.nokta_tahmini(P, bobinler, lambda f: (_ for _ in ()).throw(FileNotFoundError("tablo yok"))) is None


def test_kabin_noktasi_DOGRULA_kuraliyla_AYNI_kalibrasyon_yoksa_None(tmp_path, monkeypatch):
    from servers import kabin_kalibrasyonu
    from servers import sensor_konumu as sk

    from ai_hub.cv_ortak import sabit_duzlem as sd

    monkeypatch.setattr(kabin_kalibrasyonu, "_veri_koku", lambda: tmp_path / "bos")
    assert sk.kabin_noktasi(10.0, 20.0, 3.0) is None

    class _H:
        ext_cm = (54.0, 37.0, 40.0)

    monkeypatch.setattr(sd, "yukle", lambda kok: ({"sahte": True}, None))
    monkeypatch.setattr(sd, "DuzlemHaritasi", lambda kal: _H())
    assert sk.kabin_noktasi(10.0, 20.0, 3.0) == [float(v) for v in sd.kabin_noktasi_mm(10.0, 20.0, 3.0, _H.ext_cm)]


@pytest.mark.parametrize(
    "govde,gecerli",
    [
        ({"serbest": True}, True),
        ({"solCm": 0, "onCm": 100, "yukseklikCm": 5.5, "notMetni": " a "}, True),
        ({"solCm": -0.1, "onCm": 1, "yukseklikCm": 1}, False),
        ({"solCm": 1, "onCm": 100.1, "yukseklikCm": 1}, False),
        ({"solCm": 1, "onCm": 1}, False),
        ({"solCm": math.nan, "onCm": 1, "yukseklikCm": 1}, False),
        ({"serbest": True, "notMetni": "x" * 201}, False),
    ],
)
def test_dogrula_SINIRLAR(govde, gecerli):
    from servers import sensor_konumu as sk

    g = sk.SensorKonumuGovde(**govde)
    if gecerli:
        alan = sk.dogrula(g)
        assert (
            alan["serbest"] is bool(govde.get("serbest")) and alan["not_metni"] == (govde.get("notMetni") or "").strip()
        )
    else:
        with pytest.raises(ValueError):
            sk.dogrula(g)


# ── uçlar: seans sonrası (geçmiş) ──────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_GIRIS_YOKKEN_detay_ve_CSV_BIREBIR(db, monkeypatch):
    from servers import history_router as h

    sid = _seans(db)
    govde = h.get_session_full_details(sid, db=db)
    assert set(govde) == {"session", "coil_runs", "sensor_samples"}, "giriş yokken yanıta anahtar eklendi"
    satirlar = list(csv.reader(io.StringIO(h.export_coil_runs_csv(sid, db=db).body.decode("utf-8-sig"))))
    assert len(satirlar) == 1, "giriş yokken CSV'ye konum bölümü eklendi"


def test_KRITIK_gecmis_EKLE_DUZELT_SIL_detayda_dilimler_CSV_de_ayni_tablo(db, monkeypatch):
    from servers import history_router as h
    from servers import sensor_konumu as sk

    monkeypatch.setattr(sk, "kabin_noktasi", lambda s, o, y: [s, o, y])
    monkeypatch.setattr(sk, "nokta_tahmini", lambda P, b: 2.0)
    sid = _seans(db)
    rid = db.start_coil_run(sid, 1, started_epoch=1000.0, frequency_hz=100, duty_percent=50, phase=0, hw_type="STM")
    db.end_coil_run(rid, 1600.0)
    db.add_sensor_samples_batch(sid, [{"coil_id": "6", "sample_ts": 1300.0, "magnetic_field_mt": 2.2}])
    r = h.sensor_konumu_ekle(
        sid, _istek(), sk.SensorKonumuGovde(solCm=10, onCm=20, yukseklikCm=3, notMetni="A1", zamanEpoch=1200.0), db=db
    )
    kid = r["id"]
    d = h.get_session_full_details(sid, db=db)
    assert [k["id"] for k in d["sensor_konumlari"]] == [kid]
    assert [(x["serbest"], x["tahmin_mt"], x["fark_yuzde"]) for x in d["konum_dilimleri"]] == [
        (True, None, None),
        (False, 2.0, 10.0),
    ]
    h.sensor_konumu_guncelle(
        sid, kid, _istek(), sk.SensorKonumuGovde(solCm=11, onCm=20, yukseklikCm=3, zamanEpoch=1250.0), db=db
    )
    assert db.sensor_konumlari(sid)[0]["sol_cm"] == 11.0 and db.sensor_konumlari(sid)[0]["zaman_epoch"] == 1250.0
    satirlar = list(csv.reader(io.StringIO(h.export_coil_runs_csv(sid, db=db).body.decode("utf-8-sig"))))
    i = satirlar.index([])
    assert satirlar[i + 1] == ["Kabin sensoru (MLX) konum dilimleri"]
    assert (
        satirlar[i + 2][2] == "Konum(sol/on/yukseklik cm)"
        and satirlar[i + 3][2] == "serbest"
        and satirlar[i + 4][2] == "11 / 20 / 3"
    )
    assert satirlar[i + 4][5] == "2.0" and satirlar[i + 4][6] == "10.0"
    h.sensor_konumu_sil(sid, kid, _istek(), db=db)
    assert db.sensor_konumlari(sid) == []


@pytest.mark.parametrize(
    "govde,kod",
    [
        ({"solCm": 500, "onCm": 1, "yukseklikCm": 1, "zamanEpoch": 1200.0}, 422),
        ({"serbest": True, "zamanEpoch": 500.0}, 422),  # seans öncesi
        ({"serbest": True, "zamanEpoch": 9999.0}, 422),  # seans sonrası
    ],
)
def test_gecmis_GECERSIZ_girdi_422_ZAMAN_disi_422(db, govde, kod):
    from fastapi import HTTPException
    from servers import history_router as h
    from servers import sensor_konumu as sk

    sid = _seans(db)
    with pytest.raises(HTTPException) as e:
        h.sensor_konumu_ekle(sid, _istek(), sk.SensorKonumuGovde(**govde), db=db)
    assert e.value.status_code == kod and db.sensor_konumlari(sid) == []


def test_gecmis_SEANS_yok_404_KAYIT_yok_404_ve_zaman_VERILMEZSE_baslangic(db):
    from fastapi import HTTPException
    from servers import history_router as h
    from servers import sensor_konumu as sk

    for cagri in (
        lambda: h.sensor_konumu_ekle(99999, _istek(), sk.SensorKonumuGovde(serbest=True), db=db),
        lambda: h.sensor_konumu_guncelle(_seans(db), 777, _istek(), sk.SensorKonumuGovde(serbest=True), db=db),
        lambda: h.sensor_konumu_sil(_seans(db), 777, _istek(), db=db),
    ):
        with pytest.raises(HTTPException) as e:
            cagri()
        assert e.value.status_code == 404
    sid = _seans(db, bas=1000.0)
    h.sensor_konumu_ekle(sid, _istek(), sk.SensorKonumuGovde(serbest=True), db=db)
    assert db.sensor_konumlari(sid)[0]["zaman_epoch"] == 1000.0


def test_KRITIK_KIMLIK_kayitli_operatorlu_klinikte_KIMLIKSIZ_428_kayit_YOK(db, monkeypatch):
    from fastapi import HTTPException
    from servers import auth
    from servers import history_router as h
    from servers import sensor_konumu as sk

    monkeypatch.setattr(auth, "kayitli_operator_var", lambda: True)
    monkeypatch.setattr(auth, "cozumlenmis_operator", lambda request: None)
    sid = _seans(db)
    with pytest.raises(HTTPException) as e:
        h.sensor_konumu_ekle(sid, _istek(), sk.SensorKonumuGovde(serbest=True, zamanEpoch=1100.0), db=db)
    assert e.value.status_code == 428 and db.sensor_konumlari(sid) == []


def test_PDF_konum_tablosu_YALNIZ_giris_varken(db, monkeypatch):
    from servers import sensor_konumu as sk
    from utils import pdf_report_generator as prg

    monkeypatch.setattr(sk, "kabin_noktasi", lambda s, o, y: [s, o, y])
    monkeypatch.setattr(sk, "nokta_tahmini", lambda P, b: 1.5)
    sid = _seans(db)
    g = prg.PDFReportGenerator.__new__(prg.PDFReportGenerator)
    g.db = db
    g.styles = {"Heading3": None, "UnicodeNormal": None}
    eklenen: list = []
    monkeypatch.setattr(prg, "Paragraph", lambda metin, stil: ("P", metin))
    monkeypatch.setattr(prg, "Spacer", lambda *a: ("S",))
    g._add_sensor_konum_table(eklenen, sid)
    assert eklenen == [], "giriş yokken PDF'e tablo eklendi"
    db.sensor_konumu_ekle(sid, 1200.0, serbest=False, sol_cm=10, on_cm=20, yukseklik_cm=3)
    g._add_sensor_konum_table(eklenen, sid)
    tablo = next(x for x in eklenen if isinstance(x, prg.Table))
    satirlar = tablo._cellvalues
    assert satirlar[0][2] == "Konum (sol / ön / yükseklik cm)" and [s[2] for s in satirlar[1:]] == [
        "serbest",
        "10 / 20 / 3",
    ]
    assert satirlar[2][5] == "1,50"  # TR ondalık virgül (Y306)
    assert ("P", "Kabin sensörü (MLX) konum dilimleri") in eklenen


def test_PDF_GERCEK_uretim_yolunda_konum_tablosu_ve_HATASI_raporu_dusurmez(temp_app_data, tmp_path, monkeypatch):
    from servers import sensor_konumu as sk
    from utils.pdf_report_generator import PDFReportGenerator

    monkeypatch.setattr(sk, "kabin_noktasi", lambda s, o, y: None)
    u = PDFReportGenerator(app_data_dir=tmp_path)
    sid = u.db.start_session(treatment_mode="Manuel", patient_name="Pamuk")
    u.db.end_session(sid, session_status="stopped")
    u.db.sensor_konumu_ekle(sid, time.time(), serbest=False, sol_cm=10, on_cm=20, yukseklik_cm=3)
    yakalanan: list = []
    gercek = u._build_pdf

    def _yakala(story, output_path, label):
        yakalanan.append(list(story))
        return gercek(story, output_path, label)

    u._build_pdf = _yakala
    yol = u.generate_session_report(session_ids=[sid], output_path=str(tmp_path / "konum.pdf"))
    with open(yol, "rb") as f:
        assert f.read(5) == b"%PDF-"
    tablolar = [
        x
        for x in yakalanan[0]
        if type(x).__name__ == "Table" and "Konum (sol / ön / yükseklik cm)" in [str(h) for h in x._cellvalues[0]]
    ]
    assert len(tablolar) == 1
    u._add_sensor_konum_table(yakalanan[0], None)  # seans kimliği yok → hiçbir şey
    monkeypatch.setattr(u, "_add_sensor_konum_table", lambda *a: (_ for _ in ()).throw(RuntimeError("tablo patladı")))
    yol2 = u.generate_session_report(session_ids=[sid], output_path=str(tmp_path / "konum2.pdf"))
    with open(yol2, "rb") as f:
        assert f.read(5) == b"%PDF-", "konum tablosu hatası raporu düşürdü"
