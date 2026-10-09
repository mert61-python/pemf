# -*- coding: utf-8 -*-
"""D2.63 (B-3.11 · B-3.20) — yerel yedek PENCERESİ korunur.

ÖLÇÜLEN KUSURLAR (DENETIM-03, 2-D'de yeniden ölçüldü):
  B-3.11 (YÜKSEK) `HeadlessDBMaintenance._loop` `last_backup = 0.0` ile `time.monotonic()` karşılaştırıyordu: 24 saatten uzun açık
         makinede (monotonic ≥ 86 400) İLK turda `now - last_backup >= backup_interval` hep doğru → "diskte taze yedek var" koruması
         (`first and not self._recent_backup_exists()`) devre dışı, HER yeniden başlatma yedek alıyordu. Rotasyon son 14'ü tuttuğu
         için 14 yeniden başlatma tüm yedek geçmişini aynı günün kopyalarıyla değiştirir (felaket kurtarma penceresi yok olur).
  B-3.20 Rotasyon (`_cleanup_backups`) ve tazelik (`_recent_backup_exists`) dosyaları YALNIZ ad / mtime ile sayıyordu: 0 baytlık
         artık (eski sürümün başarısız yedeği — sahadaki 1.9.50 bırakıyor) "taze yedek" sayılıp açılış yedeğini 24 saat bastırıyor ve
         rotasyonda SAĞLAM yedeğin yuvasını alıyordu. Ayrıca yedek doğrudan son ada yazılıyordu: yazım ortasında süreç ölürse son
         adda yarım dosya kalır.
DÜZELTME: açılış kararı diskteki EN YENİ AÇILABİLEN yedeğin yaşından (monotonic'ten bağımsız); yedek geçici ada yazılır, açılarak
doğrulanır, sonra son ada taşınır; rotasyon ve tazelik yalnız açılabilen yedekleri sayar; 0 baytlık artık silinir; DOLU ama
açılamayan dosya (başka anahtarla şifreli olabilir — kurtarılabilir veri) SİLİNMEZ ve sayılmaz, uyarı yazılır.
Sahte en alt katta: "disk dolu" SQLite'ın kendi sayfa sınırıyla (`PRAGMA max_page_count`) bağlayıcıda; saat `time` modülünde.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import threading
import time
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sahte_sqlcipher

K = "D263-birincil-anahtar"
GUN = 24 * 3600


def _dbler(monkeypatch, app: Path, sifreli: bool):
    from database import patient_database as pdb
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    if sifreli:
        sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
        monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
        anahtar = K
    else:
        monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
        anahtar = ""
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: anahtar)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: anahtar)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = thdb.TreatmentHistoryDB(app)
    sid = tdb.start_session(treatment_mode="Manuel", patient_name="D263Hasta")
    tdb.end_session(sid, duration_minutes=3)
    hdb = pdb.PatientDatabase(str(app / "patients.db"))
    hdb.add_patient({"name": "D263Hasta", "species": "Kedi"})
    return tdb, hdb


def _servis(app: Path, tdb, hdb):
    from services.headless_db_maintenance import HeadlessDBMaintenance

    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir = app
    w.db = tdb
    w.patient_db = hdb
    w.maint_interval = 6 * 3600
    w.backup_interval = GUN
    w.disk_interval = 30 * 60
    w.backup_retention_keep = 14
    w._stop = threading.Event()
    w._thread = None
    return w


def _gecerli_yedekler(app: Path, tdb, hdb, gun_listesi, simdi=None):
    """`gun_listesi` gün önceye damgalı GERÇEK yedekler (ad damgası + mtime aynı gün)."""
    simdi = simdi or datetime.now()
    bdir = app / "backups"
    bdir.mkdir(exist_ok=True)
    kaynak_t = bdir / "_kaynak_t.db"
    kaynak_h = bdir / "_kaynak_h.db"
    assert tdb.create_backup(str(kaynak_t)) and hdb.create_backup(str(kaynak_h)), "aparat: kaynak yedek alınamadı"
    yollar = []
    for g in gun_listesi:
        t = simdi - timedelta(days=g)
        damga = t.strftime("%Y%m%d_%H%M%S")
        for kaynak, onek in ((kaynak_t, "pemf_treatment_history_"), (kaynak_h, "pemf_patients_")):
            p = bdir / f"{onek}{damga}.db"
            shutil.copy2(kaynak, p)
            ts = t.timestamp()
            os.utime(p, (ts, ts))
            yollar.append(p)
    kaynak_t.unlink()
    kaynak_h.unlink()
    return yollar


class _TekTur:
    """`_stop` yerine: döngü İLK turdan sonra durur (`wait` çağrısı durdurur)."""

    def __init__(self, tur=1):
        self._kalan = tur

    def is_set(self):
        return self._kalan <= 0

    def wait(self, _sn=None):
        self._kalan -= 1
        return self._kalan <= 0


def _monotonic_sabit(monkeypatch, deger_listesi):
    import services.headless_db_maintenance as hdm

    degerler = list(deger_listesi)

    def _mono():
        return degerler.pop(0) if len(degerler) > 1 else degerler[0]

    monkeypatch.setattr(hdm, "time", types.SimpleNamespace(monotonic=_mono, time=time.time, sleep=time.sleep))


def _yedek_sayaci(monkeypatch, w):
    sayac = {"n": 0}
    gercek = w._run_backup

    def _say():
        sayac["n"] += 1
        return gercek()

    monkeypatch.setattr(w, "_run_backup", _say)
    monkeypatch.setattr(w, "_run_maintenance", lambda: None)
    monkeypatch.setattr(w, "_check_disk", lambda: None)
    return sayac


# ── 1 · açılış kararı monotonic'ten bağımsız (B-3.11) ─────────────────────────────────────────────────────────────


def test_KRITIK_D263_UZUN_SURE_acik_makinede_taze_yedek_VARKEN_acilis_yedegi_ALINMAZ(temp_app_data, monkeypatch):
    tdb, hdb = _dbler(monkeypatch, temp_app_data, sifreli=False)
    try:
        _gecerli_yedekler(temp_app_data, tdb, hdb, [1 / 24])  # 1 saat önceki geçerli yedek
        w = _servis(temp_app_data, tdb, hdb)
        sayac = _yedek_sayaci(monkeypatch, w)
        _monotonic_sabit(monkeypatch, [259200.0])  # makine 3 gündür açık
        w._stop = _TekTur(1)
        w._loop()
        assert sayac["n"] == 0, (
            "1 saatlik geçerli yedek varken açılışta yedek ALINDI — 24 saatten uzun açık makinede her yeniden başlatma yedek "
            "alıyor; 14 yeniden başlatma tüm yedek geçmişini aynı günün kopyalarıyla değiştirir (B-3.11)"
        )
    finally:
        tdb.close()
        hdb._reset_thread_conn()


@pytest.mark.parametrize("mono", [100.0, 259200.0])
def test_KARSIT_D263_yedek_YOKSA_ya_da_BAYATSA_acilista_yedek_ALINIR(temp_app_data, monkeypatch, mono):
    tdb, hdb = _dbler(monkeypatch, temp_app_data, sifreli=False)
    try:
        _gecerli_yedekler(temp_app_data, tdb, hdb, [2])  # 2 gün önceki yedek = bayat
        w = _servis(temp_app_data, tdb, hdb)
        sayac = _yedek_sayaci(monkeypatch, w)
        _monotonic_sabit(monkeypatch, [mono])
        w._stop = _TekTur(1)
        w._loop()
        assert sayac["n"] == 1, f"bayat yedekle açılışta yedek alınmadı (monotonic={mono})"
    finally:
        tdb.close()
        hdb._reset_thread_conn()


def test_KARSIT_D263_atlanan_acilis_yedeginden_sonra_sonraki_yedek_EN_YENI_yedegin_yasina_gore_gelir(
    temp_app_data, monkeypatch
):
    """Açılışta 1 sa'lik yedek → atlanır; 23,5 sa sonra (yedek 24,5 sa yaşında) periyodik yedek ALINIR. "Atlanınca sayacı şimdiye
    kur" yaklaşımı yedeği 47 saate kadar geciktirirdi."""
    tdb, hdb = _dbler(monkeypatch, temp_app_data, sifreli=False)
    try:
        _gecerli_yedekler(temp_app_data, tdb, hdb, [1 / 24])
        w = _servis(temp_app_data, tdb, hdb)
        sayac = _yedek_sayaci(monkeypatch, w)
        bas = 259200.0
        _monotonic_sabit(monkeypatch, [bas, bas + 23.5 * 3600])
        w._stop = _TekTur(2)
        w._loop()
        assert sayac["n"] == 1, f"en yeni yedek 24,5 sa yaşındayken periyodik yedek alınmadı (sayı {sayac['n']})"
    finally:
        tdb.close()
        hdb._reset_thread_conn()


