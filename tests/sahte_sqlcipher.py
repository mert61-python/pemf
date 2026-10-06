# -*- coding: utf-8 -*-
"""SAHTE SQLCipher BAĞLAYICISI — yalnız düz-metin → SQLCipher GÖÇÜNÜN kullandığı alt küme (D2.08 · B-10.41).

⚠️ NEDEN: Windows CI'da sqlcipher3 yok (A-46). Göç geri-alma, yarım-göç toparlama, geçici kilit ve
"önceki yedek silinmez" davranış kapıları bu yüzden orada ATLANIYORDU; ölçüldü (2026-10-06, 2-A):
sqlcipher3 YOKKEN geri-alma satırı `pass` yapılınca göç kapı kümesi YEŞİL kalıyordu.

⚠️ SAHTE EN ALT KATTA: ürün kodu (`sqlcipher_util.migrate_to_encrypted_if_needed`) BİREBİR koşar —
taşıma, yeniden deneme, geri alma, kenara alma, yedek politikası gerçek. Yalnız bağlayıcı (bağlantı,
`PRAGMA key`, `ATTACH … KEY`, `sqlcipher_export`) sahtedir. Kurulumda `sqlcipher_util.import_sqlcipher`
bu modülü döndürecek biçimde yamanır.

"ŞİFRELİ" DOSYA BİÇİMİ: gerçek SQLite dosyasının ilk 16 baytı (`SQLite format 3\\0`) `SAHTE:` + anahtar
özetinin 10 baytıyla DEĞİŞTİRİLMİŞ kopyası. Gerçek SQLCipher dosyası gibi SQLite başlığı TAŞIMAZ:
`duz_metin_sqlite_mi` False döner, düz `sqlite3` açamaz. Yanlış anahtar ve anahtarlı bağlantıyla düz-metin
dosya "file is not a database" verir (gerçek kitaplıkla aynı ileti → `anahtar_uyusmazligi_mi` aynı çalışır).

Desteklenmeyen bir ifade gelirse `NotImplementedError` — sahte, sessizce yanlış sonuç ÜRETMEZ.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
import tempfile

SQLITE_BASLIK = b"SQLite format 3\x00"
_ONEK = b"SAHTE:"

DatabaseError = sqlite3.DatabaseError
OperationalError = sqlite3.OperationalError
IntegrityError = sqlite3.IntegrityError
Error = sqlite3.Error
Row = sqlite3.Row


def _baslik(anahtar: str) -> bytes:
    return _ONEK + hashlib.sha256(anahtar.encode("utf-8")).digest()[:10]


def sahte_sifreli_mi(yol) -> bool:
    """Dosya bu sahtenin 'şifreli' biçiminde mi?"""
    with open(yol, "rb") as f:
        return f.read(len(_ONEK)) == _ONEK


def _sema_say(yol: str) -> int:
    c = sqlite3.connect(yol)
    try:
        return c.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
    finally:
        c.close()


class _Imlec:
    def __init__(self, satirlar=()):
        self._satirlar = list(satirlar)

    def fetchone(self):
        return self._satirlar[0] if self._satirlar else None

    def fetchall(self):
        return list(self._satirlar)


class Baglanti:
    """Tembel: dosyayı yalnız ifade anında açar ve hemen kapatır (Windows'ta kilit bırakmaz)."""

    def __init__(self, yol, *a, **k):
        self.yol = str(yol)
        self.anahtar = None
        self._ekli = None  # (yol, anahtar)
        self.row_factory = None

    def execute(self, sql, *parametreler):
        s = str(sql).strip()
        m = re.fullmatch(r"PRAGMA\s+key\s*=\s*'(.*)'", s, re.S)
        if m:
            self.anahtar = m.group(1).replace("''", "'")
            return _Imlec()
        m = re.fullmatch(r"ATTACH\s+DATABASE\s+'(.*)'\s+AS\s+(\w+)\s+KEY\s+'(.*)'", s, re.S)
        if m:
            self._ekli = (m.group(1).replace("''", "'"), m.group(3).replace("''", "'"))
            return _Imlec()
        if re.fullmatch(r"SELECT\s+sqlcipher_export\('(\w+)'\)", s):
            self._disa_aktar()
            return _Imlec()
        if re.match(r"DETACH\s+DATABASE\s", s):
            self._ekli = None
            return _Imlec()
        if re.fullmatch(r"SELECT\s+count\(\*\)\s+FROM\s+sqlite_master", s):
            return _Imlec([(self._sema_sayisi(),)])
        raise NotImplementedError(f"sahte sqlcipher: desteklenmeyen ifade: {s!r}")

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def _sema_sayisi(self) -> int:
        with open(self.yol, "rb") as f:
            bas = f.read(len(SQLITE_BASLIK))
        if bas.startswith(_ONEK):
            if self.anahtar is None or bas != _baslik(self.anahtar):
                raise DatabaseError("file is not a database")
            with open(self.yol, "rb") as f:
                veri = f.read()
            fd, gecici = tempfile.mkstemp(suffix=".sahte-ham.db")
            with os.fdopen(fd, "wb") as f:
                f.write(SQLITE_BASLIK + veri[len(SQLITE_BASLIK) :])
            try:
                return _sema_say(gecici)
            finally:
                os.remove(gecici)
        if self.anahtar is not None:
            # Gerçek SQLCipher: anahtar verilmiş bağlantı DÜZ-METİN dosyayı çözemez.
            raise DatabaseError("file is not a database")
        return _sema_say(self.yol)

    def _disa_aktar(self) -> None:
        if self._ekli is None:
            raise OperationalError("sahte sqlcipher: sqlcipher_export eklenmis DB olmadan cagrildi")
        if self.anahtar is not None or sahte_sifreli_mi(self.yol):
            raise NotImplementedError("sahte sqlcipher: yalniz DUZ-METIN kaynaktan disa aktarim desteklenir")
        hedef, anahtar = self._ekli
        fd, gecici = tempfile.mkstemp(suffix=".sahte-yedek.db")
        os.close(fd)
        try:
            kaynak = sqlite3.connect(self.yol)
            kopya = sqlite3.connect(gecici)
            try:
                kaynak.backup(kopya)
            finally:
                kopya.close()
                kaynak.close()
            with open(gecici, "rb") as f:
                veri = f.read()
        finally:
            os.remove(gecici)
        if not veri.startswith(SQLITE_BASLIK):
            raise OperationalError("sahte sqlcipher: kaynak SQLite yedegi beklenmedik bicimde")
        with open(hedef, "wb") as f:
            f.write(_baslik(anahtar) + veri[len(SQLITE_BASLIK) :])


def connect(yol, *a, **k):
    return Baglanti(yol, *a, **k)


#: Göç davranış kapılarının parametreleri — `@pytest.fixture(params=BAGLAYICILAR)`.
BAGLAYICILAR = ("sahte", "gercek")


def baglayici_kur(kip: str, monkeypatch):
    """Parametreli `baglayici` fikstürlerinin ORTAK gövdesi.

    · `sahte`  → `sqlcipher_util.import_sqlcipher` bu modülü döndürür (sqlcipher3'süz koşar).
    · `gercek` → kurulu sqlcipher3; yoksa ATLANIR (neden "sqlcipher3" içerir → A-46 / D2.07 CI adımı sayar).
    """
    import pytest
    from database import sqlcipher_util as su

    if kip == "gercek":
        gercek = su.import_sqlcipher()
        if gercek is None:
            pytest.skip("sqlcipher3 yok — gercek baglayici kolu (sahte kol yine kosar)")
        return gercek
    modul = sys.modules[__name__]
    monkeypatch.setattr(su, "import_sqlcipher", lambda: modul)
    return modul
