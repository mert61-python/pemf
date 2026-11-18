# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODD B-4 (ODK-B keşfi 18-11, kum 21_gecmis / 27_raporlar, sahip 20.png) — AI Pro seans KAYDI.

ÖLÇÜLEN: AI Pro satırında `target_condition` / `frequency_hz` / `intensity_mt` NULL → geçmiş kartı "Hedef -", "0 Hz", "Yoğunluk —";
elle durdurulan seans `completed` → Raporlar "Tamamlanma %100", "Dur./Hata 0" (planlanan süre verilmemişken tamamlanmış).
SÖZLEŞME: satır MÜHÜRDEN hedefi (etiket / hedef adı), sürüş frekansını ve ODAK dozunu (mT) taşır; operatörün elle durdurması
`stopped` (KPI "durdurulan"da sayılır, tamamlanan DEĞİL); süre dolumu `completed` AYNEN. Düzen `test_ai_pro_seans_HASTAYA_…` ile aynı
(GERÇEK onay akışı + GERÇEK HC + geçici tedavi DB'si; ODAK tahmincisi sahte).
"""

from __future__ import annotations

import pytest
from kd_kalibrasyon_yardimci import odak_tahminci  # noqa: F401  ODK5: kedi önerisi de ODAK'tan
from test_ai_pro_seans_HASTAYA_baglanir_ve_KAPANIR_E15_E07 import _taze_lokalizasyon, o  # noqa: F401  aynı düzenek


def _baslat(o, **oneri_ek):
    _taze_lokalizasyon(o.air)
    r = o.c.post("/api/ai/pro/propose", json={"organ_id": 2, "duration_minutes": 5, **oneri_ek})
    assert r.status_code == 200, r.text[:300]
    oneri = r.json()
    pid = oneri["proposalId"]
    assert (
        o.c.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": "hekim@test.local"}).status_code
        == 200
    )
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 200, r.text[:300]
    with o.api._session_lock:
        return o.api._active_session.get("db_session_id"), oneri["specs"]


def _satir(o, sid):
    with o.db._get_connection() as c:
        r = c.execute(
            "SELECT target_condition, frequency_hz, intensity_mt, session_status FROM treatment_sessions WHERE id = ?",
            (sid,),
        ).fetchone()
    return dict(zip(("hedef", "frek", "doz", "durum"), tuple(r)))


def test_KRITIK_B4_AI_Pro_satiri_HEDEF_FREKANS_ve_ODAK_DOZU_tasir(o):
    from servers import ai_pro_hedef

    sid, specs = _baslat(o, patient_name="Boncuk", frek_hz=76)
    s = _satir(o, sid)
    beklenen_hedef = specs.get("target_label") or ai_pro_hedef.saglayici_al("kedi").hedef_adi(2)
    assert s["hedef"] and s["hedef"] == beklenen_hedef, f"satırda hedef yok / yanlış: {s} (mühür {beklenen_hedef!r})"
    assert s["frek"] == pytest.approx(76.0), f"satırda sürüş frekansı yok: {s}"
    assert specs["odak"]["doz_mT"] > 0 and s["doz"] == pytest.approx(specs["odak"]["doz_mT"]), (
        f"satırda ODAK dozu yok: {s}"
    )


def test_KRITIK_B4_ELLE_durdurma_STOPPED_KPI_tamamlanan_SAYMAZ_durdurulan_SAYAR(o):
    from servers import system_router

    sid, _ = _baslat(o, patient_name="Boncuk")
    once = system_router.get_kpi_summary()
    assert o.c.post("/api/ai/pro/stop").status_code == 200
    assert _satir(o, sid)["durum"] == "stopped"
    sonra = system_router.get_kpi_summary()
    assert sonra["completedSessions"] == once["completedSessions"], (once, sonra)
    assert sonra["stoppedSessions"] == once["stoppedSessions"] + 1, (once, sonra)


# KARŞIT (süre dolumu `completed`, döngü kesintisi `interrupted`, acil durdurma AYNEN): test_ai_pro_SURE_DOLUMU_kesinti_SAYILMAZ_C2_1_1.py ·
# test_ai_pro_seans_HASTAYA_baglanir_ve_KAPANIR_E15_E07.py (KESINTIYE_UGRADI / ACIL_DURDUR muhru) — bu dosya onlari degistirmez.
