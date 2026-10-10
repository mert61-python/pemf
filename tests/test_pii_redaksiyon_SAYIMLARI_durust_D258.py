# -*- coding: utf-8 -*-
"""D2.58 · B-3.89 · B-3.90 — PII redaksiyon sayımları DÜRÜST.

(a) B-3.89 ÖLÇÜLEN KUSUR: `redact_old_session_pii` `WHERE session_date < ?` ile süresi dolmuş TÜM satırları her turda yeniden
    güncelliyordu (CASE değeri aynı bıraksa da `rowcount` hepsini sayar) → ekleme-only KVKK denetim izine her 6 saatte sahte
    "maskelendi" kaydı düşüyordu (~50 günde 200'lük görünüm dolar). Zaten maskeli / PII'siz (`[ANONIM]`, boş) satır sayılmamalı, iz
    tekrarlanmamalı; bekleyen sayısı ile maskelenen sayısı AYNI ölçütten türemeli.
(b) B-3.90 ÖLÇÜLEN KUSUR: `redaksiyon_bekleyen_sayisi` DB hatasında DEBUG + `0` dönüyordu → ekran "bekleyen yok" sanıp geri dönüşsüz
    maskeleme sorusunu SORMUYOR, onay da "0 kayıt" diye yazılıyordu. Artık `None` ("sayılamadı") + WARNING; ekran söyler, onay verilmez.
GERÇEK: TreatmentHistoryDB (sentetik, tmp), headless bakım turunun GERÇEK gövdesi, `/api/settings/retention` uçları. Arıza GERÇEK
SQLite hatası (seans tablosu yerinde yok → sayım sorgusu `OperationalError`; ayar okumaları çalışır) — Python yaması yok.
⚠️ Maskeleme OPT-IN kalır (varsayılan-açık YAPILMAZ — Ö.4).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


def _seans(db, ad, gun_once, operator="Dr. Test", parametreler=None):
    tarih = (datetime.now() - timedelta(days=gun_once)).strftime("%Y-%m-%d")
    with db._get_connection() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, operator_name) "
            "VALUES (?,?,?,?,?)",
            (tarih, "10:00", "Manuel", ad, operator),
        )
        sid = cur.lastrowid
        for ad_, deger in (parametreler or {}).items():
            cur.execute(
                "INSERT INTO session_parameters (session_id, parameter_name, parameter_value) VALUES (?,?,?)",
                (sid, ad_, deger),
            )
        c.commit()
        return sid


def _headless_tur(db):
    from services.headless_db_maintenance import HeadlessDBMaintenance

    bakim = HeadlessDBMaintenance.__new__(HeadlessDBMaintenance)
    bakim.db = db
    bakim._run_maintenance()


def _maske_izleri(db):
    return db.denetim_oku(50, "retention.pii_maskelendi")


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import treatment_history_db as thm
    from servers import api_server as api
    from servers import system_router as sr

    for ad in ("PEMF_RETAIN_PII_DAYS", "PEMF_MASK_HISTORY_PII"):
        monkeypatch.delenv(ad, raising=False)
    for ad in ("PEMF_RETAIN_SENSOR_DAYS", "PEMF_RETAIN_DOSE_DAYS", "PEMF_RETAIN_EVENT_DAYS", "PEMF_RETAIN_OUTBOX_DAYS"):
        monkeypatch.setenv(ad, "0")
    db = thm.TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(sr, "_pii_ayar_db", lambda: db)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    try:
        yield type("O", (), {"db": db, "c": TestClient(api.app, client=("127.0.0.1", 51958))})
    finally:
        db.close_connections()


def test_KRITIK_B389_ikinci_tur_HICBIR_sey_saymaz_iz_TEKRARLANMAZ(o):
    """Plan kapısı (a): GERÇEK bakım turu ardışık iki kez → ikinci turda maskelenen 0 ve denetim izinde TEK 'maskelendi' olayı.
    MUTASYON: maskeli-satır dışlayıcısı silinir → KIRMIZI."""
    _seans(o.db, "Pamuk Eski", 400, parametreler={"patient_owner_email": "sahip@ornek.com"})
    _seans(o.db, "Boncuk Taze", 10)
    o.db.pii_onayla(gun=365, sayi=1)
    r1 = o.db.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert (r1["sessions_pii_redacted"], r1["parameters_pii_redacted"]) == (1, 1), f"aparat: ilk tur maskelemedi: {r1}"
    _headless_tur(o.db)
    _headless_tur(o.db)
    r3 = o.db.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert (r3["sessions_pii_redacted"], r3["parameters_pii_redacted"]) == (0, 0), (
        f"zaten maskeli satır yeniden 'maskelendi' sayıldı (B-3.89): {r3}"
    )
    izler = _maske_izleri(o.db)
    assert len(izler) == 1, (
        f"ekleme-only denetim izine her turda sahte 'maskelendi' kaydı düştü (B-3.89): {len(izler)} iz"
    )
    assert izler[0]["item_count"] == 1 and json.loads(izler[0]["detail"])["parametre"] == 1, izler[0]


def test_KRITIK_B389_PIIsiz_satir_SAYILMAZ_maskelenecek_alan_SAYILIR_bekleyen_ile_AYNI_olcut(o):
    """`[ANONIM]` ad + boş hekim (anonimleşmiş, PII'siz) satır ne bekleyen ne maskelenen sayılır; yalnız hekim adı olan satır sayılır
    ve maskelenir; adı zaten maskeli ama parametresinde PII kalan seans bekleyen sayılır. Bekleyen = gerçekten değişen seans sayısı."""
    _seans(o.db, "[ANONIM]", 400, operator="")  # PII yok
    _seans(o.db, "", 400, operator="Dr. Hekim")  # yalnız hekim adı
    sid_p = _seans(
        o.db, "[REDACTED]", 400, operator="[REDACTED]", parametreler={"patient_owner_email": "kalan@ornek.com"}
    )
    assert o.db.redaksiyon_bekleyen_sayisi(365) == 2, (
        "bekleyen sayısı PII'siz satırı saydı ya da parametre PII'sini atladı"
    )
    o.db.pii_onayla(gun=365, sayi=2)
    r = o.db.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert (r["sessions_pii_redacted"], r["parameters_pii_redacted"]) == (1, 1), r
    with o.db._get_connection() as c:
        satirlar = sorted(tuple(x) for x in c.execute("SELECT patient_name, operator_name FROM treatment_sessions"))
        deger = c.execute("SELECT parameter_value FROM session_parameters WHERE session_id=?", (sid_p,)).fetchone()[0]
    assert satirlar == sorted([("[ANONIM]", ""), ("", "[REDACTED]"), ("[REDACTED]", "[REDACTED]")]), satirlar
    assert deger == "[REDACTED]"
    assert o.db.redaksiyon_bekleyen_sayisi(365) == 0


def _seans_tablosunu_kaldir(db):
    """GERÇEK arıza: seans tablosu yerinde yok → sayım sorgusu SQLite `OperationalError`; ayar (system_settings) okumaları çalışır."""
    with db._get_connection() as c:
        c.execute("ALTER TABLE treatment_sessions RENAME TO treatment_sessions_gizli")
        c.commit()


def test_KRITIK_B390_sayim_HATASINDA_0_degil_SAYILAMADI_ve_WARNING(o, caplog):
    """Plan kapısı (b): DB hatasında `None` + WARNING; ekran ucu 'sayılamadı' (null) der. MUTASYON: DEBUG + return 0 → KIRMIZI."""
    _seans(o.db, "Pamuk Eski", 400)
    _seans_tablosunu_kaldir(o.db)
    caplog.set_level(logging.DEBUG)
    assert o.db.redaksiyon_bekleyen_sayisi(365) is None, "DB hatasında bekleyen sayısı uydurma (0) döndü (B-3.90)"
    assert any(r.levelno >= logging.WARNING and "bekleyen" in r.getMessage() for r in caplog.records), (
        "sayım hatası WARNING olarak günlüğe yazılmadı (DEBUG'da kayboluyordu)"
    )
    g = o.c.get("/api/settings/retention")
    assert g.status_code == 200, g.text[:200]
    assert g.json()["pending"] is None, f"ekran ucu sayılamayan bekleyeni 0 gösteriyor: {g.json()}"


def test_KRITIK_B390_sayilamayan_kapsam_ONAYLANAMAZ(o):
    """Etkilenecek kayıt sayısı okunamıyorsa onay YAZILMAZ (A-09: sayı gösterilmeden onay yok) — 503, onay kaydı yok."""
    _seans(o.db, "Pamuk Eski", 400)
    _seans_tablosunu_kaldir(o.db)
    r = o.c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 365})
    assert r.status_code == 503, f"sayılamayan kapsam onaylandı: {r.status_code} {r.text[:200]}"
    assert o.db.pii_onayi_oku() is None


def test_KRITIK_B390_bakim_turu_sayilamayan_bekleyeni_0_RAPORLAMAZ_ve_UYARIR(o, caplog):
    """Bakım raporu `pii_pending` sayılamayınca None (0 değil) ve WARNING."""
    _seans(o.db, "Pamuk Eski", 400)
    _seans_tablosunu_kaldir(o.db)
    caplog.set_level(logging.DEBUG)
    r = o.db.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert r["pii_pending"] is None, f"bakım raporu sayılamayan bekleyeni 0 yazdı: {r}"
    assert any(x.levelno >= logging.WARNING and "sayılamadı" in x.getMessage() for x in caplog.records)


def test_KARSIT_saglam_DB_de_sayim_GERCEK(o):
    """Araç kör değil: sağlam DB'de bekleyen sayısı gerçek sayı (None değil)."""
    _seans(o.db, "Pamuk Eski", 400)
    _seans(o.db, "Boncuk Taze", 10)
    assert o.db.redaksiyon_bekleyen_sayisi(365) == 1
    assert o.c.get("/api/settings/retention").json()["pending"] == 1


def test_KRITIK_arayuz_fiksturu_GERCEK_sayilamadi_yanitiyla_AYNI(o):
    """Arayüz yarısı (`screens/__tests__/veriSaklamaSayilamadi.D258.web.test.tsx`) bu GERÇEK yanıtı okur (pending null). Bayatlarsa
    KIRMIZI; yenilemek: `D258_FIKSTUR_YAZ=1` (S-A2.5)."""
    import os
    from pathlib import Path

    _seans(o.db, "Pamuk Eski", 400)
    _seans_tablosunu_kaldir(o.db)
    r = o.c.get("/api/settings/retention")
    govde = r.json()
    govde.pop("anonymization", None)
    beklenen = {"durum": r.status_code, "govde": govde}
    f = Path(__file__).resolve().parents[1] / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__"
    f = f / "retentionSayilamadi.D258.json"
    if os.environ.get("D258_FIKSTUR_YAZ") == "1":
        f.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert f.exists(), "arayüz fikstürü yok (D258_FIKSTUR_YAZ=1 ile üret)"
    assert json.loads(f.read_text(encoding="utf-8")) == beklenen, "arayüz fikstürü GERÇEK yanıttan BAYATLADI"
