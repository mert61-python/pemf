# -*- coding: utf-8 -*-
"""D2.54 (B-3.33 · B-3.34) · A-06 · A-27 · Y125 — 5 yıl inaktif hastanın anonimleştirmesi OPERATÖR ONAYINA bağlı, EKSİKSİZ ve yeniden
denenir; hekim atfı KALIR.

ÖLÇÜLEN KUSURLAR:
- A-06: günlük bakım döngüsü 1825 gün inaktif hastaları onaysız ve SESSİZ (yalnız günlük satırı) geri dönüşsüz anonimleştiriyordu.
- B-3.33 / Y125: `ai_analyses` (hasta adı, özet, hekimin gerekçe metni, Y114 değerlendirme geçmişi) anonimleşmiyordu → [ANONIM] hastanın
  adı AI geçmişinde, PDF'te ve aramada kalıyordu.
- B-3.34: tedavi-DB kopyasının anonimleştirmesi bir kez düşerse kanonik taraf `anonymized=1` olduğu için hasta bir daha SEÇİLMİYOR →
  tedavi geçmişindeki adlar SÜRESİZ kalıyordu.
- A-27: anonimleştirme seans satırındaki HEKİM adını (`operator_name`) da `[ANONIM]` yapıyordu — hekim atfı kalmalı (anonimleştirme
  hastayı hedefler); `patient_veteriner` (hastanın veteriner hekimi) de seans parametresinden siliniyordu.
Kapı fonksiyon zincirine pinli (`services.kvkk_anonimlestirme.tur` → kanonik `anonymize_inactive_patients` → tedavi-DB kopyası + AI
kayıtları), günlük döngünün onu çağırdığı ayrıca ölçülür. GERÇEK `PatientDatabase` + GERÇEK `TreatmentHistoryDB` (geçici dizin).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta

import pytest

AD = "İpek Işıl Kızılcık"
SAHIP = "Ayşe Sahibi-5410"
EPOSTA = "sahip5410@ornek.com"
HEKIM = "Dr Mehmet Hekim"
HEKIM_EPOSTA = "dr.mehmet@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield type("O", (), {"pdb": pdb, "tdb": tdb})
    finally:
        tdb.close_connections()


def _hasta(o, ad=AD, gun=2200, sahip=SAHIP, eposta=EPOSTA) -> str:
    pid = o.pdb.add_patient({"name": ad, "owner": sahip, "owner_email": eposta, "veteriner": HEKIM})
    with o.pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=gun)).isoformat(), pid),
        )
        c.commit()
    return pid


def _gecmis(o, pid, ad=AD):
    """Tedavi DB'si: ayna hasta + seans (hekim adıyla) + parametreler + kimlikli AI analizi + iki değerlendirme (Y114 geçmişi)."""
    t = o.tdb
    tpid = t.upsert_patient({"name": ad, "patient_uuid": pid, "owner_name": SAHIP, "owner_email": EPOSTA})
    sid = int(
        t.start_session(treatment_mode="Manuel", patient_name=ad, operator_name=HEKIM, operator_email=HEKIM_EPOSTA)
    )
    t.set_session_meta(sid, patient_id=tpid)
    t.set_session_parameter(sid, "patient_owner_email", EPOSTA, "")
    t.set_session_parameter(sid, "patient_veteriner", HEKIM, "")
    t.end_session(sid, patient_notes=f"{ad} sakin", duration_minutes=10)
    aid = t.add_ai_analysis(
        module_id="kalca",
        patient_name=ad,
        result_summary=f"{ad.upper()} için kalça bulgusu",
        result_detail={"hasta": ad, "skor": 0.8},
        operator_email=HEKIM_EPOSTA,
        patient_uuid=pid,
    )
    t.set_ai_review(aid, "rejected", f"{ad.lower()} sahibi {SAHIP} ile görüşüldü", reviewed_by=HEKIM_EPOSTA)
    t.set_ai_review(aid, "approved", "tamam", reviewed_by=HEKIM_EPOSTA)
    return sid, aid


