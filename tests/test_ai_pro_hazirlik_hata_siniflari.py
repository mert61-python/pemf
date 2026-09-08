# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO: MODEL YÜKLEME SIRASI + HAZIRLIK HATA SINIFLARI (Faz 1, 2026-09-09).

Üç şeyi kilitler:

1. **Model KAMERADAN ÖNCE yüklenir.** Eskiden `_ai_hazirlik_loop` ve `_ai_pro_loop` önce
   `VideoCapture(0)` açıp SONRA modeli yüklüyordu. Ağır sağlayıcılarda (petri: 239 MB ONNX +
   90 MB YOLO + ısıtma) bu, kameranın yükleme boyunca TUTULMASI demek: araya `/ai/pro/start`
   girerse `_ai_hazirlik_durdur_ic` join'i dolar ve onaylı seans kamerayı alamaz. Yükleme öne
   alınınca kamera tutma süresi model yükünden bağımsız olur.

2. **Seans loop'u başlamadan ölürse oturum PASİFE alınır.** `/ai/pro/start`, `start_ai_session`i
   thread spawn'ından ÖNCE çağırıyor. Loop kamerayı açamazsa `_ai_loop_active=False` yapıp
   dönüyordu ama `_active_session` AI modunda AKTİF kalıyordu → panel ve seans geçmişi seansı
   "sürüyor" gösteriyor, süre-watchdog dolana kadar kapanmıyordu. Bobin sürülmediği için tedavi
   yok; GÖRÜNEN durum ile GERÇEK durum ayrışıyordu.

3. **Hazırlık hataları SINIFLANDIRILIR ve eylem söyler.** Ham istisna metni / `VideoCapture(0)`
   gibi iç ayrıntılar kullanıcıya GİTMEZ (yalnız log'a) — operatöre "yazılımda bug var" izlenimi
   veren metin yerine ne yapacağını söyleyen metin gider (hata-mesajı-eylem-söylesin kuralı).
"""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient


class _AcikCap:
    def isOpened(self):  # noqa: N802  (OpenCV adı)
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        return None


class _KapaliCap:
    def isOpened(self):  # noqa: N802  (OpenCV adı)
        return False

    def release(self):
        return None


@pytest.fixture()
def env(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis

    izler = {"kamera_acildi": 0, "yukleme": 0}

    class _Sag:
        ad = "sahte"
        title = "Sahte Model"
        subject_label = "sahte özne"
        achieved_B = 0.001
        duty_sum = 2.0
        join_timeout_s = 11.0
        varsayilan_hedef = 0
        patlat = None  # istisna örneği ya da None

        def hedef_idleri(self):
            return frozenset({0, 1})

        def yukle(self):
            izler["yukleme"] += 1
            if self.patlat is not None:
                raise self.patlat

        def localize(self, frame_bgr, hedef_id):
            return (False, 0.0, 0.0, 0.0, 0.0, None, False, None)

        def predict(self, x, y, z, hedef_id):
            return [0.1] * 7, [0.0] * 7, 0.1

        def hedef_adi(self, hedef_id):
            return f"Sahte {hedef_id}"

        def ipucu(self, ozne_var, hedef_adi):
            return "sahte ipucu"

        def xai_sensitivity(self, *a, **k):
            return None

    sag = _Sag()
    monkeypatch.setitem(hedef.SAGLAYICILAR, "sahte", sag)

    snap_cache = dict(air._ai_organ_cache)
    snap = (air._ai_hedef_modeli, air._ai_hazirlik_hata, air._ai_hazirlik_hata_kodu, air._ai_organ_id)
    with apis._session_lock:
        sess_snap = dict(apis._active_session)

    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    air._ai_hazirlik_hata = ""
    air._ai_hazirlik_hata_kodu = ""
    air._ai_hedef_modeli = "sahte"

    def _cap(*a):
        izler["kamera_acildi"] += 1
        return _AcikCap()

    monkeypatch.setattr(air.cv2, "VideoCapture", _cap)
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(apis, "update_live_session_state", lambda *a, **k: None)
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": False, "mode": "Sistem Hazır"})

    yield air, apis, TestClient(apis.app), sag, izler

    air._ai_hazirlik_durdur_ic()
    air._ai_loop_active = False
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_hedef_modeli, air._ai_hazirlik_hata, air._ai_hazirlik_hata_kodu, air._ai_organ_id = snap
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess_snap)


def _bekle(kosul, sn=5.0):
    son = time.time() + sn
    while time.time() < son:
        if kosul():
            return True
        time.sleep(0.03)
    return False


def test_KRITIK_model_KAMERADAN_ONCE_yuklenir(env):
    """Davranışsal kapı: yükleme patlarsa kamera HİÇ açılmamış olmalı.

    MUTASYON: `_ai_hazirlik_loop`ta `_sag.yukle()` çağrısını `VideoCapture(0)`dan SONRAYA taşıyın
    → KIRMIZI (kamera bir kez açılmış olur)."""
    air, apis, client, sag, izler = env
    sag.patlat = RuntimeError("agir model yuklenemedi")

    r = client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0, "model": "sahte"})
    assert r.status_code == 200, r.text[:200]
    assert _bekle(lambda: air._ai_hazirlik_active is False), "hazırlık sonlanmadı"

    assert izler["yukleme"] == 1, "model yükleme hiç denenmedi"
    assert izler["kamera_acildi"] == 0, (
        "model yüklenemediği hâlde kamera AÇILDI — ağır sağlayıcıda kamera yükleme boyunca tutulur "
        "ve seans devri (handoff) çift VideoCapture riskine girer"
    )


def test_KRITIK_hata_sinifi_MODEL_PAKETI_ve_eylem_soyler(env):
    """Ağırlık yok (FileNotFoundError) → kurulum yönlendirmesi; ham ayrıntı sızmaz."""
    air, apis, client, sag, izler = env
    sag.patlat = FileNotFoundError("BaggingRegressor.onnx bulunamadı ve otomatik indirilemedi.")

    client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0, "model": "sahte"})
    assert _bekle(lambda: air._ai_hazirlik_active is False)
    st = client.get("/api/ai/pro/status").json()

    assert st["hazirlikHataKodu"] == "model_paketi", f"sınıf yanlış: {st['hazirlikHataKodu']!r}"
    mesaj = st["hazirlikHata"]
    assert "Sahte Model" in mesaj, "hangi modelin paketi eksik söylenmiyor"
    assert "kurulum" in mesaj.lower(), f"mesaj bir EYLEM söylemiyor: {mesaj!r}"
    for sizinti in ("FileNotFoundError", "onnx", "Traceback"):
        assert sizinti not in mesaj, f"ham teknik ayrıntı sızdı ({sizinti}): {mesaj!r}"


def test_KRITIK_hata_sinifi_KAMERA_metninde_VideoCapture_YOK(env):
    """Kamera açılamadı → kod 'kamera'; iç API adı kullanıcıya gitmez (yalnız log'a)."""
    air, apis, client, sag, izler = env
    import servers.ai_router as air2

    monkey = air2.cv2
    eski = monkey.VideoCapture
    monkey.VideoCapture = lambda *a: _KapaliCap()
    try:
        client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0, "model": "sahte"})
        assert _bekle(lambda: air._ai_hazirlik_active is False)
        st = client.get("/api/ai/pro/status").json()
    finally:
        monkey.VideoCapture = eski

    assert st["hazirlikHataKodu"] == "kamera", f"sınıf yanlış: {st['hazirlikHataKodu']!r}"
    mesaj = st["hazirlikHata"]
    assert "VideoCapture" not in mesaj, f"iç API adı kullanıcı metninde: {mesaj!r}"
    assert "kontrol" in mesaj.lower(), f"mesaj bir EYLEM söylemiyor: {mesaj!r}"


