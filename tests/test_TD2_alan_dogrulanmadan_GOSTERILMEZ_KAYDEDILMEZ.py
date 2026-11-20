# Author: mertaygn, cglrgrkn
"""TD2 (tezgâh Oturum 13 · K6) — doğrulanmamış manyetik alan GÖSTERİLMEZ, seans CSV'sine / ölçülen yoğunluğa YAZILMAZ.

ÖLÇÜLEN KUSUR: MLX90393 kazanç ayarı uygulanmadığında (firmware geri okumuyordu) her okuma ~5× büyük çıkıyor ve "Ölçülen (mT)",
seans alan CSV'si sessizce yanlış dolduruluyordu (tezgâh: Dünya alanı 4–5×; bobin |pp| 13,3 mT ≈ gerçekte 2,7–3,3).
SÖZLEŞME (firmware TD2 ile birlikte): firmware alanı yalnız GERİ OKUNAN ayarla basar ve her `B=` satırına `GS=<kazanç>,RS=<çözünürlük>`
doğrulama işareti ekler; açılış `STM_SENS` satırı `ayar=DOGRULANDI|DOGRULANAMADI` der. Backend:
  * işaretsiz `B=` (ayarı doğrulanmamış firmware — tezgâhtaki GERÇEK satır) → alan anahtarları ATILIR, `alan_dogrulanamadi` bayrağı;
  * `STM_SENS … ayar=DOGRULANAMADI` → aynı bayrak (firmware o hatta alan basmaz);
  * canlı durum: bobin `alanDogrulanamadi: true`, `magneticMt` / `measuredFields` YAZILMAZ, sensör kaydı ve seans alan kaydı
    ÇAĞRILMAZ; bildirim TEK sefer (kod FW-ALAN); doğrulanmış alan gelince bayrak iner, değer yazılır.
⚠️ AI Pro `achieved_B` sensörden GELMEZ (sabit `ai_router._AI_ACHIEVED_B` / `ai_pro_hedef.KEDI_ACHIEVED_B` = 1 mT) — kapı bunu da pinler.
"""

from __future__ import annotations

import logging
import threading

import pytest

#: Tezgâh kanıtı (`tz13\kanit\C6_yeni_imaj_acilis.txt`) — HEAD e872 imajının işaretsiz satırı (~5× ölçek).
ESKI_TELE = "-> STM_TELE: C=6,B=1.866,N=284,XN=-0.445,XP=-0.306,YN=1.130,YP=1.262,ZN=-1.359,ZP=-1.139"
YENI_TELE = "-> STM_TELE: C=6,B=0.050,N=344,XN=0.030,XP=0.030,YN=0.000,YP=0.000,ZN=-0.040,ZP=-0.040,GS=0,RS=0"
SENS_TUTMADI = "-> STM_SENS: C=6 I2C2 sicaklik=0x00 alan=0x18 kazanc=7 res=0 ayar=DOGRULANAMADI"
SENS_TUTTU = "-> STM_SENS: C=6 I2C2 sicaklik=0x00 alan=0x18 kazanc=0 res=0 ayar=DOGRULANDI"


@pytest.fixture
def cekirdek():
    import headless_core as hcm

    c = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    c.logger = logging.getLogger("test-td2")
    c._stm_state_lock = threading.RLock()
    c.stm_kimlik = None
    c.stm_uyumlu = None
    c.stm_uyumsuzluk_sebebi = ""
    c.olaylar = []
    c._set_stm_connected = lambda v: None
    c._publish_event = lambda tur, veri=None, **k: c.olaylar.append((tur, veri))
    return c


def test_KRITIK_isaretsiz_B_alani_ATILIR_bayrak_konur(cekirdek):
    g = cekirdek._parse_stm_tele(ESKI_TELE)
    assert g is not None and g.get("alan_dogrulanamadi") is True, g
    for k in ("magnetic_field", "magnetic_samples", "mag_x_min", "mag_z_max"):
        assert k not in g, f"doğrulanmamış alan anahtarı sızdı: {k} → {g}"


def test_KARSIT_isaretli_B_alani_TASINIR(cekirdek):
    g = cekirdek._parse_stm_tele(YENI_TELE)
    assert g["magnetic_field"] == pytest.approx(0.050) and g["mag_z_min"] == pytest.approx(-0.040), g
    assert "alan_dogrulanamadi" not in g, g


