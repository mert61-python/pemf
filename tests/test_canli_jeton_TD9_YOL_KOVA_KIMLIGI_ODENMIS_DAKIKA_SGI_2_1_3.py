# Author: mertaygn, cglrgrkn
"""SGI-2.1 / 2.2 / 2.3 (bağımsız inceleme) — TD9 (Y148) canlı kip jetonu: yol sınıfı, kova kimliği, ödenmiş dakika.

· 2.1 dakika başı ücret YALNIZ arayüzün canlı kamera kipi olan uçlarda (FGS / segmentasyon / termal / kedi organ; T3 · Y190e sahip
  2026-10-24: petri / fantom canlı kamerası da); başka "goruntu" ucuna başlık eklemek elle analizin kare başı ücretini dakikaya
  ÇEVİRMEZ (Y148: elle analiz maliyeti değişmez).
· 2.2 kova `istek_id`si süreç yeniden başlayınca / 4 sa sonra TEKRAR kullanılmaz (sunucu RPC'si `istek_id`de idempotent: tekrar = ücretsiz).
· 2.3 ödenmiş canlı dakikanın sonraki kareleri bakiye 0'da 402 almaz (Y148: kareler ücretsiz) ve o dakika canlı olmayan uca taşınmaz.
GERÇEK uygulama + GERÇEK `jeton_gate` / `jeton_tuketimi` + GERÇEK uçlar; sahte yalnız EN ALT katta: Supabase taşıması (bakiye satırı +
`rpc/jeton_tuket` — RPC'nin `(user_id, istek_id)` İDEMPOTANSI `database/supabase_jetonlar.sql` ile aynı biçimde taklit edilir: aynı
`istek_id` ikinci kez gelirse `ok: true, tekrar: true` ve bakiye DÜŞMEZ), termal model ve saat.
"""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
TERMAL = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"
OTURUM = "canli-sgi2-0001abcd"


def _jwt(sub: str) -> str:
    from jwt_test_anahtari import imzali_jwt  # TA T4: GERÇEK ES256 imza (JWKS doğrulaması)

    return imzali_jwt({"sub": sub})


