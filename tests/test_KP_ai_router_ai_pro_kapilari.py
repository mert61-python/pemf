# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/servers/ai_router.py · sözleşmeler: AI Pro öneri / onay / başlatma / durdurma / kare / sürüş kapıları.

- `/propose`: araştırma modelinde otomatik hedefin seçili kimliği modelin hedeflerinde değilse 409; doz modeli sıfır doz
  üretirse 422 (`dozUretmedi`); uzak istek kimlik denetimi yapılamazsa hasta BAĞLANMAZ (fail-closed).
- `/approve` / `/reject`: ikinci karar 409, bilinmeyen öneri 404; denetim izi yazılamasa da karar kaydı yazılır.
- `/start`: güncelleme sürüyorsa 409 (onay tüketilmez); güncelleme denetimi bozuksa başlatmayı ENGELLEMEZ; mühürdeki model
  bilinmiyorsa 422 (onay tüketilmez); STM red denetimi bozuksa başlatmayı engellemez; doğrulama ile tüketim arasında onay
  tüketildiyse 428; seans kaydı beklenmedik hatayla yazılamasa da döngü başlar; başlatma sırasında acil durdurma gelirse 409 +
  seans pasif + onay YANAR (aynı onayla yeniden başlatma 428).
- `stop_ai_pro`: seans okunamasa / STOP bildirimi düşse / canlı E bağlamı temizlenemese de durdurma tamamlanır; seans okunamasa
  da STOP TÜM bobinlere (STM 1-7 + ESP 8) gider.
- `_ai_pro_satirini_kapat`: başka yolun kapattığı satır EZİLMEZ; DB hatası yükselmez.
- `/hazirlik/baslat`: modele ait olmayan hedef varsayılana çekilir; önizleme zaten çalışıyorsa ikinci iş parçacığı açılmaz.
- `/frame`: büyük kare 960 px'e küçültülür; kapı reddi (HTTPException) 500'e çevrilmez; `_frame_kayip_stopu` nesil artırımı /
  STOP iş parçacığı hata verse de yükselmez ve STOP denenir.
- `_ai_seansi_pasife_al`, `_drive_coils_ai_pro`, `_localize_organ_cpu`, hazırlık teşhis yardımcıları.

Aparat: `tests/ai_pro_aparati.kur` (DB tmp, yayın / bildirim kaydedilir, döngü no-op). Sahte EN ALT katta: donanım (kayıtçı
`update_coil`), bildirim gönderimi (`_push_notification`), güncelleme bayrağı (gerçek `update_manager` durumu), DB nesnesi.
"""

from __future__ import annotations

import asyncio
import base64
import sqlite3
import sys
import time
import types

import ai_pro_aparati as ap
import cv2
import numpy as np
import pytest
from kd_kalibrasyon_yardimci import (
    kd_gecerli_kalibrasyon,  # noqa: F401,E402  KD · Y259: kalibrasyon ön koşulu sağlanmış (bu dosya başka kuralı ölçer)
)
from servers import ai_router as air
from utils import ceviri

#: Aparat `_predict_and_drive`ı sahteler; doz kapısı testleri GERÇEK zarfı (kırpma + sıfır doz) kullanır.
_GERCEK_TAHMIN = air._predict_and_drive


@pytest.fixture
def ns(monkeypatch, tmp_path):
    o = ap.kur(monkeypatch, tmp_path)
    try:
        yield o
    finally:
        ap.dongu_bitir(o.air)
        o.geri()
        o.c.close()


def _oneri(model="kedi", organ=2, sure=5, onayla=True):
    from servers import ai_approval

    rec = ai_approval.create("ai_pro", {"organ_id": organ, "duration_minutes": sure, "model": model})
    if onayla:
        ai_approval.approve(rec["id"], "hekim@test.local")
    return rec["id"]


def _kos(coro):
    dongu = asyncio.SelectorEventLoop()
    try:
        return dongu.run_until_complete(coro)
    finally:
        dongu.run_until_complete(dongu.shutdown_default_executor())
        dongu.close()


# ───────────────────────────── /propose ─────────────────────────────


def test_uzak_istek_kimlik_denetimi_YAPILAMAZSA_hasta_BAGLANMAZ(monkeypatch):
    """X-Forwarded-For'lu istek + jeton çözümü DB hatası → True (kimliksiz say); çözüm başarılıysa False (karşıt)."""
    from servers import operator_tokens

    istek = types.SimpleNamespace(headers={"x-forwarded-for": "203.0.113.5"}, query_params={})

    def _kilitli(t):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(operator_tokens, "cozumle", _kilitli)
    assert air._uzaktan_kimliksiz_mi(istek) is True
    monkeypatch.setattr(operator_tokens, "cozumle", lambda t: {"email": "hekim@test.local"})
    assert air._uzaktan_kimliksiz_mi(istek) is False


