# -*- coding: utf-8 -*-
"""D2-4.1 (2-D incelemesi, orkestratör · A-07 · B2-1.5 ilkesi · Ö.4-Y8 karşıt kollu) — süren tedavi seansında geri yükleme (REPLACE_ALL)
seansın kaydını SİLMEZ; geri yükleme sürerken yeni seans BAŞLATILMAZ.

ÖLÇÜLEN KUSUR (HEAD `a76ee0d`, orkestratör sondası O2): bobin 1 sürerken (elle seans) cihazın KENDİSİNDEN dolu cihaza REPLACE_ALL → 200;
süren seansın `treatment_sessions` satırı ve bobin koşusu SİLİNDİ, seans sürdü (`is_active` True, bobin çalışıyor); durdurma ya da ACİL
DURDUR sonrası o seansın HİÇBİR kaydı yok — uygulanan doz ve ACİL DURDUR olayı kayıtsız (A-07: kritik olaylar süresiz). Silme uçları aynı
durumda 409 veriyor (B2-1.5: `history_router._suren_seans_reddi`). Simetriği: geri yükleme kilidi tutulurken (paket çözülürken, hedef
okunurken) başlatılan seans, içe aktarmanın silme adımında aynı biçimde gider.
DÜZELTME: `_ice_aktar` süren seans varken (elle ya da AI Pro) 409 + iz `reddedildi/seans_suruyor`, hiçbir şey silinmez; `/api/session/start`
ve `start_ai_session` geri yükleme kilidi tutulurken başlatmaz (elle 409; AI Pro Y65 yolu: 503, onay YANMAZ). ACİL DURDUR / STOP'a
dokunulmaz (karşıt kol). Gerçek: uçlar, `TreatmentHistoryDB`, `PatientDatabase`, `HardwareController` (`gercek_hc`, kayıtçı kuyruk),
kilit `api._VERI_TASIMA_KILIDI`'nin kendisi.
"""

from __future__ import annotations

import ai_pro_aparati as ap
import pytest
import veri_tasima_aparati as vta

