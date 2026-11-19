# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-E açık #9 · İNCELEME-2 §10 #2 devamı — `/session/start`ta başlatma bayrağı kurulduktan SONRA, bobin sürüşünden ÖNCEKİ
bölgede (denetim izi, sahip e-postası, DB satırı, artık koşular, ESP döngüsü) beklenmeyen istisna seansı TUTARLI kapatır.

ÖLÇÜLEN KUSUR (`ee4b170` yalnız SÜRÜŞ istisnasını kapsadı): bu bölgede kaçan istisnada uç 500'le çıkıyor, `_active_session`
`is_active` + `baslatma_ucusta` KALIYORDU — sonraki seans 409 alır, arayüz hayalet seans gösterir, DB satırı (açıldıysa)
`active` kalır ve bir sonraki açılışta "Elektrik Kesintisi" mühürlenir.

GERÇEK: `/api/session/start`, `/api/session/stop`, `HardwareController` (kayıtçı kuyruk), `coil_run_tracker`, tmp
`TreatmentHistoryDB`. Sahte: yalnız istisna enjeksiyonu — (a) DB satırından ÖNCE (`_lookup_owner_email`), (b) DB satırından
SONRA (ESP frekans normalizasyonu, `utils.stm32_protocol_limits`).
"""

from __future__ import annotations

import pytest
from topoloji import TUM_STM

_B1 = sorted(TUM_STM)[0]


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    import database.treatment_history_db as thdb
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import coil_run_tracker

    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setattr(thdb, "get_treatment_db", lambda *_a, **_k: db)
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session.clear()
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        monkeypatch.setattr(api.state, "core", hc.core)
        c = TestClient(api.app, raise_server_exceptions=False)
        try:
            yield api, hc, db, c, monkeypatch
        finally:
            c.post("/api/session/stop")
            hc.stop_all_coils()
            with api._session_lock:
                api._active_session.clear()
                api._active_session.update(eski)


def _baslat(c):
    return c.post(
        "/api/session/start",
        json={
            "mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5,
            "coil_ids": [_B1], "patient_name": "Pamuk", "patient_id": "p-1",
        },
    )  # fmt: skip


def _durumlar(db) -> list[str]:
    with db._get_connection() as conn:
        return [r[0] for r in conn.execute("SELECT session_status FROM treatment_sessions ORDER BY id").fetchall()]


def _surus(hc, once):
    from kayitci_donanim import paket_coz

    return [p for p in hc.core._hw_send_queue.paketler[once:] if any(x > 0 for x in paket_coz(p)[0])]


def _patlat(mp, api, nokta):
    if nokta == "db_oncesi":

        def _sahip(*_a, **_k):
            raise RuntimeError("acik-9: beklenmeyen hata (DB satirindan ONCE)")

        mp.setattr(api, "_lookup_owner_email", _sahip)
    else:
        import utils.stm32_protocol_limits as lim

        def _normallestir(*_a, **_k):
            raise RuntimeError("acik-9: beklenmeyen hata (DB satirindan SONRA, surusten ONCE)")

        mp.setattr(lim, "normalize_esp_frequency_hz", _normallestir)


@pytest.mark.parametrize("nokta", ["db_oncesi", "db_sonrasi"])
def test_KRITIK_surus_ONCESI_istisna_seansi_TUTARLI_kapatir_bayrak_iner_satir_cancelled(ortam, nokta):
    api, hc, db, c, mp = ortam
    _patlat(mp, api, nokta)
    once = len(hc.core._hw_send_queue.paketler)
    r = _baslat(c)
    with api._session_lock:
        aktif = bool(api._active_session.get("is_active"))
        ucusta = bool(api._active_session.get("baslatma_ucusta"))
    assert not aktif and not ucusta, (
        f"sürüş ÖNCESİ istisnadan sonra seans YARIM kaldı (is_active={aktif}, baslatma_ucusta={ucusta}; yanıt "
        f"{r.status_code}) — sonraki seans 409, arayüz hayalet seans gösterir"
    )
    assert r.status_code == 503 and "BAŞLATILMADI" in r.json().get("detail", ""), f"{r.status_code} {r.text[:200]}"
    assert not _surus(hc, once), "istisnaya rağmen bobin SÜRÜLDÜ"
    durumlar = _durumlar(db)
    if nokta == "db_sonrasi":
        assert durumlar and durumlar[-1] == "cancelled", f"açılmış DB satırı 'İptal Edildi' kapanmadı: {durumlar}"
    else:
        assert "active" not in durumlar, f"DB'de açık satır kaldı: {durumlar}"


def test_KARSIT_istisnadan_sonra_SONRAKI_seans_normal_baslar(ortam):
    api, hc, db, c, mp = ortam
    with mp.context() as m:
        _patlat(m, api, "db_sonrasi")
        _baslat(c)
    r = _baslat(c)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert c.post("/api/session/stop").status_code == 200
    assert _durumlar(db)[-1] == "stopped", _durumlar(
        db
    )  # Y306: süre dolmadan elle Durdur = "Durduruldu" (stopped) — iptal / donanım reddi DEĞİL


def test_KRITIK_istisna_yardimcisi_BASKA_seansin_ucustaki_baslatma_bayragini_INDIRMEZ(ortam):
    """1-F inceleme (#9 çürütme sorusu): A'nın sürüş-öncesi istisnası, A durdurulup B'nin başlatması UÇUŞTAYKEN
    yardımcıya ulaşırsa yalnız A'nın bayrağı iner. B'nin `baslatma_ucusta`'sı inerse B'nin bobinine gelen tekil STOP nesli
    artırmaz ve B o bobini STOP'tan SONRA enerjiler (1-C i1-F5 sınıfı; Ö.4-Y8). GERÇEK uçlar; B kendi
    `_lookup_owner_email`'inde (uçuşta, bayrak kurulu) bekletilir."""
    import threading

    api, hc, db, c, mp = ortam
    b_ucusta, b_birak = threading.Event(), threading.Event()
    b_yanit: dict = {}

    def _b_baslat():
        b_yanit["r"] = c.post(
            "/api/session/start",
            json={
                "mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5,
                "coil_ids": [_B1], "patient_name": "Boncuk", "patient_id": "p-B",
            },
        )  # fmt: skip

    def _sahip(hasta_id, *_a, **_k):
        if hasta_id == "p-B":
            b_ucusta.set()
            b_birak.wait(20)
            return None
        # A: önce A durdurulur, B başlar ve UÇUŞTA bekler; sonra A'nın beklenmeyen istisnası.
        assert c.post("/api/session/stop").status_code == 200, "aparat: A durdurulamadı"
        threading.Thread(target=_b_baslat, daemon=True).start()
        assert b_ucusta.wait(20), "aparat: B'nin başlatması uçuşa girmedi"
        raise RuntimeError("acik-9: A'nin beklenmeyen istisnasi (B ucusta)")

    mp.setattr(api, "_lookup_owner_email", _sahip)
    try:
        r = _baslat(c)
        assert r.status_code == 503, f"aparat: A'nın istisnası 503 vermedi: {r.status_code} {r.text[:200]}"
        with api._session_lock:
            b_aktif = bool(api._active_session.get("is_active"))
            b_ucusta_bayragi = bool(api._active_session.get("baslatma_ucusta"))
            b_hasta = api._active_session.get("patient_name")
        assert b_aktif and b_hasta == "Boncuk", f"aparat: B uçuşta değil ({b_aktif}, {b_hasta})"
        assert b_ucusta_bayragi, (
            "A'nın istisna kapanışı B'nin UÇUŞTAKİ başlatma bayrağını İNDİRDİ — B'nin bobinine gelen STOP artık "
            "başlatmayı iptal etmez (bobin STOP'tan sonra enerjilenir)"
        )
    finally:
        b_birak.set()
        for _ in range(200):
            if "r" in b_yanit:
                break
            import time

            time.sleep(0.05)
