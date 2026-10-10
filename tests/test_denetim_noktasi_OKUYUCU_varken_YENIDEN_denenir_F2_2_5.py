# -*- coding: utf-8 -*-
"""F2-2.5 (2-F incelemesi A2) — silme / VACUUM sonrası WAL denetim noktası AÇIK OKUYUCU yüzünden tamamlanamazsa kalıntı SESSİZCE kalmaz:
kalıcı "bekliyor" işareti (Y121 / D1.58'in mevcut işareti) yazılır ve günlük bakım YENİDEN dener.

ÖLÇÜLEN (sonda `_inceleme/K2/sonda_okuyucu_varken_denetim_noktasi.py`): ikinci bağlantıda 7 sn süren okuma işlemi varken
- hasta DB `bekleyen_vacuum_calistir` (Y121): True döner, işaret 0 YAZILIR, silinen hastaların saklanan değerleri 3/3 dosyada; okuyucu
  kapandıktan sonra ertesi tur `False` (işaret 0 → denenmez), kalıntı 3/3 SÜRER — "tamamlandı" yalanı;
- tedavi DB tekil AI silme (D2.29) ve "Tümünü sil" (S-F.3): kalıntı 1/1 ve 3/3; okuyucu kapandıktan sonra `bekleyen_vacuum_calistir` False,
  +50 yazımda kalıntı sürer. Denetim noktası yalnız WARNING; yeniden deneme / kalıcı işaret YOK.
Arıza GERÇEK: ikinci sqlite3 bağlantısında `BEGIN` + `SELECT` (okuma işlemi açık) — LAN liste okuması / dışa aktarma / yedek / bütünlük
denetimi gibi uzun okuyucunun benzetimi.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

OKUMA_SN = 6.5  # busy_timeout (5 sn) üstü


def _bayt(yol, belirtecler) -> int:
    p = Path(yol)
    b = b"".join(f.read_bytes() for f in (p, p.with_name(p.name + "-wal")) if f.exists())
    return sum(1 for t in belirtecler if t.encode() in b)


class _Okuyucu:
    def __init__(self, yol, tablo):
        self.yol, self.tablo = str(yol), tablo
        self.hazir = threading.Event()
        self.th = threading.Thread(target=self._kos, daemon=True)

    def _kos(self):
        c = sqlite3.connect(self.yol, isolation_level=None)
        try:
            c.execute("BEGIN")
            c.execute(f"SELECT COUNT(*) FROM {self.tablo}").fetchone()
            self.hazir.set()
            time.sleep(OKUMA_SN)
            c.execute("COMMIT")
        finally:
            c.close()

    def __enter__(self):
        self.th.start()
        assert self.hazir.wait(5), "aparat: okuyucu açılamadı"
        return self

    def __exit__(self, *a):
        self.th.join(OKUMA_SN + 5)


@pytest.fixture
def tdb(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def test_KRITIK_hasta_DB_bekleyen_VACUUM_okuyucu_varken_isaret_KALIR_sonra_kalinti_GIDER(tmp_path):
    from database.patient_database import PatientDatabase

    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    for i in range(3):
        pdb.add_patient({"name": f"Okuyucu F225 {i}", "owner": "Sahip"})
    with pdb._get_connection() as c:
        saklanan = [r[0] for r in c.execute("SELECT name FROM patients").fetchall()]
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.execute("PRAGMA secure_delete=OFF")  # yalnız VACUUM + denetim noktası ölçülsün (Y121 kapısıyla aynı)
        c.execute("DELETE FROM patient_search_index")
        c.execute("DELETE FROM patients")
        c.commit()
    pdb._vacuum_isaretini_yaz("1")  # Y121: düşen VACUUM'un kalıcı işareti
    assert _bayt(pdb.db_file, saklanan) == 3, "aparat KÖR"
    with _Okuyucu(pdb.db_file, "patients"):
        pdb.bekleyen_vacuum_calistir()
        assert _bayt(pdb.db_file, saklanan) == 3, "aparat: okuyucu denetim noktasını engellemedi"
        assert pdb.vacuum_bekliyor_mu() is True, (
            "denetim noktası okuyucu yüzünden TAMAMLANAMADI, silinen değerler dosyada — ama işaret 0 yazıldı ('tamamlandı' yalanı)"
        )
    pdb.bekleyen_vacuum_calistir()  # günlük bakımın ertesi turu
    assert _bayt(pdb.db_file, saklanan) == 0, "okuyucu kapandıktan sonraki tur kalıntıyı temizlemedi"
    assert pdb.vacuum_bekliyor_mu() is False


def test_KRITIK_hasta_tekil_silme_okuyucu_varken_isaret_YAZILIR_bakim_kalintiyi_TEMIZLER(tmp_path):
    """D2.29 hasta silmesi: denetim noktası okuyucu yüzünden düşerse kalıcı işaret → günlük bakımın bekleyen VACUUM'u temizler."""
    from database.patient_database import PatientDatabase

    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    pid = pdb.add_patient({"name": "Okuyucu Tekil F225", "owner": "Sahip"})
    with pdb._get_connection() as c:
        saklanan = [r[0] for r in c.execute("SELECT name FROM patients").fetchall()]
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert _bayt(pdb.db_file, saklanan) == 1, "aparat KÖR"
    with _Okuyucu(pdb.db_file, "patients"):
        assert pdb.delete_patient(pid)
        assert _bayt(pdb.db_file, saklanan) == 1, "aparat: okuyucu denetim noktasını engellemedi"
    assert pdb.vacuum_bekliyor_mu() is True, "hasta silmesinin denetim noktası düştü ama kalıcı işaret YOK"
    pdb.bekleyen_vacuum_calistir()
    assert _bayt(pdb.db_file, saklanan) == 0 and pdb.vacuum_bekliyor_mu() is False


