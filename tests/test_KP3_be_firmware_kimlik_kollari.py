# -*- coding: utf-8 -*-
"""KP-3 C · `servers/firmware_manager.py` (yarım yakma kurtarması) + `utils/stm32_kimlik.py` (uyum kararı) kapsanmayan kolları — her test
bir DAVRANIŞ iddiası. ⚠️ Ürün kodu DEĞİŞMEDİ; gerçek kart / ST-Link YOK — `stm_yakma.yedekten_geri_don` ve kayıt yazıcısı sahtelenir.

- Sürüm eşitliği: ayrıştırılamayan sürüm hedefe "ulaşılmış" SAYILMAZ; `2.4` ≡ `2.4.0`.
- Yarım yakma (Y82): yedekten geri dönüş doğrulandıysa yarım kayıt silinir ve sonuç "geri_donuldu" — Y80 kaydı yazılamasa bile (uyarı);
  geri dönüş başarısızsa "basarisiz" + kodlu ayrıntı (yarım kayıt KALIR → sonraki açılış yine dener / elle kurtarma).
- Uyum kararı: kimlik yok + el sıkışma doğrulaması yanıtsız → None + FW-KIMLIK eylem metni; kanal ve tahmini paket boyu uyan eski
  (maskesiz) banner → uyumlu.
"""

from __future__ import annotations

import logging

from servers import firmware_manager as fm
from utils import stm32_kimlik as sk
from utils import stm_yakma as sy


def test_surum_esitligi_ayristirilamayan_ulasilmis_sayilmaz():
    assert fm._ayni_surum("bilinmiyor", "2.4") is False
    assert fm._ayni_surum("2.4", "2.4.0") is True


def _yarim_kayit(monkeypatch, tmp_path):
    monkeypatch.setattr(fm, "_yedek_dizini", lambda: tmp_path)
    yedek = tmp_path / "onceki.bin"
    yedek.write_bytes(b"\x01" * 16)
    fm._kayit_yaz(
        tmp_path, fm.YARIM_YAKMA_DOSYASI, {"hedef": "2.5", "yedek": str(yedek), "sha256": "ab" * 32, "zaman": "t"}
    )
    return yedek


def test_yarim_yakma_geri_donus_dogrulandi_y80_yazilamasa_da(monkeypatch, tmp_path, caplog):
    _yarim_kayit(monkeypatch, tmp_path)
    monkeypatch.setattr(
        sy, "yedekten_geri_don", lambda *a, **k: sy.Sonuc(sy.TAMAM, "geri yazıldı ve doğrulandı", adimlar=["yaz"])
    )
    gercek_yaz = fm._kayit_yaz

    def _y80_yazilamaz(kok, ad, veri):
        if ad == fm.SON_YAKMA_DOSYASI:
            raise OSError(28, "disk dolu")
        return gercek_yaz(kok, ad, veri)

    monkeypatch.setattr(fm, "_kayit_yaz", _y80_yazilamaz)
    with caplog.at_level(logging.WARNING, logger=fm.logger.name):
        d = fm._yarim_yakmayi_ele_al("2.3", True, True, None)
    assert d == {"sonuc": "geri_donuldu", "ayrinti": "geri yazıldı ve doğrulandı"}
    assert fm._kayit_oku(tmp_path, fm.YARIM_YAKMA_DOSYASI) is None, "doğrulanmış geri dönüşten sonra yarım kayıt kaldı"
    assert any("Y80 kaydı yazılamadı (kurtarma sonrası)" in r.getMessage() for r in caplog.records)


def test_yarim_yakma_geri_donus_basarisiz_kayit_kalir(monkeypatch, tmp_path, caplog):
    _yarim_kayit(monkeypatch, tmp_path)
    monkeypatch.setattr(sy, "yedekten_geri_don", lambda *a, **k: sy.Sonuc(sy.GERI_DONUS_BASARISIZ, "yedek yazılamadı"))
    with caplog.at_level(logging.ERROR, logger=fm.logger.name):
        d = fm._yarim_yakmayi_ele_al("2.3", True, True, None)
    assert d == {"sonuc": "basarisiz", "ayrinti": f"[{sy.GERI_DONUS_BASARISIZ}] yedek yazılamadı"}
    assert fm._kayit_oku(tmp_path, fm.YARIM_YAKMA_DOSYASI) is not None, "başarısız kurtarmada yarım kayıt silindi"
    assert any("yarım kalan yakma kurtarılamadı" in r.getMessage() for r in caplog.records)


def test_uyum_kimliksiz_yanitsiz_ve_eski_maskesiz_banner():
    uyumlu, sebep, kod = sk.uyum_karari(None, None, dogrulanamadi=True)
    assert (
        uyumlu is None
        and kod == sk.UYUM_KODU_KIMLIK
        and sebep.startswith("Kart el sikisma dogrulamasina yanit vermedi")
    )
    eski = sk.Stm32Kimlik(surum="DDS v2.2", kanal=5, kip=None, maske=None, ham="STM_READY DDS v2.2 (5-ch)")
    assert sk.uyum_denetle(eski, 5, 88) == (True, "")
    assert sk.uyum_denetle(eski, 5, 89)[0] is False, "eski banner paket boyu farkı uyumlu sayıldı (karşıt kanıt)"
