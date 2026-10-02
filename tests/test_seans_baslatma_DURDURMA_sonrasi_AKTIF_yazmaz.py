# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-C bağımsız inceleme i2-F3 — seans başlatma, sürüş SIRASINDA gelen durdurmadan sonra "AKTİF" yazmaz.

ÖLÇÜLEN KUSUR (c5b3c04 sonrası, i2 30/30 × 2 kol × 2 koşu): `/api/session/start`ın STM sürüşü (to_thread) bobin 1'i
kabul ettikten SONRA, bobin 2'den ÖNCE operatör durdurur (seans durdurma ya da E-stop + Sıfırla). Bobin 2 nesille DOĞRU
reddediliyordu ama `_stm_kabul=[1]` boş olmadığı için akış canlı durumu "AKTİF" yazıyor (yazım `surus_nesli`
taşımıyordu), seans alan kaydını (CSV) durdurmadan SONRA AÇIYOR ve "success" dönüyordu — seans da bobin de yokken.
Operatörün sonraki "Durdur"u seanssız dala gidip canlı durumu hiç yazmadığı için gösterge takılı, CSV açık kalıyordu.

KAPI: `HardwareController.update_coil` sarılır; bobin 1 START'ı döndükten sonra sürüş iş parçacığı Event'te tutulur
(gerçekte: to_thread iş parçacığının GIL/zamanlayıcıda bekletilmesi). 2 kol × 30 deneme. KARŞIT: yalnız E-stop'ta
(mandal kurulu) canlı durum "Acil Durdurma" kalır.
"""

from __future__ import annotations

import threading

import ai_pro_aparati as ap
import pytest

DENEME = 30


class _KayitciAlan:
    def __init__(self):
        self.olaylar: list = []

    def seans_basladi(self, *a, **k):
        self.olaylar.append("basladi")
        return None

    def seans_bitti(self, *a, **k):
        self.olaylar.append("bitti")
        return None


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    ns.alan = _KayitciAlan()
    monkeypatch.setattr(ns.api, "_seans_alan", ns.alan)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _tur(o, monkeypatch, durdurma: str) -> dict:
    ap.mandali_sifirla(o.c)
    o.c.post("/api/session/stop")
    o.hc.stop_all_coils()
    ap.mandali_sifirla(o.c)
    gecti, devam = threading.Event(), threading.Event()
    orj = o.hc.update_coil

    def _sarili(cid, *a, **kw):
        sonuc = orj(cid, *a, **kw)
        if (
            cid == 1
            and kw.get("start", True)
            and threading.current_thread().name != "MainThread"
            and not gecti.is_set()
        ):
            gecti.set()
            assert devam.wait(10), "aparat: engel kalkmadı"
        return sonuc

    monkeypatch.setattr(o.hc, "update_coil", _sarili)
    kutu: dict = {}

    def _calis():
        kutu["yanit"] = o.c.post(
            "/api/session/start",
            json={
                "coil_ids": [1, 2],
                "frequency": 50,
                "duty": 10,
                "phase": 0,
                "duration_minutes": 5,
                "mode": "Manuel-R1",
            },
        )

    t = threading.Thread(target=_calis, name="test-R1", daemon=True)
    t.start()
    assert gecti.wait(10), "aparat: R1 bobin 1 sürüşüne ulaşmadı"
    n_alan = len(o.alan.olaylar)
    if durdurma == "session_stop":
        assert o.c.post("/api/session/stop").status_code == 200
    elif durdurma == "estop_sifirla":
        o.api._emergency_stop_all("manual")
        ap.mandali_sifirla(o.c)
    else:  # yalnız E-stop (KARŞIT)
        o.api._emergency_stop_all("manual")
    devam.set()
    t.join(15)
    assert not t.is_alive(), "aparat: R1 bitmedi"
    monkeypatch.setattr(o.hc, "update_coil", orj)
    with o.api._session_lock:
        seans_aktif = bool(o.api._active_session.get("is_active"))
    with o.ls._live_state_lock:
        canli = dict(o.ls._live_state["activeTreatment"])
    sonuc = {
        "r1_status": (kutu["yanit"].json() or {}).get("status"),
        "r1_http": kutu["yanit"].status_code,
        "seans_aktif": seans_aktif,
        "calisan": ap.calisan(o),
        "canli_aktif": bool(canli.get("isActive")),
        "canli_mod": canli.get("mode"),
    }
    o.c.post("/api/session/stop")  # operatörün sonraki "Durdur"u
    with o.ls._live_state_lock:
        sonuc["durdurdan_sonra_canli_aktif"] = bool(o.ls._live_state["activeTreatment"].get("isActive"))
    ol = o.alan.olaylar[n_alan:]
    sonuc["csv_acik"] = bool(ol) and ol[-1] == "basladi"
    return sonuc


@pytest.mark.parametrize("durdurma", ["session_stop", "estop_sifirla"])
def test_KRITIK_durdurma_SONRASI_seans_baslatma_AKTIF_yazmaz_N30(o, monkeypatch, durdurma):
    say = dict(canli_aktif_seans_yok=0, success_yalani=0, csv_acik=0, durdur_sonrasi_takili=0, bobin_calisiyor=0)
    ornek = None
    for _ in range(DENEME):
        s = _tur(o, monkeypatch, durdurma)
        bu = {
            "canli_aktif_seans_yok": s["canli_aktif"] and not s["seans_aktif"],
            "success_yalani": s["r1_status"] == "success" and not s["seans_aktif"],
            "csv_acik": s["csv_acik"],
            "durdur_sonrasi_takili": s["durdurdan_sonra_canli_aktif"],
            "bobin_calisiyor": bool(s["calisan"]),
        }
        for k, v in bu.items():
            say[k] += bool(v)
        if any(bu.values()) and ornek is None:
            ornek = s
    assert all(v == 0 for v in say.values()), f"{durdurma}: {DENEME} denemede: {say} — örnek {ornek}"


def test_KARSIT_yalniz_ESTOP_mandal_kuruluyken_AKTIF_yazilmaz(o, monkeypatch):
    for _ in range(5):
        s = _tur(o, monkeypatch, "estop")
        assert not s["canli_aktif"] and s["canli_mod"] == "Acil Durdurma", s


def test_KRITIK_denetim_ile_AKTIF_yazimi_ARASINDA_durdurma_CSV_ve_success_URETMEZ_N30(o, monkeypatch):
    """Sürüş sonrası denetim geçtikten sonra, "aktif" yazımından HEMEN ÖNCE gelen durdurma: yazım kilit altında
    reddedilir (nesil) ve başlatma bunu görür — CSV açılmaz, "success" denmez, canlı durum aktif kalmaz."""
    say = dict(canli_aktif=0, success=0, csv_acik=0)
    ornek = None
    orj = o.api.update_live_session_state
    for _ in range(DENEME):
        ap.mandali_sifirla(o.c)
        o.c.post("/api/session/stop")
        o.hc.stop_all_coils()
        geldi, devam = threading.Event(), threading.Event()

        def _bekleyen(*a, **k):
            if k.get("is_active") and k.get("mode") == "Manuel-R1" and not geldi.is_set():
                geldi.set()
                assert devam.wait(10), "aparat: yazım engeli kalkmadı"
            return orj(*a, **k)

        monkeypatch.setattr(o.api, "update_live_session_state", _bekleyen)
        n_alan = len(o.alan.olaylar)
        kutu: dict = {}
        t = threading.Thread(
            target=lambda: kutu.update(
                r=o.c.post(
                    "/api/session/start",
                    json={
                        "coil_ids": [1],
                        "frequency": 50,
                        "duty": 10,
                        "phase": 0,
                        "duration_minutes": 5,
                        "mode": "Manuel-R1",
                    },
                )
            ),
            daemon=True,
        )
        t.start()
        assert geldi.wait(10), "aparat: başlatma 'aktif' yazımına ulaşmadı"
        assert o.c.post("/api/session/stop").status_code == 200  # durdurma, denetimden SONRA, yazımdan ÖNCE
        devam.set()
        t.join(15)
        assert not t.is_alive(), "aparat: başlatma bitmedi"
        monkeypatch.setattr(o.api, "update_live_session_state", orj)
        with o.ls._live_state_lock:
            canli_aktif = bool(o.ls._live_state["activeTreatment"].get("isActive"))
        ol = o.alan.olaylar[n_alan:]
        bu = {
            "canli_aktif": canli_aktif,
            "success": (kutu["r"].json() or {}).get("status") == "success",
            "csv_acik": bool(ol) and ol[-1] == "basladi",
        }
        for k, v in bu.items():
            say[k] += bool(v)
        if any(bu.values()) and ornek is None:
            ornek = (kutu["r"].status_code, kutu["r"].text[:120], ol)
    assert all(v == 0 for v in say.values()), f"{DENEME} denemede: {say} — örnek {ornek}"


def _bloklu_baslat(o, monkeypatch):
    """Bobin 1 START'ı döndükten sonra sürüş iş parçacığını tutan başlatma; (iş parçacığı, kutu, devam, orj)."""
    gecti, devam = threading.Event(), threading.Event()
    orj = o.hc.update_coil

    def _sarili(cid, *a, **kw):
        sonuc = orj(cid, *a, **kw)
        if (
            cid == 1
            and kw.get("start", True)
            and threading.current_thread().name != "MainThread"
            and not gecti.is_set()
        ):
            gecti.set()
            assert devam.wait(10), "aparat: engel kalkmadı"
        return sonuc

    monkeypatch.setattr(o.hc, "update_coil", _sarili)
    kutu: dict = {}
    t = threading.Thread(
        target=lambda: kutu.update(
            r=o.c.post(
                "/api/session/start",
                json={
                    "coil_ids": [1, 2],
                    "frequency": 50,
                    "duty": 10,
                    "phase": 0,
                    "duration_minutes": 5,
                    "mode": "Manuel-R1",
                },
            )
        ),
        name="test-R1",
        daemon=True,
    )
    t.start()
    assert gecti.wait(10), "aparat: R1 bobin 1 sürüşüne ulaşmadı"
    return t, kutu, devam, orj


