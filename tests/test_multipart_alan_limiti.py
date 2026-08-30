# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MULTIPART FORM-ALANI LİMİTİ — saha bulgusu 2026-08-30.

Yara Kapanma (scratch) analizinde büyük görüntü seçince "Part/Field exceeded maximum size of
1024KB" hatası geliyordu; mobil görüntüyü `image_base64` FORM ALANI olarak gönderiyor ve
Starlette non-file alanlara 1MB varsayılan uyguluyor.

⚠️ Bu test, DÜZELTMENİN GERÇEKTEN ÇALIŞTIĞINI FastAPI ile uçtan uca kanıtlar — çünkü önceki
"çözüm" (`ai_router._allow_large_upload`, `request.form(max_part_size=)`) ÖLÇÜLDÜĞÜNDE FastAPI ile
çalışmıyordu (form cache'i erken doluyordu). Bu kapı, o sessiz-bozukluğun tekrarını yakalar.
"""

from __future__ import annotations

import pytest

from utils.multipart_limit import MAX_FIELD_BYTES, buyuk_form_alani_limitini_uygula


@pytest.fixture(scope="module", autouse=True)
def _patch():
    buyuk_form_alani_limitini_uygula()  # idempotent


def _app_client():
    from fastapi import FastAPI, Form
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.post("/t")
    async def t(image_base64: str = Form(None)):
        return {"len": len(image_base64 or "")}

    return TestClient(app)


def test_KRITIK_1MB_ustu_base64_alani_GECER():
    """⚠️ Sahadaki hatanın ta kendisi: 1MB'dan büyük base64 form alanı artık 400 vermemeli.

    (Önceki request.form(max_part_size=) yolu burada 400 veriyordu — FastAPI cache'i.)"""
    c = _app_client()
    r = c.post("/t", data={"image_base64": "A" * (3 * 1024 * 1024)})  # 3 MB
    assert r.status_code == 200, (
        f"1MB üstü base64 alanı reddedildi ({r.status_code}: {r.text[:80]}) → scratch analizi başlamaz"
    )
    assert r.json()["len"] == 3 * 1024 * 1024


def test_ust_TAVAN_korunuyor_RAM_DoS():
    """Limit sınırsız DEĞİL: tavanı aşan alan yine 400 (bellek koruması)."""
    c = _app_client()
    asiri = "A" * (MAX_FIELD_BYTES + 2 * 1024 * 1024)
    r = c.post("/t", data={"image_base64": asiri})
    assert r.status_code == 400, "tavan üstü alan geçti → RAM DoS koruması kalktı"


def test_25MB_image_base64_SIGAR():
    """Uçların en büyük base64 girdisi (25 MB image, _MAX_IMAGE_BYTES) tavanın ALTINDA olmalı."""
    assert MAX_FIELD_BYTES >= 25 * 1024 * 1024, (
        "field limiti 25 MB base64 image'i karşılamıyor → büyük görüntü hâlâ takılır"
    )


def test_patch_IDEMPOTENT():
    """İkinci çağrı no-op (çift-patch/sonsuz sarmalama yok)."""
    from starlette.requests import Request

    buyuk_form_alani_limitini_uygula()
    assert getattr(Request.form, "_pemf_multipart_patched", False) is True
    assert buyuk_form_alani_limitini_uygula() is False


def test_KRITIK_api_server_PATCHI_UYGULUYOR():
    """⚠️ ZAYIF-ÇIPA: util doğru olsa da api_server onu çağırmazsa sahada etki YOK."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "servers" / "api_server.py").read_text(encoding="utf-8")
    assert "buyuk_form_alani_limitini_uygula" in src or "_buyuk_form_limiti" in src, (
        "api_server multipart limit patch'ini çağırmıyor → scratch hatası geri gelir"
    )
