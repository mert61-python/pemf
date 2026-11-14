# -*- coding: utf-8 -*-
"""KP-5 · 17 (İH #22 kalıntısı, KP5-LISTESI 17): erişimsiz Windows hesabında hasta listesi "Hastalar yüklenemedi. Bağlantıyı kontrol edin."
diyordu — yanıltıcı (bağlantı sağlam, sorun İZİN). Liste ucu DB'siz kipte hasta DB'sinin açılış nedeni ERİŞİM YOK ise sağlık ucunun
`dbSebep`iyle AYNI erişim iletisini (`sistem.db.erisimYok`, eylem: başlatıcının paylaşım kartı) 503 gerekçesi olarak verir; başka
nedende (göç / bozuk) liste okuma iletisi AYNEN. Uçtan uca gerçek ACL benzetimi: `test_acilis_DB_acilamasa_ACIL_DURDUR_yasar.py` A14
(alt süreçte gerçek `main()`); bu dosya aynı kararı süreç İÇİNDE (kapsam ölçülür) ve iki dilde sabitler.

Arıza EN ALT katta: ürünün kendi açılış kilidi (`acilis_hatasini_kilitle`) + çekirdeğin açılış ayrıntısı (`db_acilis_ayrintilari`,
`HeadlessCore._db_ac`'ın yazdığı biçim)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class _Cekirdek:
    """`HeadlessCore`un sağlık / liste ucunun okuduğu iki sözlüğü (aynı biçim: ad → metin · ad → (tür, istisna adı))."""

    def __init__(self, tur: str):
        from headless_core import db_acilis_metni

        self.db_acilis_hatalari = {"hasta": db_acilis_metni(tur, "hasta", "PermissionError", "tr"), "tedavi": None}
        self.db_acilis_ayrintilari = {"hasta": (tur, "PermissionError")}


def _istemci(monkeypatch, tur: str) -> TestClient:
    from servers import api_server, patient_router
    from utils.path_utils import get_app_data_directory

    g = patient_router.get_patient_database.__globals__  # ucun KENDİ modülü (bkz. D1S7 aparatı)
    monkeypatch.setitem(g, "_patient_db", None)
    monkeypatch.setitem(g, "_acilis_kilidi", {})
    g["acilis_hatasini_kilitle"](get_app_data_directory(), PermissionError(13, "Erişim engellendi"))
    monkeypatch.setattr(api_server.state, "core", _Cekirdek(tur), raising=False)
    return TestClient(api_server.app, client=("127.0.0.1", 50000), raise_server_exceptions=False)


@pytest.mark.parametrize(
    "dil, beklenen",
    [
        ("tr", "Bu Windows hesabının PEMF verisine erişimi yok — başlatıcıdaki paylaşım kartıyla erişim verin."),
        (
            "en",
            "This Windows account has no access to the PEMF data — grant access with the sharing card in the launcher.",
        ),
    ],
)
def test_KRITIK_erisimsiz_hesapta_hasta_listesi_503_ERISIM_iletisi_saglikla_AYNI(monkeypatch, dil, beklenen):
    c = _istemci(monkeypatch, "erisimYok")
    r = c.get("/api/patients", headers={"X-PEMF-Dil": dil})
    assert r.status_code == 503, r.text[:200]
    assert r.json()["detail"] == beklenen, r.json()
    h = c.get("/api/health", headers={"X-PEMF-Dil": dil}).json()
    assert h["dbReady"] is False and h["dbSebep"] == beklenen, f"liste ile sağlık nedeni AYRIŞTI: {h.get('dbSebep')!r}"


@pytest.mark.parametrize("tur", ["goc", "acilamadi", "eskiKok"])
def test_KARSIT_baska_nedende_liste_okuma_iletisi_AYNEN(monkeypatch, tur):
    r = _istemci(monkeypatch, tur).get("/api/patients", headers={"X-PEMF-Dil": "tr"})
    assert r.status_code == 503
    assert "yeni kart açmayın" in r.json()["detail"] and "erişimi yok" not in r.json()["detail"], r.json()
