# -*- coding: utf-8 -*-
"""B2B2-3 (2-B2 kapanışında bulundu — B2B2-1 `1d54383`'ün GERİLEMESİ) — veri klasörü `\\\\` ile başlayan yoldayken kimlik kararı.

ÖLÇÜLEN KUSUR: B2B2-1 kimlik KARARI okumasını (`AuthDB._kati_oku`) `Path(db_path).resolve().as_uri() + "?mode=rw"` URI'siyle
açtı. Veri klasörü UNC yolundaysa (`PEMF_DATA_DIR=\\\\sunucu\\pay`, etki alanında ağa yönlendirilmiş `%APPDATA%`; eşlenmiş ağ
sürücüsü de `resolve()` ile UNC'ye çözülür) ya da `\\\\?\\` önekliyse URI'nin otorite alanı dolar ve SQLite reddeder
(`invalid uri authority: …` — ölçüldü, `\\\\127.0.0.1\\…` ve `\\\\?\\C:\\…`). Katı OLMAYAN yol (`_conn`, düz yol) aynı dosyayı
açıyordu → PIN/kayıt çalışır ama HER kimlik kararı "okunamıyor" sayılır, FAIL-CLOSED: operatörsüz klinik dahil değerlendirme ve
silme 428 + "Cihazın kimlik veritabanı okunamıyor" (Y113), `/api/operators` 503. B2B2-1'in ebeveyninde (`0df7277`) bu yol açılıyordu.

DÜZELTME (`AuthDB._kati_baglan`): URI yalnız sürücü harfli yerel yolda (`os.path.abspath` — eşlenmiş sürücü harfi UNC'ye
çözülmez); `\\\\` ile başlayan yolda `_conn` ile aynı düz yol, dosya YOKSA açılmaz (yaratılmasın — `mode=rw` eşdeğeri).
Kısa zaman aşımı ve kilidi beklememe (B2B2-1) iki dalda da aynı.

GERÇEK: tekil `AuthDB`, ürünün kendi kayıt/doğrulama uçları, gerçek SQLite dosyası (tekilin DB'sinin kopyası) `\\\\?\\` önekli
gerçek yolla — ağ paylaşımı kurmak yönetici hakkı ister (kabuk yükseltilmemiş), `\\\\?\\` aynı `\\\\` dalını gerçek dosyayla
ölçer. Gerçek ağ paylaşımı BİLİNMİYOR (ölçülmedi).
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows yol biçimi (\\\\?\\ öneki)")

AYSE = "dr.ayse@klinik.com"
TEK = "tek@klinik.com"
LAN = ("192.168.1.89", 52435)
ARIZA_BASI = "Cihazın kimlik veritabanı okunamıyor"


def _operatorleri_sil(c):
    for op in c.get("/api/operators").json().get("data", []):
        c.post("/api/operators/remove", json={"email": op["email"]})


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from database.patient_database import PatientDatabase
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens, patient_router

    o = apa.kur(monkeypatch, tmp_path)
    o.hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: o.hdb)
    secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.tmp = tmp_path
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 52434), backend_options=secenek)
    o.lan = TestClient(o.api.app, client=LAN, backend_options=secenek)
    operator_tokens.temizle_hepsi()
    _operatorleri_sil(o.yerel)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            yield o
    finally:
        operator_tokens.temizle_hepsi()
        _operatorleri_sil(o.yerel)
        o.geri()


def _onekli(p: Path) -> Path:
    return Path("\\\\?\\" + str(p))


def _onekli_kopya(o, m, ad="onekli"):
    """Tekilin auth DB'sinin kopyası; tekil `db_path` `\\\\?\\` önekli GERÇEK yola bağlanır. Dönen: öneksiz kopya yolu."""
    from database.auth_db import get_auth_db

    adb = get_auth_db()
    d = o.tmp / ad
    d.mkdir()
    for sfx in ("", "-wal", "-shm"):
        f = Path(str(adb.db_path) + sfx)
        if f.exists():
            shutil.copy2(f, d / f.name)
    kopya = d / "auth_users.db"
    m.setattr(adb, "db_path", _onekli(kopya))
    assert str(adb.db_path).startswith("\\\\?\\"), "aparat: önek yok"
    return kopya


def _auth_hatalari(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "servers.auth" and r.levelno >= logging.ERROR]


def test_KRITIK_KURAL2_operatorsuz_klinik_ONEKLI_yolda_KILITLENMEZ(o, monkeypatch, caplog):
    """Operatörsüz klinik (Kural 2): değerlendirme beyanla 200, hasta silme 200; arıza iletisi ve ERROR günlüğü YOK."""
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    pid = o.hdb.add_patient({"name": "Tekir", "species": "Kedi", "operator_email": TEK})
    caplog.set_level(logging.WARNING, logger="servers.auth")
    with monkeypatch.context() as m:
        _onekli_kopya(o, m)
        r_op = o.yerel.get("/api/operators")
        r_deg = o.lan.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": TEK})
        r_sil = o.lan.delete(f"/api/patients/{pid}")
    assert r_op.status_code == 200 and r_op.json().get("data") == [], (r_op.status_code, r_op.text[:200])
    assert r_deg.status_code == 200, (
        f"operatörsüz klinik önekli yolda KİLİTLENDİ: {r_deg.status_code} {r_deg.text[:200]}"
    )
    assert next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid).get("reviewed_by") == TEK
    assert r_sil.status_code == 200, (r_sil.status_code, r_sil.text[:200])
    assert not _auth_hatalari(caplog), _auth_hatalari(caplog)


