# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.61 (B-3.80) — tedavi DB'sinin açılış göçü güvencesi GERÇEĞİ söyler.

Kusur: `thdb_sema` başlığı "`_run_startup_migrations_with_rollback` her göç adımını GERİ ALINABİLİR tutar",
database/README "rollback'li açılış göçleri" diyordu. Ölçüm (gerçek `TreatmentHistoryDB`, eski şemalı DB): kurucu ÖNCE
`_init_database` (`_semayi_kur` → `_safe_add_column` = `ALTER TABLE … ADD COLUMN`) koşar, `pre_migration_*` yedeği ANCAK
SONRA ve yalnız şema sürümü hedefin altındayken alınır; rollback'in koruduğu tek adım `_ensure_schema_version` (sürüm
metadata'sı). Yani yedek göç SONRASI şemayı taşır, kolon göçleri geri alınmaz (eklemeli + idempotent oldukları için veri
kaybettirmez).

Seçim (D67-A2): BELGE gerçeği söyler (en muhafazakâr). Davranışı güvenceye getirmek (yedeği kolon göçlerinden önce
almak) her açılışta tam-DB kopyası ya da bekleyen kolon tespiti ister — göç sırasını değiştirir, küçük değil.

Kapı: yedeğin içeriği ÖLÇÜLÜR; belgeler ölçüme göre konuşur (yedek yeni kolonu taşıyorsa "her adım geri alınabilir"
YASAK ve "kolon göçleri yedekten ÖNCE … geri alınmaz" ZORUNLU; ileride yedek öne alınırsa tersi).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SEMA = KOK / "apps" / "backend" / "database" / "thdb_sema.py"
README = KOK / "apps" / "backend" / "database" / "README.md"
#: Tur 2 (çürütücü): eski iki kalıp yalnız birebir sözü yakalıyordu ("tum goc adimlari GERI ALINABILIR", "göçler rollback'li"
#: kaçıyordu) → her "geri alınabilir" iddiası (ASCII / Türkçe, büyük-küçük) ve göçü niteleyen her "rollback'li" yasak.
_YASAK = re.compile(
    r"her\s+goc\s+adimini\s+GERI\s+ALINABILIR|rollback'li açılış göçleri"
    r"|ger[iİıI]\s+al[ıiIİ]nab[iİıI]l"
    r"|rollback'?l[iİıI]\s+(?:açılış\s+|acilis\s+)?g[öo][çc]|g[öo][çc]\w*\s+(?:\(\s*)?(?:\w+\s+)?rollback'?l[iİıI]",
    re.I,
)


@pytest.fixture
def yedek_yeni_kolonu_tasir(tmp_path, monkeypatch) -> bool:
    """Eski şemalı (`treatment_sessions.updated_at` YOK, sürüm 2) düz DB → GERÇEK kurucu → `pre_migration_v2_*`
    yedeğinde kolon var mı."""
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)  # düz-metin: yedek sqlite3 ile okunur
    from database.treatment_history_db import TreatmentHistoryDB

    kok = tmp_path / "gecmis"
    TreatmentHistoryDB(kok).close()
    yol = kok / "pemf_treatment_history.db"
    with sqlite3.connect(yol) as c:
        c.execute("ALTER TABLE treatment_sessions DROP COLUMN updated_at")
        c.execute("UPDATE system_settings SET setting_value='2' WHERE setting_key='db_schema_version'")
    with sqlite3.connect(yol) as c:
        kolonlar = {r[1] for r in c.execute("PRAGMA table_info(treatment_sessions)")}
    assert "updated_at" not in kolonlar, "aparat: eski şema kurulamadı"
    TreatmentHistoryDB(kok).close()
    yedekler = sorted((kok / "migration_backups").glob("pre_migration_v2_*.db"))
    assert len(yedekler) == 1, f"aparat: sürüm 2 → 3 göçünde tek yedek bekleniyordu: {yedekler}"
    with sqlite3.connect(yedekler[0]) as c:
        yedek_kolonlari = {r[1] for r in c.execute("PRAGMA table_info(treatment_sessions)")}
    with sqlite3.connect(yol) as c:
        canli_kolonlari = {r[1] for r in c.execute("PRAGMA table_info(treatment_sessions)")}
    assert "updated_at" in canli_kolonlari, "aparat: kolon göçü koşmadı"
    return "updated_at" in yedek_kolonlari


def _metinler() -> dict[str, str]:
    sema = SEMA.read_text(encoding="utf-8")
    bas = sema.split('"""', 2)[1]
    satir = next(s for s in README.read_text(encoding="utf-8").splitlines() if s.startswith("| `thdb_sema.py` |"))
    return {"thdb_sema başlığı": bas, "database/README thdb_sema satırı": satir}


def test_KRITIK_goc_guvencesi_OLCULEN_yedek_sirasini_soyler_D6_61(yedek_yeni_kolonu_tasir):
    for ad, metin in _metinler().items():
        tek = re.sub(r"\s+", " ", metin)
        if yedek_yeni_kolonu_tasir:  # bugün: yedek kolon göçünden SONRA
            m = _YASAK.search(tek)
            assert m is None, (
                f"{ad} kolon göçlerini de geri alınabilir sayıyor ({m.group(0)!r}); ölçüm: yedek göç SONRASI şemayı taşır"
            )
            assert re.search(
                r"kolon\s+göçleri.{0,160}geri\s+alınmaz|kolon\s+gocleri.{0,160}geri\s+alinmaz", tek, re.I
            ), f"{ad} kolon göçlerinin yedekten ÖNCE koştuğunu ve geri ALINMADIĞINI söylemiyor"
        else:  # yedek öne alınmışsa belge "geri alınmaz" diyemez
            assert not re.search(r"geri\s+alınmaz|geri\s+alinmaz", tek, re.I), (
                f"{ad} artık yanlış: yedek kolon göçünden ÖNCE"
            )