def test_propose_arastirma_OTOMATIK_hedefin_secili_kimligi_GECERSIZSE_409(ns, monkeypatch):
    """Petri (bayrak açık), organ 0 = otomatik; önbellekteki seçili kimlik 999 modelin hedeflerinde YOK → 409 otomatikHedefGecersiz."""
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    ns.air._ai_organ_cache.update(
        {"localized": True, "organ_id": 0, "model": "petri", "at": time.time(), "secili_id": 999, "kosulsuz": False}
    )
    r = ns.c.post("/api/ai/pro/propose", json={"organ_id": 0, "model": "petri"})
    assert r.status_code == 409, r.text[:300]
    beklenen = ceviri.t("ai.pro.hata.otomatikHedefGecersiz", mesaj=air.otomatik_hedef_secilemedi_mesaji(), secili=999)
    assert r.json()["detail"] == beklenen


def test_propose_doz_modeli_SIFIR_doz_uretirse_422_oneri_KAYDEDILMEZ(ns, monkeypatch):
    """Kedi organ 2, taze konum; doz modeli [0]*7 → 422 `ai.pro.hata.dozUretmedi`; onay kaydı oluşmaz."""
    from servers import ai_approval, ai_pro_hedef

    monkeypatch.setattr(ns.air, "_predict_and_drive", _GERCEK_TAHMIN)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", lambda self, *a, **k: ([0.0] * 7, [0.0] * 7, 0.0))
    ns.air._ai_organ_cache.update(
        {"localized": True, "organ_id": 2, "model": "kedi", "at": time.time(), "x_mm": 10.0, "y_mm": 5.0, "z_mm": 0.0}
    )
    once = len(ai_approval._store)
    r = ns.c.post("/api/ai/pro/propose", json={"organ_id": 2, "model": "kedi"})
    assert r.status_code == 422, r.text[:300]
    assert r.json()["detail"] == ceviri.t("ai.pro.hata.dozUretmedi")
    assert len(ai_approval._store) == once


# ───────────────────────────── /approve · /reject · onay izi ─────────────────────────────


def test_approve_IKINCI_karar_409_zaten_karar_verildi(ns):
    """Onaylanmış öneri yeniden onaylanır → 409 + `onay.hata.zatenKarar` (durum: approved)."""
    pid = _oneri(onayla=False)
    r1 = ns.c.post("/api/ai/pro/approve", json={"proposal_id": pid})
    assert r1.status_code == 200, r1.text[:300]
    r2 = ns.c.post("/api/ai/pro/approve", json={"proposal_id": pid})
    assert r2.status_code == 409
    assert r2.json()["detail"] == ceviri.t("onay.hata.zatenKarar", durum="approved")


def test_reject_BILINMEYEN_oneri_404(ns):
    """Var olmayan öneri reddedilir → 404 + `onay.hata.oneriYok`."""
    r = ns.c.post("/api/ai/pro/reject", json={"proposal_id": "yok-boyle-bir-oneri", "reason": "x"})
    assert r.status_code == 404
    assert ceviri.t("onay.hata.oneriYok") in r.json()["detail"]


