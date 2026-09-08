# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO: CANLI E BAĞLAMI TEMİZLİĞİ · VEKİL MODEL SEÇİMİ · XAI BAZ NOKTASI · DENETİM İZİ
(Faz 1, 2026-09-09).

Dört küçük ama sessiz hata sınıfını kapatır:

1. **Canlı E bağlamı seans bitince temizlenmiyordu.** `efield_live` bağlamı fantom/petri analizi
   (ve artık seans) tarafından kurulur; `/ai/pro/stop` ve loop teardown temizlemediği için bir
   sonraki (ör. kedi) seansında E barı ESKİ hedefin değerini "canlı" göstermeye devam ederdi.

2. **Vekil E modeli her zaman PhantomPredictor'dı.** Petri seansında fantom vekili kullanmak
   barı yanlış ölçeğe oturtur; artık bağlamdaki modele göre seçilir (geriye uyumlu: model
   verilmezse fantom).

3. **Kedi XAI baz noktası kaymıştı (sahip kararı #9).** "Dozu en çok ne belirledi" satırı
   `achieved_B`/`duty_sum` verilmediği için modülün varsayılanlarıyla (0.001 / 2.0) üretiliyordu,
   oysa doz 1.5 duty_sum ile hesaplanıyordu → açıklama BAŞKA bir çalışma noktasını anlatıyordu.

4. **Onay izinde istemci profili yoktu.** Backend profil bilmez (AI uçları auth-muaf, sahip
   kararı) ve buna göre yetki VERMEZ; ama "hangi profil bu dozu onaylattı" sorusu sonradan
   yanıtlanabilsin diye istemcinin BİLDİRDİĞİ profil mühür meta'sına yazılır.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def env(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis
    from servers import efield_live as ef

    class _Sag:
        ad = "sahte"
        title = "Sahte Model"
        subject_label = "sahte özne"
        achieved_B = 0.001
        duty_sum = 2.4
        join_timeout_s = 6.0
        varsayilan_hedef = 0

        def hedef_idleri(self):
            return frozenset({0, 1})

        def yukle(self):
            return None

        def localize(self, frame_bgr, hedef_id):
            return (True, 1.0, 2.0, 3.0, 0.9, None, True, None)

        def predict(self, x, y, z, hedef_id):
            return [0.2] * 7, [0.0] * 7, 0.3

        def hedef_adi(self, hedef_id):
            return f"Sahte {hedef_id}"

        def ipucu(self, ozne_var, hedef_adi):
            return "sahte ipucu"

        def xai_sensitivity(self, *a, **k):
            return None

    monkeypatch.setitem(hedef.SAGLAYICILAR, "sahte", _Sag())
    # Araştırma modelleriyle SÜRÜŞ bayrağı (2026-09-09): bu dosya mühür/akış sözleşmesini
    # ölçüyor, tezgâh kapısını değil → bayrak AÇIK. Kapının kendisi
    # tests/test_ai_pro_arastirma_bayragi.py içinde ölçülür.
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")

    snap_cache = dict(air._ai_organ_cache)
    snap = (air._ai_hedef_modeli, air._ai_organ_id)
    with apis._session_lock:
        sess_snap = dict(apis._active_session)
    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    air._ai_hedef_modeli = "sahte"
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(apis, "update_live_session_state", lambda *a, **k: None)
    monkeypatch.setattr(apis, "_mqtt_publish", lambda *a, **k: True)
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": False, "mode": "Sistem Hazır"})

    import time as _t

    air._ai_organ_id = 1
    with air._ai_cache_lock:
        air._ai_organ_cache.update(
            {
                "x_mm": 1.0,
                "y_mm": 2.0,
                "z_mm": 3.0,
                "reliability": 0.9,
                "localized": True,
                "overlay_bgr": None,
                "at": _t.time(),
                "organ_id": 1,
                "kedi_var": True,
                "guven_dokumu": None,
                "model": "sahte",
            }
        )

    yield air, apis, ef, TestClient(apis.app)

    ef.set_context([])
    air._ai_loop_active = False
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_hedef_modeli, air._ai_organ_id = snap
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess_snap)


def test_KRITIK_stop_canli_E_baglamini_TEMIZLER(env):
    """MUTASYON: `stop_ai_pro`daki `set_context([])` çağrısını kaldırın → KIRMIZI (bağlam kalır ve
    sonraki seansta E barı eski hedefi 'canlı' gösterir)."""
    air, apis, ef, client = env
    ef.set_context([{"centroid_cabin_mm": [10.0, 20.0, 30.0], "organ_id": 1}], model="sahte")
    assert ef.get_context() is not None, "test kurulumu: bağlam kurulmadı"

    r = client.post("/api/ai/pro/stop")
    assert r.status_code == 200

    assert ef.get_context() is None, (
        "seans durduruldu ama canlı E bağlamı duruyor — bir sonraki seansta bar ESKİ hedefin değerini canlı gösterir"
    )


