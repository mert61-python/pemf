# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.E04 · İG-6.7 — teyitsiz ACİL DURDUR'dan sonra "durdu" ile "teyit edildi" AYRI: backend teyit durumunu ayrı bir
alanla yayınlar (`estop_teyit` iletisi + anlık görüntüde `estopTeyit`); teyit yalnız teyitli bir E-stop ya da kartın
GERÇEK tüm-sıfır ACK'i ile gelir.

ÖLÇÜLEN KUSUR (aday doğrulaması İG-6.7, gerçek backend + STOP'a yanıt vermeyen sahte STM + gerçek web): teyitsiz E-stop'tan
sonra backend teyitten BAĞIMSIZ `coil_status running:false` yayınlıyor (`_emergency_stop_all` canlı durumu koşulsuz
sıfırlar) ve istemci bunu "durdu" kanıtı sayıyordu: kayan ACİL DURDUR KALKIYOR, Ana Ekran "Sistem Hazır" diyordu — STM 16
tüm-sıfır paketin 9'unu yanıtsız bırakmışken. Backend'de teyit durumu hiç yayınlanmıyordu (yalnız tek seferlik HTTP yanıtı).

Kapı: GERÇEK `_emergency_stop_all` (teyitsiz: STM STOP kuyruğa verilemedi) + GERÇEK `HeadlessCore._handle_stm_line` (kartın
ACK'i firmware aynasından) → GERÇEK olay veriyolu + api işleyicileri. Arayüz fikstürü
`apps/ui/src/components/ui/__tests__/__fixtures__/teyitsizAcilDurdur.ws.json` buradan üretilir (bayatlık kapısı).
Ö.4-Y8: hiçbir iddia STOP'u kapılamaz; teyitsizlik yalnız GÖRÜNÜRLÜĞÜ artırır.
"""

from __future__ import annotations

import copy
import json
import logging
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from topoloji import TUM_STM

_KOK = Path(__file__).resolve().parents[1]
_FIKSTUR = (
    _KOK / "apps" / "ui" / "src" / "components" / "ui" / "__tests__" / "__fixtures__" / "teyitsizAcilDurdur.ws.json"
)


def _ack(dutyler) -> str:
    n = len(TUM_STM)
    d = ",".join(str(int(x)) for x in dutyler)
    sifir = ",".join("0" for _ in range(n))
    f = ",".join(("100" if x else "0") for x in dutyler)
    t = ",".join(("5" if x else "0") for x in dutyler)
    return f"-> STM_OK: D={d} P={sifir} F={f} T={t}"


@pytest.fixture
def ortam(monkeypatch):
    import event_bus as eb
    import headless_core as hcm
    from servers import api_server as api
    from servers import live_state as ls
    from utils.simple_signal import SimpleSignal

    yayinlar: list = []
    kaydet = lambda m, *a, **k: yayinlar.append(copy.deepcopy(m))  # noqa: E731
    monkeypatch.setattr(ls, "_ws_broadcast_sync", kaydet)
    monkeypatch.setattr(api, "_ws_broadcast_sync", kaydet)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    monkeypatch.setattr(api, "_event_bus_registered", False)
    with api._session_lock:
        api._active_session.clear()
    with ls._live_state_lock:
        eski = {k: copy.deepcopy(ls._live_state.get(k)) for k in ("stm", "coils", "activeTreatment", "estopTeyit")}
        for _c in ls._live_state["coils"].values():
            _c.update({"connected": True, "running": False})
        ls._live_state["stm"] = "online"
        ls._live_state["activeTreatment"].update({"isActive": False, "mode": "Sistem Hazır"})
        ls._live_state["estopTeyit"] = None

    class _HC:
        stop_sonucu = False  # teyitsiz: STOP kuyruğa verilemedi (ölü gönderici / kablo)
        coils_state = {b: {"is_running": False} for b in TUM_STM}

        def stop_all_coils(self):
            return self.stop_sonucu

        def update_coil(self, *a, **k):
            return True

        def on_disconnect(self):
            return True

    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-e04")
    core.event_bus = yeni_bus
    core._stm_state_lock = threading.RLock()
    core.stm_is_connected = True
    core.stm_kimlik = None
    core.stm_uyumlu = None
    core.stm_uyumsuzluk_sebebi = ""
    core.stm_connected_signal = SimpleSignal()
    core.stm_connected_signal.connect(core._on_stm_connected_slot)
    hc = _HC()
    monkeypatch.setattr(api.state, "hardware", hc)
    monkeypatch.setattr(api.state, "core", core)
    try:
        api._register_event_bus_handlers()
        yield SimpleNamespace(api=api, ls=ls, core=core, hc=hc, yayinlar=yayinlar)
    finally:
        yeni_bus.shutdown()
        with ls._live_state_lock:
            for k, v in eski.items():
                ls._live_state[k] = v


def _teyit_iletileri(o):
    return [m["data"] for m in o.yayinlar if m.get("type") == "estop_teyit"]


def test_KRITIK_teyitsiz_estop_TEYIT_DURUMU_ayri_yayinlanir_ve_anlik_goruntude_durur(ortam):
    o = ortam
    sonuc = o.api._emergency_stop_all("manual")
    assert sonuc["confirmed"] is False, "aparat: E-stop teyitsiz olmali"
    teyit = _teyit_iletileri(o)
    assert teyit and teyit[-1]["teyitli"] is False, f"teyitsiz E-stop'un teyit durumu yayinlanmadi: {o.yayinlar[-4:]}"
    tipler = [m.get("type") for m in o.yayinlar]
    assert tipler.index("estop_teyit") > tipler.index("emergency_stop"), "teyit, durdurma iletisinden ONCE yayinlandi"
    assert o.api._build_ws_snapshot().get("estopTeyit", {}).get("teyitli") is False, "anlik goruntude teyit yok"


def test_KRITIK_kartin_GERCEK_tum_sifir_ACKi_teyitsizligi_kaldirir(ortam):
    o = ortam
    o.api._emergency_stop_all("manual")
    o.core._handle_stm_line(_ack([0] * len(TUM_STM)), None)
    assert o.api._build_ws_snapshot()["estopTeyit"]["teyitli"] is True, "kartin tum-sifir ACK'i teyit vermedi"
    assert _teyit_iletileri(o)[-1] == {**_teyit_iletileri(o)[-1], "teyitli": True, "kaynak": "stm_ack"}


def test_KARSIT_calisan_bobinli_ACK_ya_da_ESP_ACIKken_STM_ACKi_teyit_VERMEZ(ortam, monkeypatch):
    o = ortam
    o.api._emergency_stop_all("manual")
    o.core._handle_stm_line(_ack([40] + [0] * (len(TUM_STM) - 1)), None)
    assert o.api._build_ws_snapshot()["estopTeyit"]["teyitli"] is False, "calisan bobinli ACK teyit sayildi"
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    o.core._handle_stm_line(_ack([0] * len(TUM_STM)), None)
    assert o.api._build_ws_snapshot()["estopTeyit"]["teyitli"] is False, "ESP acikken STM ACK'i ESP'yi de teyit etti"


def test_KARSIT_teyitli_estop_teyitli_yayinlanir(ortam):
    o = ortam
    o.hc.stop_sonucu = True
    sonuc = o.api._emergency_stop_all("manual")
    assert sonuc["confirmed"] is True, (
        "aparat: ESP kapali + STM STOP kuyrukta (yazim izi bildirmeyen HC) teyitli olmali"
    )
    assert _teyit_iletileri(o)[-1]["teyitli"] is True


# ── Arayüz fikstürü ─────────────────────────────────────────────────────────────────────────────────────────────────
def ws_dizisi_uret(o) -> list[dict]:
    """Teyitsiz E-stop'un istemciye giden iletileri (istemcinin okuduğu alanlar)."""
    o.yayinlar.clear()
    o.api._emergency_stop_all("manual")
    dizi = []
    for m in o.yayinlar:
        tip = m.get("type")
        if tip == "coil_status":
            dizi.append({"type": tip, "coilId": m["coilId"], "data": {"running": m["data"]["running"]}})
        elif tip == "emergency_stop":
            dizi.append({"type": tip, "data": {"reason": m["data"]["reason"]}})
        elif tip == "estop_teyit":
            dizi.append({"type": tip, "data": {"teyitli": m["data"]["teyitli"], "kaynak": m["data"]["kaynak"]}})
        elif tip == "session_update":
            dizi.append({"type": tip, "data": {"isActive": m["data"]["isActive"], "mode": m["data"]["mode"]}})
    return dizi


def test_arayuz_fiksturu_GERCEK_backend_dizisiyle_AYNI(ortam):
    beklenen = ws_dizisi_uret(ortam)
    assert _FIKSTUR.is_file(), f"arayuz fiksturu yok: {_FIKSTUR}"
    assert json.loads(_FIKSTUR.read_text(encoding="utf-8")) == beklenen, (
        "fikstur backend'in GERCEK dizisinden BAYATLADI"
    )
    assert beklenen[-1]["type"] == "estop_teyit" and beklenen[-1]["data"]["teyitli"] is False
