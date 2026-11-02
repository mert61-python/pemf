# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/servers/ai_router.py · sözleşmeler: AI Pro HAZIRLIK önizleme döngüsü ve SEANS döngüsü (sunucu kamerası).

Döngüler test iş parçacığında EŞZAMANLI koşturulur (iş parçacığı açılmaz); kamera sahte (`cv2.VideoCapture`, gerçek kamera
AÇILMAZ), `ai_router.time` modül-yerel sahte (uyku kaydedilir, gerçek bekleme YOK), sağlayıcı yükleme / lokalizasyon / doz
modeli (`ai_pro_hedef.KediSaglayici`) yamalı; donanım kayıtçı. İddialar:

- hazırlık: kare okunamazsa 0,3 sn bekleyip yeniden okur; lokalizasyon hatası önbelleği GEÇERSİZ kılar; önizleme yayını hata
  verse de döngü ölmez; kamera bırakılır, bayrak iner.
- seans: kabin kamerası SEÇİLMEDİYSE kamera açılmaz, döngü bayrağı iner, kendi seansı pasife alınır.
- seans: kare okunamazsa 0,5 sn bekler; lokalizasyon hatası önbelleği geçersiz kılar; 3 ardışık kayıpta (kayıp nesli artırılamasa
  da) 1-7'ye STOP gider; hedef yeniden bulununca 7 bobin sürülür; overlay yayın karesi ≤ 960 px; WS yayın hatası döngüyü
  öldürmez; döngü sonu STM `stop_all` / ESP STOP yayını / E bağlamı temizliği hata verse de seans pasife alınır.
