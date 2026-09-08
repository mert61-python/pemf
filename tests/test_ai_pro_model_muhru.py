# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO MODEL MÜHRÜ — hangi modelin sürüleceği ONAYLA birlikte kilitlenir (Faz 1, 2026-09-08).

Araştırma modunda AI Pro'da iki model olacak (Fantom Tümör, Petri Kuyu) ve kedi yalnız veteriner
modunda kalacak (plan: docs/arastirma-ai-pro-fantom-petri-plani.md). Model seçimi YENİ ROTA
AÇMADAN mevcut uçların gövdesinden `model` alanıyla gelir.

Kilitlenen sözleşme — 2026-08-06 sahip kararının ("organ ve süre GÖVDEDEN değil MÜHÜRDEN okunur")
model boyutuna genişletilmesi:

  · `/propose` gövdedeki modeli DOĞRULAR ve onay mührüne (`specs.model`) YAZAR.
  · `/start` modeli MÜHÜRDEN okur; gövdedeki `model` YOK SAYILIR → "fantom önerisini onaylat,
    kediyi başlat" (ya da tersi) yapısal olarak imkânsız. Aksi halde hekim/araştırmacı bir modelin
    dozunu onaylarken bobinler BAŞKA bir modelin ürettiği desenle sürülebilirdi.
  · Lokalizasyon önbelleği MODEL DAMGALI: kedi hazırlığından kalan taze ölçüm, fantom önerisine
    "taze" görünüp yanlış modelin koordinatıyla doz ürettiremez.
  · Seans bitince aktif model VARSAYILANA döner: `model` göndermeyen eski istemcilerin kareleri
    bir sonraki seansta yanlış sağlayıcıya gitmesin.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def muhur_env(monkeypatch):
    """Sahte bir hedef modeli kaydeder; propose/start akışını HTTP üzerinden koşturur."""
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis

    izler = {"predict": [], "localize": []}

    class _Sahte:
        ad = "sahte"
        title = "Sahte Model"
        subject_label = "sahte özne"
        achieved_B = 0.002
        duty_sum = 2.4
        join_timeout_s = 7.0
        varsayilan_hedef = 0

        def hedef_idleri(self):
            return frozenset({0, 1})

        def yukle(self):
            return None

        def localize(self, frame_bgr, hedef_id):
            izler["localize"].append(hedef_id)
            return (True, 1.0, 2.0, 3.0, 0.9, None, True, None)

        def predict(self, x_mm, y_mm, z_mm, hedef_id):
            izler["predict"].append(hedef_id)
            return [0.9] * 7, [10.0] * 7, 0.25  # 0.9 HAM → zarf 0.50'ye kırpar

        def hedef_adi(self, hedef_id):
            return f"Sahte hedef {hedef_id}"

        def ipucu(self, ozne_var, hedef_adi):
            return "sahte ipucu"

        def xai_sensitivity(self, *a, **k):
            return None

    monkeypatch.setitem(hedef.SAGLAYICILAR, "sahte", _Sahte())
    # Araştırma modelleriyle SÜRÜŞ bayrağı (2026-09-09): bu dosya mühür/akış sözleşmesini
    # ölçüyor, tezgâh kapısını değil → bayrak AÇIK. Kapının kendisi
    # tests/test_ai_pro_arastirma_bayragi.py içinde ölçülür.
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")

    snap_cache = dict(air._ai_organ_cache)
    snap = (air._ai_organ_id, air._ai_hedef_modeli, air._ai_owner_client, air._ai_loop_active)
    with apis._session_lock:
        sess_snap = dict(apis._active_session)

    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    air._ai_hedef_modeli = hedef.VARSAYILAN_MODEL
    air._ai_owner_client = ""
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: None)

    class _KapaliCap:
        """Seans loop'u kamerayı açamaz → hemen döner (bu dosya sürüşü değil MÜHRÜ ölçüyor)."""

        def isOpened(self):  # noqa: N802  (OpenCV adı)
            return False

        def release(self):
            return None

    monkeypatch.setattr(air.cv2, "VideoCapture", lambda *a: _KapaliCap())
    monkeypatch.setattr(air.time, "sleep", lambda _s: None)  # 5x0,5 sn yeniden deneme beklemesi
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": False, "mode": "Sistem Hazır"})

    def taze_cache(model: str, hedef_id: int = 1):
        """Verilen model adına damgalı, taze bir lokalizasyon önbelleği kur."""
        import time

        air._ai_organ_id = hedef_id
        with air._ai_cache_lock:
            air._ai_organ_cache.update(
                {
                    "x_mm": 1.0,
                    "y_mm": 2.0,
                    "z_mm": 3.0,
                    "reliability": 0.9,
                    "localized": True,
                    "overlay_bgr": None,
                    "at": time.time(),
                    "organ_id": hedef_id,
                    "kedi_var": True,
                    "guven_dokumu": None,
                    "model": model,
                }
            )

    yield air, apis, TestClient(apis.app), taze_cache, izler

    air._ai_loop_active = False
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_organ_id, air._ai_hedef_modeli, air._ai_owner_client, air._ai_loop_active = snap
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess_snap)


