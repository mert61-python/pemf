# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YS2 e · B9 (YG2 25-11, `DENETIM\\YAYIN-GUNU.md`): açılışta hotspot backend'in ilk yoklamasından SONRA kalkınca Sistem Durumu
"Cihaz Wi-Fi'si (PEMF-Gateway)" ≤ 60 sn yanlış "Kapalı" (kırmızı) gösteriyordu — `_cached_poll` TTL 60 sn olumsuz sonucu da tutuyordu.

SÖZLEŞME: olumsuz (kapalı) sonuç 10 sn sonra yeniden yoklanır; olumlu (açık) sonuç 60 sn önbellekte (yoklama fırtınası yok —
`test_kalan_davranissal::test_pahali_yoklamalar_ONBELLEKLENIR` aynen); hata / zaman aşımında son değer korunur; kapalıyken `arp`
sayımı (arp) aynen. Bağlantı mantığı değişmez. APARAT: gerçek `NetworkStatusService._check_hotspot`; saat ve komut koşucusu sahte (en alt kat).
"""

from __future__ import annotations

import types

import pytest


@pytest.fixture
def ns(monkeypatch):
    from services import headless_services as hs

    saat = {"t": 1000.0}
    monkeypatch.setattr(hs.time, "monotonic", lambda: saat["t"])
    monkeypatch.setattr(hs.platform, "system", lambda: "Windows")
    durum = {"aktif": False, "komutlar": []}

    def _kos(komut, *a, **k):
        durum["komutlar"].append(komut[0])
        if komut[0] == "powershell":
            return types.SimpleNamespace(returncode=0, stdout="192.168.137.1\n" if durum["aktif"] else "")
        return types.SimpleNamespace(returncode=0, stdout="  192.168.137.20  aa-bb  dynamic\n")

    monkeypatch.setattr(hs, "_run_command", _kos)
    m = hs.NetworkStatusService.__new__(hs.NetworkStatusService)
    return types.SimpleNamespace(m=m, saat=saat, durum=durum)


def test_KRITIK_B9_acilista_KAPALI_sonucu_hotspot_kalkinca_60_sn_BEKLETMEZ(ns):
    assert ns.m._check_hotspot()["active"] is False  # ilk yoklama: hotspot henüz kalkmadı
    ns.durum["aktif"] = True  # hotspot kalktı
    ns.saat["t"] += 12.0
    assert ns.m._check_hotspot()["active"] is True, (
        "hotspot kalktığı hâlde 'Kapalı' önbellekten döndü (≤ 60 sn yanlış kırmızı)"
    )


def test_KARSIT_B9_ACIK_sonuc_60_sn_onbellekte_yoklama_firtinasi_YOK(ns):
    ns.durum["aktif"] = True
    assert ns.m._check_hotspot()["active"] is True
    n = len(ns.durum["komutlar"])
    ns.saat["t"] += 30.0
    assert ns.m._check_hotspot()["active"] is True
    assert len(ns.durum["komutlar"]) == n, "açık sonuç 60 sn dolmadan yeniden yoklandı (süreç fırtınası)"


def test_B9_KAPALI_sonuc_10_sn_icinde_YENIDEN_yoklanmaz(ns):
    assert ns.m._check_hotspot()["active"] is False
    n = len(ns.durum["komutlar"])
    ns.saat["t"] += 5.0
    ns.m._check_hotspot()
    assert len(ns.durum["komutlar"]) == n, "olumsuz sonuç 10 sn dolmadan yeniden yoklandı"


def test_B9_ACIKKEN_istemci_sayisi_AYNEN(ns):
    ns.durum["aktif"] = True
    assert ns.m._check_hotspot() == {"active": True, "ssid": "", "ip": "192.168.137.1", "clients": 1}