def test_onay_izi_denetim_kaydi_YAZILAMASA_da_karar_kaydi_yazilir(monkeypatch):
    """session_events yazımı DB kilidiyle düşer → uyarı; AI Pro karar kaydı yine yazılır ve True döner."""
    from servers import api_server as api

    kayit = []

    class _DB:
        def record_session_event(self, *a, **k):
            raise sqlite3.OperationalError("database is locked")

        def ai_pro_karari_yaz(self, pid, karar, **k):
            kayit.append((pid, karar, k["operator_email"], k["patient_uuid"]))

    monkeypatch.setattr(api, "_get_treatment_db", lambda: _DB())
    rec = {"id": "p-1", "operator": "hekim@test.local", "specs": {"patient_id": "h-9", "patient_name": "Boncuk"}}
    assert air._kaydet_onay_izi("ai_proposal_approved", rec) is True
    assert kayit == [("p-1", "onaylandi", "hekim@test.local", "h-9")]


# ───────────────────────────── /start ─────────────────────────────


def test_start_GUNCELLEME_suruyorsa_409_onay_TUKETILMEZ(ns, monkeypatch):
    """update_manager uygulama bayrağı açık → 409 `guncellemeSuruyor`; onay 'approved' kalır."""
    from servers import ai_approval, update_manager

    monkeypatch.setattr(update_manager, "_applying", True)
    monkeypatch.setattr(update_manager, "_applying_since", time.monotonic())
    pid = _oneri()
    r = ns.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 409 and r.json()["detail"] == ceviri.t("ai.pro.hata.guncellemeSuruyor")
    assert ai_approval.get(pid)["status"] == "approved"


def test_start_guncelleme_DENETIMI_bozuksa_ENGELLEMEZ_sonraki_kapiya_gecer(ns, monkeypatch):
    """Güncelleme bayrağının zaman damgası bozuk (TypeError) → denetim yutulur; geçersiz öneri kendi kapısında 428 alır."""
    from servers import update_manager

    monkeypatch.setattr(update_manager, "_applying", True)
    monkeypatch.setattr(update_manager, "_applying_since", "bozuk")
    r = ns.c.post("/api/ai/pro/start", json={"proposal_id": "olmayan-oneri"})
    assert r.status_code == 428, r.text[:300]


def test_start_muhurdeki_model_BILINMIYORSA_422_onay_TUKETILMEZ(ns):
    """Mühürde model 'zurafa' → 422 (sağlayıcı hatası metni); onay 'approved' kalır, döngü açılmaz."""
    from servers import ai_approval

    pid = _oneri(model="zurafa")
    r = ns.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 422 and "zurafa" in r.json()["detail"]
    assert ai_approval.get(pid)["status"] == "approved" and ns.air._ai_loop_active is False


def test_start_STM_red_denetimi_BOZUKSA_baslatmayi_ENGELLEMEZ(ns, monkeypatch):
    """`stm_komutlari_reddediyor` hata verir → başlatma sürer: 200 'AI Pro Closed-Loop Started', onay tüketilir."""
    from servers import ai_approval, live_state

    def _bozuk():
        raise RuntimeError("stm durum tablosu okunamadı")

    monkeypatch.setattr(live_state, "stm_komutlari_reddediyor", _bozuk)
    pid = _oneri()
    r = ns.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["message"] == "AI Pro Closed-Loop Started" and r.json()["organId"] == 2
    assert ai_approval.get(pid)["status"] == "consumed"


def test_start_dogrulama_ile_tuketim_ARASINDA_onay_tuketildiyse_428_dongu_ACILMAZ(ns, monkeypatch):
    """Eşzamanlı başka başlatma onayı tüketti (DB hazırlık denetimi penceresinde) → 428 `onayKullanildi`; döngü bayrağı inik."""
    from servers import ai_approval

    pid = _oneri()

    def _kayit_hazir():
        ai_approval.consume(pid)  # yarışın öteki kolu
        return True, ""

    monkeypatch.setattr(ns.api, "_kayit_db_hazir", _kayit_hazir)
    r = ns.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 428 and r.json()["detail"] == ceviri.t("onay.hata.onayKullanildi")
    assert ns.air._ai_loop_active is False


