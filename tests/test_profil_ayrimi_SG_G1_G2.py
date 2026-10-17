# -*- coding: utf-8 -*-
"""SG.G1 / G2 (sahip gözlemi 2026-10-13) — seans / AI analizi / hasta (denek) / Performans Raporu PROFİLE GÖRE AYRI.

SAHİP: "raporlar seans geçmişi vs de ayrılmalı profillere göre … klinikle araştırma modunun alakası yok" + "araştırma modunun ai
analiz geçmişinde veteriner modunun ai analizi geçmişi de görünüyor".
ÖLÇÜLEN KUSUR (önce-kırmızı, `e872da6a`): liste / rapor / KPI uçları profil BİLMİYORDU — araştırma profili veteriner seanslarını,
AI analizlerini, hastalarını ve KPI'sını görüyordu; "Tümünü Sil" araştırmada veteriner kayıtlarına da uzanıyordu.
SÖZLEŞME (`apps/backend/utils/profil.py`):
  · istemci etkin profili `X-PEMF-Profil` ile bildirir; YENİ kayıt profiliyle yazılır;
  · başlık VARSA liste / sayım / KPI o profilin kümesi; YOKSA (eski istemci — yayınlanmış APK) bugünkü gibi süzgeçsiz;
  · ESKİ kayıt (profil boş) okumada TÜRETİLİR, veri değişmez: AI → `mode`, yoksa modül; seans → araştırma AI Pro öneki;
    hasta → veteriner + ev sahibi (S-SG.7);
  · toplu silme kapsamı YALNIZ DARALIR (başka profilin kaydı silinmez);
  · göç EKLEMELİ (eski DB açılır, iki kez açmak aynı, veri birebir) ve cihaz taşıması profili korur.
GERÇEK: SQLite DB'leri (geçici), uçlar (TestClient), arayüzün modül tablosu (kaynaktan).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
BASLIK = "X-PEMF-Profil"
VET, ARS, EV = "veterinarian", "researcher", "pet_owner"


def _h(profil):
    return {BASLIK: profil} if profil else {}


# ── tek kaynak: arayüzün modül tablosu ↔ backend ─────────────────────────────


def test_KAPI_arastirma_modulleri_ARAYUZUN_modul_tablosuyla_AYNI():
    """Sürüklenme kapısı: `AiHubScreen.ALL_MODULES` içinde `modes: ["researcher"]` olan kimlikler = `ARASTIRMA_AI_MODULLERI`
    (eski — `mode`suz — AI kaydının profili bu kümeden türetilir; ayrışırsa eski kayıt yanlış profilde görünür)."""
    from utils.profil import ARASTIRMA_AI_MODULLERI

    kaynak = (KOK / "apps/ui/src/screens/AiHubScreen.tsx").read_text(encoding="utf-8")
    # SGI-1.5: tablo bloğu ayrı okunur ve girdi çok satıra yayılsa da yakalanır; blokta geçen HER `id:` ayrıştırılmış olmalı (biçim
    # değişikliği bir girdiyi sessizce dışarıda bırakırsa kapı kör kalmasın — eskiden tek satır deseni + `>= 10` alt sınırı vardı).
    blok = re.search(r"const ALL_MODULES\b.*?=\s*\[(.*?)\n\s*\];", kaynak, re.S)
    assert blok, "ALL_MODULES bloğu bulunamadı — kapı kör"
    satirlar = re.findall(r'id:\s*"([a-z_]+)"[^{}]*?modes:\s*\[([^\]]*)\]', blok.group(1), re.S)
    assert len(satirlar) == len(re.findall(r"\bid:\s*\"", blok.group(1))) >= 10, (
        f"ALL_MODULES girdilerinin hepsi okunamadı ({len(satirlar)} ayrıştırıldı) — kapı kör"
    )
    arastirma = {m for m, modlar in satirlar if '"researcher"' in modlar}
    assert arastirma == set(ARASTIRMA_AI_MODULLERI), (
        f"arayüz ↔ backend araştırma modülleri AYRIŞTI: arayüzde {sorted(arastirma)}, backend {sorted(ARASTIRMA_AI_MODULLERI)}"
    )


def test_KAPI_arastirma_AI_Pro_onekleri_saglayici_adlariyla_AYNI():
    """Eski seansın profili `treatment_mode` önekinden türer (`AI Pro · {sağlayıcı.title}`); başlık değişirse kapı kırılır."""
    from servers import ai_pro_hedef as h
    from utils.profil import ARASTIRMA_SEANS_ONEKLERI, seans_profili

    for s in (h.FantomSaglayici, h.PetriSaglayici):
        assert seans_profili("", f"AI Pro · {s.title}") == ARS, f"{s.__name__}: '{s.title}' öneklerde yok"
    assert seans_profili("", f"AI Pro · {h.KediSaglayici.title}") == VET
    assert all(o.startswith("AI Pro · ") for o in ARASTIRMA_SEANS_ONEKLERI)
    src = (KOK / "apps/backend/servers/ai_router.py").read_text(encoding="utf-8")
    assert 'f"AI Pro · {_saglayici.title}"' in src, "AI Pro seans adı biçimi değişti — öneki yeniden doğrulayın"


def test_turetme_kurallari():
    from utils.profil import ai_kaydi_profili, gecerli_profil, hasta_profilde_mi, seans_profili

    assert gecerli_profil(" Researcher ") == ARS and gecerli_profil("admin") is None and gecerli_profil(None) is None
    assert ai_kaydi_profili(VET, "em_fantom") == VET, "yazılmış mode KAZANIR"
    assert ai_kaydi_profili("", "em_fantom") == ARS and ai_kaydi_profili("", "landmark") == VET
    assert ai_kaydi_profili("bozuk", "") == VET
    assert seans_profili(EV, "AI Pro · Fantom Tümör") == EV
    assert seans_profili("", "Manuel") == VET
    assert hasta_profilde_mi("", VET) and hasta_profilde_mi("", EV) and not hasta_profilde_mi("", ARS)
    assert hasta_profilde_mi(ARS, ARS) and not hasta_profilde_mi(ARS, VET)


# ── seans geçmişi + istatistik + KPI ─────────────────────────────────────────


@pytest.fixture
def tdb(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    db = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield db
    finally:
        db.close_connections()


def _seanslar(db):
    """vet (yazılı) · araştırma (yazılı) · ev sahibi (yazılı) · ESKİ manuel (boş → vet) · ESKİ fantom AI Pro (boş → araştırma)."""
    k = {
        "vet": db.start_session("Manuel", patient_name="V", profil=VET),
        "ars": db.start_session("Manuel", patient_name="R", profil=ARS),
        "ev": db.start_session("Manuel", patient_name="E", profil=EV),
        "eski_vet": db.start_session("Manuel", patient_name="EV1"),
        "eski_ars": db.start_session("AI Pro · Fantom Tümör", patient_name="EF"),
    }
    for sid in k.values():
        db.end_session(sid, duration_minutes=3)
    return k


def test_KRITIK_seans_gecmisi_PROFILE_gore_eski_kayit_TURETILIR(tdb):
    """MUTASYON: süzgeç SQL'den çıkarılırsa / türetme öneki bozulursa → KIRMIZI."""
    k = _seanslar(tdb)
    ids = lambda p: {r["id"] for r in tdb.get_session_history(limit=100, profil=p)}  # noqa: E731
    assert ids(VET) == {k["vet"], k["eski_vet"]}
    assert ids(ARS) == {k["ars"], k["eski_ars"]}, "araştırma geçmişinde veteriner seansı var / eski fantom seansı yok"
    assert ids(EV) == {k["ev"]}
    assert ids(None) == set(k.values()), "profil yokken (eski istemci) süzgeç UYGULANDI"
    with tdb._get_connection() as c:
        bos = c.execute("SELECT COUNT(*) FROM treatment_sessions WHERE COALESCE(profil,'') = ''").fetchone()[0]
    assert bos == 2, "eski kayıtların profili okumada türetilmeli, VERİ DEĞİŞMEMELİ"


