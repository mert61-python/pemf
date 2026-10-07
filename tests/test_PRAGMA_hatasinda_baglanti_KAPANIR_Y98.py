# -*- coding: utf-8 -*-
"""Y98 (2-A O-2A.2) — PRAGMA hatasında açılan DÜZ bağlantı KAPATILIR.

ÖLÇÜLEN KUSUR (2-A, D2.45/D2.46 önce kayıtları): hasta `_get_connection` ve tedavi `_create_connection` düz `sqlite3`
bağlantısını açıp PRAGMA'ları uyguluyor; dosya SQLite değilse (şifreli DB + binding yok / anahtar yok, bozuk dosya)
ilk okuyan PRAGMA "file is not a database" (`sqlite3.DatabaseError`, OperationalError DEĞİL) ile düşüyor ve bağlantı
KAPATILMIYOR. Bağlantı istisnanın izindeki çerçevede yaşar; istisnayı tutan her şey (günlük kaydı, yakalayıcı, zincir)
dosya tutamağını da tutar → Windows'ta karantina/göç taşıması `WinError 32` ile 24 deneme (~6 sn) bekledi.

SAHİP KARARI Y98: PRAGMA hatasında açılan düz bağlantı kapatılır.

Sahte EN ALT katta: `sqlite3.connect` casusu yalnız açılan bağlantıları KAYDEDER (davranış gerçek); Windows kolu
casussuz — istisna tutulurken dosya GERÇEKTEN yeniden adlandırılabiliyor mu.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

_WIN = os.name == "nt"
K = "Y98-anahtar"


def _sifreli_gibi(yol: Path) -> Path:
    """SQLite başlığı taşımayan dosya: düz bağlantının ilk okuyan PRAGMA'sı 'file is not a database' verir."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(b"\xab" * 8192)
    return yol


@pytest.fixture
def casus(monkeypatch):
    """`sqlite3.connect` ile açılan HER bağlantıyı (yol, bağlantı) kaydeder; davranışı değiştirmez."""
    gercek = sqlite3.connect
    acilan = []

    def _connect(yol, *a, **k):
        c = gercek(yol, *a, **k)
        acilan.append((str(yol), c))
        return c

    monkeypatch.setattr(sqlite3, "connect", _connect)
    return acilan


def _acik_mi(c) -> bool:
    try:
        c.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return False  # "Cannot operate on a closed database."
    except sqlite3.DatabaseError:
        return True  # açık ama dosya SQLite değil
    return True


def _hasta_kur(monkeypatch, yol: Path):
    """B-3.48 yolu: anahtar VAR, sqlcipher3 binding YOK, bayrak 0 → düz bağlantı şifreli dosyayı açamaz."""
    from database import patient_database as pdb

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "0")
    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: K)
    return lambda: pdb.PatientDatabase(str(yol))


def _tedavi_kur(monkeypatch, app: Path):
    """Şifresiz kurulum (bayrak 0, anahtar yok) ama dosya SQLite değil → düz bağlantının journal_mode'u düşer."""
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    return lambda: thdb.TreatmentHistoryDB(app)


def test_KRITIK_hasta_DB_PRAGMA_hatasinda_duz_baglanti_KAPANIR(tmp_path, monkeypatch, casus):
    """MUTASYON: hasta `_get_connection`daki kapatmayı kaldırmak → KIRMIZI."""
    yol = _sifreli_gibi(tmp_path / "PEMF_GUI" / "patients.db")
    ac = _hasta_kur(monkeypatch, yol)
    with pytest.raises(RuntimeError, match="file is not a database") as ei:
        ac()
    bu_dosya = [c for y, c in casus if Path(y) == yol]
    assert bu_dosya, "ön koşul: düz bağlantı açılmalıydı"
    acik = [c for c in bu_dosya if _acik_mi(c)]
    assert not acik, f"PRAGMA hatasından sonra {len(acik)}/{len(bu_dosya)} düz bağlantı AÇIK kaldı (Y98)"
    assert ei.value is not None


def test_KRITIK_tedavi_DB_PRAGMA_hatasinda_duz_baglanti_KAPANIR(tmp_path, monkeypatch, casus):
    """MUTASYON: tedavi `_create_connection`daki kapatmayı kaldırmak ya da yalnız OperationalError'ı yakalamak → KIRMIZI
    ("file is not a database" `DatabaseError`'dır)."""
    app = tmp_path / "PEMF_GUI"
    yol = _sifreli_gibi(app / "pemf_treatment_history.db")
    ac = _tedavi_kur(monkeypatch, app)
    with pytest.raises(sqlite3.DatabaseError, match="file is not a database"):
        ac()
    bu_dosya = [c for y, c in casus if Path(y) == yol]
    assert bu_dosya, "ön koşul: düz bağlantı açılmalıydı"
    acik = [c for c in bu_dosya if _acik_mi(c)]
    assert not acik, f"PRAGMA hatasından sonra {len(acik)}/{len(bu_dosya)} düz bağlantı AÇIK kaldı (Y98)"


@pytest.mark.skipif(not _WIN, reason="acik tutamagin yeniden adlandirmayi kilitlemesi Windows'a ozgu")
@pytest.mark.parametrize("hangi", ["hasta", "tedavi"])
def test_KRITIK_istisna_TUTULURKEN_dosya_yeniden_adlandirilabilir(tmp_path, monkeypatch, hangi):
    """Kullanıcının gördüğü etki: hata nesnesi yaşarken (günlük kaydı / zincir) dosya kilitli kalmamalı — karantina ve
    göç taşıması 6 sn beklememeli. HEAD: `WinError 32`."""
    app = tmp_path / "PEMF_GUI"
    if hangi == "hasta":
        yol = _sifreli_gibi(app / "patients.db")
        ac = _hasta_kur(monkeypatch, yol)
    else:
        yol = _sifreli_gibi(app / "pemf_treatment_history.db")
        ac = _tedavi_kur(monkeypatch, app)
    with pytest.raises(Exception, match="file is not a database") as ei:
        ac()
    kenar = yol.with_name(yol.name + ".y98")
    try:
        os.rename(yol, kenar)
    except PermissionError as e:
        pytest.fail(f"PRAGMA hatasından sonra {yol.name} hâlâ AÇIK (istisna yaşıyor): {e}")
    os.rename(kenar, yol)
    assert ei.value is not None  # istisna bu noktaya dek tutuldu


def test_KARSIT_saglam_duz_DB_baglantisi_ACIK_kalir_ve_calisir(tmp_path, monkeypatch, casus):
    """Kapatma YALNIZ hata yolunda: sağlam şifresiz kurulumda havuz bağlantısı açık ve kullanılabilir."""
    app = tmp_path / "PEMF_GUI"
    t = _tedavi_kur(monkeypatch, app)()
    try:
        t.end_session(t.start_session("Y98-saglam"))
        assert len(t.get_session_history(limit=5)) == 1
        acik = [c for y, c in casus if Path(y) == app / "pemf_treatment_history.db" and _acik_mi(c)]
        assert acik, "sağlam kurulumda havuz bağlantısı kapatıldı"
    finally:
        t.close_connections()
