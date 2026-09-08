# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ARAŞTIRMA AI PRO BAYRAĞI — tezgâh doğrulaması gelmeden fantom/petri BOBİN SÜRMEZ (2026-09-09).

NEDEN BAYRAK: `phantom_cv`/`petri_cv` koordinat dönüşümü ArUco modunda marker→kabin ROTASYONUNU
uygulamıyor (`ray_cabin = ray_marker`) ve kesişimi kabin Z=`plate_z` düzleminde alıyor; kedi hattı
(cat_organ) ise kabin-merkezli PnP kullanıyor. İki hattın AYNI 3B çerçeveyi ürettiği KANITLANMADI
ve fantom modelinin eğitim aralığı çok dar. Yanlış çerçeve = bobinlerin YANLIŞ NOKTAYA odaklanması.
Plan kararı #6 (hoca ile netleşecek) ve karakterizasyon golden'ı:
tests/test_koordinat_donusumu_karakterizasyon.py

NEDEN BACKEND'DE, UI'DA DEĞİL: AI Pro uçları sahip kararıyla auth-muaf ve backend istemci
profilini bilmez. Yalnız düğmeyi gizlemek yetmezdi — eski/yanlış bir istemci ya da curl doğrudan
propose → approve → start yapabilirdi. Bayrak `deploy/device.env` ile taşınır (kurulum onu NSSM
servis ortamına yazar; backend `.env`i KENDİ okumaz).

