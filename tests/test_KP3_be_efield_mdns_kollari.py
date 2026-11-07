# -*- coding: utf-8 -*-
"""KP-3 C · `servers/efield_live.py` + `servers/auto_discovery.py` kapsanmayan kolları — her test bir DAVRANIŞ iddiası. ⚠️ AĞ YOK:
zeroconf / soket EN ALT katta sahtelenir (çok noktaya yayın yapılmaz, 8.8.8.8'e UDP bağlanılmaz).

E-alanı (canlı bar — kıskaç/tavan DEĞİL, yalnız gösterim):
- Eğitim aralığı okunamazsa uyarı + None (ve önbelleğe alınır — her tikte yeniden denenmez); aralık bilinmiyorsa E HESAPLANMAZ
  (`egitimAraligiBilinmiyor`); vekil yoksa / tahmin patlarsa None.
- Vekil yüklenemezse neden ("hata": depo paketi kırık) saklanır, canlı bar kapalı kalır; neden modele göre sorgulanır.
- Döngü hatası döngüyü düşürmez (DEBUG günlüğü).
mDNS:
- Cihaz kimliği / makine adı okunamazsa servis adı taban ada düşer; UDP rota IP'si LAN ise o, değilse LAN adayı, o da patlarsa 127.0.0.1.
- Başlatma hatası → False + uyarı (istisna sızmaz); yeniden kayıt hatası yalnız uyarı; durdurmada kayıt silinemese de durum temizlenir.
"""

from __future__ import annotations

import logging
import sys
import types

import pytest
from servers import auto_discovery as ad
from servers import efield_live as el


class _Dur(BaseException):
    """Sonsuz döngüyü ilk turdan sonra kesmek için (Exception DEĞİL — döngünün `except Exception`ı yakalamaz)."""


def test_egitim_araligi_okunamazsa_none_ve_onbellege_alinir(monkeypatch, caplog):
    sayac = {"n": 0}

    def _patla():
        sayac["n"] += 1
        raise KeyError("background")

    sahte = types.SimpleNamespace(xai_ref_stats=_patla)
    import ai_hub.inference_em_fantom as paket

    monkeypatch.setattr(paket, "inference_em_fantom", sahte, raising=False)
    monkeypatch.setitem(sys.modules, "ai_hub.inference_em_fantom.inference_em_fantom", sahte)
    monkeypatch.setattr(el, "_aralik", {})
    with caplog.at_level(logging.WARNING, logger=el.logger.name):
        assert el.egitim_b_araligi_T("fantom") is None
        assert el.egitim_b_araligi_T("fantom") is None
    assert sayac["n"] == 1, "okunamayan aralık her çağrıda yeniden denendi"
    assert any("eğitim B aralığı okunamadı" in r.getMessage() for r in caplog.records)


def test_aralik_bilinmiyorsa_e_hesaplanmaz_vekil_yok_ya_da_patlarsa_none(monkeypatch):
    monkeypatch.setattr(el, "get_context", lambda: {"model": "fantom", "x": 0, "y": 0, "z": 0, "organ_id": 1})
    monkeypatch.setattr(el, "telemetry_inputs", lambda coils: (0.004, 0.5, 2))
    monkeypatch.setattr(el, "egitim_b_araligi_T", lambda model=None: None)
    d = el.compute([{"id": 1}])
    assert d["egitimAraligiBilinmiyor"] is True and d["healthy"] is None
    monkeypatch.setattr(el, "egitim_b_araligi_T", lambda model=None: (0.0, 1.0))
    monkeypatch.setattr(el, "_predictor", lambda model=None: None)
    assert el.compute([{"id": 1}]) is None

    class _Patlayan:
        def predict(self, *a):
            raise RuntimeError("onnx oturumu kapandı")

    monkeypatch.setattr(el, "_predictor", lambda model=None: _Patlayan())
    assert el.compute([{"id": 1}]) is None


def test_vekil_yuklenemezse_neden_saklanir(monkeypatch, caplog):
    monkeypatch.setattr(el, "_pred", {})
    monkeypatch.setattr(el, "_pred_neden", {})
    monkeypatch.setitem(sys.modules, "ai_hub.inference_em_petri.inference_em_petri", None)
    with caplog.at_level(logging.WARNING, logger=el.logger.name):
        assert el._predictor("petri") is None
    assert el.vekil_yuklenemedi_nedeni("Petri ") == "hata"  # depo paketi (ai_hub) kırık = "hata", ağırlık yok DEĞİL
    assert el.vekil_yuklenemedi_nedeni("fantom") is None
    assert el._pred["petri"] is False, "başarısız yükleme önbelleğe alınmadı (her tikte yeniden denenir)"
    assert any("vekil modeli yüklenemedi (hata)" in r.getMessage() for r in caplog.records)


