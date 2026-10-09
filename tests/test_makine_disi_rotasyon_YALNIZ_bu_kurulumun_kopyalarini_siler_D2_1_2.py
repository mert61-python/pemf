# -*- coding: utf-8 -*-
"""D2-1.2 (2-D incelemesi, A1) — aynı makine dışı dizini paylaşan İKİNCİ kurulumun yedeklerini rotasyon SİLMEMELİ (A-45).

ÖLÇÜLEN KUSUR (HEAD a76ee0d): `_rotasyon` bir dosyayı "bu kurulumun yedeği" saymak için yalnız AD desenine ve AÇILABİLİRLİĞE bakar.
Düz (şifresiz) kurulumda her düz SQLite dosyası anahtarsız açılır; şifreli kurulumda da başka cihazın DÜZ yedeği açılır. Aynı
`PEMF_BACKUP_DIR`'i paylaşan iki cihazda rotasyon iki cihazın kopyalarını TEK havuzda sayar ve komşunun kopyalarını siler:
N=3, 4 gün → A'nın 1, B'nin 2 kopyası kaldı [ÖLÇTÜM sonda]. A birkaç gün kapalı kalırsa B, A'nın TÜM makine dışı kopyalarını siler.
DÜZELTME: makine dışı rotasyon yalnız bu kurulumun KOPYALADIĞI (yerel kayıt) ya da bu kurulumun anahtarıyla şifreli açılan dosyaları sayar
ve siler; komşunun dosyası yabancı sayılır (dokunulmaz). Y11 (son N) tek cihazda DEĞİŞMEZ (karşıt kol).
SAHTE EN ALT KATTA: yalnız saat (`datetime.now`). Yedek, kopya, rotasyon GERÇEK.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import threading
from datetime import datetime as _dt
from datetime import timedelta
from pathlib import Path

import pytest

N = 3


def _cihaz(tmp_path: Path, monkeypatch, ad: str):
    from database.treatment_history_db import TreatmentHistoryDB
    from services.headless_db_maintenance import HeadlessDBMaintenance

    app = tmp_path / f"cihaz_{ad}" / "PEMF_GUI"
    app.mkdir(parents=True)
    db = TreatmentHistoryDB(app)
    assert not db.at_rest_encrypted
    db.start_session(treatment_mode="Manuel", patient_name=f"Hasta_{ad}")
    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = app, db, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, N
    w._stop, w._thread = threading.Event(), None
    return w


@pytest.fixture
def duz(monkeypatch, tmp_path):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    nas = tmp_path / "NAS_ortak"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))
    acik = []
    yield nas, acik
    for w in acik:
        w.db.close()


def _tur(monkeypatch, w, gun: int, saat: int):
    import services.headless_db_maintenance as hdm

    an = _dt(2026, 10, 1, saat, 0, 0) + timedelta(days=gun)

    class _Saat:
        @staticmethod
        def now(tz=None):
            return an

    monkeypatch.setattr(hdm, "datetime", _Saat)
    w._run_backup()


def _kopyalar(nas: Path, hasta: str) -> list:
    desen = re.compile(r"pemf_treatment_history_\d{8}_\d{6}\.db")
    out = []
    for p in sorted(nas.iterdir()):
        if desen.fullmatch(p.name):
            c = sqlite3.connect(str(p))
            try:
                if hasta in {r[0] for r in c.execute("SELECT patient_name FROM treatment_sessions")}:
                    out.append(p.name)
            finally:
                c.close()
    return out


def test_KRITIK_A45_ayni_NAS_iki_cihaz_birbirinin_kopyasini_SILMEZ_ve_paylasim_SOYLENIR(
    tmp_path, monkeypatch, duz, caplog
):
    import logging

    nas, acik = duz
    a = _cihaz(tmp_path, monkeypatch, "A")
    acik.append(a)
    b = _cihaz(tmp_path, monkeypatch, "B")
    acik.append(b)
    with caplog.at_level(logging.WARNING, logger="services.headless_db_maintenance"):
        for gun in range(4):
            _tur(monkeypatch, a, gun, saat=3)
            _tur(monkeypatch, b, gun, saat=4)
    ka, kb = _kopyalar(nas, "Hasta_A"), _kopyalar(nas, "Hasta_B")
    assert ka and kb, "ön koşul: okuyucu iki cihazın kopyasını da görebiliyor"
    assert len(ka) >= N and len(kb) >= N, (
        f"aynı makine dışı dizini paylaşan cihazlar birbirinin kopyasını SİLDİ (A-45): A={ka} B={kb} (her biri için en az N={N})"
    )
    assert any(r.levelno >= logging.ERROR and "paylas" in r.getMessage().lower() for r in caplog.records), (
        "makine dışı dizinin başka bir kurulumla PAYLAŞILDIĞI (rotasyonun bu yüzden durduğu) günlükte ERROR ile söylenmedi"
    )


def test_KRITIK_A45_cihaz_KAPALIYKEN_komsu_onun_makine_disi_kopyalarini_SILMEZ(tmp_path, monkeypatch, duz):
    nas, acik = duz
    a = _cihaz(tmp_path, monkeypatch, "A")
    acik.append(a)
    for gun in range(4):
        _tur(monkeypatch, a, gun, saat=3)
    once = _kopyalar(nas, "Hasta_A")
    assert len(once) == N
    b = _cihaz(tmp_path, monkeypatch, "B")  # klinik ikinci cihazı aynı NAS dizinine bağladı; A bir hafta kapalı
    acik.append(b)
    for gun in range(4, 11):
        _tur(monkeypatch, b, gun, saat=4)
    assert _kopyalar(nas, "Hasta_A") == once, (
        f"A kapalıyken B'nin rotasyonu A'nın makine dışı kopyalarını sildi: önce {once}, sonra {_kopyalar(nas, 'Hasta_A')} — "
        "A'nın diski şimdi ölürse makine dışı yedeği YOK"
    )
    assert len(_kopyalar(nas, "Hasta_B")) >= N, "B'nin kendi kopyaları da gitmemeli"


def test_KARSIT_Y11_tek_cihaz_onceden_KALAN_kendi_kopyalari_da_rotasyona_girer(tmp_path, monkeypatch, duz):
    """Yükseltme: düzeltmeden önce makine dışına kopyalanmış KENDİ yedekleri (yerelde de duran) rotasyon dışında kalmamalı (Y11 / KVKK)."""
    nas, acik = duz
    monkeypatch.delenv(
        "PEMF_BACKUP_DIR"
    )  # düzeltme öncesi dönem: makine dışı kopyalar İŞARETSİZ (eski kod) — burada elle konur
    a = _cihaz(tmp_path, monkeypatch, "A")
    acik.append(a)
    for gun in range(4):
        _tur(monkeypatch, a, gun, saat=3)
    nas.mkdir(exist_ok=True)
    for p in sorted(a.app_data_dir.joinpath("backups").glob("pemf_treatment_history_*.db")):
        shutil.copy2(p, nas / p.name)
    assert len(_kopyalar(nas, "Hasta_A")) == N
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))
    for gun in range(4, 8):
        _tur(monkeypatch, a, gun, saat=3)
    assert len(_kopyalar(nas, "Hasta_A")) == N, f"tek cihazda makine dışında N={N} kalmadı: {_kopyalar(nas, 'Hasta_A')}"
