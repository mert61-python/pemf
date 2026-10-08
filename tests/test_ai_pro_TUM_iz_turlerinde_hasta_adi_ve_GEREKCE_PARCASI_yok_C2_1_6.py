# -*- coding: utf-8 -*-
"""C2-1.6 (2-C inceleme, A1) — KÖR KAPI: O-A2.2 kapısı yalnız `ai_proposal_approved/rejected` türlerine ve TAM metne bakar.

Ölçülen (A1 mutantları, `kayit/k2_mutasyon.txt`, O-A2.2 kapısı 4/4 YEŞİL kaldı):
  k2m1 red izine gerekçenin SON 25 karakteri eklenir ("…ri kötü, lokalizasyon hatalı" — klinik bulgu) → YEŞİL
  k2m3 `/propose` mührün `specs`ini (hasta ADI dahil) YENİ bir olay türüyle `session_events`e yazar → YEŞİL
Hafıza dersi "mühüre eklenen alan tüm yazıcılara akar": bekçi YAZICIYA değil TABLOYA bakmalı. Bu kapı öner → red → öner → onay
→ başlat → durdur akışından sonra `session_events`in TÜM satırlarında hasta adını ve gerekçenin her ≥4 harfli sözcüğünü (ham,
`\\u` kaçışlı, ayrıştırılmış) arar. Pozitif kontrol: aynı arama propose YANITINDA adı BULUR. HEAD'de YEŞİL.
"""

from __future__ import annotations

import json
import re
import time

import pytest

AD = "Şükrü Çağlar Ğİz"
GEREKCE = "Şükrü Çağlar Ğİz kilosu yüksek tırnakları uzun"


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = ap.kur(monkeypatch, tmp_path)
    operator_tokens.temizle_hepsi()
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.c.post("/api/ai/pro/stop")
    finally:
        o.air._ai_loop_active = False
        o.geri()


def _taze(air, organ=2):
    air._ai_organ_id = organ
    with air._ai_cache_lock:
        air._ai_organ_cache.update(
            {
                "x_mm": 1.0,
                "y_mm": 2.0,
                "z_mm": 3.0,
                "reliability": 0.9,
                "localized": True,
                "overlay_bgr": None,
                "at": time.time(),
                "organ_id": organ,
                "kedi_var": True,
                "guven_dokumu": None,
                "model": "kedi",
            }
        )


def _parcalar():
    return [AD] + [s for s in re.split(r"\W+", GEREKCE) if len(s) >= 4]


def _bul(metin: str) -> list:
    bulunan = []
    for p in _parcalar():
        if p in metin or json.dumps(p)[1:-1] in metin:
            bulunan.append(p)
    return bulunan


def test_KRITIK_C2_1_6_session_events_TUM_turlerde_hasta_adi_ve_gerekce_PARCASI_yok(o):
    _taze(o.air)
    oneri = {"organ_id": 2, "duration_minutes": 5, "patient_id": "u-c216", "patient_name": AD}
    r = o.c.post("/api/ai/pro/propose", json=oneri)
    assert AD in r.text or json.dumps(AD)[1:-1] in r.text, "pozitif kontrol: arama propose yanıtında adı bulmalı"
    pid = r.json()["proposalId"]
    o.c.post("/api/ai/pro/reject", json={"proposal_id": pid, "operator_email": "h@k.com", "reason": GEREKCE})
    _taze(o.air)
    pid2 = o.c.post("/api/ai/pro/propose", json=oneri).json()["proposalId"]
    o.c.post("/api/ai/pro/approve", json={"proposal_id": pid2, "operator_email": "h@k.com"})
    assert o.c.post("/api/ai/pro/start", json={"proposal_id": pid2}).status_code == 200
    o.c.post("/api/ai/pro/stop")
    with o.db._get_connection() as c:
        satirlar = c.execute("SELECT event_type, COALESCE(payload,'') FROM session_events").fetchall()
    assert any(t == "ai_proposal_rejected" for t, _ in satirlar), "ön koşul: red izi yazılmalı"
    sizinti = []
    for tur, yuk in satirlar:
        b = _bul(yuk)
        try:
            b += [p for p in _parcalar() if p in json.dumps(json.loads(yuk), ensure_ascii=False)]
        except Exception:
            pass
        if b:
            sizinti.append((tur, sorted(set(b))))
    assert sizinti == [], f"hasta adı / red gerekçesi PARÇASI süresiz denetim izinde: {sizinti}"
