# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.83 · S-1.1 + D1.84 · B-5.2 (Y25) — AI Pro bobin 1-7'yi STM tek kaynağından sürer; ekran yalnız SÜRÜLENİ "sürüldü" der.

ÖLÇÜLEN KUSUR (DENETIM-01 S-1.1 · 05 B-5.2; ikiz): `_drive_coils_ai_pro` bobin 1-5'i `HardwareController.update_coil`
ile, 6-7'yi `for idx in (5, 6)` → MQTT `pemf/coil/{6,7}/control` ile sürüyordu. Faz 4'ten (ccd2063) beri 6-7 STM'de
(`live_state.STM_COIL_IDS = {1..7}`, `ESP_COIL_IDS = {8}`) → telde 6-7 duty 0, MQTT konuları ÖLÜ (1-C §9 #3). Hekimin
onayladığı 7 bobinlik planın 6-7 payı uygulanmıyordu; panel ve kayıt ise 7 bobini "uygulandı" gösteriyordu
(`perCoil` planlanan değer, sürüş sonucu değil; `update_coil`'in dönüşü okunmuyordu — İG-5.32).

Sahip kararı Y25: 6-7 AI Pro'da STM'e yönlendirilir; sıra şartı (D1.80 onaysız /frame, D1.81 E-stop sonrası yeniden
enerjileme) 1-C'de kapandı. A-47: termal kesme EKLENMEZ. Ekran 6-7 (ve herhangi bir bobin) için gerçeği gösterir:
sürülmediyse "sürülmedi". Tezgâh (sahadaki firmware'in 7 bobini sürdüğü) Oturum 13 — burada paket düzeyinde ölçülür.

KAPI: GERÇEK `HardwareController` (kayıtçı kuyruk, firmware aynası) + GERÇEK `_drive_coils_ai_pro` / `/frame` / döngü;
ESP AÇIK (`PEMF_ESP_ENABLED=1`) — ölü konulara yayın da ölçülsün. 1-C §9 #4: teardown `ai_stop_` kimliği D1.E10 gibi
süreç-içi sıra eki taşır.
"""

from __future__ import annotations

import re

import ai_pro_aparati as ap
import numpy as np
import pytest

D7 = [0.30, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36]
P7 = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    ns = ap.kur(monkeypatch, tmp_path)
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


def _start_yayinlari(o, bobinler=(6, 7)):
    return [
        (t, p)
        for t, p in o.yayin
        if str(p.get("command", "")).lower() == "start" and any(t == f"pemf/coil/{b}/control" for b in bobinler)
    ]


def _son_duty(o, once):
    paketler = ap.surus_paketleri(o, once)
    return paketler[-1] if paketler else ()


def test_KRITIK_D183_surus_bobin_1_7_STMe_GIDER_6_7_MQTTye_GITMEZ(o):
    from utils import estop_mandali

    ap.muhurlu_seans_yaz(o.api, sure_dk=10)
    once = ap.paket_sayisi(o)
    with estop_mandali.surus_baglami(estop_mandali.nesil()):
        surulen = o.air._drive_coils_ai_pro(D7, P7)
    son = _son_duty(o, once)
    assert sorted(ap.calisan(o)) == [1, 2, 3, 4, 5, 6, 7], f"çalışan bobinler {ap.calisan(o)} (telde son duty {son})"
    assert len(son) >= 7 and all(d > 0 for d in son[:7]), f"telde 1-7'nin hepsi sürülmedi: {son}"
    assert not _start_yayinlari(o), f"6-7 ÖLÜ MQTT konularına START yayınlandı: {_start_yayinlari(o)}"
    assert surulen == [1, 2, 3, 4, 5, 6, 7], f"sürüş sonucu (sürülen bobinler) döndürülmüyor: {surulen!r}"


def test_KARSIT_D183_muhur_YOKKEN_hicbir_bobin_surulmez(o):
    from utils import estop_mandali

    once = ap.paket_sayisi(o)
    with estop_mandali.surus_baglami(estop_mandali.nesil()):
        surulen = o.air._drive_coils_ai_pro(D7, P7)
    assert not ap.surus_paketleri(o, once) and not ap.calisan(o) and not surulen


def test_KRITIK_D184_frame_perCoil_SURULDU_kumesi_TELDE_surulen_kumeye_ESIT(o, monkeypatch):
    monkeypatch.setattr(o.air, "_predict_and_drive", lambda *a, **k: (list(D7), list(P7), 0.5))
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    j = ap.kare(o).json()
    assert j.get("driven") is True, f"aparat: kare sürülmeliydi: {j.get('driven')}"
    pc = {c["id"]: c for c in j.get("perCoil") or []}
    assert set(pc) == set(range(1, 8)), f"perCoil 7 bobini taşımıyor: {sorted(pc)}"
    suruldu = {i for i, c in pc.items() if c.get("suruldu") is True}
    assert suruldu == set(ap.calisan(o)) == set(range(1, 8)), (
        f"perCoil 'sürüldü' {sorted(suruldu)} ≠ telde çalışan {sorted(ap.calisan(o))} (alan: {sorted(pc[6])})"
    )


def test_KRITIK_D184_REDDEDILEN_bobin_SURULMEDI_gosterilir(o, monkeypatch):
    """Kart bobin 6'yı reddederse (`update_coil` False) yanıt 6'yı "sürüldü" DEMEZ; diğerleri sürülür."""
    monkeypatch.setattr(o.air, "_predict_and_drive", lambda *a, **k: (list(D7), list(P7), 0.5))
    gercek = o.hc.update_coil

    def _alti_red(cid, *a, **k):
        if cid == 6 and k.get("start"):
            return False
        return gercek(cid, *a, **k)

    monkeypatch.setattr(o.hc, "update_coil", _alti_red)
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    j = ap.kare(o).json()
    pc = {c["id"]: c for c in j.get("perCoil") or []}
    assert pc and pc[6].get("suruldu") is False, f"reddedilen bobin 6 'sürüldü' gösterildi: {pc.get(6)}"
    assert {i for i, c in pc.items() if c.get("suruldu")} == set(ap.calisan(o)), (pc, ap.calisan(o))
    assert 6 not in ap.calisan(o)


def test_KRITIK_D184_DONGU_ws_perCoil_SURULDU_ve_teardown_ai_stop_KIMLIGI_sirali(monkeypatch, tmp_path):
    """GERÇEK `_ai_pro_loop` (sahte kamera): WS `ai_vision.perCoil` 1-7'yi "sürüldü" der; durdurmada teardown'ın ESP
    STOP kimliği D1.E10 gibi sıra eki taşır (1-C §9 #4: yalnız ms → aynı ms'de 8266 tekrar önbelleği ikinciyi yutar)."""
    from kayitci_donanim import gercek_hc

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)  # ⚠️ ayrı kurulum: `o` aparatı döngüyü no-op'a yamalar
    monkeypatch.setattr(ns.air, "_predict_and_drive", lambda *a, **k: (list(D7), list(P7), 0.5))
    from servers import ai_pro_hedef

    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)  # em_kedi ağırlığı depoda yok

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
    hc_ctx = gercek_hc()
    ns.hc = hc_ctx.__enter__()
    monkeypatch.setattr(ns.api.state, "hardware", ns.hc)
    try:
        _pid, r = ap.onayli_baslat(ns, organ=2)
        assert r.status_code == 200, r.text[:200]

        def _ws_percoil():
            for m in reversed(ns.ws):
                if isinstance(m, dict) and m.get("type") == "ai_vision" and (m.get("data") or {}).get("perCoil"):
                    return m["data"]["perCoil"]
            return None

        assert ap.bekle(lambda: _ws_percoil() is not None and ap.calisan(ns) != [], 5), (
            f"aparat: döngü sürüş yayını yapmadı: {_ws_percoil()} (çalışan {ap.calisan(ns)})"
        )
        assert ap.bekle(lambda: any(c.get("suruldu") for c in _ws_percoil()), 3), (
            f"WS perCoil 'sürüldü' bilgisini taşımıyor: {_ws_percoil()}"
        )
        pc = {c["id"]: c for c in _ws_percoil()}
        assert {i for i, c in pc.items() if c.get("suruldu")} == set(range(1, 8)), pc
        # ACİL DURDUR: mandal kuruluyken teardown ESP STOP'u HER ZAMAN gönderir (1-C i3-F-1) → `ai_stop_` dalı koşar.
        # (`/ai/pro/stop` yetkiyi önce kesip STOP'u kendisi gönderir; teardown o yolda ESP STOP yayınlamaz.)
        ns.api._emergency_stop_all("manual")
        assert ap.bekle(lambda: not ns.air._ai_loop_active, 5)
        stoplar = [p.get("command_id", "") for t, p in ns.yayin if str(p.get("command", "")).lower() == "stop"]
        ai_stop = [k for k in stoplar if k.startswith("ai_stop_")]
        assert ai_stop, f"aparat: teardown ESP STOP'u yayınlanmadı: {stoplar[-5:]}"
        assert all(re.fullmatch(r"ai_stop_\d+_\d+_\d+", k) for k in ai_stop), (
            f"ai_stop_ kimliğinde sıra eki yok: {ai_stop}"
        )
    finally:
        ns.air._ai_loop_active = False
        ns.hc.stop_all_coils()
        hc_ctx.__exit__(None, None, None)
        ns.geri()


def test_KRITIK_D184_TUM_bobinler_REDDEDILINCE_frame_SURULDU_demez(o, monkeypatch):
    monkeypatch.setattr(o.air, "_predict_and_drive", lambda *a, **k: (list(D7), list(P7), 0.5))
    gercek = o.hc.update_coil
    monkeypatch.setattr(o.hc, "update_coil", lambda cid, *a, **k: False if k.get("start") else gercek(cid, *a, **k))
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    j = ap.kare(o).json()
    assert j.get("driven") is not True, f"hiçbir bobin kabul edilmediği hâlde kare 'sürüldü' dedi: {j.get('driven')}"
    assert not any(c.get("suruldu") for c in j.get("perCoil") or []), j.get("perCoil")


def test_KRITIK_D183_TEK_KAYNAK_STM_COIL_IDS_kullanilir_disindaki_bobin_SURULMEDI(o, monkeypatch):
    """Topoloji tek kaynaktan: 6-7 STM kümesinde değilse sürülmez, ÖLÜ konuya yayınlanmaz, "sürülmedi" olur."""
    from servers import live_state
    from utils import estop_mandali

    monkeypatch.setattr(live_state, "STM_COIL_IDS", {1, 2, 3, 4, 5})
    ap.muhurlu_seans_yaz(o.api, sure_dk=10)
    with estop_mandali.surus_baglami(estop_mandali.nesil()):
        surulen = o.air._drive_coils_ai_pro(D7, P7)
    assert surulen == [1, 2, 3, 4, 5] and sorted(ap.calisan(o)) == [1, 2, 3, 4, 5], (surulen, ap.calisan(o))
    assert not _start_yayinlari(o), "STM dışı bobin ölü MQTT konusuna yayınlandı"
    pc = {c["id"]: c for c in o.air._build_ai_pro_percoil(D7, P7, surulen)}
    assert pc[6]["suruldu"] is False and pc[7]["suruldu"] is False and pc[5]["suruldu"] is True