def _onerip_onayla(client, model: str, hedef_id: int = 1):
    r = client.post("/api/ai/pro/propose", json={"organ_id": hedef_id, "duration_minutes": 5, "model": model})
    assert r.status_code == 200, f"propose başarısız: {r.status_code} {r.text[:200]}"
    pid = r.json()["proposalId"]
    ra = client.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": "t@t"})
    assert ra.status_code == 200, ra.text[:200]
    return pid, r.json()


def test_KRITIK_onay_muhru_MODELI_tasir(muhur_env):
    """MUTASYON: propose'da `specs`ten "model" satırını silin → KIRMIZI."""
    air, apis, client, taze_cache, izler = muhur_env
    taze_cache("sahte")

    _pid, yanit = _onerip_onayla(client, "sahte")

    assert yanit["specs"].get("model") == "sahte", (
        f"öneri mührü modeli taşımıyor: {yanit['specs']} — mühürsüz model 'fantom onayla, kedi "
        "başlat' açığını geri getirir"
    )
    assert yanit["specs"].get("target_label") == "Sahte hedef 1", "mühürde hedef etiketi yok"
    assert yanit["meta"].get("subject_label") == "sahte özne"
    assert izler["predict"] == [1], "öneri sahte modelin predict'ini çağırmadı"


def test_KRITIK_start_modeli_MUHURDEN_okur_govdeyi_YOK_SAYAR(muhur_env):
    """Sözleşmenin kalbi. MUTASYON: start'ta `_spec.get("model")` yerine `payload.model` okuyun →
    KIRMIZI (aktif model 'kedi' olur, yani onaylanan modelden BAŞKASI sürülür)."""
    air, apis, client, taze_cache, izler = muhur_env
    taze_cache("sahte")
    pid, _ = _onerip_onayla(client, "sahte")

    # Gövdede KASITEN farklı model + farklı organ/süre gönderilir; hepsi yok sayılmalı.
    r = client.post(
        "/api/ai/pro/start",
        json={"proposal_id": pid, "model": "kedi", "organ_id": 5, "duration_minutes": 90, "client_id": "S"},
    )
    assert r.status_code == 200, r.text[:300]
    assert air._ai_hedef_modeli == "sahte", (
        f"aktif model {air._ai_hedef_modeli!r} — gövdedeki model mührü EZDİ: onaylanan modelden "
        "başkasının duty/faz deseniyle bobinler sürülür"
    )
    assert air._ai_organ_id == 1, "hedef de gövdeden okundu (mühür ilkesi bozuldu)"
    assert air._ai_duration_min == 5, "süre de gövdeden okundu (mühür ilkesi bozuldu)"


def test_KRITIK_muhurlu_duty_kirpma_SINIRINI_asmaz(muhur_env):
    """Sağlayıcı 0.9 ham döndürür; mühre yazılan D zarf kırpmasından geçmiş olmalı — onay
    ekranında gösterilen değer donanıma gidenle AYNI olsun."""
    from utils.stm32_protocol_limits import AI_PRO_DUTY_MAX_RATIO

    air, apis, client, taze_cache, izler = muhur_env
    taze_cache("sahte")
    _pid, yanit = _onerip_onayla(client, "sahte")

    D = yanit["specs"]["D"]
    assert max(D) <= AI_PRO_DUTY_MAX_RATIO + 1e-9, f"mühürdeki duty {max(D)} kırpma sınırını aşıyor"