@pytest.mark.parametrize("yol", ["tekil_D229", "toplu_SF3"])
def test_KRITIK_tedavi_DB_AI_silme_okuyucu_varken_kalinti_GUNLUK_bakimda_GIDER(tdb, yol):
    belirtecler = [f"OKUYUCU-F225-{yol}-{i}" for i in range(3 if yol == "toplu_SF3" else 1)]
    kimlikler = [
        tdb.add_ai_analysis(module_id="m", patient_name="P", result_summary=f"{t} " + "x" * 200) for t in belirtecler
    ]
    with tdb._get_connection() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert _bayt(tdb.db_path, belirtecler) == len(belirtecler), "aparat KÖR"
    with _Okuyucu(tdb.db_path, "ai_analyses"):
        if yol == "tekil_D229":
            assert tdb.delete_ai_analysis(kimlikler[0])
        else:
            assert tdb.clear_ai_analyses(None) == 3
        assert _bayt(tdb.db_path, belirtecler) > 0, "aparat: okuyucu denetim noktasını engellemedi"
    # günlük bakım turu (seans yokken) — `_daily_maintenance_loop` bunu çağırır
    tdb.bekleyen_vacuum_calistir()
    assert _bayt(tdb.db_path, belirtecler) == 0, (
        f"{yol}: denetim noktası okuyucu yüzünden düştü, kalıntı günlük bakımda da GİTMEDİ (yeniden deneme / kalıcı işaret yok)"
    )


def test_KRITIK_tedavi_DB_ertelenmis_VACUUM_okuyucu_varken_isaret_KALIR(tdb):
    """D1.58 / S-F.3: seans sürerken ertelenen VACUUM bakımda okuyucuya denk gelirse işaret 0 yazılmaz; sonraki tur temizler."""
    b = [f"OKUYUCU-F225-ERTELE-{i}" for i in range(3)]
    for t in b:
        tdb.add_ai_analysis(module_id="m", patient_name="P", result_summary=f"{t} " + "x" * 200)
    with tdb._get_connection() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert tdb.clear_ai_analyses(None, vacuum_ertele=True) == 3 and tdb.vacuum_bekliyor_mu() is True
    with _Okuyucu(tdb.db_path, "ai_analyses"):
        tdb.bekleyen_vacuum_calistir()
        assert _bayt(tdb.db_path, b) > 0, "aparat: okuyucu denetim noktasını engellemedi"
        assert tdb.vacuum_bekliyor_mu() is True, (
            "ertelenmiş VACUUM'un denetim noktası düştü, kalıntı duruyor — ama işaret 0 yazıldı"
        )
    tdb.bekleyen_vacuum_calistir()
    assert _bayt(tdb.db_path, b) == 0 and tdb.vacuum_bekliyor_mu() is False


def test_KARSIT_okuyucusuz_silme_ZATEN_kalintisiz_ve_isaret_YOK(tdb):
    aid = tdb.add_ai_analysis(module_id="m", patient_name="P", result_summary="OKUYUCUSUZ-F225 " + "x" * 200)
    with tdb._get_connection() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert tdb.delete_ai_analysis(aid)
    assert _bayt(tdb.db_path, ["OKUYUCUSUZ-F225"]) == 0
    assert tdb.vacuum_bekliyor_mu() is False, "okuyucusuz başarılı silmede gereksiz VACUUM işareti"
