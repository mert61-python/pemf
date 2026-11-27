# -*- coding: utf-8 -*-
"""Y308 uçtan uca (sanal kart / kayıtçı donanım, GERÇEK uçlar): seans sırasında kabin sensörü konumu girilir ("Sensörü taşıdım" →
konumlu, sonra serbest), seans durdurulur, seans detayı ve CSV aynı dilimleri verir. Seans yokken canlı giriş 409 (eylem söyler);
giriş hiç yapılmayan seansın detayı bugünküyle birebir. Sürüş ve STOP hiçbir konum koşuluna bağlı değildir (konum yokken de durur).
Gerçek MLX'le doğrulama Pazartesi tezgâhta (B8: "sensörü 2 noktada konumlu ölç + 1 serbest dilim")."""

from __future__ import annotations

import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import history_router

    o = ap.kur(monkeypatch, tmp_path)
    o.api.app.dependency_overrides[history_router.get_db] = lambda: (
        o.db
    )  # geçmiş uçları aparatın DB'sini okusun (D189 düzeneği)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.c.post("/api/session/stop")
    finally:
        o.api.app.dependency_overrides.pop(history_router.get_db, None)
        o.air._ai_loop_active = False
        o.geri()


def _baslat(o) -> int:
    r = o.c.post(
        "/api/session/start",
        json={
            "coil_ids": [1],
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "duration_minutes": 5,
            "mode": "Manuel",
            "patient_name": "Boncuk",
        },
    )
    assert r.status_code == 200, r.text[:300]
    with o.api._session_lock:
        return o.api._active_session.get("db_session_id")


def test_KRITIK_seans_YOKKEN_canli_giris_409_ve_GET_aktif_degil(o):
    r = o.c.post("/api/session/sensor_konumu", json={"serbest": True})
    assert r.status_code == 409 and "seans" in r.json()["detail"].lower()
    assert o.c.get("/api/session/sensor_konumu").json() == {"aktif": False, "konum": None}


def test_KRITIK_UCTAN_UCA_konumlu_ve_serbest_giris_DURDUR_detay_ve_CSV(o, monkeypatch):
    from servers import sensor_konumu as sk

    monkeypatch.setattr(sk, "kabin_noktasi", lambda s, on, y: [s, on, y])
    monkeypatch.setattr(sk, "nokta_tahmini", lambda P, b: 1.0 if b else None)
    sid = _baslat(o)
    assert o.c.get("/api/session/sensor_konumu").json() == {"aktif": True, "konum": None}
    r = o.c.post(
        "/api/session/sensor_konumu", json={"solCm": 27, "onCm": 20, "yukseklikCm": 2.5, "notMetni": "plaka yanı"}
    )
    assert r.status_code == 200, r.text
    son = o.c.get("/api/session/sensor_konumu").json()["konum"]
    assert (son["serbest"], son["sol_cm"], son["not_metni"]) == (False, 27.0, "plaka yanı")
    assert o.c.post("/api/session/sensor_konumu", json={"solCm": 999, "onCm": 1, "yukseklikCm": 1}).status_code == 422
    assert o.c.post("/api/session/sensor_konumu", json={"serbest": True}).status_code == 200
    assert o.c.get("/api/session/sensor_konumu").json()["konum"]["serbest"] is True
    assert o.c.post("/api/session/stop").status_code == 200
    d = o.c.get(f"/api/history/{sid}/details").json()
    assert [k["serbest"] for k in d["sensor_konumlari"]] == [False, True]
    dil = d["konum_dilimleri"]
    assert [x["serbest"] for x in dil][-2:] == [False, True]
    konumlu = [x for x in dil if not x["serbest"]]
    assert len(konumlu) == 1 and konumlu[0]["sol_cm"] == 27.0 and konumlu[0]["tahmin_mt"] == 1.0
    csv_metni = o.c.get(f"/api/history/{sid}/coil_runs.csv").content.decode("utf-8-sig")
    # YS2 d (B7): konum sayısı detay / PDF / CSV dosyasında dile göre (TR virgül) — TR CSV artık 2,5 yazar
    assert "konum dilimleri" in csv_metni and "27 / 20 / 2,5" in csv_metni


def test_KARSIT_giris_YAPILMAYAN_seansin_detayi_BIREBIR_ve_STOP_konumsuz_calisir(o):
    sid = _baslat(o)
    assert o.c.post("/api/session/stop").status_code == 200
    d = o.c.get(f"/api/history/{sid}/details").json()
    assert set(d) == {"session", "coil_runs", "sensor_samples"} and d["session"]["session_status"] == "stopped"


def test_canli_giris_DB_YOKKEN_503_kayit_yok(o, monkeypatch):
    _baslat(o)
    monkeypatch.setattr(o.api, "_get_treatment_db", lambda: None)
    r = o.c.post("/api/session/sensor_konumu", json={"serbest": True})
    assert r.status_code == 503
