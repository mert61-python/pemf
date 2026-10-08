# -*- coding: utf-8 -*-
"""D2.61 (B-3.70) — at-rest bayrağı BAŞARISIZ bağlantıda düşmez · başarısız yedek 0 baytlık / yarım dosya BIRAKMAZ.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.70, 2-D'de yeniden ölçüldü):
  1. `TreatmentHistoryDB._create_connection` şifreli bağlantı AÇILAMAYINCA (geçici G-Ç / kilit, `PEMF_ENCRYPT_AT_REST=1`)
     `RuntimeError`dan ÖNCE `self.at_rest_encrypted = False` yazıyordu. Bayrak örnek düzeyinde → tek bir iş parçacığındaki
     geçici arıza `/api/health` ve kurtarma uyarısına "şifresiz" dedirtiyordu (DB şifreli, öteki bağlantılar sağlam).
  2. Aynı bayrak `create_backup`ın dalını seçer: bayrak yanlışlıkla False iken havuzdaki şifreli bağlantıdan DÜZ `sqlite3`
     hedefe yedek denenir → `TypeError` (bağlayıcılar karışmaz) → yedek ALINMAZ ve hedefte 0 baytlık dosya KALIR. Bu artık
     rotasyon yuvasını ve `_recent_backup_exists` tazelik denetimini kandırır (yedek sessizce alınmamış olur).
  3. Herhangi bir başka yedek arızasında (disk dolu, G-Ç) da hedef dosya 0 bayt kalıyordu — tedavi VE hasta DB'sinde.

SAHTE EN ALT KATTA: arıza bağlayıcının kendisinde (`sqlcipher3.dbapi2.connect` / `sqlite3.connect`), yalnız ilgili yol / iş
parçacığı için; "disk dolu" gerçek SQLite sınırıyla (`PRAGMA max_page_count`) — SQLite'ın kendi SQLITE_FULL'ü. Ürün zinciri
(havuz, bayrak, `create_backup` dal seçimi) gerçek. Şifreli kol GERÇEK sqlcipher3 ister (yoksa atlanır → A-46 CI kırmızısı).
"""

from __future__ import annotations

import os
import queue
import sqlite3
import threading
from pathlib import Path

import pytest
import sahte_sqlcipher

K = "D261-birincil-anahtar"
ISCI = "D261-isci"


def _tedavi_sifreli(monkeypatch, app: Path):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    mod = sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: K)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = thdb.TreatmentHistoryDB(app)
    sid = db.start_session(treatment_mode="Manuel", patient_name="D261Hasta")
    db.end_session(sid, duration_minutes=5)
    return mod, db


def _tedavi_duz(monkeypatch, app: Path):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = thdb.TreatmentHistoryDB(app)
    sid = db.start_session(treatment_mode="Manuel", patient_name="D261Hasta")
    db.end_session(sid, duration_minutes=5)
    return db


def _hasta(monkeypatch, app: Path, sifreli: bool):
    from database import patient_database as pdb

    if sifreli:
        sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
        monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
        monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: K)
    else:
        monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
        monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    db = pdb.PatientDatabase(str(app / "patients.db"))
    db.add_patient({"name": "D261Hasta", "species": "Kedi"})
    return db


class _KaliciIsParcacigi:
    """Bakım döngüsü gibi KALICI bir iş parçacığı: kendi havuz bağlantısını tutar, işleri sırayla koşar."""

    def __init__(self, ad: str):
        self._q: queue.Queue = queue.Queue()
        self._t = threading.Thread(target=self._dongu, name=ad, daemon=True)
        self._t.start()

    def _dongu(self):
        while True:
            is_ = self._q.get()
            if is_ is None:
                return
            fn, sonuc = is_
            try:
                sonuc.put(("ok", fn()))
            except BaseException as e:  # noqa: BLE001 — sonucu çağırana taşı
                sonuc.put(("hata", e))

    def kos(self, fn):
        sonuc: queue.Queue = queue.Queue()
        self._q.put((fn, sonuc))
        tur, deger = sonuc.get(timeout=60)
        if tur == "hata":
            raise deger
        return deger

    def bitir(self):
        self._q.put(None)
        self._t.join(timeout=10)


def _isci_baglantisi_bir_kez_dusur(monkeypatch, mod, db_yolu: Path) -> dict:
    """`ISCI` adlı iş parçacığında tedavi DB'sine şifreli bağlantı açılışı G-Ç hatasıyla düşer (geçici disk arızası)."""
    gercek = mod.connect
    sayac = {"dusen": 0}

    def _connect(yol, *a, **k):
        if threading.current_thread().name == ISCI and os.path.normcase(str(yol)) == os.path.normcase(str(db_yolu)):
            sayac["dusen"] += 1
            raise mod.OperationalError("disk I/O error")
        return gercek(yol, *a, **k)

    monkeypatch.setattr(mod, "connect", _connect)
    return sayac


