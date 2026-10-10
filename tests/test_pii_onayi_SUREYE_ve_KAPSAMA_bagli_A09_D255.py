# -*- coding: utf-8 -*-
"""D2.55 · B-3.35 · SAHİP KARARI A-09 — PII maskeleme onayı ONAYLANAN SÜREYE ve KAPSAMA bağlıdır.

A-09: "Saklama süresi ya da maskeleme kapsamı her değiştiğinde YENİ ONAY istenir; etkilenecek kayıt sayısı gösterilir."
ÖLÇÜLEN KUSUR: onay süreden bağımsız bir boolean'dı (`pii_redaction_acknowledged_at` zaman damgası). Klinik 1825 günü onayladıktan sonra
süre 365'e düşürülünce, genişleyen kapsam (365–1825 gün arası seanslar) yeni onay istenmeden ve ekranda gösterilmeden bir sonraki bakım
turunda GERİ DÖNÜŞSÜZ maskeleniyordu.
GERÇEK: TreatmentHistoryDB (sentetik, tmp), `/api/settings/retention` uçları (TestClient), headless bakım turunun GERÇEK gövdesi
(`HeadlessDBMaintenance._run_maintenance`). Sahte: yalnız DB/uygulama dizini yönlendirmesi.
⚠️ Maskeleme OPT-IN kalır (varsayılan-açık YAPILMAZ — Ö.4); bu kapı yalnız onayın kapsamını ölçer.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

ESKI_AD = "Pamuk Dörtyüz"  # 400 günlük seans: 365 günlük süreye GİRER, 1825'e girmez
TAZE_AD = "Boncuk Taze"  # 10 günlük seans: hiçbir sürede maskelenmez


def _eski_seans(db, ad, gun_once):
    tarih = (datetime.now() - timedelta(days=gun_once)).strftime("%Y-%m-%d")
    with db._get_connection() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, operator_name) "
            "VALUES (?,?,?,?,?)",
            (tarih, "10:00", "Manuel", ad, "Dr. Test"),
        )
        c.commit()


def _adlar(db):
    with db._get_connection() as c:
        return sorted(r[0] for r in c.execute("SELECT patient_name FROM treatment_sessions"))


def _headless_tur(db):
    """Headless bakım turunun GERÇEK gövdesi (6 sa'lik döngünün bir turu) — süre `PEMF_RETAIN_PII_DAYS`/operatör ayarından."""
    from services.headless_db_maintenance import HeadlessDBMaintenance

    bakim = HeadlessDBMaintenance.__new__(HeadlessDBMaintenance)
    bakim.db = db
    bakim._run_maintenance()


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import treatment_history_db as thm
    from servers import api_server as api
    from servers import system_router as sr

    for ad in ("PEMF_RETAIN_PII_DAYS", "PEMF_MASK_HISTORY_PII"):
        monkeypatch.delenv(ad, raising=False)
    # Bu kapı yalnız PII adımını ölçer: öteki silme adımları kapalı (0 = adım kapalı).
    for ad in ("PEMF_RETAIN_SENSOR_DAYS", "PEMF_RETAIN_DOSE_DAYS", "PEMF_RETAIN_EVENT_DAYS", "PEMF_RETAIN_OUTBOX_DAYS"):
        monkeypatch.setenv(ad, "0")
    db = thm.TreatmentHistoryDB(tmp_path / "gecmis")
    _eski_seans(db, ESKI_AD, 400)
    _eski_seans(db, TAZE_AD, 10)
    monkeypatch.setattr(api, "_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(sr, "_pii_ayar_db", lambda: db)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    try:
        yield type("O", (), {"db": db, "c": TestClient(api.app, client=("127.0.0.1", 51955))})
    finally:
        db.close_connections()


def _durum(o):
    r = o.c.get("/api/settings/retention")
    assert r.status_code == 200, r.text[:300]
    return r.json()


def test_KRITIK_A09_sure_KISALINCA_genisleyen_kapsam_YENI_ONAYSIZ_maskelenmez_ve_bekleyen_GOSTERILIR(o):
    """Plan kapısı: 1825 gün onaylı → süre GERÇEK uçla 365'e düşer → GERÇEK bakım turu 400 günlük seansı MASKELEMEZ; ekran onaysız
    der ve 1 bekleyen gösterir. Yeni onaydan sonra maskelenir. MUTASYON: onay süreden bağımsız boolean → KIRMIZI."""
    c = o.c
    assert c.post("/api/settings/retention", json={"days": 1825}).status_code == 200
    assert c.post("/api/settings/retention", json={"acknowledge": True}).status_code == 200
    assert _durum(o)["acknowledged"] is True
    _headless_tur(o.db)
    assert ESKI_AD in _adlar(o.db), "aparat: 1825 günlük süreyle 400 günlük seans maskelenmemeliydi"

    assert c.post("/api/settings/retention", json={"days": 365}).status_code == 200
    d = _durum(o)
    _headless_tur(o.db)
    assert ESKI_AD in _adlar(o.db), (
        "süre 1825 → 365 kısalınca genişleyen kapsam YENİ ONAY istenmeden GERİ DÖNÜŞSÜZ maskelendi (A-09)"
    )
    assert (d["days"], d["acknowledged"], d["pending"]) == (365, False, 1), (
        f"süre değişince ekran yeni onay istemiyor / etkilenecek kayıt sayısını göstermiyor (A-09): {d}"
    )

    assert c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 365}).status_code == 200
    _headless_tur(o.db)
    assert ESKI_AD not in _adlar(o.db) and TAZE_AD in _adlar(o.db), "yeni onaydan sonra 365 günlük kapsam maskelenmeli"