Bayrak KEDİYİ ETKİLEMEZ (veteriner akışı bayraktan bağımsız) ve analiz/önizleme yollarını da
kapatmaz — yalnız kedi DIŞI modelle DOZ ÖNERİSİ ve SEANS BAŞLATMA kapılıdır.
"""

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def env(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis

    class _Sag:
        ad = "sahte"
        title = "Sahte Araştırma Modeli"
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
    monkeypatch.delenv("PEMF_ARASTIRMA_AIPRO", raising=False)  # varsayılan KAPALI

    snap_cache = dict(air._ai_organ_cache)
    snap = (air._ai_hedef_modeli, air._ai_organ_id, air._ai_owner_client)
    with apis._session_lock:
        sess_snap = dict(apis._active_session)
    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    air._ai_owner_client = ""
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(apis, "update_live_session_state", lambda *a, **k: None)
    monkeypatch.setattr(apis, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: None)
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": False, "mode": "Sistem Hazır"})

    def taze(model: str, hedef_id: int = 1):
        air._ai_hedef_modeli = model
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

    yield air, apis, TestClient(apis.app), taze, monkeypatch

    air._ai_loop_active = False
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_hedef_modeli, air._ai_organ_id, air._ai_owner_client = snap
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess_snap)


def test_KRITIK_bayrak_KAPALIYKEN_arastirma_modeli_onerisi_409(env):
    """MUTASYON: `propose`daki `_arastirma_aipro_kapisi(...)` çağrısını kaldırın → KIRMIZI
    (doğrulanmamış çerçeveyle doz önerilir ve onaylanabilir)."""
    air, apis, client, taze, mp = env
    taze("sahte")

    r = client.post("/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": "sahte"})

    assert r.status_code == 409, f"bayrak kapalıyken araştırma modeli önerisi verildi ({r.status_code})"
    detay = r.json().get("detail", "")
    assert "tezgâh" in detay.lower() or "tezgah" in detay.lower(), f"409 metni nedeni söylemiyor: {detay!r}"
    assert "bobin sürülmez" in detay.lower(), f"metin ne yapılabildiğini söylemiyor: {detay!r}"


def test_KRITIK_bayrak_KEDIYI_etkilemez(env):
    """Veteriner akışı bayraktan BAĞIMSIZ: bayrak kapalıyken kedi önerisi çalışmalı."""
    air, apis, client, taze, mp = env
    taze("kedi", hedef_id=2)
    mp.setattr(air, "_predict_and_drive", lambda *a, **k: ([0.2] * 7, [0.0] * 7, 0.1))

    r = client.post("/api/ai/pro/propose", json={"organ_id": 2, "duration_minutes": 5})

    assert r.status_code == 200, f"bayrak kedi akışını da kapattı ({r.status_code}): {r.text[:200]}"
    assert r.json()["specs"]["model"] == "kedi"


def test_KRITIK_bayrak_ACIKKEN_arastirma_modeli_gecer(env):
    """Karşıt-kanıt: kapı "her zaman reddet" mutasyonuna dönüşmemeli."""
    air, apis, client, taze, mp = env
    mp.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    taze("sahte")

    r = client.post("/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": "sahte"})

    assert r.status_code == 200, f"bayrak açıkken de reddedildi ({r.status_code}): {r.text[:200]}"
    assert r.json()["specs"]["model"] == "sahte"


def test_KRITIK_bayrak_ACIKKEN_alinan_onay_bayrak_KAPANINCA_baslatilamaz(env):
    """Tezgâh sonucu olumsuz çıkıp bayrak kapatılırsa, ELDEKİ onay da sürülmemeli.
    MUTASYON: `start`taki bayrak kontrolünü kaldırın → KIRMIZI."""
    air, apis, client, taze, mp = env
    mp.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    taze("sahte")
    r = client.post("/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": "sahte"})
    assert r.status_code == 200, r.text[:200]
    pid = r.json()["proposalId"]
    assert client.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": "t@t"}).status_code == 200

    mp.delenv("PEMF_ARASTIRMA_AIPRO", raising=False)  # bayrak KAPATILDI
    rs = client.post("/api/ai/pro/start", json={"proposal_id": pid, "client_id": "S"})

    assert rs.status_code == 409, f"bayrak kapandığı hâlde eldeki onay başlatıldı ({rs.status_code})"
    assert air._ai_loop_active is False, "reddedilen start `_ai_loop_active` bayrağını kirletti"
    with apis._session_lock:
        assert not bool(apis._active_session.get("is_active")), "reddedilen start oturumu aktif bıraktı"


def test_KRITIK_bayrak_durumu_STATUS_ve_HAZIRLIK_uclarinda_gorunur(env):
    """Panel kartları "Deneysel — tezgâh doğrulaması bekleniyor" diye pasifleştirebilsin; sahada
    "neden Onayla açılmıyor?" sorusu tek istekle yanıtlanabilsin (frozen EXE'de env'in servise
    geçtiğinin kanıtı da bu)."""
    air, apis, client, taze, mp = env

    st = client.get("/api/ai/pro/status").json()
    assert st.get("arastirmaAiProAcik") is False, "status bayrağı bildirmiyor"

    hz = client.get("/api/ai/hazirlik").json()
    blok = hz.get("arastirmaAiPro") or {}
    assert blok.get("acik") is False, f"hazırlık ucu bayrağı bildirmiyor: {blok}"
    assert blok.get("bayrak") == "PEMF_ARASTIRMA_AIPRO", f"bayrak adı yanlış: {blok}"
    assert blok.get("neden"), "kapalı bayrak için gerekçe metni yok"

    mp.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    st2 = client.get("/api/ai/pro/status").json()
    assert st2.get("arastirmaAiProAcik") is True, "bayrak açıldı ama status hâlâ kapalı diyor"


def test_YAPISAL_bayrak_device_env_ile_TASINIR(env):
    """Bayrağın taşıyıcısı yazılı olmalı: `deploy/device.env` satırı kurulumla servis ortamına
    iner (backend `.env` dosyasını KENDİ okumaz — api_server bunu açıkça belirtir).
    MUTASYON: satırı device.env'den silin → KIRMIZI (bayrak sahada hiç açılamaz)."""
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    env_dosyasi = (kok / "deploy" / "device.env").read_text(encoding="utf-8")
    assert "PEMF_ARASTIRMA_AIPRO=" in env_dosyasi, (
        "deploy/device.env bayrağı taşımıyor — saha kurulumunda araştırma AI Pro hiç açılamaz "
        "(kurulum env'leri bu dosyadan NSSM'e yazar)"
    )
    satir = [s for s in env_dosyasi.splitlines() if s.startswith("PEMF_ARASTIRMA_AIPRO=")]
    assert satir == ["PEMF_ARASTIRMA_AIPRO=0"], f"varsayılan KAPALI olmalı (tezgâh doğrulanmadı): {satir}"