def test_seans_gecmisi_sayfalamasi_SUZULMUS_kumeyle_tutarli(tdb):
    for i in range(6):
        tdb.start_session("Manuel", patient_name=f"P{i}", profil=(ARS if i % 2 else VET))
    s1 = tdb.get_session_history(limit=2, profil=ARS)
    s2 = tdb.get_session_history(limit=2, profil=ARS, before_id=s1[-1]["id"])
    assert len(s1) == 2 and len(s2) == 1, "sayfa boyu süzülmüş kümeyle tutarlı değil (Python'da süzme?)"
    assert {r["patient_name"] for r in s1 + s2} == {"P1", "P3", "P5"}


def test_KRITIK_istatistik_ve_KPI_PROFILIN_seanslari(tdb, monkeypatch):
    from servers import api_server, history_router

    _seanslar(tdb)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: tdb)
    api_server.app.dependency_overrides[history_router.get_db] = lambda: tdb
    try:
        c = TestClient(api_server.app, client=("127.0.0.1", 52611))
        for p, n in ((VET, 2), (ARS, 2), (EV, 1), (None, 5)):
            kpi = c.get("/api/kpi/summary", headers=_h(p)).json()
            assert kpi["totalSessions"] == n and kpi["completedSessions"] == n, f"KPI {p}: {kpi}"
            assert sum(d["count"] for d in kpi["last7Days"]) == n, f"KPI son 7 gün {p}: {kpi['last7Days']}"
            st = c.get("/api/history/statistics", headers=_h(p)).json()
            assert st["total_sessions"] == n and st["completed_sessions"] == n, f"istatistik {p}: {st}"
            h = c.get("/api/history/", headers=_h(p)).json()
            assert len(h) == n, f"geçmiş {p}: {len(h)}"
        assert c.get("/api/kpi/summary", headers=_h(ARS)).json()["modeDistribution"] == {
            "Manuel": 1,
            "AI Pro · Fantom Tümör": 1,
        }
    finally:
        api_server.app.dependency_overrides.pop(history_router.get_db, None)


