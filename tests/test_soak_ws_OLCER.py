# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.22 (B-9.26) — `soak_http_ws` GERÇEKTEN WebSocket açıyor ve kopmayı karara katıyor.

ARIZA: betik adı, özeti ve belgeler "HTTP + WebSocket soak" diyordu ama hiç `/ws` açmıyordu — canlı
telemetri/kontrol kanalının kopma sınıfı soak'ta GÖRÜNMÜYORDU, yine de "TEMIZ" kaydı düşüldü
(VERIFICATION §7).

KAPI: betiğin GERÇEK `main()`i 127.0.0.1 rastgele porttaki SAHTE backend'e karşı kısa koşar
(`sahte_soak_backend`); psutil sahtedir, RSS kararlı. WS ortada kesilir → kopma raporlanır ve ≠0;
sunucu kaydında `Upgrade: websocket` ≥1. Karşıt: WS açık kalır → TEMIZ / 0. `/ws` artık açıldığı için
varsayılan port 8000 (sahibin backend'i) SESSİZCE hedeflenmez: `--port` zorunlu.
MUTASYON: WS istemci bloğunu silmek → KIRMIZI.
"""

from __future__ import annotations

import sys

import pytest
from betik_alt_sureci import betik_modulu
from sahte_soak_backend import SahteBackend, kos, sahte_psutil, soak_modulu


def test_KRITIK_soak_GERCEK_WS_acar_ve_KOPMAYI_karara_katar(monkeypatch, capsys):
    m = soak_modulu(monkeypatch)
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", 500.0))
    sunucu = SahteBackend("kes")
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port)
    finally:
        sunucu.kapat()
    assert sunucu.ws_yukseltme_sayisi() >= 1, "soak /ws'ye HİÇ yükseltme isteği atmadı — WS ölçülmüyor (B-9.26)"
    assert rc != 0, f"WS koptuğu hâlde çıkış {rc} (B-9.26):\n{cikti[-800:]}"
    assert "TEMIZ" not in cikti and "KOP" in cikti.upper(), f"WS kopması raporlanmadı:\n{cikti[-800:]}"


def test_KRITIK_WS_ye_HIC_baglanilamazsa_OLCULMEDI_der(monkeypatch, capsys):
    """Bağlanılamayan kanal "kararlı" sayılamaz — ve "koptu" ile de karıştırılmaz (ölçülmedi)."""
    m = soak_modulu(monkeypatch)
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", 500.0))
    sunucu = SahteBackend("reddet")
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port)
    finally:
        sunucu.kapat()
    assert rc != 0 and "TEMIZ" not in cikti, f"WS'ye hiç bağlanılamadığı hâlde TEMIZ/0 (rc={rc}):\n{cikti[-800:]}"
    assert "OLCULMEDI" in cikti, f"bağlanılamayan WS 'ölçülmedi' diye raporlanmadı:\n{cikti[-800:]}"


def test_KARSIT_KANIT_WS_acik_ve_RSS_kararli_TEMIZ(monkeypatch, capsys):
    m = soak_modulu(monkeypatch)
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", 500.0))
    sunucu = SahteBackend("tut")
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port)
    finally:
        sunucu.kapat()
    assert sunucu.ws_yukseltme_sayisi() >= 1, "karşıt senaryo WS açmadı"
    assert rc == 0 and "TEMIZ" in cikti, f"sağlıklı koşu TEMIZ değil (rc={rc}):\n{cikti[-800:]}"


def test_KRITIK_port_ZORUNLU_istek_ATILMAZ(monkeypatch):
    m = betik_modulu("soak_http_ws")
    istekler: list[str] = []
    monkeypatch.setattr(m, "_istek", lambda taban, yol, *a, **k: istekler.append(taban + yol) or (0, 0))
    monkeypatch.setattr(sys, "argv", ["soak_http_ws.py", "--dakika", "0.01"])
    with pytest.raises(SystemExit) as e:
        m.main()
    assert e.value.code == 2, f"--port verilmeden çalıştı (çıkış {e.value.code!r})"
    assert not istekler, f"--port verilmeden istek atıldı: {istekler}"
