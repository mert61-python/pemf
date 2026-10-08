# -*- coding: utf-8 -*-
"""C2-2.7 (2-C inceleme A2 · Y114 f2e0482) — AYNI AI kaydını EŞZAMANLI değerlendiren iki hekimden birinin gerekçe / düzeltilmiş
teşhis METNİ kaybolmaz (ne geçmişte ne güncel alanda).

ÖLÇÜLEN (HEAD 1cd770c, `_inceleme/kayit/sonda_k6.txt` [K6b]): ilk değerlendirme (red, "ilk gerekce") sonrası iki iş parçacığı
(ayrı bağlantılar — üretimde `/api/ai/log/review` → `asyncio.to_thread(db.set_ai_review)`) aynı anda düzeltme yazar: iki çağrı da
`True` döner ama **30/30 denemede** ikisinden birinin metni HİÇBİR yerde yok (`gecmis=['ilk gerekce'] guncel='B duzeltmesi'
eksik={'C duzeltmesi'}`). Kök: `set_ai_review` "okuma ve yazma AYNI bağlantı/işlemde" der ama Python `sqlite3` SELECT'ten önce
işlem AÇMAZ (örtük BEGIN yalnız UPDATE'ten önce) → iki okuyucu aynı `review_history`yi okur, ikinci UPDATE birincinin geçmişini
EZER (kayıp güncelleme). Y114'ün amacı tam bu metinlerin kaybolmamasıydı.
DÜZELTME: okuma `BEGIN IMMEDIATE` ile yazma kilidi altında (ikinci yazar birincinin commit'ini bekler, taze geçmişi okur).
GERÇEK: `TreatmentHistoryDB` (geçici), `set_ai_review`, GERÇEK `/api/ai/log/review` + `GET /api/ai/log`; geçmiş SQL ile.
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    try:
        yield type("O", (), {"db": db, "api": api})
    finally:
        db.close_connections()


def _metinler(o, aid):
    with o.db._get_connection() as c:
        c.row_factory = None
        st, note, hist = c.execute(
            "SELECT review_status, review_note, review_history FROM ai_analyses WHERE id = ?", (aid,)
        ).fetchone()
    return [x["note"] for x in json.loads(hist or "[]")], note


def _eszamanli(isler):
    engel = threading.Barrier(len(isler))
    sonuc = []

    def _kos(f):
        engel.wait()
        sonuc.append(f())

    ip = [threading.Thread(target=_kos, args=(f,)) for f in isler]
    for t in ip:
        t.start()
    for t in ip:
        t.join(30)
    return sonuc


def test_KRITIK_eszamanli_iki_degerlendirmede_HICBIR_metin_KAYBOLMAZ(o):
    kayiplar = []
    for i in range(10):
        aid = o.db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="ozet")
        assert o.db.set_ai_review(aid, "rejected", "ilk gerekce", "a@k.com")
        sonuc = _eszamanli(
            [
                lambda: o.db.set_ai_review(aid, "corrected", "B duzeltmesi", "b@k.com"),
                lambda: o.db.set_ai_review(aid, "corrected", "C duzeltmesi", "c@k.com"),
            ]
        )
        gecmis, guncel = _metinler(o, aid)
        eksik = {"ilk gerekce", "B duzeltmesi", "C duzeltmesi"} - set(gecmis + [guncel])
        if eksik or sonuc != [True, True] or len(gecmis) != 2:
            kayiplar.append((i, sonuc, gecmis, guncel, sorted(eksik)))
    assert kayiplar == [], f"eşzamanlı değerlendirmede metin KAYBOLDU (10 denemede {len(kayiplar)}): {kayiplar[:3]}"


def test_KRITIK_GERCEK_uc_eszamanli_iki_degerlendirme_gecmisi_GET_ile_TAM(o):
    c = TestClient(o.api.app, client=("127.0.0.1", 51240))  # Kural 2 (operatörsüz) — beyanla
    kayiplar = []
    for i in range(10):
        aid = o.db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="ozet")
        assert (
            c.post(
                "/api/ai/log/review",
                json={"analysis_id": aid, "status": "rejected", "note": "ilk gerekce", "reviewed_by": "a@k.com"},
            ).status_code
            == 200
        )
        sonuc = _eszamanli(
            [
                lambda: (
                    c.post(
                        "/api/ai/log/review",
                        json={
                            "analysis_id": aid,
                            "status": "corrected",
                            "note": "B duzeltmesi",
                            "reviewed_by": "b@k.com",
                        },
                    ).status_code
                ),
                lambda: (
                    c.post(
                        "/api/ai/log/review",
                        json={
                            "analysis_id": aid,
                            "status": "corrected",
                            "note": "C duzeltmesi",
                            "reviewed_by": "c@k.com",
                        },
                    ).status_code
                ),
            ]
        )
        kayit = next(k for k in c.get("/api/ai/log?limit=50").json()["data"] if k["id"] == aid)
        metinler = sorted([x["note"] for x in kayit["review_history"]] + [kayit["review_note"]])
        if sonuc != [200, 200] or metinler != ["B duzeltmesi", "C duzeltmesi", "ilk gerekce"]:
            kayiplar.append((i, sonuc, metinler))
    assert kayiplar == [], f"GERÇEK uçta eşzamanlı değerlendirme metni KAYBETTİ ({len(kayiplar)}/10): {kayiplar[:3]}"


def test_KARSIT_sirali_degerlendirmeler_eskiden_yeniye_ve_olmayan_kayit_False(o):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="ozet")
    for st, n, k in (("rejected", "g1", "a"), ("corrected", "g2", "b"), ("approved", "", "c")):
        assert o.db.set_ai_review(aid, st, n, k)
    gecmis, guncel = _metinler(o, aid)
    assert (gecmis, guncel) == (["g1", "g2"], "")
    assert o.db.set_ai_review(987654, "approved", "", "x") is False
