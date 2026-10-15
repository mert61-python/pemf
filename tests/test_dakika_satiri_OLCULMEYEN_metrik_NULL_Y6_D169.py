# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.69 · B-1.7 · S-1.3 · sahip kararı Y6 — ölçülmemiş metrik DAKİKA SATIRINA (sensor_samples) 0.0 değil NULL yazılır.

Y6 (SAHIP-CEVAPLARI): "Ölçülmemiş metrik (sıcaklık, akım, alan) NULL / '—' yazılır, 0.0 YAZILMAZ" — tıbbi kayıt
ölçülmeyeni ölçülmüş gibi göstermemeli. Koşu ÖZETİ kısmı 1-E'de (D1.89) düzeldi; dakika satırları (`_emit_minute_averages`)
"eski davranışla birebir" diye 0.0 yazmaya devam ediyordu (1-E §7 #3): bobin 1-5 (yalnız akım ölçer) her dakika
`temperature_c=0.0, magnetic_field_mt=0.0` yazıyor, seans detayının sıcaklık grafiği 0 °C çizgisi çizip "bu seansta
sensör verisi yok" mesajını bastırıyordu.

KAPI: GERÇEK `hardware.stm.telemetry` işleyicisi + GERÇEK sensör döngüsü turu (`tests/dongu_tek_tur.py`, dakika sınırı
o iş parçacığında atlanır) → GERÇEK `_emit_minute_averages` → tampondaki satır.
"""

from __future__ import annotations

import pytest
from akim_olcumu_aparati import akim_olcumu_acik  # noqa: F401  (CH4 · Y154: akım sensörü AÇIKKEN yolu)
from dongu_tek_tur import bir_tur_kos


class _Olay:
    def __init__(self, govde: dict):
        self.event_type = "hardware.stm.telemetry"
        self.data = govde


_ALANLAR = ("objectTemp", "ambientTemp", "magneticMt", "currentA")


@pytest.fixture()
def api(monkeypatch):
    from servers import api_server as api

    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_flush_sensor_buffer_if_active", lambda: None)  # satır tamponda okunur (DB'ye gitmesin)

    def _temizle():
        with api._live_state_lock:
            for i in range(7):
                c = api._live_state["coils"][i]
                for a in _ALANLAR:
                    c[a] = 0.0
                c["measuredFields"] = []
                c["running"] = False
        for i in range(8):
            api._coil_olculen_alanlar.pop(i, None)
            api._coil_last_telemetry.pop(i, None)
        with api._minute_acc_lock:
            api._minute_acc.clear()
        with api._sensor_sample_buffer_lock:
            api._sensor_sample_buffer.clear()
        with api._session_lock:
            api._active_session["is_active"] = False

    _temizle()
    yield api
    _temizle()


def _dakika(api, coil_id: int) -> dict:
    """Bobin çalışırken sensör döngüsünün bir turu + DAKİKA SINIRI → o bobinin dakika satırı."""
    with api._live_state_lock:
        api._live_state["coils"][coil_id - 1]["running"] = True
    with api._session_lock:
        api._active_session["is_active"] = True
    uyku, hatalar = bir_tur_kos(api._sensor_persistence_loop, dakika_atla=True)
    assert (uyku, hatalar) == (1, []), f"aparat: sensör döngüsü turu uyku={uyku} hata={hatalar}"
    with api._sensor_sample_buffer_lock:
        satirlar = [r for r in api._sensor_sample_buffer if str(r.get("coil_id")) == str(coil_id)]
    assert satirlar, "aparat: dakika satırı üretilmedi (sınır atlanmadı?)"
    return satirlar[-1]


def test_KRITIK_Y6_yalniz_AKIM_olcen_bobinin_dakika_satirinda_sicaklik_ve_alan_NULL(api):
    api._handle_backend_event(_Olay({"coil_id": 2, "current": 0.41}))
    satir = _dakika(api, 2)
    assert satir["current_a"] == pytest.approx(0.41), f"aparat: ölçülen akım satıra girmedi: {satir}"
    assert satir["temperature_c"] is None and satir["magnetic_field_mt"] is None and satir["ambient_temp_c"] is None, (
        "ölçülmemiş metrik dakika satırına 0.0 ('ölçüldü, 0') yazıldı: "
        f"T={satir['temperature_c']!r} B={satir['magnetic_field_mt']!r} ortam={satir['ambient_temp_c']!r}"
    )


def test_KRITIK_Y6_yalniz_SICAKLIK_olcen_bobinin_dakika_satirinda_akim_NULL(api):
    api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 41.5}))
    satir = _dakika(api, 6)
    assert satir["temperature_c"] == pytest.approx(41.5)
    assert satir["current_a"] is None, f"ölçülmemiş akım dakika satırına {satir['current_a']!r} yazıldı"


def test_KARSIT_olculen_SIFIR_degeri_0_kalir_NULL_olmaz(api):
    """Ölçülmüş gerçek sıfır (akım 0,0 A) ile ölçülmemiş ayırt edilebilmeli: ölçülen 0 → 0.0 (NULL DEĞİL)."""
    api._handle_backend_event(_Olay({"coil_id": 3, "current": 0.0}))
    satir = _dakika(api, 3)
    assert satir["current_a"] == 0.0 and satir["current_a"] is not None
