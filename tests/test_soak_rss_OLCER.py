# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.15 (B-10.97) — `soak_http_ws` bellek sızıntısını ÖLÇEMEDİĞİNDE "TEMIZ" demiyor.

ARIZA: psutil yoksa ya da `PEMF_Backend` süreci bulunamazsa RSS 0 okunuyordu; oran 0 → sonuç
"TEMIZ" / 0 (bellek sızıntısı hiç ölçülmeden). Tek örnekte de 0 dönüyordu. RSS ölçülemezken ısınma
beklemesi 180 sn boşuna dönüyordu (ölçülemeyen şey oturmaz). Veri kökünü çözen ölü import D0Ö.19
(`a7a2b48`) ile düzeldi (kapı: `test_f4_rapor_soak_betikleri_CALISIYOR`).

KAPI: GERÇEK `main()`, sahte backend (`sahte_soak_backend`) + sahte psutil (`python.exe` — backend yok):
"RSS ÖLÇÜLMEDİ" ve ≠0, TEMIZ DEĞİL; tek örnek → ≠0; RSS ölçülemezken ısınma beklenmez.
MUTASYON: RSS=0'da denetimi atlayıp TEMIZ dönmek → KIRMIZI.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from betik_alt_sureci import betik_modulu
from sahte_soak_backend import SahteBackend, kos, sahte_psutil, soak_modulu


def test_KRITIK_RSS_OLCULEMEZSE_TEMIZ_DEMEZ(monkeypatch, capsys):
    m = soak_modulu(monkeypatch)
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("python.exe", 80.0))  # backend süreci YOK
    sunucu = SahteBackend("tut")
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port)
    finally:
        sunucu.kapat()
    assert rc != 0 and "TEMIZ" not in cikti, f"RSS hiç ölçülmeden TEMIZ/0 (B-10.97, rc={rc}):\n{cikti[-800:]}"
    assert "RSS ÖLÇÜLMEDİ" in cikti, f"'RSS ÖLÇÜLMEDİ' denmedi:\n{cikti[-800:]}"
    assert sunucu.ws_yukseltme_sayisi() >= 1, "soak /ws açmadı — 'HTTP + WebSocket soak' iddiası boş (B-10.97)"


def test_KRITIK_tek_ornekte_cikis_SIFIR_DEGIL(monkeypatch, capsys):
    m = soak_modulu(monkeypatch)
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", 500.0))
    sunucu = SahteBackend("tut")
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port, dakika=0.03, aralik=30.0)
    finally:
        sunucu.kapat()
    assert rc != 0, f"tek örnekle karar verilemez ama çıkış 0 (B-10.97):\n{cikti[-600:]}"
    # D0Ö.22 ek: erken dönüş yolunda da WS sayaçları basılır (eskiden bu yolda WS özeti hiç yoktu).
    assert "baglanti" in cikti and "KOPMA" in cikti, f"tek örnek yolunda WS özeti yok:\n{cikti[-600:]}"


def test_KRITIK_RSS_OLCULEMEZKEN_isinma_BEKLENMEZ(monkeypatch):
    m = betik_modulu("soak_http_ws")
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("python.exe", 80.0))
    saat = {"t": 0.0}
    uykular: list[float] = []

    def _uyu(sn):
        uykular.append(sn)
        saat["t"] += sn

    monkeypatch.setattr(m, "time", SimpleNamespace(monotonic=lambda: saat["t"], sleep=_uyu))
    m._rss_oturmasini_bekle(azami_sn=30.0)
    assert not uykular, f"RSS ölçülemezken {sum(uykular):.0f} sn ısınma beklendi (ölçülemeyen şey oturmaz)"
