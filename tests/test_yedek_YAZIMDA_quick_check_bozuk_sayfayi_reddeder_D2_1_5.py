# -*- coding: utf-8 -*-
"""D2-1.5 (2-D incelemesi, A1) — KÖR KAPI: "yazım anında `PRAGMA quick_check`" (D2.63) kilitli değil.

`yedek_yaz` geçici dosyayı `yedek_acilir_mi(…, tam=True)` ile doğrular. `tam=False` (yalnız şema okuması) mutantı 2-D kapılarında
(D2.63 + D2.61 + retention) YEŞİL kalır [ÖLÇTÜM kayit/K2_mutasyon.txt a1k2_m1: 32 passed]: yazım sırasında veri sayfası bozulan bir
yedek (başlık + sqlite_master sağlam) "doğrulandı" sayılıp son ada taşınır ve rotasyonda sağlam bir yedeğin yuvasını alır.
Bu kol bozulmayı EN ALT katta, gerçek baytla kurar: yazım bittikten sonra, doğrulamadan hemen önce geçici dosyanın SON sayfasında 256 bayt
XOR'lanır (sayfa 1 = başlık + şema DOKUNULMAZ). Beklenen: create_backup False, son ad yok, geçici yok.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


@pytest.mark.parametrize("hangisi", ["tedavi", "hasta"])
def test_KRITIK_yazimda_veri_sayfasi_bozulan_yedek_SON_ADA_tasinmaz(temp_app_data, monkeypatch, hangisi):
    from database import patient_database as pdb
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb
    from database import yedek_dosyasi as yd

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = thdb.TreatmentHistoryDB(temp_app_data)
    hdb = pdb.PatientDatabase(str(temp_app_data / "patients.db"))
    try:
        for i in range(150):
            tdb.start_session(treatment_mode="Manuel", patient_name=f"D215-{i:03d}-" + "q" * 120)
            hdb.add_patient({"name": f"D215-{i:03d}", "species": "Kedi", "owner_name": "w" * 120})
        db = tdb if hangisi == "tedavi" else hdb
        bdir = temp_app_data / "backups"
        bdir.mkdir(exist_ok=True)
        hedef = bdir / f"{'pemf_treatment_history_' if hangisi == 'tedavi' else 'pemf_patients_'}20261009_090909.db"
        gercek = yd.yedek_acilir_mi
        bozuldu = []

        def _bozup_dogrula(yol, *a, **k):
            if str(yol).endswith(yd.GECICI_EK) and not bozuldu:
                # Son sayfanın SONUNDAKİ hücre içeriği alanı (SQLite hücreleri sayfa sonundan geriye yazar; sayfa başındaki boşluk
                # bozulsa quick_check görmez — aparat kendi kırmızısını ürettiğini aşağıda `bozuldu` + HEAD-yeşil ile kanıtlar).
                boyut = os.path.getsize(yol)
                with open(yol, "r+b") as f:
                    f.seek(boyut - 300)
                    eski = f.read(256)
                    f.seek(boyut - 300)
                    f.write(bytes(b ^ 0x5A for b in eski))
                bozuldu.append(Path(yol).name)
            return gercek(yol, *a, **k)

        monkeypatch.setattr(yd, "yedek_acilir_mi", _bozup_dogrula)
        sonuc = db.create_backup(str(hedef))
        assert bozuldu, "aparat: geçici dosya doğrulamadan önce bozulamadı"
        assert sonuc is False and not hedef.exists(), (
            f"yazımda veri sayfası bozulan yedek 'doğrulandı' sayılıp SON ADA taşındı (create_backup={sonuc}) — "
            "yazım anında quick_check yapılmıyor (yalnız şema okuması)"
        )
        assert not list(bdir.glob("*" + yd.GECICI_EK)), "bozuk geçici dosya kaldı"
    finally:
        tdb.close()
        hdb._reset_thread_conn()