def test_KRITIK_baglam_MODELI_tasir_ve_vekil_model_ona_gore_secilir(env):
    """Bağlam modeli taşımalı; `_predictor` petri için farklı bir vekil döndürmeli.

    Ağırlıklar bu ortamda yoksa vekil `None` olur — o durumda YALNIZ bağlamın modeli taşıdığı
    ölçülür (kapı boş çalışmasın diye ayrım açıkça raporlanır)."""
    air, apis, ef, client = env
    ef.set_context([{"centroid_cabin_mm": [1.0, 2.0, 3.0], "organ_id": 1}], model="petri")
    ctx = ef.get_context()
    assert ctx is not None and ctx.get("model") == "petri", f"bağlam modeli taşımıyor: {ctx}"

    fantom = ef._predictor("fantom")
    petri = ef._predictor("petri")
    if fantom is None or petri is None:
        pytest.skip("EM vekil ağırlıkları bu ortamda yok — model seçimi yalnız bağlam düzeyinde ölçüldü")
    assert type(fantom) is not type(petri), (
        "petri bağlamında da fantom vekili kullanılıyor — canlı E barı yanlış ölçeğe oturur"
    )


def test_KARSIT_KANIT_model_verilmezse_FANTOM_vekili_korunur(env):
    """Geriye uyum: `model` argümanı olmayan eski çağrılar (AI Hub fantom analizi) etkilenmez."""
    air, apis, ef, client = env
    ef.set_context([{"centroid_cabin_mm": [1.0, 2.0, 3.0], "organ_id": 1}])
    ctx = ef.get_context()
    assert ctx is not None and ctx.get("model") is None, f"model verilmedi ama bağlama yazıldı: {ctx}"

    varsayilan = ef._predictor(None)
    fantom = ef._predictor("fantom")
    if varsayilan is None:
        pytest.skip("EM vekil ağırlıkları bu ortamda yok")
    assert varsayilan is fantom, "model verilmeyince fantom vekili dönmüyor (eski davranış bozuldu)"


def test_KRITIK_kedi_XAI_FIILEN_kullanilan_baz_noktasiyla_uretilir(monkeypatch):
    """Sahip kararı #9. MUTASYON: `xai_sensitivity`den `achieved_B`/`duty_sum` argümanlarını
    kaldırın → KIRMIZI (modül varsayılanı 2.0 kullanılır, doz ise 1.5 ile üretilir)."""
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air

    yakalanan = {}

    class _SahteIek:
        @staticmethod
        def xai_hizli_sensitivity(predictor, x, y, z, organ_id, achieved_B=None, duty_sum=None, top_n=3):
            yakalanan.update({"achieved_B": achieved_B, "duty_sum": duty_sum, "organ_id": organ_id})
            return [{"feature": "duty_sum", "etki": 1.0}]

    # ⚠️ `from ai_hub.em_kedi import inference_em_kedi as _iek` iki yoldan çözülebilir: alt modül
    # daha önce import edildiyse PAKET ATTRIBUTE'u, edilmediyse `sys.modules`. Süit sırasına göre
    # ikisi de gerçekleşebildiği için İKİSİ de yamalanır (aksi hâlde test sıraya bağlı kırılır).
    import sys

    import ai_hub.em_kedi as _paket

    monkeypatch.setitem(sys.modules, "ai_hub.em_kedi.inference_em_kedi", _SahteIek)
    monkeypatch.setattr(_paket, "inference_em_kedi", _SahteIek, raising=False)
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda: object())

    kedi = hedef.saglayici_al("kedi")
    kedi.xai_sensitivity(1.0, 2.0, 3.0, 2)

    assert yakalanan.get("achieved_B") == kedi.achieved_B, (
        f"XAI achieved_B={yakalanan.get('achieved_B')} ≠ dozda kullanılan {kedi.achieved_B}"
    )
    assert yakalanan.get("duty_sum") == kedi.duty_sum, (
        f"XAI duty_sum={yakalanan.get('duty_sum')} ≠ dozda kullanılan {kedi.duty_sum} — açıklama "
        "BAŞKA bir çalışma noktasını anlatır (XAI vekil-nokta kayması)"
    )


def test_KRITIK_onay_izine_istemci_PROFILI_yazilir(env):
    """Denetim izi. Backend profile göre yetki VERMEZ (auth-muafiyet değişmezi); yalnız kaydeder."""
    air, apis, ef, client = env

    r = client.post(
        "/api/ai/pro/propose",
        json={"organ_id": 1, "duration_minutes": 5, "model": "sahte", "client_mode": "researcher"},
    )
    assert r.status_code == 200, r.text[:200]
    assert r.json()["meta"].get("client_mode") == "researcher", (
        f"istemci profili mühür meta'sına yazılmadı: {r.json()['meta']}"
    )


def test_KARSIT_KANIT_profil_ALANI_YOKKEN_oneri_calisir(env):
    """`client_mode` göndermeyen eski istemci kırılmaz (alan boş kalır)."""
    air, apis, ef, client = env

    r = client.post("/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": "sahte"})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["meta"].get("client_mode") == "", "alan yokken öneri bozuldu"
