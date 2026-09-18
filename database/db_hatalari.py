# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SQLCipher + sqlite3 ISTISNA DEMETLERI — TEK KAYNAK (2026-09-18).

⚠️ NEDEN AYRI MODUL: `sqlcipher3` KENDI exception siniflarini firlatir ve `sqlite3`in
except'leri onlari **YAKALAMAZ**. Bu yuzden her yakalama iki tarafi birden kapsamali.
Demetler `patient_database.py` ve `treatment_history_db.py` icinde AYNI ALTI SATIR olarak
KOPYALANMISTI — yani sifreli ve duz-metin yollari ayni anda calissin diye yazilan koruma,
iki yerde ayri ayri bakim istiyordu.

⚠️ BU DEPO BU SINIFI ZATEN YASADI: `goc_sonrasi_yedek_politikasi` da iki dosyaya
kopyalanmisti ve kopyalar UC ayri yerden ayrismisti (bayrak adi · ACL politikasi · log
seviyesi) — hicbiri denetimde gorunmuyordu. Kopyalamanin maliyeti "okumasi zor" degil,
**sessizce ayrisan davranis**. Kendi kopyanizi YAZMAYIN; buradan import edin.

⚠️ NASIL BULUNDU (durustluk kaydi): B4 bolmesinde metotlar karisim modullerine tasinirken
bu adlar geride kaldi ve `thdb_telemetri` / `thdb_outbox` icinde TANIMSIZ oldu. TAM SUIT
BUNU GOREMEDI — cunku ilgili `except` dallari yalnizca gercek bir DB hatasinda kosar.
Yakalayan sey `ruff` (F821) oldu. Ders: "testler yesil" bir except dalinin dogru oldugunu
KANITLAMAZ; statik denetim ayri bir agdir.

Kullanim:
    from database.db_hatalari import _DB_ERROR, _DB_INTEGRITY, _DB_OPERATIONAL
"""

from __future__ import annotations

import sqlite3

from database.sqlcipher_util import import_sqlcipher

# ⚠️ IKI KOPYA ZATEN AYRISMISTI (olculdu 2026-09-18, birlestirme sirasinda):
#   patient_database.py      -> `import_sqlcipher()` : sqlcipher3 VE pysqlcipher3 dener
#   treatment_history_db.py  -> `from sqlcipher3 import dbapi2` : YALNIZ sqlcipher3
# Yani yalniz `pysqlcipher3` bulunan bir ortamda hasta DB'si her iki istisna ailesini
# yakalarken tedavi DB'si sqlite3-only demete dusuyordu — sifreli yolda firlayan
# `sqlcipher3.Error` YAKALANMADAN gececekti. Tam olarak A1b'nin sinifi: ayni politikanin
# iki kopyasi sessizce ayrisir. TEK KAYNAK, GUCLU olana gore yazildi.
_sqlcipher_mod = import_sqlcipher()
if _sqlcipher_mod is not None:
    _DB_OPERATIONAL = (sqlite3.OperationalError, _sqlcipher_mod.OperationalError)
    _DB_ERROR = (sqlite3.Error, _sqlcipher_mod.Error)
    _DB_INTEGRITY = (sqlite3.IntegrityError, _sqlcipher_mod.IntegrityError)
else:  # binding yok (duz-metin yol) -> yalniz sqlite3
    _DB_OPERATIONAL = sqlite3.OperationalError
    _DB_ERROR = sqlite3.Error
    _DB_INTEGRITY = sqlite3.IntegrityError

#: ⚠️ `_DB_ERROR` ZATEN bir demet olabilir; `except (_DB_ERROR, RuntimeError)` ic-ice demet
#: uretir ve Python "catching classes that do not inherit from BaseException" der.
#: Duzlestirilmis hali:
_DB_VEYA_RUNTIME = (*_DB_ERROR, RuntimeError) if isinstance(_DB_ERROR, tuple) else (_DB_ERROR, RuntimeError)

__all__ = ["_DB_ERROR", "_DB_INTEGRITY", "_DB_OPERATIONAL", "_DB_VEYA_RUNTIME"]
