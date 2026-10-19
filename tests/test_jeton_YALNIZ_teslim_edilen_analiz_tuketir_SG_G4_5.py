# -*- coding: utf-8 -*-
"""SG.G4-5 / G5-4 — reddedilen / düşen / teslim edilemeyen AI analizi JETON DÜŞÜRMEZ (sahip gözlemi 2026-10-13).

Ölçülen durum [ÖLÇTÜM `ec5e967c`]: `jeton_gate` router-seviyesi bağımlılık olarak UÇTAN ÖNCE koşuyor ve kararla BİRLİKTE jetonu
düşürüyordu (`JetonYoneticisi.izin` → `_tuket`). Sonuç: modalite / termal makullik kapısının 422'si, model hatasının 500'ü ve istemcinin
iptal ettiği canlı kare de 1 jeton yakıyordu. Kurulu üründe (günlük, 2026-10-13 20:00–20:08) segmentasyon canlı kipinde 63 kare H&E
sanılıp 422 aldı — hepsi ücretlendi; sahibin hesabında 16 dakikada 218 görüntü tüketimi (koordinatör, canlı defter).
Düzeltme: KARAR `jeton_gate`te (402 aynen), TÜKETİM `jeton_tuketimi`nde (`scope="function"` yield bağımlılığı) — yalnız uç
istisnasız dönünce ve istemci hâlâ bağlıyken. Fiyat / kural DEĞİŞMEDİ (1 analiz = maliyet tablosu).
Ölçüm: GERÇEK uygulama, GERÇEK `jeton_gate` / `jeton_tuketimi`, GERÇEK görüntü kapıları; sahte YALNIZ en alt katlarda — Supabase taşıma
(`_bakiye_satiri_oku`, `_tuketim_gonder_canli`) ve model tahmincisi. Defter gerçek dosya (`PEMF_DATA_DIR` = tmp_path).
"""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
TERMAL = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"


def _jwt(sub: str) -> str:
    b = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{b}.imza"


def _kamera_karesi() -> bytes:
    """Termal OLMAYAN sentetik oda karesi (kişisel veri yok) — termal uç bunu 422'ler (SG.G4)."""
    rng = np.random.default_rng(5)
    img = np.zeros((240, 320, 3), np.float32)
    img[:] = (155, 170, 190)
    img[:, :100] = (120, 128, 168)
    cv2.ellipse(img, (160, 90), (50, 64), 0, 0, 360, (128, 158, 205), -1)
    img = np.clip(img + rng.normal(0, 6, img.shape), 0, 255).astype(np.uint8)
    ok, b = cv2.imencode(".jpg", img)
    return b.tobytes()


