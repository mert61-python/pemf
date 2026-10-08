# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""O-A2.4 (2-B incelemesi → 2-B2) — cihaz operatör kaydı testler arası SIZMAZ (conftest `_operator_kaydi_sizmaz`).

ÖLÇÜLEN KUSUR: `database.auth_db.get_auth_db()` süreç-tekildir; bir testin bıraktığı kayıtlı operatör süitin geri kalanını
"kayıtlı operatörlü cihaz" kipine çevirir (`kayitli_operator_var()` True → Kural 2 dalı yerine kimlik dalı). Gözcü (operatör
kaydeden 24 dosya): `test_operator_identity_server_side` dosya sonunda `a@klinik.com` bırakıyordu, sıradaki dosya kayıtlı
operatörlü cihazda başlıyordu; 2-B'de `test_operators_api` / `test_audit_trail` aynı sınıftan `test_session_lifecycle`'ı
sıraya bağlı kırmızı yapmıştı.

SÖZLEŞME: bir test operatör kaydedip temizlemeden bitse de sonraki test cihazı kendinden önceki hâliyle görür (operatörsüz
klinik → Kural 2), sızan operatörün jetonu ölür ve gözcü sızıntıyı KAYDEDER (işaretsiz testte KIRMIZI). Kollar SIRALI (pytest
dosya içi tanım sırası; süitte rastgele sıra eklentisi YOK): 1. kol bilerek sızdırır (`operator_sizintisi_beklenir` — yalnız
kırmızıyı kaldırır), 2. kol temiz görmeli. Gerçek ürün yolu: kayıt `AuthDB.enroll_operator`, jeton `operator_tokens.uret`,
kip sorusu `servers.auth.kayitli_operator_var`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_SIZAN = "sizan.hekim@oa24.test"
_JETON: list = []


def _kayitli_conftest():
    """pytest'in YÜKLEDİĞİ conftest (`import conftest` başka kipte ikinci kopya yaratabilir → kör kayıt)."""
    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (_KOK / "tests" / "conftest.py").resolve(), (
        "kayıtlı tests/conftest.py bulunamadı — gözcü kaydı okunamaz"
    )
    return c


@pytest.mark.operator_sizintisi_beklenir
def test_OA24_1_kol_operatoru_KAYITLI_birakir():
    from database.auth_db import get_auth_db
    from servers import auth, operator_tokens

    ok, hata = get_auth_db().enroll_operator(_SIZAN, "Dr. Sızan", "123456")
    assert ok, f"aparat: operatör kaydedilemedi ({hata})"
    _JETON.append(operator_tokens.uret(_SIZAN))
    assert auth.kayitli_operator_var() is True, "aparat: kayıt kipi değişmedi"
    # sızıntı deseni (O-A2.4): temizlemeden test biter


def test_KRITIK_OA24_2_kol_sonraki_test_OPERATORSUZ_cihazda_baslar():
    from database.auth_db import get_auth_db
    from servers import auth, operator_tokens

    kalan = [o["email"] for o in get_auth_db().list_operators(kati=True)]
    assert _SIZAN not in kalan, f"önceki testin bıraktığı operatör sonraki teste SIZDI: {kalan}"
    assert auth.kayitli_operator_var() is False, (
        "önceki testin operatörü cihazı 'kayıtlı operatörlü' kipe çevirdi — Kural 2 testleri sıraya bağlı kırmızı/maskeli olur"
    )
    assert _JETON and operator_tokens.cozumle(_JETON[0]) == "", "sızan operatörün jetonu hâlâ geçerli"
    kayit = [
        k
        for k in _kayitli_conftest()._OPERATOR_SIZINTI_KAYDI
        if k[0].endswith("test_OA24_1_kol_operatoru_KAYITLI_birakir")
    ]
    assert kayit and kayit[-1][1:] == ("test", (_SIZAN,), True), f"gözcü sızıntıyı KAYDETMEDİ: {kayit}"


def test_KARSIT_OA24_kendi_temizleyen_test_KAYDA_girmez():
    from database.auth_db import get_auth_db

    adb = get_auth_db()
    try:
        assert adb.enroll_operator("temiz@oa24.test", "Dr. Temiz", "123456")[0]
    finally:
        adb.remove_operator("temiz@oa24.test")


def test_KARSIT_OA24_temizleyen_teste_gozcu_kaydi_YOK():
    kayit = [k for k in _kayitli_conftest()._OPERATOR_SIZINTI_KAYDI if "test_KARSIT_OA24_kendi_temizleyen" in k[0]]
    assert kayit == [], f"kendi temizleyen test sızıntı sayıldı (gözcü aşırı): {kayit}"
