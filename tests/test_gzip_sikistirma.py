# -*- coding: utf-8 -*-
# Author: mertaygn
"""GZIP SIKIŞTIRMA — AI Hub planı, ADIM 5.

===============================================================================
NEDEN
===============================================================================
Çok panelli AI yanıtı (ADIM 3) base64 JPEG taşıyor ve base64 ikili veriyi **%33 şişirir**.
gzip o şişmeyi büyük ölçüde geri alır. Kazanç YALNIZ Tauri / doğrudan `:8000` yolunda —
docker/web dağıtımında nginx zaten sıkıştırıyor.

===============================================================================
⚠️ BU DOSYA NE ÖLÇER
===============================================================================
"Middleware kayıtlı mı" DEĞİL, **gerçek AI yanıtının** sıkıştırıldığı ölçülür — üstelik
uydurma bir test yolunda değil, ADIM 3'ün ürettiği gerçek 7 panelli petri yanıtında.

⚠️ İLK YAZIMDA çalışma anında `@app.get("/__gzip_kapi_testi__")` ile sahte bir uç ekleniyordu;
uygulama zaten kurulu olduğu için 404 döndü. Sahte uç kurulabilseydi bile YANLIŞ ŞEYİ ölçerdi:
kapının değeri, ÜRETİMDEKİ yükün sıkıştığını göstermesinde.

Ölçülenler:
  · gerçek AI yanıtı sıkışır ve gövde GERÇEKTEN gzip'tir (açılıp aslıyla karşılaştırılır),
  · küçük yanıt (`/api/health`) sıkışmaz — küçük yanıtta gzip saf CPU kaybı,
  · `accept-encoding` göndermeyen istemci BOZULMADAN çalışır,
  · WebSocket ETKİLENMEZ (Starlette gzip'i `http` olmayan scope'a dokunmaz).
"""

from __future__ import annotations

import ast
import io
import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51241))


def _asgari() -> int:
    from servers.api_server import GZIP_ASGARI_BAYT

    return GZIP_ASGARI_BAYT


def _panel(w: int, h: int):
    """Gürültülü BGR kare — düz renk aldatıcıdır (gzip onu %99 sıkıştırır, kapı hep yeşil görünür)."""
    rng = np.random.default_rng(w * 977 + h)
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


def _jpeg_gri(w: int = 256, h: int = 192) -> bytes:
    """Alan kapısından geçen gri gradyan (em_petri {COLOR, GRAYSCALE} kabul eder)."""
    g = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
    ok, buf = cv2.imencode(".jpg", cv2.merge([g, g, g]))
    assert ok
    return buf.tobytes()


class _SahteSonuc:
    def __init__(self):
        self.success = True
        self.error = None
        self.n_wells = 2
        self.n_cancer = 1
        self.n_healthy = 1
        self.method = "sahte"
        self.mm_per_px = 0.5
        self.wells = []
        self.timing_ms = {}
        self.plausibility = {}
        self.yolo_ayar = {}
        self.resize = {}


@pytest.fixture()
def sahte_boru(monkeypatch):
    """Petri boru hattını taklit et; 7 panel üretsin (modeller CI'da yüklü değil)."""
    from servers import ai_router
    from utils.panel_yayin import PETRI_PANEL_ADLARI

    olculer = [(640, 480), (800, 600), (320, 240), (1024, 768), (500, 900), (1200, 400), (1600, 1067)]
    paneller = {k: _panel(w, h) for k, (w, h) in zip(PETRI_PANEL_ADLARI, olculer)}

    class _SahtePipeline:
        def __init__(self, cfg, **kw):
            pass

        def process_image(self, img, **kw):
            return _SahteSonuc(), {}

        def render_panels(self, ctx, result, lang="tr"):
            return dict(paneller)

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(
        ai_router,
        "_get_or_load_model",
        lambda key, loader: {
            "cls": _SahtePipeline,
            "cfg": object(),
            "yolo_path": "x.onnx",
            "yolo": object(),
            "predictor": object(),
        },
    )


def _petri(client, kodlama: str):
    return client.post(
        "/api/ai/vision/em_petri",
        files={"file": ("t.jpg", _jpeg_gri(), "image/jpeg")},
        headers={"accept-encoding": kodlama},
    )


# ============================================================================
# 1. ⚠️ ASIL KAPI — GERÇEK AI YANITI SIKIŞIYOR
# ============================================================================


