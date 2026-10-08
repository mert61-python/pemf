# -*- coding: utf-8 -*-
"""O-A2.2 (2-B incelemesi) — AI Pro öneri reddinin GEREKÇE METNİ `session_events` yüküne yazılmaz (PII).

KUSUR: `_kaydet_onay_izi` red izine `reason` alanını METİN olarak yazıyordu. Hekimin serbest gerekçesi hasta/sahip adı, klinik
bulgu gibi kişisel veri taşıyabilir; `session_events` append-only denetim izidir (saklama: kritik olaylar süresiz — A-07) ve
dışa aktarma/destek paketlerinde dolaşır. D2.19'un AI değerlendirmesi kuralıyla AYNI ilke: iz METİNSİZ, yalnız varlığı
(`gerekce_var`). (2-B incelemesi ADAY İG-6.27 ölçümünde red gerekçesini tam da bu yükten okumuştu.)
Kapı GERÇEK uçları koşar (`/ai/pro/reject`, `/ai/pro/approve`); iz SQL ile, ham yük METNİNDE ve AYRIŞTIRILMIŞ değerlerde
aranır (hafıza: sızıntı denetimi `json.dumps` kaçışında kör — her iki biçim de denenir).
"""

from __future__ import annotations

import json

import pytest

GEREKCE = "Ayşe Yılmaz'ın kedisi Pamuk — böbrek değerleri kötü, lokalizasyon hatalı"


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap

    o = ap.kur(monkeypatch, tmp_path)
    try:
        yield o
    finally:
        o.geri()


def _oneri(o) -> str:
    from servers import ai_approval

    return ai_approval.create("ai_pro", {"organ_id": 2, "duration_minutes": 5, "model": "kedi"})["id"]


def _izler(o, olay: str) -> list:
    with o.db._get_connection() as c:
        return [r[0] for r in c.execute("SELECT payload FROM session_events WHERE event_type = ?", (olay,)).fetchall()]


def _metin_var(ham: str, metin: str) -> bool:
    if metin in ham or json.dumps(metin)[1:-1] in ham:
        return True
    try:
        return metin in json.dumps(json.loads(ham), ensure_ascii=False)
    except Exception:
        return False


def test_KRITIK_red_gerekcesi_METNI_iz_yukunde_YOK_varligi_VAR(o):
    pid = _oneri(o)
    r = o.c.post(
        "/api/ai/pro/reject", json={"proposal_id": pid, "operator_email": "hekim@test.local", "reason": GEREKCE}
    )
    assert r.status_code == 200, r.text[:200]
    izler = _izler(o, "ai_proposal_rejected")
    assert len(izler) == 1, f"ön koşul: red izi yazılmalı ({izler})"
    assert not _metin_var(izler[0], GEREKCE) and not _metin_var(izler[0], "Ayşe Yılmaz"), (
        "red gerekçesi METNİ denetim izinde"
    )
    yuk = json.loads(izler[0])
    assert yuk.get("gerekce_var") is True and yuk.get("proposal_id") == pid


def test_KARSIT_reddedilen_oneri_BASLATILAMAZ_onay_izi_YAZILIR(o):
    """Davranış değişmez: red kararı geçerli (reddedilen öneri başlatılamaz); onay izi yine yazılır."""
    pid = _oneri(o)
    o.c.post("/api/ai/pro/reject", json={"proposal_id": pid, "operator_email": "hekim@test.local", "reason": GEREKCE})
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code >= 400, "reddedilen öneri başlatıldı"
    pid2 = _oneri(o)
    assert (
        o.c.post("/api/ai/pro/approve", json={"proposal_id": pid2, "operator_email": "hekim@test.local"}).status_code
        == 200
    )
    onay = [json.loads(p) for p in _izler(o, "ai_proposal_approved")]
    assert [y.get("proposal_id") for y in onay] == [pid2]


def _taze_lokalizasyon(air, organ: int = 2):
    import time

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


HASTA_ADI = "Pamuk Yılmaz"
HASTA_KIMLIGI = "pamuk-kimlik-oa22-01"


def _gercek_oneri(o) -> str:
    """GERÇEK `/api/ai/pro/propose` — D2.E15'ten beri hasta (kimlik + ad) öneri mührüne (`specs`) yazılır."""
    _taze_lokalizasyon(o.air)
    r = o.c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 2, "duration_minutes": 5, "patient_id": HASTA_KIMLIGI, "patient_name": HASTA_ADI},
    )
    assert r.status_code == 200, r.text[:300]
    assert r.json()["specs"].get("patient_name") == HASTA_ADI, "ön koşul: hasta adı öneri mühründe (pencere gösterir)"
    return r.json()["proposalId"]


@pytest.mark.parametrize("olay", ["ai_proposal_approved", "ai_proposal_rejected"])
def test_KRITIK_E15_onay_ve_red_izinde_hasta_ADI_YOK_opak_kimlik_VAR(o, olay):
    """D2.E15 hastayı öneri mührüne koydu; iz `specs`i AYNEN yazdığı için hasta ADI süresiz denetim izine sızıyordu (2-C
    içinde ölçüldü, yayınlanmadı). İz yalnız opak kimliği taşır — hangi hastaya onaylatıldığı yine izlenebilir."""
    pid = _gercek_oneri(o)
    if olay == "ai_proposal_approved":
        r = o.c.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": "hekim@test.local"})
    else:
        r = o.c.post(
            "/api/ai/pro/reject", json={"proposal_id": pid, "operator_email": "hekim@test.local", "reason": ""}
        )
    assert r.status_code == 200, r.text[:200]
    izler = _izler(o, olay)
    assert len(izler) == 1, f"ön koşul: iz yazılmalı ({izler})"
    assert not _metin_var(izler[0], HASTA_ADI) and not _metin_var(izler[0], "Pamuk"), "hasta ADI denetim izinde"
    yuk = json.loads(izler[0])
    assert (yuk.get("specs") or {}).get("patient_id") == HASTA_KIMLIGI, "opak hasta kimliği izde olmalı"
    assert (yuk.get("specs") or {}).get("organ_id") == 2, "doz parametreleri izde kalmalı (onay izinin amacı)"
