# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""OYZ (istem 56 AŞAMA 3b-2) — GA canlı alan haritası ODM'nin bobin başına ÖTELEMESİNİ içeren kalibrasyonu kullanır.

GA (canlı alan, `servers/canli_alan_hesapci.py`) ODM'den (`bobin_oteleme_mm`, 18-11 tezgâh ölçümü) ÖNCE yazıldı; birleşimde ikisi de korunur.
SÖZLEŞME:
  - Hesapçının haritası, bobin r için M_r(P) = CST_r(P − Δ_r) alanıyla hesaplanır: yalnız ötelenen bobin sürülürken harita, ÖTELEMESİZ
    modelin P − Δ noktalarındaki alanına eşittir (8 bit yuvarlamasıyla) ve ötelemesiz haritadan belirgin biçimde ayrılır.
  - İletideki kalibrasyon kimliği ötelemeyi taşır (öteleme değişince ızgara / Gram önbelleği yenilenir — bayat harita YOK).
  - Varsayılan sağlayıcı (ürün yolu) ötelemeyi veri kökündeki `kabin_kalibrasyonu/alan_kalibrasyonu.json`'dan okur.
Sentetik tablo + izlenen örnek kalibrasyon (CI'da da koşar)."""

from __future__ import annotations

import base64
import json

import canli_alan_aparati as ap
import numpy as np

#: ODM kalibrasyonu 5a248f7d — bobin 1 ötelemesi (ölçüm çerçevesi: x sağ, y yukarı, z ön), mm
DELTA = np.array([-2.1, 21.8, -13.8])
ISTEK = {"bobinler": [[1, 100.0, 0.5, 0.0]]}


def _K(delta_b1) -> dict:
    K = ap.kalibrasyon()
    ote = np.zeros((7, 3))
    ote[0] = delta_b1
    K["bobin_oteleme_mm"] = ote.tolist()
    return K


def _coz(v) -> np.ndarray:
    return np.frombuffer(base64.b64decode(v["deger"]), dtype=np.uint8)


def test_KRITIK_OYZ_canli_harita_ODM_OTELEMESIYLE_hesaplanir_kimlik_TASIR():
    from servers.canli_alan_hesapci import Hesapci, izgara, tablo_icinde

    from ai_hub.odak.alan import backend_to_olcum

    T = ap.tablo()
    A = ap.model(100.0, K=_K(DELTA), T=T)
    A0 = ap.model(100.0, K=_K([0.0, 0.0, 0.0]), T=T)
    assert np.allclose(A.oteleme[0], DELTA) and not A.oteleme[1:].any() and not A0.oteleme.any()
    assert A.kimlik != A0.kimlik

    v = Hesapci(lambda f: A).isle(ISTEK)
    v0 = Hesapci(lambda f: A0).isle(ISTEK)
    assert v["durum"] == v0["durum"] == "tamam"
    assert v["kalibrasyon"] == A.kimlik and v0["kalibrasyon"] == A0.kimlik

    _, _, P = izgara(A.cam)
    ic = tablo_icinde(A, P)
    duty = np.array([0.5, 0, 0, 0, 0, 0, 0])
    faz = np.zeros(7)
    # bobin 1'in alanı P'de = ötelemesiz modelin (P − Δ)'daki alanı
    beklenen = A0.td_tepe_faz(A0.alan_olcum(backend_to_olcum(P[ic]) - DELTA), duty, faz)
    kod, kod0 = _coz(v), _coz(v0)
    assert np.all(kod[~ic] == 255)
    assert np.max(np.abs(kod[ic] * v["olcek"] - beklenen)) <= v["olcek"] / 2 + 1e-6
    # öteleme haritayı gözle görülür değiştirir (yuvarlama payının çok üstünde)
    fark = np.abs(kod[ic] * v["olcek"] - kod0[ic] * v0["olcek"])
    assert fark.max() > 10 * max(v["olcek"], v0["olcek"])


def test_KRITIK_OYZ_oteleme_DEGISINCE_harita_YENIDEN_bayat_degil():
    from servers.canli_alan_hesapci import Hesapci

    T = ap.tablo()
    hangi = {"A": ap.model(100.0, K=_K([0.0, 0.0, 0.0]), T=T)}
    h = Hesapci(lambda f: hangi["A"])
    v1 = h.isle(ISTEK)
    hangi["A"] = ap.model(100.0, K=_K(DELTA), T=T)
    v2 = h.isle(ISTEK)
    assert v1["durum"] == v2["durum"] == "tamam"
    assert v2["kalibrasyon"] == hangi["A"].kimlik != v1["kalibrasyon"]
    assert v2["deger"] != v1["deger"]


def test_KRITIK_OYZ_VARSAYILAN_saglayici_OTELEMEYI_veri_kokunden_okur(tmp_path, monkeypatch):
    from servers import canli_alan_hesapci
    from utils import path_utils

    from ai_hub.odak import alan as alan_mod
    from ai_hub.odak import oneri

    d = tmp_path / "kabin_kalibrasyonu"
    d.mkdir()
    (d / "alan_kalibrasyonu.json").write_text(json.dumps(_K(DELTA)), encoding="utf-8")
    monkeypatch.setattr(path_utils, "get_app_data_directory", lambda: str(tmp_path))
    T = ap.tablo()
    monkeypatch.setattr(alan_mod, "alan_tablosu", lambda yol=None: T)
    monkeypatch.setattr(oneri, "_SON", {})

    A = canli_alan_hesapci.varsayilan_model(100.0)
    assert np.allclose(A.oteleme[0], DELTA) and not A.oteleme[1:].any()
    v = canli_alan_hesapci.Hesapci().isle(ISTEK)
    assert v["durum"] == "tamam" and v["kalibrasyon"] == A.kimlik
