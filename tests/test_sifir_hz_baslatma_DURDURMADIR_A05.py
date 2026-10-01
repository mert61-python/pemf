# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.53 · B-1.10 · A-05 — 0 Hz BAŞLATMA = o bobin için STOP; protokol sınırı (Ö.4-Y9) KALIR.

SAHİP KARARI A-05 (2026-09-29, "önerilen"): arayüzün "frekans 0 → bobini parkla" niyeti DURDURMADIR. Protokol
sınırı (`normalize_frequency_hz` / `normalize_esp_frequency_hz`, 1 Hz tabanı) KALDIRILMAZ; sıfır olmayan
frekanslarda aynen çalışır; 0 Hz sınıra ULAŞMADAN STOP olarak ele alınır.

ÖLÇÜLEN KUSUR (plan tv-F5_4, v-A26): `update_coil(freq=0, duty=50, start=True)` paketi freq 1.0 / duty 0.5 ile
kuyruğa koyup "success" dönüyordu — operatör bobini parkladığını sanırken bobin 1 Hz'de, girdiği duty ile enerjili;
kayıt "0 Hz". Arayüz 0'ı bilerek korur (`CoilParameterPanel` NaN-guard yorumu) ve `start: true` ile gönderir.

Kapı GERÇEK `HardwareController` (`kayitci_donanim.gercek_hc`, paketler firmware aynasıyla çözülür) ve GERÇEK
uçlarla koşar; ölçüt KUYRUKTAKİ PAKET + bobin durumu + koşu kaydı çağrıları. KARŞIT (Y9): sıfır olmayan alt-sınır
değeri (0,5 Hz) 1 Hz'e normalize edilip SÜRÜLÜR — sınır kaldırılırsa kırmızı.
"""

from __future__ import annotations

import pytest
from topoloji import TUM_ESP, TUM_STM

_STM_B = min(TUM_STM)


def _cozum(hc, i=-1):
    from kayitci_donanim import paket_coz

    return paket_coz(hc.core._hw_send_queue.paketler[i])


def _surulen(hc, coil_id=_STM_B):
    """Senaryo: 0 Hz isteğinden ÖNCE bobin GERÇEKTEN sürülüyor (yoksa "duty 0" her pakette zaten doğrudur)."""
    assert hc.update_coil(coil_id, 100.0, 30.0, 0.0, 1, start=True) is True
    duty = _cozum(hc)[0]
    assert duty[coil_id - 1] == pytest.approx(0.30), f"senaryo: bobin surulmuyor {duty}"


@pytest.fixture
def ortam(monkeypatch):
    from kayitci_donanim import gercek_hc
    from servers import api_server as api

    yayinlar: list = []
    kosu = {"basla": [], "bitir": []}
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: yayinlar.append((topic, payload)) or False)
    monkeypatch.setattr(api, "_begin_coil_run", lambda *a, **k: kosu["basla"].append(a))
    monkeypatch.setattr(api, "_finish_coil_run", lambda *a, **k: kosu["bitir"].append(a))
    monkeypatch.setitem(api._active_session, "is_active", False)
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        monkeypatch.setattr(api.state, "core", hc.core)
        yield api, hc, yayinlar, kosu


def test_KRITIK_update_coil_0Hz_baslatma_bobini_DURDURUR_ve_baslatmadi_der(ortam):
    from utils.stm32_protocol_limits import normalize_esp_frequency_hz, normalize_frequency_hz

    _api, hc, _y, _k = ortam
    _surulen(hc)
    for sifir in (0, 0.0, "0"):
        sonuc = hc.update_coil(_STM_B, sifir, 50.0, 0.0, 1, start=True)
        duty, _faz, freq, *_ = _cozum(hc)
        assert duty[_STM_B - 1] == 0.0, (
            f"0 Hz ({sifir!r}) bobini SURDU: duty {duty[_STM_B - 1]} freq {freq[_STM_B - 1]}"
        )
        assert hc.coils_state[_STM_B]["is_running"] is False, f"0 Hz ({sifir!r}) bobini 'calisiyor' birakti"
        assert sonuc is False, f"0 Hz ({sifir!r}) START'i 'basarili' dondu — cagiranlar kosu kaydi acar"
    # Y9 taşıyıcı: protokol sınırı YERİNDE (sıfır olmayan değerlerde 1 Hz tabanı)
    assert normalize_frequency_hz(0) == 1.0 and normalize_esp_frequency_hz(0) == 1.0


def test_KRITIK_start_all_0Hz_TUM_bobinleri_DURDURUR(ortam):
    _api, hc, _y, _k = ortam
    assert hc.start_all_coils(100.0, 30.0, 0.0, 1) is True
    assert hc.start_all_coils(0, 50.0, 0.0, 1) is False, "0 Hz start_all 'basarili' dondu"
    assert all(d == 0.0 for d in _cozum(hc)[0]), f"0 Hz start_all bobinleri SURDU: {_cozum(hc)[0]}"
    assert not any(s["is_running"] for s in hc.coils_state.values())


def test_KRITIK_tekil_uc_0Hz_PARK_istegi_STOP_olarak_uygulanir(ortam):
    from fastapi.testclient import TestClient

    api, hc, yayinlar, kosu = ortam
    _surulen(hc)
    r = TestClient(api.app).post(f"/api/coil/{_STM_B}/control", json={"start": True, "freq": 0, "duty": 50, "phase": 0})
    g = r.json()
    assert _cozum(hc)[0][_STM_B - 1] == 0.0, "tekil uc 0 Hz isteginde bobini SURDU"
    assert g.get("status") == "success" and g.get("sifirHzDurdurma") is True, f"park istegi DURDURMA sayilmadi: {g}"
    assert not kosu["basla"], f"0 Hz isteginde KOSU KAYDI acildi: {kosu['basla']}"
    assert kosu["bitir"], "0 Hz (durdurma) acik kosuyu KAPATMADI"
    if TUM_ESP:  # ESP bobini (kapalı olsa da kod yolu silinmez — Ö.4-Y7): STOP yayını, 1 Hz START değil
        b = min(TUM_ESP)
        r = TestClient(api.app).post(f"/api/coil/{b}/control", json={"start": True, "freq": 0, "duty": 50, "phase": 0})
        komutlar = [p.get("command") for t, p in yayinlar if t == f"pemf/coil/{b}/control"]
        assert komutlar and komutlar[-1] == "stop", f"ESP bobini 0 Hz isteginde STOP almadi: {komutlar}"
        assert r.json().get("sifirHzDurdurma") is True


def test_KRITIK_batch_0Hz_PARK_istegi_STOP_olarak_uygulanir(ortam):
    from fastapi.testclient import TestClient

    api, hc, yayinlar, kosu = ortam
    _surulen(hc)
    bobinler = [_STM_B] + sorted(TUM_ESP)
    r = TestClient(api.app).post("/api/coil/batch", json={"coil_ids": bobinler, "start": True, "freq": 0, "duty": 50})
    g = r.json()
    assert _cozum(hc)[0][_STM_B - 1] == 0.0, "batch 0 Hz isteginde STM bobinini SURDU"
    assert g.get("sifirHzDurdurma") is True, f"batch park istegi DURDURMA sayilmadi: {g}"
    assert not kosu["basla"], f"batch 0 Hz isteginde KOSU KAYDI acildi: {kosu['basla']}"
    for b in sorted(TUM_ESP):
        komutlar = [p.get("command") for t, p in yayinlar if t == f"pemf/coil/{b}/control"]
        assert komutlar and komutlar[-1] == "stop", f"batch ESP {b} 0 Hz isteginde STOP almadi: {komutlar}"


def test_KRITIK_seans_0Hz_BASLAMAZ_bobin_SURULMEZ_neden_DURUSTCE_soylenir(ortam, monkeypatch, tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import coil_run_tracker

    api, hc, _y, _k = ortam
    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    r = TestClient(api.app).post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 0,
            "duty": 50,
            "phase": 0,
            "intensity": 0.0,
            "duration_minutes": 5,
            "coil_ids": [_STM_B],
            "patient_name": "Pamuk",
        },
    )
    assert r.status_code != 200, f"0 Hz seans BASLADI: {r.status_code} {r.text[:200]}"
    assert "0 Hz" in r.text and "firmware" not in r.text.lower(), f"neden yanlis soylendi: {r.text[:300]}"
    with api._session_lock:
        assert api._active_session.get("is_active") is not True, "0 Hz seans 'aktif' kaldi"
    assert not any(
        d > 0 for p in hc.core._hw_send_queue.paketler for d in __import__("kayitci_donanim").paket_coz(p)[0]
    )


def test_KARSIT_sifir_OLMAYAN_alt_sinir_degeri_1Hz_e_normalize_edilip_SURULUR_Y9(ortam):
    """Ö.4-Y9: protokol sınırı TAŞIYICI — 0,5 Hz durdurma DEĞİLDİR, 1 Hz'e çekilip sürülür (A-05 yalnız tam 0)."""
    from fastapi.testclient import TestClient

    api, hc, _y, kosu = ortam
    assert hc.update_coil(_STM_B, 0.5, 30.0, 0.0, 1, start=True) is True
    duty, _faz, freq, *_ = _cozum(hc)
    assert freq[_STM_B - 1] == pytest.approx(1.0) and duty[_STM_B - 1] == pytest.approx(0.30), (
        f"0,5 Hz protokol sinirinda 1 Hz'e normalize edilmedi / surulmedi: freq {freq[_STM_B - 1]} duty {duty[_STM_B - 1]}"
    )
    r = TestClient(api.app).post(f"/api/coil/{_STM_B}/control", json={"start": True, "freq": 0.5, "duty": 30})
    assert r.json().get("status") == "success" and "sifirHzDurdurma" not in r.json()
    assert kosu["basla"], "sifir olmayan frekansta kosu kaydi acilmadi"
    # STOP (start=False) 0 Hz ile de olağan durdurmadır
    assert hc.update_coil(_STM_B, 0, 0, 0, 0, start=False) is True
