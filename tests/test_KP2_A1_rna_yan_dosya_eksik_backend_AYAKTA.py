# -*- coding: utf-8 -*-
"""KP-2 A1 (Y240, KP1-IB.2) · ai_hub/inference_human_kidney_rna/inference_human_kidney_rna.py `_require` · sözleşmeler:

- Yan dosya (best_model_meta.json / scaler.pkl / feature_indices.npy / classes.json) eksik → `FileNotFoundError` (dosya adı + yol iletide);
  `SystemExit` DEĞİL. Var olan dosyada `_require` hiçbir şey yükseltmez.
- `_load_meta_and_aux` dört yan dosyanın HER BİRİNİ denetler (biri eksikse o dosyanın adıyla düşer — sonraki yükleyici hatası değil).
- XAI yolu (`xai_top_genler`) da aynı yükleyiciden geçer → `FileNotFoundError` (uçtaki `except Exception` onu yakalar).
- GERÇEK uygulama yığını (`servers.api_server.app` + tüm ara katmanlar; uvicorn 0.48 `run_asgi` yakalaması) üzerinde RNA isteği yan dosya
  eksikken 500 + `ai.hata.rnaAnaliz` döner, olay döngüsü YAŞAR, aynı döngüdeki komşu iş tamamlanır ve ARDINDAN gelen ACİL DURDUR isteği
  200 + `confirmed` döner. (Önce: SystemExit `starlette/middleware/base.py` alt görevinden döngüye kaçıyor, döngü / backend süreci
  düşüyordu — hafıza "basehttpmiddleware-altinda-systemexit-sureci-dusurur".)

Sahte EN ALT katta: yalnız yan dosya yolları (modül sabitleri → tmp). Port / dinleyici YOK (ASGI doğrudan, kendi olay döngüsü).
ACİL DURDUR mandalı conftest `_estop_mandali_sizmaz` ile test sonunda sıfırlanır.
"""

from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import urlencode

import pandas as pd
import pytest
from utils import ceviri

from ai_hub.inference_human_kidney_rna import inference_human_kidney_rna as ihr

_YAN = [
    ("META_PATH", "best_model_meta.json"),
    ("SCALER_PATH", "scaler.pkl"),
    ("FEATURE_IDX_PATH", "feature_indices.npy"),
    ("CLASSES_PATH", "classes.json"),
]


def test_require_EKSIK_dosyada_FileNotFoundError_ad_ve_yol_iletide_SystemExit_DEGIL(tmp_path):
    """Eksik yan dosya → `FileNotFoundError` (SystemExit değil — BaseHTTPMiddleware altında süreci düşürmez); iletide etiket + yol."""
    eksik = tmp_path / "yok" / "scaler.pkl"
    with pytest.raises(FileNotFoundError) as ex:
        ihr._require(eksik, "scaler.pkl")
    assert not isinstance(ex.value, SystemExit)
    assert "scaler.pkl not found at" in str(ex.value)
    assert str(eksik) in str(ex.value)


def test_require_VAR_olan_dosyada_hicbir_sey_yukseltmez(tmp_path):
    """Var olan yan dosya → `_require` None döner (yükleme sürer)."""
    var = tmp_path / "classes.json"
    var.write_text("[]", encoding="utf-8")
    assert ihr._require(var, "classes.json") is None


@pytest.mark.parametrize("sira", range(len(_YAN)), ids=[ad for _, ad in _YAN])
def test_load_meta_and_aux_HER_yan_dosyayi_denetler_eksik_olanin_ADIYLA_duser(monkeypatch, tmp_path, sira):
    """Sıradaki yan dosya eksik (öncekiler var) → `_load_meta_and_aux` o dosyanın ADIYLA `FileNotFoundError` (denetim satırı silinirse
    yükleyicinin farklı hatası / sessiz geçiş yakalanır)."""
    for i, (sabit, ad) in enumerate(_YAN):
        yol = tmp_path / ad
        if i < sira:
            yol.write_bytes(b"{}")
        monkeypatch.setattr(ihr, sabit, yol)
    beklenen_ad = _YAN[sira][1]
    with pytest.raises(FileNotFoundError) as ex:
        ihr._load_meta_and_aux()
    assert f"{beklenen_ad} not found at" in str(ex.value)


def test_xai_top_genler_yan_dosya_eksikse_FileNotFoundError(monkeypatch, tmp_path):
    """XAI yolu da aynı yükleyiciden geçer → META eksikse `FileNotFoundError` (uçtaki `except Exception` yakalayıp `xai_error` yazar;
    SystemExit o yakalamayı da atlıyordu)."""
    monkeypatch.setattr(ihr, "META_PATH", tmp_path / "yok" / "best_model_meta.json")
    df = pd.DataFrame([[1.0, 2.0]], index=["h1"], columns=["g1", "g2"])
    with pytest.raises(FileNotFoundError) as ex:
        ihr.xai_top_genler(df)
    assert "best_model_meta.json not found at" in str(ex.value)


