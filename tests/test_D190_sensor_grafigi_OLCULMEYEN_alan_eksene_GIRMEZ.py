# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.90 · B-6.22 + İG-6.90 — fikstür ve sözleşme yarısı: Sensör Monitörü grafiği ölçülmeyen alanı (bobin 7'nin 0.0 mT'si)
eksene ve eğriye KATMAZ.

ÖLÇÜLEN KUSUR (aday İG-6.90, gerçek backend yayınları + web canvas `fillText` okuması): bobin 6 alan basarken
(B=12,3 mT) bobin 7 yalnız sıcaklık basıyor; WS `sensor_data` bobin 7 için `magneticMt: 0.0` + `measuredFields` (alan
YOK) taşıyor. Arayüz `measuredFields`i geçmişe taşımadığı için grafik 0.0'ı ölçüm sayıp mT eksenini 0,0–12,3'e çekiyordu
(yalnız bobin 6: 12,2–12,4). 1.9.50'de VAR (web `RealtimeChart.tsx:94`, native `:275`).

Bu dosya arayüz kapısının GİRDİSİNİ gerçek yoldan üretir: firmware satırı (`STM_TELE: …`) → GERÇEK ayrıştırıcı
(`HeadlessCore._parse_stm_tele`) → GERÇEK olay işleyicisi (`_handle_backend_event`) → yakalanan `sensor_data` yayınları.
Fikstür `apps/ui/src/components/visual/__tests__/__fixtures__/sensorGrafigi.D190.ws.json`; bayatlarsa
`test_arayuz_fiksturu_GERCEK_yayinlarla_AYNI` KIRMIZI (yeniden üret: `D190_FIKSTUR_YAZ=1`). Zaman damgaları sıra
numarasına sabitlenir (yalnız sıralama anlamlı).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

_KOK = Path(__file__).resolve().parents[1]
_FIKSTUR = (
    _KOK / "apps" / "ui" / "src" / "components" / "visual" / "__tests__" / "__fixtures__" / "sensorGrafigi.D190.ws.json"
)
_ALANLAR = ("objectTemp", "ambientTemp", "magneticMt", "currentA")

# Firmware satırları (aday ölçümündeki değerler): bobin 6 sıcaklık + alan, bobin 7 YALNIZ sıcaklık, bobin 1 YALNIZ akım.
_SATIRLAR = [
    "STM_TELE: C=6,T=34.20,B=12.300",
    "STM_TELE: C=7,T=33.10",
    "STM_TELE: C=1,I=0.42",
    "STM_TELE: C=6,T=34.30,B=12.200",
    "STM_TELE: C=7,T=33.20",
    "STM_TELE: C=1,I=0.43",
    "STM_TELE: C=6,T=34.40,B=12.400",
    "STM_TELE: C=7,T=33.30",
    "STM_TELE: C=1,I=0.41",
]


class _Olay:
    def __init__(self, govde: dict):
        self.event_type = "hardware.stm.telemetry"
        self.data = govde


@pytest.fixture()
def yayinlar(monkeypatch):
    from servers import api_server as api

    yakalanan: list[dict] = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: yakalanan.append(m))
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)

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

    _temizle()
    try:
        yield api, yakalanan
    finally:
        _temizle()


def _uret(api, yakalanan) -> list[dict]:
    from headless_core import HeadlessCore

    ayristirici = SimpleNamespace(_TELE_DESENI=HeadlessCore._TELE_DESENI)
    for satir in _SATIRLAR:
        govde = HeadlessCore._parse_stm_tele(ayristirici, satir)
        assert govde, f"aparat: ayristirici satiri okumadi: {satir}"
        api._handle_backend_event(_Olay(govde))
    sd = [m for m in yakalanan if m.get("type") == "sensor_data"]
    assert len(sd) == len(_SATIRLAR), f"aparat: her satir bir sensor_data yayini uretmeli ({len(sd)})"
    return [{**m, "timestamp": 1000 + i} for i, m in enumerate(sd)]


def test_KRITIK_sozlesme_olculmeyen_alan_measuredFields_DISINDA_ve_deger_0(yayinlar):
    """Arayüz düzeltmesinin dayandığı sözleşme: ölçülmeyen alan SAYI olarak 0.0 gelir ama `measuredFields`te YOKTUR."""
    api, yakalanan = yayinlar
    sd = _uret(api, yakalanan)
    b7 = [m["data"] for m in sd if m["coilId"] == 7]
    b6 = [m["data"] for m in sd if m["coilId"] == 6]
    assert all("magneticMt" not in d["measuredFields"] and d["magneticMt"] == 0.0 for d in b7), b7
    assert all("objectTemp" in d["measuredFields"] for d in b7), b7
    assert all("magneticMt" in d["measuredFields"] and d["magneticMt"] > 12 for d in b6), b6


def test_arayuz_fiksturu_GERCEK_yayinlarla_AYNI(yayinlar):
    api, yakalanan = yayinlar
    metin = json.dumps(_uret(api, yakalanan), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("D190_FIKSTUR_YAZ") == "1":
        _FIKSTUR.parent.mkdir(parents=True, exist_ok=True)
        _FIKSTUR.write_text(metin, encoding="utf-8")
    assert _FIKSTUR.exists(), "arayuz fiksturu yok (D190_FIKSTUR_YAZ=1 ile uret)"
    assert json.loads(_FIKSTUR.read_text(encoding="utf-8")) == json.loads(metin), (
        "arayuz fiksturu BAYAT: gercek sensor_data yayini degisti (D190_FIKSTUR_YAZ=1 ile yeniden uret, jest kapisini kos)"
    )
