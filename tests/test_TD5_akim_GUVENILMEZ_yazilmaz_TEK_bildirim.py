# Author: mertaygn, cglrgrkn
"""TD5 (tezgâh Oturum 13 · K4, A4) — güvenilmez akım GÖSTERİLMEZ / KAYDEDİLMEZ, bobin başına TEK birleşik uyarı.

ÖLÇÜLEN KUSUR (tezgâh, PSU KAPALI): kart takılı olmayan ACS712 girişlerinden `C=1,I=74.630` · `C=3,I=19.820,X=1` basıyordu; backend
sayıları "ölçülmüş" yayınlıyor (arayüz 10–115 A, "Anlık Güç" 6,3 W) ve doz kaydına (dakika ortalaması) yazıyordu; her `X=1` 0→1
geçişinde "akımı ölçüm aralığını AŞTI (ADC tavanı ~12 A) — gösterilen akım GÜVENİLMEZ ve doz kaydına öyle giriyor" → 46 bildirim.
SÖZLEŞME: `X=1` ya da ACS712-30A aralığı dışı RMS → `current` ATILIR, `akim_guvenilmez`; canlı durum `akimGuvenilmez`, `currentA`
/ `measuredFields` / sensör kaydı YAZILMAZ, önceki değerin tazelik damgası düşer; bildirim bobin başına STM bağlantısı boyunca TEK:
"Akım ölçümü bu bobinde güvenilir değil — doz kaydına akım yazılmadı."; yeni bağlantıda (kart değişmiş olabilir) yeniden hak eder.
"""

from __future__ import annotations

import logging
import threading

import pytest

#: Tezgâh kanıtındaki GERÇEK satırlar (`tz13\kanit\C6_yeni_imaj_acilis.txt`).
YUZEN_74A = "-> STM_TELE: C=1,I=74.630"
DOYGUN = "-> STM_TELE: C=3,I=19.820,X=1"
GERCEK = "-> STM_TELE: C=3,I=2.000"
METIN = "Akım ölçümü bu bobinde güvenilir değil — doz kaydına akım yazılmadı."


@pytest.fixture
def cekirdek():
    import headless_core as hcm

    c = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    c.logger = logging.getLogger("test-td5")
    c._stm_state_lock = threading.RLock()
    return c


@pytest.mark.parametrize("satir", [YUZEN_74A, DOYGUN])
def test_KRITIK_guvenilmez_akim_ATILIR_bayrak_konur(cekirdek, satir):
    g = cekirdek._parse_stm_tele(satir)
    assert g is not None and g.get("akim_guvenilmez") is True and "current" not in g, g


def test_KARSIT_aralik_ici_akim_TASINIR(cekirdek):
    g = cekirdek._parse_stm_tele(GERCEK)
    assert g == {"coil_id": 3, "current": 2.0}, g


class _Olay:
    def __init__(self, tur, data=None):
        self.event_type = tur
        self.data = data or {}


@pytest.fixture
def api(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin, bildirim, kayit = [], [], []
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", lambda m, s="info": bildirim.append((m, s)))
    monkeypatch.setattr(a._sensor_kaydedici, "kaydet_arka_planda", lambda *x, **k: kayit.append(x))
    with a._live_state_lock:
        coil = a._live_state["coils"][2]
        monkeypatch.setitem(coil, "currentA", 0.0)
        monkeypatch.setitem(coil, "measuredFields", [])
        monkeypatch.setitem(coil, "akimGuvenilmez", False)
    monkeypatch.setitem(a._coil_olculen_alanlar, 2, {})
    bildirilen = getattr(a, "_akim_guvenilmez_bildirildi", None)
    if bildirilen is not None:
        monkeypatch.setattr(a, "_akim_guvenilmez_bildirildi", set())
    return a, yayin, bildirim, kayit


def _uyarilar(bildirim):
    return [m for m, _s in bildirim if "Bobin 3" in m and ("güvenilir değil" in m or "AŞTI" in m)]


def test_KRITIK_doygun_akim_EKRANA_ve_KAYDA_yazilmaz_TEK_bildirim(api, cekirdek):
    a, yayin, bildirim, kayit = api
    for _ in range(3):
        a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(DOYGUN)))
    coil = a._live_state["coils"][2]
    assert coil["currentA"] == 0.0 and "currentA" not in coil["measuredFields"], coil
    assert coil.get("akimGuvenilmez") is True, coil
    assert not kayit, f"güvenilmez akım sensör kaydına gitti: {kayit}"
    u = _uyarilar(bildirim)
    assert len(u) == 1 and METIN in u[0], bildirim


def test_KRITIK_yuzen_giris_aci_kapa_SELI_BITER(api, cekirdek):
    """Tezgâh: yüzen girişte X her saniye açılıp kapandı → 46 bildirim. Aynı bağlantıda tekrar tekrar gelse de TEK uyarı."""
    a, _y, bildirim, _k = api
    for _ in range(5):
        a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(DOYGUN)))
        a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(GERCEK)))
    assert len(_uyarilar(bildirim)) == 1, bildirim


def test_KARSIT_guvenilir_akim_YAZILIR_bayrak_iner_yeni_baglantida_uyari_HAK_EDER(api, cekirdek, monkeypatch):
    a, _y, bildirim, kayit = api
    monkeypatch.setattr(a, "update_live_stm_status", lambda *x, **k: None)
    a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(DOYGUN)))
    a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(GERCEK)))
    coil = a._live_state["coils"][2]
    assert coil["currentA"] == pytest.approx(2.0) and coil.get("akimGuvenilmez") is False and kayit
    a._handle_backend_event(_Olay("hardware.stm.connected"))
    a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(DOYGUN)))
    assert len(_uyarilar(bildirim)) == 2, bildirim


def test_KRITIK_ayristiriciyi_atlayan_olay_da_YAZILMAZ(api):
    """API kendi başına da uygular: `current_saturated` ya da aralık dışı akım taşıyan olay (ayrıştırıcı dışı üretici)."""
    a, _y, bildirim, kayit = api
    a._handle_backend_event(_Olay("hardware.stm.telemetry", {"coil_id": 3, "current": 12.1, "current_saturated": True}))
    a._handle_backend_event(_Olay("hardware.stm.telemetry", {"coil_id": 3, "current": 74.6}))
    coil = a._live_state["coils"][2]
    assert coil["currentA"] == 0.0 and coil.get("akimGuvenilmez") is True and not kayit, coil
    assert len(_uyarilar(bildirim)) == 1, bildirim


def test_aralik_sabiti_cekirdek_ile_AYNI():
    import headless_core
    from servers import api_server

    assert headless_core.ACS712_AZAMI_A == api_server._ACS712_AZAMI_A == 30.0


def test_KRITIK_onceki_guvenilir_deger_TAZE_SAYILMAZ(api, cekirdek):
    a, _y, _b, _k = api
    a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(GERCEK)))
    assert "currentA" in a._live_state["coils"][2]["measuredFields"]
    a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(DOYGUN)))
    assert "currentA" not in a._live_state["coils"][2]["measuredFields"]
    assert "currentA" not in a._coil_olculen_alanlar[2]
