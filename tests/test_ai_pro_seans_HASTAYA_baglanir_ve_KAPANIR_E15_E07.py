# -*- coding: utf-8 -*-
"""D2.E15 (İG-5.14) + D2.E07 (YA-1) — AI Pro seansının DB satırı HASTAYA bağlanır ve durdurulunca GERÇEK süreyle KAPANIR.

ÖLÇÜLEN KUSURLAR (ADAY-DOĞRULAMA-D2, ikisi de iki ölçücüyle):
  · İG-5.14: arayüz `/ai/pro/start`'a `patient_name` gönderiyor ama `AiProStartPayload`'da alan yok (pydantic atar) →
    AI Pro satırı `patient_name/patient_id` NULL, `/api/history` adsız, hastanın Seans Geçmişi'nde tedavi YOK.
  · YA-1: `/ai/pro/stop` ve döngünün kendi bitişi `_finalize_session_db` çağırmıyordu → satır `active` kalıyor; yeniden
    açılışta kurtarma onu "Elektrik Kesintisi" (`ABORTED_DUE_TO_POWER`), `end_time = start_time`, 0 dk mühürlüyordu →
    verilmiş bir AI Pro tedavisi geçmişte "elektrik kesintisiyle iptal, 0 dk".
DÜZELTME İLKESİ: hasta ÖNERİ MÜHRÜNE yazılır (organ/süre/model ile aynı ilke — "A için onaylat, B'ye başlat" imkânsız);
`/start` mühürden okuyup elle seans yoluyla AYNI bağı kurar. Kapanış STOP'tan SONRA (Ö.4-Y8): operatör durdurması
"completed", döngünün kendi kesintisi (hedef kaybı / doz hatası / kamera) "interrupted". ACİL DURDUR'un "EMERGENCY_STOPPED"
mührü ezilmez. Tünelden AI Pro erişimi (sahip kararı D-2.2) DEĞİŞMEZ. Satırlar SQL ile okunur.
"""

from __future__ import annotations

import numpy as np
import pytest

U1 = "boncuk-kimlik-e15-01"
U2 = "baska-kimlik-e15-02"
TUNEL = {"cf-ray": "8a1b2c3d4e5f-IST", "cf-connecting-ip": "203.0.113.9"}


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = ap.kur(monkeypatch, tmp_path)
    o.kok = tmp_path / "gecmis"
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


def _oner_onayla_baslat(o, oneri_ek: dict, baslat_ek: dict | None = None, baslik=None):
    _taze_lokalizasyon(o.air)
    r = o.c.post("/api/ai/pro/propose", json={"organ_id": 2, "duration_minutes": 5, **oneri_ek})
    assert r.status_code == 200, r.text[:300]
    pid = r.json()["proposalId"]
    r = o.c.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": "hekim@test.local"}, headers=baslik)
    assert r.status_code == 200, r.text[:300]
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid, **(baslat_ek or {})}, headers=baslik)
    assert r.status_code == 200, r.text[:300]
    with o.api._session_lock:
        return o.api._active_session.get("db_session_id")


def _seans(o, sid):
    with o.db._get_connection() as c:
        r = c.execute(
            "SELECT s.session_status, s.end_time, s.patient_name, s.patient_id, p.patient_uuid, s.started_epoch, s.ended_epoch "
            "FROM treatment_sessions s LEFT JOIN patients p ON p.id = s.patient_id WHERE s.id = ?",
            (sid,),
        ).fetchone()
    return dict(zip(("durum", "bitis", "ad", "hasta_satiri", "hasta_kimligi", "basla_epoch", "bitis_epoch"), tuple(r)))