def test_KRITIK_MODEL_DEGISIMINDE_bayat_cache_taze_SAYILMAZ(muhur_env):
    """Kedi hazırlığından kalan ölçüm, sahte model önerisine "taze" görünmemeli.

    MUTASYON: propose tazelik koşulundan `model` karşılaştırmasını silin → KIRMIZI (öneri 200
    döner ve YANLIŞ modelin koordinatıyla doz üretir)."""
    air, apis, client, taze_cache, izler = muhur_env
    taze_cache("kedi")  # cache KEDİ damgalı

    r = client.post("/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": "sahte"})

    assert r.status_code == 409, (
        f"başka modelin bayat cache'i taze sayıldı ({r.status_code}) — yanlış modelin koordinatıyla doz önerilir"
    )
    assert not izler["predict"], "reddedilmesi gereken istekte doz modeli çağrıldı"


def test_KRITIK_gecersiz_model_422(muhur_env):
    air, apis, client, taze_cache, izler = muhur_env
    taze_cache("kedi")

    r = client.post("/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": "yok-boyle"})
    assert r.status_code == 422, f"bilinmeyen model kabul edildi ({r.status_code})"

    r2 = client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0, "model": "yok-boyle"})
    assert r2.status_code == 422, f"hazırlık bilinmeyen modeli kabul etti ({r2.status_code})"


def test_KRITIK_hedef_kumesi_MODELE_gore_dogrulanir(muhur_env):
    """Sahte modelin hedefleri {0,1}; kedinin organ 5'i onun için geçersizdir."""
    air, apis, client, taze_cache, izler = muhur_env
    taze_cache("sahte", hedef_id=1)

    r = client.post("/api/ai/pro/propose", json={"organ_id": 5, "duration_minutes": 5, "model": "sahte"})
    assert r.status_code == 422, f"model hedef kümesi dışındaki hedef kabul edildi ({r.status_code})"
    assert "Sahte Model" in r.json().get("detail", ""), "422 metni modelin dilinde değil"


def test_KRITIK_organ_ucu_AKTIF_modelle_uyusmayan_istegi_reddeder(muhur_env):
    air, apis, client, taze_cache, izler = muhur_env
    air._ai_hedef_modeli = "sahte"

    r = client.post("/api/ai/pro/organ", json={"organ_id": 1, "model": "kedi", "client_id": ""})
    assert r.status_code == 422, f"aktif modelle uyuşmayan hedef değişimi kabul edildi ({r.status_code})"

    r2 = client.post("/api/ai/pro/organ", json={"organ_id": 1, "model": "sahte", "client_id": ""})
    assert r2.status_code == 200, r2.text[:200]
    assert r2.json()["model"] == "sahte" and r2.json()["organName"] == "Sahte hedef 1"


def test_KRITIK_stop_aktif_modeli_VARSAYILANA_dondurur(muhur_env):
    """Fantom seansından sonra `model` göndermeyen istemcinin kareleri kediye dönmeli."""
    import servers.ai_pro_hedef as hedef

    air, apis, client, taze_cache, izler = muhur_env
    taze_cache("sahte")
    pid, _ = _onerip_onayla(client, "sahte")
    client.post("/api/ai/pro/start", json={"proposal_id": pid, "client_id": "S"})
    assert air._ai_hedef_modeli == "sahte"

    r = client.post("/api/ai/pro/stop")
    assert r.status_code == 200
    assert air._ai_hedef_modeli == hedef.VARSAYILAN_MODEL, (
        "seans bitti ama aktif model sahte kaldı — sonraki modelsiz istek yanlış sağlayıcıya gider"
    )


def test_KARSIT_KANIT_model_ALANI_YOKKEN_kedi_akisi_AYNI(muhur_env):
    """Geriye-uyum: `model` göndermeyen eski istemci bugünkü kedi davranışını sürdürür."""
    air, apis, client, taze_cache, izler = muhur_env
    taze_cache("kedi", hedef_id=2)
    izler_kedi = {"predict": 0}

    def _sahte_predict(x, y, z, oid):
        izler_kedi["predict"] += 1
        return [0.2] * 7, [0.0] * 7, 0.1

    import servers.ai_pro_hedef as hedef

    monkey = hedef.SAGLAYICILAR["kedi"]
    eski = monkey.predict
    monkey.predict = _sahte_predict  # type: ignore[assignment]
    try:
        r = client.post("/api/ai/pro/propose", json={"organ_id": 2, "duration_minutes": 5})
        assert r.status_code == 200, r.text[:200]
        assert r.json()["specs"]["model"] == "kedi", "model alanı yokken varsayılan kedi olmadı"
        assert izler_kedi["predict"] == 1, "kedi doz modeli çağrılmadı"
        assert not izler["predict"], "sahte model çağrıldı"
    finally:
        monkey.predict = eski  # type: ignore[assignment]