def test_KRITIK_yeni_hazirlik_eski_hata_KODUNU_temizler(env):
    """B3 dersi: bayat hata metni/kodu yeni denemede kutuda kalmamalı."""
    air, apis, client, sag, izler = env
    sag.patlat = RuntimeError("ilk deneme")
    client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0, "model": "sahte"})
    assert _bekle(lambda: air._ai_hazirlik_hata_kodu == "model_yukleme")

    sag.patlat = None
    client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0, "model": "sahte"})
    st = client.get("/api/ai/pro/status").json()
    assert st["hazirlikHataKodu"] == "", f"bayat hata kodu kaldı: {st['hazirlikHataKodu']!r}"
    assert st["hazirlikHata"] == "", "bayat hata metni kaldı"


def test_KRITIK_seans_kamerayi_acamazsa_oturum_PASIFE_alinir(env, monkeypatch):
    """`/ai/pro/start` oturumu thread'den ÖNCE aktif yazıyor; loop kamerayı açamazsa oturum
    pasife çekilmeli. MUTASYON: `_ai_seansi_pasife_al` çağrılarını kaldırın → KIRMIZI (oturum
    'sürüyor' kalır, panel ve geçmiş yanıltır)."""
    air, apis, client, sag, izler = env
    monkeypatch.setattr(air.cv2, "VideoCapture", lambda *a: _KapaliCap())
    monkeypatch.setattr(air.time, "sleep", lambda _s: None)  # 5x0,5 sn yeniden deneme
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": True, "session_id": "ai_9", "mode": "AI Pro · Sahte Model"})
    air._ai_loop_active = True

    air._ai_pro_loop()

    assert air._ai_loop_active is False, "loop bayrağı temizlenmedi"
    with apis._session_lock:
        aktif = bool(apis._active_session.get("is_active"))
    assert aktif is False, (
        "kamera açılamadı ama oturum AI modunda AKTİF kaldı — panel ve seans geçmişi tedavi "
        "sürüyormuş gibi gösterir (bobin sürülmüyor)"
    )


def test_KRITIK_kamera_devri_join_suresi_SAGLAYICIDAN_okunur(env):
    """Ağır sağlayıcı daha uzun bekleme ister; sabit 6 sn petri turunu kaçırıp çift kamera açar.
    MUTASYON: `t.join(timeout=6.0)` sabitine dönün → KIRMIZI."""
    from pathlib import Path

    air, apis, client, sag, izler = env
    src = Path(air.__file__).read_text(encoding="utf-8")
    i = src.index("def _ai_hazirlik_durdur_ic")
    govde = src[i : src.index("\ndef ", i + 10)]
    assert "join_timeout_s" in govde, (
        "kamera devri sabit bir join süresi kullanıyor — sağlayıcı bazlı süre okunmalı "
        "(petri gibi ağır modellerde bir lokalizasyon turu 6 sn'yi aşabilir)"
    )
    assert float(getattr(sag, "join_timeout_s")) == 11.0, "test sağlayıcısı beklenen süreyi taşımıyor"