def test_KRITIK_surus_SIRASINDA_seansi_AI_Pro_devralirsa_baslatma_SUCCESS_ve_CSV_uretmez_N30(o, monkeypatch):
    """Kimlik ön-denetimi: nesli BOZMAYAN bir devralma (onaylı AI Pro seansı `start_ai_session` ile oturumu alır)
    sürüş sırasında olursa başlatma "aktif" yazmaz, CSV açmaz, "success" demez (seans artık onun değil)."""
    say = dict(success=0, csv_acik=0, canli_manuel=0)
    ornek = None
    for _ in range(DENEME):
        ap.mandali_sifirla(o.c)
        o.c.post("/api/ai/pro/stop")
        o.c.post("/api/session/stop")
        o.hc.stop_all_coils()
        n_alan = len(o.alan.olaylar)
        t, kutu, devam, orj = _bloklu_baslat(o, monkeypatch)
        _pid, ra = ap.onayli_baslat(o)  # başka bir operatör onaylı AI Pro başlatır (oturumu devralır)
        assert ra.status_code == 200 and ra.json().get("status") == "success", (
            f"aparat: AI Pro açılmadı {ra.text[:200]}"
        )
        devam.set()
        t.join(15)
        assert not t.is_alive(), "aparat: R1 bitmedi"
        monkeypatch.setattr(o.hc, "update_coil", orj)
        with o.ls._live_state_lock:
            canli = dict(o.ls._live_state["activeTreatment"])
        ol = o.alan.olaylar[n_alan:]
        bu = {
            "success": (kutu["r"].json() or {}).get("status") == "success",
            "csv_acik": bool(ol) and ol[-1] == "basladi",
            "canli_manuel": bool(canli.get("isActive")) and canli.get("mode") == "Manuel-R1",
        }
        for k, v in bu.items():
            say[k] += bool(v)
        if any(bu.values()) and ornek is None:
            ornek = (kutu["r"].status_code, kutu["r"].text[:120], ol, canli.get("mode"))
    o.c.post("/api/ai/pro/stop")
    assert all(v == 0 for v in say.values()), f"{DENEME} denemede: {say} — örnek {ornek}"


