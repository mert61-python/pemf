# -*- coding: utf-8 -*-
"""D2.04 (B-3.105) — ANAHTAR YOKKEN ŞİFRELİ DB KARANTİNAYA ALINMAZ (hasta + tedavi ikizi).

KORUNAN KOŞUL. `patient_database._init_database` açılış hatasında dosyayı yalnız
`self.at_rest_encrypted and anahtar_uyusmazligi_mi(e)` ise kenara alır (D2.46'dan beri: anahtarın varlığı değil, ŞİFRELİ
BAĞLANTININ açılmış olması; bu dosya yazıldığında koşul `self._cipher_key and …` idi); tedavi ikizi
(`treatment_history_db._init_database`) aynı kuralı birincil anahtarın gerçek uyuşmazlığı (`_anahtar_vardi_ama_acmadi`,
D2.45) ya da `_cipher_key_cache` ile uygular. Anahtar
HİÇ okunamadıysa (bayrak ≠ 1, kaynak boş) şifreli dosya düz sqlite3 ile açılmaya çalışılır ve
"file is not a database" verir — bu bir anahtar UYUŞMAZLIĞI DEĞİLDİR: doğru anahtar sonradan
gelirse veri tam olarak kurtarılabilir. Koşul düşerse kurtarılabilir şifreli hasta DB'si
`.acilamadi-*` altına itilir ve yerine BOŞ, DÜZ-METİN bir DB kurulur (sessiz veri kaybı + PII
düz-metin yazılmaya başlar).

KÖRLÜK ÖLÇÜMÜ (2026-10-06, 2-A). Koşuldan `self._cipher_key and` silinince (plan mutantı) ya da
anahtar yerine binding (`self._sqlcipher_mod`) sınanınca ya da tedavi ikizinde `_cipher_key_cache
and` silinince: 97a24ff'te karantina kapı kümesi (7 dosya, 70 test) üç mutantta da YEŞİLDİ.
8bec382 (D1.37) bunu DOLAYLI kapattı: alt süreçte gerçek `main()` koşan
`test_acilis_DB_acilamasa_ACIL_DURDUR_yasar.py::test_KRITIK_GENEL_bozuk_DB_RuntimeError_de_backendi_OLDURMEZ`
(~96 sn'lik küme) bozuk-dosya senaryosunda dosyanın dokunulmadığını iddia ediyor. Bu dosya koşulu
DOĞRUDAN, saniyeler içinde ve sqlcipher3'süz de (rastgele bayt = SQLCipher'ın dışarıdan görünüşü)
sınar; sqlcipher3 varsa gerçek şifreli DB'nin doğru anahtarla hâlâ AÇILDIĞINI da gösterir.

KARŞIT (gerçek uyuşmazlıkta karantina SÜRER): test_anahtar_uyusmazligi_karantina.py ::
test_KRITIK_ESKI_anahtarli_DB_backendi_OLDURMEZ (hasta) ve
::test_KRITIK_TEDAVI_GECMISI_eski_anahtarda_backendi_OLDURMEZ (tedavi).
"""

from __future__ import annotations

import hashlib
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DOGRU_ANAHTAR = "D204-dogru-anahtar"


