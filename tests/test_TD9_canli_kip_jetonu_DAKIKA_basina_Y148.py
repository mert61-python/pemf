# -*- coding: utf-8 -*-
"""TD9 (Y148, sahip 2026-10-14) — CANLI kamera kipinde jeton DAKİKA BAŞINA; kareler ücretsiz, sonuçsuz / hatalı dakika 0.

ÖLÇÜLEN DURUM (SG S-SG.4): canlı kipte her BAŞARILI kare 1 jeton ("goruntu"); uyarlamalı döngüyle dakikada ~60'a kadar (10 dk ≈ 600).
SÖZLEŞME: istemci canlı oturum başına `X-PEMF-Canli-Oturum` gönderir; oturumun ilk karesinden itibaren 60 sn'lik her kova için, en az
bir SONUÇ teslim edildiyse TEK tüketim (`istek_id` = `canli-<oturum>-<kova>`, `detay` = "canli_dakika", `tur` MEVCUT tür — yeni
`token_ledger.tur` YOK). "Kedi bulunamadı" ve ret / hata kareleri ücretlendirmez. Yolda kalan ödeme defterinde de kova başına tek
kayıt; internetsiz canlı kare 402 (2026-10-19 S-4B.5 — çevrimdışı analiz yok).
Elle analiz (başlıksız) ve AI Pro kare muafiyeti DEĞİŞMEZ.
Ölçüm: GERÇEK uygulama + GERÇEK `jeton_gate` / `jeton_tuketimi` + GERÇEK uçlar; sahte yalnız Supabase taşıması, model ve saat.
"""

from __future__ import annotations

import base64
import importlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
TERMAL = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"
OTURUM = "canli-test-0001abcd"


def _jwt(sub: str) -> str:
    b = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{b}.imza"


def _oda_karesi() -> bytes:
    rng = np.random.default_rng(7)
    img = np.zeros((240, 320, 3), np.float32)
    img[:] = (150, 165, 185)
    cv2.rectangle(img, (40, 60), (200, 200), (90, 110, 140), -1)
    img = np.clip(img + rng.normal(0, 6, img.shape), 0, 255).astype(np.uint8)
    return cv2.imencode(".jpg", img)[1].tobytes()


class _Termal:
    def predict(self, yol, threshold=0.5):
        return {"label": "Healthy", "probability_sick": 0.1, "confidence": 0.9}