def test_KRITIK_surus_SIRASINDA_seansi_bitirmeyen_stop_all_KENDI_seansi_KAPATILIR_N30(o, monkeypatch):
    """Seansı BİTİRMEYEN durdurma (legacy `stop_all_coils`: nesil++ + tüm STOP) sürüş sırasında gelirse bobinler durur;
    başlatma kendi seansını aktif BIRAKMAZ (süre bekçisi ve ekran "sürüyor" demesin), "success" demez."""
    say = dict(seans_aktif=0, success=0, canli_aktif=0, csv_acik=0)
    ornek = None
    for _ in range(DENEME):
        ap.mandali_sifirla(o.c)
        o.c.post("/api/session/stop")
        o.hc.stop_all_coils()
        n_alan = len(o.alan.olaylar)
        t, kutu, devam, orj = _bloklu_baslat(o, monkeypatch)
        r = o.c.post("/api/hardware/command", json={"command": "stop_all_coils", "params": {}})
        assert r.status_code == 200, r.text[:200]
        devam.set()
        t.join(15)
        assert not t.is_alive(), "aparat: R1 bitmedi"
        monkeypatch.setattr(o.hc, "update_coil", orj)
        with o.api._session_lock:
            seans_aktif = bool(o.api._active_session.get("is_active"))
        with o.ls._live_state_lock:
            canli_aktif = bool(o.ls._live_state["activeTreatment"].get("isActive"))
        ol = o.alan.olaylar[n_alan:]
        bu = {
            "seans_aktif": seans_aktif,
            "success": (kutu["r"].json() or {}).get("status") == "success",
            "canli_aktif": canli_aktif,
            "csv_acik": bool(ol) and ol[-1] == "basladi",
        }
        for k, v in bu.items():
            say[k] += bool(v)
        if any(bu.values()) and ornek is None:
            ornek = (kutu["r"].status_code, kutu["r"].text[:120], ol, ap.calisan(o))
    assert all(v == 0 for v in say.values()), f"{DENEME} denemede: {say} — örnek {ornek}"


def test_KRITIK_seanssiz_DURDUR_bayat_AKTIF_gostergeyi_ve_CSVyi_KAPATIR(o):
    """Seans yokken canlı durum (herhangi bir bayat yazımla) "aktif" kalmışsa operatörün Durdur'u onu temizler."""
    ap.mandali_sifirla(o.c)
    o.c.post("/api/session/stop")
    with o.api._session_lock:
        assert not o.api._active_session.get("is_active"), "aparat: seans aktif"
    o.ls.update_live_session_state(is_active=True, mode="Bayat-yazim", freq=50)
    o.alan.seans_basladi("bayat", {})
    n_alan = len(o.alan.olaylar)
    r = o.c.post("/api/session/stop")
    assert r.status_code == 200, r.text[:200]
    with o.ls._live_state_lock:
        canli = dict(o.ls._live_state["activeTreatment"])
    assert not canli.get("isActive"), f"seanssız Durdur bayat 'aktif' göstergeyi temizlemedi: {canli.get('mode')}"
    assert o.alan.olaylar[n_alan:] == ["bitti"], f"seanssız Durdur açık CSV'yi kapatmadı: {o.alan.olaylar[n_alan:]}"
