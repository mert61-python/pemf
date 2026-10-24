# Author: mertaygn, cglrgrkn
"""D3.05 (B-2.13) — `kaydet=1` YALNIZ cihazın kendi ekranından (sıkı loopback) sunucunun masaüstüne yazar; LAN / tünel isteği
dosyayı YANITTA (akış) alır.

ÖLÇÜLEN KUSUR (HEAD): `/api/history/export_csv?kaydet=1` ve `export_pdf?kaydet=1` (ve aynı sınıf `/api/ai/log/{id}/pdf?kaydet=1`)
istemci adresine bakmadan sunucunun masaüstüne yazıyordu → kliniğin Wi-Fi'ındaki herhangi bir cihaz kliniğin düz-metin PII içeren
CSV / PDF'ini at-rest şifrelemenin DIŞINDA masaüstüne yazdırabiliyordu. Sahte yalnız EN ALT katta: masaüstü çözücüsü (conftest
izolasyonu) ve AI PDF üreticisinin girdisi değil — gerçek uçlar.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def masaustu():
    import servers.seans_alan_kaydi as sak

    dizin, _ = sak.masaustu_dizini()
    return Path(dizin)


def _istemci(host: str):
    from servers import api_server

    return TestClient(api_server.app, client=(host, 51306))


@pytest.fixture
def seans():
    """CSV yazma yolu ancak VERİ varken koşar (boş DB "kayıt yok" dalına girer — o dal hiç yazmaz; kör kapı olurdu)."""
    from servers.history_router import get_db

    sid = get_db().start_session(
        treatment_mode="Manuel", target_condition="test", operator_name="op", patient_name="D305Testi"
    )
    assert sid, "test seansı oluşturulamadı → kapı hiçbir şey ölçmüyor"
    return sid


def _dosyalar(d: Path) -> set[str]:
    return {p.name for p in d.glob("PEMF_*")} if d.is_dir() else set()


UZAK = [
    pytest.param("192.168.1.40", {}, id="LAN"),
    pytest.param("127.0.0.1", {"cf-connecting-ip": "203.0.113.5", "cf-ray": "8c1d-IST"}, id="tunel"),
]


@pytest.mark.parametrize(("host", "basliklar"), UZAK)
@pytest.mark.parametrize("uc", ["/api/history/export_pdf?session_ids=1&kaydet=1", "/api/history/export_csv?kaydet=1"])
def test_KRITIK_D3_05_LAN_ve_tunel_kaydet_istegi_MASAUSTUNE_YAZMAZ_akis_doner(masaustu, seans, host, basliklar, uc):
    once = _dosyalar(masaustu)
    r = _istemci(host).get(uc, headers=basliklar)
    assert _dosyalar(masaustu) == once, f"{host} isteği sunucunun masaüstüne dosya yazdı: {_dosyalar(masaustu) - once}"
    assert not (r.headers.get("content-type", "").startswith("application/json") and "yol" in r.text), (
        f"uzak isteğe masaüstü YOLU döndü: {r.text[:200]}"
    )


@pytest.mark.parametrize("uc", ["/api/history/export_pdf?session_ids=1&kaydet=1", "/api/history/export_csv?kaydet=1"])
def test_KARSIT_D3_05_cihazin_kendi_ekrani_MASAUSTUNE_yazar(masaustu, seans, uc):
    once = _dosyalar(masaustu)
    g = _istemci("127.0.0.1").get(uc).json()
    assert g.get("status") == "success" and Path(g["yol"]).exists(), g
    assert _dosyalar(masaustu) - once, "cihazın kendi ekranı masaüstüne yazamadı"


def test_KRITIK_D3_05_istek_nesnesi_YOKSA_yazilmaz_fail_closed():
    from servers.history_router import _masaustune_yazilir_mi

    assert _masaustune_yazilir_mi(1, None) is False
    assert _masaustune_yazilir_mi(0, object()) is False