def test_KRITIK_A09_her_DEGISIMDE_yeni_onay_geri_donus_eski_onayi_CANLANDIRMAZ(o):
    """365 onaylı → 730 → yeniden 365: A-09 'her değiştiğinde' — eski onay kendiliğinden geri gelmez."""
    c = o.c
    assert c.post("/api/settings/retention", json={"days": 365}).status_code == 200
    assert c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 365}).status_code == 200
    assert c.post("/api/settings/retention", json={"days": 730}).status_code == 200
    assert c.post("/api/settings/retention", json={"days": 365}).status_code == 200
    _headless_tur(o.db)
    assert ESKI_AD in _adlar(o.db), "süre değişip geri dönünce eski onayla maskelendi (A-09: her değişimde yeni onay)"
    assert _durum(o)["acknowledged"] is False


def test_KARSIT_ayni_sureye_yeniden_basmak_onayi_DUSURMEZ(o):
    """Değişmeyen süre (aynı düğmeye tekrar basmak) onayı geçersiz kılmaz — yalnız gerçek DEĞİŞİM yeni onay ister."""
    c = o.c
    assert c.post("/api/settings/retention", json={"days": 365}).status_code == 200
    assert c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 365}).status_code == 200
    assert c.post("/api/settings/retention", json={"days": 365}).status_code == 200
    _headless_tur(o.db)
    assert ESKI_AD not in _adlar(o.db) and TAZE_AD in _adlar(o.db)


def test_KRITIK_A09_ortam_degiskeniyle_degisen_sure_de_onayi_GECERSIZ_kilar(o, monkeypatch):
    """Operatör süre seçmemişse etkin süre `PEMF_RETAIN_PII_DAYS`'tir (vars. 365). Onay 365'e verildi; kurulum ortamı 30'a
    çekilince (kapsam genişler) yeni onay olmadan maskelenmez."""
    assert o.c.post("/api/settings/retention", json={"acknowledge": True}).status_code == 200
    with o.db._get_connection() as c:
        c.execute(
            "UPDATE treatment_sessions SET session_date=? WHERE patient_name=?",
            ((datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d"), ESKI_AD),
        )
        c.commit()
    monkeypatch.setenv("PEMF_RETAIN_PII_DAYS", "30")
    _headless_tur(o.db)
    assert ESKI_AD in _adlar(o.db), "ortamla 365 → 30 kısalan süre eski onayla maskeledi (A-09)"
    d = _durum(o)
    assert (d["days"], d["acknowledged"], d["pending"]) == (30, False, 1), d


def test_KRITIK_bayat_ekrandan_onay_REDDEDILIR_409(o):
    """Operatör 1825'i görüp onaylarken süre başka yerden 365'e çekildiyse onay 365'e YAZILMAZ (görmediği kapsamı onaylamış olurdu)."""
    c = o.c
    assert c.post("/api/settings/retention", json={"days": 365}).status_code == 200
    r = c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 1825})
    assert r.status_code == 409, f"bayat ekrandan gelen onay kabul edildi: {r.status_code} {r.text[:200]}"
    assert _durum(o)["acknowledged"] is False
    _headless_tur(o.db)
    assert ESKI_AD in _adlar(o.db)