def _tedavi_metni(o) -> str:
    """Tedavi DB'sindeki TÜM metin değerleri (ham + json kaçışlı arama için birleşik)."""
    parcalar = []
    with o.tdb._get_connection() as c:
        for (t,) in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'audit_events'"
        ).fetchall():
            for satir in c.execute(f'SELECT * FROM "{t}"').fetchall():
                parcalar += [v for v in tuple(satir) if isinstance(v, str)]
    return "\n".join(parcalar)


def _iceriyor(metin: str, aranan: str) -> bool:
    return aranan in metin or json.dumps(aranan)[1:-1] in metin


def _onayla(o, gun=1825):
    o.tdb.anonim_onayi_yaz(gun=gun, sayi=1, kim=HEKIM_EPOSTA)


def test_KRITIK_A06_ONAYSIZ_hicbir_sey_anonimlesmez_bekleyen_SAYILIR_ve_UYARILIR(o, caplog):
    """MUTASYON: onay denetimi silinir → KIRMIZI (sessiz, geri dönüşsüz anonimleştirme)."""
    from services import kvkk_anonimlestirme as kv

    pid = _hasta(o)
    _gecmis(o, pid)
    with caplog.at_level(logging.WARNING):
        sonuc = kv.tur(o.pdb, o.tdb)
    assert sonuc["onay"] is False and sonuc["bekleyen"] == 1 and sonuc["anonimlestirilen"] == 0, sonuc
    assert o.pdb.get_patient(pid)["name"] == AD, "ONAYSIZ anonimleştirme yapıldı (A-06)"
    assert _iceriyor(_tedavi_metni(o), AD)
    assert any("onay" in r.getMessage().lower() and "1" in r.getMessage() for r in caplog.records), (
        "bekleyen sayı uyarısı yok"
    )


def test_KRITIK_ONAYLI_hasta_HER_YERDEN_anonim_hekim_atfi_KALIR(o):
    """MUTASYON: AI kayıtlarının anonimleştirmesi silinir / seans `operator_name` yeniden [ANONIM] yapılır → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pid = _hasta(o)
    sid, aid = _gecmis(o, pid)
    _onayla(o)
    sonuc = kv.tur(o.pdb, o.tdb)
    assert sonuc["anonimlestirilen"] == 1, sonuc
    assert o.pdb.get_patient(pid)["name"] == "[ANONIM]"
    metin = _tedavi_metni(o)
    for aranan in (AD, AD.upper(), AD.lower(), "ipek ışıl kızılcık", SAHIP, EPOSTA):
        assert not _iceriyor(metin, aranan), f"anonimleştirmeden sonra tedavi DB'sinde duruyor: {aranan!r}"
    with o.tdb._get_connection() as c:
        hekim = c.execute("SELECT operator_name, operator_email FROM treatment_sessions WHERE id=?", (sid,)).fetchone()
        vet = c.execute(
            "SELECT parameter_value FROM session_parameters WHERE session_id=? AND parameter_name='patient_veteriner'",
            (sid,),
        ).fetchone()
    assert tuple(hekim) == (HEKIM, HEKIM_EPOSTA), f"A-27: hekim atfı silindi: {tuple(hekim)}"
    assert vet[0] == HEKIM, f"A-27: hastanın veteriner hekimi silindi: {vet[0]!r}"
    ai = next(a for a in o.tdb.get_ai_analyses(10) if a["id"] == aid)
    assert ai["patient_name"] == "[ANONIM]" and "kalça bulgusu" in ai["result_summary"], ai["result_summary"]
    assert ai["operator_email"] == HEKIM_EPOSTA and ai.get("reviewed_by") == HEKIM_EPOSTA, "A-27: AI hekim atfı silindi"
    assert [g.get("reviewed_by") for g in ai["review_history"]] == [HEKIM_EPOSTA], ai["review_history"]


def test_KRITIK_B334_tedavi_DB_adimi_DUSERSE_sonraki_turda_YENIDEN_denenir(o):
    """MUTASYON: kalıcı bekleyen listesi / yeniden deneme silinir → KIRMIZI (tedavi geçmişindeki ad süresiz kalırdı)."""
    from services import kvkk_anonimlestirme as kv

    pid = _hasta(o)
    _gecmis(o, pid)
    _onayla(o)
    with o.tdb._get_connection() as c:
        c.execute(
            "CREATE TRIGGER d254_ariza BEFORE UPDATE OF patient_name ON treatment_sessions "
            "BEGIN SELECT RAISE(ABORT, 'D2.54 enjekte ariza'); END"
        )
        c.commit()
    ilk = kv.tur(o.pdb, o.tdb)
    assert o.pdb.get_patient(pid)["name"] == "[ANONIM]" and ilk["tedavi_bekleyen"] == 1, ilk
    assert _iceriyor(_tedavi_metni(o), AD), "aparat: arıza tedavi-DB adımını düşürmedi"
    with o.tdb._get_connection() as c:
        c.execute("DROP TRIGGER d254_ariza")
        c.commit()
    ikinci = kv.tur(o.pdb, o.tdb)
    assert ikinci["tedavi_bekleyen"] == 0, ikinci
    assert not _iceriyor(_tedavi_metni(o), AD), "ikinci turda tedavi-DB anonimleştirmesi yeniden DENENMEDİ"


def test_KRITIK_A09_esik_degisince_eski_onay_GECERSIZ(o):
    """Onay onaylanan eşiğe bağlı: 730 güne verilmiş onay 1825 günlük kural için sayılmaz (ya da tersi) → yeni onay gerekir.
    MUTASYON: onay eşikten bağımsız bir bayrağa döner → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pid = _hasta(o)
    _onayla(o, gun=730)
    sonuc = kv.tur(o.pdb, o.tdb)
    assert sonuc["onay"] is False and o.pdb.get_patient(pid)["name"] == AD, sonuc