def test_start_seans_kaydi_BEKLENMEDIK_hatayla_yazilamasa_da_dongu_baslar(ns, monkeypatch):
    """start_ai_session RuntimeError (KayitAcilamadi DEĞİL) → günlüğe yazılır, uç 200, döngü iş parçacığı başlatılır."""
    baslayan = []

    def _seans(*a, **k):
        raise RuntimeError("seans alanı yazılamadı")

    monkeypatch.setattr(ns.api, "start_ai_session", _seans)
    monkeypatch.setattr(ns.air, "_ai_pro_loop", lambda muhur: baslayan.append(muhur["onay"]))
    pid = _oneri()
    r = ns.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 200, r.text[:300]
    assert ap.dongu_bitir(ns.air) == 0
    assert baslayan == [pid]


def test_start_SIRASINDA_acil_durdurma_gelirse_409_ve_seans_PASIF(ns, monkeypatch):
    """Seans yazıldıktan sonra mandal kurulur → 409 `baslatmaSirasindaDurduruldu`; kendi seansı pasif; döngü açılmaz; onay
    YANAR ('consumed', geri VERİLMEZ — D1.81 "güvenli yön") → mandal sıfırlansa da AYNI onayla `/start` 428 `onayKullanildi`
    alır, döngü yine açılmaz (TUR 2 · KP1-IB.5: iptalde onayı geri veren mutant bu iddiayla düşer)."""
    from servers import ai_approval
    from utils import estop_mandali

    gercek = ns.api.start_ai_session
    baslayan = []

    def _seans_sonra_estop(*a, **k):
        gercek(*a, **k)
        estop_mandali.mandalla("kp-test acil durdurma")

    monkeypatch.setattr(ns.api, "start_ai_session", _seans_sonra_estop)
    monkeypatch.setattr(ns.air, "_ai_pro_loop", lambda muhur: baslayan.append(1))
    pid = _oneri()
    r = ns.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 409, r.text[:300]
    assert r.json()["detail"] == ceviri.t("ai.pro.hata.baslatmaSirasindaDurduruldu")
    with ns.api._session_lock:
        s = dict(ns.api._active_session)
    assert s.get("onay_kimligi") == pid and s.get("is_active") is False
    assert ns.air._ai_loop_active is False and baslayan == []
    assert ai_approval.get(pid)["status"] == "consumed"
    # Operatör mandalı sıfırlar, gerçek seans yazıcısı geri gelir: eski onay yeniden başlatma yetkisi VERMEZ.
    estop_mandali.sifirla("kp-test sifirla")
    monkeypatch.setattr(ns.api, "start_ai_session", gercek)
    r2 = ns.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r2.status_code == 428, r2.text[:300]
    assert r2.json()["detail"] == ceviri.t("onay.hata.onayKullanildi")
    assert ns.air._ai_loop_active is False and baslayan == []
    assert ai_approval.get(pid)["status"] == "consumed"


def test_start_SIRASINDA_acil_durdurma_ve_seans_OKUNAMAZSA_yine_409_dongu_ACILMAZ(ns, monkeypatch):
    """Seans yazıldı, mandal kuruldu ve oturum okunamaz hâle geldi → pasife alma hatası yutulur; yanıt yine 409, döngü yok."""
    from utils import estop_mandali

    gercek = ns.api.start_ai_session
    eski = {}
    baslayan = []

    def _seans_sonra_estop(*a, **k):
        gercek(*a, **k)
        estop_mandali.mandalla("kp-test acil durdurma")
        eski["s"] = ns.api._active_session
        ns.api._active_session = None

    monkeypatch.setattr(ns.api, "start_ai_session", _seans_sonra_estop)
    monkeypatch.setattr(ns.air, "_ai_pro_loop", lambda muhur: baslayan.append(1))
    try:
        r = ns.c.post("/api/ai/pro/start", json={"proposal_id": _oneri()})
    finally:
        if "s" in eski:
            ns.api._active_session = eski["s"]
    assert r.status_code == 409 and r.json()["detail"] == ceviri.t("ai.pro.hata.baslatmaSirasindaDurduruldu")
    assert ns.air._ai_loop_active is False and baslayan == []


