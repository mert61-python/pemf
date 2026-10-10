# -*- coding: utf-8 -*-
"""F2-1.3 (2-F incelemesi · A1) — kanonik tarafı ANONİM hastanın adı tedavi DB'sine GERİ GELİRSE sonraki tur onu yeniden anonimleştirir.

ÖLÇÜLEN KUSUR (B-3.34'ün kalan yarısı): D2.54'ün kalıcı bekleyen listesi yalnız "tedavi adımı düştü" durumunu yeniden dener. Kanonik hasta
`anonymized=1` olduktan sonra tedavi DB'sine ad şu yollarla GERİ geliyor ve hiçbir tur onu bir daha görmüyordu (hasta artık aday değil,
liste boş) → ad SÜRESİZ kalıyordu:
  R1 · anonimleştirmeden ÖNCE alınmış taşıma paketinin REPLACE_ALL geri yüklemesi (`/api/data/import` → `import_rows(replace=True)`;
       hasta kartı ZATEN VAR → atlanır): seans, ayna hasta ve AI kaydı adla geri döndü;
  R2 · bayat istemcinin anonim hastaya ESKİ adla açtığı seans (`_persist_session_start` → `upsert_patient` ayna satırına eski adı yazar);
  R3 · kalıcı bekleyen listesi bozuk okunursa (`anonim_bekleyen_oku` → {} + ERROR) bir sonraki `anonim_bekleyen_ekle` eski girdiyi SİLER.
GERÇEK `PatientDatabase` + GERÇEK `TreatmentHistoryDB` (tmp), GERÇEK `services.kvkk_anonimlestirme.tur`.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import pytest

HEKIM = "dr.f213@klinik.vet"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield pdb, tdb
    finally:
        tdb.close_connections()


def _hasta(pdb, ad, gun=2200):
    pid = pdb.add_patient({"name": ad, "owner": f"Sahip {ad}", "owner_email": "f213@ornek.com"})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=gun)).isoformat(), pid),
        )
        c.commit()
    return pid


def _seans(tdb, ad, pid):
    """`api_server._persist_session_start` sırası: ayna hasta (istemcinin gönderdiği adla) → seans → hasta bağı."""
    tpid = tdb.upsert_patient({"name": ad, "patient_uuid": pid, "owner_email": "f213@ornek.com"})
    sid = int(
        tdb.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr F213", operator_email=HEKIM)
    )
    tdb.set_session_meta(sid, started_epoch=time.time(), patient_id=tpid)
    tdb.end_session(sid, patient_notes=f"{ad} sakin", duration_minutes=5)
    return sid


def _adli(tdb, ad) -> dict:
    kac = json.dumps(ad)[1:-1]
    n: dict = {}
    with tdb._get_connection() as c:
        for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            im = c.execute(f'SELECT * FROM "{t}"')
            kol = [k[0] for k in im.description]
            for s in im.fetchall():
                for k, d in zip(kol, tuple(s)):
                    if isinstance(d, str) and (ad in d or kac in d):
                        n[f"{t}.{k}"] = n.get(f"{t}.{k}", 0) + 1
    return n


def _onay(tdb):
    from services import kvkk_anonimlestirme as kv

    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim=HEKIM)


def test_KRITIK_R1_REPLACE_ALL_geri_yukleme_adi_getirirse_sonraki_tur_ANONIMLESTIRIR(o):
    """MUTASYON: tur başındaki uzlaştırma adımı silinir → KIRMIZI (geri yüklenen ad süresiz kalır)."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    ad = "Pamuk Yedek-F213"
    pid = _hasta(pdb, ad)
    _seans(tdb, ad, pid)
    tdb.add_ai_analysis(
        module_id="m", patient_name=ad, result_summary=f"{ad} bulgu", patient_uuid=pid, operator_email=HEKIM
    )
    paket = tdb.export_rows()  # anonimleştirmeden ÖNCE alınmış taşıma paketi
    _onay(tdb)
    assert kv.tur(pdb, tdb)["anonimlestirilen"] == 1 and not _adli(tdb, ad), "aparat: ilk tur anonimleştirmedi"
    tdb.import_rows(paket, replace=True)  # `/api/data/import` DB yolu; hasta kartı ZATEN VAR → uç onu atlar
    assert pdb.get_patient(pid)["name"] == "[ANONIM]"
    assert _adli(tdb, ad), "aparat: geri yükleme adı geri getirmedi"
    kv.tur(pdb, tdb)
    assert not _adli(tdb, ad), f"geri yüklenen ad tedavi DB'sinde SÜRESİZ kaldı: {_adli(tdb, ad)}"
    with tdb._get_connection() as c:
        hekim = c.execute("SELECT operator_email FROM treatment_sessions").fetchone()[0]
    assert hekim == HEKIM, "A-27: hekim atfı uzlaştırmada silindi"