def test_KRITIK_Y125_kimliksiz_AI_kaydi_ad_TEK_hastaya_cozulurse_anonim_BELIRSIZSE_dokunulmaz(o):
    from services import kvkk_anonimlestirme as kv

    pid = _hasta(o)
    _gecmis(o, pid)
    eski = o.tdb.add_ai_analysis(module_id="ses", patient_name=AD, result_summary="eski kimliksiz kayıt")
    belirsiz_ad = "Boncuk"
    p1 = _hasta(o, ad=belirsiz_ad, sahip="S1", eposta="s1@ornek.com")
    _hasta(o, ad=belirsiz_ad, gun=10, sahip="S2", eposta="s2@ornek.com")  # aynı adlı AKTİF hasta
    o.tdb.upsert_patient({"name": belirsiz_ad, "patient_uuid": p1, "owner_name": "S1"})
    belirsiz = o.tdb.add_ai_analysis(module_id="ses", patient_name=belirsiz_ad, result_summary="kimin?")
    _onayla(o)
    kv.tur(o.pdb, o.tdb)
    kayit = {a["id"]: a for a in o.tdb.get_ai_analyses(50)}
    assert kayit[eski]["patient_name"] == "[ANONIM]", "kimliksiz ama TEK hastaya çözülen eski AI kaydı anonimleşmedi"
    assert kayit[belirsiz]["patient_name"] == belirsiz_ad, (
        "aynı adlı AKTİF hasta varken kimliksiz kayıt anonimleşti (yanlış hasta)"
    )


def test_KARSIT_aktif_hasta_ve_kaydi_DOKUNULMAZ(o):
    from services import kvkk_anonimlestirme as kv

    aktif = _hasta(o, ad="Tarçın Aktif", gun=10)
    _gecmis(o, aktif, ad="Tarçın Aktif")
    _onayla(o)
    assert kv.tur(o.pdb, o.tdb)["anonimlestirilen"] == 0
    assert o.pdb.get_patient(aktif)["name"] == "Tarçın Aktif" and _iceriyor(_tedavi_metni(o), "Tarçın Aktif")


class _TurBitti(BaseException):
    pass