# ───────────────────────────── stop_ai_pro ─────────────────────────────


def test_stop_seans_OKUNAMASA_da_durdurma_tamamlanir(ns, monkeypatch):
    """`_active_session` okunamaz → niyet / pasife alma yutulur; yanıt success, döngü bayrağı iner, sahip temizlenir VE bobin
    STOP'u seans okumasına BAĞLI DEĞİL: STM 1-7'nin her birine `update_coil(start=False)` (START YOK) + ESP bobin 8'e tek STOP
    yayını gider (TUR 2 · KP1-IB.4: STOP'u yalnız okunabilen seansta gönderen mutant bu iddiayla düşer)."""
    hw = _KayitDonanim()  # EN ALT kat: donanım kontrolcüsünün `update_coil` çağrıları kaydedilir
    monkeypatch.setattr(ns.api.state, "hardware", hw)
    monkeypatch.setattr(ns.air, "_ai_loop_active", True)
    monkeypatch.setattr(ns.air, "_ai_owner_client", "sahip-x")
    eski = ns.api._active_session  # aparat yıkımı monkeypatch'ten ÖNCE koşar → elle geri konur
    ns.api._active_session = None
    try:
        r = air.stop_ai_pro()
    finally:
        ns.api._active_session = eski
    assert r == {"status": "success", "message": "AI Pro Closed-Loop Stopped"}
    assert ns.air._ai_loop_active is False and ns.air._ai_owner_client == ""
    assert hw.cagri == [(cid, False) for cid in range(1, 8)]
    assert [konu for konu, _y in ns.yayin] == ["pemf/coil/8/control"]
    assert ns.yayin[0][1]["command"] == "stop"


def test_stop_ESP_STOP_yayini_HATA_verse_de_E_baglami_temizlenir_seans_pasif(ns, monkeypatch):
    """Bobin 8 (ESP) STOP yayını OSError → STOP katmanı hatası yutulur; canlı E bağlamı temizlenir, AI seansı pasif."""
    from servers import efield_live as ef

    ap.muhurlu_seans_yaz(ns.api)
    monkeypatch.setattr(ns.api.state, "hardware", None)
    yayin = []

    def _yayinla(konu, yuk):
        yayin.append(konu)
        raise OSError("broker soketi kapalı")

    monkeypatch.setattr(ns.api, "_mqtt_publish", _yayinla)
    ef.set_context([{"centroid_cabin_mm": [10.0, 20.0, 30.0], "organ_id": 1}], model="fantom")
    try:
        assert air.stop_ai_pro()["status"] == "success"
        assert yayin == ["pemf/coil/8/control"]
        assert ef.get_context() is None
        with ns.api._session_lock:
            assert ns.api._active_session.get("is_active") is False
    finally:
        ef.set_context([])


def test_stop_canli_E_baglami_TEMIZLENEMESE_de_seans_pasife_alinir(ns, monkeypatch):
    """efield_live.set_context hata → yutulur; AI seansı pasif, yanıt success."""
    from servers import efield_live as ef

    ap.muhurlu_seans_yaz(ns.api)

    def _bozuk(*a, **k):
        raise RuntimeError("E bağlam kilidi")

    monkeypatch.setattr(ef, "set_context", _bozuk)
    assert air.stop_ai_pro()["status"] == "success"
    with ns.api._session_lock:
        assert ns.api._active_session.get("is_active") is False


# ───────────────────────────── _ai_pro_satirini_kapat ─────────────────────────────