def test_KRITIK_STM_SENS_ayar_DOGRULANAMADI_olay_uretir(cekirdek):
    cekirdek._handle_stm_line(SENS_TUTMADI, retry_last_payload=lambda: None)
    assert ("hardware.stm.telemetry", {"coil_id": 6, "alan_dogrulanamadi": True}) in cekirdek.olaylar, cekirdek.olaylar
    cekirdek.olaylar.clear()
    cekirdek._handle_stm_line(SENS_TUTTU, retry_last_payload=lambda: None)
    assert not [o for o in cekirdek.olaylar if o[0] == "hardware.stm.telemetry"], cekirdek.olaylar


@pytest.fixture
def api(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin, bildirim, kayit, seans = [], [], [], []
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", lambda m, s="info": bildirim.append((m, s)))
    monkeypatch.setattr(a._sensor_kaydedici, "kaydet_arka_planda", lambda *x, **k: kayit.append(x))
    monkeypatch.setattr(a._seans_alan, "olcum", lambda *x, **k: seans.append(x))
    with a._live_state_lock:
        coil = a._live_state["coils"][5]
        monkeypatch.setitem(coil, "magneticMt", 0.0)
        monkeypatch.setitem(coil, "measuredFields", [])
        monkeypatch.setitem(coil, "alanDogrulanamadi", False)
    monkeypatch.setitem(a._coil_olculen_alanlar, 5, {})
    return a, yayin, bildirim, kayit, seans


class _Olay:
    def __init__(self, data):
        self.event_type = "hardware.stm.telemetry"
        self.data = data


def test_KRITIK_dogrulanmamis_alan_CANLI_duruma_CSVye_seans_kaydina_YAZILMAZ(api, cekirdek):
    a, yayin, bildirim, kayit, seans = api
    a._handle_backend_event(_Olay(cekirdek._parse_stm_tele(ESKI_TELE)))
    a._handle_backend_event(_Olay(cekirdek._parse_stm_tele(ESKI_TELE)))
    coil = a._live_state["coils"][5]
    assert coil["alanDogrulanamadi"] is True and coil["magneticMt"] == 0.0, coil
    assert "magneticMt" not in (coil.get("measuredFields") or []), coil
    assert not kayit and not seans, f"doğrulanmamış alan kayda gitti: {kayit} {seans}"
    uyari = [
        m for m, _s in bildirim if "doğrulanamadı" in m and "FW-ALAN" in m
    ]  # Y306: metin "Kabin sensörü (MLX …) doğrulanamadı"
    assert len(uyari) == 1 and "FW-ALAN" in uyari[0], bildirim
    assert any(m.get("type") == "coil_status" and m["data"].get("alanDogrulanamadi") for m in yayin)


def test_KARSIT_dogrulanmis_alan_YAZILIR_bayrak_iner(api, cekirdek):
    a, _y, _b, kayit, seans = api
    a._handle_backend_event(_Olay(cekirdek._parse_stm_tele(ESKI_TELE)))
    a._handle_backend_event(_Olay(cekirdek._parse_stm_tele(YENI_TELE)))
    coil = a._live_state["coils"][5]
    assert coil["alanDogrulanamadi"] is False and coil["magneticMt"] == pytest.approx(0.050)
    assert "magneticMt" in coil["measuredFields"] and kayit and seans


def test_KRITIK_dogrulanmis_alandan_SONRA_isaretsiz_gelirse_alan_TAZE_SAYILMAZ(api, cekirdek):
    """Kart değişti / ayar kayboldu: önceki doğrulanmış değerin damgası tazelik penceresinde kalıp `measuredFields`'ta
    görünmeye (CoilParameterPanel, KPI, dakika ortalaması) devam ETMEMELİ."""
    a, _y, _b, _k, _s = api
    a._handle_backend_event(_Olay(cekirdek._parse_stm_tele(YENI_TELE)))
    assert "magneticMt" in a._live_state["coils"][5]["measuredFields"]
    a._handle_backend_event(_Olay(cekirdek._parse_stm_tele(ESKI_TELE)))
    coil = a._live_state["coils"][5]
    assert coil["alanDogrulanamadi"] is True and "magneticMt" not in coil["measuredFields"], coil
    assert "magneticMt" not in a._coil_olculen_alanlar[5], a._coil_olculen_alanlar[5]


def test_AI_Pro_achieved_B_SENSORDEN_gelmez_sabit():
    """Tezgâh "AI Pro achieved_B ~5×" dedi; kodda achieved_B sabit 1 mT (sensör ölçeği AI Pro dozunu ETKİLEMEZ)."""
    from servers import ai_pro_hedef, ai_router

    assert ai_router._AI_ACHIEVED_B == 0.001 and ai_pro_hedef.KEDI_ACHIEVED_B == 0.001
