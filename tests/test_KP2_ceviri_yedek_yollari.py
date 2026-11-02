# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KP-2 · apps/backend/utils/ceviri.py · sözleşmeler: okunamayan dil kataloğu boş sayılır ve o dilin anahtarları TÜRKÇE
yedeğe düşer (günlüğe ERROR) · bozuk istek nesnesinde dil `tr` · cihaz dili diske yazılamazsa ASIL hata yükselir, geçici dosya
kalmaz, unlink hatası asıl hatayı gölgelemez · sayıya çevrilemeyen `count` çoğul (`_other`) biçimi seçer · üretimde (katı
kip kapalı) eksik yer tutucu boş dizgeye düşer, KeyError YOK.

Sahte yalnız EN ALT katta: donmuş EXE platform işareti (`sys.frozen` / `sys._MEIPASS` → tmp katalog dizini), dosya sistemi
(hedef yolda DİZİN → gerçek `os.replace` hatası), `os.unlink`, ortam değişkenleri.
"""

from __future__ import annotations

import json
import logging
import sys
from types import SimpleNamespace

import pytest
from utils import ceviri


@pytest.fixture()
def katalog_onbellegi_geri(monkeypatch):
    """Testin yeniden yüklediği katalog önbelleği test sonunda ESKİ nesneye döner (sonraki testler gerçek kataloğu görür)."""
    monkeypatch.setattr(ceviri, "_kataloglar", ceviri._kataloglar)
    yield


def test_bozuk_EN_katalogu_bos_sayilir_EN_anahtarlar_TURKCE_yedege_duser(
    tmp_path, monkeypatch, caplog, katalog_onbellegi_geri
):
    kat = tmp_path / "i18n"
    kat.mkdir()
    (kat / "tr.json").write_text(json.dumps({"ornek": {"selam": "Merhaba {{ad}}"}}), encoding="utf-8")
    (kat / "en.json").write_text("{bozuk", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ceviri.katalog_dizini() == kat
    with caplog.at_level(logging.ERROR, logger=ceviri.__name__):
        assert ceviri.kataloglar(yeniden=True) == {"tr": {"ornek.selam": "Merhaba {{ad}}"}, "en": {}}
    assert any("katalog okunamadi" in r.getMessage() and r.levelno == logging.ERROR for r in caplog.records)
    assert ceviri.t("ornek.selam", dil="en", ad="Pamuk") == "Merhaba Pamuk"


def test_bozuk_istek_nesnesi_dili_TR(monkeypatch):
    assert ceviri.istekten_dil(object()) == "tr"
    assert ceviri.istekten_dil(SimpleNamespace(headers=None, query_params={})) == "tr"
    # KARŞIT: düzgün istek nesnesinde başlık okunur
    assert ceviri.istekten_dil(SimpleNamespace(headers={"X-PEMF-Dil": "en"}, query_params={})) == "en"


def _kok():
    return ceviri._veri_koku()


def test_cihaz_dili_YAZILAMAZSA_hata_yukselir_gecici_dosya_kalmaz_ayar_degismez():
    hedef = _kok() / ceviri.CIHAZ_DILI_DOSYASI
    hedef.mkdir(parents=True)
    with pytest.raises(OSError):
        ceviri.cihaz_dili_yaz("en")
    assert not list(_kok().glob("*.tmp")), "geçici dil dosyası artığı kaldı"
    assert ceviri.cihaz_dili_ayarli_mi() is None and ceviri.cihaz_dili() == "tr"


def test_cihaz_dili_gecici_dosya_SILINEMESE_de_ASIL_hata_yukselir(monkeypatch):
    (_kok() / ceviri.CIHAZ_DILI_DOSYASI).mkdir(parents=True)
    istenen = []

    def _kilitli(yol, *a, **k):
        istenen.append(str(yol))
        raise PermissionError(13, "kp2-sahte-unlink-kilitli", str(yol))

    monkeypatch.setattr(ceviri.os, "unlink", _kilitli)
    with pytest.raises(OSError) as hata:
        ceviri.cihaz_dili_yaz("en")
    assert "kp2-sahte-unlink-kilitli" not in str(hata.value)
    assert len(istenen) == 1 and istenen[0].endswith(".tmp")


@pytest.mark.parametrize(
    "count, beklenen", [("çok", "çok records"), ([1], "[1] records"), (1, "1 record"), (2, "2 records")]
)
def test_count_SAYI_degilse_COGUL_secilir(count, beklenen):
    assert ceviri.t("ai.rapor.kayit", dil="en", count=count) == beklenen


def test_uretimde_eksik_yer_tutucu_BOS_dizgeye_duser_KeyError_yok(monkeypatch):
    ham = ceviri.kataloglar()["tr"]["ayarlar.arayuzDili.yazilamadi"]
    assert "{{neden}}" in ham
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PEMF_I18N_KATI", raising=False)
    assert ceviri.t("ayarlar.arayuzDili.yazilamadi", dil="tr") == ham.replace("{{neden}}", "")
    # KARŞIT: katı kipte eksik yer tutucu sessiz geçmez
    monkeypatch.setenv("PEMF_I18N_KATI", "1")
    with pytest.raises(KeyError):
        ceviri.t("ayarlar.arayuzDili.yazilamadi", dil="tr")