def test_satir_BASKA_yolca_kapatildiysa_muhru_EZILMEZ(monkeypatch):
    """DB'de satır 'completed' → `_finalize_session_db` ÇAĞRILMAZ; DB hatası da yükselmez (günlük)."""
    from servers import api_server as api

    finalize = []
    monkeypatch.setattr(api, "_finalize_session_db", lambda *a, **k: finalize.append(a))
    monkeypatch.setattr(
        api,
        "_get_treatment_db",
        lambda: types.SimpleNamespace(get_session_details=lambda i: {"session_status": "completed"}),
    )
    air._ai_pro_satirini_kapat({"db_session_id": 7, "start_time": 1.0}, "ai-pro-durdurma")
    assert finalize == []

    def _kilitli(i):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(api, "_get_treatment_db", lambda: types.SimpleNamespace(get_session_details=_kilitli))
    assert air._ai_pro_satirini_kapat({"db_session_id": 7}, "ai-pro-durdurma") is None
    assert finalize == []


# ───────────────────────────── /hazirlik/baslat ─────────────────────────────


def test_hazirlik_modele_AIT_OLMAYAN_hedef_varsayilana_cekilir_calisan_onizleme_IKINCI_kez_acilmaz(ns, monkeypatch):
    """Kedi + organ 9 (0-6 dışı) → `_ai_organ_id` = varsayılan 0; önizleme zaten çalışıyor → `hazirlikCalisiyor`, iş parçacığı yok."""
    monkeypatch.setattr(ns.air, "_ai_hazirlik_active", True)
    monkeypatch.setattr(ns.air, "_ai_organ_id", 4)
    monkeypatch.setattr(ns.air, "_ai_hazirlik_thread", None)
    r = ns.c.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 9, "model": "kedi"})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["message"] == ceviri.t("ai.pro.mesaj.hazirlikCalisiyor")
    assert ns.air._ai_organ_id == 0 and ns.air._ai_hazirlik_thread is None


# ───────────────────────────── /frame ─────────────────────────────


