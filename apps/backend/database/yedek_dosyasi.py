# -*- coding: utf-8 -*-
"""Yedek DOSYASININ kendisi — tedavi ve hasta DB'sinin `create_backup`ı ve bakım döngüsünün rotasyonu/tazeliği için TEK kaynak (2-D).

⚠️ D2.61 (B-3.70): başarısız bir yedek denemesi hedefte 0 baytlık (ya da yarım) dosya BIRAKIYORDU — iki DB'de de. SQLite yedek
API'si hata verince yazdığını geri alır ama hedef dosya zaten oluşmuştur [ÖLÇTÜM 2-D sondası: disk dolu → 0 B; şifreli kaynak →
düz hedef `TypeError` → 0 B]. Bu artık, rotasyonda sağlam bir yedeğin yuvasını alır ve "son yedek ne zaman" denetimini kandırır.

⚠️ D2.63 (B-3.20): yedek SON ADA doğrudan yazılmaz. Önce `<ad>.yazim.tmp`ye yazılır (rotasyon deseni `*.db` ile EŞLEŞMEZ), açılarak
doğrulanır (`PRAGMA quick_check`), ancak sonra `os.replace` ile son ada taşınır. Yazım ortasında süreç ölürse son adda yarım dosya
kalmaz; doğrulama düşerse son ad hiç oluşmaz. Rotasyon / tazelik de yalnız `yedek_acilir_mi` olan dosyaları sayar.
Kapılar: tests/test_at_rest_bayragi_ve_yarim_yedek_D261.py · tests/test_yerel_yedek_penceresi_KORUNUR_D263.py
"""

from __future__ import annotations

import logging
import os
import sqlite3

_log = logging.getLogger(__name__)

#: Yazım sırasındaki geçici ad eki — `pemf_*_*.db` rotasyon desenine UYMAZ (yarım dosya hiçbir zaman "yedek" sayılmaz).
GECICI_EK = ".yazim.tmp"
_SQLITE_BASLIK = b"SQLite format 3\x00"


def gecici_yol(yol: str) -> str:
    return f"{yol}{GECICI_EK}"


def basarisiz_yedegi_kaldir(yol: str, logger) -> None:
    """Başarısız yedek denemesinin bıraktığı dosyayı (ve `-journal` / `-wal` / `-shm` eşlerini) kaldırır.

    Yalnız denemenin KENDİ yazdığı (geçici) dosyaya çağrılır. Silinen dosya veri taşımaz: kaynak DB yerinde ve sağlamdır. Hata
    YÜKSELTMEZ; kaldırılamazsa WARNING yazar — artığın varlığı operatörden saklanmaz."""
    for ek in ("", "-journal", "-wal", "-shm"):
        p = f"{yol}{ek}"
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            logger.warning("Basarisiz yedek artigi kaldirilamadi: %s — elle silin.", p, exc_info=True)


def yedek_acilir_mi(yol, sqlcipher_mod=None, anahtar: str = "", tam: bool = False) -> bool:
    """Dosya bir veritabanı olarak AÇILIYOR mu: boş değil, şeması okunuyor (şifreliyse verilen anahtarla); `tam` ise
    `PRAGMA quick_check` 'ok'. ASLA istisna atmaz.

    SQLite başlığı yoksa dosya şifrelidir: anahtar ya da bağlayıcı verilmemişse AÇILAMAZ sayılır (bilinmiyor ≠ geçerli)."""
    try:
        if os.path.getsize(yol) == 0:
            return False
        with open(yol, "rb") as f:
            duz = f.read(len(_SQLITE_BASLIK)) == _SQLITE_BASLIK
    except OSError:
        return False
    if not duz and (not anahtar or sqlcipher_mod is None):
        return False
    c = None
    try:
        c = sqlite3.connect(str(yol)) if duz else sqlcipher_mod.connect(str(yol))
        if not duz:
            c.execute("PRAGMA key='{}'".format(anahtar.replace("'", "''")))
        if int(c.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]) <= 0:
            return False
        if tam:
            r = c.execute("PRAGMA quick_check").fetchone()
            return bool(r) and str(r[0]).strip().lower() == "ok"
        return True
    except Exception:
        # Yoklama: açılmaması BEKLENEN bir sonuçtur (çağıran WARNING/ERROR yazar); nedeni yine de saklanmaz.
        _log.debug("Yedek acilamadi / dogrulanamadi: %s", yol, exc_info=True)
        return False
    finally:
        if c is not None:
            try:
                c.close()
            except Exception:
                pass


def yedek_yaz(src_conn, yol: str, baglayici, anahtar: str, logger) -> None:
    """`src_conn`ın çevrimiçi yedeğini `yol`a GEÇİCİ AD → DOĞRULAMA → `os.replace` sırasıyla yazar. Başarısızlıkta istisna
    YÜKSELİR, son ad oluşmaz / önceden varsa DEĞİŞMEZ, geçici dosya kaldırılır.

    `baglayici`: hedefi açacak modül (`sqlite3` ya da sqlcipher3); `anahtar` boş değilse hedefe `PRAGMA key` uygulanır ve
    doğrulama aynı anahtarla yapılır."""
    gecici = gecici_yol(yol)
    basarisiz_yedegi_kaldir(gecici, logger)  # önceki çökmeden kalmış aynı adlı geçici (bizim artığımız)
    dst = None
    tamam = False
    try:
        dst = baglayici.connect(gecici)
        if anahtar:
            dst.execute("PRAGMA key='{}'".format(anahtar.replace("'", "''")))
        src_conn.backup(dst)
        dst.commit()
        dst.close()
        dst = None
        if not yedek_acilir_mi(gecici, baglayici if anahtar else None, anahtar, tam=True):
            raise RuntimeError(f"yazilan yedek DOGRULANAMADI (acilmiyor / quick_check basarisiz): {gecici}")
        os.replace(gecici, yol)
        tamam = True
    finally:
        if dst is not None:
            try:
                dst.close()
            except Exception:
                pass
        if not tamam:
            basarisiz_yedegi_kaldir(gecici, logger)