def test_tumunu_CSV_disa_aktarim_PROFILIN_seanslari(tdb):
    from servers import api_server, history_router

    k = _seanslar(tdb)
    api_server.app.dependency_overrides[history_router.get_db] = lambda: tdb
    try:
        c = TestClient(api_server.app, client=("127.0.0.1", 52612))
        r = c.get("/api/history/export_csv", headers=_h(ARS))
        assert r.status_code == 200, r.text[:200]
        satir = [s for s in r.text.splitlines()[1:] if s.strip()]
        assert sorted(int(s.split(",")[0]) for s in satir) == sorted([k["ars"], k["eski_ars"]])
        r0 = c.get("/api/history/export_csv")
        assert len([s for s in r0.text.splitlines()[1:] if s.strip()]) == 5, "başlıksız 'Tümünü' süzüldü"
    finally:
        api_server.app.dependency_overrides.pop(history_router.get_db, None)


# ── seans başlatma ucu profili yazar ─────────────────────────────────────────


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            yield ns
    finally:
        ns.geri()


_SEANS = {"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1, 2]}


@pytest.mark.parametrize("profil, beklenen", [(ARS, ARS), (EV, EV), (None, ""), ("uydurma", "")])
def test_KRITIK_seans_baslatma_ISTEGIN_profilini_yazar(o, profil, beklenen):
    r = o.c.post("/api/session/start", json=_SEANS, headers=_h(profil))
    assert r.status_code == 200, r.text[:200]
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    o.c.post("/api/session/stop")
    with o.db._get_connection() as c:
        (yazilan,) = c.execute("SELECT COALESCE(profil,'') FROM treatment_sessions WHERE id=?", (sid,)).fetchone()
    assert yazilan == beklenen, f"başlık {profil!r} → satır profili {yazilan!r}"


# ── AI analiz geçmişi ────────────────────────────────────────────────────────


@pytest.fixture
def ai(tdb, monkeypatch):
    from servers import api_server

    tdb.add_ai_analysis(mode=VET, module_id="landmark", result_summary="vet-fgs")
    tdb.add_ai_analysis(mode=ARS, module_id="em_fantom", result_summary="ars-fantom")
    tdb.add_ai_analysis(mode=EV, module_id="landmark", result_summary="ev-fgs")
    tdb.add_ai_analysis(module_id="histopath", result_summary="eski-histo")  # mode yok → araştırma
    tdb.add_ai_analysis(module_id="thermal", result_summary="eski-termal")  # mode yok → veteriner
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: tdb)
    return TestClient(api_server.app, client=("127.0.0.1", 52613))


def _ozet(c, p):
    return sorted(k["result_summary"] for k in c.get("/api/ai/log?limit=50", headers=_h(p)).json()["data"])


