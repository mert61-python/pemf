# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""H-1.2 (1-H bağımsız incelemesi) — `/api/health` → `firmwareGuncelleme` (D1.116) NEDEN yakılmadığını söyler.

ÖLÇÜLEN KUSUR (inceleme `kayit/kt_tablo.json`: bağımsız karar tablosu, 122 koşu, GERÇEK `backend_service.main()` çocuk
süreçte):
  (a) Y1 varsayılanında (bayrak yok / '0') karar `firmware_guncelle` + "firmware 2.3 → 2.4 ile client … uyumlu olacak"
      gerekçesiyle görünüyordu; `uygulandi=False`, `hata` boş — otomatik yakmanın KAPALI olduğu yazmıyordu (destek
      "güncelleme takıldı" okur).
  (b) STM bağlanmadan yapılan ölçümde (D1.121 yedeği, Y76 "neden karar verilmediğini söyler") gerekçe "karar verilemedi
      → dokunulmuyor (firmware sürümü ayrıştırılamadı: '')" diyordu — asıl sebep kartın BAĞLI OLMAMASI.

KAPI: GERÇEK `acilis_denetimi` (aparat `test_firmware_yakma_sonrasi_SURUM_TEYIDI_H11`: uyum varlığı kurallı, yakıcı SAHTE);
karşıt kollar bayrak '1' ve STM bağlı hâlde bu eklerin ÇIKMADIĞINI ölçer.
"""

from __future__ import annotations

from test_firmware_yakma_sonrasi_SURUM_TEYIDI_H11 import BANNER_FMT, _Kaynak, _kos, zincir  # noqa: F401 — fikstür


def test_KRITIK_H12_bayrak_KAPALIYKEN_firmware_guncelle_karari_YAKILMADIGINI_soyler(zincir):
    z = zincir
    cagri: list[str] = []
    z["mp"].setattr(z["sy"], "_kos", lambda *a, **k: cagri.append("kos") or (0, ""))
    d = dict(z["fm"].acilis_denetimi(firmware_surum="2.3", stm_bagli=True, uygula=False))
    assert d["eylem"] == z["fm"].su.FIRMWARE_GUNCELLE and cagri == [], f"aparat: karar / yakıcı {d} {cagri}"
    assert d["uygulandi"] is False
    assert "otomatik yakma KAPALI" in d["gerekce"] and "PEMF_FW_AUTO_UPDATE=1" in d["gerekce"], (
        f"bayrak kapalıyken 'firmware_guncelle' kararı NEDEN yakılmadığını söylemiyor: {d['gerekce']!r}"
    )


def test_KARSIT_H12_bayrak_1de_gerekce_KAPALI_demez(zincir):
    _cagri, d = _kos(zincir, _Kaynak(BANNER_FMT.format("2.4")))
    assert d["uygulandi"] is True, d
    assert "otomatik yakma KAPALI" not in d["gerekce"], d["gerekce"]


def test_KRITIK_H12_STM_BAGLI_DEGILKEN_gerekce_STM_bagli_degil_der(zincir):
    """D1.121 yedek ölçümü (STM 20 sn içinde bağlanmadı → `stm_bagli=False`, sürüm '')."""
    d = dict(zincir["fm"].acilis_denetimi(firmware_surum="", stm_bagli=False, uygula=False))
    assert d["uygulandi"] is False and d["eylem"] != zincir["fm"].su.FIRMWARE_GUNCELLE, d
    assert "STM bağlı değil" in d["gerekce"], f"STM bağlanmamışken gerekçe sebebi söylemiyor: {d['gerekce']!r}"


def test_KARSIT_H12_STM_bagliyken_gerekce_STM_bagli_degil_DEMEZ(zincir):
    d = dict(zincir["fm"].acilis_denetimi(firmware_surum="2.3", stm_bagli=True, uygula=False))
    assert "STM bağlı değil" not in d["gerekce"], d["gerekce"]
