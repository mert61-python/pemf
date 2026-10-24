# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T3 · Y192 (sahip, 2026-10-24) — canlı kabin kamerası İLK KARE gelmeden "kapalı" sayılıyordu.

İSTEK (sahip, ekran görüntüsü): "canlı kamera çalışmıyor bu makinede, kamera da var hp'nin kendi kamerası ama açmıyor" — uyarı: "Canlı
kamera açık değil. "Canlı Kamera" düğmesiyle yeniden başlatın."
ÖLÇÜLEN (GERÇEK HP kamerası, 85acab5e; görüntü kaydedilmedi): `canli_baslat` 0,28 sn'de AÇIK döner, okuyucunun İLK karesi ~0,5 sn
sonra gelir; arada `canli_kare` None döner → uç bunu 409 "canlı kamera açık değil" yapar → arayüzün önizleme döngüsü (başlatmanın HEMEN
ardından ilk istek) oturumu kapandı sanıp canlıyı DURDURUR. Sahte kamerayla yazılan Y190 testleri kareyi anında verdiği için görmedi.
KAPI: oturum açık ama kare henüz yok → `canli_kare` None DEĞİL `hazir: False` döner (uç 200 "bekliyor", 409 yalnız gerçekten kapalı
oturum); uç ilk kareyi kısa süre BEKLER; tek kare (`kare_al`) canlı açıkken kare gelmediyse canlıyı KAPATMADAN None döner.
Sahte yalnız EN ALT katta: `cv2` (ilk okuması gecikmeli kamera).
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from test_T2D2_kabin_kamerasi_SECIMI_ve_1080p import _SahteCv2, veri  # noqa: F401


class _YavasCv2(_SahteCv2):
    """İlk okuma `gecikme` sn süren kamera (MSMF ısınması gibi; ölçülen HP kamerası ~0,25–0,5 sn)."""

    def __init__(self, gecikme=0.6, **k):
        super().__init__(**k)
        self.gecikme = gecikme

    def VideoCapture(self, i):  # noqa: N802
        cap = super().VideoCapture(i)
        ana = cap.read
        ilk = [True]

        def _oku():
            if ilk[0]:
                ilk[0] = False
                time.sleep(self.gecikme)
            return ana()

        cap.read = _oku
        return cap


@pytest.fixture()
def canli(veri):
    kk, kok = veri
    yield kk, kok
    kk.canli_durdur()


def test_KRITIK_ilk_kare_GELMEDEN_oturum_KAPALI_sayilmaz_hazir_False(canli):
    kk, _ = canli
    cv = _YavasCv2(gecikme=0.6)
    kk.kamera_sec(0)
    assert kk.canli_baslat(cv) == {"indeks": 0, "acik": True}
    k = kk.canli_kare(cv2=cv)  # başlatmanın HEMEN ardından (arayüzün ilk önizleme isteği)
    assert k is not None, "ilk kare gelmeden oturum KAPALI sayıldı (uç 409 → arayüz canlıyı durdurur)"
    assert k["hazir"] is False and "image_base64" not in k and kk.canli_acik(), k
    t = kk.canli_kare(cv2=cv, bekle_sn=3.0)
    assert t["hazir"] is True and (t["genislik"], t["yukseklik"]) == (960, 540) and t["image_base64"], t


def test_KARSIT_oturum_GERCEKTEN_kapaliysa_None(canli):
    kk, _ = canli
    assert kk.canli_kare() is None
    cv = _SahteCv2()
    kk.kamera_sec(0)
    kk.canli_baslat(cv)
    kk.canli_durdur()
    assert kk.canli_kare(cv2=cv, bekle_sn=0.5) is None


def test_KRITIK_tek_kare_CANLI_aciksa_kare_yoksa_canliyi_KAPATMAZ(canli, monkeypatch):
    kk, _ = canli
    monkeypatch.setattr(kk, "CANLI_ILK_KARE_BEKLE_SN", 0.2)
    cv = _YavasCv2(gecikme=1.5)
    kk.kamera_sec(0)
    kk.canli_baslat(cv)
    assert kk.kare_al(cv) is None, "kare yokken uydurma / boş kare döndü"
    assert kk.canli_acik() and cv.acilan == [0], "tek kare canlı oturumu kapattı ya da ikinci kamera açtı"


@pytest.fixture()
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    return TestClient(api_server.app)


def test_KRITIK_uc_hazir_olmayan_karede_200_BEKLIYOR_kapali_oturumda_409(istemci, monkeypatch):
    from utils import kabin_kamerasi as kk

    gelen = []

    def _hazir_degil(tam=False, cv2=None, bekle_sn=0.0):
        gelen.append(bekle_sn)
        return {"indeks": 0, "hazir": False}

    monkeypatch.setattr(kk, "canli_kare", _hazir_degil)
    r = istemci.get("/api/settings/kabin-kamerasi/canli/kare")
    assert r.status_code == 200 and r.json()["status"] == "bekliyor" and r.json()["hazir"] is False, r.text[:200]
    assert gelen and gelen[0] > 0, "uç ilk kareyi hiç BEKLEMİYOR"
    monkeypatch.setattr(kk, "canli_kare", lambda tam=False, cv2=None, bekle_sn=0.0: None)
    assert istemci.get("/api/settings/kabin-kamerasi/canli/kare").status_code == 409  # KARŞIT


def test_KARSIT_hazir_karede_eski_yanit_AYNI(istemci, monkeypatch):
    from utils import kabin_kamerasi as kk

    monkeypatch.setattr(
        kk,
        "canli_kare",
        lambda tam=False, cv2=None, bekle_sn=0.0: {
            "indeks": 0,
            "hazir": True,
            "genislik": 960,
            "yukseklik": 540,
            "yas_ms": 3,
            "image_base64": "QQ==",
        },
    )
    j = istemci.get("/api/settings/kabin-kamerasi/canli/kare").json()
    assert j["status"] == "success" and j["image_base64"] == "QQ==" and j["genislik"] == 960


def test_sahte_kamera_aparati_GERCEKTEN_gecikir():
    cv = _YavasCv2(gecikme=0.3)
    cap = cv.VideoCapture(0)
    t = time.monotonic()
    ok, k = cap.read()
    assert ok and time.monotonic() - t >= 0.25 and isinstance(k, np.ndarray)
