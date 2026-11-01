# -*- coding: utf-8 -*-
"""KP-1 · `servers/firmware_manager.py` (yardımcı kollar; oto-firmware KAPALI kalır) · sözleşmeler: yakma penceresi okunamazsa sağlık
"yakılmıyor" der (ASLA düşmez) · firmware kaydı: kök yoksa okuma None / yazma HATA (Y82: yarım kayıt yazılamazsa yakılmaz) / silme sessiz,
bozuk ya da nesne olmayan kayıt "bozuk" sayılır, silinemeyen kayıt günlüklenir · Y80: bozuk son-yakma kaydı "bu ikili denendi" sayılır
(fail-closed) · uyum varlığı adresi pin dışındaysa ya da boyut tavanını aşarsa kural OKUNMAZ (None — bekle) · geçici dosya silinemese de
geçici dizin temizlenir · yedek dizini çözülemezse None · ilk yedek adı: yedek yoksa boş, yazılamazsa uyarı · budamada silinemeyen yedek
diğerlerini engellemez, İLK yedek hiç budanmaz.

Ağ / kart / ST-Link / gerçek veri kökü YOK: uyum varlığı açıcısı (`update_manager._pinli_ac`), pin denetimi, dosya silme ve veri kökü
çözücüsü EN ALT katta sahte; dizinler tmp.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest
from servers import firmware_manager as fm
from servers import update_manager as um


def test_yakma_penceresi_okunamazsa_SAGLIK_dusmez_yakilmiyor_der(monkeypatch):
    from utils import firmware_yakma_penceresi as pencere

    monkeypatch.setattr(pencere, "acik_mi", lambda: (_ for _ in ()).throw(RuntimeError("pencere bozuk")))
    assert fm._yakiliyor_mu() is False and fm.durum()["yakiliyor"] is False


def test_KRITIK_kok_YOKSA_kayit_okunmaz_YAZILAMAZ_silme_sessiz(tmp_path):
    assert fm._kayit_oku(None, fm.SON_YAKMA_DOSYASI) is None
    with pytest.raises(OSError, match="çözülemedi"):
        fm._kayit_yaz(None, fm.YARIM_YAKMA_DOSYASI, {"a": 1})  # Y82: yarım kayıt yazılamazsa çağıran YAKMAZ
    fm._kayit_sil(None, fm.YARIM_YAKMA_DOSYASI)


def test_bozuk_ya_da_nesne_olmayan_kayit_BOZUK_sayilir_Y80_denendi_fail_closed(tmp_path, monkeypatch, caplog):
    (tmp_path / fm.SON_YAKMA_DOSYASI).write_text("{bozuk", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger=fm.logger.name):
        assert fm._kayit_oku(tmp_path, fm.SON_YAKMA_DOSYASI) == {"bozuk": True}
    assert any("bozuk kayıt" in r.getMessage() for r in caplog.records)
    monkeypatch.setattr(fm, "_yedek_dizini", lambda: tmp_path)
    assert fm._ayni_sha_denendi_mi({"sha256": "abc"}) == {"bozuk": True}, (
        "okunamayan son-yakma kaydı aynı ikilinin KÖR yeniden yakılmasına izin verdi"
    )
    (tmp_path / fm.SON_YAKMA_DOSYASI).write_text("[1, 2]", encoding="utf-8")
    assert fm._kayit_oku(tmp_path, fm.SON_YAKMA_DOSYASI) == {"bozuk": True}


def test_silinemeyen_kayit_GUNLUKLENIR(tmp_path, monkeypatch, caplog):
    gercek = Path.unlink
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self, *a, **k: (
            (_ for _ in ()).throw(PermissionError("kilitli"))
            if self.name == fm.YARIM_YAKMA_DOSYASI
            else gercek(self, *a, **k)
        ),
    )
    with caplog.at_level(logging.WARNING, logger=fm.logger.name):
        fm._kayit_sil(tmp_path, fm.YARIM_YAKMA_DOSYASI)
    assert any("firmware kaydı silinemedi" in r.getMessage() for r in caplog.records)


def test_uyum_varligi_PIN_DISI_adreste_ve_BOYUT_tavaninda_OKUNMAZ(monkeypatch, caplog):
    monkeypatch.setattr(um, "_validate_installer_url", lambda url: (False, "host pin dışı"))
    with caplog.at_level(logging.ERROR, logger=fm.logger.name):
        assert fm.manifest_oku() is None
    assert any("pin dışında" in r.getMessage() for r in caplog.records)
    monkeypatch.setattr(um, "_validate_installer_url", lambda url: (True, ""))

    class _Yanit(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        um, "_pinli_ac", lambda url, timeout=None, headers=None: _Yanit(b"x" * (um._MAX_MANIFEST_BYTES + 1))
    )
    assert fm.manifest_oku() is None, "tavanı aşan manifest okundu"
    monkeypatch.setattr(
        um, "_pinli_ac", lambda url, timeout=None, headers=None: _Yanit(json.dumps({"firmware": {}}).encode())
    )
    assert fm.manifest_oku() == {"firmware": {}}


def test_gecici_dosya_silinemese_de_GECICI_DIZIN_temizlenir(tmp_path, monkeypatch, caplog):
    dizin_silinen: list = []
    monkeypatch.setattr(um, "_discard_temp_dir", lambda yol: dizin_silinen.append(Path(yol)))
    hedef = tmp_path / "pemf_upd_x" / "pemf_fw.bin"
    gercek = Path.unlink
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self, *a, **k: (
            (_ for _ in ()).throw(PermissionError("AV")) if self.name == "pemf_fw.bin" else gercek(self, *a, **k)
        ),
    )
    with caplog.at_level(logging.WARNING, logger=fm.logger.name):
        fm._gecici_sil(hedef)
    assert dizin_silinen == [hedef], "geçici dizin temizliği atlandı (yetim pemf_upd_* dizinleri — D1.115)"
    assert any("geçici firmware dosyası silinemedi" in r.getMessage() for r in caplog.records)


def test_yedek_dizini_COZULEMEZSE_None(monkeypatch, caplog):
    import utils.path_utils as pu

    monkeypatch.setattr(pu, "get_app_data_directory", lambda: (_ for _ in ()).throw(RuntimeError("kök yok")))
    with caplog.at_level(logging.WARNING, logger=fm.logger.name):
        assert fm._yedek_dizini() is None
    assert any("yedek dizini çözülemedi" in r.getMessage() for r in caplog.records)


def test_ilk_yedek_adi_yedek_YOKSA_bos_YAZILAMAZSA_uyari(tmp_path, monkeypatch, caplog):
    assert fm._ilk_yedek_adi(tmp_path, []) == ""
    y = tmp_path / "pemf_yedek_20261101_100000.bin"
    y.write_bytes(b"x")
    gercek = Path.write_text
    monkeypatch.setattr(
        Path,
        "write_text",
        lambda self, *a, **k: (
            (_ for _ in ()).throw(PermissionError("salt okunur"))
            if self.name == fm.ILK_YEDEK_DOSYASI
            else gercek(self, *a, **k)
        ),
    )
    with caplog.at_level(logging.WARNING, logger=fm.logger.name):
        assert fm._ilk_yedek_adi(tmp_path, [y]) == y.name
    assert any("ilk firmware yedeğinin adı kaydedilemedi" in r.getMessage() for r in caplog.records)


def test_KRITIK_budamada_ILK_yedek_hic_silinmez_silinemeyen_digerlerini_ENGELLEMEZ(tmp_path, monkeypatch, caplog):
    adlar = [f"pemf_yedek_202611{g:02d}_100000.bin" for g in range(1, 9)]  # 8 yedek, en eskisi 01
    for a in adlar:
        (tmp_path / a).write_bytes(b"x")
    gercek = Path.unlink
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self, *a, **k: (
            (_ for _ in ()).throw(PermissionError("kilitli")) if self.name == adlar[1] else gercek(self, *a, **k)
        ),
    )
    with caplog.at_level(logging.WARNING, logger=fm.logger.name):
        fm._yedekleri_buda(tmp_path, tut=3)
    kalan = sorted(p.name for p in tmp_path.glob("pemf_yedek_*.bin"))
    assert adlar[0] in kalan, "İLK (asıl saha) firmware yedeği budandı"
    assert adlar[1] in kalan and adlar[2] not in kalan and adlar[3] not in kalan and adlar[4] not in kalan, (
        "silinemeyen yedek döngüyü durdurdu"
    )
    assert kalan[-3:] == adlar[-3:]
    assert any("eski firmware yedeği silinemedi" in r.getMessage() for r in caplog.records)
