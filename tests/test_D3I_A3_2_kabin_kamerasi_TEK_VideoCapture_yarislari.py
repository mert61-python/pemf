# -*- coding: utf-8 -*-
"""D3I-A3.2 KAPI ADAYI — kabin kamerası "tek VideoCapture / AI Pro öncelikli" sözleşmesi EŞZAMANLI çağrılarda da tutar.

Modül sözleşmesi (`utils/kabin_kamerasi.py` başlığı, Y190): "`kamera_ac` (AI Pro hazırlık / seans, tek kare) açık canlı oturumu ÖNCE
kapatır — AI Pro önceliklidir, iki `VideoCapture` çakışmaz". ÖLÇÜLEN (HEAD `199f9a76`): (1) canlı başlatma kamerayı AÇARKEN gelen
`kamera_ac` canlıyı göremez → iki `VideoCapture` aynı anda açık ve AI Pro açtıktan SONRA canlı oturum da açık kalır; (2) uç girişteki
AI Pro meşguliyet denetimi kilit dışında → AI Pro bu arada kamerayı alırsa canlı yine açılır; (3) eşzamanlı "Fotoğraf Çek" / tarama
her biri ayrı `VideoCapture` açar (aynı anda 6 ölçüldü).
Sahte EN ALT katta: GERÇEK `cv2` modülünün `VideoCapture`ı sahte (yavaş açılış). Gerçek kamera YOK.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest


class _Kamera:
    kilit = threading.Lock()
    olusan = acik = en_cok_acik = 0
    acilis_sn = 0.0
    #: ilk N açılışın süresi (sıra) — boşsa `acilis_sn`; `acilisa_girdi`: bir açılış BAŞLADI (zamanlama uykusu yerine olay)
    acilis_sirasi: list = []
    acilisa_girdi = threading.Event()

    @classmethod
    def sifirla(cls, sira=()):
        with cls.kilit:
            cls.olusan = cls.acik = cls.en_cok_acik = 0
            cls.acilis_sirasi = list(sira)
        cls.acilis_sn = 0.0
        cls.acilisa_girdi = threading.Event()

    def __init__(self, indeks, *a, **k):
        with type(self).kilit:
            bekle = type(self).acilis_sirasi.pop(0) if type(self).acilis_sirasi else type(self).acilis_sn
        type(self).acilisa_girdi.set()
        time.sleep(bekle)
        self._acik = True
        with type(self).kilit:
            type(self).olusan += 1
            type(self).acik += 1
            type(self).en_cok_acik = max(type(self).en_cok_acik, type(self).acik)

    def isOpened(self):
        return self._acik

    def set(self, *a):
        return True

    def get(self, prop):
        return {3: 1920.0, 4: 1080.0}.get(int(prop), 0.0)

    def read(self):
        time.sleep(0.01)
        return True, np.full((1080, 1920, 3), 90, dtype=np.uint8)

    def release(self):
        with type(self).kilit:
            if self._acik:
                self._acik = False
                type(self).acik -= 1


@pytest.fixture
def kk(monkeypatch):
    import cv2
    from utils import kabin_kamerasi as kk

    _Kamera.sifirla()
    monkeypatch.setattr(cv2, "VideoCapture", _Kamera)
    monkeypatch.setenv("PEMF_KABIN_KAMERASI", "1")
    kk.canli_durdur()
    yield kk
    kk.canli_durdur(bekle_sn=5.0)


def _bekle(kosul, sure=5.0):
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.02)
    return kosul()


def test_KRITIK_canli_ACILIRKEN_AI_Pro_kamera_ac_canliyi_KAPATIR_iki_kamera_ACIK_kalmaz(kk):
    _Kamera.acilis_sn = 0.6
    t = threading.Thread(target=kk.canli_baslat, daemon=True)
    t.start()
    assert _Kamera.acilisa_girdi.wait(5), (
        "aparat: canlı başlatma kamerayı açmaya başlamadı"
    )  # açıyor, henüz kayıtlı değil
    cap, _ = kk.kamera_ac()
    t.join(5)
    try:
        assert not kk.canli_acik(), "AI Pro kamerayı açtıktan SONRA canlı oturum da AÇIK — iki okuyucu aynı kamerada"
        assert _Kamera.en_cok_acik == 1, f"aynı anda {_Kamera.en_cok_acik} VideoCapture açık"
    finally:
        cap.release()


def test_KRITIK_canli_baslat_AI_Pro_mesgulu_KILIT_ALTINDA_yeniden_sorar(kk):
    with pytest.raises(getattr(kk, "KameraMesgul", TypeError)):
        kk.canli_baslat(mesgul=lambda: True)
    assert _Kamera.olusan == 0 and not kk.canli_acik()
    assert kk.canli_baslat(mesgul=lambda: False) is not None  # KARŞIT


def test_KRITIK_canli_baslat_ucu_AI_Pro_girisi_SONRASI_devralirsa_409(kk, monkeypatch):
    """Uç girişte AI Pro meşgul değil; kamera açılışı beklerken AI Pro hazırlığı başlar → canlı açılmamalı (409)."""
    import servers.ai_router as air
    import servers.api_server as apis
    import servers.settings_router as sr
    from fastapi.testclient import TestClient

    cagri = {"n": 0}

    def _mesgul():
        cagri["n"] += 1
        return cagri["n"] > 1  # ilk (giriş) denetimi geçer, sonraki (kilit altı) AI Pro'yu görür

    monkeypatch.setattr(sr, "_ai_kamerasi_mesgul", _mesgul)
    monkeypatch.setattr(air, "_ai_hazirlik_active", False)
    r = TestClient(apis.app).post("/api/settings/kabin-kamerasi/canli/baslat")
    assert r.status_code == 409, (r.status_code, r.text[:200])
    assert not kk.canli_acik() and _Kamera.olusan == 0


def test_KRITIK_eszamanli_FOTOGRAF_CEK_ve_TARAMA_tek_VideoCapture(kk):
    _Kamera.acilis_sn = 0.3
    isler = [threading.Thread(target=kk.kare_al, daemon=True) for _ in range(3)]
    isler += [threading.Thread(target=kk.kameralari_tara, kwargs={"sayi": 2}, daemon=True) for _ in range(2)]
    for t in isler:
        t.start()
    for t in isler:
        t.join(20)
    assert _Kamera.en_cok_acik == 1, f"eşzamanlı tek kare / tarama aynı anda {_Kamera.en_cok_acik} VideoCapture açtı"
    assert _Kamera.acik == 0


def test_KARSIT_canli_acikken_kare_al_canli_kareyi_kullanir(kk):
    assert kk.canli_baslat() is not None
    assert _bekle(lambda: (kk.canli_kare() or {}).get("hazir"))
    n = _Kamera.olusan
    assert kk.kare_al()["genislik"] == 1920
    assert _Kamera.olusan == n


def test_KRITIK_AI_Pro_kamera_ac_ASILI_canli_acilisini_SINIRLI_bekler(kk, monkeypatch):
    """Canlının açılışı asılırsa (sürücü) AI Pro hazırlık / seans döngüsünün `kamera_ac`ı süresiz beklemez: `KAMERA_DEVIR_BEKLE_SN`
    dolunca eski davranışla (kilitsiz) devralır. (Bu patolojik kolda iki `VideoCapture` olabilir — süresiz bekleyen seans döngüsünden iyidir.)"""
    monkeypatch.setattr(kk, "KAMERA_DEVIR_BEKLE_SN", 0.3)
    _Kamera.sifirla(sira=(3.0,))  # 1. açılış (canlı) 3 sn asılı; AI Pro'nunki hızlı
    t = threading.Thread(target=kk.canli_baslat, daemon=True)
    t.start()
    assert _Kamera.acilisa_girdi.wait(5), "aparat: canlı başlatma kamerayı açmaya başlamadı"
    t0 = time.monotonic()
    cap, _ = kk.kamera_ac()
    sure = time.monotonic() - t0
    try:
        assert sure < 1.5, f"AI Pro kamera_ac asılı canlı açılışını {sure:.2f} sn bekledi (sınır 0,3 sn)"
        assert cap.isOpened()
    finally:
        cap.release()
        t.join(10)
        kk.canli_durdur(bekle_sn=5.0)
