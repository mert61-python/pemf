# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""JETON KAPISI AI UÇLARINA BAĞLANIR — JETON-SISTEMI Adım 4 ("EN KRİTİK ADIM"), 2026-08-22.

ÖLÇÜLEN DURUM: `servers/jeton.py` 16 testle kilitliydi ama HİÇBİR üretim kodundan çağrılmıyordu
(`JetonYoneticisi` yalnız modülün kendisinde + testlerde). `PEMF_JETON_ENFORCED` bayrağı bugün
açılsa bile davranış DEĞİŞMEZDİ — sessiz no-op tuzağı. Bu dosya bağlantıyı kilitler.

SÖZLEŞME:
  1. `ai_router` seviyesinde `jeton_gate` bağımlılığı var (entitlement/ai_queue_gate deseni).
  2. Bayrak KAPALIYKEN kapı tam no-op — bugünkü canlı davranış değişmez (sahip kararı:
     "ücretsiz sistem aktifte kalsın"). Satış bu değişiklikle AÇILMAZ.
  3. Uç→işlem eşlemesi belgeyle aynı: ağır araştırma (rna/kidney_ct/histopath)=3, ses=1,
     görüntü=1, AI Pro seans başlatma=5. `pro/stop` HİÇBİR KOŞULDA kapılanmaz (seans durdurma
     güvenlik sınıfıdır); `pro/frame` seans-içi kare akışıdır ve seans-başına ücretin parçasıdır
     (kare başına ücret 5 jetonluk seansı yüzlerce jetona çevirirdi — kapılanmaz).
  4. ⚠️ TIBBİ GÜVENLİK (4.3): tedavi/kontrol uçları (`/api/session/*`, `/api/coil/*`, acil
     durdurma) jeton kapısının ARKASINDA DEĞİLDİR — yapısal olarak doğrulanır.
  5. Bayrak AÇIK + bakiye 0 → 402 + Türkçe mesaj; mesaj tedavinin ETKİLENMEDİĞİNİ söyler.
  6. Bakiye OKUNAMIYORSA (çevrimdışı klinik) analiz DURMAZ (fail-open + yerel defter) —
     internet yokluğu kliniği çalışamaz hâle getirmez.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def jeton(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    import servers.jeton as j

    importlib.reload(j)
    return j


class _Istek:
    """jeton_gate'in kullandığı en küçük Request yüzeyi."""

    def __init__(self, path: str, token: str = "test-jwt"):
        self.url = type("U", (), {"path": path})()
        self.headers = {"authorization": f"Bearer {token}"} if token else {}


# ── 1) Kablolama: kapı ai_router'a BAĞLI ─────────────────────────────────────────


def test_KRITIK_jeton_gate_ai_router_bagimliligi():
    """Modül yazılmış ama bağlanmamışsa bayrak açılınca hiçbir şey olmaz (sessiz no-op tuzağı)."""
    os.environ.pop("PEMF_SIMULATE", None)
    from servers.ai_router import ai_router

    adlar = [getattr(d.dependency, "__name__", "") for d in (ai_router.dependencies or [])]
    assert "jeton_gate" in adlar, (
        f"ai_router bağımlılıklarında jeton_gate YOK ({adlar}) — PEMF_JETON_ENFORCED açılsa "
        "bile jeton sistemi çift yönlü no-op kalır (Adım 4 yapılmamış)"
    )
    # Mevcut kapılar korunur (aşırı-düzeltme koruması):
    assert "ai_queue_gate" in adlar, "jeton_gate eklenirken ai_queue_gate DÜŞMÜŞ"


def test_KRITIK_GUVENLIK_tedavi_uclari_jeton_kapisinin_ARKASINDA_DEGIL():
    """4.3 — pazarlık edilemez: seans/bobin/acil-durdurma uçları jeton kapılı OLAMAZ."""
    from servers.api_server import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if not (path.startswith("/api/session") or path.startswith("/api/coil") or "emergency" in path):
            continue
        bagimliliklar = [
            getattr(d.call, "__name__", "") for d in getattr(getattr(route, "dependant", None), "dependencies", [])
        ]
        assert "jeton_gate" not in bagimliliklar, (
            f"{path} JETON KAPILI — jeton ticari kapıdır, tedavi/acil-durdurma yolunu ASLA kapılayamaz"
        )


# ── 2) Uç → işlem eşlemesi ───────────────────────────────────────────────────────


def test_KRITIK_uc_eslemesi_belgeyle_AYNI(jeton):
    esle = jeton._islem_turu
    assert esle("/api/ai/pro/stop") is None, "pro/stop kapılanamaz (seans durdurma = güvenlik sınıfı)"
    assert esle("/api/ai/pro/frame") is None, "pro/frame seans-içi akış — kare başına ücret olmaz"
    assert esle("/api/ai/pro/status") is None
    assert esle("/api/ai/pro/start") == "ai_pro_seans"
    assert esle("/api/ai/rna/kidney") == "agir_arastirma"
    assert esle("/api/ai/vision/kidney_ct") == "agir_arastirma"
    assert esle("/api/ai/vision/histopath") == "agir_arastirma"
    assert esle("/api/ai/sound/cat") == "ses"
    assert esle("/api/ai/vision/landmark") == "goruntu"
    assert esle("/api/ai/disease") == "goruntu"
    # ai_router dışı yollar bu kapının işi değil:
    assert esle("/api/session/stop") is None
    assert esle("/api/coil/6/control") is None


# ── 3) Bayrak kapalı → tam no-op ─────────────────────────────────────────────────


def test_KRITIK_bayrak_KAPALIYKEN_kapi_hicbir_sey_yapmaz(jeton, monkeypatch):
    """Sahip kararı: satış kapalı. Kapıyı bağlamak canlı davranışı DEĞİŞTİRMEMELİ.

    ⚠️ ÖLÇÜ ÇAĞRI SAYACIDIR, istisna değil (mutasyon M64 ilk turda KAÇTI): fırlatan sahte
    okuyucu kapının kendi except bloğuna yutuluyor ve iç katmandaki (izin içi) bayrak kontrolü
    dış katman mutasyonunu maskeliyordu. Sayaç yutulamaz."""
    monkeypatch.setattr(jeton, "JETON_ENFORCED", False)
    cagrilar: list = []
    monkeypatch.setattr(jeton, "_bakiye_satiri_oku", lambda token: (cagrilar.append(token), {"aylik_hak": 0})[1])
    jeton._jeton_kapisi_karari(_Istek("/api/ai/vision/landmark"))  # istisna atmamalı
    assert not cagrilar, "bayrak KAPALIYKEN ağ çağrısı yapıldı — kapı no-op değil (canlı davranış değişti)"


# ── 4) Bayrak açık: 402 + Türkçe mesaj; çevrimdışı fail-open ─────────────────────


def test_KRITIK_bakiye_SIFIRKEN_402_ve_mesaj_tedaviyi_soyluyor(jeton, monkeypatch):
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(
        jeton,
        "_bakiye_satiri_oku",
        lambda token: {"aylik_hak": 0, "satin_alinan": 0, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0},
    )
    monkeypatch.setattr(jeton, "_tuketim_gonder_canli", lambda token, **k: True)

    with pytest.raises(HTTPException) as ex:
        jeton._jeton_kapisi_karari(_Istek("/api/ai/vision/landmark"))
    assert ex.value.status_code == 402
    assert "ETKİLENMEZ" in str(ex.value.detail) or "etkilenmez" in str(ex.value.detail).lower(), (
        f"402 mesajı tedavinin etkilenmediğini söylemiyor: {ex.value.detail!r}"
    )


def test_KRITIK_bakiye_varken_analiz_GECER_ve_tuketim_gider(jeton, monkeypatch):
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(
        jeton,
        "_bakiye_satiri_oku",
        lambda token: {"aylik_hak": 50, "satin_alinan": 0, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0},
    )
    gidenler: list = []
    monkeypatch.setattr(jeton, "_tuketim_gonder_canli", lambda token, **k: (gidenler.append(k), True)[1])

    jeton._jeton_kapisi_karari(_Istek("/api/ai/vision/kidney_ct"))  # istisna yok
    assert gidenler and gidenler[0]["miktar"] == jeton.MALIYET["agir_arastirma"], (
        f"ağır araştırma 3 jeton düşmeli: {gidenler!r}"
    )


def test_KRITIK_PAYG_borc_tavaninda_402(jeton, monkeypatch):
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(
        jeton,
        "_bakiye_satiri_oku",
        lambda token: {
            "aylik_hak": 0,
            "satin_alinan": 0,
            "odeme_modeli": "kullandikca",
            "kullandikca_borc": jeton.BORC_TAVANI,
        },
    )
    with pytest.raises(HTTPException) as ex:
        jeton._jeton_kapisi_karari(_Istek("/api/ai/vision/landmark"))
    assert ex.value.status_code == 402


def test_KARSIT_KANIT_cevrimdisi_klinikte_analiz_DURMAZ(jeton, monkeypatch):
    """İnternet yokluğu kliniği çalışamaz hâle GETİRMEZ (fail-open + yerel defter)."""
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)

    def _patlayan(token):
        raise ConnectionError("ag yok")

    monkeypatch.setattr(jeton, "_bakiye_satiri_oku", _patlayan)
    jeton._jeton_kapisi_karari(_Istek("/api/ai/vision/landmark"))  # istisna atmamalı (izin)


def test_KARSIT_KANIT_serbest_uc_bayrak_ACIKKEN_bile_ag_cagrisi_yapmaz(jeton, monkeypatch):
    """pro/stop için bakiye OKUNMAZ bile — ağ gecikmesi seans durdurmayı geciktiremez."""
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(
        jeton, "_bakiye_satiri_oku", lambda token: (_ for _ in ()).throw(AssertionError("pro/stop icin ag cagrisi"))
    )
    jeton._jeton_kapisi_karari(_Istek("/api/ai/pro/stop"))
