# -*- coding: utf-8 -*-
"""DEV-D5.GPU (21'in devri → 22-SON) — GPU mikroservisinin (`ai_service/app.py`, :8100) açıklama hatası İSTEK DİLİNDE gelir.

ÖLÇÜLEN (D67 §5): servis katalog taşımaz → `xai_error`ı 12 yerde SABİT Türkçe ("Açıklama üretilemedi", "Açıklama en fazla 25 hastalık CSV
için üretilir (IG maliyeti).") döndürüyordu; gömülü yol (`ai_router`) aynı alanı `ceviri.t` ile İSTEK dilinde kurar. Mikroservis
profilinde İngilizce arayüz Türkçe açıklama hatası gösteriyordu. Artık arka uç servis yanıtını TEK yerde (`ai_client._post_*`) katalog
metnine çevirir (gömülü yolla AYNI anahtarlar). Servisin sabit metni eşleme anahtarıdır → servis metni değişirse burada KIRMIZI (sessizce
Türkçe kalmaz).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


def _servis_xai_hata_metinleri() -> set[str]:
    agac = ast.parse((KOK / "ai_service" / "app.py").read_text(encoding="utf-8"))
    bulunan = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Assign) and isinstance(d.value, ast.Constant) and isinstance(d.value.value, str):
            for h in d.targets:
                if isinstance(h, ast.Subscript) and isinstance(h.slice, ast.Constant) and h.slice.value == "xai_error":
                    bulunan.add(d.value.value)
    return bulunan


def test_KRITIK_servisin_HER_xai_error_metni_eslemede_VAR():
    from servers import ai_client

    metinler = _servis_xai_hata_metinleri()
    assert len(metinler) >= 2, f"aparat: servisteki xai_error atamaları bulunamadı: {metinler}"
    eksik = sorted(metinler - set(ai_client._XAI_HATA_METINLERI))
    assert not eksik, f"servis yeni / değişmiş xai_error metni döndürüyor — eşleme yok, istemciye TÜRKÇE gider: {eksik}"


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_xai_hatasi_ISTEK_dilinde_katalog_metnine_cevrilir(dil):
    from servers import ai_client
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(dil)
    try:
        for servis_metni, anahtar in ai_client._XAI_HATA_METINLERI.items():
            yanit = ai_client._xai_hatasini_cevir({"xai_error": servis_metni, "success": True})
            assert yanit["xai_error"] == ceviri.t(anahtar, dil), (dil, servis_metni, yanit)
            assert yanit["success"] is True
        if dil == "en":
            assert (
                ai_client._xai_hatasini_cevir({"xai_error": "Açıklama üretilemedi"})["xai_error"]
                == "Explanation could not be generated"
            )
    finally:
        ceviri.istek_dili_var.reset(jeton)


def test_KARSIT_bilinmeyen_metin_ve_sozluk_olmayan_yanit_AYNEN():
    from servers import ai_client

    assert ai_client._xai_hatasini_cevir({"xai_error": "başka bir şey"}) == {"xai_error": "başka bir şey"}
    assert ai_client._xai_hatasini_cevir({"top_1_class": "A"}) == {"top_1_class": "A"}
    assert ai_client._xai_hatasini_cevir([1, 2]) == [1, 2]


def test_KRITIK_iki_gonderim_yolu_da_ceviriden_GECER(monkeypatch):
    """`_post_sync` (iş parçacığı yolu) ve `_post_async` yanıtı çeviriden geçirir — sahte EN ALTTA: httpx istemcisi."""
    import asyncio

    from servers import ai_client
    from utils import ceviri

    class _Yanit:
        def raise_for_status(self):
            return None

        def json(self):
            return {"xai_error": "Açıklama üretilemedi"}

    class _Istemci:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Yanit()

        def close(self):
            return None

    class _AsyncIstemci(_Istemci):
        async def post(self, *a, **k):
            return _Yanit()

    monkeypatch.setattr(ai_client.httpx, "Client", _Istemci)
    monkeypatch.setattr(ai_client.httpx, "AsyncClient", _AsyncIstemci)
    jeton = ceviri.istek_dili_var.set("en")
    try:
        assert ai_client._post_sync("http://127.0.0.1:9/x")["xai_error"] == "Explanation could not be generated"
        assert (
            asyncio.run(ai_client._post_async("http://127.0.0.1:9/x"))["xai_error"]
            == "Explanation could not be generated"
        )
    finally:
        ceviri.istek_dili_var.reset(jeton)
