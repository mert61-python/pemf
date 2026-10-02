# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.53 · D1.81 · 1-C bağımsız inceleme i3-F-4 — mandal kuruluyken 0 Hz isteği (A-05: 0 Hz = o bobin için STOP) STOP üretir.

Y4: mandal YALNIZ START'ı engeller. A-05: 0 Hz başlatma = STOP (D1.53: HC, tekil, batch, seans). Mandal 409'u tekil ve
batch'te 0 Hz dönüşümünden SONRA (doğru), ama legacy `/api/hardware/command` (start_coil / start_all_coils) ve
`/api/session/start` 0 Hz'e bakmadan 409 dönüyordu → mandallıyken 0 Hz isteği HİÇ STOP üretmiyordu (ölçüldü: i3, 3 yol;
mandal öncesi sürüm 1/1/2 STOP paketi → 0/0/0). Mandal kurulu = E-stop STOP'unu zaten göndermişti (fiziksel etki düşük);
ihlal kural düzeyinde: mandal bir STOP'u reddetti.

DÜZELTME: legacy uçta 409 yalnız 0 Hz OLMAYAN START'a; seans girişinde mandallıyken 0 Hz → istenen bobinlere STOP + A-05
nedeni (seans AÇILMAZ, DB satırı yazılmaz).
KAPI (GERÇEK uçlar + GERÇEK `HardwareController`; ölçüt istek SONRASI tüm-duty-0 paket, firmware aynası): önce bobin 1
GERÇEKTEN sürülür, sonra GERÇEK `_emergency_stop_all` (mandal kurulur), sonra 0 Hz isteği.
KARŞIT: mandallıyken 0 Hz OLMAYAN START hâlâ 409 ve sürüş yok (mandal gevşemedi).
"""

from __future__ import annotations

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _stop_paket(o, once: int) -> int:
    from kayitci_donanim import paket_coz

    return sum(1 for p in o.hc.core._hw_send_queue.paketler[once:] if all(d == 0 for d in paket_coz(p)[0]))


_SEANS = {"mode": "Manuel", "duty": 50, "phase": 0, "duration_minutes": 5, "coil_ids": [1, 2], "patient_name": "Pamuk"}
_ISTEK = {
    "tekil_coil_control": ("/api/coil/1/control", {"start": True, "freq": 0, "duty": 50, "phase": 0}),
    "batch": ("/api/coil/batch", {"coil_ids": [1, 2], "start": True, "freq": 0, "duty": 50}),
    "legacy_start_coil": (
        "/api/hardware/command",
        {"command": "start_coil", "params": {"coil_id": 1, "freq": 0, "duty": 50}},
    ),
    "legacy_start_all": ("/api/hardware/command", {"command": "start_all_coils", "params": {"freq": 0, "duty": 50}}),
    "seans_start": ("/api/session/start", {**_SEANS, "frequency": 0}),
}


def _mandalli_surulmus(o):
    from utils import estop_mandali as m

    assert o.hc.update_coil(1, 100.0, 40.0, 0.0, 5, start=True) is True, "aparat: bobin 1 sürülmedi"
    o.api._emergency_stop_all("manual")
    assert m.mandalli_mi(), "aparat: E-stop mandalı kurmadı"


@pytest.mark.parametrize("yol", list(_ISTEK))
def test_KRITIK_mandalliyken_0Hz_istegi_STOP_uretir_A05_Y4(o, yol):
    _mandalli_surulmus(o)
    once = ap.paket_sayisi(o)
    uc, govde = _ISTEK[yol]
    r = o.c.post(uc, json=govde)
    stop_n = _stop_paket(o, once)
    assert stop_n >= 1, (
        f"mandal kuruluyken 0 Hz (A-05 = STOP) isteği '{yol}' HİÇ STOP üretmedi (HTTP {r.status_code}: {r.text[:120]}) — "
        "mandal bir STOP'u reddetti (Y4: mandal YALNIZ START'ı engeller)"
    )
    assert not ap.surus_paketleri(o, once) and ap.calisan(o) == [], f"'{yol}': 0 Hz isteği bir bobini SÜRDÜ"
    if yol == "seans_start":
        assert r.status_code != 200 and "0 Hz" in r.text and "MANDALLI" not in r.text, (
            f"0 Hz seans: neden A-05 (0 Hz = durdurma) olmalı, mandal mesajı değil: {r.status_code} {r.text[:200]}"
        )
        with o.api._session_lock:
            assert o.api._active_session.get("is_active") is not True, "mandallıyken 0 Hz seans 'aktif' kaldı"


@pytest.mark.parametrize(
    "uc,govde",
    [
        ("/api/hardware/command", {"command": "start_coil", "params": {"coil_id": 1, "freq": 100, "duty": 50}}),
        ("/api/hardware/command", {"command": "start_all_coils", "params": {"freq": 100, "duty": 50}}),
        ("/api/session/start", {**_SEANS, "frequency": 100}),
    ],
)
def test_KARSIT_mandalliyken_0Hz_OLMAYAN_START_hala_409(o, uc, govde):
    _mandalli_surulmus(o)
    once = ap.paket_sayisi(o)
    r = o.c.post(uc, json=govde)
    assert r.status_code == 409 and "Sıfırla" in r.json().get("detail", ""), f"{uc}: {r.status_code} {r.text[:200]}"
    assert not ap.surus_paketleri(o, once) and ap.calisan(o) == [], f"{uc}: mandallıyken START sürdü"
