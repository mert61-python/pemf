# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/servers/ai_router.py · sözleşmeler: içe aktarmada depo kökü sys.path'e eklenir; seans döngüsünde
hedef-kaybı STOP'u hata verirse döngü ölmez; `/frame` aktif-seans denetimi hata verirse bobin SÜRÜLMEZ (fail-closed).

- İçe aktarma: depo kökü (`kaynak_kokunu_bul`) `sys.path`te YOKSA listenin BAŞINA eklenir; varsa ikinci kez eklenmez. Modül
  gövdesi aynı dosya yolundan AYRI bir ad altında (ikiz) yürütülür — gerçek `servers.ai_router` girdisine dokunulmaz.
- Seans döngüsü: hedef her turda kayıp (lokalizasyon hatası); 3. ve 4. turdaki STOP'ta donanım çekirdeği okunamaz (STOP
  yardımcısı yükselir) → hata KENDİ dalında yutulur ("hedef-kayip STOP hatasi"), tur hatası sayılmaz, döngü sürer; hiçbir
  bobin START almaz; kapanışta STM stop_all yine gider, seans pasife alınır, kamera bırakılır.
- `/frame`: mühürlü seans + hedef bulundu iken aktif-seans denetiminde saat okunamazsa → sessionActive=False, driven=False,
  doz modeli çağrılmaz, hiçbir bobin START almaz (karşıt: saat sağlamken aynı kare 7 bobini sürer).

Sahte EN ALT katta: kamera (`cv2.VideoCapture`), saat (`ai_router.time` modül-yerel ad alanı), donanım kontrolcüsü (kayıtçı;
çekirdek özelliği yükselir), lokalizasyon sağlayıcısı (`KediSaglayici.localize`/`yukle`). Aparat: `tests/ai_pro_aparati.kur`.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import time
import types

import ai_pro_aparati as ap
import numpy as np
import pytest
from servers import ai_router as air

_GERCEK_LOKALIZE = air._localize_organ
_GERCEK_TAHMIN = air._predict_and_drive


# ───────────────────────────── içe aktarma: depo kökü sys.path ─────────────────────────────


def _ikiz_yukle(ad):
    """ai_router.py'yi AYNI dosya yolundan ayrı bir modül adıyla yürütür (sys.modules'a eklemez, gerçek girdiye dokunmaz)."""
    spec = importlib.util.spec_from_file_location(ad, air.__file__)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ice_aktarma_depo_KOKU_sys_pathte_YOKSA_BASA_eklenir_VARSA_ikinci_kez_eklenmez(monkeypatch):
    """sys.path'ten depo kökü çıkarılmış → modül gövdesi kökü listenin BAŞINA ekler (kök = ai_router'ın gördüğü depo kökü);
    kök zaten varken yeniden yürütme onu İKİNCİ kez eklemez (tek girdi kalır)."""
    kok = air.project_root
    assert kok and kok != air.current_dir
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != kok])
    assert kok not in sys.path
    ikiz = _ikiz_yukle("kp_ai_router_ikiz_a")
    assert ikiz.project_root == kok
    assert sys.path[0] == kok
    assert sys.path.count(kok) == 1
    # kök artık var → ikinci yürütme eklemez
    _ikiz_yukle("kp_ai_router_ikiz_b")
    assert sys.path.count(kok) == 1 and sys.path[0] == kok


# ───────────────────────────── seans döngüsü: hedef-kaybı STOP hatası ─────────────────────────────


class _Kamera:
    """Sahte kabin kamerası: `kareler` sırayla okunur (None = okunamadı)."""

    def __init__(self, kareler):
        self.kareler = list(kareler)
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
        return (kare is not None), kare

    def release(self):
        self.birakildi = True