def _iscide_baglan(db) -> str:
    sonuc = {}

    def _calis():
        try:
            with db._get_connection() as c:
                c.execute("SELECT 1").fetchone()
            sonuc["r"] = "acildi"
        except RuntimeError as e:
            sonuc["r"] = f"RuntimeError: {e}"
        except Exception as e:  # noqa: BLE001
            sonuc["r"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=_calis, name=ISCI)
    t.start()
    t.join(timeout=30)
    return sonuc.get("r", "bitmedi")


def _sifreli_yedek_acilir(mod, yol: Path, anahtar: str) -> int:
    c = mod.connect(str(yol))
    try:
        c.execute(f"PRAGMA key='{anahtar}'")
        return int(c.execute("SELECT count(*) FROM treatment_sessions").fetchone()[0])
    finally:
        c.close()


# ── 1 · bayrak ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_KRITIK_D261_iscide_sifreli_baglanti_DUSUNCE_at_rest_bayragi_DUSMEZ(temp_app_data, monkeypatch):
    mod, db = _tedavi_sifreli(monkeypatch, temp_app_data)
    try:
        assert db.get_database_health_snapshot()["at_rest_encrypted"] is True, (
            "ön koşul: şifreli DB 'şifreli' görünmeli"
        )
        sayac = _isci_baglantisi_bir_kez_dusur(monkeypatch, mod, db.db_path)
        r = _iscide_baglan(db)
        assert sayac["dusen"] >= 1 and r.startswith("RuntimeError"), f"aparat: işçi bağlantısı düşmedi ({r}, {sayac})"
        assert db.get_database_health_snapshot()["at_rest_encrypted"] is True, (
            "tek bir iş parçacığındaki geçici bağlantı arızası at_rest_encrypted bayrağını False'a çekti — /api/health "
            "şifreli DB'yi 'şifresiz' raporluyor, kurtarma uyarısı sönüyor"
        )
    finally:
        db.close()


def test_KARSIT_D261_gercekten_SIFRESIZ_kurulumda_bayrak_False(temp_app_data, monkeypatch):
    db = _tedavi_duz(monkeypatch, temp_app_data)
    try:
        assert db.get_database_health_snapshot()["at_rest_encrypted"] is False
    finally:
        db.close()


# ── 2 · zincir: bayrak düşer → yedek düz dala sapar → 0 bayt ──────────────────────────────────────────────────────


def test_KRITIK_D261_iscideki_ariza_KALICI_is_parcacigindaki_yedegi_SIFRESIZ_dala_saptirmaz(temp_app_data, monkeypatch):
    mod, db = _tedavi_sifreli(monkeypatch, temp_app_data)
    bakim = _KaliciIsParcacigi("D261-bakim")
    hedef = temp_app_data / "backups" / "pemf_treatment_history_20261009_010101.db"
    try:
        bakim.kos(db.run_maintenance)  # bakım iş parçacığı kendi havuz bağlantısını alır
        sayac = _isci_baglantisi_bir_kez_dusur(monkeypatch, mod, db.db_path)
        assert _iscide_baglan(db).startswith("RuntimeError") and sayac["dusen"] >= 1, "aparat: işçi arızası kurulamadı"
        sonuc = bakim.kos(lambda: db.create_backup(str(hedef)))
        boyut = hedef.stat().st_size if hedef.exists() else None
        assert sonuc is True, f"geçici işçi arızasından sonra yedek ALINMADI (dosya boyutu {boyut})"
        assert boyut and boyut > 0, f"yedek dosyası boş/yok: {boyut}"
        assert _sifreli_yedek_acilir(mod, hedef, K) == 1, "yedek birincil anahtarla açılıp seansı göstermeli"
    finally:
        bakim.kos(db.close_connections)
        bakim.bitir()
        db.close()


# ── 3 · başarısız yedek artık bırakmaz (iki DB × iki dal) ─────────────────────────────────────────────────────────


def _disk_dolu(monkeypatch, mod, yedek_dizini: Path) -> dict:
    """`yedek_dizini` altındaki hedefe açılan bağlantı 'disk dolu' olur: SQLite'ın kendi sayfa sınırı (SQLITE_FULL)."""
    gercek = mod.connect
    sayac = {"n": 0}

    def _connect(yol, *a, **k):
        c = gercek(yol, *a, **k)
        if os.path.normcase(str(Path(yol).parent)) == os.path.normcase(str(yedek_dizini)):
            sayac["n"] += 1
            c.execute("PRAGMA max_page_count=2")
        return c

    monkeypatch.setattr(mod, "connect", _connect)
    return sayac