def test_KRITIK_AI_gecmisi_PROFILE_gore_eski_kayit_MODULDEN_turetilir(ai):
    """Sahibin gözlemi: araştırma AI geçmişinde veteriner analizleri görünüyordu. MUTASYON: süzgeç kaldırılır → KIRMIZI."""
    assert _ozet(ai, ARS) == ["ars-fantom", "eski-histo"]
    assert _ozet(ai, VET) == ["eski-termal", "vet-fgs"]
    assert _ozet(ai, EV) == ["ev-fgs"]
    assert len(_ozet(ai, None)) == 5, "eski istemci (başlıksız) süzüldü"


def test_AI_kaydi_mode_gondermeyen_yazicida_ISTEGIN_profili(ai, tdb):
    r = ai.post("/api/ai/log", json={"module": "x", "summary": "yeni-ars", "module_id": "landmark"}, headers=_h(ARS))
    assert r.status_code == 200, r.text[:200]
    assert "yeni-ars" in _ozet(ai, ARS) and "yeni-ars" not in _ozet(ai, VET)
    r = ai.post("/api/ai/log", json={"summary": "mode-kazanir", "mode": VET, "module_id": "em_fantom"}, headers=_h(ARS))
    assert r.status_code == 200 and "mode-kazanir" in _ozet(ai, VET)


def test_KRITIK_AI_toplu_silme_YALNIZ_profilin_kayitlari(ai):
    """Kapsam GENİŞLEMEZ: araştırmada "Tümünü Sil" veteriner analizlerini silmez. MUTASYON: silmede süzgeç yok → KIRMIZI."""
    r = ai.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True}, headers=_h(ARS))
    assert r.status_code == 200 and r.json()["deleted"] == 2, r.text[:200]
    assert _ozet(ai, None) == ["eski-termal", "ev-fgs", "vet-fgs"]


# ── hasta / denek ────────────────────────────────────────────────────────────


@pytest.fixture
def hc(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from servers import api_server, patient_router

    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: pdb)
    c = TestClient(api_server.app, client=("127.0.0.1", 52614))
    for ad, p in (("Vet-Mia", VET), ("Ars-Fantom1", ARS), ("Ev-Pamuk", EV), ("Baslıksız", None)):
        r = c.post("/api/patients", json={"name": ad}, headers=_h(p))
        assert r.status_code == 200 and r.json()["status"] == "success", r.text[:200]
    return c, pdb


def _adlar(c, p, **q):
    j = c.get("/api/patients", params=q, headers=_h(p)).json()
    return sorted(h["name"] for h in j["data"]), j["total"]


def test_KRITIK_hasta_listesi_PROFILE_gore_eski_kayit_VET_ve_EV_SAHIBINDE(hc):
    """S-SG.7: profili boş (eski / başlıksız istemcinin) kayıt veteriner ve ev sahibinde görünür, araştırmada görünmez."""
    c, _ = hc
    assert _adlar(c, ARS) == (["Ars-Fantom1"], 1), "araştırmada veteriner hastası görünüyor"
    assert _adlar(c, VET) == (["Baslıksız", "Vet-Mia"], 2)
    assert _adlar(c, EV) == (["Baslıksız", "Ev-Pamuk"], 2)
    assert _adlar(c, None) == (sorted(["Vet-Mia", "Ars-Fantom1", "Ev-Pamuk", "Baslıksız"]), 4), "eski istemci süzüldü"
    assert _adlar(c, VET, limit=1)[1] == 2, "sayfalı istekte 'total' süzülmüş kümenin sayısı değil"


def test_hasta_GUNCELLEME_profili_DEGISTIRMEZ(hc):
    c, pdb = hc
    pid = next(h["id"] for h in c.get("/api/patients", headers=_h(VET)).json()["data"] if h["name"] == "Vet-Mia")
    r = c.post("/api/patients", json={"id": pid, "name": "Vet-Mia2"}, headers=_h(ARS))
    assert r.status_code == 200
    assert _adlar(c, VET)[0] == ["Baslıksız", "Vet-Mia2"] and "Vet-Mia2" not in _adlar(c, ARS)[0]


