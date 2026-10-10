# -*- coding: utf-8 -*-
"""F2-2.6 (2-F incelemesi A2) — Y121'in "okunamayan işaret = bekliyor" sözleşmesi (patient_database.vacuum_bekliyor_mu) ÖLÇÜLÜYOR.

ÖLÇÜLEN KÖRLÜK: `vacuum_bekliyor_mu` okuma hatasında True döner (emin değilsek yeniden dene — VACUUM zararsız). Bu dalı `return False`'a çeviren
mutant Y121 kapısında (5 test) ve D2.29 kapısında YEŞİL — sözleşme hiçbir testte koşmuyor. Mutantta işaret tablosu okunamazken (bozuk/eksik
`bakim_durumu`, kilit) düşmüş VACUUM'un kalıntısı günlük bakımda hiç denenmez.
Arıza EN ALT katta, GERÇEK SQLite hatası: `bakim_durumu` tablosu yok ("no such table" — eski şema / yarım göç); okuma `OperationalError`.
"""

from __future__ import annotations

from pathlib import Path


def _bayt(yol, belirtecler) -> int:
    p = Path(yol)
    b = b"".join(f.read_bytes() for f in (p, p.with_name(p.name + "-wal")) if f.exists())
    return sum(1 for t in belirtecler if t.encode() in b)


def test_KRITIK_isaret_tablosu_OKUNAMAZKEN_bekliyor_sayilir_ve_bakim_VACUUMU_kalintiyi_temizler(tmp_path):
    from database.patient_database import PatientDatabase

    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    for i in range(3):
        pdb.add_patient({"name": f"Okunamayan F226 {i}", "owner": "Sahip"})
    with pdb._get_connection() as c:
        saklanan = [r[0] for r in c.execute("SELECT name FROM patients").fetchall()]
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.execute("PRAGMA secure_delete=OFF")  # yalnız VACUUM + denetim noktası ölçülsün (Y121 kapısıyla aynı)
        c.execute("DELETE FROM patient_search_index")
        c.execute("DELETE FROM patients")
        c.execute("DROP TABLE bakim_durumu")  # işaret OKUNAMAZ (gerçek "no such table")
        c.commit()
    assert _bayt(pdb.db_file, saklanan) == 3, "aparat KÖR"
    assert pdb.vacuum_bekliyor_mu() is True, "okunamayan VACUUM işareti 'bekliyor' sayılmadı (Y121 sözleşmesi)"
    pdb.bekleyen_vacuum_calistir()
    assert _bayt(pdb.db_file, saklanan) == 0, "okunamayan işaretle bakım VACUUM'u koşmadı — kalıntı duruyor"


def test_KARSIT_okunabilir_isaret_0_iken_VACUUM_kosmaz(tmp_path):
    from database.patient_database import PatientDatabase

    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    assert pdb.vacuum_bekliyor_mu() is False and pdb.bekleyen_vacuum_calistir() is False