class _CekirdegiKirikDonanim:
    """Kayıtçı donanım: `core` özelliği okunurken yükselir (seri çekirdek yeniden başlatılırken); bobin komutları kaydedilir."""

    def __init__(self):
        self.cagri = []
        self.stop_all = 0
        self.core_okuma = 0

    @property
    def core(self):
        self.core_okuma += 1
        raise RuntimeError("seri çekirdek yeniden başlatılıyor")

    def update_coil(self, cid, *a, start=True, **k):
        self.cagri.append((cid, start))
        return True

    def calisan_bobin_durumu(self):
        return {}

    def stop_all_coils(self):
        self.stop_all += 1
        return True


@pytest.fixture
def dns(monkeypatch, tmp_path):
    o = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(o.air, "_localize_organ", _GERCEK_LOKALIZE)
    monkeypatch.setattr(o.air, "_predict_and_drive", _GERCEK_TAHMIN)
    try:
        yield o
    finally:
        o.air._ai_loop_active = False
        o.geri()
        o.c.close()


def test_seans_dongusu_hedef_kaybi_STOP_HATASI_kendi_dalinda_yutulur_dongu_SURER_kapanis_STOP_gider(
    dns, monkeypatch, caplog
):
    """4 tur, hedef her turda kayıp; 3. ve 4. turda STOP yardımcısı (donanım çekirdeği okunamaz) yükselir → her biri
    "AI Pro: hedef-kayip STOP hatasi" (RuntimeError) olarak yutulur, "AI Loop iteration error" YOK; 4 tur tamamlanır
    (uyku 4×); hiçbir bobin START almaz; kapanışta stop_all 1×, seans pasif, kamera bırakılır, bayrak iner."""
    from servers import ai_pro_hedef
    from utils import estop_mandali

    hw = _CekirdegiKirikDonanim()
    monkeypatch.setattr(dns.api.state, "hardware", hw)
    ap.muhurlu_seans_yaz(dns.api, onay_hedefi=2)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    lokal = {"n": 0}

    def _lokalize(self, kare, oid):
        lokal["n"] += 1
        raise RuntimeError("pose/PnP çözülemedi")

    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "localize", _lokalize)
    kare = np.zeros((48, 64, 3), np.uint8)
    kamera = _Kamera([kare, kare, kare, kare])
    monkeypatch.setattr(air.cv2, "VideoCapture", lambda indeks, *a: kamera)
    uykular = []

    def _uyu(s):
        uykular.append(round(float(s), 2))
        if len(uykular) >= 4:
            dns.air._ai_loop_active = False

    monkeypatch.setattr(air, "time", types.SimpleNamespace(time=time.time, monotonic=time.monotonic, sleep=_uyu))
    monkeypatch.setattr(
        dns.air, "_ai_organ_cache", {**air._ai_organ_cache, "localized": True, "organ_id": -1, "at": 0.0}
    )
    monkeypatch.setattr(dns.air, "_ai_organ_id", 2)
    monkeypatch.setattr(dns.air, "_ai_relocalize", True)
    monkeypatch.setattr(dns.air, "_ai_hedef_modeli", "kedi")
    monkeypatch.setattr(dns.air, "_ai_duration_min", 5)
    monkeypatch.setattr(dns.air, "_ai_started_at", time.monotonic())
    monkeypatch.setattr(dns.air, "_ai_dongu_no", 51)
    monkeypatch.setattr(dns.air, "_ai_loop_active", True)
    muhur = {"nesil": estop_mandali.nesil(), "onay": "test-onay", "dongu": 51, "hedef": 2}

    with caplog.at_level(logging.ERROR, logger="ai_router"):
        dns.air._ai_pro_loop(muhur)

    stop_hatalari = [r for r in caplog.records if r.getMessage() == "AI Pro: hedef-kayip STOP hatasi"]
    assert len(stop_hatalari) == 2, [r.getMessage() for r in caplog.records]
    for r in stop_hatalari:
        assert r.exc_info and r.exc_info[0] is RuntimeError and "seri çekirdek" in str(r.exc_info[1])
    assert hw.core_okuma == 2
    assert not [r for r in caplog.records if "AI Loop iteration error" in r.getMessage()]
    assert lokal["n"] == 4 and len(uykular) == 4
    assert [c for c, s in hw.cagri if s] == []
    assert hw.stop_all == 1
    assert kamera.birakildi and dns.air._ai_loop_active is False
    with dns.api._session_lock:
        assert dns.api._active_session.get("is_active") is False