def test_KRITIK_hasta_TUMUNU_SIL_yalniz_profilin_listesi(hc):
    """Kapsam GENİŞLEMEZ: araştırmada "Tümünü Sil" yalnız araştırma deneklerini; veteriner "Tümünü Sil" ekranda gördüğünü
    (kendi + eski) siler, araştırma ve ev sahibi kayıtları DURUR. MUTASYON: silmede koşul yok → KIRMIZI."""
    c, _ = hc
    r = c.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"}, headers=_h(ARS))
    assert r.status_code == 200, r.text[:200]
    assert _adlar(c, None)[0] == sorted(["Vet-Mia", "Ev-Pamuk", "Baslıksız"])
    r = c.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"}, headers=_h(VET))
    assert r.status_code == 200
    assert _adlar(c, None)[0] == ["Ev-Pamuk"]


def test_cihaz_tasimasi_hasta_PROFILINI_korur(tmp_path, hc):
    from database.patient_database import PatientDatabase

    _, kaynak = hc
    hedef = PatientDatabase(str(tmp_path / "hedef.db"))
    for h in kaynak.disa_aktarim_hastalari():
        hedef.add_patient(dict(h), patient_id=h["id"])
    with kaynak._get_connection() as a, hedef._get_connection() as b:
        q = "SELECT id, COALESCE(profil,'') FROM patients ORDER BY id"
        ka, kb = [tuple(r) for r in a.execute(q).fetchall()], [tuple(r) for r in b.execute(q).fetchall()]
    assert ka == kb and {p for _, p in ka} == {VET, ARS, EV, ""}, f"taşımada profil kayboldu: {ka} → {kb}"


# ── göç: eski DB ─────────────────────────────────────────────────────────────


def test_KRITIK_GOC_eski_DB_acilir_iki_kez_ayni_veri_BIREBIR(tmp_path, monkeypatch):
    """Profil kolonu OLMAYAN (eski sürüm) tedavi + hasta DB'si: açılış kolonu ekler, satırlar birebir kalır, ikinci açılış
    hiçbir şey değiştirmez, eski satırlar türetilmiş profilleriyle listelenir."""
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    t = TreatmentHistoryDB(tmp_path / "g")
    sid = t.start_session("Manuel", patient_name="Eski")
    sid2 = t.start_session("AI Pro · Petri Kuyu", patient_name="EskiP")
    for s in (sid, sid2):  # kapalı seanslar: açılış kurtarması (yarım seans → ABORTED) satırı değiştirmesin
        t.end_session(s, duration_minutes=2)
    with t._get_connection() as c:
        c.execute("ALTER TABLE treatment_sessions DROP COLUMN profil")
        c.commit()
        once = c.execute("SELECT * FROM treatment_sessions ORDER BY id").fetchall()
    t.close_connections()
    p = PatientDatabase(str(tmp_path / "p.db"))
    p.add_patient({"name": "EskiHasta"})
    with p._get_connection() as c:
        c.execute("ALTER TABLE patients DROP COLUMN profil")
        c.commit()
        p_once = c.execute("SELECT * FROM patients").fetchall()
    for _ in range(2):
        t2 = TreatmentHistoryDB(tmp_path / "g")
        with t2._get_connection() as c:
            kol = [r[1] for r in c.execute("PRAGMA table_info(treatment_sessions)").fetchall()]
            assert kol.count("profil") == 1
            sonra = [
                tuple(r)[: len(once[0])] for r in c.execute("SELECT * FROM treatment_sessions ORDER BY id").fetchall()
            ]
        assert sonra == [tuple(r) for r in once], "göç eski satırları DEĞİŞTİRDİ"
        assert [r["id"] for r in t2.get_session_history(limit=10, profil=VET)] == [sid]
        assert [r["patient_name"] for r in t2.get_session_history(limit=10, profil=ARS)] == ["EskiP"]
        t2.close_connections()
        p2 = PatientDatabase(str(tmp_path / "p.db"))
        with p2._get_connection() as c:
            assert [r[1] for r in c.execute("PRAGMA table_info(patients)").fetchall()].count("profil") == 1
            p_sonra = [tuple(r)[: len(p_once[0])] for r in c.execute("SELECT * FROM patients").fetchall()]
        assert p_sonra == [tuple(r) for r in p_once]
        assert [h["name"] for h in p2.get_all_patients(profil=EV)] == ["EskiHasta"]
        assert p2.get_all_patients(profil=ARS) == [] and p2.count_patients(profil=ARS) == 0
