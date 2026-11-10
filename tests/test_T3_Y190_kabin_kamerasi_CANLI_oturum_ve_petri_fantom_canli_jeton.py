# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T3 · Y190 (sahip, 2026-10-24) — petri / fantom analizinde "Fotoğraf Çek" doğrudan kabin kamerası, kamera seçimi panelde, CANLI kamera.

İSTEK (sahip): "fotoğraf çek direkt kabin kamerasından çekmeliydi … kabin kamerasından çek gereksiz buton. kamera seçimi de burada
olmalı, ayarlar içinde değil. telefonda telefonun kamerasını açmalı. galeriden seç normal kalmalı. bir de canlı kamera eklenmeli
hem fantoma hem petriye." Kararlar: canlı = önizleme + otomatik analiz · seçim petri / fantom panelinde + AI Pro'da, Ayarlar'dan
kalkar · telefonda telefonun kamerasıyla canlı · jeton: dakika başı 1 (Y148 ile aynı kural).

ÖLÇÜLEN (önce, HEAD 3a4c2f5b): kabin kamerası her karede açılıp kapanıyor (`kare_al`: aç + 1920×1080 iste + 6 okuma + bırak —
gerçek kamerada saniyeler; canlı kip bununla çalışmaz); canlı kamera oturumu YOK; petri / fantom uçları canlı başlıkla bile kare
başı ücretlenir (`_CANLI_UCLAR` dışı); sunucu metinleri kullanıcıyı artık var olmayan "Ayarlar ▸ Kabin kamerası"na yolluyor.
KAPI (bu dosya): canlı oturum seçili kamerayı TEK `VideoCapture`la açık tutar, son kareyi önizleme (960 px) / tam (kalibrasyon
boyutu) verir, kare istenmezse kendiliğinden kapanır ve kamerayı BIRAKIR; AI Pro / tek kare (`kamera_ac`) canlıyı ÖNCE kapatır
(iki `VideoCapture` çakışmaz); uçlar meşgulde / seçimsizde 409, açılamazsa 503; tarama canlı açıkken 409; seçim değişince canlı
kapanır; petri / fantom canlı başlıkla DAKİKA yoluna girer, başlıksız elle analiz kare başı kalır (karşıt).
Sahte yalnız EN ALT katta: `cv2` (`_SahteCv2` — VideoCapture / read / release sırası kaydı).
"""

from __future__ import annotations

import base64
import importlib
import time
from types import SimpleNamespace

import pytest
from test_T2D2_kabin_kamerasi_SECIMI_ve_1080p import _SahteCv2, veri  # noqa: F401


def _bekle(kosul, sn=3.0):
    son = time.monotonic() + sn
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.02)
    return kosul()


@pytest.fixture()
def canli(veri, monkeypatch):
    """Her testten sonra canlı oturum KAPANIR (okuyucu iş parçacığı test dışına sızmaz)."""
    kk, kok = veri
    yield kk, kok
    kk.canli_durdur()
    assert not kk.canli_acik()


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 1. CANLI OTURUM (utils.kabin_kamerasi)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_canli_SECIMSIZ_kamera_ACMAZ_secimle_TEK_VideoCapture_ve_1080p(canli):
    kk, _ = canli
    cv = _SahteCv2()
    with pytest.raises(kk.KameraSecilmedi):
        kk.canli_baslat(cv)
    assert cv.acilan == [] and not kk.canli_acik(), "seçim yokken kamera açıldı (dahili kameraya düşüş)"
    kk.kamera_sec(1)
    d = kk.canli_baslat(cv)
    assert d == {"indeks": 1, "acik": True} and kk.canli_acik()
    assert kk.canli_baslat(cv) == {"indeks": 1, "acik": True}, "ikinci başlatma aynı oturum olmalı"
    assert cv.acilan == [1], f"canlı oturum kamerayı {len(cv.acilan)} kez açtı"
    # KD madde 0 (b): kalibrasyon yokken kameranın EN YÜKSEK modu istenir (9999 → sürücü 1920×1080 verir).
    assert cv.capler[0].sira[:2] == [("set", 3, 9999.0), ("set", 4, 9999.0)], cv.capler[0].sira[:3]


def test_KRITIK_canli_kare_ONIZLEME_kucuk_TAM_kalibrasyon_boyutu_ve_kamera_KAPANINCA_birakilir(canli):
    kk, _ = canli
    cv = _SahteCv2()
    kk.kamera_sec(1)
    kk.canli_baslat(cv)
    assert _bekle(lambda: (kk.canli_kare(cv2=cv) or {}).get("hazir") is True), "canlı oturumdan kare gelmedi"
    o = kk.canli_kare(cv2=cv)
    t = kk.canli_kare(tam=True, cv2=cv)
    assert (o["genislik"], o["yukseklik"]) == (kk.CANLI_ONIZLEME_GENISLIK, 540), o
    assert (t["genislik"], t["yukseklik"]) == (1920, 1080) and t["indeks"] == 1, (
        "analiz karesi kalibrasyon boyutunda olmalı"
    )
    assert base64.b64decode(t["image_base64"]) and isinstance(t["yas_ms"], int) and t["yas_ms"] >= 0
    cap = cv.capler[0]
    kk.canli_durdur()
    assert not kk.canli_acik() and cap.sira[-1] == ("release",), "durdurunca kamera BIRAKILMADI"
    assert kk.canli_kare(cv2=cv) is None  # durdurulmuş oturum: None (Y192: hazır-değil ile karışmaz)


def test_KRITIK_canli_kare_ISTENMEZSE_kendiliginden_kapanir_ve_kamerayi_birakir(canli, monkeypatch):
    """Sekme kapandı / ağ koptu → kamera sonsuza dek açık KALMAZ (sonraki tek kare / AI Pro açabilsin)."""
    kk, _ = canli
    monkeypatch.setattr(kk, "CANLI_ZAMAN_ASIMI_SN", 0.25)
    cv = _SahteCv2()
    kk.kamera_sec(1)
    kk.canli_baslat(cv)
    assert kk.canli_acik()
    assert _bekle(lambda: not kk.canli_acik(), sn=4.0), "kare istenmeyen canlı oturum kapanmadı"
    assert _bekle(lambda: cv.capler[0].sira[-1] == ("release",)), "zaman aşımında kamera bırakılmadı"
    # KARŞIT: kare istendikçe oturum AÇIK kalır
    kk.canli_baslat(cv)
    for _ in range(12):
        time.sleep(0.05)
        kk.canli_kare(cv2=cv)
    assert kk.canli_acik(), "kare istenirken canlı oturum zaman aşımına düştü"


def test_KRITIK_kamera_ac_AI_Pro_CANLIYI_once_kapatir_iki_VideoCapture_cakismaz(canli):
    kk, _ = canli
    cv = _SahteCv2()
    kk.kamera_sec(1)
    kk.canli_baslat(cv)
    canli_cap = cv.capler[0]
    cap, indeks = kk.kamera_ac(cv)
    assert not kk.canli_acik(), "AI Pro kamerayı açtı ama canlı oturum hâlâ açık"
    assert ("release",) in canli_cap.sira, "canlı kamera bırakılmadan ikinci VideoCapture açıldı"
    assert indeks == 1 and cv.acilan == [1, 1]
    cap.release()


def test_KRITIK_kare_al_CANLI_aciksa_ikinci_kamera_ACMAZ_son_tam_kareyi_verir(canli):
    kk, _ = canli
    cv = _SahteCv2()
    kk.kamera_sec(1)
    kk.canli_baslat(cv)
    assert _bekle(lambda: (kk.canli_kare(cv2=cv) or {}).get("hazir") is True)
    k = kk.kare_al(cv)
    assert (k["genislik"], k["yukseklik"]) == (1920, 1080)
    assert cv.acilan == [1] and kk.canli_acik(), "canlı açıkken tek kare İKİNCİ VideoCapture açtı / canlıyı kapattı"


def test_canli_baslat_ACILAMAZSA_None_ve_kamera_birakilir(canli):
    kk, _ = canli
    cv = _SahteCv2(acik=())
    kk.kamera_sec(0)
    assert kk.canli_baslat(cv) is None and not kk.canli_acik()
    assert cv.capler[-1].sira[-1] == ("release",)


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 2. UÇLAR (settings_router)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    return TestClient(api_server.app)


def test_KRITIK_canli_baslat_ucu_MESGULDE_409_SECIMSIZDE_409_ACILAMAZSA_503_basarida_oturum(istemci, monkeypatch):
    from servers import settings_router as sr
    from utils import kabin_kamerasi as kk

    acildi = []
    monkeypatch.setattr(kk, "canli_baslat", lambda *a, **k: acildi.append(1) or {"indeks": 2, "acik": True})
    monkeypatch.setattr(sr, "_ai_kamerasi_mesgul", lambda: True)
    r = istemci.post("/api/settings/kabin-kamerasi/canli/baslat")
    assert r.status_code == 409 and "AI Pro" in r.json()["detail"] and acildi == [], r.text[:200]
    monkeypatch.setattr(sr, "_ai_kamerasi_mesgul", lambda: False)

    def _secilmedi(*a, **k):
        raise kk.KameraSecilmedi()

    monkeypatch.setattr(kk, "canli_baslat", _secilmedi)
    r = istemci.post("/api/settings/kabin-kamerasi/canli/baslat")
    assert r.status_code == 409 and "Kabin kamerası" in r.json()["detail"], r.text[:200]
    monkeypatch.setattr(kk, "canli_baslat", lambda *a, **k: None)
    monkeypatch.setattr(kk, "secili_kamera", lambda: {"indeks": 2, "kaynak": "ayar"})
    r = istemci.post("/api/settings/kabin-kamerasi/canli/baslat")
    assert r.status_code == 503 and "(kamera 2)" in r.json()["detail"], r.text[:200]
    monkeypatch.setattr(kk, "canli_baslat", lambda *a, **k: {"indeks": 2, "acik": True})
    r = istemci.post("/api/settings/kabin-kamerasi/canli/baslat")
    assert r.status_code == 200 and r.json() == {"status": "success", "indeks": 2, "acik": True}, r.text[:200]


def test_KRITIK_canli_kare_ucu_KAPALIYSA_409_eylem_soyler_TAM_parametresi_gecer(istemci, monkeypatch):
    from utils import kabin_kamerasi as kk

    monkeypatch.setattr(kk, "canli_kare", lambda tam=False, cv2=None, bekle_sn=0.0: None)
    r = istemci.get("/api/settings/kabin-kamerasi/canli/kare")
    assert r.status_code == 409 and "Canlı Kamera" in r.json()["detail"], r.text[:200]
    gelen = []

    def _kare(tam=False, cv2=None, bekle_sn=0.0):
        gelen.append(tam)
        return {
            "indeks": 1,
            "hazir": True,
            "genislik": 1920 if tam else 960,
            "yukseklik": 1080,
            "yas_ms": 5,
            "image_base64": "QQ==",
        }

    monkeypatch.setattr(kk, "canli_kare", _kare)
    assert istemci.get("/api/settings/kabin-kamerasi/canli/kare").json()["genislik"] == 960
    assert istemci.get("/api/settings/kabin-kamerasi/canli/kare?tam=true").json()["genislik"] == 1920
    assert gelen == [False, True], gelen


def test_KRITIK_canli_durdur_ucu_oturumu_KAPATIR_tarama_CANLI_acikken_409_secim_degisince_canli_KAPANIR(
    istemci, canli, monkeypatch
):
    from servers import settings_router as sr

    kk, _ = canli
    cv = _SahteCv2()
    kk.kamera_sec(1)
    kk.canli_baslat(cv)
    monkeypatch.setattr(sr, "_ai_kamerasi_mesgul", lambda: False)
    taradi = []
    monkeypatch.setattr(kk, "kameralari_tara", lambda *a, **k: taradi.append(1) or [])
    r = istemci.post("/api/settings/kabin-kamerasi/tara")
    assert r.status_code == 409 and "Canlı kamera" in r.json()["detail"] and taradi == [], r.text[:200]
    r = istemci.post("/api/settings/kabin-kamerasi", json={"indeks": 0})
    assert r.status_code == 200 and not kk.canli_acik(), "seçim değişti ama canlı oturum ESKİ kamerayı tutuyor"
    assert cv.capler[0].sira[-1] == ("release",)
    assert istemci.post("/api/settings/kabin-kamerasi/tara").status_code == 200 and taradi == [1]  # KARŞIT
    kk.kamera_sec(1)
    kk.canli_baslat(cv)
    r = istemci.post("/api/settings/kabin-kamerasi/canli/durdur")
    assert r.status_code == 200 and not kk.canli_acik()
    assert istemci.post("/api/settings/kabin-kamerasi/canli/durdur").status_code == 200, "kapalıyken durdur da başarı"


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 3. JETON — petri / fantom canlı dakika başı (Y190e), elle analiz kare başı (karşıt)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def _jwt(sub: str) -> str:
    """Sahte belirteç ÇALIŞMA ANINDA üretilir (depoda belirteç biçimli dizge durmaz — gitleaks `jwt` kuralı)."""
    import json

    g = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{g}.sahte-imza"


def _istek(yol, oturum=None):
    h = {"authorization": f"Bearer {_jwt('hekim-a')}"}
    if oturum:
        h["x-pemf-canli-oturum"] = oturum
    return SimpleNamespace(url=SimpleNamespace(path=yol), headers=h)


@pytest.mark.parametrize("yol", ["/api/ai/vision/em_petri", "/api/ai/vision/em_fantom"])
def test_KRITIK_petri_fantom_CANLI_baslikla_DAKIKA_yoluna_girer_basliksiz_KARE_basi(yol, monkeypatch, tmp_path):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    j = importlib.import_module("servers.jeton")
    monkeypatch.setattr(j, "JETON_ENFORCED", True)
    monkeypatch.setattr(j, "_canli_oturumlar", {})
    monkeypatch.setattr(
        j,
        "_bakiye_satiri_oku",
        lambda token: {"aylik_hak": 0, "satin_alinan": 100, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0},
    )
    assert yol in j._CANLI_UCLAR
    t = j._jeton_on_karari(_istek(yol, "canli-y190-0001abcd"))
    assert t is not None and getattr(t, "canli", False), f"{yol}: canlı başlıkla dakika başı ücret yoluna GİRMEDİ"
    t0 = j._jeton_on_karari(_istek(yol))
    assert t0 is not None and not getattr(t0, "canli", False), (
        f"{yol}: başlıksız elle analiz dakika yoluna girdi (Y148)"
    )


def test_canli_metinleri_IKI_dilde_ve_kullaniciyi_OLMAYAN_Ayarlar_bolumune_yollamaz():
    import i18n_yardimci as iy

    for dil in ("tr", "en"):
        kat = iy.katalog("sunucu", dil)
        for anahtar in (
            "ayarlar.kabinKamerasi.canliMesgul",
            "ayarlar.kabinKamerasi.canliKapali",
            "ayarlar.kabinKamerasi.taramaCanliAcik",
        ):
            assert kat.get(anahtar), (dil, anahtar)
        for anahtar in ("ai.pro.hazirlik.kameraSecilmedi", "ayarlar.kabinKamerasi.kareAlinamadi"):
            assert "Ayarlar ▸" not in kat[anahtar] and "Settings ▸" not in kat[anahtar], (dil, anahtar, kat[anahtar])


def test_KRITIK_petri_fantom_canli_TESPIT_YOK_karesi_dakikayi_UCRETLENDIRMEZ_sonucu_olan_karesi_eder():
    """Y148 / TD9: canlı dakika yalnız SONUÇ teslim edilen kovada ücretlenir. Petri / fantom "tespit yok" yanıtı 200 +
    `status: no_detection` döner — `sonuc_izle` sarmalayıcısı olmadan bu kare dakikayı ücretlendirirdi (ölçüldü: sarmalayıcı yoktu)."""
    j = importlib.import_module("servers.jeton")
    from servers import ai_router as air

    assert j.sonucsuz_mu({"status": "no_detection", "n_wells": 0}) is True
    assert j.sonucsuz_mu({"status": "success", "n_wells": 3, "n_cancer": 1}) is False  # KARŞIT
    assert j.sonucsuz_mu({"status": "success", "n_tumor": 0}) is False, "başarılı 0-tümör sonucu da SONUÇTUR"
    for fn in (air.analyze_em_petri, air.analyze_em_fantom):
        assert getattr(fn, "__wrapped__", None) is not None, f"{fn.__name__}: sonuc_izle ile sarılmamış"
