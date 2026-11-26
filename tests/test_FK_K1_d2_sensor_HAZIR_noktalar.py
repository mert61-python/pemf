# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FK · K1 d2 (istem 58) — "Kabin sensörü (MLX)" konum girişinde tezgâh planının HAZIR NOKTALARI (yeni şema / uç YOK).

KUSUR: K2'de sahip MLX'i 7 kedi organ noktası arasında taşıyacak; giriş her noktada üç sayının (sol / ön / yükseklik) elle yazılmasını
istiyordu (nokta adı / sırası yok, yazım hatası dilim tahminini sessizce başka noktaya götürür). DÜZELTME: veri kökündeki
`kabin_kalibrasyonu/sensor_noktalari.json` (kedi fizik planı üretir) süzülüp canlı ucun `hazir` alanında döner; arayüz dokununca alanları
doldurur (kayıt mevcut girişle). Dosya yok / bozuk → boş liste, uç ve form bugünküyle aynı. Geçersiz nokta atlanır (aynı `dogrula`).
"""

from __future__ import annotations

import json

import pytest


def _yaz(kok, veri):
    d = kok / "kabin_kalibrasyonu"
    d.mkdir(parents=True, exist_ok=True)
    (d / "sensor_noktalari.json").write_text(
        veri if isinstance(veri, str) else json.dumps(veri, ensure_ascii=False), encoding="utf-8"
    )


def test_KRITIK_FK_K1_d2_hazir_noktalar_SIRALI_suzulmus_ve_iki_dilli(tmp_path):
    from servers import sensor_konumu as sk

    _yaz(
        tmp_path,
        {
            "noktalar": [
                {
                    "ad": {"tr": "Kedi orta · karaciğer", "en": "Cat orta · liver"},
                    "sol_cm": 28.2,
                    "on_cm": 20.0,
                    "yukseklik_cm": 7.25,
                },
                {"ad": "Yalnız ad", "sol_cm": 13, "on_cm": 24.8, "yukseklik_cm": 7.25},
                {"ad": {"tr": "aralık dışı"}, "sol_cm": 120, "on_cm": 1, "yukseklik_cm": 1},
                {"ad": {"tr": "sayı değil"}, "sol_cm": "abc", "on_cm": 1, "yukseklik_cm": 1},
                {"ad": {"tr": "  "}, "sol_cm": 1, "on_cm": 1, "yukseklik_cm": 1},
                {"ad": {"en": "yalnız en"}, "sol_cm": 1, "on_cm": 1, "yukseklik_cm": 1},
                "nokta değil",
                {"ad": {"tr": "eksik"}, "sol_cm": 1, "on_cm": 1},
            ]
        },
    )
    r = sk.hazir_noktalar(tmp_path)
    assert r == [
        {
            "ad": {"tr": "Kedi orta · karaciğer", "en": "Cat orta · liver"},
            "sol_cm": 28.2,
            "on_cm": 20.0,
            "yukseklik_cm": 7.25,
        },
        {"ad": {"tr": "Yalnız ad", "en": "Yalnız ad"}, "sol_cm": 13.0, "on_cm": 24.8, "yukseklik_cm": 7.25},
    ]


def test_KRITIK_FK_K1_d2_hazir_noktalar_AZAMI_ve_uzun_ad_kirpilir(tmp_path):
    from servers import sensor_konumu as sk

    _yaz(
        tmp_path,
        {
            "noktalar": [
                {"ad": {"tr": "n" * 500, "en": ""}, "sol_cm": i % 50, "on_cm": 1, "yukseklik_cm": 1} for i in range(60)
            ]
        },
    )
    r = sk.hazir_noktalar(tmp_path)
    assert len(r) == sk.HAZIR_AZAMI
    assert len(r[0]["ad"]["tr"]) == sk.NOT_AZAMI and r[0]["ad"]["en"] == r[0]["ad"]["tr"]  # EN boş → TR


@pytest.mark.parametrize(
    "veri", [None, "{bozuk", json.dumps([1, 2]), json.dumps({"noktalar": "x"}), json.dumps({"baska": []})]
)
def test_KARSIT_FK_K1_d2_dosya_YOK_ya_da_BOZUK_bos_liste(tmp_path, veri):
    from servers import sensor_konumu as sk

    if veri is not None:
        _yaz(tmp_path, veri)
    assert sk.hazir_noktalar(tmp_path) == []


def test_KRITIK_FK_K1_d2_canli_uc_HAZIR_alani(tmp_path, monkeypatch):
    """Canlı uç (`GET /api/session/sensor_konumu`): liste DOLUYSA seans yokken de / seansta `hazir` taşır; dosya yokken yanıt BİREBİR eski."""
    from fastapi.testclient import TestClient
    from servers import api_server as api

    beklenen = [
        {
            "ad": {"tr": "Kedi p1 · mesane", "en": "Cat p1 · bladder"},
            "sol_cm": 13.3,
            "on_cm": 25.9,
            "yukseklik_cm": 7.25,
        }
    ]
    monkeypatch.setattr(api, "_app_data_dir", lambda: str(tmp_path))
    c = TestClient(api.app)
    # KARŞIT: dosya YOKKEN yanıt bugünküyle BİREBİR (`hazir` anahtarı hiç yok)
    assert c.get("/api/session/sensor_konumu").json() == {"aktif": False, "konum": None}
    _yaz(tmp_path, {"noktalar": beklenen})
    j = c.get("/api/session/sensor_konumu").json()
    assert j == {"aktif": False, "konum": None, "hazir": beklenen}

    class _Db:
        def sensor_konumlari(self, sid):
            return [{"id": 1, "sol_cm": 1.0}]

    monkeypatch.setitem(api._active_session, "is_active", True)
    monkeypatch.setitem(api._active_session, "db_session_id", 7)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: _Db())
    j = c.get("/api/session/sensor_konumu").json()
    assert j == {"aktif": True, "konum": {"id": 1, "sol_cm": 1.0}, "hazir": beklenen}