class _Tahminci:
    def __init__(self):
        self.patlat = False

    def predict(self, yol, threshold=0.5):
        if self.patlat:
            raise RuntimeError("sahte: model çöktü")
        return {"label": "Healthy", "probability_sick": 0.1, "confidence": 0.9}


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    j = importlib.import_module("servers.jeton")
    from servers import ai_router as air
    from servers import api_server

    monkeypatch.setattr(j, "JETON_ENFORCED", True)
    monkeypatch.setattr(j, "_son_uzlastirma", None, raising=False)
    bakiye = {"aylik_hak": 0, "satin_alinan": 100, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}
    okunan, giden = [], []

    def _oku(token):
        okunan.append(token)
        if bakiye.get("_cevrimdisi"):
            raise ConnectionError("ag yok")
        return dict(bakiye)

    def _gonder(token, **k):
        giden.append(k)
        return not bakiye.get("_odeme_kopuk")  # okuma gider, düşüm gitmez → yolda kalan ödeme (2026-10-19)

    monkeypatch.setattr(j, "_bakiye_satiri_oku", _oku)
    monkeypatch.setattr(j, "_tuketim_gonder_canli", _gonder)
    tahminci = _Tahminci()
    gercek = air._get_or_load_model
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: tahminci if ad == "thermal" else gercek(ad, y))
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    client = TestClient(api_server.app, client=("127.0.0.1", 51234))
    yield client, j, bakiye, okunan, giden, tahminci
    t = getattr(j, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


def _termal(client, veri: bytes):
    return client.post(
        "/api/ai/vision/thermal",
        files={"file": ("k.jpg", veri, "image/jpeg")},
        headers={"Authorization": f"Bearer {_jwt('hekim-a')}"},
    )


def test_KRITIK_reddedilen_422_analiz_JETON_DUSURMEZ(ortam):
    client, j, bakiye, okunan, giden, _ = ortam
    r = _termal(client, _kamera_karesi())
    assert r.status_code == 422, r.text[:200]
    assert okunan, "KARŞIT: kapı bakiyeyi hiç okumadı — ölçüm kör (bayrak açık değil mi?)"
    assert giden == [], f"422 reddedilen analiz için jeton DÜŞTÜ: {giden}"


def test_KARSIT_KANIT_basarili_analiz_TAM_BIR_KEZ_tuketir(ortam):
    client, j, bakiye, okunan, giden, _ = ortam
    r = _termal(client, TERMAL.read_bytes())
    assert r.status_code == 200, r.text[:200]
    assert len(giden) == 1 and giden[0]["miktar"] == 1 and giden[0]["detay"] == "goruntu", giden


def test_KRITIK_model_HATASI_500_JETON_DUSURMEZ(ortam):
    client, j, bakiye, okunan, giden, tahminci = ortam
    tahminci.patlat = True
    r = _termal(client, TERMAL.read_bytes())
    assert r.status_code == 500, r.text[:200]
    assert giden == [], f"düşen analiz için jeton DÜŞTÜ: {giden}"


def test_KRITIK_istemci_KOPTUYSA_sonuc_teslim_edilemez_JETON_DUSURMEZ(ortam, monkeypatch):
    client, j, bakiye, okunan, giden, _ = ortam
    from starlette.requests import Request

    async def _koptu(self):
        return True

    monkeypatch.setattr(Request, "is_disconnected", _koptu)
    r = _termal(client, TERMAL.read_bytes())
    assert r.status_code == 200
    assert giden == [], f"istemcisi kopan (iptal edilen canlı kare) analiz için jeton DÜŞTÜ: {giden}"


def test_KRITIK_yolda_kalan_odeme_YALNIZ_basarili_analizde_deftere_yazilir(ortam):
    """Düşüm ağ kopukluğuyla gönderilemiyor (2026-10-19 — çevrimdışı analiz yok; defter = yolda kalan ödeme): reddedilen analiz
    deftere yazmaz, başarılı analiz yazar."""
    client, j, bakiye, okunan, giden, _ = ortam
    bakiye["_odeme_kopuk"] = True
    sayac = lambda: j._defter_yoneticisi(sahip=j._jwt_sahip(_jwt("hekim-a"))).sahibin_bekleyen_sayisi()  # noqa: E731
    assert sayac() == 0
    assert _termal(client, _kamera_karesi()).status_code == 422
    assert sayac() == 0, "reddedilen analiz deftere tüketim yazdı"
    assert _termal(client, TERMAL.read_bytes()).status_code == 200
    assert sayac() == 1, "başarılı analizin gönderilemeyen düşümü deftere YAZILMADI (yolda kalan ödeme kayboldu)"


def test_KRITIK_internetsiz_analiz_402_model_KOSMAZ_tuketim_YOK_S4B5(ortam, monkeypatch):
    """S-4B.5 (2026-10-19): internetsiz (bakiye okunamıyor) analiz uca HİÇ girmez — 402 + sebep başlığı, model çağrılmaz, tüketim yok."""
    client, j, bakiye, okunan, giden, tahminci = ortam
    bakiye["_cevrimdisi"] = True
    cagri: list = []
    gercek = tahminci.predict
    monkeypatch.setattr(tahminci, "predict", lambda *a, **k: (cagri.append(1), gercek(*a, **k))[1])
    r = _termal(client, TERMAL.read_bytes())
    assert r.status_code == 402, r.text[:200]
    assert r.headers.get("x-pemf-jeton-sebep") == "cevrimdisi", dict(r.headers)
    assert okunan, "KARŞIT: kapı bakiyeyi hiç okumadı — ölçüm kör"
    assert cagri == [] and giden == [], (
        f"internetsiz analiz modeli koşturdu ({len(cagri)}) ya da tüketim gönderdi ({giden})"
    )


def test_KARSIT_KANIT_yetersiz_bakiye_402_ve_tuketim_YOK(ortam):
    client, j, bakiye, okunan, giden, _ = ortam
    bakiye["satin_alinan"] = 0
    r = _termal(client, TERMAL.read_bytes())
    assert r.status_code == 402 and "Seans, acil durdurma" in r.json()["detail"], r.text[:200]
    assert giden == []


def test_KRITIK_tuketim_bagimliligi_router_da_ve_FONKSIYON_kapsamli():
    """Yapısal: tüketim yanıt GÖNDERİLMEDEN önce (fonksiyon kapsamı) koşar — istek kapsamında koşsaydı kopma sorusu yanıt
    teslim edildikten sonra sorulurdu (uvicorn tamamlanan yanıtta `http.disconnect` döner → hiçbir analiz ücretlenmezdi)."""
    from servers import ai_router as air

    bag = {getattr(d.dependency, "__name__", ""): d for d in air.ai_router.dependencies}
    assert "jeton_gate" in bag and "jeton_tuketimi" in bag, sorted(bag)
    assert bag["jeton_tuketimi"].scope == "function", bag["jeton_tuketimi"]
