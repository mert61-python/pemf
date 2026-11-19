# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""JETON KAPISI AI UÇLARINA BAĞLANIR — JETON-SISTEMI Adım 4 ("EN KRİTİK ADIM"), 2026-08-22.

ÖLÇÜLEN DURUM: `apps/backend/servers/jeton.py` 16 testle kilitliydi ama HİÇBİR üretim kodundan çağrılmıyordu
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
  6. Bakiye OKUNAMIYORSA (internet yok) yeni analiz BAŞLATILMAZ — 402, `X-PEMF-Jeton-Sebep: cevrimdisi` (S-4B.5 + S-4BI.8,
     sahip kararı 2026-10-19; eskiden fail-open + yerel defter). Seans / acil durdurma / sensör internetsiz de SERBEST.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from jwt_test_anahtari import imzali_jwt  # TA T4: GERÇEK ES256 imzalı test belirteci (JWKS doğrulaması)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def jeton(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    import servers.jeton as j

    importlib.reload(j)
    from jwt_test_anahtari import TEST_JWKS

    j._jwks_getir = lambda: (
        TEST_JWKS
    )  # TA T4: yeniden yükleme conftest'in JWKS bağını siler → test anahtarına yeniden bağla
    return j


class _Istek:
    """jeton_gate'in kullandığı en küçük Request yüzeyi."""

    # 4B-1.5: gerçek Supabase jetonu `sub` taşıyan bir JWT'dir; kimliği çözülemeyen jeton zorlama açıkken 402 alır.
    def __init__(self, path: str, token: "str | None" = None):
        token = imzali_jwt({"sub": "test-kullanici"}) if token is None else token
        self.url = type("U", (), {"path": path})()
        self.headers = {"authorization": f"Bearer {token}"} if token else {}


# ── 1) Kablolama: kapı ai_router'a BAĞLI ─────────────────────────────────────────


def test_KRITIK_jeton_gate_ai_router_bagimliligi():
    """Modül yazılmış ama bağlanmamışsa bayrak açılınca hiçbir şey olmaz (sessiz no-op tuzağı)."""
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
    # ⚠️ GERÇEK rota (2026-09-08): serbest listede `/api/ai/pro/frame` yazıyordu ama böyle bir uç
    # HİÇ olmadı; canlı rota `/api/ai/ai_pro/frame` (test_route_contract.py:20). Ölü girdi her
    # kareyi "goruntu" sınıfına düşürüyordu (FREE_MODE gizliyordu). Bu satır artık ÜRETİM yolunu
    # ölçer — yol yanlış yazılırsa KIRMIZI.
    assert esle("/api/ai/ai_pro/frame") is None, "ai_pro/frame seans-içi akış — kare başına ücret olmaz"
    assert esle("/api/ai/pro/hazirlik/baslat") is None, "hazırlık önizlemesi bobin sürmez — analiz değil"
    assert esle("/api/ai/pro/hazirlik/durdur") is None, "hazırlık durdurma kapılanamaz"
    assert esle("/api/ai/hazirlik") is None, "self-test/envanter okuma analiz değil (metodsuz eşleme)"
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


def test_KRITIK_serbest_listede_OLU_yol_YOK(jeton):
    """2026-09-08 bulgusu: listede `/api/ai/pro/frame` yazıyordu ama böyle bir rota HİÇ olmadı
    (gerçek uç `/api/ai/ai_pro/frame`) → eşleşme tutmuyor, her kare "goruntu" sınıfına düşüyordu.
    FREE_MODE=true bunu gizledi; ücretlendirme açılsaydı 5 jetonluk seans kare başına ücretlenirdi.

    Muafiyet listeleri ADLA çalıştığı için tek harflik sapma sessizce ücretlendirmeye düşürür.
    Kapı: serbest listedeki HER yol uygulamada GERÇEKTEN kayıtlı bir rota olmalı.
    MUTASYON: listeye var olmayan bir yol ekleyin → KIRMIZI."""
    import servers.api_server as apis

    gercek = {getattr(r, "path", "") for r in apis.app.routes}
    olu = sorted(p for p in jeton._SERBEST_AI_UCLARI if p not in gercek)
    assert not olu, (
        f"jeton serbest listesinde ÖLÜ yol(lar) var: {olu} — bu uçlar aslında ücretlendirmeye "
        "düşüyor. Rota adını uygulamadaki gerçek yolla eşleyin (tests/test_route_contract.py)."
    )


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


