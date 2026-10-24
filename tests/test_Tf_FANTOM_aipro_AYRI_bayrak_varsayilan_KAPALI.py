# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T-f (Y195, GÜVENLİK — T2B B1, T3 açık #4) — FANTOM AI Pro sürüşü AYRI, VARSAYILAN KAPALI bayrakta; `PEMF_ARASTIRMA_AIPRO` yalnız
PETRİ'yi açar.

ÖLÇÜLEN KUSUR (T2B / T3, 2026-10-23): fantom hattı boş kabinde ve petri karelerinde 1–61 "tümör" buldu ve sonucu "sürülebilir" dedi;
`PEMF_ARASTIRMA_AIPRO` petri İÇİN açıldığında (bu makine + LattePanda, Y145) fantomun öneri / onay / BAŞLATMA / sürüş-anı kapısı da
açılıyordu (`_arastirma_aipro_kapisi`: kedi değilse tek bayrak).
SÖZLEŞME: fantom → yalnız `PEMF_ARASTIRMA_AIPRO_FANTOM` (yok / boş / bozuk = KAPALI); petri ve öteki araştırma modelleri → genel bayrak;
kedi → Y142. Kapı BACKEND'de, GERÇEK uçlarda (propose / approve / start + sürüş-anı mühür denetimi). Analiz / önizleme bayraktan
bağımsız (kapı çağrılmaz). Taşıyıcı: `deploy/device.env` + launcher `install.rs`. Sağlayıcı sahte (yalnız CV boru hattı yerine).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]


def _sag(ad: str):
    class _Sag:
        title = f"Sahte {ad}"
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
            return f"{ad} {hedef_id}"

        def ipucu(self, ozne_var, hedef_adi):
            return "sahte ipucu"

        def xai_sensitivity(self, *a, **k):
            return None

    s = _Sag()
    s.ad = ad
    return s


@pytest.fixture()
def env(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setitem(hedef.SAGLAYICILAR, "fantom", _sag("fantom"))
    monkeypatch.setitem(hedef.SAGLAYICILAR, "petri", _sag("petri"))
    # Bu makinenin kullanıcı ortamı: petri bayrağı AÇIK (Y145 / T3) — fantomu AÇMAMALI.
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.delenv("PEMF_ARASTIRMA_AIPRO_FANTOM", raising=False)

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


def _oner(client, model: str):
    return client.post("/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": model})


def test_KRITIK_petri_bayragi_ACIKKEN_FANTOM_onerisi_409_ve_metin_KAPALI_der(env):
    air, apis, client, taze, mp = env
    taze("fantom")
    r = _oner(client, "fantom")
    assert r.status_code == 409, f"petri bayrağı açıkken fantom önerisi verildi ({r.status_code}) — sahte tümörle doz"
    detay = r.json().get("detail", "")
    assert "Fantom AI Pro sürüşü KAPALI" in detay and "elle" in detay, detay


def test_KARSIT_petri_bayragi_PETRIYI_acar(env):
    air, apis, client, taze, mp = env
    taze("petri")
    r = _oner(client, "petri")
    assert r.status_code == 200 and r.json()["specs"]["model"] == "petri", r.text[:200]


def test_KARSIT_fantom_KENDI_bayragiyla_acilir(env):
    air, apis, client, taze, mp = env
    mp.setenv("PEMF_ARASTIRMA_AIPRO_FANTOM", "1")
    taze("fantom")
    r = _oner(client, "fantom")
    assert r.status_code == 200 and r.json()["specs"]["model"] == "fantom", r.text[:200]


@pytest.mark.parametrize("deger", ["", "0", "evet", " "])
def test_KRITIK_fantom_bayragi_bozuk_ya_da_bos_KAPALI(env, deger):
    air, apis, client, taze, mp = env
    mp.setenv("PEMF_ARASTIRMA_AIPRO_FANTOM", deger)
    taze("fantom")
    assert _oner(client, "fantom").status_code == 409


def test_KRITIK_fantom_bayragi_PETRIYI_acmaz(env):
    air, apis, client, taze, mp = env
    mp.delenv("PEMF_ARASTIRMA_AIPRO", raising=False)
    mp.setenv("PEMF_ARASTIRMA_AIPRO_FANTOM", "1")
    taze("petri")
    assert _oner(client, "petri").status_code == 409, "fantom bayrağı petri sürüşünü de açtı"


def test_KRITIK_fantom_onayi_bayrak_KAPANINCA_baslatilamaz_ve_SURUS_ANINDA_reddedilir(env):
    air, apis, client, taze, mp = env
    mp.setenv("PEMF_ARASTIRMA_AIPRO_FANTOM", "1")
    taze("fantom")
    r = _oner(client, "fantom")
    assert r.status_code == 200, r.text[:200]
    pid = r.json()["proposalId"]
    assert client.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": "t@t"}).status_code == 200
    mp.delenv("PEMF_ARASTIRMA_AIPRO_FANTOM", raising=False)  # fantom bayrağı kapatıldı (petri bayrağı AÇIK kalıyor)
    rs = client.post("/api/ai/pro/start", json={"proposal_id": pid, "client_id": "S"})
    assert rs.status_code == 409, f"fantom bayrağı kapandığı hâlde eldeki onay başlatıldı ({rs.status_code})"
    assert air._ai_loop_active is False
    # Sürüş anı: mühür fantomsa ve fantom bayrağı kapalıysa (petri bayrağı açık olsa da) SÜRÜLMEZ.
    air._ai_hedef_modeli = "fantom"
    assert air._muhur_surulebilir_mi({"model": "fantom", "hedef": 1}) is False


def test_KRITIK_durum_uclari_fantom_bayragini_AYRI_bildirir(env):
    air, apis, client, taze, mp = env
    st = client.get("/api/ai/pro/status").json()
    assert st.get("arastirmaAiProAcik") is True and st.get("arastirmaAiProFantomAcik") is False, st
    blok = client.get("/api/ai/hazirlik").json().get("arastirmaAiPro") or {}
    assert blok.get("fantomAcik") is False and blok.get("fantomBayrak") == "PEMF_ARASTIRMA_AIPRO_FANTOM", blok
    mp.setenv("PEMF_ARASTIRMA_AIPRO_FANTOM", "1")
    assert client.get("/api/ai/pro/status").json().get("arastirmaAiProFantomAcik") is True


def test_YAPISAL_fantom_bayragi_device_env_ve_launcherda_TASINIR_varsayilan_KAPALI():
    env_dosyasi = (KOK / "deploy" / "device.env").read_text(encoding="utf-8")
    assert "\nPEMF_ARASTIRMA_AIPRO_FANTOM=0" in env_dosyasi.replace("\r\n", "\n"), (
        "device.env fantom bayrağını KAPALI taşımıyor"
    )
    rs = (KOK / "launcher" / "core" / "src" / "install.rs").read_text(encoding="utf-8")
    assert 'pub const ENV_ARASTIRMA_AIPRO_FANTOM: &str = "PEMF_ARASTIRMA_AIPRO_FANTOM";' in rs
    i = rs.index("ENV_ARASTIRMA_AIPRO_FANTOM.to_string(),")
    assert '.unwrap_or_else(|| "0".to_string())' in rs[i : i + 220], "launcher varsayılanı KAPALI değil"
