# Author: mertaygn, cglrgrkn
"""ÇÖKME SONRASI SEANS YETİM KALMAMALI — UYGULANAN DOZ KAYDI KAYBOLMAZ.

SAHA/KAMPANYA BULGUSU (2026-08-14, S01). Seans sürerken backend çökerse (elektrik kesintisi,
servis kill, güncelleme), yeniden açılışta kayıt şu hâlde kalıyordu:

    treatment_sessions : session_status='active', end_time=NULL, duration_minutes=NULL
    session_coil_runs  : ended_epoch=NULL, duration_seconds=NULL

Yani **hastaya uygulanan doz hiç yazılmıyordu.** Tıbbi cihazda kabul edilemez: geçmiş "tedavi
sürüyor" der, KPI onu saymaz, denetimde "bu hastaya ne verildi" sorusu cevapsız kalır.

NEDEN OLUYORDU. `recover_stale_active_sessions` YALNIZ 12 saatten eski seansları kapatıyordu.
Oysa tek çağrıldığı yer AÇILIŞTIR (`TreatmentHistoryDB.__init__`) ve açılışta bu cihazın hiçbir
seansı canlı olamaz — süreç yeni başlamıştır. Eşik, çalıştığı tek bağlamda koruma sağlamıyor,
yalnızca kaydı belirsiz bırakıyordu.

⚠️ BİTİŞ ZAMANI "ŞİMDİ" OLAMAZ. Cihaz günlerce kapalı kalmış olabilir; `now` yazmak 3 günlük
tedavi kaydı üretir — tıbben YANLIŞ bir kayıt, boş kayıttan daha kötüdür. Bitiş, KANITTAN
türetilir: son bobin çalışması ve son sensör örneği.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.treatment_history_db import TreatmentHistoryDB  # noqa: E402


def _seans_ac(db, hasta="Pamuk", baslangic_epoch=None):
    """Açık (active) bir seans + iki bobin çalışması yaz — çökme anındaki hâli taklit eder."""
    import datetime as _dt

    t0 = baslangic_epoch if baslangic_epoch is not None else time.time()
    d = _dt.datetime.fromtimestamp(t0)
    with db._get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO treatment_sessions
               (session_date, start_time, treatment_mode, patient_name, session_status)
               VALUES (?, ?, 'Manuel', ?, 'active')""",
            (d.strftime("%Y-%m-%d"), d.strftime("%H:%M:%S"), hasta),
        )
        sid = c.lastrowid
        for coil in (1, 2):
            c.execute(
                """INSERT INTO session_coil_runs
                   (session_id, coil_id, started_epoch, frequency_hz, duty_percent, created_at)
                   VALUES (?, ?, ?, 45, 35, ?)""",
                (sid, coil, t0, t0),
            )
        conn.commit()
    return sid