def test_KRITIK_AI_yaniti_GERCEKTEN_gzip(client, sahte_boru):
    """⚠️ Başlığa bakmak YETMEZ: `Content-Encoding: gzip` yazıp gövdeyi düz gönderen bir ara
    katman istemciyi çökertir. Gövde AÇILIP JSON olarak doğrulanır.

    MUTASYON: `app.add_middleware(GZipMiddleware, ...)` satırını sil → KIRMIZI.
    """
    r = _petri(client, "gzip")
    assert r.status_code == 200, r.text
    assert r.headers.get("content-encoding") == "gzip", "AI yaniti SIKISTIRILMADI"

    y = r.json()  # httpx gövdeyi kendisi açar → açılabildiğinin kanıtı
    assert len(y["paneller"]) == 7
    ham = len(json.dumps(y).encode("utf-8"))
    telde = int(r.headers["content-length"])
    assert telde < ham, f"gzip yuku BUYUTTU: {telde} >= {ham}"

    oran = telde / ham
    # ⚠️ base64 JPEG gürültüsünde beklenen kazanç ~%20-30 (base64'ün %33 şişmesinin geri
    # alınması). Eşik gevşek: asıl iddia "sıkışıyor", kesin oran makineye/JPEG'e bağlı.
    assert oran < 0.90, f"beklenen kazanc yok (oran {oran:.3f}, ham {ham} bayt)"
    print(f"\n[OLCUM] AI yaniti: ham {ham / 1024:.1f} KB -> telde {telde / 1024:.1f} KB (oran {oran:.3f})")


def test_KRITIK_accept_encoding_YOKSA_duz_yanit(client, sahte_boru):
    """⚠️ gzip'i istemeyen bir istemciye sıkıştırılmış gövde göndermek onu çökertir."""
    r = _petri(client, "identity")
    assert r.status_code == 200, r.text
    assert "content-encoding" not in {k.lower() for k in r.headers}
    assert len(r.json()["paneller"]) == 7


# ============================================================================
# 2. ⚠️ KÜÇÜK YANIT SIKIŞTIRILMAZ
# ============================================================================


def test_KRITIK_KUCUK_yanit_sikistirilmaz(client):
    """⚠️ Küçük yanıtta gzip SAF KAYIP: ~20 bayt gzip başlığı + CPU, kazanç yok. Sağlık ucu
    ve canlı durum anlık görüntüsü saniyede birkaç kez çekiliyor.

    MUTASYON: `minimum_size=GZIP_ASGARI_BAYT`ı `minimum_size=0` yap → KIRMIZI.
    """
    r = client.get("/api/health", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200, r.text
    assert len(r.content) < _asgari(), f"saglik yaniti beklenenden buyuk ({len(r.content)} bayt) — capa bayat"
    assert "content-encoding" not in {k.lower() for k in r.headers}, "kucuk yanit da sikistiriliyor -> saf CPU kaybi"


def test_esik_MAKUL_aralikta():
    """Eşik 0 ya da devasa olursa middleware ya her şeyi ya hiçbir şeyi sıkıştırır."""
    assert 512 <= _asgari() <= 8192, f"GZIP_ASGARI_BAYT makul aralik disinda: {_asgari()}"


# ============================================================================
# 3. ⚠️ WEBSOCKET ETKİLENMEZ
# ============================================================================


def test_KRITIK_WEBSOCKET_etkilenmez(client):
    """⚠️ Starlette gzip'i `scope["type"] != "http"` olan her şeyi dokunmadan geçirir.

    Canlı telemetri WS'i bozulsaydı kontrol ekranı sessizce ölürdü — bu bir cihaz ekranı.
    """
    with client.websocket_connect("/ws") as ws:
        ilk = ws.receive_json()
        assert isinstance(ilk, dict), f"WS ilk mesaji sozluk degil: {type(ilk)}"


# ============================================================================
# 4. YAPISAL — SÖZLEŞME TEK KAYNAKTA
# ============================================================================


def test_YAPISAL_gzip_KAYITLI_ve_asgari_boyut_SABITE_BAGLI():
    """Kayıt gerçekten `GZIP_ASGARI_BAYT` sabitini kullanmalı.

    ⚠️ Elle yazılmış bir sayı sabitle sessizce ayrışır ve yukarıdaki eşik kapısı anlamını
    yitirir (bu depoda "kopyalanan sabit" sınıfı defalarca ölçüldü).
    """
    agac = ast.parse(io.open(KOK / "servers" / "api_server.py", encoding="utf-8").read())
    bulundu = False
    for d in ast.walk(agac):
        if not isinstance(d, ast.Call):
            continue
        if not (isinstance(d.func, ast.Attribute) and d.func.attr == "add_middleware"):
            continue
        if d.args and isinstance(d.args[0], ast.Name) and d.args[0].id == "GZipMiddleware":
            bulundu = True
            kw = {k.arg: k.value for k in d.keywords}
            assert "minimum_size" in kw, "minimum_size verilmemis (Starlette varsayilani 500)"
            assert isinstance(kw["minimum_size"], ast.Name) and kw["minimum_size"].id == "GZIP_ASGARI_BAYT", (
                "minimum_size elle yazilmis sayi -> GZIP_ASGARI_BAYT ile sessizce ayrisir"
            )
    assert bulundu, "GZipMiddleware KAYITLI DEGIL"
