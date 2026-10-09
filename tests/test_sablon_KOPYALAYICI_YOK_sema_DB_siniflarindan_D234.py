# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.34 (B-9.1 · B-11.13) · Y26 (sahip kararı: DB şablonları ve şablon-kopya dalı KALDIRILIR) — veri kökünde DB yoksa açılış
ŞABLON KOPYALAMAZ; şemayı DB sınıfları kurar.

Kusur [ÖLÇTÜM]: `path_utils.initialize_database` `db` yoksa paketteki boş DÜZ-METİN şablonu (`_MEIPASS\\database\\*_template.db`)
veri köküne kopyalıyordu — 09-13 veri kaybının 3. yolu: yarım göç toparlaması düşerse canlı DB'nin yerine BOŞ şablon konur, klinik
geçmişi kaybolmuş görünür. 1.9.50 EXE'si şablonları taşıyor (kopyalayıcı sahada CANLI); HEAD spec'i şablonları F4'ten beri bulamıyor
(sessiz düşüş) ama spec'i "düzeltmek" yolu uyandırırdı. `deploy/README.md` paket içeriğinde "`_internal\\database\\*_template.db` —
BOTH" diyordu.

Ölçüm: frozen benzetimi — `sys._MEIPASS` içinde İŞARETLİ şablonlar olan geçici paket kökü, `PEMF_DATA_DIR` boş geçici veri kökü;
gerçek `initialize_database` ve gerçek DB sınıfları.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_SABLONLAR = ("patients_template.db", "pemf_treatment_history_template.db")
# Silinen şablonların tablo kümesi [ÖLÇTÜM 2026-10-09: iki şablon da 0 satır]: DB sınıfları bunların HEPSİNİ kurar → şablonsuz kayıp YOK.
_SABLON_TABLOLARI = {
    "patients.db": {"patients"},
    "pemf_treatment_history.db": {"session_parameters", "system_settings", "treatment_sessions"},
}


def _isaretli_paket(kok: Path) -> Path:
    d = kok / "database"
    d.mkdir(parents=True)
    for ad in _SABLONLAR:
        c = sqlite3.connect(d / ad)
        c.execute("CREATE TABLE SABLON_ISARETI (x)")
        c.commit()
        c.close()
    return kok


def _tablolar(yol: Path) -> set[str]:
    c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    try:
        return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        c.close()


def test_KRITIK_paket_sablon_TASISA_bile_veri_kokune_KOPYALANMAZ_D234(tmp_path, monkeypatch):
    from utils import path_utils

    monkeypatch.setattr(sys, "_MEIPASS", str(_isaretli_paket(tmp_path / "paket")), raising=False)
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    yollar = path_utils.initialize_database()
    assert set(yollar) == set(_SABLON_TABLOLARI), yollar
    kopyalanan = [ad for ad, yol in yollar.items() if Path(yol).exists() and "SABLON_ISARETI" in _tablolar(Path(yol))]
    assert not kopyalanan, f"açılış paketteki BOŞ ŞABLONU veri köküne koydu (09-13 kaybının 3. yolu): {kopyalanan}"


def test_KARSIT_yarim_goc_TOPARLAMASI_initialize_databasede_KALIR_D234(tmp_path, monkeypatch):
    """Kaldırılan yalnız kopyalayıcı: `db` yok + `db.plain.bak` var → açılış düz-metin yedeği GERİ KOYAR (09-13 dersi)."""
    from utils import path_utils

    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    kok = path_utils.get_app_data_directory()
    kok.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(kok / "patients.db.plain.bak")
    c.execute("CREATE TABLE patients (id INTEGER PRIMARY KEY, name TEXT)")
    c.execute("INSERT INTO patients (name) VALUES ('SENTETIK-HASTA')")
    c.commit()
    c.close()
    path_utils.initialize_database()
    hedef = kok / "patients.db"
    assert hedef.exists() and not (kok / "patients.db.plain.bak").exists(), "yarım göç toparlanmadı"
    c = sqlite3.connect(f"file:{hedef}?mode=ro", uri=True)
    try:
        assert c.execute("SELECT name FROM patients").fetchall() == [("SENTETIK-HASTA",)]
    finally:
        c.close()


def test_KRITIK_sema_DB_SINIFLARINDAN_tam_silinen_sablonun_her_tablosu_kurulur_D234(tmp_path):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    kok = tmp_path / "veri"
    kok.mkdir()
    hdb = PatientDatabase(str(kok / "patients.db"))
    tdb = TreatmentHistoryDB(kok)
    kurulan = {}
    for ad, db in (("patients.db", hdb), ("pemf_treatment_history.db", tdb)):
        with db._get_connection() as conn:
            kurulan[ad] = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tdb.close()
    eksik = {ad: sorted(tablolar - kurulan[ad]) for ad, tablolar in _SABLON_TABLOLARI.items() if tablolar - kurulan[ad]}
    assert not eksik, f"şablonun taşıdığı tablo DB sınıfınca KURULMUYOR — şablon kaldırılırsa kaybolur: {eksik}"


def test_KRITIK_sablon_DB_dosyalari_depoda_YOK_ve_paket_belgesi_SAVUNMAZ_D234():
    """Y26: şablonlar depodan silinir (spec'i yeniden yönlendirmek yolu uyandıramaz); paket içeriği tablosu onları listelemez."""
    # F4 öncesi kök `database/`, F4 sonrası `apps/backend/database/`; `resource_path`in yedek kökü `pemf_gui/`.
    kalan = [
        str(p.relative_to(KOK))
        for d in ("database", "apps/backend/database", "pemf_gui/database")
        for p in (KOK / d).glob("*_template.db")
    ]
    assert not kalan, f"DB şablonları hâlâ depoda: {kalan}"
    readme = (KOK / "deploy" / "README.md").read_text(encoding="utf-8")
    assert "_template.db" not in readme, "deploy/README paket içeriğinde hâlâ `*_template.db` listeliyor"
