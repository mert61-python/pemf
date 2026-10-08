# -*- coding: utf-8 -*-
"""C2-1.2 (2-C inceleme, A1) — D2.22 kalıcı "taşıma yapıldı" işareti GERÇEK arızada da KONMAMALI.

KUSUR (D2.22, `4603fef`): `_ai_hasta_kimliklerini_tasi_bir_kez` işareti "taşıma düşmediyse" koyar; ama iki alt katman
arızayı YUTAR ve "başarılı" döner:
  (a) hasta defteri okunamazken (`PatientDatabase.get_all_patients` → `except _DB_ERROR: return []`) harita BOŞ kurulur,
      hiçbir kayıt bağlanmaz, işaret KONUR;
  (b) tedavi DB'si yazımı reddederken (disk korkuluğu) `ai_analiz_kimliklerini_doldur` istisnayı yutup sıfır döner, işaret
      (`_set_system_setting`, korkuluksuz) KONUR.
İşaret konduktan sonra taşıma bir daha HİÇ koşmaz → tekil adlı eski analiz kimliğine hiç bağlanmaz; A-62 ile kimlikli
hastanın kartı/şeridi onu kalıcı olarak göstermez. D2.22 kapısının "taşıma DÜŞERSE işaret konmaz" kolu arızayı ÇAĞIRANIN
katında (`ai_analiz_kimliklerini_doldur` fırlatır) kurduğu için bunu göremiyordu.
Arızalar EN ALT katta: (a) hasta DB dosyası İKİNCİ bir SQLite bağlantısıyla gerçekten kilitlenir; (b) gerçek korkuluk
(`_ensure_write_guardrail`), yalnız disk ÖLÇÜMÜ "kritik".
"""

from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server

    kok = tmp_path / "gecmis"
    kok.mkdir()
    d = TreatmentHistoryDB(kok)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)
    monkeypatch.setattr("database.patient_database.get_patient_database", lambda: pdb)
    monkeypatch.setattr(api_server, "_ai_kimlik_tasindi", False)
    try:
        yield api_server, d, pdb, tmp_path
    finally:
        d.close_connections()


def _kimlik(d, ozet: str) -> str:
    with d._get_connection() as c:
        return c.execute(
            "SELECT COALESCE(patient_uuid,'') FROM ai_analyses WHERE result_summary = ?", (ozet,)
        ).fetchone()[0]


def _isaret(d):
    return d._get_system_setting("ai_hasta_kimlik_tasimasi_yapildi")


def test_KRITIK_C2_1_2_hasta_defteri_KILITLIYKEN_isaret_konmaz_sonraki_acilista_baglanir(o):
    api, d, pdb, tmp = o
    pamuk = pdb.add_patient({"name": "Pamuk", "species": "Kedi"})
    d.add_ai_analysis(module_id="landmark", patient_name="Pamuk", result_summary="ESKI-PAMUK")
    pdb._reset_thread_conn()  # bu iş parçacığının boşta bağlantısı kapanır; okuyucu kilit SÜRERKEN yeniden açar
    kc = sqlite3.connect(str(tmp / "patients.db"), isolation_level=None, timeout=5)
    kilitli = False
    try:
        kc.execute("PRAGMA locking_mode=EXCLUSIVE")
        kc.execute("BEGIN EXCLUSIVE")
        kc.execute("UPDATE patients SET name = name")
        kilitli = True
        api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    finally:
        if kilitli:
            kc.execute("ROLLBACK")
        kc.close()
    assert kilitli, "aparat: hasta DB'si kilitlenemedi"
    assert _kimlik(d, "ESKI-PAMUK") == "", "ön koşul: kilitliyken taşıma bağlayamamalı"
    api._ai_kimlik_tasindi = False  # yeniden açılış (DB aynı)
    pdb._reset_thread_conn()
    api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    assert _kimlik(d, "ESKI-PAMUK") == pamuk, (
        f"hasta defteri okunamazken taşıma 'yapıldı' işaretlendi (işaret={_isaret(d)!r}); tekil adlı eski analiz "
        "bir daha hiç bağlanmıyor"
    )


def test_KRITIK_C2_1_2_disk_korkulugu_reddederken_isaret_konmaz_sonraki_acilista_baglanir(o, monkeypatch):
    api, d, pdb, _tmp = o
    pamuk = pdb.add_patient({"name": "Pamuk", "species": "Kedi"})
    d.add_ai_analysis(module_id="landmark", patient_name="Pamuk", result_summary="ESKI-PAMUK")
    with monkeypatch.context() as m:
        m.setattr(
            type(d), "get_disk_space_status", lambda self: {"critical": True, "free_mb": 120, "threshold_mb": 500}
        )
        api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    assert _kimlik(d, "ESKI-PAMUK") == "", "ön koşul: korkuluk yazımı reddetmeli"
    api._ai_kimlik_tasindi = False
    api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    assert _kimlik(d, "ESKI-PAMUK") == pamuk, (
        f"korkuluk yazımı reddederken taşıma 'yapıldı' işaretlendi (işaret={_isaret(d)!r})"
    )


def test_KARSIT_C2_1_2_bos_hasta_defterinde_de_basarili_tasima_ISARETI_konur(o):
    """Arıza yokken (defter okunabilir; bağlanacak ad yok) işaret konur — D2.22'nin tek seferlik kuralı korunur."""
    api, d, _pdb, _tmp = o
    d.add_ai_analysis(module_id="landmark", patient_name="Yok", result_summary="ESKI-YOK")
    api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    assert _isaret(d) == "1"


def test_KARSIT_C2_1_2_GERCEK_yazma_yolu_tasimayi_TETIKLER_tekil_ad_baglanir(o):
    """Taşımanın TEK tetikleyicisi `POST /api/ai/log` [grep]. A1 k9m3 (tetik kaldırılır) D2.56 + D2.22 + hasta_kimligi'nde 24/24
    YEŞİL kalıyordu — bu kol onu kırmızı yapar."""
    from fastapi.testclient import TestClient

    api, d, pdb, _tmp = o
    pamuk = pdb.add_patient({"name": "Pamuk", "species": "Kedi"})
    d.add_ai_analysis(module_id="landmark", patient_name="Pamuk", result_summary="ESKI-PAMUK")
    r = TestClient(api.app, client=("192.168.1.50", 51099)).post(
        "/api/ai/log", json={"module": "m", "summary": "yeni", "patient_name": "X"}
    )
    assert r.status_code == 200, r.text[:200]
    assert _kimlik(d, "ESKI-PAMUK") == pamuk, "gerçek yazma yolu eski analizin kimlik taşımasını tetiklemedi"
