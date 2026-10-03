# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.97 · B-10.235 · B-10.236 · B-10.259 — `api_server` üzerindeki üç metin/yorum çapalı kapı DAVRANIŞA bağlanır.

ÖLÇÜLEN KÖRLÜK (bu commit'te; ürün bugün doğru):
  (235) `test_esp_control_topic` selftest/reset'in ESP yayınını KAYNAK METNİNDE `_esp_control_broadcast(` sayarak
        arıyordu → reset'teki çağrı YORUMA alınsa da sayı tutar (yorum satırı aynı metni taşır), kapı yeşil kalır;
        seans dışı ESP bobini enerjili kalırdı.
  (236) `test_esp_gozetimsiz_sure_kapagi::test_kapak_STM_ile_AYNI_KAYNAKTAN_gelir` sabitin ADINI kaynakta arıyordu —
        docstring adı taşıdığı için kapak işlevi `return 7200` yazsa (import silinse) yeşil kalır; davranış kolları da
        yeşil kalır çünkü bugünkü sabit 120 dk = 7200 sn. İki transport bir gün ayrışırdı (bulgunun kök nedeni).
  (259) `test_surum_kaymasi_guvenlik_sozlesmesi` teyitsiz durdurmanın 409 `detail`indeki ACİL DURDUR yönlendirmesini
        kaynağın 4000 karakterlik penceresinde arıyordu — pencere içindeki YORUM "ACİL DURDUR'a basın" metnini taşır;
        uyarı metninden yönlendirme silinse yeşil kalır, eski istemci operatöre ne yapacağını söylemez.
"""

from __future__ import annotations

import ast
import inspect
import threading

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    ns.c = TestClient(ns.api.app, client=("127.0.0.1", 51237))
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
            hc.stop_all_coils()
    finally:
        ns.geri()


# ── (235) selftest / reset_pwm ESP yayınını GERÇEKTEN yapar ──────────────────────────────────────────────────
def test_KRITIK_235_selftest_ve_reset_ucu_ESP_yayinini_GERCEKTEN_cagirir(o, monkeypatch):
    cagrilar: list = []
    olay = threading.Event()

    def _kayitci(command, id_prefix, extra=None):
        cagrilar.append((command, id_prefix))
        if len(cagrilar) >= 2:
            olay.set()

    monkeypatch.setattr(o.api, "_esp_control_broadcast", _kayitci)
    assert o.c.post("/api/hardware/selftest").status_code == 200
    assert o.c.post("/api/hardware/reset_pwm").status_code == 200
    assert olay.wait(10), f"uçların arka plan iş parçacıkları ESP yayınını yapmadı: {cagrilar}"
    assert sorted(cagrilar) == [("SELFTEST", "selftest"), ("stop", "reset")], (
        f"selftest/reset ESP bobinlerine (6-8) yayın yapmıyor — seans dışı ESP bobini enerjili kalır: {cagrilar}"
    )


# ── (236) ESP gözetimsiz kapağı TEK KAYNAKTAN (hardware_controller) ───────────────────────────────────────────
def test_KRITIK_236_esp_kapagi_hardware_controller_SABITINDEN_okunur_AST_ve_davranis(monkeypatch):
    from controllers import hardware_controller as hwc
    from servers import api_server as api

    fn = ast.parse(inspect.getsource(api._esp_duration_seconds)).body[0]
    govde = fn.body[1:] if ast.get_docstring(fn) is not None else fn.body
    adlar = {
        n.id if isinstance(n, ast.Name) else n.attr
        for g in govde
        for n in ast.walk(g)
        if isinstance(n, (ast.Name, ast.Attribute))
    }
    sayilar = [n.value for g in govde for n in ast.walk(g) if isinstance(n, ast.Constant) and isinstance(n.value, int)]
    assert "GOZETIMSIZ_VARSAYILAN_DAKIKA" in adlar, (
        "ESP kapak işlevi (docstring HARİÇ) klinik sabiti hardware_controller'dan OKUMUYOR — ayrı bir sayı yazılmış"
    )
    assert not [s for s in sayilar if s >= 600], f"ESP kapak işlevinde gömülü süre sabiti: {sayilar}"
    monkeypatch.setattr(hwc, "GOZETIMSIZ_VARSAYILAN_DAKIKA", 37)
    assert api._esp_duration_seconds(0) == 37 * 60, "STM sınırı değişince ESP kapağı İZLEMEDİ — iki transport ayrıştı"
    assert api._esp_duration_seconds(90) == 90, "açıkça verilen süreye dokunuldu (yeni üst sınır DEĞİL)"


# ── (259) teyitsiz durdurma 409'unun detail'i ACİL DURDUR'u söyler — GERÇEK yanıttan ─────────────────────────
def test_KRITIK_259_teyitsiz_durdurma_409_detail_ACIL_DURDUR_der_GERCEK_yanit(o, monkeypatch):
    r = o.c.post(
        "/api/session/start",
        json={"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1, 2]},
    )
    assert r.status_code == 200, r.text[:200]
    # Kablo çıkık / gönderici takılı: çekirdek yazım izi BİLDİRİR ama STOP'un porta yazıldığını doğrulayamaz (STOP yine
    # kuyruğa verilir). Kayıtçı çekirdekte bu kancalar yok (yokken ürün "kuyruğa verildi"yi teyit sayar) → eklenir.
    monkeypatch.setattr(o.hc.core, "hw_yazim_isareti", lambda: 1, raising=False)
    monkeypatch.setattr(o.hc.core, "hw_stop_sirasi_yazildi_bekle", lambda *a, **k: False, raising=False)
    monkeypatch.setattr(o.hc.core, "hw_stop_yazildi_bekle", lambda *a, **k: False, raising=False)
    y = o.c.post("/api/session/stop")
    assert y.status_code == 409, f"aparat: teyitsiz durdurma beklenirdi ({y.status_code}: {y.text[:200]})"
    g = y.json()
    assert sorted(g.get("hardware_stop_unconfirmed") or []) == [1, 2], g
    detay = str(g.get("detail") or "")
    assert "ACİL DURDUR" in detay, (
        f"teyitsiz durdurmanın 409 detail'i operatöre ACİL DURDUR'u söylemiyor (eski istemci YALNIZ detail'i "
        f"gösterir): {detay!r}"
    )