def test_dongu_hatasi_donguyu_dusurmez(monkeypatch, caplog):
    yakalanan: dict = {}

    class _Is:
        def __init__(self, target=None, **k):
            yakalanan["hedef"] = target

        def start(self):
            pass

    def _uyu(s):
        raise _Dur()

    monkeypatch.setattr(el, "threading", types.SimpleNamespace(Thread=_Is))
    monkeypatch.setattr(el, "time", types.SimpleNamespace(sleep=_uyu, time=lambda: 0.0))

    def _patla():
        raise RuntimeError("seans durumu okunamadı")

    el.start_loop(lambda: [], _patla)
    with caplog.at_level(logging.DEBUG, logger=el.logger.name), pytest.raises(_Dur):
        yakalanan["hedef"]()
    assert any("E-alanı döngü hatası" in r.getMessage() for r in caplog.records)


# ── auto_discovery ────────────────────────────────────────────────────────────────────────────────────────────────────
class _UdpSoket:
    def __init__(self, ip=None):
        self.ip = ip

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def connect(self, adres):
        if self.ip is None:
            raise OSError("ağ erişilemez")

    def getsockname(self):
        return (self.ip, 50000)


def _soket_modulu(ip=None, ad_hatasi=False):
    def _ad():
        if ad_hatasi:
            raise OSError("makine adı okunamadı")
        return "klinik-pc"

    return types.SimpleNamespace(AF_INET=2, SOCK_DGRAM=2, socket=lambda *a: _UdpSoket(ip), gethostname=_ad)


def test_mdns_adi_kimlik_ve_makine_adi_okunamazsa_taban(monkeypatch):
    from utils import path_utils

    def _patla():
        raise OSError("kimlik dosyası yok")

    monkeypatch.setenv("PEMF_DEVICE_NAME", "x")
    monkeypatch.delenv("PEMF_DEVICE_NAME")
    monkeypatch.setattr(path_utils, "get_unique_device_id", _patla)
    monkeypatch.setattr(ad, "socket", _soket_modulu(ad_hatasi=True))
    assert ad._mdns_ad("PEMF-Vet") == "PEMF-Vet"


def test_yerel_ip_lan_rota_aday_ve_geri_donus(monkeypatch):
    from utils import zeroconf_singleton as zs

    monkeypatch.setattr(ad, "socket", _soket_modulu(ip="192.168.4.20"))
    assert ad._get_local_ip() == "192.168.4.20"

    def _patla():
        raise OSError("arayüzler okunamadı")

    monkeypatch.setattr(ad, "socket", _soket_modulu(ip=None))
    monkeypatch.setattr(zs, "_real_lan_ipv4s", _patla)
    assert ad._get_local_ip() == "127.0.0.1"


@pytest.fixture
def mdns_durumu(monkeypatch):
    for ad_ in ("_zeroconf_instance", "_mdns_service_info", "_mdns_started", "_mdns_port", "_mdns_device_name"):
        monkeypatch.setattr(ad, ad_, getattr(ad, ad_))
    return ad


def test_mdns_baslatma_ve_yeniden_kayit_hatasi_firlatmaz(mdns_durumu, monkeypatch, caplog):
    from utils import zeroconf_singleton as zs

    def _patla(*a, **k):
        raise RuntimeError("zeroconf soketi açılamadı")

    monkeypatch.setattr(ad, "_get_local_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(zs, "get_shared_zeroconf", _patla)
    with caplog.at_level(logging.WARNING, logger=ad.logger.name):
        assert ad.start_mdns(18000, "PEMF-Vet") is False
        monkeypatch.setattr(ad, "_mdns_started", True)
        monkeypatch.setattr(ad, "_get_local_ip", lambda: "192.168.4.20")
        ad._reregister()
    mesajlar = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("mDNS başlatılamadı: RuntimeError") for m in mesajlar)
    assert any(m.startswith("_pemfvet re-register hatası: RuntimeError") for m in mesajlar)


def test_mdns_durdurma_kayit_silinemese_de_durum_temizlenir(mdns_durumu, monkeypatch):
    class _Zc:
        def unregister_service(self, info):
            raise OSError("arayüz kapandı")

    monkeypatch.setattr(ad, "_zeroconf_instance", _Zc())
    monkeypatch.setattr(ad, "_mdns_service_info", object())
    monkeypatch.setattr(ad, "_mdns_started", True)
    ad.stop_mdns()
    assert ad._zeroconf_instance is None and ad._mdns_service_info is None and ad._mdns_started is False