# ── 2 · rotasyon ve tazelik yalnız AÇILABİLEN yedekleri sayar (B-3.20) ────────────────────────────────────────────


def _disk_dolu(monkeypatch, mod, bdir: Path):
    gercek = mod.connect

    def _connect(yol, *a, **k):
        c = gercek(yol, *a, **k)
        if os.path.normcase(str(Path(yol).parent)) == os.path.normcase(str(bdir)):
            c.execute("PRAGMA max_page_count=2")
        return c

    monkeypatch.setattr(mod, "connect", _connect)


@pytest.mark.parametrize("sifreli", [False, True], ids=["duz", "sifreli"])
def test_KRITIK_D263_0_bayt_ARTIKLAR_taze_sayilmaz_rotasyonda_SAGLAM_yedegi_silmez_ve_temizlenir(
    temp_app_data, monkeypatch, sifreli
):
    tdb, hdb = _dbler(monkeypatch, temp_app_data, sifreli)
    bdir = temp_app_data / "backups"
    try:
        gecerli = _gecerli_yedekler(temp_app_data, tdb, hdb, list(range(15, 1, -1)))  # 14 geçerli, 15..2 gün önce
        en_eski_t = min(p for p in gecerli if p.name.startswith("pemf_treatment_history_"))
        en_eski_h = min(p for p in gecerli if p.name.startswith("pemf_patients_"))
        # Sahadaki eski sürümün bıraktığı 0 baytlık artıklar — daha YENİ damga ve mtime (son 3 saat).
        artiklar = []
        for s in (3, 2, 1):
            t = datetime.now() - timedelta(hours=s)
            for onek in ("pemf_treatment_history_", "pemf_patients_"):
                p = bdir / f"{onek}{t.strftime('%Y%m%d_%H%M%S')}.db"
                p.write_bytes(b"")
                os.utime(p, (t.timestamp(), t.timestamp()))
                artiklar.append(p)
        w = _servis(temp_app_data, tdb, hdb)
        assert w._recent_backup_exists() is False, (
            "0 baytlık artık 'taze yedek' sayıldı — açılış yedeği 24 saat bastırılır (yedek sessizce alınmamış olur)"
        )
        # Üç yedek turu, hepsi disk dolu ile düşer (gerçek SQLite sayfa sınırı).
        _disk_dolu(monkeypatch, sqlite3, bdir)
        if sifreli:
            from database.sqlcipher_util import import_sqlcipher

            _disk_dolu(monkeypatch, import_sqlcipher(), bdir)
        import services.headless_db_maintenance as hdm

        anlar = [datetime.now() + timedelta(seconds=i) for i in range(3)]

        class _Saat:
            @staticmethod
            def now():
                return anlar.pop(0) if len(anlar) > 1 else anlar[0]

        monkeypatch.setattr(hdm, "datetime", _Saat)
        monkeypatch.setattr(w, "_refresh_recovery", lambda d: None)
        for _ in range(3):
            w._run_backup()
        kalan = sorted(p.name for p in bdir.iterdir())
        assert en_eski_t.name in kalan and en_eski_h.name in kalan, (
            "rotasyon EN ESKİ SAĞLAM yedeği sildi — yerini 0 baytlık / başarısız dosyalar aldı (felaket kurtarma penceresi daraldı)"
        )
        assert sorted(p.name for p in gecerli) == [k for k in kalan if k in {p.name for p in gecerli}]
        sifir = [k for k in kalan if (bdir / k).stat().st_size == 0]
        assert sifir == [], f"0 baytlık yedek artıkları kaldı: {sifir}"
        assert w._recent_backup_exists() is False
    finally:
        tdb.close()
        hdb._reset_thread_conn()


