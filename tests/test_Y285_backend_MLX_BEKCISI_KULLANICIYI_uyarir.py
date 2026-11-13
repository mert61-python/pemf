# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y285 (sahip 13 Kasım 2026: "kopsa bile bağlanır; birkaç denemeden sonra bağlanmazsa kullanıcıya bir uyarı gider: manyetik alan sensörü
düştü — sensörü çıkarıp takın ya da kartın gücünü kesip yeniden bağlayın") — BACKEND KISMI (firmware: `test_Y285_firmware_*`).

ÖLÇÜLEN (tezgâh 13-11, iki kez): kart `STM_OK` veriyor, `B=` YOK — arayüz bunu SÖYLEMİYORDU (alan "—", uyarı yok; sahip reset'le buldu).
SÖZLEŞME: bu backend sürecinde `B=` görülmüş bir bobinde `B=` `mlx_bekci.ESIK_S` boyunca gelmezse TEK uyarı (`bildirim.mlxDustu`, iki dilde,
kullanıcıya EYLEM: kabloyu çıkar-tak / kartın gücünü kes); `B=` geri gelince `bildirim.mlxGeriGeldi`. Hiç `B=` görülmemiş hat (I2C1) ve
STM kopukken uyarı YOK. Okuyucu bekçiyi BOŞ okumada da tıklar (port zaman aşımı) — sessiz kart satır üretmese de uyarı çıkar.
GERÇEK: `MlxBekci`, `HeadlessCore._handle_stm_line` / `_set_stm_connected` / `_hw_sender_worker` okuyucusu, `api_server._handle_backend_event`
+ `live_state._bildir` + katalog; sahte yalnız saat, seri port baytları, WS yayını ve bildirim yakalayıcısı.
"""

from __future__ import annotations

import logging
import threading
import time

import pytest
from test_TD1_STM_okuyucu_YARIM_satiri_birlestirir_SGI_3_1 import cekirdek  # noqa: F401  (gerçek okuyucu aparatı)

TELE_B = "-> STM_TELE: C=6,B=0.050,N=344,XN=0.030,XP=0.030,YN=0.000,YP=0.000,ZN=-0.040,ZP=-0.040,GS=0,RS=0"
TELE_ISARETSIZ_B = "-> STM_TELE: C=6,B=1.866,N=284,XN=-0.445,XP=-0.306,YN=1.130,YP=1.262,ZN=-1.359,ZP=-1.139"
TELE_YALNIZ_T = "-> STM_TELE: C=7,T=25.10,A=24.00"


class _Saat:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _bekci(saat, esik=10.0):
    from utils.mlx_bekci import MlxBekci

    return MlxBekci(saat=saat, esik_s=esik)


# ── birim: MlxBekci ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_esik_DOLUNCA_TEK_sefer_bildirir_B_gelince_yeniden_izler():
    s = _Saat()
    b = _bekci(s)
    b.baglandi()
    b.veri(6)
    s.t += 9.9
    assert b.tikla() == []
    s.t += 0.1
    assert b.tikla() == [6]
    s.t += 30
    assert b.tikla() == [], "aynı düşüş İKİNCİ kez bildirildi"
    b.veri(6)
    s.t += 10
    assert b.tikla() == [6], "geri gelip yeniden düşen sensör bildirilmedi"


def test_KARSIT_hic_B_gelmemis_hat_ve_KOPUK_STM_uyari_URETMEZ():
    s = _Saat()
    b = _bekci(s)
    b.baglandi()
    s.t += 100
    assert b.tikla() == [], "sensörü hiç görülmemiş hat uyarı üretti (I2C1 her bağlantıda uyarırdı)"
    b.veri(6)
    b.koptu()
    s.t += 100
    assert b.tikla() == [], "STM kopukken sensör uyarısı üretildi"


def test_KRITIK_yeniden_baglaninca_sure_BAGLANTI_anindan_onceki_karar_SILINIR():
    s = _Saat()
    b = _bekci(s)
    b.baglandi()
    b.veri(6)
    s.t += 10
    assert b.tikla() == [6]
    b.koptu()
    s.t += 500
    b.baglandi()  # kart yeniden açıldı: açılış + ilk pencere payı
    s.t += 9
    assert b.tikla() == [], "yeniden bağlanınca süre bağlantı anından başlamadı (kart açılırken uyarı)"
    s.t += 1
    assert b.tikla() == [6], "yeniden bağlandıktan sonra hâlâ gelmeyen sensör yeniden bildirilmedi"


# ── headless_core: satır → bekçi → olay ─────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def yalin():
    import headless_core as hcm
    from utils.simple_signal import SimpleSignal

    c = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    c.logger = logging.getLogger("test-y285")
    c._stm_state_lock = threading.RLock()
    c.stm_kimlik = None
    c.stm_uyumlu = None
    c.stm_uyumsuzluk_sebebi = ""
    c.stm_is_connected = False
    c.stm_connected_signal = SimpleSignal()
    c.olaylar = []
    c._publish_event = lambda tur, veri=None, **k: c.olaylar.append((tur, veri))
    c.saat = _Saat()
    c._mlx_bekci_durumu = _bekci(c.saat)
    return c


def _kayip(c):
    return [v for t, v in c.olaylar if t == "hardware.stm.telemetry" and v.get("alan_kayip")]


def test_KRITIK_B_satiri_bekciyi_BESLER_esikte_alan_kayip_olayi(yalin):
    c = yalin
    c._set_stm_connected(True)  # GERÇEK geçiş → bekçi bağlandı
    c._handle_stm_line(TELE_B, retry_last_payload=lambda: None)
    c._handle_stm_line(TELE_YALNIZ_T, retry_last_payload=lambda: None)  # bobin 7 sıcaklık: alan değil
    c.saat.t += 10
    c._mlx_bekci_tikla()
    assert _kayip(c) == [{"coil_id": 6, "alan_kayip": True}], c.olaylar
    c._mlx_bekci_tikla()
    assert len(_kayip(c)) == 1, "aynı düşüş iki olay üretti"


def test_KRITIK_isaretsiz_B_de_sensorun_YASADIGINI_gosterir(yalin):
    c = yalin
    c._set_stm_connected(True)
    c._handle_stm_line(TELE_B, retry_last_payload=lambda: None)
    c.saat.t += 9
    c._handle_stm_line(
        TELE_ISARETSIZ_B, retry_last_payload=lambda: None
    )  # eski firmware / doğrulanmamış ayar: sensör VAR
    c.saat.t += 9
    c._mlx_bekci_tikla()
    assert not _kayip(c), "doğrulanmamış B= gelirken 'sensör düştü' denildi"


def test_KRITIK_STM_KOPUNCA_sayac_durur(yalin):
    c = yalin
    c._set_stm_connected(True)
    c._handle_stm_line(TELE_B, retry_last_payload=lambda: None)
    c._set_stm_connected(False)  # GERÇEK geçiş → bekçi koptu
    c.saat.t += 60
    c._mlx_bekci_tikla()
    assert not _kayip(c), "STM kopukken alan sensörü uyarısı (asıl sorun bağlantı)"


# ── okuyucu: boş okumada da tıklar ──────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_okuyucu_SESSIZ_kartta_da_bekciyi_tiklar(cekirdek):  # noqa: F811
    from utils.mlx_bekci import MlxBekci

    core, kart = cekirdek
    core._mlx_bekci_durumu = MlxBekci(esik_s=0.5)
    core._mlx_bekci_durumu.baglandi()  # aparat `_set_stm_connected`ı yakalar
    kart.q.put((TELE_B + "\r\n").encode())
    bitis = time.monotonic() + 5.0
    while time.monotonic() < bitis and not any(v and v.get("alan_kayip") for _t, v in core.olaylar):
        time.sleep(0.05)
    assert [v for _t, v in core.olaylar if v and v.get("alan_kayip")] == [{"coil_id": 6, "alan_kayip": True}], (
        "kart B= satırından sonra sustu; okuyucu bekçiyi tıklamadı (uyarı hiç çıkmazdı)"
    )


# ── api_server: olay → bayrak + iki dilli bildirim ──────────────────────────────────────────────────────────────────────────
@pytest.fixture
def api(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin, bildirim = [], []
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(
        ls, "_push_notification", lambda m, s="info": bildirim.append((m, s, dict(ls._BILDIRIM_MESAJLARI.get() or {})))
    )
    monkeypatch.setattr(
        a, "_push_notification", lambda m, s="info": bildirim.append((m, s, dict(ls._BILDIRIM_MESAJLARI.get() or {})))
    )
    monkeypatch.setattr(a._sensor_kaydedici, "kaydet_arka_planda", lambda *x, **k: None)
    monkeypatch.setattr(a._seans_alan, "olcum", lambda *x, **k: None)
    with a._live_state_lock:
        coil = a._live_state["coils"][5]
        monkeypatch.setitem(coil, "magneticMt", 0.0)
        monkeypatch.setitem(coil, "measuredFields", [])
        monkeypatch.setitem(coil, "alanDogrulanamadi", False)
        monkeypatch.setitem(coil, "alanKayip", False)
    monkeypatch.setitem(a._coil_olculen_alanlar, 5, {})
    return a, yayin, bildirim


class _Olay:
    def __init__(self, data):
        self.event_type = "hardware.stm.telemetry"
        self.data = data


def test_KRITIK_dusunce_KULLANICIYA_eylem_soyleyen_IKI_DILLI_uyari_TEK_sefer(api, yalin):
    a, yayin, bildirim = api
    a._handle_backend_event(_Olay({"coil_id": 6, "alan_kayip": True}))
    a._handle_backend_event(_Olay({"coil_id": 6, "alan_kayip": True}))
    assert a._live_state["coils"][5]["alanKayip"] is True
    uyari = [(m, s, ms) for m, s, ms in bildirim if "manyetik alan sensörü veri göndermiyor" in m]
    assert len(uyari) == 1 and uyari[0][1] == "warning", bildirim
    m, _s, ms = uyari[0]
    assert m.startswith("⚠️ Bobin 6 ") and "kablosunu çıkarıp yeniden takın" in m and "kartın gücünü kesip" in m, m
    assert "unplug and reconnect the sensor cable" in ms.get("en", "") and "power the board off" in ms["en"], ms
    assert any(x.get("type") == "coil_status" and x["data"].get("alanKayip") for x in yayin), yayin


def test_KRITIK_B_GELINCE_bayrak_iner_YENIDEN_BAGLANDI_bildirilir(api, yalin):
    a, _yayin, bildirim = api
    a._handle_backend_event(_Olay({"coil_id": 6, "alan_kayip": True}))
    a._handle_backend_event(_Olay(yalin._parse_stm_tele(TELE_B)))
    assert a._live_state["coils"][5]["alanKayip"] is False
    geri = [(m, s) for m, s, _ms in bildirim if "yeniden bağlandı" in m]
    assert geri == [("Bobin 6 manyetik alan sensörü yeniden bağlandı — alan ölçümü sürüyor.", "info")], bildirim
    a._handle_backend_event(_Olay(yalin._parse_stm_tele(TELE_B)))
    assert len([m for m, _s, _ms in bildirim if "yeniden bağlandı" in m]) == 1, (
        "her B= satırında 'yeniden bağlandı' dendi"
    )


def test_KARSIT_hic_dusmemis_sensorde_B_satiri_BILDIRIM_uretmez(api, yalin):
    a, _yayin, bildirim = api
    a._handle_backend_event(_Olay(yalin._parse_stm_tele(TELE_B)))
    assert not [m for m, _s, _ms in bildirim if "manyetik alan sensörü" in m], bildirim