# ── D2.E15 · hasta bağı ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_E15_onerideki_hasta_seans_satirina_ve_gecmise_BAGLANIR(o):
    sid = _oner_onayla_baslat(o, {"patient_id": U1, "patient_name": "Boncuk"})
    s = _seans(o, sid)
    assert (s["ad"], s["hasta_kimligi"]) == ("Boncuk", U1), f"AI Pro satırı hastaya bağlanmadı: {s}"
    o.c.post("/api/ai/pro/stop")
    from servers.history_router import get_db

    o.api.app.dependency_overrides[get_db] = lambda: o.db  # geçmiş ucu aynı (aparat) tedavi DB'sini okusun
    try:
        yanit = o.c.get("/api/history/?limit=10").json()
    finally:
        o.api.app.dependency_overrides.pop(get_db, None)
    gecmis = [h for h in yanit if h.get("id") == sid]
    assert [h.get("patient_name") for h in gecmis] == ["Boncuk"], f"/api/history hastayı göstermiyor: {gecmis}"


def test_KRITIK_E15_hasta_MUHURDEN_okunur_baslatma_govdesi_yok_sayilir(o):
    """'A için onaylat, B'ye başlat' imkânsız: `/start` gövdesindeki farklı hasta mührü EZMEZ."""
    sid = _oner_onayla_baslat(
        o, {"patient_id": U1, "patient_name": "Boncuk"}, {"patient_id": U2, "patient_name": "Başka"}
    )
    s = _seans(o, sid)
    assert (s["ad"], s["hasta_kimligi"]) == ("Boncuk", U1), f"başlatma gövdesi mühürdeki hastayı ezdi: {s}"


def test_KARSIT_E15_hasta_secilmeden_baslatma_BUGUNKU_GIBI_sahipsiz(o):
    sid = _oner_onayla_baslat(o, {})
    s = _seans(o, sid)
    assert (s["ad"], s["hasta_satiri"]) == (None, None)


def test_KARSIT_E15_tunelden_AI_Pro_erisimi_DEGISMEZ_ve_hasta_baglanir(o):
    """Sahip kararı D-2.2: `/api/ai/pro/*` tünelden kimliksiz erişilebilir (onay 200, mühür '') — bu madde değiştirmez."""
    sid = _oner_onayla_baslat(o, {"patient_id": U1, "patient_name": "Boncuk"}, baslik=TUNEL)
    s = _seans(o, sid)
    assert (s["ad"], s["hasta_kimligi"]) == ("Boncuk", U1)


# ── D2.E07 · kapanış ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_E07_durdurulan_AI_Pro_satiri_KAPANIR_yeniden_acilista_ELEKTRIK_KESINTISI_olmaz(o):
    from database.treatment_history_db import TreatmentHistoryDB

    sid = _oner_onayla_baslat(o, {"patient_id": U1, "patient_name": "Boncuk"})
    assert o.c.post("/api/ai/pro/stop").status_code == 200
    s = _seans(o, sid)
    assert s["durum"] == "completed" and s["bitis"] and s["bitis_epoch"], f"durdurulan AI Pro satırı kapanmadı: {s}"
    assert float(s["bitis_epoch"]) >= float(s["basla_epoch"])
    TreatmentHistoryDB(o.kok)  # yeniden açılış (kurtarma __init__'te koşar)
    assert _seans(o, sid)["durum"] == "completed", "yeniden açılış durdurulmuş tedaviyi 'Elektrik Kesintisi' yaptı"


def test_KRITIK_E07_kapanis_STOPtan_SONRA_O4_Y8(o, monkeypatch):
    """Satır kapatılırken bobinler ZATEN durmuş olmalı (STOP sırası değişmez; finalize gecikmesi STOP'u bekletemez)."""
    import ai_pro_aparati as ap

    sid = _oner_onayla_baslat(o, {"patient_id": U1, "patient_name": "Boncuk"})
    o.c.post("/api/ai/ai_pro/frame", data={"image_base64": "/9j/2Q==", "client_id": ""})
    assert ap.bekle(lambda: bool(ap.calisan(o)), 3), "aparat: AI Pro bobinleri sürmedi"
    anlik = []
    gercek = o.api._finalize_session_db

    def _kaydeden(*a, **k):
        anlik.append(list(ap.calisan(o)))
        return gercek(*a, **k)

    monkeypatch.setattr(o.api, "_finalize_session_db", _kaydeden)
    o.c.post("/api/ai/pro/stop")
    assert anlik == [[]], f"satır STOP'tan ÖNCE kapatıldı (çalışan bobinler: {anlik})"
    assert _seans(o, sid)["durum"] == "completed"