def test_KARSIT_D263_DOLU_ama_ACILAMAYAN_yedek_SILINMEZ_sayilmaz_ve_uyarilir(temp_app_data, monkeypatch, caplog):
    """Başka anahtarla şifrelenmiş (anahtar değişiminden önceki) bir yedek açılamaz ama KURTARILABİLİR veridir — rotasyon onu
    silmez, geçerli yedek sayısına katmaz (sağlam yedeğin yerini almaz), günlükte söyler."""
    tdb, hdb = _dbler(monkeypatch, temp_app_data, sifreli=False)
    bdir = temp_app_data / "backups"
    try:
        gecerli = _gecerli_yedekler(
            temp_app_data, tdb, hdb, list(range(16, 1, -1))
        )  # 15 geçerli → 1'i rotasyonla gider
        yabanci = bdir / "pemf_treatment_history_20991231_235959.db"  # en YENİ ad
        yabanci.write_bytes(os.urandom(8192))  # SQLite başlığı yok: başka anahtarla şifreli bir dosyanın görünüşü
        w = _servis(temp_app_data, tdb, hdb)
        with caplog.at_level(logging.WARNING):
            w._cleanup_backups(bdir)
        kalan = {p.name for p in bdir.iterdir()}
        assert yabanci.name in kalan, (
            "dolu ama açılamayan yedek SİLİNDİ — başka anahtarla kurtarılabilir veri yok edildi"
        )
        t_gecerli = sorted(p.name for p in gecerli if p.name.startswith("pemf_treatment_history_"))
        assert t_gecerli[0] not in kalan, "rotasyon çalışmadı (15 geçerli tedavi yedeğinden en eskisi kalmamalı)"
        assert all(n in kalan for n in t_gecerli[1:]), "açılamayan dosya sağlam yedeğin yuvasını aldı"
        assert any("acilamayan" in r.getMessage().lower() for r in caplog.records), (
            "açılamayan yedek günlükte söylenmiyor"
        )
    finally:
        tdb.close()
        hdb._reset_thread_conn()


