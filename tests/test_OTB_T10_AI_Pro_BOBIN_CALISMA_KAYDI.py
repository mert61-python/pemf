# -*- coding: utf-8 -*-
"""OTB T-10 (ODM tezgâhı 19-11): AI Pro seansında bobinler ~2 dk sürüldü ama seans detayı "Bu seansta bobin çalışma kaydı yok" dedi —
bobin koşusu (`session_coil_runs`) yalnız ELLE başlatma uçlarında açılıyordu; AI Pro döngüsü / kare yolu telde sürdüğü bobinler için
kayıt açmıyordu. SÖZLEŞME: AI Pro sürüşünde telde KABUL edilen her bobin için seansta BİR koşu (frekans = mühürdeki, duty %, faz, `stm`)
— her turda yeniden açılmaz; seans kapanışında kapanır (süre yazılır). Düzen `test_ODK_ai_pro_odak_entegrasyon` ile aynı (GERÇEK HC +
geçici tedavi DB'si + gerçek ODAK alanı; EN ALT sahte: ODAK modeli)."""

from __future__ import annotations

import ai_pro_aparati as ap
from test_ODK_ai_pro_odak_entegrasyon import M2, P2, _Hat, _hazirlik, _oner, _Sonuc, o  # noqa: F401  aynı düzenek


def _kosular(o, sid):
    from utils import dongu_disi_yazim

    # OYZ4: kayıt sürüş yolunda DEĞİL — FIFO kayıt işçisinde, beklenmeden açılır; okumadan önce işçi boşaltılır.
    assert dongu_disi_yazim.bosalt(30), "kayıt işçisi 30 sn'de boşalmadı"
    with o.db._get_connection() as c:
        return c.execute(
            "SELECT coil_id, frequency_hz, duty_percent, hw_type, ended_epoch FROM session_coil_runs WHERE session_id = ? ORDER BY coil_id",
            (sid,),
        ).fetchall()


def test_KRITIK_T10_AI_Pro_suruste_BOBIN_CALISMA_KAYDI_acilir_turda_YINELENMEZ_kapanista_KAPANIR(o):
    from servers import ai_approval

    _hazirlik(o)
    pid = _oner(o, doz_mT=0.4).json()["proposalId"]
    ai_approval.approve(pid, "arastirmaci@test.local")
    assert o.c.post("/api/ai/pro/start", json={"proposal_id": pid}).status_code == 200
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    assert sid, "AI Pro seansının DB satırı yok"
    for _ in range(3):  # üç tur: duty / faz her turda yeniden hesaplanır
        _Hat.sonuc = _Sonuc([(P2, M2, 300)])
        j = ap.kare(o).json()
        assert j.get("driven") is True, j
    surulen = sorted(c["id"] for c in j["perCoil"] if c.get("suruldu"))
    k = _kosular(o, sid)
    assert surulen and [r[0] for r in k] == surulen, f"sürülen bobin {surulen} · kayıt {k}"
    assert all(r[1] == 100.0 and r[2] > 0 and r[3] == "stm" and r[4] is None for r in k), k
    assert o.c.post("/api/ai/pro/stop").status_code == 200
    k2 = _kosular(o, sid)
    assert [r[0] for r in k2] == surulen and all(r[4] is not None for r in k2), f"seans kapanınca koşu kapanmadı: {k2}"


def test_T10_kayit_HATASI_surusu_DURDURMAZ(o, monkeypatch):
    from servers import ai_approval, coil_run_tracker

    def patla(*a, **k):
        raise RuntimeError("DB yok")

    monkeypatch.setattr(coil_run_tracker, "_begin_coil_run_govde", patla)  # OYZ4: AI Pro kaydı işçide gövdeyi çağırır
    _hazirlik(o)
    pid = _oner(o, doz_mT=0.4).json()["proposalId"]
    ai_approval.approve(pid, "arastirmaci@test.local")
    assert o.c.post("/api/ai/pro/start", json={"proposal_id": pid}).status_code == 200
    _Hat.sonuc = _Sonuc([(P2, M2, 300)])
    assert ap.kare(o).json().get("driven") is True