# ───────────────────────────── /frame: aktif-seans denetimi hatası ─────────────────────────────


class _CalisanDonanim:
    def __init__(self):
        self.baslat = []

    def update_coil(self, cid, *a, start=True, **k):
        if start:
            self.baslat.append(cid)
        return True

    def calisan_bobin_durumu(self):
        return {}


@pytest.fixture
def fns(monkeypatch, tmp_path):
    o = ap.kur(monkeypatch, tmp_path)
    try:
        yield o
    finally:
        ap.dongu_bitir(o.air)
        o.geri()
        o.c.close()


def _saat_kur(monkeypatch, kirik):
    """`ai_router.time` modül-yerel sahte: `kirik["acik"]` iken `/frame` gövdesinin İLK DOĞRUDAN monotonik saat okuması
    (aktif-seans denetimi) BİR KEZ OSError verir; sonraki okumalar ve yardımcıların okumaları gerçek saat. Hata sayısı `kirik["n"]`."""
    gercek = time.monotonic

    def _mono():
        if kirik["acik"] and sys._getframe(1).f_code.co_name == "ai_pro_frame":
            kirik["acik"] = False
            kirik["n"] += 1
            raise OSError("monotonik saat okunamadı")
        return gercek()

    monkeypatch.setattr(air, "time", types.SimpleNamespace(time=time.time, monotonic=_mono, sleep=time.sleep))


def test_frame_aktif_seans_DENETIMI_HATA_verirse_SURULMEZ_karsit_saglam_saatte_7_bobin(fns, monkeypatch, caplog):
    """Mühürlü seans + taze lokalizasyon (hedef = mühür hedefi): saat sağlamken kare 7 bobini sürer (driven=True);
    aktif-seans denetiminde saat okunamazsa → 200, sessionActive=False, driven=False, doz modeli ÇAĞRILMAZ, START yok,
    "ai_pro_frame: aktif-seans kontrolü hatası" günlüğe düşer."""
    ap.muhurlu_seans_yaz(fns.api)
    hw = _CalisanDonanim()
    monkeypatch.setattr(fns.api.state, "hardware", hw)
    kirik = {"acik": False, "n": 0}
    _saat_kur(monkeypatch, kirik)

    # karşıt: saat sağlam → sürülür
    monkeypatch.setattr(fns.air, "_ai_relocalize", True)
    r0 = ap.kare(fns)
    assert r0.status_code == 200, r0.text[:300]
    assert r0.json()["driven"] is True and r0.json()["sessionActive"] is True
    assert hw.baslat == [1, 2, 3, 4, 5, 6, 7]
    tahmin_once = fns.tahmin.sayi
    assert tahmin_once == 1

    # saat aktif-seans denetiminde okunamaz → fail-closed
    hw.baslat.clear()
    kirik["acik"] = True
    monkeypatch.setattr(fns.air, "_ai_relocalize", True)
    with caplog.at_level(logging.ERROR, logger="ai_router"):
        r = ap.kare(fns)
    assert kirik["n"] == 1
    assert hw.baslat == []
    assert fns.tahmin.sayi == tahmin_once
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["sessionActive"] is False and j["driven"] is False
    assert j["detected"] is True
    kayit = [x for x in caplog.records if x.getMessage() == "ai_pro_frame: aktif-seans kontrolü hatası"]
    assert len(kayit) == 1 and kayit[0].exc_info[0] is OSError
