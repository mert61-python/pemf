# Author: mertaygn, cglrgrkn
"""S-SGI.2 (sahip kararı 2026-10-18 "Kare tavanını şimdi ekle") — canlı dakika kovası başına KARE TAVANI.

Ölçülen boşluk (SGI-2.1): canlı başlığını (`X-PEMF-Canli-Oturum`) ekleyen DEĞİŞTİRİLMİŞ istemci, canlı kipli uçta (FGS / segmentasyon /
termal / kedi organ) dakikada sınırsız elle analizi 1 jetona yaptırabiliyordu (20 elle analiz → 1 jeton ölçüldü).
SÖZLEŞME: arayüzün canlı döngüsü kare başlangıçları arasında ≥ 1 sn bekler → meşru canlı kip 60 sn'lik kovada ≤ 60 kare ve dakika
başına 1 jeton öder (DEĞİŞMEZ). Kovadaki 61. ve sonraki kare canlı dakika fiyatından ÇIKAR, kare başı ("goruntu", 1 jeton)
ücretlenir; ödenmiş dakikanın "kareler ücretsiz" kısa devresi o karelere uygulanmaz (bakiye yoksa 402). Sayaç kova değişince sıfırlanır.
Tavan değeri (60) burada DAVRANIŞLA pinlenir — modül sabiti okunmaz.
GERÇEK uygulama + GERÇEK `jeton_gate` / `jeton_tuketimi` / karar gövdesi; sahte yalnız EN ALT katta: Supabase taşıması (bakiye satırı +
idempotent `rpc/jeton_tuket` taklidi), termal model ve saat.
"""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
TERMAL = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"
OTURUM = "canli-sgi2-tavan-0001"


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
        iid = str(k.get("istek_id") or "")
        if iid and iid in sunucu["defter"]:
            return True  # supabase_jetonlar.sql idempotansı: tekrar → bakiye DÜŞMEZ
        m = int(k.get("miktar") or 0)
        if sunucu["bakiye"] < m:
            return False
        sunucu["bakiye"] -= m
        if iid:
            sunucu["defter"].add(iid)
        sunucu["dusulen"].append(dict(k))
        return True

    monkeypatch.setattr(j, "_bakiye_satiri_oku", _oku)
    monkeypatch.setattr(j, "_tuketim_gonder_canli", _rpc)
    gercek = air._get_or_load_model
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: _Termal() if ad == "thermal" else gercek(ad, y))
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    client = TestClient(api_server.app, client=("127.0.0.1", 51237))
    yield SimpleNamespace(client=client, j=j, sunucu=sunucu, saat=saat)
    t = getattr(j, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


def _harcanan(o) -> int:
    return sum(int(k["miktar"]) for k in o.sunucu["dusulen"])


def _analiz(o, oturum=OTURUM):
    h = {"Authorization": f"Bearer {_jwt('hekim-a')}", "X-PEMF-Canli-Oturum": oturum}
    return o.client.post(
        "/api/ai/vision/thermal", files={"file": ("k.png", TERMAL.read_bytes(), "image/png")}, headers=h
    )


def _kare(o, sahip="hekim-a", oturum=OTURUM) -> int:
    """GERÇEK karar gövdesi + başarılı teslimin tüketimi (uç modeli koşmadan): 200 ya da 402."""
    istek = SimpleNamespace(
        url=SimpleNamespace(path="/api/ai/vision/thermal"),
        headers={"authorization": f"Bearer {_jwt(sahip)}", "x-pemf-canli-oturum": oturum},
    )
    try:
        tuketici = o.j._jeton_on_karari(istek)
    except HTTPException as e:
        return e.status_code
    if tuketici is not None:
        tuketici()
    return 200


def test_KRITIK_degistirilmis_istemci_dakikada_90_analiz_TAVAN_ustu_kare_basi_ucretlenir(ortam):
    """Ölçülen kötüye kullanımın uçtan uca hâli: canlı başlıklı 90 analiz aynı dakikada (0,5 sn arayla) — eskiden 1 jeton."""
    o = ortam
    for _ in range(90):
        assert _analiz(o).status_code == 200
        o.saat[0] += 0.5  # 90 kare 45 sn'de: tek kova
    assert _harcanan(o) == 1 + 30, (
        f"aynı dakikada 90 canlı analiz {_harcanan(o)} jeton (1 dakika + 30 tavan üstü kare beklenir)"
    )
    tavan_ustu = [k for k in o.sunucu["dusulen"] if not str(k.get("istek_id") or "").startswith("canli-")]
    assert len(tavan_ustu) == 30, "tavan üstü kareler canlı dakika kimliğiyle düştü (idempotans onları YUTAR)"


def test_KARSIT_KANIT_mesru_canli_dongu_1_sn_aralik_dakika_basina_1_jeton(ortam):
    """Arayüzün döngüsü (başlangıçlar arası ≥ 1 sn): 3 dakika = 180 kare, her kova tam 60 kare → 3 jeton (TD9 / Y148 aynen)."""
    o = ortam
    for _ in range(180):
        assert _kare(o) == 200
        o.saat[0] += 1.0
    assert _harcanan(o) == 3, _harcanan(o)


def test_KRITIK_tavan_ustu_karede_odenmis_dakika_kisa_devresi_YOK_bakiye_0_ise_402(ortam):
    o = ortam
    o.sunucu["bakiye"] = 1
    durum = []
    for _ in range(61):
        durum.append(_kare(o))
        o.saat[0] += 0.25
    assert durum[:60] == [200] * 60, "ödenmiş canlı dakikanın tavan içi kareleri ücretsiz kalmalı (SGI-2.3)"
    assert durum[60] == 402, "61. kare ödenmiş dakikanın kısa devresiyle ÜCRETSİZ geçti"
    assert _harcanan(o) == 1


def test_KRITIK_sayac_KOVA_degisince_sifirlanir_ve_SAHIP_OTURUM_basina_ayri(ortam):
    o = ortam
    for _ in range(61):
        assert _kare(o) == 200
        o.saat[0] += 0.5  # 30,5 sn — kova 0
    assert _harcanan(o) == 2  # dakika + 1 tavan üstü kare
    o.saat[0] = 1000.0 + 60.0  # kova 1
    for _ in range(60):
        assert _kare(o) == 200
        o.saat[0] += 0.5
    assert _harcanan(o) == 3, "yeni dakikada sayaç sıfırlanmadı (tavan içi kareler ücretlendi)"
    # başka hekim / başka oturum kendi sayacıyla başlar: tavan içi tek kare yalnız kendi dakikasını öder
    assert _kare(o, sahip="hekim-b") == 200
    assert _kare(o, oturum="canli-sgi2-tavan-0002") == 200
    assert _harcanan(o) == 5


def test_KARSIT_tavan_ayari_bozuk_degerde_VARSAYILANA_duser(monkeypatch):
    """Ticari ayarın yazım hatası içe aktarmayı öldürmez (D1.14 / Ö.4-Y8 ruhu) ve tavanı kaldırmaz."""
    j = importlib.import_module("servers.jeton")
    monkeypatch.setenv("PEMF_JETON_CANLI_KARE_TAVANI", "altmis")
    assert j._sayi("PEMF_JETON_CANLI_KARE_TAVANI", 60) == 60