# ── 3 · yedek GEÇİCİ ada yazılır, doğrulanır, sonra son ada taşınır ───────────────────────────────────────────────


@pytest.mark.parametrize("hangisi", ["tedavi", "hasta"])
@pytest.mark.parametrize("sifreli", [False, True], ids=["duz", "sifreli"])
def test_KRITIK_D263_yedek_SON_ADA_dogrudan_yazilmaz_dogrulanmadan_son_ad_OLUSMAZ(
    temp_app_data, monkeypatch, hangisi, sifreli
):
    tdb, hdb = _dbler(monkeypatch, temp_app_data, sifreli)
    db = tdb if hangisi == "tedavi" else hdb
    bdir = temp_app_data / "backups"
    bdir.mkdir(exist_ok=True)
    hedef = bdir / f"{'pemf_treatment_history_' if hangisi == 'tedavi' else 'pemf_patients_'}20261009_060606.db"
    if sifreli:
        from database.sqlcipher_util import import_sqlcipher

        mod = import_sqlcipher()
    else:
        mod = sqlite3
    gercek = mod.connect
    cagrilar = []

    def _connect(yol, *a, **k):
        if os.path.normcase(str(Path(yol).parent)) == os.path.normcase(str(bdir)):
            cagrilar.append((Path(yol).name, hedef.exists()))
        return gercek(yol, *a, **k)

    monkeypatch.setattr(mod, "connect", _connect)
    try:
        assert db.create_backup(str(hedef)) is True
        assert cagrilar, "aparat: yedek dizinine bağlantı görülmedi"
        assert all(ad != hedef.name for ad, _ in cagrilar), (
            f"yedek SON ADA doğrudan yazılıyor ({cagrilar}) — yazım ortasında süreç ölürse son adda yarım dosya kalır"
        )
        assert all(var is False for _, var in cagrilar), "son ad, yazım ve doğrulama bitmeden oluştu"
        assert hedef.stat().st_size > 0
        assert sorted(p.name for p in bdir.iterdir()) == [hedef.name], "geçici dosya artığı kaldı"
    finally:
        tdb.close()
        hdb._reset_thread_conn()


@pytest.mark.parametrize("hangisi", ["tedavi", "hasta"])
def test_KRITIK_D263_DOGRULAMA_dusunce_yedek_False_son_ad_YOK_gecici_YOK(temp_app_data, monkeypatch, hangisi):
    """Yazılan geçici dosya açılarak doğrulanamazsa (G-Ç / bozuk sayfa) yedek BAŞARISIZDIR: son ad oluşmaz, geçici silinir."""
    tdb, hdb = _dbler(monkeypatch, temp_app_data, sifreli=False)
    db = tdb if hangisi == "tedavi" else hdb
    bdir = temp_app_data / "backups"
    bdir.mkdir(exist_ok=True)
    hedef = bdir / f"{'pemf_treatment_history_' if hangisi == 'tedavi' else 'pemf_patients_'}20261009_070707.db"
    gercek = sqlite3.connect
    sayac = {"n": 0}

    def _connect(yol, *a, **k):
        if os.path.normcase(str(Path(yol).parent)) == os.path.normcase(str(bdir)):
            sayac["n"] += 1
            if sayac["n"] >= 2:  # yazımdan SONRAKİ ilk açılış = doğrulama
                raise sqlite3.OperationalError("disk I/O error")
        return gercek(yol, *a, **k)

    monkeypatch.setattr(sqlite3, "connect", _connect)
    try:
        sonuc = db.create_backup(str(hedef))
        assert sayac["n"] >= 2, f"yazılan yedek AÇILARAK doğrulanmadı (yedek dizinine {sayac['n']} bağlantı)"
        assert sonuc is False, "doğrulanamayan yedek 'başarılı' döndü"
        assert list(bdir.iterdir()) == [], f"doğrulanamayan yedekten artık kaldı: {[p.name for p in bdir.iterdir()]}"
    finally:
        tdb.close()
        hdb._reset_thread_conn()
