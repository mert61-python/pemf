# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) A2 — canlı alan: hesapçı (`servers/canli_alan_hesapci.py`, AYRI SÜREÇTE koşar) + ana sunucu tarafı (`servers/canli_alan.py`
abonelik + 1 Hz döngü).

SÖZLEŞME:
  - Izgara cam İÇİ, 20 mm, merkezli; en alt katman taban camının 5 mm üstü (plaka sıvı ortası). Tablo dışı nokta = 255 (gösterilmez).
  - Değer = kod × ölçek (mT); en büyük kod 254; kalibrasyon / tablo yok → eylem kodlu durum, ÇÖKME YOK.
  - Hesap = ürünün alan modeli: tek frekansta `td_tepe_faz` ile, farklı frekansta `ortak_dalga` ile AYNI (8 bit yuvarlamasıyla).
  - Bobinler + kalibrasyon DEĞİŞMEDİYSE hesap yok (son sonuç); değişince / kalibrasyon değişince yeniden.
  - Ana sunucu: çalışan bobin yok → `sifir` (hesap / alt süreç HİÇ çağrılmaz); hesap yanıt vermezse `hata`; döngü YALNIZ abone varken,
    son abone gidince biter ve hesabı (alt süreç) KAPATIR; hesap / gönderim / okuma hatası döngüyü düşürmez.
