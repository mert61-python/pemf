# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.10 (B-3.54 · B-3.55) — `sqlcipher_util` modül başlığı ve karantina kapısının gerekçesi KODLA aynı.

ÖLÇÜLEN (HEAD ebf1c3fe, 2026-10-28):
  · `apps/backend/database/sqlcipher_util.py:11-12` "NOT: treatment_history_db.py kendi (calisan, test-edilmis) inline kopyasini
    korur; bu modul yeni cagiranlar (patient_database) icindir." — 2026-09-15'ten (A1 · 2/2) beri YANLIŞ: tedavi DB'si
    `thdb_sema.SemaKarisimi._migrate_to_encrypted_if_needed` → `sqlcipher_util.migrate_to_encrypted_if_needed`e DELEGE ediyor;
    tedavi DB modüllerinde (`treatment_history_db.py`, `thdb_*.py`) `sqlcipher_export` çağrısı YOK. (Aynı başlığın anahtar KAYNAĞI
    cümlesi D6.09'da düzeltildi; o kol `tests/test_sqlcipher_anahtar_YERI_belge_ve_ileti_D6_09.py`'de.)
  · `tests/test_karantina_okuyucu_tuglalastirmaz.py:15-17` gerekçesi "`api_server._daily_maintenance_loop` günlük yedeği
    `shutil.copy2` ile alıyor" diyordu — o kopyalayıcı kaldırıldı (bkz. D6.07 kapısı).

⚠️ "TEK ÇAĞIRAN" KAPISI BİLEREK YOK: `database/yedek_dosyasi.py` MEŞRU ikinci `sqlcipher_export` çağıranıdır (yedek şifreleme /
düz kopya). Kapı yalnız TEDAVİ DB yolunda kopya göç gövdesi olmadığını ve delegasyonu ölçer.
Kapı yalnız dosya okur ve AST ayrıştırır; ürün kodu İÇE AKTARILMAZ.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DB = KOK / "apps" / "backend" / "database"
UTIL = DB / "sqlcipher_util.py"


def _agac(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def _cagri_adlari(dugum: ast.AST) -> set[str]:
    adlar: set[str] = set()
    for d in ast.walk(dugum):
        if isinstance(d, ast.Call):
            f = d.func
            if isinstance(f, ast.Name):
                adlar.add(f.id)
            elif isinstance(f, ast.Attribute):
                adlar.add(f.attr)
    return adlar


def _sql_export_cagiran_islevler(p: Path) -> list[str]:
    """`execute("… sqlcipher_export(…)")` biçimli GERÇEK çağrılar (dize sabiti bir Call argümanında; yorum / docstring SAYILMAZ)."""
    bulunan = []
    for d in ast.walk(_agac(p)):
        if isinstance(d, ast.Call):
            for a in d.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and "sqlcipher_export" in a.value:
                    bulunan.append(f"{p.name}:{d.lineno}")
    return bulunan


def _tedavi_modulleri() -> list[Path]:
    return [DB / "treatment_history_db.py", *sorted(DB.glob("thdb_*.py"))]


def _delege_eden_metot() -> ast.FunctionDef:
    for p in _tedavi_modulleri():
        for d in ast.walk(_agac(p)):
            if isinstance(d, ast.FunctionDef) and d.name == "_migrate_to_encrypted_if_needed":
                return d
    raise AssertionError("tedavi DB'sinin _migrate_to_encrypted_if_needed metodu bulunamadı — kapıyı yeniden ölçün")


def test_tedavi_DB_goc_govdesini_KOPYALAMAZ_ortak_govdeye_delege_eder():
    kopya = [k for p in _tedavi_modulleri() for k in _sql_export_cagiran_islevler(p)]
    assert not kopya, f"tedavi DB modüllerinde sqlcipher_export çağrısı var (göç gövdesi kopyası?): {kopya}"
    m = _delege_eden_metot()
    importlar = {(d.module, a.name) for d in ast.walk(m) if isinstance(d, ast.ImportFrom) for a in d.names}
    assert ("database.sqlcipher_util", "migrate_to_encrypted_if_needed") in importlar, (
        "tedavi DB'si migrate_to_encrypted_if_needed'i sqlcipher_util'den içe aktarmıyor"
    )
    assert "migrate_to_encrypted_if_needed" in _cagri_adlari(m), "tedavi DB'si ortak göç gövdesini ÇAĞIRMIYOR"
    # Ortak gövde gerçekten sqlcipher_util'de.
    assert _sql_export_cagiran_islevler(UTIL), (
        "sqlcipher_util'de sqlcipher_export çağrısı yok — ortak gövde taşındı mı?"
    )


def test_sqlcipher_util_modul_basligi_INLINE_KOPYA_iddiasi_tasimaz_delegasyonu_soyler():
    doc = ast.get_docstring(_agac(UTIL)) or ""
    assert not re.search(r"inline\s+kopya", doc, re.I), (
        "sqlcipher_util modül başlığı tedavi DB'sinin 'inline kopya' taşıdığını söylüyor; tedavi DB'si DELEGE ediyor"
    )
    assert "thdb_sema" in doc and "delege" in doc, (
        "modül başlığı tedavi DB'sinin ortak gövdeye delege ettiğini söylemiyor"
    )
    assert "yedek_dosyasi" in doc, "modül başlığı meşru ikinci sqlcipher_export çağıranını (yedek_dosyasi) anmıyor"


def test_karantina_kapisinin_gerekcesi_bakim_dongusunu_KOPYALAYICI_diye_suclamaz():
    yol = KOK / "tests" / "test_karantina_okuyucu_tuglalastirmaz.py"
    doc = ast.get_docstring(_agac(yol)) or ""
    paragraflar = [p for p in re.split(r"\n\s*\n", doc) if "_daily_maintenance_loop" in p]
    assert paragraflar, "karantina kapısının gerekçesi eski suçluyu artık anmıyor — kapıyı yeniden ölçün"
    for p in paragraflar:
        assert "copy2" not in p, "karantina kapısı _daily_maintenance_loop'u hâlâ `copy2` kopyalayıcısı diye anlatıyor"
        assert "KALDIRILDI" in p, "karantina kapısının gerekçesi kopyalayıcının KALDIRILDIĞINI söylemiyor"