def test_KRITIK_gunluk_dongu_ONAYSIZ_anonimlestirmez(o, monkeypatch):
    """Günlük döngü artık `kvkk_anonimlestirme.tur`u çağırır: onay yokken 5 yıl inaktif hasta anonimleşmez.
    MUTASYON: döngüye eski `anonymize_inactive_patients(1825)` geri konur → KIRMIZI."""
    from servers import api_server as api

    pid = _hasta(o)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: o.tdb)
    monkeypatch.setattr(api, "get_patient_database", lambda: o.pdb)
    orj = time.sleep
    durum = {"ident": None, "uyku": 0}

    def _sleep(s):
        if threading.get_ident() == durum["ident"]:
            durum["uyku"] += 1
            if durum["uyku"] >= 2:
                raise _TurBitti()
            return None
        return orj(s)

    def _kos():
        durum["ident"] = threading.get_ident()
        try:
            api._daily_maintenance_loop()
        except _TurBitti:
            pass

    time.sleep = _sleep
    try:
        th = threading.Thread(target=_kos, daemon=True)
        th.start()
        th.join(30)
    finally:
        time.sleep = orj
    assert durum["uyku"] == 2 and not th.is_alive()
    assert o.pdb.get_patient(pid)["name"] == AD, "günlük döngü ONAYSIZ anonimleştirdi (A-06)"


@pytest.fixture
def api_istemcisi(o, monkeypatch):
    from database import patient_database as pmod
    from fastapi.testclient import TestClient
    from servers import api_server as api
    from servers import system_router as sr

    monkeypatch.setattr(sr, "_pii_ayar_db", lambda: o.tdb)
    monkeypatch.setattr(pmod, "get_patient_database", lambda *a, **k: o.pdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: o.tdb)
    return TestClient(api.app, client=("127.0.0.1", 51937))


def test_KRITIK_API_bekleyen_sayi_gosterilir_onay_ESIK_ve_SAYIYLA_kayda_gecer(o, api_istemcisi):
    """A-06 / A-09: Ayarlar ekranı bekleyen hasta sayısını görür; onay eşik + o anki sayıyla yazılır ve denetim izine geçer.
    MUTASYON: POST onayı yazmaz / GET bekleyeni göstermez → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pid = _hasta(o)
    c = api_istemcisi
    durum = c.get("/api/settings/retention").json()["anonymization"]
    assert (durum["days"], durum["acknowledged"], durum["pending"]) == (1825, False, 1), durum
    assert c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 365}).status_code == 200
    assert o.tdb.anonim_onayi_oku() is None, "PII maskeleme onayı anonimleştirme onayı SAYILMAMALI (ayrı karar)"
    assert c.post("/api/settings/retention", json={"anonymize_acknowledge": True}).status_code == 200
    onay = o.tdb.anonim_onayi_oku()
    assert (onay["gun"], onay["sayi"]) == (1825, 1), onay
    iz = o.tdb.denetim_oku(10, "retention.anonim_onay")
    assert iz and iz[0]["item_count"] == 1 and json.loads(iz[0]["detail"])["gun"] == 1825, iz
    assert c.get("/api/settings/retention").json()["anonymization"]["acknowledged"] is True
    assert kv.tur(o.pdb, o.tdb)["anonimlestirilen"] == 1 and o.pdb.get_patient(pid)["name"] == "[ANONIM]"


def test_KRITIK_arayuz_fiksturu_GERCEK_retention_yanitiyla_AYNI(o, api_istemcisi):
    """Arayüz yarısı (`screens/__tests__/veriSaklamaAnonim.D254.web.test.tsx`) bu GERÇEK yanıtı okur (jest Python koşturamaz):
    onaysız, 1 hasta bekliyor. Bayatlarsa KIRMIZI; yenilemek: `D254_FIKSTUR_YAZ=1` (yalnız dosyanın tamamı yeşilken kalıcı — S-A2.5)."""
    import os
    from pathlib import Path

    _hasta(o)
    r = api_istemcisi.get("/api/settings/retention")
    beklenen = {"durum": r.status_code, "govde": r.json()}
    f = Path(__file__).resolve().parents[1] / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__"
    f = f / "retentionAnonim.D254.json"
    if os.environ.get("D254_FIKSTUR_YAZ") == "1":
        f.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert f.exists(), "arayüz fikstürü yok (D254_FIKSTUR_YAZ=1 ile üret)"
    assert json.loads(f.read_text(encoding="utf-8")) == beklenen, "arayüz fikstürü GERÇEK yanıttan BAYATLADI"