class _Seg:
    def __init__(self):
        self.kedi = 1

    def predict(self, **k):
        return [SimpleNamespace(boxes=[0] * self.kedi, masks=None)]


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    j = importlib.import_module("servers.jeton")
    from servers import ai_router as air
    from servers import api_server

    monkeypatch.setattr(j, "JETON_ENFORCED", True)
    monkeypatch.setattr(j, "_son_uzlastirma", None, raising=False)
    if hasattr(j, "_canli_oturumlar"):
        monkeypatch.setattr(j, "_canli_oturumlar", {})
    saat = [1000.0]
    monkeypatch.setattr(j, "time", SimpleNamespace(monotonic=lambda: saat[0], time=lambda: 1.7e9 + saat[0]))
    bakiye = {"aylik_hak": 0, "satin_alinan": 1000, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}
    giden = []

    def _oku(token):
        if bakiye.get("_cevrimdisi"):
            raise ConnectionError("ag yok")
        return dict(bakiye)

    monkeypatch.setattr(j, "_bakiye_satiri_oku", _oku)
    monkeypatch.setattr(j, "_tuketim_gonder_canli", lambda token, **k: giden.append(k) or True)
    seg = _Seg()
    gercek = air._get_or_load_model
    monkeypatch.setattr(
        air,
        "_get_or_load_model",
        lambda ad, y: _Termal() if ad == "thermal" else (seg if ad == "seg" else gercek(ad, y)),
    )
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    client = TestClient(api_server.app, client=("127.0.0.1", 51235))
    yield SimpleNamespace(
        client=client, j=j, bakiye=bakiye, giden=giden, saat=saat, seg=seg,
        defter=tmp_path / "PEMF_GUI" / "jeton_bekleyen.json",  # Y202: defter `<PEMF_DATA_DIR>/PEMF_GUI/` altında
    )  # fmt: skip
    t = getattr(j, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


def _kare(o, uc="thermal", canli=True, veri=None):
    h = {"Authorization": f"Bearer {_jwt('hekim-a')}"}
    if canli:
        h["X-PEMF-Canli-Oturum"] = OTURUM
    veri = veri if veri is not None else (TERMAL.read_bytes() if uc == "thermal" else _oda_karesi())
    return o.client.post(f"/api/ai/vision/{uc}", files={"file": ("k.jpg", veri, "image/jpeg")}, headers=h)


def test_KRITIK_10_dakika_canli_kullanim_EN_COK_10_jeton(ortam):
    o = ortam
    for _ in range(120):  # 10 dk, 5 sn'de bir kare (gerçekte ~1/sn — kural kare sayısından bağımsız)
        r = _kare(o)
        assert r.status_code == 200, r.text[:200]
        o.saat[0] += 5.0
    toplam = sum(int(k["miktar"]) for k in o.giden)
    assert toplam <= 10, f"10 dk canlı kullanımda {toplam} jeton ({len(o.giden)} tüketim) — dakika başına olmalı"
    assert toplam == 10 and all(k["detay"] == "canli_dakika" and k["tur"] == "analiz" for k in o.giden), o.giden[:3]
    assert sorted(_kova_no(k["istek_id"]) for k in o.giden) == list(range(10)), o.giden


def _kova_no(iid: str) -> int:
    """`canli-<oturum>-<nesil>-<kova>` (SGI-2.2: nesil yeniden başlayan süreçte kimlik tekrarını önler) → kova."""
    import re

    m = re.fullmatch(rf"canli-{OTURUM}-[0-9a-f]{{8}}-(\d+)", iid)
    assert m, iid
    return int(m.group(1))


def test_KRITIK_kedisiz_ve_hatali_dakika_UCRETSIZ(ortam):
    o = ortam
    o.seg.kedi = 0
    for _ in range(6):  # dakika 0: kedi yok (bilgi yanıtı 200)
        r = _kare(o, uc="segmentation")
        assert r.status_code == 200 and r.json()["cat_count"] == 0, r.text[:200]
        o.saat[0] += 10.0
    for _ in range(6):  # dakika 1: termal uca termal olmayan kare → 422
        assert _kare(o, uc="thermal", veri=_oda_karesi()).status_code == 422
        o.saat[0] += 10.0
    assert o.giden == [], f"kedisiz / hatalı dakika ücretlendi: {o.giden}"
    o.seg.kedi = 1
    assert _kare(o, uc="segmentation").status_code == 200  # dakika 2: sonuç → 1 jeton
    assert [_kova_no(k["istek_id"]) for k in o.giden] == [2], o.giden


def test_KRITIK_ayni_dakika_IKI_KEZ_dusmez_yolda_kalan_odeme_defterinde_de(ortam, monkeypatch):
    """Düşüm ağ kopukluğuyla gönderilemedi (yolda kalan ödeme, 2026-10-19 — çevrimdışı analiz artık yok): dakika kovası defterde de TEK."""
    o = ortam
    monkeypatch.setattr(o.j, "_tuketim_gonder_canli", lambda token, **k: False)
    for _ in range(5):
        assert _kare(o).status_code == 200
        o.saat[0] += 3.0
    kayitlar = json.loads(o.defter.read_text(encoding="utf-8"))
    assert [_kova_no(k["istek_id"]) for k in kayitlar] == [0] and kayitlar[0]["miktar"] == 1, kayitlar


def test_KRITIK_internetsiz_canli_kare_402_cevrimdisi_ve_defter_YOK_S4B5(ortam):
    """S-4B.5 (2026-10-19): internetsiz canlı kare de analiz değildir — 402, sebep başlığı `cevrimdisi`, defter yazılmaz (eskiden
    çevrimdışı izin + defter)."""
    o = ortam
    o.bakiye["_cevrimdisi"] = True
    r = _kare(o)
    assert r.status_code == 402, r.text[:200]
    assert r.headers.get("x-pemf-jeton-sebep") == "cevrimdisi", dict(r.headers)
    assert "internet gerekir" in r.json().get("detail", ""), r.text[:200]
    assert not o.defter.exists() and o.giden == [], "internetsiz canlı kare deftere / sunucuya tüketim yazdı"


def test_KARSIT_elle_analiz_DEGISMEZ_her_analiz_1_goruntu(ortam):
    o = ortam
    for _ in range(3):
        assert _kare(o, canli=False).status_code == 200
    assert [(k["miktar"], k["detay"]) for k in o.giden] == [(1, "goruntu")] * 3, o.giden


def test_KARSIT_gecersiz_oturum_kimligi_ELLE_sayilir(ortam):
    o = ortam
    h = {"Authorization": f"Bearer {_jwt('hekim-a')}", "X-PEMF-Canli-Oturum": "../x"}
    for _ in range(2):
        r = o.client.post(
            "/api/ai/vision/thermal", files={"file": ("k.jpg", TERMAL.read_bytes(), "image/jpeg")}, headers=h
        )
        assert r.status_code == 200
    assert [k["detay"] for k in o.giden] == ["goruntu", "goruntu"], o.giden


def test_canli_dakika_maliyeti_WEB_ile_AYNI():
    import re

    j = importlib.import_module("servers.jeton")
    web = (KOK / "apps" / "web" / "src" / "config.ts").read_text(encoding="utf-8")
    m = re.search(r"maliyet:\s*\{([^}]*)\}", web)
    assert m and re.search(r"canli_dakika:\s*1\b", m.group(1)) and j.MALIYET.get("canli_dakika") == 1


def test_bekleme_suresi_SAHTE_saat_disinda_gercek_time_kullanilmaz():
    """Aparat kontrolü: modül `time`ı yamalanabilir (gerçek saat testleri yavaşlatmaz)."""
    j = importlib.import_module("servers.jeton")
    assert j.time is time or hasattr(j.time, "monotonic")


def test_KRITIK_arayuzun_IKI_canli_dongusu_oturum_basligini_GONDERIR():
    """Başlık adı backend ile AYNI ve AI Hub'daki canlı kare döngüleri (görüntü modülleri, kedi organ; T3 · Y190e: + petri / fantom
    `useEmCanli`) onu gönderir — gönderilmezse canlı kareler "elle analiz" sayılıp kare başına ücretlenir (Y148 ihlali)."""
    import re

    j = importlib.import_module("servers.jeton")
    ts = (KOK / "apps" / "ui" / "src" / "utils" / "canliKare.ts").read_text(encoding="utf-8")
    m = re.search(r'CANLI_OTURUM_BASLIGI = "([^"]+)"', ts)
    assert m and m.group(1).lower() == j.CANLI_OTURUM_BASLIGI, (m and m.group(1), j.CANLI_OTURUM_BASLIGI)
    ekran = (KOK / "apps" / "ui" / "src" / "screens" / "AiHubScreen.tsx").read_text(encoding="utf-8")
    assert ekran.count("[CANLI_OTURUM_BASLIGI]: oturum.kimlik") == 3, (
        "canlı döngülerden biri oturum başlığını göndermiyor"
    )
