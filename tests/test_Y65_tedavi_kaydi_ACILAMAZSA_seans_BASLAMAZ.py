# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y65 (sahip, 1-F inceleme S-İF1) — seans başlatılırken tedavi kaydının DB satırı AÇILAMAZSA seans BAŞLAMAZ.

ÖLÇÜLEN KUSUR (1-G önce-kırmızı, `f65402b`; önceden var): `/api/session/start` seans satırını "best-effort" açıyordu —
`start_session` istisnası (DB > 5 sn meşgul: seans bitiminde arka planda koşan ertelenmiş KVKK VACUUM'u (Y62) ya da başka
bir DB hatası) yalnız günlüğe yazılıyor, seans `db_session_id=None` ile SÜRÜLÜYORDU → seans satırı, koşu kayıtları ve
sensör/dakika satırları HİÇ oluşmuyordu (kaydedilen ≠ uygulanan; D1.77'nin "kayıtsız tedavi başlamaz" ilkesine aykırı).
AI Pro başlatması da aynıydı (`start_ai_session`: "AI seansi DB satiri acilamadi (tedavi surer)").

SÖZLEŞME (sahip Y65): bobin SÜRÜLMEDEN 503 "Tedavi kaydı açılamadı — seans BAŞLATILMADI; birkaç saniye sonra yeniden
deneyin". Seans aktif KALMAZ (yeniden deneme "Zaten aktif bir seans var" 409'u almaz). AI Pro'da hekimin onayı YANMAZ
(D1.E06 — başlamayan tedavi): DB düzelince aynı onayla başlar. STOP ve ACİL DURDUR etkilenmez (Ö.4-Y8 — karşıt kol).
AI Pro bir manuel seansı DEVRALIRKEN satır açılamazsa SÜREN seans AYNEN kalır (satır devralmadan ÖNCE açılır; 1-G ilk
taslağı sonra açıyordu → manuel seans kapanıyor, bobinleri oturumsuz sürüyordu — ölçüldü). Ölçüt HTTP kodu değil TEL
(gerçek `HardwareController`, kayıtçı kuyruk) ve DB.
"""

from __future__ import annotations

import sqlite3

import ai_pro_aparati as ap
import pytest

Y65_METNI = "Tedavi kaydı açılamadı — seans BAŞLATILMADI; birkaç saniye sonra yeniden deneyin"
_SEANS = {"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1, 2]}


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _db_mesgul(o, monkeypatch):
    """`start_session` SQLite'ın meşgul hatasını verir (busy_timeout 5 sn doldu — ör. VACUUM sürerken). @return orijinal."""
    orj = o.db.start_session

    def _kilitli(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(o.db, "start_session", _kilitli)
    return orj


def _surus(o, once):
    from kayitci_donanim import paket_coz

    return [p for p in o.hc.core._hw_send_queue.paketler[once:] if any(x > 0 for x in paket_coz(p)[0])]


def _satir_sayisi(o):
    with o.db._get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM treatment_sessions").fetchone()[0]


def _kayitsiz_db(o, monkeypatch):
    """Tedavi DB'si hiç yok (`_get_treatment_db()` None) — `_persist_session_start` (None, None) döner."""
    monkeypatch.setattr(o.api, "_get_treatment_db", lambda: None)


@pytest.mark.parametrize("ariza", ["mesgul", "db_yok"])
def test_KRITIK_Y65_satir_ACILAMAZSA_seans_BASLAMAZ_telde_START_yok_seans_AKTIF_kalmaz(o, monkeypatch, ariza):
    (_db_mesgul if ariza == "mesgul" else _kayitsiz_db)(o, monkeypatch)
    once, n = len(o.hc.core._hw_send_queue.paketler), _satir_sayisi(o)
    r = o.c.post("/api/session/start", json=_SEANS)
    assert not _surus(o, once) and not ap.calisan(o), (
        f"{ariza}: tedavi kaydının DB satırı açılamadığı hâlde bobinler SÜRÜLDÜ — kayıtsız tedavi (yanıt {r.status_code} "
        f"{r.text[:160]})"
    )
    assert r.status_code == 503 and r.json().get("detail") == Y65_METNI, f"{r.status_code} {r.text[:200]}"
    assert _satir_sayisi(o) == n
    with o.api._session_lock:
        assert not o.api._active_session.get("is_active"), "başlamayan seans AKTİF kaldı"
        assert not o.api._active_session.get("baslatma_ucusta"), "başlamayan seansın başlatma bayrağı inmedi"


def test_KRITIK_Y65_DB_duzelince_yeniden_deneme_BASLAR_409_almaz(o, monkeypatch):
    orj = _db_mesgul(o, monkeypatch)
    r1 = o.c.post("/api/session/start", json=_SEANS)
    assert r1.status_code == 503, r1.text[:200]
    monkeypatch.setattr(o.db, "start_session", orj)  # DB düzeldi
    once = len(o.hc.core._hw_send_queue.paketler)
    r2 = o.c.post("/api/session/start", json=_SEANS)
    assert r2.status_code == 200 and r2.json().get("status") == "success", (
        f"DB düzelince yeniden deneme başlamadı (ilk denemenin seansı aktif mi kaldı?): {r2.status_code} {r2.text[:200]}"
    )
    assert _surus(o, once), "yeniden denemede bobinler sürülmedi"
    with o.api._session_lock:
        assert o.api._active_session.get("db_session_id"), "başlayan seansın DB satırı yok"
    o.c.post("/api/session/stop")


def test_KRITIK_Y65_AI_Pro_satir_ACILAMAZSA_BASLAMAZ_ve_ONAY_YANMAZ(o, monkeypatch):
    from servers import ai_approval

    orj = _db_mesgul(o, monkeypatch)
    once = len(o.hc.core._hw_send_queue.paketler)
    pid, r = ap.onayli_baslat(o)
    assert not _surus(o, once) and not o.air._ai_loop_active, (
        f"AI Pro: tedavi kaydı açılamadığı hâlde otonom sürüş/döngü BAŞLADI (yanıt {r.status_code} {r.text[:160]})"
    )
    assert r.status_code == 503 and r.json().get("detail") == Y65_METNI, f"{r.status_code} {r.text[:200]}"
    with o.api._session_lock:
        assert not o.api._active_session.get("is_active"), "başlamayan AI Pro seansı AKTİF kaldı"
    ai_approval.dogrula(pid)  # D1.E06: onay YANMADI — fırlatırsa KIRMIZI
    monkeypatch.setattr(o.db, "start_session", orj)  # DB düzeldi
    r2 = o.c.post("/api/ai/pro/start", json={"proposal_id": pid, "client_id": ""})
    assert r2.status_code == 200 and r2.json().get("status") == "success", (
        f"DB düzelince AYNI onayla AI Pro başlamadı: {r2.status_code} {r2.text[:200]}"
    )
    o.c.post("/api/ai/pro/stop")


def test_KRITIK_Y65_AI_Pro_DEVRALMADA_satir_ACILAMAZSA_SUREN_manuel_seans_AYNEN_surer(o, monkeypatch):
    """1-G (Y65 uygulamasının kendi dalı): manuel seans sürerken AI Pro başlatılır ve AI satırı açılamaz → SÜREN seans
    AYNEN kalır: oturum (kimlik + aktif + DB satırı), bobinleri ve DB satırı (`active`, kapatılmaz). 1-G ilk taslağı satırı
    devralmadan SONRA açıyordu: manuel seans kapatılıyor, oturum siliniyor, bobinleri ise keep-alive ile SAHİPSİZ ve
    kayıtsız sürmeye devam ediyordu (`/ai/pro/start` 503 derken)."""
    r0 = o.c.post("/api/session/start", json=_SEANS)
    assert r0.status_code == 200, r0.text[:200]
    with o.api._session_lock:
        once = dict(o.api._active_session)
    assert once.get("is_active") and once.get("db_session_id") and ap.calisan(o) == [1, 2], (
        f"aparat: manuel seans: {once}"
    )
    _db_mesgul(o, monkeypatch)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 503 and r.json().get("detail") == Y65_METNI, f"{r.status_code} {r.text[:200]}"
    with o.api._session_lock:
        sonra = dict(o.api._active_session)
    ayni = {k: (once.get(k), sonra.get(k)) for k in ("is_active", "session_id", "db_session_id", "coil_ids", "mode")}
    assert all(a == b for a, b in ayni.values()), (
        f"AI Pro'nun satırı açılamadı ama SÜREN manuel seans devralındı (önce, sonra): {ayni} — bobinler "
        f"{ap.calisan(o)} oturumsuz sürüyor olabilir"
    )
    assert ap.calisan(o) == [1, 2], f"süren manuel seansın bobinleri değişti: {ap.calisan(o)}"
    with o.db._get_connection() as conn:
        durum = conn.execute(
            "SELECT session_status FROM treatment_sessions WHERE id = ?", (once["db_session_id"],)
        ).fetchone()[0]
    assert durum == "active", f"süren manuel seansın DB satırı kapatıldı ({durum!r}) — devralma yan etkisi"
    o.c.post("/api/session/stop")


def test_KARSIT_Y8_DB_meşgulken_ACIL_DURDUR_ve_seans_DURDURMA_calisir(o, monkeypatch):
    from kayitci_donanim import paket_coz

    r0 = o.c.post("/api/session/start", json=_SEANS)  # DB sağlam: seans başlar, bobin 1-2 sürülür
    assert r0.status_code == 200, r0.text[:200]
    _db_mesgul(o, monkeypatch)
    once = len(o.hc.core._hw_send_queue.paketler)
    r = o.c.post("/api/session/stop")
    assert r.status_code in (200, 409), r.text[:200]
    yeni = o.hc.core._hw_send_queue.paketler[once:]
    assert yeni and all(x == 0 for x in paket_coz(yeni[-1])[0]), "DB meşgulken seans durdurma STOP göndermedi"
    o.hc.update_coil(1, 100, 40, 0, 5, start=True)
    once = len(o.hc.core._hw_send_queue.paketler)
    r = o.c.post("/api/hardware/emergency_stop")
    assert r.status_code == 200
    yeni = o.hc.core._hw_send_queue.paketler[once:]
    assert yeni and all(all(x == 0 for x in paket_coz(p)[0]) for p in yeni), "DB meşgulken ACİL DURDUR STOP göndermedi"


def test_KARSIT_Y65_DB_saglamken_seans_BASLAR_ve_satiri_VAR(o):
    once, n = len(o.hc.core._hw_send_queue.paketler), _satir_sayisi(o)
    r = o.c.post("/api/session/start", json=_SEANS)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert _surus(o, once) and _satir_sayisi(o) == n + 1
    o.c.post("/api/session/stop")
