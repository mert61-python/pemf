# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.88 · B-6.30 · A-19 (+ D1.E09 · İG-5.31) — FGS "Otonom Biofeedback" AI Pro MÜHRÜNE bağlı; landmark ucu cihazı SÜRMEZ.

ÖLÇÜLEN KUSUR (06 · B-6.30; D0): `POST /api/ai/vision/landmark` `auto_adjust=true` ile — galeriden seçilmiş TEK fotoğraf,
istemcide bir onay penceresi — `start_ai_session(…, 30 dk, range(1, 9))` + `start_all_coils` + ESP START yayını yapıp 200
dönüyordu: hekim onayı → mühür akışı YOK. Aynı durumda AI Pro 428 veriyor (onay asimetrisi). Sahip kararı A-19: öneri →
hekim onayı → mühür akışından geçmeden sürüş başlamaz.

DÜZELTME: `auto_adjust=true` → 428 + eylem metni, analiz yapılmaz, hiçbir seans/bobin/yayın yok (mikroservis profilinde
de; kapı devretmeden önce). Sürüş yolu kaldırıldı (mühürlü seansta da zaten sürmüyordu). `auto_adjust=false` salt
analiz: aynen çalışır.

D1.E09 (İG-5.31): model nokta başına güven kanalı vermiyor (`kpt_shape [48,2]`) → yanıt bunu `nokta_gorunurlugu_
dogrulanmadi` ile SÖYLER (skor reddedilmez: görüntü temelli görünürlük ölçütleri gerçek fotoğrafta yanlış ret ve
kaçırma verdi — D1D raporu). Güven kanalı olan modelde alan False.