def test_KARSIT_E07_ACIL_DURDUR_muhru_EZILMEZ(o):
    sid = _oner_onayla_baslat(o, {"patient_id": U1, "patient_name": "Boncuk"})
    assert o.c.post("/api/hardware/emergency_stop").status_code == 200
    o.c.post("/api/ai/pro/stop")
    assert _seans(o, sid)["durum"] == "EMERGENCY_STOPPED"


class _BozulanKedi:
    def __init__(self):
        self.n = 0

    def __call__(self, saglayici, *a, **k):
        self.n += 1
        if self.n == 1:
            return [0.3] * 7, [0.0] * 7, 1.0
        raise RuntimeError("doz modeli seans ortasında bozuldu (test)")


def test_KRITIK_E07_dongunun_KENDI_kesintisi_satiri_KESINTIYE_UGRADI_diye_kapatir(monkeypatch, tmp_path):
    """GERÇEK `_ai_pro_loop` (sahte kamera): doz modeli bozulunca N turda STOP → satır `interrupted`, `end_time` dolu."""
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    gercek_tahmin = __import__("servers.ai_router", fromlist=["x"])._predict_and_drive
    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:
        monkeypatch.setattr(ns.air, "_predict_and_drive", gercek_tahmin)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", _BozulanKedi())
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)

        class _Kamera:
            def __init__(self, *a, **k):
                pass

            def isOpened(self):  # noqa: N802
                return True

            def read(self):
                return True, np.zeros((8, 8, 3), dtype=np.uint8)

            def release(self):
                pass

        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _Kamera)
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2)
            assert r.status_code == 200, r.text[:200]
            with ns.api._session_lock:
                sid = ns.api._active_session.get("db_session_id")
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü ilk geçerli dozla sürmedi"
            assert ap.bekle(lambda: ap.dongu_bitir(ns.air, 0.01) == 0 and not ns.air._ai_loop_active, 8.0)
        with ns.db._get_connection() as c:
            durum, bitis = c.execute(
                "SELECT session_status, end_time FROM treatment_sessions WHERE id = ?", (sid,)
            ).fetchone()
        assert (durum, bool(bitis)) == ("interrupted", True), f"döngünün kendi kesintisi satırı kapatmadı: {durum!r}"
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


def test_KRITIK_E07_operator_durdurmasi_DONGU_teardownu_once_kossa_da_KESINTI_sayilmaz(monkeypatch, tmp_path):
    """Yarış BELİRLENİMCİ kurulur: `/ai/pro/stop` döngü bayrağını indirdikten SONRA, oturumu pasife almadan ÖNCE (önizleme
    durdurma adımında) GERÇEK döngünün teardown'ının bitmesi beklenir. Operatör durdurması yine "completed" olmalı."""
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:

        class _Kamera:
            def __init__(self, *a, **k):
                pass

            def isOpened(self):  # noqa: N802
                return True

            def read(self):
                return True, np.zeros((8, 8, 3), dtype=np.uint8)

            def release(self):
                pass

        from servers import ai_pro_hedef

        gercek_tahmin = __import__("servers.ai_router", fromlist=["x"])._predict_and_drive
        monkeypatch.setattr(ns.air, "_predict_and_drive", gercek_tahmin)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", lambda self, *a, **k: ([0.3] * 7, [0.0] * 7, 1.0))
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _Kamera)
        monkeypatch.setattr(ns.air, "_ai_hazirlik_durdur_ic", lambda *a, **k: ap.dongu_bitir(ns.air, 5.0))
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2)
            assert r.status_code == 200, r.text[:200]
            with ns.api._session_lock:
                sid = ns.api._active_session.get("db_session_id")
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            assert ns.c.post("/api/ai/pro/stop").status_code == 200
        with ns.db._get_connection() as c:
            durum = c.execute("SELECT session_status FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]
        assert durum == "completed", f"operatör durdurması döngünün teardown'ında '{durum}' yazıldı"
    finally:
        ns.air._ai_loop_active = False
        ns.geri()
