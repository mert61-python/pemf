# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.57 · B-3.75 — `get_treatment_db` AYNI DB dosyası FARKLI yol yazımıyla istenince süren seansı mühürlememeli.

ÖLÇÜLEN KUSUR (f870777): tekil örnek ham `Path` eşitsizliğiyle (`current_db_path != requested_db_path`) karşılaştırılıyordu.
Aynı dosyaya giden başka bir yazım (`kök/x/..`, 8.3 kısa ad, göreli/mutlak) YENİ bir `TreatmentHistoryDB` kuruyordu;
kurucunun açılış kurtarması (`recover_stale_active_sessions(max_age_hours=0)`) süren seansı ve açık bobin koşularını
`ABORTED_DUE_TO_POWER` ile MÜHÜRLÜYOR, eski örneğin bağlantı havuzu da kapatılmadan bırakılıyordu. Arada çökme olursa doz
süresi yanlış kanıtta kalıcı donar (denetim ölçümü: 29 dk yerine 5 dk).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest


@pytest.fixture
def tekil(monkeypatch):
    """Süreç geneli tekil örneği test için yalıt (önceki/sonraki testlere sızmasın)."""
    from database import treatment_history_db as thdb

    monkeypatch.setattr(thdb, "_treatment_db_instance", None)
    yield thdb
    inst = thdb._treatment_db_instance
    if inst is not None:
        try:
            inst.close()
        except Exception:
            pass


def _durum(db, sid):
    with db._get_connection() as conn:
        return conn.execute("SELECT session_status FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]


def test_KRITIK_ayni_DB_farkli_yazimla_istenince_SUREN_seans_ve_kosu_MUHURLENMEZ(tekil, tmp_path):
    kok = tmp_path / "veri"
    kok.mkdir()
    db = tekil.get_treatment_db(kok)
    sid = db.start_session(treatment_mode="Manuel", target_condition=None)
    run = db.start_coil_run(sid, 1, frequency_hz=100.0, duty_percent=40.0, phase=0.0, started_epoch=time.time())
    assert _durum(db, sid) == "active" and run

    farkli = Path(str(kok) + "/alt/..")  # aynı dizin, başka yazım (pathlib '..'yı çözmez)
    assert farkli != kok and farkli.resolve() == kok.resolve(), "aparat: yazım farkı kurulamadı"
    db2 = tekil.get_treatment_db(farkli)
    assert _durum(db2, sid) == "active", (
        "aynı DB dosyası farklı yazımla istenince YENİ örnek kuruldu ve açılış kurtarması SÜREN seansı mühürledi "
        f"(durum={_durum(db2, sid)!r})"
    )
    assert db2 is db, "aynı DB dosyası için İKİNCİ örnek kuruldu (eski örneğin havuzu kapatılmadan)"
    kosu = [k for k in db.get_session_coil_runs(sid) if k["id"] == run][0]
    assert kosu["ended_epoch"] is None, "süren bobin koşusu farklı yazım yüzünden kapatıldı"


def test_KARSIT_GERCEKTEN_farkli_DB_yeni_ornek_ve_ESKISI_KAPATILIR(tekil, tmp_path, monkeypatch):
    """Gerçekten başka bir kök istenirse yeni örnek kurulur (eski davranış) — ama eski örneğin bağlantıları kapatılır."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    db_a = tekil.get_treatment_db(a)
    kapatildi = []
    gercek = db_a.close
    monkeypatch.setattr(db_a, "close", lambda: (kapatildi.append(True), gercek())[1])
    db_b = tekil.get_treatment_db(b)
    assert db_b is not db_a and Path(db_b.db_path).parent == b
    assert kapatildi, "farklı köke geçişte ESKİ örnek kapatılmadı (bağlantı havuzu sızar)"


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="dizin bağlantısı (junction) Windows'a özgü")
def test_KRITIK_ayni_DB_BAGLANTI_yoluyla_istenince_de_SUREN_seans_MUHURLENMEZ(tekil, tmp_path):
    """Yalnız DOSYA KİMLİĞİYLE (samefile) görülebilen yazım: dizin bağlantısı (junction; 8.3 kısa ad ile aynı sınıf).
    Normalize metin karşılaştırması bunu FARKLI sanar. Bağlantı yalnız BAĞLANTI olarak sökülür (hedef silinmez)."""
    import os
    import subprocess

    kok = tmp_path / "veri"
    kok.mkdir()
    db = tekil.get_treatment_db(kok)
    sid = db.start_session(treatment_mode="Manuel", target_condition=None)
    bag = tmp_path / "bag"
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(bag), str(kok)], capture_output=True, timeout=20)
    if r.returncode != 0 or not bag.exists():
        pytest.skip(f"aparat: junction kurulamadı ({r.returncode})")
    try:
        assert os.path.abspath(str(bag)) != os.path.abspath(str(kok)), "aparat: yazım farkı yok"
        db2 = tekil.get_treatment_db(bag)
        assert _durum(db2, sid) == "active", (
            "bağlantı yoluyla istenen AYNI DB yeni örnek kurdu ve süren seansı mühürledi"
        )
        assert db2 is db
    finally:
        os.rmdir(str(bag))  # yalnız bağlantı (hedef dizin silinmez)
    assert (kok / "pemf_treatment_history.db").exists(), "aparat: bağlantı sökülürken hedef silindi"
