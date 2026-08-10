# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GERİ DÖNÜŞSÜZ PII MASKELEME — operatör bilmeden çalışmaz (2026-08-09 denetimi, Tier 1).

ARIZA: seans kayıtlarındaki hasta/operatör adı ve notlar, süre dolunca `[REDACTED]` ile GERİ
DÖNÜŞSÜZ maskeleniyordu ve bu tamamen SESSİZ oluyordu. Süre yalnız `PEMF_RETAIN_PII_DAYS`
ortam değişkeniyle ayarlanabiliyordu — hiçbir veteriner bunu bilmez.

Sonuç: klinik 366. günde hasta adı yerine `[REDACTED]` görüyor, sebebini hiçbir yerde
bulamıyor ve "veritabanım bozuldu" diye destek arıyor. Tıbbi-hukuki saklama süresi ülkeye ve
kliniğe göre değişir (KVKK silmeyi ister, açılmış bir dava dosyası saklamayı) → KARAR
OPERATÖRÜNDÜR; yazılım onu sessizce almaz.
"""

import os
from datetime import datetime, timedelta

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


def _db(dizin):
    from database.treatment_history_db import TreatmentHistoryDB

    return TreatmentHistoryDB(dizin)


def _eski_seans(db, ad, gun_once):
    """Belirtilen gün kadar önce yapılmış bir seans yaz."""
    tarih = (datetime.now() - timedelta(days=gun_once)).strftime("%Y-%m-%d")
    with db._get_connection() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, "
            "patient_name, operator_name) VALUES (?,?,?,?,?)",
            (tarih, "10:00", "Manuel", ad, "Dr. Test"),
        )
        c.commit()
        return cur.lastrowid


def _adlar(db):
    with db._get_connection() as c:
        return sorted(r[0] for r in c.execute("SELECT patient_name FROM treatment_sessions"))


@pytest.fixture
def dolu(tmp_path):
    d = _db(tmp_path)
    _eski_seans(d, "EskiPamuk", 400)  # süre dolmuş
    _eski_seans(d, "YeniBoncuk", 10)  # taze
    yield d
    d.close_connections()


# ── kapı: onay yoksa maskeleme YOK ───────────────────────────────────────────


def test_KRITIK_onay_YOKKEN_maskeleme_YAPILMAZ(dolu):
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert r["sessions_pii_redacted"] == 0, "onaysiz GERI DONUSSUZ maskeleme yapildi"
    assert "EskiPamuk" in _adlar(dolu), "hasta adi sessizce silindi"


def test_KRITIK_bekleyen_kayit_sayisi_RAPORLANIR(dolu):
    """Arayüz "ne kaybedeceğini" söyleyebilsin diye sayı raporlanmalı."""
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert r["pii_pending"] == 1, f"bekleyen kayit sayisi yanlis: {r}"


def test_onaydan_SONRA_maskeleme_calisir(dolu):
    dolu.pii_onayla()
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert r["sessions_pii_redacted"] == 1
    assert "[REDACTED]" in _adlar(dolu)
    assert "YeniBoncuk" in _adlar(dolu), "sure dolmamis kayit da maskelendi"


def test_sure_SIFIRSA_hicbir_sey_maskelenmez(dolu):
    """0 = kapalı. Kliniği süresiz saklamaya zorlamak da, silmeye zorlamak da yanlış."""
    dolu.pii_onayla()
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=0
    )
    assert r["sessions_pii_redacted"] == 0
    assert "EskiPamuk" in _adlar(dolu)


# ── operatörün seçtiği süre ortam değişkenini EZER ───────────────────────────


def test_KRITIK_operator_suresi_ORTAM_DEGISKENINI_ezer(dolu):
    """Ayar arayüzden yönetilir; env yalnız varsayılandır. Aksi hâlde operatör ekrandan
    değiştirir ama hiçbir şey değişmez."""
    dolu.pii_onayla()
    dolu.pii_suresi_yaz(0)  # operatör: KAPALI
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert r["sessions_pii_redacted"] == 0, "operator karari yok sayildi"
    assert "EskiPamuk" in _adlar(dolu)


def test_operator_suresi_kalici(tmp_path):
    d = _db(tmp_path)
    try:
        assert d.pii_suresi_oku() is None
        d.pii_suresi_yaz(730)
        assert d.pii_suresi_oku() == 730
    finally:
        d.close_connections()


def test_kuru_calisma_hicbir_seyi_DEGISTIRMEZ(dolu):
    once = _adlar(dolu)
    assert dolu.redaksiyon_bekleyen_sayisi(365) == 1
    assert _adlar(dolu) == once, "on-sayim kayitlari degistirdi"


def test_zaten_maskelenmis_kayit_TEKRAR_SAYILMAZ(dolu):
    dolu.pii_onayla()
    dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert dolu.redaksiyon_bekleyen_sayisi(365) == 0, "maskelenmis kayit bekleyen sayildi"


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def api():
    from servers import api_server

    return api_server


@pytest.fixture
def client(api, tmp_path, monkeypatch, dolu):
    monkeypatch.setattr(api, "_app_data_dir", lambda: tmp_path)
    from database import treatment_history_db as thm

    monkeypatch.setattr(thm, "get_treatment_db", lambda _d: dolu)
    return TestClient(api.app, client=("127.0.0.1", 51234))


def test_API_durum_bekleyeni_bildirir(client):
    r = client.get("/api/settings/retention")
    assert r.status_code == 200, r.text[:300]
    g = r.json()
    assert g["pending"] == 1, f"arayuz kac kayit maskelenecegini goremiyor: {g}"
    assert g["acknowledged"] is False
    assert g["days"] == 365


def test_API_onay_maskelemeyi_ACAR(client, dolu):
    assert client.post("/api/settings/retention", json={"acknowledge": True}).status_code == 200
    assert dolu.pii_onayi_var_mi() is True
    assert client.get("/api/settings/retention").json()["pending"] == 0


def test_API_sure_ayarlanabilir(client, dolu):
    assert client.post("/api/settings/retention", json={"days": 730}).status_code == 200
    g = client.get("/api/settings/retention").json()
    assert g["days"] == 730 and g["configured"] is True


def test_KRITIK_sure_degistirmek_ONAY_YERINE_GECMEZ(client, dolu):
    """Süreyi değiştirmek tek başına geri dönüşsüz maskelemeyi başlatmamalı."""
    client.post("/api/settings/retention", json={"days": 30})
    assert dolu.pii_onayi_var_mi() is False, "sure degisikligi onay sayildi"


def test_gecersiz_sure_REDDEDILIR(client):
    assert client.post("/api/settings/retention", json={"days": -5}).status_code == 400
    assert client.post("/api/settings/retention", json={"days": 999999}).status_code == 400


def test_KRITIK_LANdan_kimliksiz_REDDEDILIR(api):
    """Bu uç tıbbi kaydın kalıcılığını belirler — klinik ağındaki rastgele bir cihaz
    saklama süresini 1 güne çekememeli."""
    lan = TestClient(api.app, client=("192.168.1.77", 51234))
    assert lan.get("/api/settings/retention").status_code == 403
    assert lan.post("/api/settings/retention", json={"days": 1}).status_code == 403


# ── TERMAL KORUMA DÜRÜSTLÜĞÜ (2026-08-09 denetimi, Tier 2) ──────────────────
# `firmware/README.md` "termal koruma sensör/ESP tarafındadır" diyordu. Bu ifade 1-5 numaralı
# bobinler için DOĞRU DEĞİLDİ: STM protokolünde sıcaklık alanı YOK, o bobinlerden hiç ölçüm
# gelmiyor ve tek kesme mantığı (`objectTemp > 48`) hiçbir zaman tetiklenemiyor. Yani 8 bobinin
# 5'i hastanın üzerinde hiçbir sıcaklık koruması olmadan enerjileniyor.
# Yanlış güvence korumasızlıktan tehlikelidir: koruma var sanılınca donanım önlemi ertelenir.


def test_KRITIK_firmware_README_yanlis_termal_iddiasi_ICERMEZ():
    from pathlib import Path

    p = Path(__file__).resolve().parent.parent / "firmware" / "README.md"
    metin = p.read_text(encoding="utf-8")
    assert "termal koruma sensör/ESP tarafındadır. Sahip bunu bilerek" not in metin, (
        "yanlis termal koruma iddiasi geri geldi — 1-5 bobinlerinde sensor/ESP YOK"
    )
    # Sınır AÇIKÇA yazılı olmalı ki donanım önlemi ertelenmesin.
    assert "1-5" in metin and "hiçbir sıcaklık" in metin.replace("HİÇBİR", "hiçbir"), (
        "sinirin kapsami (1-5 bobinlerinde koruma yok) README'de yazmiyor"
    )


def test_STM_protokolunde_sicaklik_alani_YOK():
    """İddianın dayanağı: STM paketi duty/phase/freq/duration taşır, sıcaklık TAŞIMAZ."""
    from pathlib import Path

    hc = (Path(__file__).resolve().parent.parent / "controllers" / "hardware_controller.py").read_text(encoding="utf-8")
    assert "temperature" not in hc.lower(), "STM kontrolcusune sicaklik eklendi — README/UI sinir notlari GUNCELLENMELI"
