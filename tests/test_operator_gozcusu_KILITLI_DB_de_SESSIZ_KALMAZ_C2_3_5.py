# -*- coding: utf-8 -*-
"""C2-3.5 (2-C incelemesi A3 · 2-B2 O-A2.4 gözcüsü `2cccae2`) — conftest operatör sızıntı gözcüsü, test SONUNDA tekil auth DB'si
okunamıyorsa SESSİZ kalmaz (sahte yeşil yok).

ÖLÇÜLEN KUSUR: `tests/conftest.py` `_operator_sizintisini_geri_al` test sonundaki okuma `None` (kilit / bozuk / izin) dönünce
"karar verilmez" deyip ÇIKAR. Ölçüldü (sahte test `_inceleme/sonda/test_zz_a3_d8i_kilitte_gozcu.py`): bir test operatör kaydedip tekil
DB'yi kilitli bırakınca test YEŞİL geçti, gözcü kaydı BOŞ, operatör sonraki testte hâlâ kayıtlıydı (Kural 2 sessizce çevrildi) — gözcünün
önlemek için var olduğu sınıf. Test başında okunamayan durum (taban yok) değişmez.

Meta kapı (OA24 deseni): 1. kol işaretli (`operator_sizintisi_beklenir` — kırmızıyı kaldırır, kayıt aynen), operatör bırakır ve DB'yi
kilitli bırakır; KRİTİK 2. kol kilidi kaldırır, gözcü kaydında 1. kolu arar, temizler. KARŞIT: temiz test kayda girmez.
"""

from __future__ import annotations

import sqlite3
import sys

import pytest

_KILIT: dict = {}
SIZAN = "sizan.kilitte@c235.test"


def _gozcu_kaydi():
    c = sys.modules.get("conftest")
    assert c is not None and hasattr(c, "_OPERATOR_SIZINTI_KAYDI"), "aparat: conftest gözcü kaydı yok"
    return c._OPERATOR_SIZINTI_KAYDI


@pytest.mark.operator_sizintisi_beklenir
def test_C235_1_kol_operator_birakir_ve_tekil_DB_kilitli_kalir():
    from database.auth_db import get_auth_db

    adb = get_auth_db()
    assert adb.enroll_operator(SIZAN, "S", "123456") == (True, None)
    kc = sqlite3.connect(str(adb.db_path), isolation_level=None, timeout=1)
    kc.execute("PRAGMA locking_mode=EXCLUSIVE")
    kc.execute("BEGIN EXCLUSIVE")
    kc.execute("UPDATE device_operators SET last_active = last_active")
    _KILIT["kc"] = kc


def test_KRITIK_C235_2_kol_gozcu_KILITLI_DB_de_sizintiyi_KAYDETTI():
    from database.auth_db import get_auth_db
    from servers import operator_tokens

    kc = _KILIT.pop("kc", None)
    if kc is not None:
        kc.execute("ROLLBACK")
        kc.close()
    kayit = [k for k in _gozcu_kaydi() if k[0].endswith("test_C235_1_kol_operator_birakir_ve_tekil_DB_kilitli_kalir")]
    hala_kayitli = SIZAN in [o["email"] for o in get_auth_db().list_operators(kati=True)]
    get_auth_db().remove_operator(SIZAN)  # temizlik (1. kolun bıraktığı)
    operator_tokens.iptal_email(SIZAN)
    assert kc is not None, "aparat: 1. kol kilidi kurmadı (sıra?)"
    assert hala_kayitli, "aparat: 1. kolun operatörü yok — sızıntı kurulamadı"
    assert kayit, (
        "gözcü, test sonunda tekil auth DB'si KİLİTLİYKEN SESSİZ kaldı: 1. kolun bıraktığı operatör kaydedilmedi (sahte yeşil; "
        "sonraki testler 'kayıtlı operatörlü cihaz' kipinde koşar)"
    )


def test_KARSIT_C235_temiz_test_gozcu_kaydina_GIRMEZ():
    from database.auth_db import get_auth_db

    adb = get_auth_db()
    assert adb.enroll_operator("temiz@c235.test", "T", "123456") == (True, None)
    adb.remove_operator("temiz@c235.test")


def test_KARSIT_C235_temiz_teste_kayit_YOK():
    assert not [k for k in _gozcu_kaydi() if "temiz_test_gozcu_kaydina_GIRMEZ" in k[0]], _gozcu_kaydi()