def _seans(db, sid):
    with db._get_connection() as conn:
        r = conn.execute("SELECT * FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()
        runs = conn.execute("SELECT * FROM session_coil_runs WHERE session_id = ? ORDER BY coil_id", (sid,)).fetchall()
    return r, runs


def test_KRITIK_cokmeden_kalan_seans_ACILISTA_kapatilir(tmp_path):
    """En kritik değişmez: açılışta 'active' kalan seans KAPATILIR — 12 saat beklenmez.

    Eskiden bu seans, cihaz 12 saat sonra bir kez daha açılana kadar 'active' kalıyordu; pratikte
    kayıt kalıcı olarak eksik kalıyordu."""
    db = TreatmentHistoryDB(tmp_path)
    sid = _seans_ac(db, baslangic_epoch=time.time() - 600)  # 10 dk once basladi

    # Backend yeniden acildi (yeni ornek = acilis yolu).
    TreatmentHistoryDB(tmp_path)

    r, _ = _seans(db, sid)
    assert r["session_status"] != "active", (
        "cokmeden kalan seans hala 'active' → gecmis 'tedavi suruyor' der, doz kaydi eksik kalir"
    )
    assert r["end_time"], "end_time yazilmadi"
    assert r["duration_minutes"] is not None, "duration_minutes yazilmadi → uygulanan doz kayip"


def test_KRITIK_yarim_kalan_BOBIN_calismalari_da_kapatilir(tmp_path):
    """Doz kaydı seans satırında değil, `session_coil_runs`ta durur. Seans kapatılıp bobin
    çalışmaları açık bırakılırsa "hangi bobin ne kadar sürdü" yine cevapsızdır."""
    db = TreatmentHistoryDB(tmp_path)
    sid = _seans_ac(db, baslangic_epoch=time.time() - 300)

    TreatmentHistoryDB(tmp_path)

    _, runs = _seans(db, sid)
    assert runs, "bobin calismasi yok — test kurulumu gecersiz"
    for run in runs:
        assert run["ended_epoch"] is not None, f"bobin {run['coil_id']} calismasi ACIK kaldi → uygulanan doz belirsiz"
        assert run["duration_seconds"] is not None, f"bobin {run['coil_id']} suresi yazilmadi"


def test_KRITIK_bitis_KANITTAN_turetilir_SIMDIden_degil(tmp_path):
    """⚠️ Cihaz günlerce kapalı kalmış olabilir. Bitişi `now` yazmak "3 gün süren tedavi"
    üretir — yanlış tıbbi kayıt, eksik kayıttan DAHA KÖTÜDÜR (denetimde gerçek sanılır).

    Bitiş, son KANITTAN türetilmeli: son sensör örneği / son bobin çalışması."""
    db = TreatmentHistoryDB(tmp_path)
    uc_gun_once = time.time() - 3 * 24 * 3600
    sid = _seans_ac(db, baslangic_epoch=uc_gun_once)

    # Kanit: seans basladiktan 8 dk sonra son telemetri geldi, sonra cihaz oldu.
    son_kanit = uc_gun_once + 8 * 60
    with db._get_connection() as conn:
        conn.execute(
            """INSERT INTO sensor_samples (session_id, coil_id, sample_ts, temperature_c, created_at)
               VALUES (?, '1', ?, 36.5, ?)""",
            (sid, son_kanit, son_kanit),
        )
        conn.commit()

    TreatmentHistoryDB(tmp_path)

    r, _ = _seans(db, sid)
    sure = int(r["duration_minutes"])
    assert sure <= 15, (
        f"sure {sure} dk yazildi — 'simdi'den turetilmis (cihaz 3 gun kapaliydi). Yanlis tibbi kayit uretiliyor."
    )
    assert sure >= 5, f"sure {sure} dk — son telemetri kanitindan (8 dk) turetilmedi"


def test_kapatilan_seans_ACIL_DURDURMADAN_ayirt_edilebilir(tmp_path):
    """Kurtarılan seans, normal biten bir seanstan ayırt edilebilmeli — aksi hâlde denetimde
    "bu kayıt neden yarım?" sorusu cevapsız kalır."""
    db = TreatmentHistoryDB(tmp_path)
    sid = _seans_ac(db, baslangic_epoch=time.time() - 120)

    TreatmentHistoryDB(tmp_path)

    r, _ = _seans(db, sid)
    assert r["session_status"] not in ("completed", "active"), (
        f"durum '{r['session_status']}' → kesintiyle biten seans normal bitmis gibi gorunuyor"
    )


def test_CALISAN_seansa_DOKUNULMAZ_karsit_kanit(tmp_path):
    """Karşı-kanıt: kurtarma her şeyi kapatarak da geçemez. Kurtarma AÇILIŞTA çalışır; aynı
    örnekte SONRADAN açılan bir seans, o örnek yaşadığı sürece 'active' KALMALIDIR."""
    db = TreatmentHistoryDB(tmp_path)
    TreatmentHistoryDB(tmp_path)  # acilis kurtarmasi burada calisti
    sid = _seans_ac(db)  # kurtarmadan SONRA acilan seans

    r, _ = _seans(db, sid)
    assert r["session_status"] == "active", "acilistan sonra baslayan seans kapatildi → suren tedavi 'bitti' sanilir"


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
