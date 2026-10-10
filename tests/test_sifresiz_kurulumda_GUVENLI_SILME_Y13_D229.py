# -*- coding: utf-8 -*-
"""D2.29 · B-3.91 · SAHİP KARARI Y13 — şifresiz kurulumda tekil silme dosyada KALINTI bırakmaz (SQLite `secure_delete`).

Y13: "Şifresiz kurulumda her kipte GÜVENLİ SİLME (SQLite `secure_delete`). Sahadaki kurulum şifreli; bu şifresiz kurulumlar için."
ÖLÇÜLEN KUSUR: `DELETE` satırı yalnız serbest listeye bırakır; tekil AI kaydı / hasta silmesinden sonra silinen metin haftalık VACUUM'a kadar
(her gün kapatılan makinede hiç) DB dosyasında okunabilir kalıyordu (KVKK silme hakkı). WAL kipinde eski sayfa, denetim noktasına kadar ana
dosyada durur — `secure_delete` tek başına yetmez; silme sonrası denetim noktası (TRUNCATE) da gerekir.
GERÇEK: TreatmentHistoryDB ve PatientDatabase (sentetik, tmp, ŞİFRESİZ — bekçi null keyring), gerçek silme işlevleri; ölçüm ham dosya
baytlarında (`.db` + `-wal`). KARŞIT: belirteç silmeden ÖNCE dosyada VAR (araç kör değil).
"""

from __future__ import annotations

import pytest

ZAMAN_DAMGASI = "KVKKSILINECEKBELIRTEC"


def _baytlar(yol) -> bytes:
    from pathlib import Path

    p = Path(yol)
    toplam = b""
    for ek in ("", "-wal"):
        f = p.with_name(p.name + ek)
        if f.exists():
            toplam += f.read_bytes()
    return toplam


@pytest.fixture
def tdb(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    db = TreatmentHistoryDB(tmp_path / "gecmis")
    assert db.at_rest_encrypted is False, "aparat: bu kapı ŞİFRESİZ kurulumu ölçer"
    try:
        yield db
    finally:
        db.close_connections()


@pytest.fixture
def pdb(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    db = PatientDatabase(str(tmp_path / "patients.db"))
    yield db


def test_KRITIK_Y13_tekil_AI_kaydi_silinince_metni_DOSYADA_kalmaz(tdb):
    """Plan kapısı: benzersiz metinli AI kaydı → `delete_ai_analysis` → `.db` + `-wal` baytlarında metin YOK.
    MUTASYON: `PRAGMA secure_delete=ON` ya da silme sonrası denetim noktası kaldırılır → KIRMIZI."""
    belirtec = ZAMAN_DAMGASI + "AI"
    aid = tdb.add_ai_analysis(mode="vet", module_id="m", result_summary=f"bulgu {belirtec} " + "x" * 200)
    assert aid, "aparat: AI kaydı yazılamadı"
    assert belirtec.encode() in _baytlar(tdb.db_path), "aparat KÖR: belirteç silmeden önce dosyada bulunamadı"
    assert tdb.delete_ai_analysis(aid) is True
    assert belirtec.encode() not in _baytlar(tdb.db_path), (
        "silinen AI kaydının metni şifresiz DB dosyasında OKUNABİLİR kaldı (Y13 / B-3.91)"
    )


def test_KRITIK_Y13_tekil_hasta_silinince_kimligi_DOSYADA_kalmaz(pdb):
    """Hasta DB'si (DB dosyası şifresiz): hasta alanları cihaz anahtarıyla alan düzeyinde şifreli saklanır — düz ad dosyada hiç yoktur
    (ölçüldü), ama satırın SAKLANAN değeri (şifreli metin) silmeden sonra dosyada kalırsa aynı cihazın anahtarıyla ÇÖZÜLÜR. Ölçüt: hastanın
    saklanan ad / sahip / e-posta değerleri `delete_patient` sonrası `.db` + `-wal` baytlarında YOK."""
    belirtec = ZAMAN_DAMGASI + "HASTA"
    pid = pdb.add_patient(
        {"name": belirtec, "owner": "Sahip " + belirtec, "owner_email": "e@" + belirtec.lower() + ".com"}
    )
    with pdb._get_connection() as c:
        saklanan = [
            v for v in c.execute("SELECT name, owner, owner_email FROM patients WHERE id=?", (pid,)).fetchone() if v
        ]
    assert saklanan and all(str(v).encode() in _baytlar(pdb.db_file) for v in saklanan), (
        "aparat KÖR: hastanın saklanan değerleri silmeden önce dosyada bulunamadı"
    )
    assert pdb.delete_patient(pid) is True
    kalan = [v for v in saklanan if str(v).encode() in _baytlar(pdb.db_file)]
    assert not kalan, f"silinen hastanın saklanan kimlik değerleri ({len(kalan)}) hasta DB dosyasında KALDI (Y13)"


def test_KRITIK_Y13_her_baglanti_secure_delete_ACIK(tdb, pdb):
    """İki DB'nin havuz bağlantısı `secure_delete=1` (yalnız silme işlevinde değil — toplu/temizlik yolları da aynı bağlantıyı kullanır)."""
    with tdb._get_connection() as c:
        assert c.execute("PRAGMA secure_delete").fetchone()[0] == 1, "tedavi DB bağlantısında secure_delete kapalı"
    with pdb._get_connection() as c:
        assert c.execute("PRAGMA secure_delete").fetchone()[0] == 1, "hasta DB bağlantısında secure_delete kapalı"


def test_KARSIT_silinmeyen_kayit_DOSYADA_kalir(tdb):
    """Araç kör değil ve aşırı silme yok: silinmeyen kardeş kaydın metni dosyada kalır."""
    sil = tdb.add_ai_analysis(mode="vet", module_id="m", result_summary=f"bulgu {ZAMAN_DAMGASI}SIL")
    kal = tdb.add_ai_analysis(mode="vet", module_id="m", result_summary=f"bulgu {ZAMAN_DAMGASI}KAL")
    assert tdb.delete_ai_analysis(sil) is True
    b = _baytlar(tdb.db_path)
    assert (ZAMAN_DAMGASI + "KAL").encode() in b and kal
    assert (ZAMAN_DAMGASI + "SIL").encode() not in b


def test_KRITIK_Y13_toplu_hasta_silmesi_de_kimligi_DOSYADA_birakmaz(pdb):
    """`delete_patients_bulk` (Hastalar → seçili sil) aynı ölçüt."""
    kimlikler, saklanan = [], []
    for i in range(3):
        b = f"{ZAMAN_DAMGASI}TOPLU{i}"
        pid = pdb.add_patient({"name": b, "owner": "Sahip " + b})
        kimlikler.append(pid)
        with pdb._get_connection() as c:
            saklanan += [v for v in c.execute("SELECT name, owner FROM patients WHERE id=?", (pid,)).fetchone() if v]
    assert all(str(v).encode() in _baytlar(pdb.db_file) for v in saklanan), "aparat KÖR"
    assert pdb.delete_patients_bulk(kimlikler) == 3
    kalan = [v for v in saklanan if str(v).encode() in _baytlar(pdb.db_file)]
    assert not kalan, f"toplu silinen hastaların saklanan değerleri ({len(kalan)}) dosyada KALDI (Y13)"