def test_KRITIK_internetsiz_klinikte_ANALIZ_402_cevrimdisi_tedavi_SERBEST_S4B5(jeton, monkeypatch):
    """S-4B.5 (sahip "internetsizken analiz yapılmasın"): bakiye okunamıyor → analiz 402 + sebep başlığı `cevrimdisi`, mesaj interneti
    ve tedavinin etkilenmediğini söyler; aynı anda seans / ACİL DURDUR yolları kapıya girmez (internetsiz klinik TEDAVİ yapar)."""
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)

    def _patlayan(token):
        raise ConnectionError("ag yok")

    monkeypatch.setattr(jeton, "_bakiye_satiri_oku", _patlayan)
    with pytest.raises(HTTPException) as ex:
        jeton._jeton_kapisi_karari(_Istek("/api/ai/vision/landmark"))
    assert ex.value.status_code == 402
    assert (ex.value.headers or {}).get("X-PEMF-Jeton-Sebep") == "cevrimdisi", ex.value.headers
    assert "internet gerekir" in str(ex.value.detail) and "ETKİLENMEZ" in str(ex.value.detail), ex.value.detail
    for yol in ("/api/hardware/emergency_stop", "/api/session/stop", "/api/ai/pro/stop"):
        assert jeton._jeton_kapisi_karari(_Istek(yol)) is None, f"internetsizken tedavi yolu kapılandı: {yol}"


def test_KARSIT_KANIT_402_sebep_basligi_YETERSIZ_bakiyede_yetersiz(jeton, monkeypatch):
    """Başlık sebebi ayırt eder: bakiye 0 (çevrimiçi) → `yetersiz` (arayüz "Jeton hakkı" başlığı) — her 402'ye `cevrimdisi` yazan
    mutantı yakalar."""
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(
        jeton,
        "_bakiye_satiri_oku",
        lambda token: {"aylik_hak": 0, "satin_alinan": 0, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0},
    )
    with pytest.raises(HTTPException) as ex:
        jeton._jeton_kapisi_karari(_Istek("/api/ai/vision/landmark"))
    assert (ex.value.headers or {}).get("X-PEMF-Jeton-Sebep") == "yetersiz", ex.value.headers


def test_KRITIK_402_sebep_basligi_TARAYICIYA_acik_CORS_expose():
    """Arayüz (web paneli / webview) cihaza başka KÖKENDEN istek atar: tarayıcı yalnız `Access-Control-Expose-Headers`'ta adı geçen
    yanıt başlığını JS'e verir — yoksa `cevrimdisi` sebebi hiç okunmaz, pencere başlığı "Jeton hakkı" kalır (gerçek uygulama)."""
    from fastapi.testclient import TestClient
    from servers import api_server

    c = TestClient(api_server.app, client=("127.0.0.1", 51241))
    r = c.get("/api/health", headers={"Origin": "http://localhost:8081"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8081", (
        "ölçüm aracı: LAN kökeni CORS'tan geçmedi"
    )
    acik = [h.strip().lower() for h in r.headers.get("access-control-expose-headers", "").split(",")]
    assert "x-pemf-jeton-sebep" in acik, f"402 sebep başlığı tarayıcıya kapalı: {dict(r.headers)}"


def test_KARSIT_KANIT_serbest_uc_bayrak_ACIKKEN_bile_ag_cagrisi_yapmaz(jeton, monkeypatch):
    """pro/stop için bakiye OKUNMAZ bile — ağ gecikmesi seans durdurmayı geciktiremez."""
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(
        jeton, "_bakiye_satiri_oku", lambda token: (_ for _ in ()).throw(AssertionError("pro/stop icin ag cagrisi"))
    )
    jeton._jeton_kapisi_karari(_Istek("/api/ai/pro/stop"))
