# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP-22 (istem 48 · D ekran görüntüsü 14-11): onay penceresi hedefi HAM VERİ etiketiyle yazıyordu ("Kuyu C2") — EN arayüzde başlık,
"Kuyu" satırı ve mühür notu Türkçe kalıyordu (hedef listesi `etiketGosterim` alıyor, öneri almıyordu).
Sözleşme: `/ai/pro/propose` yanıtı YALNIZ-EK `hedefGosterim` taşır (İSTEK dilinde); mühürdeki `target_label` VERİ kalır (Türkçe;
`/start` ve seans kaydı onu okur). Gösterim yöntemi olmayan sağlayıcıda (kedi) alan boş → istemci ham etikete düşer."""

import time

import pytest
from fastapi.testclient import TestClient

C2 = {"id": 7, "label": "Kuyu C2", "x": 10.0, "y": -150.0, "z": 20.0, "reliability": 0.95, "pxn": [0.3, 0.5]}


@pytest.fixture()
def c(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.setattr(hedef, "duzlem_surus_engeli", lambda _s: None)
    monkeypatch.setattr(
        hedef,
        "odak_plani",
        lambda *a, **k: {
            "kip": "KUYUCUK",
            "doz_mT": 0.6,
            "tavan_mT": 1.2,
            "duty": [0.2] * 7,
            "faz": [0.0] * 7,
            "frek_hz": 100.0,
        },
    )
    snap = dict(air._ai_organ_cache)
    air._ai_organ_cache.update(
        {
            "localized": True,
            "organ_id": 0,
            "model": "petri",
            "at": time.time(),
            "x_mm": C2["x"],
            "y_mm": C2["y"],
            "z_mm": C2["z"],
            "reliability": 0.95,
            "kosulsuz": False,
            "targets": [C2],
            "secili_id": 7,
            "target_label": "Kuyu C2",
        }
    )
    yield TestClient(apis.app)
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap)


def _oner(c, dil):
    return c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 0, "model": "petri", "duration_minutes": 5},
        headers={"X-PEMF-Dil": dil},
    )


def test_KRITIK_EN_istekte_hedef_adi_INGILIZCE_muhur_VERISI_turkce_kalir(c):
    r = _oner(c, "en")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["hedefGosterim"] == "Well C2"
    assert j["specs"]["target_label"] == "Kuyu C2"  # mühür / seans kaydı VERİSİ değişmez


def test_TR_istekte_hedef_adi_bayt_bayt_ayni(c):
    j = _oner(c, "tr").json()
    assert j["hedefGosterim"] == "Kuyu C2" == j["specs"]["target_label"]
