# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.84 incelemesi (İNCELEME-2 i1-F-1 · B-5.2 · Y25) — `perCoil` "sürüldü" kümesi, sürüş komutu VERİLMEYEN karede/turda da
TELDE çalışan kümeye eşittir; enerjili bobin "sürülmedi" gösterilmez.

ÖLÇÜLEN KUSUR (`60567e4`, GERÇEK HC + kayıtçı kuyruk): D1.84 `suruldu`yu yalnız O karede `update_coil`'in kabul ettiği
bobinlerden kuruyordu. Sürüş komutu verilmeyen üç durumda bobinler önceki komutla keep-alive'da ÇALIŞIRKEN yanıt/WS
7 bobini "sürülmedi" (duty 0) diyordu:
  (a) `/frame` hedef-kaybı karesi, seri N=3'ten küçük (kayıp STOP'u henüz gelmedi) — telde 7 çalışan, yanıt 7 "sürülmedi";
  (b) yabancı izleyicinin karesi (sahibin seansı sürerken) — tüm seans boyunca 7 "sürülmedi";
  (c) GERÇEK döngünün kayıp turu (WS `ai_vision.perCoil`) — telde 7 çalışan, WS 7 "sürülmedi".
Y25: "ekran 6-7 için gerçeği göstermelidir (sürülmediyse 'sürülmedi')" — enerjili bobini "sürülmedi" göstermek de
gerçeği göstermemektir (operatör bobini kapalı sanar).

