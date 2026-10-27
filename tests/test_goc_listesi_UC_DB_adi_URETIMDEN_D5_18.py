# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.18 (B-10.88) KAPISI — veri kökü göç listesindeki ÜÇ veritabanı adı da ÜRETİMDEN türetilir.

ARIZA (DENETİM-10 B-10.88): `tests/test_data_dir_migration.py::test_goc_listesi_URETIM_adlarini_kullanir` yalnız HASTA DB adını
(`PatientDatabase.__init__` varsayılanı) üretimden türetiyordu. Tedavi geçmişi (`pemf_treatment_history.db`) ve hekim/operatör
(`auth_users.db`) adları göç listesinde (`path_utils._GOC_DOSYALARI`) ELLE yazılı: `TreatmentHistoryDB` ya da `AuthDB` dosya
adı değişip literal testler de güncellenince, liste unutulursa göç o veritabanını SESSİZCE taşımaz (eski kullanıcı-başına
kökteki tıbbi kayıt yeni makine-geneli kökte görünmez) ve kapı YEŞİL kalırdı (ölçüldü).
Ayrıca o modülün tamamı `skipif(Windows değil)` — ad kilidi platformdan BAĞIMSIZDIR ama Linux CI'da hiç koşmuyordu; bu dosya
platform atlaması taşımaz.

KAPI: adlar GERÇEK örneklerin `db_path.name`inden (geçici kökte) alınır; göç listesinde OLMALI, şifreli olanlar (tedavi,
hasta) `_GOC_SIFRELI`de OLMALI, `auth_users.db` (düz SQLite) OLMAMALI.
MUTASYON: `treatment_history_db.py`/`auth_db.py`deki dosya adını değiştirmek (liste unutulur) → KIRMIZI.
"""

from __future__ import annotations

import inspect


def test_KRITIK_D518_goc_listesi_UC_DB_adini_URETIMDEN_alir(temp_app_data):
    from database.auth_db import AuthDB
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from utils import path_utils

    tedavi = TreatmentHistoryDB(temp_app_data)
    try:
        tedavi_adi = tedavi.db_path.name
    finally:
        tedavi.close()
    auth_adi = AuthDB(temp_app_data).db_path.name
    hasta_adi = inspect.signature(PatientDatabase.__init__).parameters["db_file"].default

    for ad, ne in ((tedavi_adi, "tedavi geçmişi"), (auth_adi, "hekim/operatör"), (hasta_adi, "hasta")):
        assert ad in path_utils._GOC_DOSYALARI, (
            f"göç listesi üretimdeki {ne} DB adını ('{ad}') ARAMIYOR → veri kökü göçünde o kayıtlar TAŞINMAZ "
            f"(liste: {path_utils._GOC_DOSYALARI})"
        )
    assert {tedavi_adi, hasta_adi} <= set(path_utils._GOC_SIFRELI), (
        "şifreli DB'ler `_GOC_SIFRELI`de yok → anahtar uyumu denetlenmeden körlemesine kopyalanır"
    )
    assert auth_adi not in path_utils._GOC_SIFRELI, "auth_users.db düz SQLite — şifreli kümesinde olmamalı"
    assert len(set(path_utils._GOC_DOSYALARI)) == len(path_utils._GOC_DOSYALARI), (
        f"göç listesinde yinelenen ad: {path_utils._GOC_DOSYALARI}"
    )
