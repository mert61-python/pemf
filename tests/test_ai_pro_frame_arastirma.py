# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MOBİL KARE UCU × ARAŞTIRMA MODELİ (Faz 4, 2026-09-09).

`POST /api/ai/ai_pro/frame` telefondan gelen tek kareyi işler ve bobinleri sürer. Faz 1-3'te hedef
modeli soyutlandı; bu dosya kare yolunun o soyutlamayı GERÇEKTEN kullandığını ölçer:

  1. Aktif seans fantom/petri modelindeyse kare O SAĞLAYICIYA gider ve yanıt hedef adaylarını taşır
     (panelin kare üstü halkaları bunlardan besleniyor).
  2. `driven` yalnız (localized ∧ aktif seans ∧ sahip) — YABANCI kare ASLA bobin sürmez ([B1]).
  3. ⚠️ ESKİ APK GERİYE-UYUMU: `model` göndermeyen istemcide kare KEDİ hattına gider; araştırma
     sağlayıcısı HİÇ çağrılmaz. Sürüm kayması bu depoda tekrar tekrar arıza üretti (catDetected,
     ownerClientId, localizedAt); modeli "boş = kedi" saymak o dersin uygulaması.

⚠️ Kare ucu modeli GÖVDEDEN OKUMAZ: aktif hedef `_ai_hedef_modeli`dir ve onu yalnız
`/hazirlik/baslat` (seans yokken) ya da onay MÜHRÜ (`/start`) değiştirir. Bu kasıtlı — kare başına
model değiştirilebilseydi, onaylanan modelden BAŞKA bir modelin dozu sürülebilirdi.
"""

import io
import time

import pytest
from fastapi.testclient import TestClient


def _jpg(boyut: int = 32) -> bytes:
    """Gerçek kodlanmış kare — cv2 decode edebilsin (elle yazılmış PNG baytları reddedildi)."""
    import cv2
    import numpy as np

    ok, buf = cv2.imencode(".jpg", np.zeros((boyut, boyut, 3), dtype=np.uint8))
    assert ok, "test karesi kodlanamadı"
    return bytes(buf)


@pytest.fixture()
def env(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis

    izler = {"lokalize": [], "predict": []}

    class _Sag:
        ad = "sahte"
        title = "Sahte Araştırma Modeli"
        subject_label = "sahte özne"
        achieved_B = 0.001
        duty_sum = 2.4
        join_timeout_s = 6.0
        varsayilan_hedef = 0

        def hedef_idleri(self):
            return frozenset({0, 1, 2})

        def yukle(self):
            return None

        def localize(self, frame_bgr, hedef_id):
            izler["lokalize"].append(hedef_id)
            return (True, 11.0, 22.0, 33.0, 0.9, None, True, None)

        def predict(self, x, y, z, hedef_id):
            izler["predict"].append((x, y, z, hedef_id))
            return [0.2] * 7, [0.0] * 7, 0.3

        def hedef_adi(self, hedef_id):
            return f"Tümör {hedef_id}"

        def ipucu(self, ozne_var, hedef_adi):
            return "sahte ipucu"

        def son_lokalizasyon_meta(self):
            return {
                "model": self.ad,
                "method": "aruco_pnp",
                "mm_per_px": 0.5,
                "target_label": "Tümör 1",
                "targets": [{"id": 1, "label": "Tümör 1", "pxn": [0.5, 0.5], "reliability": 0.9}],
                "e_cancer": 0.13,
                "e_healthy": 0.06,
                "ood": False,
            }

        def xai_sensitivity(self, *a, **k):
            return None

    monkeypatch.setitem(hedef.SAGLAYICILAR, "sahte", _Sag())
    # Bayrak AÇIK: bu dosya kare YOLUNU ölçüyor, bayrak kapısını değil (o ayrı kapıda).
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")

    # Kedi hattı çağrıldı mı? (eski APK geriye-uyumu için gereken karşıt kanıt)
    kedi_izi = {"n": 0}
    _gercek_kedi = air._extract_organ_target

    def _kedi_sonda(*a, **k):
        kedi_izi["n"] += 1
        return (True, 1.0, 2.0, 3.0, 0.8, None, True, None)

    monkeypatch.setattr(air, "_extract_organ_target", _kedi_sonda)

    snap_cache = dict(air._ai_organ_cache)
    snap = (air._ai_hedef_modeli, air._ai_organ_id, air._ai_owner_client, air._ai_started_at, air._ai_duration_min)
    with apis._session_lock:
        sess_snap = dict(apis._active_session)

    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    air._ai_relocalize = True  # her testte taze lokalizasyon zorla
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(apis, "update_live_session_state", lambda *a, **k: None)
    monkeypatch.setattr(apis, "_mqtt_publish", lambda *a, **k: True)
    surus = {"n": 0}
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: surus.__setitem__("n", surus["n"] + 1))

    def seans(model: str, sahip: str, hedef_id: int = 1):
        """Onaylanmış AI Pro seansı: mühürlenen model aktif, süre-watchdog kapsamında."""
        air._ai_hedef_modeli = model
        air._ai_organ_id = hedef_id
        air._ai_owner_client = sahip
        air._ai_started_at = time.monotonic()
        air._ai_duration_min = 20
        air._ai_relocalize = True
        with apis._session_lock:
            apis._active_session.clear()
            apis._active_session.update({"is_active": True, "mode": "AI Pro"})

    yield air, TestClient(apis.app), seans, izler, kedi_izi, surus

    air._ai_loop_active = False
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_hedef_modeli, air._ai_organ_id, air._ai_owner_client, air._ai_started_at, air._ai_duration_min = snap
    air._extract_organ_target = _gercek_kedi
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess_snap)


def _kare(client, client_id: str):
    return client.post(
        "/api/ai/ai_pro/frame",
        files={"file": ("k.jpg", io.BytesIO(_jpg()), "image/jpeg")},
        data={"client_id": client_id},
    )


def test_KRITIK_aktif_arastirma_seansinda_kare_O_SAGLAYICIYA_gider(env):
    """MUTASYON: `_localize_organ`daki delegasyonu kaldırıp doğrudan kediye bağlayın → KIRMIZI
    (fantom seansı sürerken bobinler KEDİ modelinin dozuyla sürülürdü)."""
    air, client, seans, izler, kedi_izi, surus = env
    seans("sahte", "telefon-1")

    r = _kare(client, "telefon-1")

    assert r.status_code == 200, r.text
    j = r.json()
    assert j["model"] == "sahte", f"kare yanıtı aktif modeli bildirmiyor: {j.get('model')!r}"
    assert izler["lokalize"], "araştırma sağlayıcısının lokalize'ı HİÇ çağrılmadı"
    assert kedi_izi["n"] == 0, "araştırma seansında KEDİ hattı çağrıldı"
    # Kare üstü halkaların kaynağı: yanıt hedef adaylarını TAŞIMALI.
    assert j["targets"] and j["targets"][0]["id"] == 1, f"hedef adayları yanıtta yok: {j.get('targets')}"
    assert j["targets"][0]["pxn"] == [0.5, 0.5], "halka koordinatı (pxn) yanıtta taşınmıyor"
    assert j["method"] == "aruco_pnp", "kalibrasyon yöntemi yanıtta yok (rozet boş kalır)"
    assert j["targetName"] == "Tümör 1", f"hedef adı model diliyle değil: {j.get('targetName')!r}"


def test_KRITIK_sahip_karesi_SURER_yabanci_kare_SURMEZ(env):
    """[B1]: yanlış kameradan hesaplanan hedefe onaylı seansta enerji verilmesini engeller."""
    air, client, seans, izler, kedi_izi, surus = env
    seans("sahte", "telefon-1")

    sahip = _kare(client, "telefon-1").json()
    assert sahip["driven"] is True, "sahibin karesi bobin sürmedi (kapalı döngü kırık)"
    assert surus["n"] == 1, "sürüş çağrısı yapılmadı"

    yabanci = _kare(client, "telefon-2").json()
    assert yabanci["driven"] is False, "YABANCI kare bobin sürdü — [B1] ihlali"
    assert yabanci["foreignViewer"] is True, "yabancı istemci işaretlenmiyor"
    assert surus["n"] == 1, "yabancı kare sürüş çağrısı yaptı"


def test_KRITIK_seans_YOKKEN_arastirma_karesi_de_bobin_SURMEZ(env):
    """Audit P0: süre-watchdog kapsamı dışındaki hiçbir kare bobin sürmez (model fark etmez)."""
    air, client, seans, izler, kedi_izi, surus = env
    seans("sahte", "telefon-1")
    import servers.api_server as apis

    with apis._session_lock:
        apis._active_session.update({"is_active": False})

    j = _kare(client, "telefon-1").json()

    assert j["driven"] is False, "seans yokken kare bobin sürdü"
    assert surus["n"] == 0, "seans yokken sürüş çağrısı yapıldı"


def test_KRITIK_ESKI_APK_modelsiz_kare_KEDI_hattinda_kalir(env):
    """⚠️ SÜRÜM KAYMASI: `model` alanını hiç bilmeyen bir APK, kedi akışında BİREBİR çalışmalı.

    Kare ucu modeli gövdeden okumaz; aktif model kedi olduğunda araştırma sağlayıcısı hiç
    çağrılmaz. MUTASYON: `_aktif_saglayici()` varsayılanını araştırma modeline çevirin → KIRMIZI."""
    air, client, seans, izler, kedi_izi, surus = env
    import servers.ai_pro_hedef as hedef

    seans(hedef.VARSAYILAN_MODEL, "telefon-1")

    j = _kare(client, "telefon-1").json()

    assert j["model"] == hedef.VARSAYILAN_MODEL, f"eski istemcide model kaymış: {j.get('model')!r}"
    assert kedi_izi["n"] == 1, "kedi hattı çağrılmadı (eski APK akışı bozuldu)"
    assert not izler["lokalize"], "kedi seansında ARAŞTIRMA sağlayıcısı çağrıldı"
    # Kedi yanıtında araştırma alanları BOŞ olur (yalnız-ek sözleşme) ama anahtarlar VAR kalır.
    assert j["targets"] == [], f"kedi hattında hedef adayı üretilmiş: {j['targets']}"
    assert "catDetected" in j and "localizedAt" in j, "eski panelin okuduğu alanlar kaybolmuş"
