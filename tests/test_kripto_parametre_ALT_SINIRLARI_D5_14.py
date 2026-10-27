# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.14 (B-10.16) KAPISI — PIN ve yedek parolası kripto parametrelerine MUTLAK alt sınır (davranışla).

ARIZA (DENETİM-10 B-10.16): `_PBKDF2_ITERS=1`, `_KDF_ROUNDS=1`, `_PIN_LOCK_SECONDS=1`, `MIN_PAROLA=5` mutantlarında 227 test
YEŞİL kalıyordu: kapılar değerleri sabitin KENDİSİNDEN okuyor (`db._PIN_LOCK_SECONDS + 10`, `MIN_PAROLA - 1`) — sabit düşünce
test de birlikte düşüyordu. Yerel kaba kuvvet / çevrimdışı parola kırma direnci sessizce kaybolabilirdi.

KAPI: asgari değerler BU DOSYADA sabit (ürün sabitinden OKUNMAZ) ve ürünün GERÇEK yolunda ölçülür:
  · PIN özeti: `enroll_operator` + `verify_pin` sırasında `hashlib.pbkdf2_hmac`a giden tur sayısı ≥ 200 000,
  · yedek paketi: `encrypt_bundle` / `decrypt_bundle`ın türettiği anahtarın tur sayısı ≥ 200 000,
  · PIN kilidi: 5 hatadan sonra 299 sn ileride HÂLÂ kilitli (kilit ≥ 300 sn),
  · yedek parolası: 11 karakterlik (4+ farklı karakter) parola REDDEDİLİR, 12 karakterlik kabul.
Değerlerin ARTIRILMASI serbesttir (alt sınır); azaltılması KIRMIZI.
MUTASYON: dört sabitten biri düşürülür ya da çağrı yerine sabit yerine küçük literal yazılır → KIRMIZI.
"""

from __future__ import annotations

import hashlib
import time

import pytest

#: ⚠️ ASGARİLER BURADA — ürün sabitinden türetilmez (sabit düşerse kapı da düşmesin).
PIN_TUR_ASGARI = 200_000
YEDEK_TUR_ASGARI = 200_000
PIN_KILIT_SN_ASGARI = 300
YEDEK_PAROLA_ASGARI = 12


@pytest.fixture()
def tur_kaydi(monkeypatch):
    """`hashlib.pbkdf2_hmac` çağrılarının tur sayısını kaydeder (sonuç GERÇEK işlevden — davranış değişmez)."""
    gercek = hashlib.pbkdf2_hmac
    kayit: list = []

    def _kayitci(ad, parola, tuz, tur, *a, **k):
        kayit.append(int(tur))
        return gercek(ad, parola, tuz, tur, *a, **k)

    monkeypatch.setattr(hashlib, "pbkdf2_hmac", _kayitci)
    return kayit


def test_KRITIK_D514_PIN_ozeti_GERCEK_yolda_en_az_200k_tur(temp_app_data, tur_kaydi):
    from database.auth_db import AuthDB

    db = AuthDB(temp_app_data)
    ok, err = db.enroll_operator("d514@klinik.com", "Dr. D514", "135790")
    assert ok, f"aparat: operatör kaydı başarısız: {err}"
    assert db.verify_pin("d514@klinik.com", "135790") == (True, None), "aparat: doğru PIN geçmedi"
    assert tur_kaydi, "aparat: PIN yolu pbkdf2_hmac ÇAĞIRMADI (özet başka yoldan mı?)"
    assert min(tur_kaydi) >= PIN_TUR_ASGARI, (
        f"PIN özeti {min(tur_kaydi)} turla hesaplanıyor (< {PIN_TUR_ASGARI}) — 6 haneli PIN çevrimdışı saniyeler içinde kırılır"
    )


def test_KRITIK_D514_yedek_paketi_anahtari_en_az_200k_tur(tur_kaydi):
    from utils.data_export import decrypt_bundle, encrypt_bundle

    parola = "d514-yedek-parolasi-uzun"
    blob = encrypt_bundle({"surum": 1, "veri": [1, 2, 3]}, parola)
    sifreleme = list(tur_kaydi)
    assert decrypt_bundle(blob, parola)["veri"] == [1, 2, 3], "aparat: paket geri açılamadı"
    assert sifreleme, "aparat: encrypt_bundle pbkdf2_hmac ÇAĞIRMADI"
    assert min(tur_kaydi) >= YEDEK_TUR_ASGARI, (
        f"yedek paketi anahtarı {min(tur_kaydi)} turla türetiliyor (< {YEDEK_TUR_ASGARI}) — kliniğin TÜM hasta geçmişini "
        "taşıyan dosyanın tek koruması parola"
    )


def test_KRITIK_D514_PIN_kilidi_en_az_300_sn(temp_app_data, monkeypatch):
    from database.auth_db import AuthDB

    db = AuthDB(temp_app_data)
    e = "kilit@klinik.com"
    assert db.enroll_operator(e, "Dr. Kilit", "246802")[0]
    simdi = time.time()
    monkeypatch.setattr(time, "time", lambda: simdi)
    sonuc = None
    for _ in range(
        10
    ):  # kilit en geç birkaç hatada devreye girer (eşik ürün sabiti — burada SINIR değil kilit süresi ölçülür)
        sonuc = db.verify_pin(e, "000000")
        if sonuc == (False, "locked"):
            break
    assert sonuc == (False, "locked"), f"aparat: 10 hatada kilit devreye girmedi: {sonuc}"
    monkeypatch.setattr(time, "time", lambda: simdi + PIN_KILIT_SN_ASGARI - 1)
    assert db.verify_pin(e, "246802") == (False, "locked"), (
        f"PIN kilidi {PIN_KILIT_SN_ASGARI} sn dolmadan AÇILDI — 10^6'lık PIN uzayı yerel kaba kuvvete açık"
    )


def test_KRITIK_D514_yedek_parolasi_en_az_12_karakter():
    from utils.data_export import MIN_PAROLA, parola_gecerli_mi

    assert MIN_PAROLA >= YEDEK_PAROLA_ASGARI, f"MIN_PAROLA {MIN_PAROLA} < {YEDEK_PAROLA_ASGARI}"
    on_bir = "kedi-pemf-1"  # 11 karakter, 4+ farklı karakter (yalnız UZUNLUK kuralına takılmalı)
    assert len(on_bir) == YEDEK_PAROLA_ASGARI - 1 and len(set(on_bir)) >= 4
    assert parola_gecerli_mi(on_bir)[0] is False, "11 karakterlik yedek parolası KABUL edildi"
    assert parola_gecerli_mi(on_bir + "x")[0] is True, "karşıt: 12 karakterlik geçerli parola reddedildi"