Sentetik tablo + izlenen örnek kalibrasyon (CI'da da koşar)."""

from __future__ import annotations

import base64
import io
import json
import threading
import time

import canli_alan_aparati as ap
import numpy as np
import pytest


@pytest.fixture(scope="module")
def modeller():
    T = ap.tablo()
    K = ap.kalibrasyon()
    onbellek = {}

    def saglayici(f):
        if f not in onbellek:
            onbellek[f] = ap.model(f, K=K, T=T)
        return onbellek[f]

    return saglayici


def _istek(bobinler):
    return {"bobinler": [list(b) for b in bobinler]}


def _coz(veri):
    return np.frombuffer(base64.b64decode(veri["deger"]), dtype=np.uint8)


# ── hesapçı (alt süreç tarafı) ───────────────────────────────────────────────────────────────────────
def test_KRITIK_GA_A2_izgara_CAM_ICI_merkezli_20mm_alt_katman_PLAKA():
    from servers.canli_alan_hesapci import ADIM_MM, izgara

    kok, boyut, P = izgara([555.0, 350.0, 405.0])
    assert ADIM_MM == 20.0
    assert list(boyut) == [28, 18, 21] and len(P) == 28 * 18 * 21 == 10584
    assert np.allclose(kok, [-270.0, -170.0, -200.0])
    assert np.all(np.abs(P) <= np.array([277.5, 175.0, 202.5]))  # hepsi cam içinde
    assert np.isclose(P[:, 1].min(), -175.0 + 5.0)  # taban camı (−175) + plaka sıvı ortası 5 mm
    assert np.allclose(P.mean(axis=0), 0.0)  # merkezli
    assert np.allclose(P[0], kok) and np.allclose(P[1] - P[0], [0, 0, 20.0])  # C sırası x-y-z


def test_KRITIK_GA_A2_kodla_8bit_OLCEK_ve_TABLO_DISI_255():
    from servers.canli_alan_hesapci import KADEME, YOK, kodla

    tepe = np.array([0.0, 0.5, 1.0, 2.54, 7.0])
    ic = np.array([True, True, True, True, False])
    deger, olcek = kodla(tepe, ic)
    kod = np.frombuffer(base64.b64decode(deger), dtype=np.uint8)
    assert KADEME == 254 and YOK == 255
    assert np.isclose(olcek, 2.54 / 254)
    assert list(kod) == [0, 50, 100, 254, 255]  # tablo dışı (7,0) EN BÜYÜĞÜ etkilemez
    assert np.all(np.abs(kod[:4] * olcek - tepe[:4]) <= olcek / 2 + 1e-12)
    deger0, olcek0 = kodla(np.zeros(3), np.array([True, False, True]))
    assert olcek0 == 0.0 and list(np.frombuffer(base64.b64decode(deger0), dtype=np.uint8)) == [0, 255, 0]
    assert kodla(np.ones(2), np.array([False, False]))[1] == 0.0


def test_KRITIK_GA_A2_hesap_URUN_MODELIYLE_ayni_ve_ileti_ALANLARI(modeller):
    from servers.canli_alan_hesapci import Hesapci, izgara, tablo_icinde

    h = Hesapci(modeller)
    v = h.isle(_istek([(1, 100.0, 0.5, 0.0), (3, 100.0, 0.25, 180.0), (7, 100.0, 0.4, 90.0)]))
    A = modeller(100.0)
    assert v["durum"] == "tamam" and v["modelTahmini"] is True and v["surum"] == 1
    assert v["kalibrasyon"] == A.kimlik
    assert v["izgara"] == {
        "kok": [-270.0, -170.0, -200.0],
        "adim": 20.0,
        "boyut": [28, 18, 21],
        "cerceve": "kabin",
        "camIc": [555.0, 350.0, 405.0],
    }
    assert v["yok"] == 255 and v["uyarilar"] == [] and v["hesapMs"] >= 0
    assert v["bobinler"] == [
        {"bobin": 1, "frekans": 100.0, "duty": 0.5, "faz": 0.0},
        {"bobin": 3, "frekans": 100.0, "duty": 0.25, "faz": 180.0},
        {"bobin": 7, "frekans": 100.0, "duty": 0.4, "faz": 90.0},
    ]
    json.dumps(v)  # ileti JSON'a serileşir
    _, _, P = izgara(A.cam)
    ic = tablo_icinde(A, P)
    assert 0 < ic.sum() < len(P)  # sentetik tablo +Y kenarını örtmez → tablo dışı nokta VAR
    beklenen = A.td_tepe_faz(
        A.alan(P[ic]), np.array([0.5, 0, 0.25, 0, 0, 0, 0.4]), np.array([0, 0, 180.0, 0, 0, 0, 90.0])
    )
    kod = _coz(v)
    assert np.all(kod[~ic] == 255) and np.all(kod[ic] <= 254)
    assert np.max(np.abs(kod[ic] * v["olcek"] - beklenen)) <= v["olcek"] / 2 + 1e-6
    i = int(np.argmax(beklenen))
    assert np.isclose(v["enYuksek"]["mT"], beklenen[i], atol=1e-4)
    assert v["enYuksek"]["konum"] == [round(float(x), 1) for x in P[ic][i]]


def test_KRITIK_GA_A2_farkli_frekans_ORTAK_PENCERE_ve_UYARILAR(modeller):
    from servers.canli_alan_hesapci import Hesapci, izgara, tablo_icinde

    from ai_hub.odak.alan import ortak_dalga, td_tepe_dalga

    h = Hesapci(modeller)
    v = h.isle(_istek([(b, 100.0 if b <= 4 else 107.0, 0.3 + 0.05 * b, 30.0 * b) for b in range(1, 8)]))
    assert v["durum"] == "tamam"
    assert v["uyarilar"] == ["dutyKirpildi"]  # bobin 5–7 duty > 0,5 (model 0,5'e kadar ölçülü)
    A, A107 = modeller(100.0), modeller(107.0)
    _, _, P = izgara(A.cam)
    ic = tablo_icinde(A, P)
    duty = np.array([0.3 + 0.05 * b for b in range(1, 8)])
    faz = np.array([30.0 * b for b in range(1, 8)])
    g = np.array([1, 1, 1, 1, 0, 0, 0.0])
    W = ortak_dalga([(100.0, A.td_dalga_faz(duty * g, faz)), (107.0, A107.td_dalga_faz(duty * (1 - g), faz))])
    beklenen = td_tepe_dalga(A.alan(P[ic]), W)
    assert np.max(np.abs(_coz(v)[ic] * v["olcek"] - beklenen)) <= v["olcek"] / 2 + 1e-6
    assert h.isle(_istek([(1, 200.0, 0.3, 0.0)]))["uyarilar"] == ["frekansKalibrasyonDisi"]  # 76–147 Hz dışı
    assert h.isle(_istek([(1, 50.0, 0.3, 0.0)]))["uyarilar"] == ["frekansKalibrasyonDisi"]


def test_KRITIK_GA_A2_DEGISMEDIYSE_hesap_YOK_degisince_YENIDEN(modeller):
    from servers.canli_alan_hesapci import Hesapci

    cagri = []

    def saglayici(f):
        cagri.append(f)
        return modeller(f)

    h = Hesapci(saglayici)
    v1 = h.isle(_istek([(2, 100.0, 0.3, 0.0)]))
    assert h.isle(_istek([(2, 100.0, 0.3, 0.0)])) is v1  # aynı nesne: yeniden hesap YOK
    v3 = h.isle(_istek([(2, 100.0, 0.35, 0.0)]))
    assert v3 is not v1 and v3["bobinler"][0]["duty"] == 0.35
    assert len(cagri) == 3  # kalibrasyon her istekte veri kökünden okunur (değişirse yakalanır)


def test_KRITIK_GA_A2_KALIBRASYON_degisince_izgara_YENIDEN(modeller):
    from servers.canli_alan_hesapci import Hesapci

    K2 = ap.kalibrasyon()
    K2["kazanc"] = [v * 1.5 for v in K2["kazanc"]]
    A2 = ap.model(100.0, K=K2, T=ap.tablo())
    hangi = {"A": modeller(100.0)}
    h = Hesapci(lambda f: hangi["A"])
    v1 = h.isle(_istek([(1, 100.0, 0.5, 0.0)]))
    hangi["A"] = A2
    v2 = h.isle(_istek([(1, 100.0, 0.5, 0.0)]))
    assert v2["kalibrasyon"] == A2.kimlik != v1["kalibrasyon"]
    assert np.isclose(v2["enYuksek"]["mT"], 1.5 * v1["enYuksek"]["mT"], rtol=1e-3)


@pytest.mark.parametrize(
    "hata,kod",
    [("kal", "kalibrasyonYok"), ("eski", "kalibrasyonEski"), ("dosya", "modelYok"), ("butunluk", "modelBozuk")],
)
def test_KRITIK_GA_A2_kalibrasyon_TABLO_yok_EYLEM_KODU_cokme_yok(hata, kod):
    from servers.canli_alan_hesapci import Hesapci
    from utils.model_downloader import ModelButunlukHatasi

    from ai_hub.odak.alan import KalibrasyonHatasi

    def saglayici(f):
        raise {
            "kal": KalibrasyonHatasi("kalibrasyonYok", "yol"),
            "eski": KalibrasyonHatasi("kalibrasyonEski"),
            "dosya": FileNotFoundError("alan_tablosu.npz"),
            "butunluk": ModelButunlukHatasi("alan_tablosu.npz", "özet tutmuyor"),
        }[hata]

    v = Hesapci(saglayici).isle(_istek([(1, 100.0, 0.5, 0.0)]))
    assert v["durum"] == kod and v["modelTahmini"] is True and "deger" not in v


def test_KRITIK_GA_A2_VARSAYILAN_model_VERI_KOKUNDEN_kalibrasyonsuz_EYLEM(tmp_path, monkeypatch):
    from servers import canli_alan_hesapci
    from utils import path_utils

    monkeypatch.setattr(path_utils, "get_app_data_directory", lambda: str(tmp_path))
    assert canli_alan_hesapci.Hesapci().isle(_istek([(1, 100.0, 0.5, 0.0)]))["durum"] == "kalibrasyonYok"


def test_KRITIK_GA_A2_hesapci_ALT_SUREC_girisi_JSON_satirlari(tmp_path, monkeypatch):
    """`main` (alt sürecin girişi): her satır bir istek, her yanıt bir satır; bozuk istek döngüyü düşürmez; çıktı akışı korunur
    (`sys.stdout` stderr'e yönlenir — kütüphane `print`i protokolü bozamaz)."""
    import sys

    from servers import canli_alan_hesapci
    from utils import path_utils

    monkeypatch.setattr(path_utils, "get_app_data_directory", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdout", sys.stdout)  # main stdout'u yönlendirir — test sonunda geri gelsin
    girdi = io.StringIO('{"bobinler": [[1, 100.0, 0.5, 0.0]]}\n\nbozuk\n{"bobinler": "x"}\n')
    cikti = io.StringIO()
    assert canli_alan_hesapci.main([], girdi, cikti) == 0
    yanit = [json.loads(s) for s in cikti.getvalue().splitlines()]
    assert yanit[0]["durum"] == "kalibrasyonYok"
    assert yanit[1] == {"hata": "bozukIstek"}
    assert yanit[2] == {"hata": "ValueError"}
    assert sys.stdout is sys.stderr


# ── ana sunucu tarafı ────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_GA_A2_calisan_bobin_YOKSA_sifir_HESAP_cagrilmaz_bozuk_girdi_COKERTMEZ():
    from servers.canli_alan import CanliAlan

    cagri = []
    kutu = {"d": {}}
    s = CanliAlan(lambda: kutu["d"], lambda *a: None, hesap=lambda b: cagri.append(b) or {"durum": "tamam"})
    assert s.tur()["durum"] == "sifir"
    kutu["d"] = {1: {"freq": 100.0, "duty": 0.0, "phase": 0.0}}  # çalışıyor ama duty 0 → alan yok
    assert s.tur()["durum"] == "sifir"
    kutu["d"] = {
        "x": {"freq": 100.0, "duty": 0.3, "phase": 0.0},
        2: {"freq": None, "duty": 0.3, "phase": 0.0},
        3: {"duty": 0.3},
        4: {"freq": float("nan"), "duty": 0.3, "phase": 0.0},
        9: {"freq": 100.0, "duty": 0.3, "phase": 0.0},  # STM bobini değil
        5: {"freq": 0.0, "duty": 0.3, "phase": 0.0},
    }
    v = s.tur()
    assert v == {"surum": 1, "durum": "sifir", "zaman": v["zaman"], "modelTahmini": True}
    assert cagri == []  # çalışan bobin yokken alt süreç HİÇ başlamaz

    def _patla():
        raise RuntimeError("donanım yok")

    assert CanliAlan(_patla, lambda *a: None, hesap=lambda b: 1 / 0).tur()["durum"] == "sifir"
    assert CanliAlan(lambda: None, lambda *a: None, hesap=lambda b: 1 / 0).tur()["durum"] == "sifir"


def test_KRITIK_GA_A2_bobinler_NORMALLESIR_yanit_YOKSA_hata():
    from servers.canli_alan import CanliAlan

    giden = []
    yanit = {"v": {"durum": "tamam", "x": 1}}
    s = CanliAlan(
        lambda: {3: {"freq": 100.04, "duty": 0.300004, "phase": 370.0}, "1": {"freq": 107, "duty": 0.5, "phase": -90}},
        lambda *a: None,
        hesap=lambda b: giden.append(b) or yanit["v"],
    )
    assert s.tur() == {"durum": "tamam", "x": 1}
    assert giden[0] == [(1, 107.0, 0.5, 270.0), (3, 100.0, 0.3, 10.0)]  # sıralı, yuvarlanmış, faz mod 360
    for kotu in (None, {"hata": "bozukIstek"}, "metin"):
        yanit["v"] = kotu
        assert s.tur()["durum"] == "hata"


def test_KRITIK_GA_A2_VARSAYILAN_hesap_ALT_SUREC_ilk_turda_kurulur(monkeypatch):
    from servers import alt_surec, canli_alan

    kurulan = []

    class _Surec:
        def __init__(self, komut_satiri, ad):
            kurulan.append((komut_satiri, ad))
            self.kapandi = False

        def istek(self, veri, zaman_asimi):
            kurulan.append((veri, zaman_asimi))
            return {"durum": "tamam"}

        def kapat(self):
            self.kapandi = True

    monkeypatch.setattr(alt_surec, "JsonSatirSureci", _Surec)
    s = canli_alan.CanliAlan(lambda: {1: {"freq": 100.0, "duty": 0.5, "phase": 0.0}}, lambda *a: None)
    assert s._hesap is None  # açılışta alt süreç YOK
    assert s.tur() == {"durum": "tamam"}
    assert kurulan[0] == (alt_surec.komut("canli-alan"), "canli-alan")
    assert kurulan[1] == ({"bobinler": [[1, 100.0, 0.5, 0.0]]}, canli_alan.HESAP_ZAMAN_ASIMI_S)
    s._hesap.kapat()
    assert s._hesap._surec.kapandi


def test_KRITIK_GA_A2_DONGU_yalniz_ABONE_varken_bitince_HESABI_KAPATIR():
    from servers.canli_alan import CanliAlan

    gelen = []
    olay = threading.Event()
    say = {"n": 0, "kapat": 0}

    class _Hesap:
        def __call__(self, b):
            return {"durum": "tamam", "n": len(gelen)}

        def kapat(self):
            say["kapat"] += 1

    def gonder(ileti, alicilar):
        gelen.append((ileti, list(alicilar)))
        olay.set()
        if len(gelen) == 2:
            raise RuntimeError("gönderim hatası")  # döngüyü düşürmez

    def durum():
        say["n"] += 1
        if say["n"] == 3:
            raise RuntimeError("okuma")  # → sifir, döngü sürer
        return {1: {"freq": 100.0, "duty": 0.5, "phase": 0.0}}

    s = CanliAlan(durum, gonder, hesap=_Hesap(), aralik_s=0.01)
    assert s.abone_sayisi() == 0 and s._is is None  # abone yokken iş parçacığı YOK
    ws1, ws2 = object(), object()
    s.abone(ws1, True)
    s.abone(ws1, True)  # ikinci kez eklenmez
    assert s.abone_sayisi() == 1 and s._is is not None and s._is.name == "canli-alan"
    assert olay.wait(5)
    s.abone(ws2, True)
    t0 = time.monotonic()
    while len(gelen) < 6 and time.monotonic() - t0 < 10:
        time.sleep(0.01)
    assert len(gelen) >= 6
    assert gelen[0][0]["type"] == "alan_haritasi" and gelen[0][1] == [ws1]
    assert any(al == [ws1, ws2] for _, al in gelen)
    assert {i["data"]["durum"] for i, _ in gelen} >= {"tamam", "sifir"}
    s.abone(ws1, False)
    s.abone(ws2, False)
    s.abone(object(), False)  # abone olmayanı çıkarmak zararsız
    is_ = s._is
    if is_ is not None:
        is_.join(5)
    assert s.abone_sayisi() == 0 and s._is is None
    assert say["kapat"] == 1  # son abone gidince alt süreç kapandı
    olay.clear()
    s.abone(ws1, True)  # yeniden abone → yeni iş parçacığı
    assert olay.wait(5)
    s.abone(ws1, False)


def test_KRITIK_GA_A2_DONGU_hesap_istisnasi_HATA_durumu_kapatsiz_hesap():
    from servers.canli_alan import CanliAlan

    gelen = []
    olay = threading.Event()

    def gonder(ileti, alicilar):
        gelen.append(ileti)
        olay.set()

    s = CanliAlan(lambda: {1: {"freq": 100.0, "duty": 0.5, "phase": 0.0}}, gonder, hesap=lambda b: 1 / 0, aralik_s=0.01)
    ws = object()
    s.abone(ws, True)
    assert olay.wait(5)
    s.abone(ws, False)
    if s._is is not None:
        s._is.join(5)
    assert gelen[0]["data"]["durum"] == "hata" and gelen[0]["data"]["modelTahmini"] is True
