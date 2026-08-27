# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YARA-KAPANMA ÖN-ISITMA (klinik backend) — saha bildirimi 2026-08-27.

ÖLÇÜLEN ARIZA: "analiz ete basıyorum çalışmıyor… ilk analizde boş sonuç döndü, 2.'de çıktı."
Modül sağlamdı (kurulu backend'e doğrudan istek: HTTP 200, 1495 hücre, 23,8 sn); sorun İLK
çağrının maliyetiydi. Ölçüm (aynı makine, boşta): İLK istek 32,8 sn — ikinci 22,4 sn. Aradaki
~10 sn saf 872 MB model yüklemesi ve o süre boyunca predictor kilidi tutuluyor.

KÖK NEDEN: `isit()` (arka planda ön-yükleme) YALNIZ GPU mikroserviste (ai_service) çağrılıyordu;
klinik backend'in lifespan'inde HİÇ yoktu → her açılıştan sonraki ilk analiz tam bedeli ödüyordu.

Kilitlenen davranışlar:
 1) Klinik backend açılışta ısıtmayı BAŞLATIR (ayrı thread — default executor'da DEĞİL: 872 MB
    yükleme boyunca E-stop dahil to_thread çağrıları kuyruğa girerdi).
 2) cell/ teslim EDİLMEMİŞSE thread hiç başlatılmaz (ai_service'te ölçülen exit-134 dersi).
 3) PEMF_SCRATCH_WARMUP=0 ile kapatılabilir (araştırma profili yoksa RAM boşa gitmesin).
 4) Isıtma hatası servisi ASLA düşürmez (bir kolaylıktır).
"""

import importlib

import pytest


@pytest.fixture()
def apis():
    import servers.api_server as m

    return m


def test_KRITIK_acilista_isitma_THREAD_ile_baslar(apis, monkeypatch):
    """Ayrı thread ŞART: ısıtma default executor'u işgal ederse E-stop kuyruğa girer."""
    baslatilan = {}

    class _SahteThread:
        def __init__(self, target=None, daemon=None, name=None):
            baslatilan.update(target=target, daemon=daemon, name=name)

        def start(self):
            baslatilan["basladi"] = True

    monkeypatch.setenv("PEMF_SCRATCH_WARMUP", "1")
    monkeypatch.setattr(apis.threading, "Thread", _SahteThread)
    apis._scratch_isit_baslat()

    assert baslatilan.get("basladi") is True, "ısıtma hiç başlatılmadı — ilk analiz tam bedeli öder"
    assert baslatilan["daemon"] is True and baslatilan["name"] == "scratch-warmup"
    # Hedef GERÇEK ısıtma fonksiyonu olmalı (isim benzeri bir şey değil)
    from ai_hub.inference_paper_dilek_hoca import inference_paper_dilek_hoca as ipd

    assert baslatilan["target"] is ipd.isit


def test_KRITIK_lifespan_ISITMAYI_cagiriyor(apis):
    """Wiring kilidi: fonksiyon var ama lifespan çağırmazsa arıza aynen sürer (ölçülen durum)."""
    import inspect

    kaynak = inspect.getsource(apis.lifespan)
    assert "_scratch_isit_baslat()" in kaynak, "lifespan ısıtmayı çağırmıyor — saha arızası geri gelir"


def test_KARSIT_KANIT_WARMUP_0_iken_thread_ACILMAZ(apis, monkeypatch):
    """Araştırma profili kurulu olmayan makinede 872 MB'ı boşa yükleme."""
    acildi = {"n": 0}

    class _Sayac:
        def __init__(self, **k):
            acildi["n"] += 1

        def start(self):
            pass

    monkeypatch.setenv("PEMF_SCRATCH_WARMUP", "0")
    monkeypatch.setattr(apis.threading, "Thread", _Sayac)
    apis._scratch_isit_baslat()
    assert acildi["n"] == 0


def test_KARSIT_KANIT_cell_YOKSA_thread_ACILMAZ(apis, monkeypatch):
    """ai_service exit-134 dersi: cell/ teslim edilmemişken kısa ömürlü daemon thread
    interpreter kapanışıyla yarışıp SIGABRT üretebiliyordu → hiç başlatma."""
    acildi = {"n": 0}

    class _Sayac:
        def __init__(self, **k):
            acildi["n"] += 1

        def start(self):
            pass

    monkeypatch.setenv("PEMF_SCRATCH_WARMUP", "1")
    monkeypatch.setattr(apis.threading, "Thread", _Sayac)
    monkeypatch.setattr(importlib.util, "find_spec", lambda ad: None)
    apis._scratch_isit_baslat()
    assert acildi["n"] == 0


def test_KARSIT_KANIT_isitma_HATASI_servisi_DUSURMEZ(apis, monkeypatch):
    """Isıtma bir kolaylıktır: patlarsa backend yine ayağa kalkmalı."""
    monkeypatch.setenv("PEMF_SCRATCH_WARMUP", "1")

    def _patla(*a, **k):
        raise RuntimeError("ısıtma patladı (test)")

    monkeypatch.setattr(apis.threading, "Thread", _patla)
    apis._scratch_isit_baslat()  # istisna DIŞARI ÇIKMAMALI