@pytest.mark.parametrize("kip", ["tedavi_duz", "tedavi_sifreli", "hasta_duz", "hasta_sifreli"])
def test_KRITIK_D261_yedek_DUSTUGUNDE_hedefte_0_bayt_ARTIK_kalmaz(temp_app_data, monkeypatch, kip):
    if kip == "tedavi_sifreli":
        mod, db = _tedavi_sifreli(monkeypatch, temp_app_data)
    elif kip == "tedavi_duz":
        db, mod = _tedavi_duz(monkeypatch, temp_app_data), sqlite3
    elif kip == "hasta_sifreli":
        db = _hasta(monkeypatch, temp_app_data, True)
        from database.sqlcipher_util import import_sqlcipher

        mod = import_sqlcipher()
    else:
        db, mod = _hasta(monkeypatch, temp_app_data, False), sqlite3
    ydir = temp_app_data / "backups"
    ydir.mkdir(exist_ok=True)
    hedef = ydir / "yedek_20261009_020202.db"
    try:
        sayac = _disk_dolu(monkeypatch, mod, ydir)
        sonuc = db.create_backup(str(hedef))
        assert sayac["n"] >= 1, "aparat: yedek hedefine bağlantı 'disk dolu' kurulamadı"
        assert sonuc is False, "disk dolu yedek 'başarılı' döndü"
        kalan = sorted(p.name for p in ydir.iterdir())
        assert kalan == [], (
            f"başarısız yedek hedefte artık bıraktı: {kalan} (0 baytlık dosya rotasyonu/tazeliği kandırır)"
        )
    finally:
        try:
            db.close()
        except AttributeError:
            db._reset_thread_conn()


@pytest.mark.parametrize("kip", ["tedavi_duz", "tedavi_sifreli", "hasta_duz", "hasta_sifreli"])
def test_KARSIT_D261_saglikli_yedek_DOLU_ve_onceden_VAR_olan_dosyaya_dokunulmaz(temp_app_data, monkeypatch, kip):
    if kip == "tedavi_sifreli":
        mod, db = _tedavi_sifreli(monkeypatch, temp_app_data)
    elif kip == "tedavi_duz":
        db, mod = _tedavi_duz(monkeypatch, temp_app_data), sqlite3
    elif kip == "hasta_sifreli":
        db = _hasta(monkeypatch, temp_app_data, True)
        mod = None
    else:
        db, mod = _hasta(monkeypatch, temp_app_data, False), sqlite3
    ydir = temp_app_data / "backups"
    ydir.mkdir(exist_ok=True)
    hedef = ydir / "yedek_saglikli.db"
    baska = ydir / "yedek_baska_sureclerin.db"
    baska.write_bytes(b"onceden-var")
    try:
        assert db.create_backup(str(hedef)) is True
        assert hedef.stat().st_size > 0
        assert baska.read_bytes() == b"onceden-var", "yedek dizinindeki başka dosyaya dokunuldu"
        if kip == "tedavi_sifreli":
            assert _sifreli_yedek_acilir(mod, hedef, K) == 1
        elif kip == "tedavi_duz":
            c = sqlite3.connect(str(hedef))
            try:
                assert c.execute("SELECT count(*) FROM treatment_sessions").fetchone()[0] == 1
            finally:
                c.close()
    finally:
        try:
            db.close()
        except AttributeError:
            db._reset_thread_conn()


def test_KARSIT_D261_ayni_adda_ONCEDEN_var_olan_dosya_basarisiz_denemede_SILINMEZ(temp_app_data, monkeypatch):
    """Silinen yalnız BU denemenin oluşturduğu dosyadır — aynı adda önceden duran bir dosya (ör. aynı saniyedeki önceki
    yedek) başarısız denemede yok edilmez."""
    db = _tedavi_duz(monkeypatch, temp_app_data)
    ydir = temp_app_data / "backups"
    ydir.mkdir(exist_ok=True)
    hedef = ydir / "yedek_ayni_saniye.db"
    hedef.write_bytes(b"onceki-yedek")
    try:
        _disk_dolu(monkeypatch, sqlite3, ydir)
        assert db.create_backup(str(hedef)) is False
        assert hedef.exists(), "başarısız deneme ÖNCEDEN var olan dosyayı sildi"
    finally:
        db.close()