def test_frame_BUYUK_kare_960_pikselin_altina_kucultulur(ns, monkeypatch):
    """Seans yok, taze önbellek (lokalizasyon gerekmez) → 1200×900 kare 960×720 olarak döner."""

    async def _buyuk(*a, **k):
        return np.full((900, 1200, 3), 120, np.uint8)

    monkeypatch.setattr(ns.air, "_decode_image", _buyuk)
    monkeypatch.setattr(ns.air, "_ai_relocalize", False)
    ns.air._ai_organ_cache.update({"organ_id": ns.air._ai_organ_id, "at": time.time(), "overlay_bgr": None})
    r = ap.kare(ns)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert (j["image_w"], j["image_h"]) == (960, 720)
    img = cv2.imdecode(np.frombuffer(base64.b64decode(j["image_base64"]), np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[:2] == (720, 960)


class _CalisanDonanim:
    def __init__(self):
        self.baslat = []

    def update_coil(self, cid, *a, start=True, **k):
        if start:
            self.baslat.append(cid)
        return True

    def calisan_bobin_durumu(self):
        return {}


def test_frame_SURUS_sonrasi_canli_durum_YAZILAMASA_da_surulmus_sayilir(ns, monkeypatch):
    """Mühürlü seans + hedef bulundu + geçerli doz → 7 bobin sürülür; canlı durum güncellemesi hata verse de driven=True."""
    ap.muhurlu_seans_yaz(ns.api)
    hw = _CalisanDonanim()
    monkeypatch.setattr(ns.api.state, "hardware", hw)

    def _canli(**k):
        raise RuntimeError("canlı durum kilidi")

    monkeypatch.setattr(ns.api, "update_live_session_state", _canli)
    monkeypatch.setattr(ns.air, "_ai_relocalize", True)
    r = ap.kare(ns)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["driven"] is True and j["sessionActive"] is True
    assert hw.baslat == [1, 2, 3, 4, 5, 6, 7]


def test_frame_kapi_REDDI_500e_cevrilmez_422_kalir(ns, monkeypatch):
    """Görüntü kapısı HTTPException(422) → /frame 422 + aynı detay (genel 'AI Pro kare' 500'ü değil)."""
    from fastapi import HTTPException

    async def _ret(*a, **k):
        raise HTTPException(status_code=422, detail="kare-kapisi-reddi")

    monkeypatch.setattr(ns.air, "_decode_image", _ret)
    r = ap.kare(ns)
    assert r.status_code == 422 and r.json()["detail"] == "kare-kapisi-reddi"


def test_frame_kayip_stopu_nesil_ARTIRILAMASA_da_STOP_denenir_STOP_hatasi_YUKSELMEZ(ns, monkeypatch):
    """kayip_nesli_artir hata → STOP iş parçacığı yine çağrılır; o da hata verir → `_frame_kayip_stopu` sessizce döner."""
    from utils import estop_mandali

    cagri = []

    def _nesil():
        raise RuntimeError("nesil kilidi")

    async def _durdur(fn, *a, ad=""):
        cagri.append((fn.__name__, list(a[0]), ad))
        raise RuntimeError("STOP iş parçacığı açılamadı")

    monkeypatch.setattr(estop_mandali, "kayip_nesli_artir", _nesil)
    monkeypatch.setattr(ns.api, "_durdurma_is_parcaciginda", _durdur)
    assert _kos(air._frame_kayip_stopu("hedef bulunamadı", 3)) is None
    assert cagri == [("_stop_session_coils", [1, 2, 3, 4, 5, 6, 7], "frame-kayip-stop")]


# ───────────────────────────── _ai_seansi_pasife_al ─────────────────────────────


class _BozukDonanim:
    @property
    def coils_state(self):
        raise RuntimeError("bobin tablosu kilitli")

    def update_coil(self, *a, **k):
        raise RuntimeError("seri port kapalı")


def test_pasife_al_bobin_durumu_OKUNAMASA_ve_STOP_katmani_hata_verse_de_seans_PASIF(ns, monkeypatch):
    """Kendi seansı (onay eşleşir, bobin 1 + 8): bobin durumu okunamaz + bobin 8 ESP STOP yayını OSError → seans yine pasif,
    canlı durum 'Sistem Hazır'."""
    ap.muhurlu_seans_yaz(ns.api, coil_ids=[1, 8])
    monkeypatch.setattr(ns.api.state, "hardware", _BozukDonanim())
    yayin = []

    def _yayinla(konu, yuk):
        yayin.append(konu)
        raise OSError("broker soketi kapalı")

    monkeypatch.setattr(ns.api, "_mqtt_publish", _yayinla)
    canli = []
    monkeypatch.setattr(ns.api, "update_live_session_state", lambda **k: canli.append(k))
    air._ai_seansi_pasife_al("kamera açılamadı", {"onay": "test-onay"})
    with ns.api._session_lock:
        assert ns.api._active_session.get("is_active") is False
    assert canli == [{"is_active": False, "mode": "Sistem Hazır"}]
    assert yayin == ["pemf/coil/8/control"]


def test_pasife_al_seans_OKUNAMAZSA_istisna_YUKSELMEZ(monkeypatch):
    """`_active_session` okunamaz → hata günlüğe; çağırana istisna gitmez."""
    from servers import api_server as api

    monkeypatch.setattr(api, "_active_session", None)
    assert air._ai_seansi_pasife_al("model yüklenemedi") is None


# ───────────────────────────── _drive_coils_ai_pro ─────────────────────────────


class _KayitDonanim:
    def __init__(self, stop_patlasin=()):
        self.cagri = []
        self.stop_patlasin = set(stop_patlasin)

    def update_coil(self, cid, *a, start=True, **k):
        self.cagri.append((cid, start))
        if not start and cid in self.stop_patlasin:
            raise RuntimeError("seri port yazılamadı")
        return True

    def calisan_bobin_durumu(self):
        raise RuntimeError("tel durumu okunamadı")


def test_surus_DONANIM_yoksa_hicbir_bobin_surulmez(ns, monkeypatch):
    """Mühürlü seans var ama state.hardware None → []."""
    ap.muhurlu_seans_yaz(ns.api)
    monkeypatch.setattr(ns.api.state, "hardware", None)
    assert air._drive_coils_ai_pro([0.3] * 7, [0.0] * 7) == []


def test_surus_PLAN_DISI_bobin_tel_durumu_okunamasa_da_STOP_alir_STOP_hatasi_yutulur(ns, monkeypatch):
    """Plan dışı {3, 5}: START gitmez; tel durumu okunamaz → güvenli taraf: ikisine de STOP denenir (3'ünki hata verir);
    sürülen = [1, 2, 4, 6, 7]."""
    ap.muhurlu_seans_yaz(ns.api)
    hw = _KayitDonanim(stop_patlasin={3})
    monkeypatch.setattr(ns.api.state, "hardware", hw)
    monkeypatch.setattr(ns.air, "_ai_pro_plan_disi", {"onay": "test-onay", "bobinler": {3, 5}})
    surulen = air._drive_coils_ai_pro([0.3] * 7, [0.0] * 7)
    assert surulen == [1, 2, 4, 6, 7]
    assert [c for c, s in hw.cagri if s] == [1, 2, 4, 6, 7]
    assert [c for c, s in hw.cagri if not s] == [3, 5]


# ───────────────────────────── _localize_organ_cpu ─────────────────────────────


def test_cpu_lokalizasyon_gecici_dosya_motorca_SILINMIS_olsa_da_hedef_doner(monkeypatch, tmp_path):
    """Öngörücü geçici kareyi tüketir (silinir) → ürünün silmesi hata verir ama yutulur; organ 2 hedefi döner."""
    import os
    import tempfile

    gecici = tmp_path / "gecici"
    gecici.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(gecici))

    class _Organ:
        def predict(self, yol, render=True, target_oid=None):
            os.unlink(yol)
            return {"organs": {2: {"coord_cabin_cm": [1.0, 1.0, 1.0], "reliability": 0.8}}}

    monkeypatch.setitem(air._models, "cat_organ", _Organ())
    lokal, x, y, z, rel = air._localize_organ_cpu(np.zeros((16, 16, 3), np.uint8), 2)[:5]
    assert (lokal, x, y, z, rel) == (True, 10.0, 10.0, 10.0, 0.8)
    assert [p.name for p in gecici.iterdir()] == []


# ───────────────────────────── hazırlık teşhis yardımcıları ─────────────────────────────


def test_model_hazir_mi_COZUCU_hata_verirse_model_yok_ve_kok_neden(monkeypatch):
    """yan_dosya_coz PermissionError → ('model_yok', 'PermissionError: …')."""
    from utils import model_downloader as md

    def _engel(*a, **k):
        raise PermissionError("[WinError 5] Erişim engellendi")

    monkeypatch.setattr(md, "yan_dosya_coz", _engel)
    assert air._model_hazir_mi("ai_hub/x/y.onnx") == ("model_yok", "PermissionError: [WinError 5] Erişim engellendi")


def test_xai_zinciri_grad_cam_ICE_AKTARILAMAZSA_kod_hatali_ve_hazir_DEGIL(monkeypatch):
    """grad_cam modülü içe aktarılamaz → grad_cam='kod_hatali' + sebep; bozuk spec'li EM modülü atlanır; hazir False."""
    monkeypatch.setitem(sys.modules, "ai_hub.xai_utils.grad_cam", None)
    monkeypatch.setitem(sys.modules, "ai_hub.em_petri", types.ModuleType("ai_hub.em_petri"))
    d = air._xai_zinciri_durumu()
    assert d["grad_cam"] == "kod_hatali" and "ai_hub.xai_utils.grad_cam" in d["grad_cam_sebep"]
    assert "em_petri" not in d["em_ref_stats_eksik"]
    assert d["hazir"] is False


def test_pip_yasagi_durumu_OKUNAMAZSA_etkin_degil_ve_sebep(monkeypatch):
    """runtime_guards.kurulum_yasagi_etkin_mi hata → {'etkin': False, 'sebep': 'RuntimeError: …'}."""
    from utils import runtime_guards

    def _bozuk():
        raise RuntimeError("meta_path okunamadı")

    monkeypatch.setattr(runtime_guards, "kurulum_yasagi_etkin_mi", _bozuk)
    assert air._pip_yasagi_durumu() == {"etkin": False, "sebep": "RuntimeError: meta_path okunamadı"}
