# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""HASTA DB YOLU: ACL UYGULANAMAZSA EMANET SAKLANMAZ — ve log YALAN SOYLEMEZ (2026-09-15).

OLCULEN ARIZA. Goc kodunun iki kopyasi, ACL BASARISIZ oldugunda ZIT davraniyordu:

    apps/backend/database/treatment_history_db.py  (tedavi + AI gecmisi)
        _locked = bool(lock_down_file(backup))
        if _locked: ... return            <- kilitlendiyse emanet SAKLA
        # kilitlenemedi -> AKISI DUSUR   <- FAIL-CLOSED: guvenli-sil

    apps/backend/database/sqlcipher_util.py  (HASTA DB'si)
        lock_down_file(backup)            <- DONUS DEGERI ATILIYOR
        logger.warning("... ESCROW saklandi (ACL-kilitli): %s")   <- KOSULSUZ

⚠️ IKI AYRI KUSUR, IKISI DE HASTA DB'SINDE (daha hassas olan tarafta):

  1. FAIL-OPEN: ACL tutmasa bile `.plain.bak` diskte KALIR. O dosya TUM hasta PII'sinin
     duz-metin tam kopyasidir ve SQLCipher'i tamamen baypas eder. Korumasiz emanet,
     sifrelemenin kendisini anlamsiz kilar — tedavi DB'si tam bu gerekceyle fail-closed.

  2. LOG YALAN SOYLUYOR: `lock_down_file` BASARISIZLIKTA HATA FIRLATMAZ, `False` DONER
     (apps/backend/utils/file_acl.py:110 — "best-effort, cagiran DURMAZ"). Yani `except` dali hic
     kosmaz; kod dogrudan "ESCROW saklandi (ACL-kilitli)" satirini basar. Uygulanmamis
     bir korumayi duyuran etiket — deponun kayitli hata sinifi: DUGME ETIKETI GERCEGI
     SOYLESIN.

⚠️ Ustelik `treatment_history_db.py`nin kendi yorumu "hasta DB'si (sqlcipher_util) bu
karari Audit P3'te ZATEN almisti" diyor. OLCULDU: ALMAMIS. Yorum, kardes dosya hakkinda
yanlis bilgi veriyordu.

BUGUNKU ETKI SINIRLI: varsayilan `PEMF_KEEP_PLAIN_BACKUP=0` (guvenli-sil), yani bu dal
yalniz operator emaneti ACIKCA actiginda kosuyor. Ama actiginda, korudugunu sandigi sey
korunmuyor ve log ona "korundu" diyor.

BU KAPI davranissaldir: gercek bir goc kosturur, `lock_down_file`i BASARISIZ yapar ve
`.plain.bak`in diskte KALMADIGINI olcer.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

import pytest
import sahte_sqlcipher

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _duz_db_kur(yol: Path, ad: str) -> None:
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE hasta (ad TEXT)")
    c.execute("INSERT INTO hasta VALUES (?)", (ad,))
    c.commit()
    c.close()


@pytest.fixture(params=sahte_sqlcipher.BAGLAYICILAR)
def baglayici(request, monkeypatch):
    """D2.08 (B-10.41 · test-parca-06#12): bu dört davranış kapısı eskiden sqlcipher3 yoksa (Windows CI)
    `pytest.skip` ile atlanıyordu → escrow ACL sonucunu TERSİNE çeviren mutant orada YEŞİLDİ (ölçüldü
    2026-10-06). `sahte` kol göçü sqlcipher3'süz koşturur (yalnız bağlayıcı sahte; politika gerçek)."""
    return sahte_sqlcipher.baglayici_kur(request.param, monkeypatch)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Izole veri koku + sifreleme acik + EMANET ISTENIYOR."""
    d = tmp_path / "PEMF_GUI"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    # Bu dosyanin TAMAMI emanet dalini olcer -> bayrak ACIK.
    monkeypatch.setenv("PEMF_KEEP_PLAIN_BACKUP", "1")
    try:
        from utils import secrets_manager as sm

        if hasattr(sm, "_CACHE"):
            sm._CACHE.clear()
    except Exception:
        pass
    return d


def _acl_sonucu(monkeypatch, sonuc: bool):
    """`lock_down_file`i verilen sonucu DONECEK sekilde degistir (firlatmaz — gercek
    fonksiyonun sozlesmesi de boyle: hata olursa False doner, exception atmaz)."""
    from utils import file_acl

    cagri = {"sayi": 0}

    def _sahte(path, keep_current_user: bool = False) -> bool:
        cagri["sayi"] += 1
        return sonuc

    monkeypatch.setattr(file_acl, "lock_down_file", _sahte)
    return cagri


def _goc_kostur(ortam: Path, ad: str, caplog):
    from database import sqlcipher_util as su

    db = ortam / f"{ad}.db"
    _duz_db_kur(db, ad)
    kayitci = logging.getLogger(f"escrow_kapisi_{ad}")
    with caplog.at_level(logging.DEBUG, logger=kayitci.name):
        su.migrate_to_encrypted_if_needed(db, ortam, logger=kayitci)
    return db, Path(str(db) + ".plain.bak")


# ═══════════════════════════════════════════════════════════════════════════════════════
# ASIL SOZLESME
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_ACL_UYGULANAMAZSA_duz_metin_yedek_DISKTE_KALMAZ(ortam, monkeypatch, caplog, baglayici):
    """⚠️ BU TEST BUGUNKU KODDA KIRMIZIDIR — arizanin ta kendisi.

    Korumasiz emanet = SQLCipher'in tamamen baypas edilebilecegi bir dosyanin diskte
    birakilmasi. Tedavi DB'si bu durumda guvenli-siliyor; hasta DB'si SAKLIYORDU.
    """
    cagri = _acl_sonucu(monkeypatch, False)
    db, yedek = _goc_kostur(ortam, "AclDusenHasta", caplog)

    assert cagri["sayi"] >= 1, "ACL hic denenmedi -> test amacina ulasmadi (emanet dali kosmamis)"
    assert not yedek.exists(), (
        "ACL UYGULANAMADI ama korumasiz `.plain.bak` diskte KALDI. O dosya TUM hasta "
        "PII'sinin duz-metin tam kopyasidir ve SQLCipher'i baypas eder; disk calinir/"
        "imajlanir/buluta senkronlanirsa at-rest garantisi COKER. Tedavi DB yolu ayni "
        "durumda GUVENLI-SILIYOR (fail-closed) — hasta DB yolu da oyle olmali."
    )
    assert db.exists(), "sifreli DB kaybolmus — goc zaten basariliydi, dosya yerinde kalmali"


def test_KRITIK_ACL_uygulanamayinca_log_ACL_KILITLI_DEMEZ(ortam, monkeypatch, caplog, baglayici):
    """⚠️ DUGME ETIKETI GERCEGI SOYLESIN.

    `lock_down_file` basarisizlikta FIRLATMAZ, False doner (apps/backend/utils/file_acl.py:110).
    Eski kod donusu atiyor ve kosulsuz "ESCROW saklandi (ACL-kilitli)" basiyordu — yani
    uygulanmamis bir korumayi duyuruyordu. Operator log'a bakip "korundu" saniyordu.
    """
    _acl_sonucu(monkeypatch, False)
    _goc_kostur(ortam, "AclLogHasta", caplog)

    metin = "\n".join(r.getMessage() for r in caplog.records)
    assert "ACL-kilitli" not in metin, (
        "ACL UYGULANMADIGI HALDE log 'ACL-kilitli' diyor — uygulanmamis bir korumayi "
        f"duyuran etiket. Log:\n{metin[:800]}"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# KARSIT-KANITLAR — "her zaman sil"e kaymasin
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_ACL_TUTARSA_emanet_GERCEKTEN_saklanir(ortam, monkeypatch, caplog, baglayici):
    """Kural "ACL'e bakma, hep sil"e kayarsa emanet yetenegi sessizce olur.

    Emanet, anahtar kaybinda geri donusu olan tek kopyadir; operator bunu ACIKCA istedi
    (PEMF_KEEP_PLAIN_BACKUP=1). Kilit tutuyorsa dosya KALMALI.
    """
    cagri = _acl_sonucu(monkeypatch, True)
    _db, yedek = _goc_kostur(ortam, "AclTutanHasta", caplog)

    assert cagri["sayi"] >= 1, "ACL hic denenmedi"
    assert yedek.exists(), (
        "ACL BASARILI oldugu halde emanet silinmis — operatorun acikca istedigi "
        "geri-donus kopyasi yok edildi (PEMF_KEEP_PLAIN_BACKUP=1)"
    )


def test_KARSIT_KANIT_bayrak_KAPALIYKEN_ACL_tutsa_bile_SILINIR(tmp_path, monkeypatch, caplog, baglayici):
    """Varsayilan yol degismedi: emanet istenmiyorsa ACL basarili olsa bile silinir."""
    d = tmp_path / "PEMF_GUI"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setenv("PEMF_KEEP_PLAIN_BACKUP", "0")
    monkeypatch.delenv("PEMF_KEEP_PLAIN_BAK", raising=False)
    try:
        from utils import secrets_manager as sm

        if hasattr(sm, "_CACHE"):
            sm._CACHE.clear()
    except Exception:
        pass
    _acl_sonucu(monkeypatch, True)
    _db, yedek = _goc_kostur(d, "VarsayilanHasta", caplog)
    assert not yedek.exists(), (
        "emanet ISTENMEDIGI halde `.plain.bak` diskte kaldi — varsayilan guvenli-sil bozulmus (sahip karari 2026-08-08)"
    )