DÜZELTME: AI Pro seansı (mühür) varken sürüş komutu verilmeyen bobin telde çalışıyorsa satırı TELDEKİ değerle
(`HardwareController.calisan_bobin_durumu`) ve `suruldu: True` ile döner. Seans yokken (hazırlık) davranış aynı.
Yeni durdurma/engelleme/kıskaç YOK (A-47, Ö.4-Y8, Ö.4-Y9) — yalnız gösterim.
"""

from __future__ import annotations

import ai_pro_aparati as ap
import numpy as np
import pytest

D7 = [0.30, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36]
P7 = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
_KAYIP = (False, 0.0, 0.0, 0.0, 0.0, None, True)


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_predict_and_drive", lambda *a, **k: (list(D7), list(P7), 0.5))
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.c.post("/api/ai/pro/stop")
        if ns.hc is not None:
            ns.hc.stop_all_coils()
        ns.geri()


def _suruldu(pc) -> set:
    return {c["id"] for c in pc or [] if c.get("suruldu") is True}


def _duty(pc) -> dict:
    return {c["id"]: c["duty"] for c in pc or []}


def _ilk_kare_surer(o, istemci=""):
    _pid, r = ap.onayli_baslat(o, organ=2, istemci=istemci)
    assert r.status_code == 200, r.text[:200]
    j = ap.kare(o, istemci).json()
    assert j.get("driven") is True and sorted(ap.calisan(o)) == list(range(1, 8)), (j.get("driven"), ap.calisan(o))
    return j


def test_KRITIK_frame_KAYIP_karesi_seri_N_den_KUCUK_enerjili_bobin_SURULDU_ve_TELDEKI_duty(o, monkeypatch):
    j0 = _ilk_kare_surer(o)
    monkeypatch.setattr(o.air, "_localize_organ", lambda f, oid: _KAYIP)
    monkeypatch.setattr(o.air, "_ai_relocalize", True)
    j = ap.kare(o).json()
    assert j.get("driven") is not True and j.get("detected") is False, (j.get("driven"), j.get("detected"))
    calisan = set(ap.calisan(o))
    assert calisan == set(range(1, 8)), f"aparat: kayıp STOP'u erken geldi (çalışan {sorted(calisan)})"
    assert _suruldu(j["perCoil"]) == calisan, (
        f"telde ÇALIŞAN {sorted(calisan)} — yanıt 'sürüldü' {sorted(_suruldu(j['perCoil']))} (duty {_duty(j['perCoil'])})"
    )
    assert _duty(j["perCoil"]) == _duty(j0["perCoil"]), (
        f"enerjili bobinin duty'si TELDEKİ değer değil: {_duty(j['perCoil'])} ≠ son sürüş {_duty(j0['perCoil'])}"
    )


def test_KRITIK_YABANCI_izleyici_karesi_enerjili_bobini_SURULDU_gosterir(o):
    j0 = _ilk_kare_surer(o, "sahip-y25")
    j = ap.kare(o, "yabanci-y25").json()
    assert j.get("foreignViewer") is True and j.get("driven") is not True, (j.get("foreignViewer"), j.get("driven"))
    calisan = set(ap.calisan(o))
    assert calisan == set(range(1, 8))
    assert _suruldu(j["perCoil"]) == calisan and _duty(j["perCoil"]) == _duty(j0["perCoil"]), (
        f"yabancı izleyici: telde ÇALIŞAN {sorted(calisan)}, 'sürüldü' {sorted(_suruldu(j['perCoil']))}, "
        f"duty {_duty(j['perCoil'])}"
    )


def test_KARSIT_kayip_STOPU_sonrasi_SURULMEDI_ve_seans_YOKKEN_elle_surulen_bobin_AI_Pro_tablosunda_SURULDU_degil(
    o, monkeypatch
):
    _ilk_kare_surer(o)
    monkeypatch.setattr(o.air, "_localize_organ", lambda f, oid: _KAYIP)
    for _ in range(3):  # N=3. kayıp karesinde STOP
        monkeypatch.setattr(o.air, "_ai_relocalize", True)
        j = ap.kare(o).json()
    assert ap.calisan(o) == [] and _suruldu(j["perCoil"]) == set(), (ap.calisan(o), _suruldu(j["perCoil"]))
    # Seans yokken (hazırlık karesi) telde başka yoldan çalışan bobin AI Pro'nun "sürüldü"sü sayılmaz.
    from utils import estop_mandali

    o.c.post("/api/ai/pro/stop")
    ap.mandali_sifirla(o.c)
    assert o.hc.update_coil(3, 10.0, 25.0, 0.0, 5, start=True, nesil=estop_mandali.nesil())
    assert 3 in ap.calisan(o)
    j = ap.kare(o).json()
    assert _suruldu(j["perCoil"]) == set(), f"seans yokken AI Pro tablosu 'sürüldü' dedi: {_suruldu(j['perCoil'])}"


def test_KRITIK_DONGU_KAYIP_turu_WS_perCoil_enerjili_bobini_SURULDU_gosterir(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(ns.air, "_predict_and_drive", lambda *a, **k: (list(D7), list(P7), 0.5))
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)  # em_kedi ağırlığı depoda yok
    durum = {"bul": True}
    monkeypatch.setattr(
        ns.air, "_localize_organ", lambda f, oid: (True, 10.0, 20.0, 30.0, 0.9, None, True) if durum["bul"] else _KAYIP
    )

    class _Kamera:
        def __init__(self, *a, **k):
            pass

        def isOpened(self):  # noqa: N802
            return True

        def read(self):
            return True, np.zeros((8, 8, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _Kamera)
    kayit: list = []
    hc_ctx = gercek_hc()
    ns.hc = hc_ctx.__enter__()
    monkeypatch.setattr(ns.api.state, "hardware", ns.hc)

    def _ws(msg):
        if isinstance(msg, dict) and msg.get("type") == "ai_vision":
            kayit.append((msg["data"].get("perCoil"), set(ap.calisan(ns)), durum["bul"]))

    monkeypatch.setattr(ns.api, "_ws_broadcast_sync", _ws)
    try:
        _pid, r = ap.onayli_baslat(ns, organ=2)
        assert r.status_code == 200, r.text[:200]
        assert ap.bekle(lambda: any(_suruldu(pc) == set(range(1, 8)) for pc, _c, _b in kayit), 6), kayit[-2:]
        durum["bul"] = False
        ns.air._ai_relocalize = True
        assert ap.bekle(lambda: any(not b for _pc, _c, b in kayit), 6), "aparat: kayıp turu yayınlanmadı"
        ilk_pc, ilk_calisan = next((pc, c) for pc, c, b in kayit if not b)
        assert ilk_calisan == set(range(1, 8)), f"aparat: ilk kayıp turunda çalışan {sorted(ilk_calisan)}"
        assert _suruldu(ilk_pc) == ilk_calisan, (
            f"döngü kayıp turu: telde ÇALIŞAN {sorted(ilk_calisan)}, WS 'sürüldü' {sorted(_suruldu(ilk_pc))}, "
            f"duty {_duty(ilk_pc)}"
        )
        assert all(_duty(ilk_pc)[i] > 0 for i in range(1, 8)), f"teldeki duty gösterilmedi: {_duty(ilk_pc)}"
    finally:
        ns.air._ai_loop_active = False
        ap.bekle(lambda: False, 1.5)
        ns.hc.stop_all_coils()
        hc_ctx.__exit__(None, None, None)
        ns.geri()
