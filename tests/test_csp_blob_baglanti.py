# Author: mertaygn, cglrgrkn
"""CSP `connect-src`/`media-src` blob:/data: KAPISI (saha 2026-09-08).

ARIZA: masaüstü uygulaması (WebView2) AI analizinde "Ağ veya sunucu hatası." diyordu, backend'de
hiçbir istek/iz yoktu. Kök: `add_security_headers` CSP'sinde `connect-src 'self' https://*.supabase.co
ws://… wss://…` vardı ama `blob:`/`data:` YOKTU. Arayüz seçilen görseli `fetch(blob:…)` ile okuyup
FormData'ya koyar (AiHub'da imageFile yokken 7 çağrı yeri, scratch `dosya.file` yokken, ses kaydı);
tarayıcı bunu CSP ile kesince `TypeError: Failed to fetch` → arayüz "Ağ veya sunucu hatası".
`media-src` hiç yoktu → default-src 'self' devreye girip blob: ses çalmayı engelliyordu.
Headless Edge + CDP `securitypolicyviolation` ölçümü: connect-src->blob, connect-src->data,
media-src->blob (üçü de ihlal); yama sonrası sıfır ihlal.

Bu dosya middleware'i GERÇEKTEN koşturur (metin aramaz): sahte HTML yanıtı → CSP başlığını
yönergelere ayrıştırır ve ölçer. Mutasyonla KIRMIZI kanıtlandı: connect-src'den `blob:` silinince
test_KRITIK_connect_src_blob_ve_data_izinli düşer; media-src satırı silinince media testi düşer.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse


def _istek(host: str = "127.0.0.1:8000", yol: str = "/") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": yol,
        "raw_path": yol.encode(),
        "query_string": b"",
        "scheme": "http",
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 51000),
        "headers": [(b"host", host.encode())],
    }
    return Request(scope)


def _csp_yonergeleri(csp: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for parca in csp.split(";"):
        parca = parca.strip()
        if not parca:
            continue
        ad, *kaynaklar = parca.split()
        out[ad] = kaynaklar
    return out


@pytest.fixture(scope="module")
def middleware():
    import servers.api_server as api

    return api.add_security_headers


def _kostur(middleware, yanit, host: str = "127.0.0.1:8000"):
    async def _call_next(_request):
        return yanit

    return asyncio.run(middleware(_istek(host), _call_next))


def test_KRITIK_connect_src_blob_ve_data_izinli(middleware):
    """Arayüzün fetch(blob:) / fetch(data:) yolu CSP'ye takılmamalı (aksi halde her AI yükleme
    'Ağ veya sunucu hatası')."""
    r = _kostur(middleware, HTMLResponse("<html></html>"))
    csp = r.headers.get("content-security-policy", "")
    assert csp, "HTML yanıtında CSP başlığı yok — koruma tamamen kalkmış"
    y = _csp_yonergeleri(csp)
    assert "connect-src" in y, f"connect-src yönergesi yok: {csp}"
    assert "blob:" in y["connect-src"], (
        f"connect-src'de blob: YOK → tarayıcı fetch(blob:) isteğini keser, arayüz 'Ağ veya sunucu "
        f"hatası' der, backend'e istek hiç gelmez (saha 2026-09-08). connect-src={y['connect-src']}"
    )
    assert "data:" in y["connect-src"], f"connect-src'de data: YOK (fetch(data:) yolu kesilir): {y['connect-src']}"


def test_KRITIK_media_src_blob_izinli(middleware):
    """Kayıt/yükleme sesi blob: URL'den çalınır; media-src yoksa default-src 'self' engeller."""
    r = _kostur(middleware, HTMLResponse("<html></html>"))
    y = _csp_yonergeleri(r.headers.get("content-security-policy", ""))
    assert "media-src" in y, "media-src yönergesi yok → default-src 'self' blob: ses çalmayı keser"
    assert "blob:" in y["media-src"] and "data:" in y["media-src"], f"media-src eksik: {y['media-src']}"


def test_sizinti_onleme_korundu_self_ws_supabase_ve_kilitler(middleware):
    """Karşı-kanıt: gevşetme 'her şeye izin'e dönmemeli — connect-src hâlâ self + Supabase + aynı-host
    ws/wss ile sınırlı; object/base/frame-ancestors kilitleri yerinde."""
    r = _kostur(middleware, HTMLResponse("<html></html>"), host="192.168.1.20:8000")
    y = _csp_yonergeleri(r.headers.get("content-security-policy", ""))
    c = y["connect-src"]
    assert "'self'" in c and "https://*.supabase.co" in c
    assert "ws://192.168.1.20:8000" in c and "wss://192.168.1.20:8000" in c, f"aynı-host ws/wss yok: {c}"
    # blob:/data: dışında joker şema/host YOK (örn. 'ws:' , 'https:' , '*')
    yasak = [k for k in c if k in ("*", "ws:", "wss:", "http:", "https:", "'unsafe-inline'")]
    assert not yasak, f"connect-src gereksiz gevşetilmiş: {yasak}"
    assert y.get("object-src") == ["'none'"] and y.get("base-uri") == ["'none'"]
    assert y.get("frame-ancestors") == ["'self'"]


def test_csp_yalniz_html_yanitina_eklenir(middleware):
    """JSON API yanıtına CSP eklenmez (eski davranış korunur; tarayıcı-dışı istemciler için gürültü)."""
    r = _kostur(middleware, JSONResponse({"ok": True}))
    assert "content-security-policy" not in {k.lower() for k in r.headers.keys()}
    assert r.headers.get("x-content-type-options") == "nosniff"