def _scope(yol: str, govde: bytes, tur: bytes) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": yol,
        "raw_path": yol.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver"), (b"content-type", tur), (b"content-length", str(len(govde)).encode())],
        "client": ("127.0.0.1", 50993),
        "server": ("testserver", 80),
        "state": {},
    }


def test_KRITIK_gercek_ASGI_yigininda_RNA_yan_dosya_eksik_500_dongu_YASAR_ardindan_ACIL_DURDUR_200(
    monkeypatch, tmp_path
):
    """Gerçek `api_server.app` (tüm ara katmanlar) + uvicorn 0.48 `run_asgi` yakalaması, tek olay döngüsü: META eksik RNA isteği →
    500 + `ai.hata.rnaAnaliz` (uvicorn sarmalına istisna ULAŞMAZ), döngü yaşar, komşu iş 30/30, öngörücü önbelleğe girmez; ARDINDAN
    aynı döngüde `POST /api/hardware/emergency_stop` → 200 + `confirmed: true` (backend ACİL DURDUR'a cevap vermeye devam eder)."""
    from servers import ai_client
    from servers import ai_router as air
    from servers import api_server as api

    monkeypatch.setattr(ihr, "META_PATH", tmp_path / "kurulum_eksik" / "best_model_meta.json")
    monkeypatch.setattr(air, "_models", {})
    monkeypatch.setattr(ai_client, "AI_SERVICE_URL", "")
    monkeypatch.setenv("PEMF_AI_DOMAIN_GUARD", "0")

    def _istek(yol: str, govde: bytes, tur: bytes, kayit: dict):
        kayit["yanit"], kayit["govde"] = [], b""
        verildi = {"g": False}

        async def _receive():
            if not verildi["g"]:
                verildi["g"] = True
                return {"type": "http.request", "body": govde, "more_body": False}
            await asyncio.sleep(3600)  # istemci bağlı kalır (uvicorn'da disconnect yalnız bağlantı kopunca)

        async def _send(m):
            if m["type"] == "http.response.start":
                kayit["yanit"].append(m["status"])
            elif m["type"] == "http.response.body":
                kayit["govde"] += m.get("body", b"")

        async def _run_asgi():  # uvicorn 0.48 protocols/http/h11_impl.py:413-424 ile aynı yakalama
            try:
                await api.app(_scope(yol, govde, tur), _receive, _send)
            except BaseException as exc:  # noqa: BLE001 — uvicorn'un kendisi böyle
                kayit["uvicorn_yakaladi"] = type(exc).__name__

        return _run_asgi()

    rna, estop, komsu, durum = {}, {}, [], {}

    async def _komsu():
        for i in range(30):
            await asyncio.sleep(0.01)
            komsu.append(i)

    async def _senaryo():
        k = asyncio.ensure_future(_komsu())
        rna_govde = urlencode({"csv_base64": base64.b64encode(b"id,g1,g2\nh1,1,2\n").decode("ascii")}).encode("ascii")
        await asyncio.wait_for(_istek("/api/ai/rna/kidney", rna_govde, b"application/x-www-form-urlencoded", rna), 20)
        await asyncio.wait_for(_istek("/api/hardware/emergency_stop", b"", b"application/json", estop), 30)
        await k

    dongu = asyncio.SelectorEventLoop()
    try:
        try:
            dongu.run_until_complete(_senaryo())
            durum["dongu"] = "YASADI"
        except BaseException as exc:  # noqa: BLE001 — ölçülen şey: döngüden kaçan istisna
            durum["dongu"] = f"OLDU: {type(exc).__name__}"
    finally:
        for _tur in range(6):
            bekleyen = [t for t in asyncio.all_tasks(dongu) if not t.done()]
            if not bekleyen:
                break
            for t in bekleyen:
                t.cancel()
            try:
                dongu.run_until_complete(asyncio.gather(*bekleyen, return_exceptions=True))
            except BaseException:  # noqa: BLE001 — temizlik sürer
                pass
        dongu.run_until_complete(dongu.shutdown_default_executor())
        dongu.close()

    assert durum["dongu"] == "YASADI"
    assert "uvicorn_yakaladi" not in rna
    assert rna["yanit"] == [500]
    assert json.loads(rna["govde"])["detail"] == ceviri.t("ai.hata.rnaAnaliz")
    assert komsu == list(range(30))
    assert "kidney_rna" not in air._models
    assert estop["yanit"] == [200] and "uvicorn_yakaladi" not in estop
    estop_govde = json.loads(estop["govde"])
    assert estop_govde["status"] == "success" and estop_govde["confirmed"] is True