def test_KRITIK_kayitli_klinik_ONEKLI_yolda_kimlik_karari_DOGRU(o, monkeypatch, caplog):
    """Kayıtlı operatörlü klinik: liste okunur; jetonlu değerlendirme sahibine 200; jetonsuz 428 "Operatör seçin" (arıza DEĞİL)."""
    r = o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "Dr. Ayşe", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    aid2 = o.db.add_ai_analysis(module_id="m2", patient_name="P2", result_summary="ozet2")
    caplog.set_level(logging.WARNING, logger="servers.auth")
    with monkeypatch.context() as m:
        _onekli_kopya(o, m)
        jeton = (
            o.yerel.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json().get("operator_token")
        )
        r_op = o.yerel.get("/api/operators")
        r_jetonlu = o.lan.post(
            "/api/ai/log/review",
            json={"analysis_id": aid, "status": "approved", "reviewed_by": ""},
            headers={"X-PEMF-Operator": jeton or ""},
        )
        r_jetonsuz = o.lan.post(
            "/api/ai/log/review", json={"analysis_id": aid2, "status": "approved", "reviewed_by": ""}
        )
    assert jeton, "aparat: önekli yolda PIN doğrulaması jeton vermedi"
    assert r_op.status_code == 200, f"/api/operators önekli yolda {r_op.status_code}: {r_op.text[:200]}"
    assert [x["email"] for x in r_op.json().get("data", [])] == [AYSE]
    assert r_jetonlu.status_code == 200, (
        f"jetonlu değerlendirme önekli yolda {r_jetonlu.status_code}: {r_jetonlu.text[:200]}"
    )
    assert next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid).get("reviewed_by") == AYSE
    d = r_jetonsuz.json().get("detail", "")
    assert r_jetonsuz.status_code == 428 and d.startswith("Operatör seçin") and ARIZA_BASI not in d, (
        r_jetonsuz.status_code,
        d,
    )
    assert not _auth_hatalari(caplog), _auth_hatalari(caplog)


def test_KARSIT_ONEKLI_yolda_DOSYA_YOKSA_fail_closed_ve_dosya_YARATILMAZ(o, monkeypatch):
    """`\\\\` dalında da dosya yoksa kimlik kararı FAIL-CLOSED (Y113 iletisi) ve katı okuma boş DB YARATMAZ (Kural 2'ye dönmez)."""
    from database.auth_db import get_auth_db

    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    hedef = o.tmp / "yok_dizin_degil" / "auth_users.db"
    hedef.parent.mkdir()
    with monkeypatch.context() as m:
        m.setattr(get_auth_db(), "db_path", _onekli(hedef))
        with pytest.raises(Exception):
            get_auth_db().list_operators(kati=True)
        r = o.lan.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": TEK})
        assert not os.path.exists(hedef), "katı okuma olmayan kimlik DB'sini YARATTI (boş DB = operatörsüz klinik)"
    assert r.status_code == 428 and r.json().get("detail", "").startswith(ARIZA_BASI), (r.status_code, r.text[:200])


def test_KARSIT_ONEKLI_yolda_KILITLIYKEN_kati_okuma_KISA_surede_duser_ACIL_DURDUR_calisir(o, monkeypatch):
    """B2B2-1 sınırı `\\\\` dalında da: kilitli DB'de katı okuma kısa sürede düşer (döngü donmaz), ACİL DURDUR ve STOP 200."""
    from database.auth_db import get_auth_db

    with monkeypatch.context() as m:
        kopya = _onekli_kopya(o, m, "onekli_kilit")
        kc = sqlite3.connect(str(kopya), isolation_level=None, timeout=1)
        kc.execute("PRAGMA locking_mode=EXCLUSIVE")
        kc.execute("BEGIN EXCLUSIVE")
        kc.execute("UPDATE device_operators SET last_active = last_active")
        try:
            t0 = time.monotonic()
            with pytest.raises(Exception):
                get_auth_db().list_operators(kati=True)
            sure = time.monotonic() - t0
            assert o.lan.post("/api/hardware/emergency_stop").status_code == 200
            assert o.lan.post("/api/session/stop", json={}).status_code == 200
        finally:
            kc.execute("ROLLBACK")
            kc.close()
    assert sure < 3.0, f"önekli yolda kilitli katı okuma {sure:.1f} sn sürdü (döngüyü dondurur)"