def test_KRITIK_eski_bicim_SURESIZ_onay_hicbir_sureye_GECERLI_DEGIL(o):
    """Güncellemeden önce verilmiş onay (yalnız zaman damgası — hangi süreye verildiği bilinmiyor) hiçbir süreye geçerli sayılmaz:
    yeni onay istenir (geri dönüşsüz işlemde muhafazakâr yön). Ekran eski onayın varlığını söyleyebilsin diye `approvalStale`."""
    o.db._set_system_setting(o.db.PII_ONAY_ANAHTARI, "2026-01-02T10:00:00", "eski bicim onay")
    _headless_tur(o.db)
    assert ESKI_AD in _adlar(o.db), "süresiz eski onayla geri dönüşsüz maskeleme yapıldı (A-09)"
    d = _durum(o)
    assert (d["acknowledged"], d["pending"], d.get("approvalStale")) == (False, 1, True), d


def test_KRITIK_A09_maskeleme_KAPSAMI_degisince_onay_GECERSIZ(o, monkeypatch):
    """Maskelenen alan kümesi (seans parametrelerindeki PII adları) bir sürümde genişlerse eski onay o kapsamı kapsamaz."""
    assert o.c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 365}).status_code == 200
    monkeypatch.setattr(
        type(o.db), "_PII_PARAM_NAMES", frozenset(set(type(o.db)._PII_PARAM_NAMES) | {"patient_yeni_alan"})
    )
    _headless_tur(o.db)
    assert ESKI_AD in _adlar(o.db), "maskeleme kapsamı genişledi, eski onayla maskelendi (A-09)"
    assert _durum(o)["approvalStale"] is True


def test_KRITIK_onay_SURE_SAYI_ve_KIMLIKLE_kayda_gecer_iz_sureyi_tasir(o):
    """Onay {gun, sayi, zaman, kim} — 'etkilenecek kayıt sayısı' onay anında kayda geçer; denetim izi süreyi ve sayıyı taşır."""
    assert o.c.post("/api/settings/retention", json={"days": 365}).status_code == 200
    assert o.c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 365}).status_code == 200
    onay = o.db.pii_onayi_oku()
    assert (onay["gun"], onay["sayi"]) == (365, 1) and onay["zaman"], onay
    iz = o.db.denetim_oku(10, "retention.onay")
    assert iz and iz[0]["item_count"] == 1 and json.loads(iz[0]["detail"])["gun"] == 365, iz
    d = _durum(o)
    assert (d["approvedDays"], d["approvedCount"]) == (365, 1), d


def test_KRITIK_arayuz_fiksturu_GERCEK_bayat_onay_yanitiyla_AYNI(o):
    """Arayüz yarısı (`screens/__tests__/veriSaklamaPiiOnay.D255.web.test.tsx`) bu GERÇEK yanıtı okur: 1825 onaylıydı, süre 365'e
    düştü → onaysız, 1 bekleyen, eski onay 1825 günlüktü. Bayatlarsa KIRMIZI; yenilemek: `D255_FIKSTUR_YAZ=1` (S-A2.5)."""
    import os
    from pathlib import Path

    assert o.c.post("/api/settings/retention", json={"days": 1825}).status_code == 200
    assert o.c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 1825}).status_code == 200
    assert o.c.post("/api/settings/retention", json={"days": 365}).status_code == 200
    r = o.c.get("/api/settings/retention")
    govde = r.json()
    govde.pop("anonymization", None)  # D2.54 bloğu kendi fikstüründe; bu fikstür PII onayını taşır
    beklenen = {"durum": r.status_code, "govde": govde}
    f = Path(__file__).resolve().parents[1] / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__"
    f = f / "retentionPiiOnay.D255.json"
    if os.environ.get("D255_FIKSTUR_YAZ") == "1":
        f.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert f.exists(), "arayüz fikstürü yok (D255_FIKSTUR_YAZ=1 ile üret)"
    assert json.loads(f.read_text(encoding="utf-8")) == beklenen, "arayüz fikstürü GERÇEK yanıttan BAYATLADI"