def test_KRITIK_R2_bayat_istemcinin_ESKI_adla_actigi_seans_ANONIMLESIR(o):
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    ad = "Boncuk Bayat-F213"
    pid = _hasta(pdb, ad)
    _seans(tdb, ad, pid)
    _onay(tdb)
    kv.tur(pdb, tdb)
    pdb.touch_last_treatment(pid)
    _seans(tdb, ad, pid)  # istemci ESKİ adı gönderdi
    assert _adli(tdb, ad), "aparat: bayat ad tedavi DB'sine yazılmadı"
    kv.tur(pdb, tdb)
    assert not _adli(tdb, ad), f"bayat istemcinin geri yazdığı ad SÜRESİZ kaldı: {_adli(tdb, ad)}"


def test_KRITIK_R3_bekleyen_listesi_BOZUKKEN_eski_girdi_kaybolsa_da_ad_ANONIMLESIR(o):
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    a, b = "Duman Liste-F213", "Zeytin Liste-F213"
    pa = _hasta(pdb, a)
    _seans(tdb, a, pa)
    _onay(tdb)
    with tdb._get_connection() as c:
        c.execute(
            "CREATE TRIGGER f213_ariza BEFORE UPDATE OF patient_name ON treatment_sessions "
            "BEGIN SELECT RAISE(ABORT, 'F2-1.3 enjekte ariza'); END"
        )
        c.commit()
    assert kv.tur(pdb, tdb)["tedavi_bekleyen"] == 1, "aparat: tedavi adımı düşmedi"
    with tdb._get_connection() as c:
        c.execute("DROP TRIGGER f213_ariza")
        c.commit()
    ham = tdb._get_system_setting(tdb.ANONIM_BEKLEYEN_ANAHTARI)
    tdb._set_system_setting(tdb.ANONIM_BEKLEYEN_ANAHTARI, ham[:-3], "yarım JSON")  # okunamaz liste
    pb = _hasta(pdb, b)
    _seans(tdb, b, pb)
    kv.tur(pdb, tdb)
    kv.tur(pdb, tdb)
    assert not _adli(tdb, b)
    assert not _adli(tdb, a), f"bozuk liste ezilince A'nın adı tedavi DB'sinde SÜRESİZ kaldı: {_adli(tdb, a)}"


def test_KARSIT_hasta_yeniden_KAYDEDILDI_ya_da_AKTIF_dokunulmaz(o):
    """Klinik anonim hastanın kartını yeniden adla doldurdu (`update_patient` → `anonymized=0`) ya da hasta hiç anonim değil: uzlaştırma
    bunlara DOKUNMAZ (yalnız kanonik tarafı anonim olan hasta)."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    ad = "Tarçın Geri-F213"
    pid = _hasta(pdb, ad)
    _seans(tdb, ad, pid)
    _onay(tdb)
    kv.tur(pdb, tdb)
    assert pdb.update_patient(pid, {"name": ad, "owner": "Yeni Sahip"}) is True
    assert str(pdb.get_patient(pid).get("anonymized") or 0) in ("0", "False", "false"), (
        "aparat: kart yeniden adlanınca bayrak düşmedi"
    )
    pdb.touch_last_treatment(pid)  # `_persist_session_start` — hasta yeniden tedavi görüyor (aday değil)
    _seans(tdb, ad, pid)
    aktif = "Fıstık Aktif-F213"
    pa = _hasta(pdb, aktif, gun=10)
    _seans(tdb, aktif, pa)
    kv.tur(pdb, tdb)
    assert _adli(tdb, ad), "yeniden kaydedilen hastanın YENİ adı anonimleştirildi"
    assert _adli(tdb, aktif), "aktif hastanın adı anonimleştirildi"