"""

from __future__ import annotations

import time
import types

import ai_pro_aparati as ap
import numpy as np
import pytest
from servers import ai_router as air

_GERCEK_LOKALIZE = air._localize_organ
_GERCEK_TAHMIN = air._predict_and_drive


class _Kamera:
    """Sahte kabin kamerası: `kareler` sırayla okunur (None = okunamadı); son karede `bitir()` çağrılır."""

    def __init__(self, kareler, bitir):
        self.kareler = list(kareler)
        self.bitir = bitir
        self.okunan = 0
        self.birakildi = False

    def isOpened(self):  # noqa: N802
        return True

    def set(self, *a):
        return True

    def get(self, *a):
        return 0.0

    def read(self):
        self.okunan += 1
        kare = self.kareler.pop(0) if self.kareler else None
        if not self.kareler:
            self.bitir()
        return (kare is not None), kare

    def release(self):
        self.birakildi = True


def _sahte_zaman(monkeypatch, uykular, her_uykuda=None):
    def _uyu(s):
        uykular.append(round(float(s), 2))
        if her_uykuda is not None:
            her_uykuda(len(uykular))

    monkeypatch.setattr(air, "time", types.SimpleNamespace(time=time.time, monotonic=time.monotonic, sleep=_uyu))


def _kamera_kur(monkeypatch, kamera):
    acilan = []

    def _ac(indeks, *a):
        acilan.append(indeks)
        return kamera

    monkeypatch.setattr(air.cv2, "VideoCapture", _ac)
    return acilan


# ───────────────────────────── hazırlık döngüsü ─────────────────────────────


def test_hazirlik_kare_OKUNAMAZSA_bekler_lokalizasyon_HATASI_onbellegi_gecersiz_kilar_yayin_hatasi_OLDURMEZ(
    monkeypatch,
):
    """Kare 1 okunamaz → uyku 0,3; kare 2 lokalizasyon hatası → localized=False; önizleme yayını hata → yutulur; kamera bırakılır."""
    from servers import ai_pro_hedef
    from servers import api_server as api

    def _bitir():
        air._ai_hazirlik_active = False

    kamera = _Kamera([None, np.zeros((48, 64, 3), np.uint8)], _bitir)
    acilan = _kamera_kur(monkeypatch, kamera)
    uykular = []
    _sahte_zaman(monkeypatch, uykular)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)

    def _lokalize(self, kare, oid):
        raise RuntimeError("pose/PnP çözülemedi")

    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "localize", _lokalize)
    yayin = []

    def _yayinla(m):
        yayin.append(m)
        raise RuntimeError("WS kuyruğu dolu")

    monkeypatch.setattr(api, "_ws_broadcast_sync", _yayinla)
    monkeypatch.setattr(air, "_localize_organ", _GERCEK_LOKALIZE)
    monkeypatch.setattr(air, "_ai_organ_cache", {**air._ai_organ_cache, "localized": True, "organ_id": -1, "at": 0.0})
    monkeypatch.setattr(air, "_ai_hazirlik_active", True)
    monkeypatch.setattr(air, "_ai_hazirlik_started_at", 0.0)
    monkeypatch.setattr(air, "_ai_relocalize", True)
    monkeypatch.setattr(air, "_ai_hedef_modeli", "kedi")
    air._ai_hazirlik_loop()
    assert acilan == [0] and kamera.okunan == 2 and kamera.birakildi
    assert uykular == [0.3, 0.05]
    assert air._ai_organ_cache["localized"] is False
    assert len(yayin) == 1 and yayin[0]["data"]["preview"] is True and yayin[0]["data"]["detected"] is False
    assert air._ai_hazirlik_active is False


# ───────────────────────────── seans döngüsü ─────────────────────────────


@pytest.fixture
def ns(monkeypatch, tmp_path):
    o = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(o.air, "_localize_organ", _GERCEK_LOKALIZE)
    monkeypatch.setattr(o.air, "_predict_and_drive", _GERCEK_TAHMIN)
    try:
        yield o
    finally:
        o.air._ai_loop_active = False
        o.geri()
        o.c.close()


def test_seans_kabin_kamerasi_SECILMEDIYSE_kamera_ACILMAZ_bayrak_iner_seans_PASIF(ns, monkeypatch):
    """PEMF_KABIN_KAMERASI yok + ayar dosyası yok → KameraSecilmedi: VideoCapture çağrılmaz, `_ai_loop_active` False, kendi
    seansı (onay test-onay) pasif."""
    from servers import ai_pro_hedef

    monkeypatch.delenv("PEMF_KABIN_KAMERASI", raising=False)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    acilan = _kamera_kur(monkeypatch, None)
    ap.muhurlu_seans_yaz(ns.api)
    monkeypatch.setattr(ns.air, "_ai_dongu_no", 41)
    monkeypatch.setattr(ns.air, "_ai_loop_active", True)
    muhur = {"nesil": ap.mandal_modulu().nesil(), "onay": "test-onay", "dongu": 41, "hedef": 0}
    ns.air._ai_pro_loop(muhur)
    assert acilan == []
    assert ns.air._ai_loop_active is False
    with ns.api._session_lock:
        assert ns.api._active_session.get("is_active") is False


class _DonguDonanimi:
    def __init__(self):
        self.cagri = []
        self.stop_all = 0

    def update_coil(self, cid, *a, start=True, **k):
        self.cagri.append((cid, start))
        return True

    def calisan_bobin_durumu(self):
        return {}

    def stop_all_coils(self):
        self.stop_all += 1
        raise RuntimeError("seri port kapalı")


def test_seans_dongusu_KAYIP_STOP_SURUS_YAYIN_ve_DONGU_SONU_hatalara_dayanikli(ns, monkeypatch):
    """Tur 1 kare yok (uyku 0,5) · tur 2-4 lokalizasyon hatası (önbellek geçersiz; 3. kayıpta kayıp nesli artırılamasa da
    1-7'ye STOP) · tur 5 hedef (organ 2) bulundu → 7 bobin sürülür, 1200×1000 overlay yayın karesi 960×800 · her WS yayını hata
    verir (döngü sürer) · sonda stop_all / ESP STOP / E bağlamı temizliği hata verse de seans pasif, temizlik [] ile denendi."""
    from servers import ai_pro_hedef
    from servers import efield_live as ef
    from utils import estop_mandali

    hw = _DonguDonanimi()
    monkeypatch.setattr(ns.api.state, "hardware", hw)
    ap.muhurlu_seans_yaz(ns.api, onay_hedefi=2)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", lambda self, *a, **k: ([0.3] * 7, [0.0] * 7, 1.0))
    overlay = np.full((1000, 1200, 3), 80, np.uint8)
    lokal = {"n": 0, "onbellek_oncesi": []}

    def _lokalize(self, kare, oid):
        lokal["n"] += 1
        lokal["onbellek_oncesi"].append(air._ai_organ_cache["localized"])
        if lokal["n"] <= 3:
            raise RuntimeError("pose/PnP çözülemedi")
        return True, 10.0, 20.0, 30.0, 0.9, overlay, True, None

    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "localize", _lokalize)

    def _nesil():
        raise RuntimeError("nesil kilidi")

    monkeypatch.setattr(estop_mandali, "kayip_nesli_artir", _nesil)
    yayin = []

    def _yayinla(m):
        yayin.append(m)
        raise RuntimeError("WS kuyruğu dolu")

    monkeypatch.setattr(ns.api, "_ws_broadcast_sync", _yayinla)
    mqtt = []

    def _mqtt(konu, yuk):
        mqtt.append(konu)
        raise OSError("broker soketi kapalı")

    monkeypatch.setattr(ns.api, "_mqtt_publish", _mqtt)

    def _baglam_nesli():
        raise RuntimeError("bağlam nesli okunamadı")

    temizlik = []

    def _set(bolgeler, *a, **k):
        temizlik.append(list(bolgeler))
        raise RuntimeError("E bağlam kilidi")

    monkeypatch.setattr(ef, "baglam_nesli", _baglam_nesli)
    monkeypatch.setattr(ef, "set_context", _set)

    kare = np.zeros((48, 64, 3), np.uint8)
    kamera = _Kamera([None, kare, kare, kare, kare], lambda: None)
    _kamera_kur(monkeypatch, kamera)
    uykular = []

    def _her_uykuda(n):
        if n >= 5:
            ns.air._ai_loop_active = False

    _sahte_zaman(monkeypatch, uykular, _her_uykuda)
    monkeypatch.setattr(
        ns.air, "_ai_organ_cache", {**air._ai_organ_cache, "localized": True, "organ_id": -1, "at": 0.0}
    )
    monkeypatch.setattr(ns.air, "_ai_organ_id", 2)
    monkeypatch.setattr(ns.air, "_ai_relocalize", True)
    monkeypatch.setattr(ns.air, "_ai_hedef_modeli", "kedi")
    monkeypatch.setattr(ns.air, "_ai_duration_min", 5)
    monkeypatch.setattr(ns.air, "_ai_started_at", time.monotonic())
    monkeypatch.setattr(ns.air, "_ai_dongu_no", 42)
    monkeypatch.setattr(ns.air, "_ai_loop_active", True)
    muhur = {"nesil": estop_mandali.nesil(), "onay": "test-onay", "dongu": 42, "hedef": 2}

    ns.air._ai_pro_loop(muhur)

    assert uykular[0] == 0.5 and len(uykular) == 5
    assert lokal["n"] == 4 and lokal["onbellek_oncesi"][1:3] == [False, False]
    stoplar = [c for c, s in hw.cagri if not s]
    baslatma = [c for c, s in hw.cagri if s]
    assert stoplar[:7] == [1, 2, 3, 4, 5, 6, 7], hw.cagri
    assert baslatma == [1, 2, 3, 4, 5, 6, 7]
    assert len(yayin) == 4
    son = yayin[-1]["data"]
    assert (son["imageW"], son["imageH"]) == (960, 800) and son["detected"] is True
    assert hw.stop_all == 1 and mqtt == ["pemf/coil/8/control"]
    # biri canlı durum kapanışı (`api_server.update_live_session_state`), biri döngünün KENDİ teardown temizliği (bağlam nesli yok)
    assert temizlik == [[], []]
    assert kamera.birakildi and ns.air._ai_loop_active is False
    with ns.api._session_lock:
        assert ns.api._active_session.get("is_active") is False


def test_seans_durumu_OKUNAMAZSA_dongu_ve_kapanis_COKMEZ_bayrak_iner_kamera_birakilir(ns, monkeypatch):
    """`_active_session` okunamaz: tur başı seans denetimi hatası yutulur (kare yok → uyku 0,5), döngü bayrağı inince kapanış
    seans adımında hata verir → yutulur; STM stop_all yine denenir, kamera bırakılır, bayrak iner."""
    from servers import ai_pro_hedef
    from utils import estop_mandali

    hw = _DonguDonanimi()
    monkeypatch.setattr(ns.api.state, "hardware", hw)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    kamera = _Kamera([None], lambda: None)
    _kamera_kur(monkeypatch, kamera)
    uykular = []

    def _her_uykuda(n):
        ns.air._ai_loop_active = False

    _sahte_zaman(monkeypatch, uykular, _her_uykuda)
    monkeypatch.setattr(ns.air, "_ai_dongu_no", 43)
    monkeypatch.setattr(ns.air, "_ai_loop_active", True)
    muhur = {"nesil": estop_mandali.nesil(), "onay": "test-onay", "dongu": 43, "hedef": 0}
    eski = ns.api._active_session  # aparat yıkımı monkeypatch'ten ÖNCE koşar → elle geri konur
    ns.api._active_session = None
    try:
        ns.air._ai_pro_loop(muhur)
    finally:
        ns.api._active_session = eski
    assert uykular == [0.5]
    assert hw.stop_all == 1 and kamera.birakildi and ns.air._ai_loop_active is False