_SEANS = {"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1, 2]}
PAROLA = "D2-4-1-parola"
YEREL = ("127.0.0.1", 50771)


@pytest.fixture
def o(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            # kaynak cihaz A: yedek paketi
            tdb_a, hdb_a = vta.cihaz_kur(monkeypatch, tmp_path / "A")
            vta.doldur(tdb_a, hdb_a, ["YedekHasta1", "YedekHasta2"], seans_basi=2)
            vta.uclari_bagla(monkeypatch, tdb_a, hdb_a)
            ns.paket = vta.disa_aktar(ns.api.app, parola=PAROLA)["data_b64"]
            # hedef cihaz: aparatın tedavi DB'si (seans uçlarıyla AYNI) + hasta DB'si; içinde eski kayıt var (DOLU)
            _, ns.hdb = vta.cihaz_kur(monkeypatch, tmp_path / "B")
            vta.uclari_bagla(monkeypatch, ns.db, ns.hdb)
            vta.doldur(ns.db, ns.hdb, ["EskiHasta"], seans_basi=1)
            ns.yerel = TestClient(ns.api.app, client=YEREL)
            ns.dbler = (tdb_a, hdb_a)
            yield ns
            ns.c.post("/api/session/stop")
            if ns.api._VERI_TASIMA_KILIDI.locked():
                ns.api._VERI_TASIMA_KILIDI.release()
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


def _geri_yukle(o):
    return o.yerel.post("/api/data/import", json={"passphrase": PAROLA, "blob_b64": o.paket, "confirm": "REPLACE_ALL"})


def _seans_kaydi(o, sid):
    with o.db._get_connection() as c:
        satir = c.execute("SELECT id FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()
        kosu = c.execute("SELECT count(*) FROM session_coil_runs WHERE session_id = ?", (sid,)).fetchone()[0]
        toplam = c.execute("SELECT count(*) FROM treatment_sessions").fetchone()[0]
    return satir is not None, kosu, toplam


def _surus(o, once):
    from kayitci_donanim import paket_coz

    return [p for p in o.hc.core._hw_send_queue.paketler[once:] if any(x > 0 for x in paket_coz(p)[0])]


def test_KRITIK_D2_4_1_elle_seans_SURERKEN_REPLACE_ALL_409_seans_kaydi_ve_kosusu_SILINMEZ(o):
    r = o.c.post("/api/session/start", json=_SEANS)
    assert r.status_code == 200, r.text[:200]
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    var, kosu, toplam = _seans_kaydi(o, sid)
    assert var and kosu >= 1, "aparat: süren seansın satırı/koşusu yok"
    r = _geri_yukle(o)
    var2, kosu2, toplam2 = _seans_kaydi(o, sid)
    assert var2 and kosu2 == kosu, (
        f"süren seansın kaydı geri yüklemede SİLİNDİ (satır {var2}, koşu {kosu}→{kosu2}) — uygulanan doz ve ACİL DURDUR olayı "
        f"kayıtsız kalır (A-07); yanıt {r.status_code} {r.text[:200]}"
    )
    assert r.status_code == 409, f"seans sürerken geri yükleme reddedilmedi: {r.status_code} {r.text[:200]}"
    assert "seans" in r.json().get("detail", "").lower(), r.text[:200]
    assert toplam2 == toplam, "reddedilen geri yükleme kayıtları değiştirdi"
    # seans bitince geri yükleme bugünkü gibi çalışır (karşıt)
    assert o.c.post("/api/session/stop").status_code == 200
    r = _geri_yukle(o)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]


def test_KRITIK_D2_4_1_AI_Pro_SURERKEN_REPLACE_ALL_409(o):
    pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200, f"aparat: AI Pro başlamadı {r.status_code} {r.text[:200]}"
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    assert sid, "aparat: AI Pro seansının DB satırı yok"
    r = _geri_yukle(o)
    var, _, _ = _seans_kaydi(o, sid)
    assert var, f"süren AI Pro seansının kaydı geri yüklemede SİLİNDİ (yanıt {r.status_code} {r.text[:160]})"
    assert r.status_code == 409, f"AI Pro sürerken geri yükleme reddedilmedi: {r.status_code} {r.text[:200]}"
    o.c.post("/api/ai/pro/stop")


def test_KRITIK_D2_4_1_geri_yukleme_SURERKEN_elle_seans_BASLATILMAZ(o):
    assert o.api._VERI_TASIMA_KILIDI.acquire(blocking=False), "aparat: kilit boş değil"
    try:
        once, (_, _, toplam) = len(o.hc.core._hw_send_queue.paketler), _seans_kaydi(o, -1)
        r = o.c.post("/api/session/start", json=_SEANS)
        assert not _surus(o, once) and not ap.calisan(o), (
            f"geri yükleme sürerken seans BAŞLADI — satırı içe aktarmanın silme adımında gider (yanıt {r.status_code})"
        )
        assert r.status_code == 409 and "geri yükleme" in r.json().get("detail", "").lower(), r.text[:200]
        assert _seans_kaydi(o, -1)[2] == toplam
        with o.api._session_lock:
            assert not o.api._active_session.get("is_active"), "başlamayan seans AKTİF kaldı"
    finally:
        o.api._VERI_TASIMA_KILIDI.release()
    r = o.c.post("/api/session/start", json=_SEANS)
    assert r.status_code == 200, f"geri yükleme bitince seans başlamadı: {r.status_code} {r.text[:200]}"


def test_KRITIK_D2_4_1_geri_yukleme_SURERKEN_AI_Pro_BASLATILMAZ_onay_YANMAZ(o):
    from servers import ai_approval

    assert o.api._VERI_TASIMA_KILIDI.acquire(blocking=False), "aparat: kilit boş değil"
    try:
        once = len(o.hc.core._hw_send_queue.paketler)
        pid, r = ap.onayli_baslat(o)
        assert not _surus(o, once) and not o.air._ai_loop_active, (
            f"geri yükleme sürerken AI Pro BAŞLADI (yanıt {r.status_code} {r.text[:160]})"
        )
        assert r.status_code in (409, 503) and "geri yükleme" in r.json().get("detail", "").lower(), r.text[:200]
        ai_approval.dogrula(pid)  # D1.E06: başlamayan tedavi onayı YAKMAZ — fırlatırsa KIRMIZI
    finally:
        o.api._VERI_TASIMA_KILIDI.release()
    r2 = o.c.post("/api/ai/pro/start", json={"proposal_id": pid, "client_id": ""})
    assert r2.status_code == 200, f"geri yükleme bitince AYNI onayla AI Pro başlamadı: {r2.status_code} {r2.text[:200]}"
    o.c.post("/api/ai/pro/stop")


def test_KARSIT_Y8_geri_yukleme_SURERKEN_ACIL_DURDUR_ve_STOP_calisir(o):
    r = o.c.post("/api/session/start", json=_SEANS)
    assert r.status_code == 200, r.text[:200]
    assert o.api._VERI_TASIMA_KILIDI.acquire(blocking=False)
    try:
        cagri = o.hc.stop_all_cagri
        r = o.c.post("/api/hardware/emergency_stop")
        assert r.status_code == 200 and o.hc.stop_all_cagri > cagri, f"ACİL DURDUR kilitte çalışmadı: {r.text[:200]}"
        assert o.c.post("/api/session/stop").status_code == 200
    finally:
        o.api._VERI_TASIMA_KILIDI.release()


@pytest.fixture(autouse=True)
def _kapat(o):
    yield
    vta.kapat(*o.dbler, o.hdb)