class _Termal:
    def predict(self, yol, threshold=0.5):
        return {"label": "Healthy", "probability_sick": 0.1, "confidence": 0.9}


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    j = importlib.import_module("servers.jeton")
    from servers import ai_router as air
    from servers import api_server

    monkeypatch.setattr(j, "JETON_ENFORCED", True)
    monkeypatch.setattr(j, "_son_uzlastirma", None, raising=False)
    monkeypatch.setattr(j, "_canli_oturumlar", {})
    saat = [1000.0]
    monkeypatch.setattr(j, "time", SimpleNamespace(monotonic=lambda: saat[0], time=lambda: 1.7e9 + saat[0]))
    sunucu = {"bakiye": 1000, "defter": set(), "dusulen": []}

    def _oku(token):
        return {"aylik_hak": 0, "satin_alinan": sunucu["bakiye"], "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}

    def _rpc(token, **k):
        # supabase_jetonlar.sql::jeton_tuket — idempotans (user_id, istek_id) + satır kilidi + yetersiz red
        iid = str(k.get("istek_id") or "")
        if iid in sunucu["defter"]:
            return True  # 'tekrar': bakiye DÜŞMEZ
        m = int(k.get("miktar") or 0)
        if sunucu["bakiye"] < m:
            return False
        sunucu["bakiye"] -= m
        sunucu["defter"].add(iid)
        sunucu["dusulen"].append(dict(k))
        return True

    monkeypatch.setattr(j, "_bakiye_satiri_oku", _oku)
    monkeypatch.setattr(j, "_tuketim_gonder_canli", _rpc)
    gercek = air._get_or_load_model
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: _Termal() if ad == "thermal" else gercek(ad, y))
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    client = TestClient(api_server.app, client=("127.0.0.1", 51236))
    yield SimpleNamespace(client=client, j=j, sunucu=sunucu, saat=saat, monkeypatch=monkeypatch)
    t = getattr(j, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


def _analiz(o, oturum=None):
    h = {"Authorization": f"Bearer {_jwt('hekim-a')}"}
    if oturum:
        h["X-PEMF-Canli-Oturum"] = oturum
    return o.client.post(
        "/api/ai/vision/thermal", files={"file": ("k.png", TERMAL.read_bytes(), "image/png")}, headers=h
    )


def test_SGI_2_2_backend_YENIDEN_baslarsa_canli_oturum_onceki_dakikalari_kadar_UCRETSIZ(ortam):
    """TD raporu: "backend canlı oturum ortasında yeniden başlarsa ... en kötü durumda bir dakika eksik ücretlenir".
    30 dk canlı → yeniden başlatma (süreç belleği sıfır) → aynı oturumla 30 dk daha. Beklenen: ~60 jeton (en çok 1 eksik)."""
    o = ortam
    for _ in range(30 * 6):
        assert _analiz(o, oturum=OTURUM).status_code == 200
        o.saat[0] += 10.0
    ilk = sum(int(k["miktar"]) for k in o.sunucu["dusulen"])
    o.monkeypatch.setattr(o.j, "_canli_oturumlar", {})  # süreç yeniden başladı: kova belleği sıfır (kod: modül sözlüğü)
    for _ in range(30 * 6):
        assert _analiz(o, oturum=OTURUM).status_code == 200
        o.saat[0] += 10.0
    toplam = sum(int(k["miktar"]) for k in o.sunucu["dusulen"])
    assert ilk == 30, ilk
    assert toplam >= 59, (
        f"60 dk canlı kullanım {toplam} jeton (yeniden başlatma sonrası {toplam - ilk}) — ilk 30 dakikanın istek_id'leri tekrar"
    )


def test_SGI_2_2b_4_saatten_UZUN_kesintisiz_canli_oturum_unutulur_ve_UCRETSIZ_devam(ortam):
    """`_CANLI_UNUTMA_SN` oturumun İLK karesinden (t0) ölçülür, son kareden değil → 4 sa 10 dk kesintisiz canlıda ne olur?"""
    o = ortam
    dakika = 250
    for _ in range(dakika * 2):
        assert _analiz(o, oturum=OTURUM).status_code == 200
        o.saat[0] += 30.0
    toplam = sum(int(k["miktar"]) for k in o.sunucu["dusulen"])
    assert toplam == dakika, f"{dakika} dk kesintisiz canlı kullanım {toplam} jeton (dakika başına 1 olmalı)"


def test_SGI_2_3_odenmis_dakikada_bakiye_0_olunca_sonraki_kareler_402(ortam):
    """Son jetonla ödenen dakikanın içindeki sonraki kareler: dakika ÖDENDİ, kare ücretsiz olmalı (Y148: kareler ücretsiz)."""
    o = ortam
    o.sunucu["bakiye"] = 1
    durum = []
    for _ in range(5):
        durum.append(_analiz(o, oturum=OTURUM).status_code)
        o.saat[0] += 5.0  # hepsi aynı dakika kovası (0–25 sn)
    assert sum(int(k["miktar"]) for k in o.sunucu["dusulen"]) == 1
    assert durum == [200] * 5, f"ödenmiş dakikanın kareleri: {durum}"


def test_KARSIT_canli_10_dakika_10_jeton_ve_elle_basliksiz_kare_basina(ortam):
    o = ortam
    for _ in range(60):
        assert _analiz(o, oturum=OTURUM).status_code == 200
        o.saat[0] += 10.0
    assert sum(int(k["miktar"]) for k in o.sunucu["dusulen"]) == 10
    for _ in range(3):
        assert _analiz(o).status_code == 200
    assert sum(int(k["miktar"]) for k in o.sunucu["dusulen"]) == 13


@pytest.mark.parametrize(
    "yol",
    [
        "/api/ai/vision/reticulocytes",
        "/api/ai/disease",
        "/api/ai/disease/kidney",
    ],
)
def test_SGI_2_1b_canli_kipi_OLMAYAN_ucta_baslik_dakika_fiyatina_cevirmez(ortam, yol):
    """Arayüzün canlı kamera kipi yalnız FGS / segmentasyon / termal (VisionModule, retikülosit `galleryOnly`), kedi organ ve
    (T3 · Y190e) petri / fantom araştırma analizinde. Başka bir "goruntu" ucuna başlık eklemek (ör. retikülosit, hastalık) kare başı
    fiyatı dakikaya ÇEVİRMEMELİ.
    Gerçek KARAR gövdesi (`_jeton_on_karari`); istek nesnesi yalnız yol + başlık taşır."""
    o = ortam
    istek = SimpleNamespace(
        url=SimpleNamespace(path=yol),
        headers={"authorization": f"Bearer {_jwt('hekim-a')}", "x-pemf-canli-oturum": OTURUM},
    )
    tuketici = o.j._jeton_on_karari(istek)
    assert tuketici is not None
    assert not getattr(tuketici, "canli", False), f"{yol}: canlı başlıkla DAKİKA başına ücret yoluna girdi"


def test_SGI_2_3b_odenmis_canli_dakika_CANLI_OLMAYAN_uca_TASINMAZ(ortam):
    """Birleşik yama sınaması: termal canlı karesiyle ödenen dakika, AYNI başlıkla gelen canlı kipi OLMAYAN bir uç (retikülosit;
    T3 · Y190e'den önce araştırma em_fantom'du — artık canlı kipli) analizini ücretsiz yapmamalı (SGI-2.3 kısa devresi yol beyaz
    listesine de bakmalı)."""
    o = ortam
    assert _analiz(o, oturum=OTURUM).status_code == 200  # dakika 0 ödendi (termal canlı)
    assert sum(int(k["miktar"]) for k in o.sunucu["dusulen"]) == 1
    istek = SimpleNamespace(
        url=SimpleNamespace(path="/api/ai/vision/reticulocytes"),
        headers={"authorization": f"Bearer {_jwt('hekim-a')}", "x-pemf-canli-oturum": OTURUM},
    )
    tuketici = o.j._jeton_on_karari(istek)
    assert tuketici is not None, "reticulocytes: ödenmiş canlı dakika canlı kipi olmayan analizi ÜCRETSİZ yaptı"
    tuketici()
    assert sum(int(k["miktar"]) for k in o.sunucu["dusulen"]) == 2, o.sunucu["dusulen"]


@pytest.mark.parametrize(
    "yol",
    [
        "/api/ai/vision/landmark",
        "/api/ai/vision/segmentation",
        "/api/ai/vision/thermal",
        "/api/ai/vision/cat_organ",
        "/api/ai/vision/em_petri",
        "/api/ai/vision/em_fantom",
    ],
)
def test_KARSIT_SGI_2_1_canli_kipli_uclarda_baslik_DAKIKA_yoluna_girer(ortam, yol):
    o = ortam
    istek = SimpleNamespace(
        url=SimpleNamespace(path=yol),
        headers={"authorization": f"Bearer {_jwt('hekim-a')}", "x-pemf-canli-oturum": OTURUM},
    )
    tuketici = o.j._jeton_on_karari(istek)
    assert tuketici is not None and getattr(tuketici, "canli", False), (
        f"{yol}: canlı kipli uç dakika başına ücret yoluna GİRMEDİ"
    )


def test_KAPI_SGI_2_1_canli_uc_beyaz_listesi_GERCEK_goruntu_uclari():
    """Beyaz liste yol adıyla tutulur: uç yeniden adlandırılırsa canlı kip SESSİZCE kare başına dönmesin — her yol gerçek bir
    `goruntu` sınıfı POST ucu olmalı."""
    j = importlib.import_module("servers.jeton")
    from servers import api_server

    post = {r.path for r in api_server.app.routes if "POST" in (getattr(r, "methods", None) or set())}
    for yol in sorted(j._CANLI_UCLAR):
        assert yol in post, f"{yol}: uygulamada böyle bir POST ucu yok"
        assert j._islem_turu(yol) == "goruntu", yol