def _sha(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _sifreli_gibi_yaz(yol: Path, kip: str) -> None:
    """`rastgele`: SQLite başlığı olmayan sabit tohumlu baytlar (SQLCipher dosyası dışarıdan böyle görünür;
    sqlcipher3 GEREKTİRMEZ). `sqlcipher`: doğru anahtarla GERÇEK SQLCipher DB (içinde veri)."""
    if kip == "rastgele":
        yol.write_bytes(random.Random(204).randbytes(4096 * 3))
        return
    from database.sqlcipher_util import import_sqlcipher

    sqlcipher = import_sqlcipher()
    if sqlcipher is None:
        pytest.skip("sqlcipher3 yok — gercek SQLCipher kolu kurulamaz (rastgele kol yine kosar; A-46: CI'da sayilir)")
    c = sqlcipher.connect(str(yol))
    c.execute(f"PRAGMA key='{_DOGRU_ANAHTAR}'")
    c.execute("CREATE TABLE kayit (ad TEXT)")
    c.execute("INSERT INTO kayit VALUES ('KurtarilabilirHasta')")
    c.commit()
    c.close()


def _dogru_anahtarla_hala_acilir(yol: Path) -> None:
    from database.sqlcipher_util import import_sqlcipher, open_encrypted_conn

    c = open_encrypted_conn(yol, _DOGRU_ANAHTAR, import_sqlcipher())
    try:
        assert c.execute("SELECT ad FROM kayit").fetchone()[0] == "KurtarilabilirHasta"
    finally:
        c.close()


@pytest.fixture
def anahtarsiz(tmp_path, monkeypatch):
    """Bayrak ≠ 1 ve anahtar kaynağı BOŞ: şifreleme istenmemiş, anahtar bu makinede okunamıyor."""
    kok = tmp_path / "PEMF_GUI"
    kok.mkdir(parents=True)
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.delenv("PEMF_SQLCIPHER_KEY", raising=False)
    from database import sqlcipher_util as su

    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    return kok


def _karantina(kok: Path) -> list[str]:
    return sorted(p.name for p in kok.iterdir() if ".acilamadi-" in p.name)


@pytest.mark.parametrize("kip", ["rastgele", "sqlcipher"])
def test_KRITIK_hasta_DB_anahtar_YOKKEN_sifreli_dosyayi_KARANTINAYA_ALMAZ(anahtarsiz, monkeypatch, kip):
    """MUTASYON (D2.46 sonrası koşul; 2-A inceleme A2-9.2'de ölçüldü): `patient_database.py`
    `if not (self.at_rest_encrypted and anahtar_uyusmazligi_mi(e))` → `if not anahtar_uyusmazligi_mi(e)` → KIRMIZI
    (iki kol; sqlcipher3 YOKKEN rastgele kol). Eski plan mutantı (`self._cipher_key and` silinir) koşul değiştiği için
    artık UYGULANAMAZ."""
    from database import patient_database as pdb

    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    db = anahtarsiz / "patients.db"
    _sifreli_gibi_yaz(db, kip)
    once = _sha(db)

    with pytest.raises(RuntimeError):
        pdb.PatientDatabase(str(db))

    assert _karantina(anahtarsiz) == [], (
        f"ANAHTAR OKUNAMAZKEN sifreli hasta DB'si KARANTINAYA alindi: {_karantina(anahtarsiz)} -> dogru anahtar "
        "sonradan gelse bile veri yerinde degil, yerine BOS duz-metin DB kuruldu"
    )
    assert db.exists() and _sha(db) == once, "sifreli hasta DB'sine DOKUNULDU (tasindi ya da degisti)"
    if kip == "sqlcipher":
        _dogru_anahtarla_hala_acilir(db)


@pytest.mark.parametrize("kip", ["rastgele", "sqlcipher"])
def test_KRITIK_tedavi_DB_anahtar_YOKKEN_sifreli_dosyayi_KARANTINAYA_ALMAZ(anahtarsiz, kip):
    """Tedavi ikizi. MUTASYON: `treatment_history_db._init_database` içinde
    `getattr(self, "_cipher_key_cache", None) and` silinir → KIRMIZI."""
    from database import treatment_history_db as thdb

    db = anahtarsiz / "pemf_treatment_history.db"
    _sifreli_gibi_yaz(db, kip)
    once = _sha(db)

    with pytest.raises(Exception):
        thdb.TreatmentHistoryDB(anahtarsiz)

    assert _karantina(anahtarsiz) == [], (
        f"ANAHTAR OKUNAMAZKEN sifreli tedavi DB'si KARANTINAYA alindi: {_karantina(anahtarsiz)} -> seans gecmisi "
        "yerinde degil, yeni seanslar BOS DB'ye yazilir"
    )
    assert db.exists() and _sha(db) == once, "sifreli tedavi DB'sine DOKUNULDU (tasindi ya da degisti)"
    if kip == "sqlcipher":
        _dogru_anahtarla_hala_acilir(db)