KAPI: GERÇEK `HardwareController` (kayıtçı kuyruk) + gerçek seans/DB yolu; model sahte (48 nokta), yerel istek.
"""

from __future__ import annotations

import ai_pro_aparati as ap
import numpy as np
import pytest


class _T:
    """torch tensörü taklidi (`.cpu().numpy()`, dizinleme, uzunluk)."""

    def __init__(self, a):
        self.a = np.asarray(a, dtype=np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self.a

    def __getitem__(self, i):
        return _T(self.a[i])

    def __len__(self):
        return len(self.a)


def _yuz_noktalari():
    """Kutu (100,100)-(300,300) içinde 48 nokta (6×8 ızgara) — sıfır nokta yok, FGS hesaplanır."""
    xs, ys = np.meshgrid(np.linspace(110, 290, 8), np.linspace(110, 290, 6))
    return np.stack([xs.ravel(), ys.ravel()], axis=1)


class _Sonuc:
    def __init__(self, conf=None):
        kp = _yuz_noktalari()
        self.keypoints = type("K", (), {})()
        self.keypoints.xy = _T(kp[None])
        self.keypoints.conf = None if conf is None else _T(np.full((1, 48), conf))
        kutu = type("B", (), {})()
        kutu.xyxy = _T(np.array([[100.0, 100.0, 300.0, 300.0]]))
        self.boxes = [kutu]


class _Model:
    def __init__(self):
        self.conf = None
        self.cagri = 0

    def predict(self, *a, **k):
        self.cagri += 1
        return [_Sonuc(self.conf)]


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import auth

    ns = ap.kur(monkeypatch, tmp_path)
    ns.model = _Model()
    monkeypatch.setattr(ns.air, "_get_or_load_model", lambda ad, y: ns.model)
    # Yerel/LAN istemci (uygulamanın kendisi): eski kodda sürüş yetkisi buydu — kusur YETKİLİ yolda ölçülür.
    monkeypatch.setattr(auth, "is_local_request", lambda *a, **k: True)
    ns.seans = []
    gercek_baslat = ns.api.start_ai_session

    def _kayitci_baslat(*a, **k):
        ns.seans.append((a, k))
        return gercek_baslat(*a, **k)

    monkeypatch.setattr(ns.api, "start_ai_session", _kayitci_baslat)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.c.post("/api/session/stop")
        if ns.hc is not None:
            ns.hc.stop_all_coils()
        ns.geri()


def _landmark(o, auto: bool):
    return o.c.post(
        "/api/ai/vision/landmark", data={"image_base64": "QUJD", "auto_adjust": "true" if auto else "false"}
    )


def test_KRITIK_A19_onaysiz_otonom_FGS_istegi_428_ve_HICBIR_surus_yok(o):
    once = ap.paket_sayisi(o)
    r = _landmark(o, True)
    yayin = [t for t, p in o.yayin if str(p.get("command", "")).lower() == "start"]
    with o.api._session_lock:
        aktif = bool(o.api._active_session.get("is_active"))
    gozlem = {
        "kod": r.status_code,
        "seans": len(o.seans),
        "surus": [d for d in ap.surus_paketleri(o, once) if d[1] > 0][:2],
        "calisan": ap.calisan(o),
        "esp_start": yayin[:2],
        "seans_aktif": aktif,
    }
    assert gozlem["kod"] == 428, f"onaysız (mühürsüz) otonom FGS isteği reddedilmedi: {gozlem} {r.text[:160]}"
    assert not gozlem["seans"] and not gozlem["surus"] and not gozlem["calisan"] and not gozlem["esp_start"], (
        f"onaysız otonom FGS isteği cihazı SÜRDÜ: {gozlem}"
    )
    assert not gozlem["seans_aktif"], f"seans açık kaldı: {gozlem}"
    detay = r.json().get("detail", "")
    assert "AI Pro" in detay and "onay" in detay, f"428 eylem söylemiyor: {detay!r}"
    assert o.model.cagri == 0, "sürüş isteği reddedilmeden önce çıkarım yapıldı (saniyeler boşa)"


def test_KRITIK_A19_mikroservis_profilinde_de_428_DEVRETMEDEN_once(o, monkeypatch):
    devir = []

    async def _sahte_devret(name, **kw):
        devir.append(name)
        return {"status": "success", "detected": True, "fgs_total": 3}

    monkeypatch.setattr(o.air, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(o.air, "_kapili_devret", _sahte_devret)
    r = _landmark(o, True)
    assert r.status_code == 428 and devir == [], f"GPU profilinde otonom istek reddedilmedi: {r.status_code} {devir}"


def test_KRITIK_A19_mandalsiz_ve_seanssiz_TEMIZ_durumda_da_surmez_N10(o):
    """Sürüş yolunun kalıntısı yok: temiz durumda (mandal yok, seans yok, AI Pro kapalı) 10 denemede de sürüş 0."""
    once = ap.paket_sayisi(o)
    kodlar = [_landmark(o, True).status_code for _ in range(10)]
    assert set(kodlar) == {428}, kodlar
    assert not ap.surus_paketleri(o, once) and not ap.calisan(o) and not o.seans


@pytest.mark.parametrize("seans", ["muhurlu_ai_pro", "elle"])
def test_KRITIK_A19_SUREN_seans_varken_otonom_istek_428_ve_seans_DEGISMEZ(o, seans):
    """Eski `test_landmark_auto_aktif_AI_Pro_seansini_GASP_ETMEZ` / `…FARKLI_MODDAKI_aktif_seansi_de_DEVRALMAZ`
    (closure'a bağlıydı, yol kalktı) iddialarının davranışsal karşılığı: süren seans devralınmaz, tel değişmez."""
    if seans == "muhurlu_ai_pro":
        ap.muhurlu_seans_yaz(o.api, sure_dk=20)
    else:
        with o.api._session_lock:
            o.api._active_session.clear()
            o.api._active_session.update(
                {"is_active": True, "session_id": "test-elle", "mode": "Manuel", "tur": None, "coil_ids": [1, 2]}
            )
    with o.api._session_lock:
        once_seans = dict(o.api._active_session)
    once = ap.paket_sayisi(o)
    r = _landmark(o, True)
    with o.api._session_lock:
        sonra_seans = dict(o.api._active_session)
    assert r.status_code == 428, r.text[:160]
    assert sonra_seans == once_seans, f"süren {seans} seansı değişti: {once_seans} → {sonra_seans}"
    assert not ap.surus_paketleri(o, once) and not o.seans, "süren seans varken otonom istek donanıma dokundu"


def test_KARSIT_A19_salt_analiz_CALISIR_ve_surmez(o):
    once, y0 = ap.paket_sayisi(o), len(o.yayin)
    r = _landmark(o, False)
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j["detected"] is True and isinstance(j["fgs_total"], int), j
    assert j["hw_status"] == "idle" and j["hw_params"] == {}
    assert not ap.surus_paketleri(o, once) and not o.seans
    # 1-D inceleme i3-F-3: salt analiz ESP (bobin 8) START yayını da üretmez — STM paketi ve `start_ai_session` yalnız
    # 1-7'yi görür; ESP START denetimi yalnız `auto_adjust=true` kolundaydı (orada 428 analizden önce döner).
    esp = [(t, p.get("command")) for t, p in o.yayin[y0:] if str(p.get("command", "")).lower() == "start"]
    assert not esp, f"salt analiz ESP START yayınladı: {esp}"


def test_KRITIK_A19_GERCEK_muhurlu_AI_Pro_surerken_otonom_istek_428_ve_frame_SURMEYE_devam_eder(o):
    """1-D inceleme i3-F-4: `muhurlu_seans_yaz` gerçek `/ai/pro/start`'ın kurduğu döngü bayrağını (`_ai_loop_active`)
    kurmaz; "428 yalnız AI Pro döngüsü KAPALIYKEN" mutantı o kolda görünmüyordu. GERÇEK öner → onayla → başlat: 428,
    seans (A-16 `onay_hedefi` dahil) birebir aynı, 428 SONRASI `/frame` meşru sürüşe devam eder."""
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200 and o.air._ai_loop_active is True, r.text[:200]  # ARA DOĞRULAMA: gerçek mühürlü koşu
    with o.api._session_lock:
        once = dict(o.api._active_session)
    r_l = _landmark(o, True)
    with o.api._session_lock:
        sonra = dict(o.api._active_session)
    n = ap.paket_sayisi(o)
    j = ap.kare(o).json()
    assert r_l.status_code == 428, f"AI Pro döngüsü açıkken otonom FGS isteği reddedilmedi: {r_l.status_code}"
    assert once == sonra, f"428 süren mühürlü seansı değiştirdi: {once} → {sonra}"
    assert j.get("driven") is True and ap.surus_paketleri(o, n), "428 mühürlü seansın meşru sürüşünü kırdı"


def test_KRITIK_E09_guven_kanali_YOK_modelde_yanit_bunu_SOYLER(o):
    j = _landmark(o, False).json()
    assert j["detected"] is True
    assert j.get("nokta_gorunurlugu_dogrulanmadi") is True, (
        f"güven kanalı olmayan modelde örtülü nokta FGS'ye girebilir; yanıt bunu söylemiyor: {sorted(j)}"
    )


def test_KARSIT_E09_guven_kanali_OLAN_modelde_uyari_YOK(o):
    o.model.conf = 0.9
    j = _landmark(o, False).json()
    assert j["detected"] is True and j.get("nokta_gorunurlugu_dogrulanmadi") is False, j.get(
        "nokta_gorunurlugu_dogrulanmadi"
    )


def test_KRITIK_E09_GPU_servisi_ayni_alani_dondurur_parite(monkeypatch):
    """`ai_service/app.py::infer_landmark` aynı alanı taşır (GPU profilinde router yanıtı servisinkidir)."""
    import io

    import cv2

    import ai_service.app as a

    monkeypatch.setattr(a.predictors, "get", lambda ad: _Model())
    monkeypatch.setattr(a, "_kapi", lambda data, label: None)
    ok, buf = cv2.imencode(".jpg", np.full((64, 64, 3), 120, np.uint8))

    class _Dosya:
        file = io.BytesIO(buf.tobytes())
        filename = "kare.jpg"

    j = a.infer_landmark(file=_Dosya())
    assert isinstance(j, dict) and j.get("detected") is True, str(j)[:200]
    assert j.get("nokta_gorunurlugu_dogrulanmadi") is True, sorted(j)


def test_KARSIT_E09_GPU_servisi_guven_kanali_OLAN_modelde_alan_False(monkeypatch):
    """1-D inceleme i3-F-5: servis paritesinin KARŞIT kolu (servis "her zaman uyar" mutantı yeşil kalıyordu)."""
    import io

    import cv2

    import ai_service.app as a

    m = _Model()
    m.conf = 0.9
    monkeypatch.setattr(a.predictors, "get", lambda ad: m)
    monkeypatch.setattr(a, "_kapi", lambda data, label: None)
    ok, buf = cv2.imencode(".jpg", np.full((64, 64, 3), 120, np.uint8))

    class _Dosya:
        file = io.BytesIO(buf.tobytes())
        filename = "kare.jpg"

    j = a.infer_landmark(file=_Dosya())
    assert isinstance(j, dict) and j.get("detected") is True, str(j)[:200]
    assert j.get("nokta_gorunurlugu_dogrulanmadi") is False, j.get("nokta_gorunurlugu_dogrulanmadi")
