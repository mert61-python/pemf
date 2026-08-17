# Author: mertaygn, cglrgrkn
"""Migration rollback'i bayat `-wal`/`-shm` yan-dosyalarını GERÇEKTEN siliyor mu?

DENETİM BULGUSU (2026-08-17). `database/treatment_history_db.py` rollback dalında:

    _side = self.db_path + _sfx        # self.db_path bir Path → TypeError!

`Path + str` Python'da `TypeError: unsupported operand type(s) for +: 'WindowsPath' and 'str'`
verir. İfade `os.remove(_side)`'a HİÇ ulaşmıyordu; çevreleyen `try/except` yalnız
"Rollback: -wal temizlenemedi" uyarısı basıyordu. Yani **koruma ölü koddu.**

Sonuç: geri yüklenen yedeğin yanında bayat `-wal` kalır. Şifreli kurulumda (üretim profili:
`deploy/device.env` → `PEMF_ENCRYPT_AT_REST=1`) her SQLCipher dosyasının page-1'inde kendi rastgele
salt'ı olduğu için WAL çerçeveleri geri yüklenen dosyanın salt'ıyla uyuşmaz → `hmac check failed
for pgno=1` → `file is not a database` → karantina → cihaz **BOŞ tedavi geçmişiyle** açılır.
(Düz-metin profilde sonuç bozulma değil, SESSİZ NO-OP: bayat WAL replay edilir, `integrity_check`
"ok" der ve yarım-migration hâli geri gelir — yani rollback hiç olmamış gibi davranır.)

⚠️ Doğru kardeş desen aynı depoda: `database/auth_db.py` → `Path(str(self.db_path) + _sfx)`.

⚠️ MEVCUT "KORUMA" KÂĞITTAN KAPLANDI: `tests/test_treatment_persistence.py:339` →
`assert '"-wal"' in src and '"-shm"' in src` — bir **kaynak-metin grep'i**; `TypeError`'lı kodu
sorunsuz geçiriyordu. Davranışsal test (`tests/test_kalan_davranissal.py`) ise yalnız GEÇERSİZ-yedek
yolunu zorluyor, o da `raise` ile erken çıktığı için bu satıra hiç varmıyor. Bu dosya o boşluğu
DAVRANIŞSAL olarak kapatır: rollback gerçekten tetiklenir ve diskte `-wal` kalıp kalmadığı ölçülür.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.treatment_history_db import TreatmentHistoryDB  # noqa: E402


def _yan_dosyalar(db_path: Path):
    return [p.name for p in db_path.parent.iterdir() if p.name.startswith(db_path.name) and p.name != db_path.name]


def test_KRITIK_rollback_bayat_WAL_yan_dosyalarini_SILER(tmp_path, monkeypatch):
    """Rollback dalı koşturulur; geri yüklemeden sonra `-wal`/`-shm` diskte KALMAMALI.

    Senaryo, gerçek arıza dizisinin diskteki SONUCUNU birebir kurar:
      1) sağlam bir DB + geçerli ön-yedek var,
      2) `_ensure_schema_version` patlar (disk-dolu / I-O arızası taklidi),
      3) aynı arıza kapanış-checkpoint'ini de düşürmüş → `-wal`/`-shm` geride kalmış.
    Rollback bunları temizleyip yedeği geri koymalı.
    """
    db = TreatmentHistoryDB(tmp_path)
    db_path = Path(db.db_path)

    # Rollback dalına girebilmek için şema sürümünü GERİYE al (aksi halde metot erken döner).
    db._set_system_setting("db_schema_version", "0", "test: rollback dalini sur")
    db.close_connections()

    def _patla(*a, **k):
        raise RuntimeError("disk dolu (taklit)")

    monkeypatch.setattr(db, "_ensure_schema_version", _patla, raising=False)

    # ⚠️ BİLEŞİK ARIZAYI MODELLE — bu test ancak böyle DÜRÜST olur.
    # Kodun kendi yorumu bu temizliğin ne zaman gerektiğini söylüyor: "Son baglanti temiz
    # kapandiginda SQLite bunlari kendi siler; ama kapanis-checkpoint'i de basarisiz olduysa
    # (ayni disk-dolu/I-O arizasi) bayat -wal cerceveleri geri-yuklenen DB'ye REPLAY edilir."
    # Ölçtük: gerçek `close_connections()` yan-dosyaları ZATEN siliyor → yan-dosyaları daha erken
    # yazmak YANLIŞ-YEŞİL veriyordu (birincil mekanizma devreye giriyor ve ölü kod hiç sınanmıyor).
    # Bu yüzden `close_connections`'ı sarıp "kapanış-checkpoint'i başarısız oldu, -wal geride kaldı"
    # durumunu kuruyoruz. Bundan sonra dosyaları silebilecek TEK şey temizlik döngüsüdür.
    _gercek_kapat = db.close_connections

    def _kapat_ama_wal_birak(*a, **k):
        _gercek_kapat(*a, **k)
        (db_path.parent / (db_path.name + "-wal")).write_bytes(b"BAYAT-WAL-CERCEVELERI")
        (db_path.parent / (db_path.name + "-shm")).write_bytes(b"BAYAT-SHM")

    monkeypatch.setattr(db, "close_connections", _kapat_ama_wal_birak, raising=False)

    with pytest.raises(Exception):
        db._run_startup_migrations_with_rollback()

    kalanlar = _yan_dosyalar(db_path)
    assert not kalanlar, (
        f"rollback'ten SONRA bayat yan-dosyalar diskte KALDI: {kalanlar}. "
        "`Path + str` TypeError'a duserse `os.remove` HIC calismaz; sifreli kurulumda bayat WAL "
        "geri-yuklenen dosyanin salt'iyla uyusmaz → 'file is not a database' → karantina → "
        "cihaz BOS tedavi gecmisiyle acilir."
    )
    assert db_path.exists(), "rollback yedegi geri koymadi"


def test_yan_dosya_yolu_Path_ile_birlestirilmez_yapisal_capa():
    """Yapısal çıpa: `self.db_path + "-wal"` deseni GERİ GELMEMELİ.

    Bu, yukarıdaki davranışsal testin YERİNE değil YANINA konur: aynı hata bir gün başka bir yan-dosya
    (`-journal`) için tekrarlanırsa davranışsal test onu kapsamayabilir, ama bu desen görünür kalır.
    Doğru biçim `str(self.db_path) + _sfx` (bkz. `database/auth_db.py`)."""
    import inspect

    ham = inspect.getsource(TreatmentHistoryDB._run_startup_migrations_with_rollback)
    # ⚠️ YORUMLAR ATILIR. Aksi halde bu çıpa, hatayı AÇIKLAYAN bir yorumu (ki düzeltmenin yanında
    # bilerek duruyor) kusurun kendisi sanardı — ve tersi de mümkündü: doğru deseni anlatan bir
    # yorum yazarak kapı geçilebilirdi. Kapı yalnız YÜRÜTÜLEN satırlara bakar.
    src = "\n".join(s for s in ham.splitlines() if not s.strip().startswith("#"))
    assert "self.db_path + " not in src, (
        "`Path + str` deseni geri gelmis → TypeError, yan-dosya temizligi OLU KOD olur. "
        "Dogru bicim: str(self.db_path) + _sfx"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
