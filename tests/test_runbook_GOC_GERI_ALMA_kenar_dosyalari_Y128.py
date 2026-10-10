# -*- coding: utf-8 -*-
"""Y128 (S-D.5) — göç geri almasında kenara alınan `-wal` / `-shm.rollback-<damga>` dosyaları otomatik SİLİNMEZ; RUNBOOK elle temizlemeyi
anlatır (yarıda kalmış geri almada — `<db>.rollback.tmp` varken — DOKUNULMAZ).

Belge-kod kapısı: dosya adları KODDAN türetilir (`thdb_sema._run_startup_migrations_with_rollback`: kenar eki, yan dosya sonekleri,
yarım-geri-alma imzası; tedavi DB dosya adı `treatment_history_db`). Kod bir adı değiştirirse ya da RUNBOOK satırı adları / "dokunmayın"
uyarısını kaybederse KIRMIZI. Davranış kapısı (yan dosyalar silinmez, kenara alınır): tests/test_goc_rollback_WAL_SHM_KENARA_alinir_Y100.py.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SEMA = KOK / "apps" / "backend" / "database" / "thdb_sema.py"
THDB = KOK / "apps" / "backend" / "database" / "treatment_history_db.py"
RUNBOOK = KOK / "docs" / "RUNBOOK.md"


def _koddan_adlar():
    kaynak = SEMA.read_text(encoding="utf-8")
    ek = re.search(r'f"\{_side\}(\.[a-z]+-)\{_damga\}"', kaynak)
    sonekler = re.search(r'for _sfx in \("(-[a-z]+)", "(-[a-z]+)"\)', kaynak)
    yarim = re.search(r'str\(self\.db_path\) \+ "(\.[a-z]+\.tmp)"', kaynak)
    db = re.search(r'self\.db_path = app_data_dir / "([^"]+\.db)"', THDB.read_text(encoding="utf-8"))
    assert ek and sonekler and yarim and db, "araç: adlar kaynaktan okunamadı (kod değişmiş — kapı kör kalmasın)"
    return db.group(1), ek.group(1), sonekler.groups(), yarim.group(1)


def _satir() -> str:
    satirlar = [s for s in RUNBOOK.read_text(encoding="utf-8").splitlines() if s.startswith("|") and "rollback-" in s]
    assert len(satirlar) == 1, f"RUNBOOK 'Olay senaryoları'nda kenar dosyaları için TEK satır olmalı ({len(satirlar)})"
    return satirlar[0]


def test_KRITIK_Y128_RUNBOOK_kenar_dosyalarini_KODDAKI_adlarla_anlatir():
    """MUTASYON: koddaki kenar eki değişir (`.rollback-` → `.geri-`) → KIRMIZI; RUNBOOK satırı silinir → KIRMIZI."""
    db, ek, sonekler, _ = _koddan_adlar()
    satir = _satir()
    for s in sonekler:
        ad = f"{db}{s}{ek}"
        assert ad in satir, f"RUNBOOK kenar dosyasını koddaki adla anmıyor: {ad!r}"
    assert "otomatik SİLİNMEZ" in satir, "satır Y128'i (otomatik silinmez) söylemiyor"


def test_KRITIK_Y128_yarida_kalan_geri_almada_DOKUNMAYIN_uyarisi():
    """`<db>.rollback.tmp` varken kenar dosyalarına dokunulmaz (son seanslar orada olabilir — D2-1.11). MUTASYON: uyarı düşer → KIRMIZI."""
    db, _, _, yarim = _koddan_adlar()
    satir = _satir()
    assert f"{db}{yarim}" in satir, f"yarım-geri-alma imzası ({db}{yarim}) satırda yok"
    assert re.search(rf"{re.escape(db + yarim)}.{{0,40}}VARSA.{{0,60}}DOKUNMAYIN", satir), (
        "'.rollback.tmp VARSA dokunmayın' uyarısı yok"
    )
    assert "SİLMEYİN" in satir and "TAŞIYIN" in satir, "elle temizlik silme yerine taşımayı söylemiyor"
