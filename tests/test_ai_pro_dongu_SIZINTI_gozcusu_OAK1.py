# -*- coding: utf-8 -*-
"""O-A2-K.1 (2-A incelemesi) test yarısı — GERÇEK AI Pro döngüsü (`ai-pro-dongu` iş parçacığı) testten SIZMAZ.

ÖLÇÜLEN (2-A incelemesi, tanı eklentisi): `test_KRITIK_IG515_DONGU_…` biterken döngü YAŞIYORDU; iki test sonra kapanışı
(`_ai_pro_loop` → `efield_live.set_context([])` + `seans_bitti`) süreç geneli E bağlamını sildi → `test_KARSIT_E07_em_fantom_
OLCEKLI_kipte_baglam_KURULUR` zamanlamaya bağlı kırmızı. 2-C ölçümü (gözcü eklenip aparat düzeltilmeden): AI Pro döngüsü kuran
53 test dosyasında **17 test** döngüyü yaşar bırakıyordu (5 dosya; hepsi `ns.air._ai_loop_active = False; ns.geri()` ile
yıkıyor — bayrak iner, iş parçacığı bir tur daha yaşar).

İki katman: (1) aparat `ai_pro_aparati.dongu_bitir` — `geri()` döngüyü durdurur ve BİTMESİNİ bekler; (2) conftest gözcüsü
`_ai_pro_dongusu_sizmaz` (saf işlev `ai_pro_dongu_sizinti_sorunu`) — kaçağı durdurur, bekler ve testi KIRMIZI yapar.
Bu dosya iki katmanı da GERÇEK iş parçacığıyla ölçer (sahte iş parçacığı adı ürünün adıdır; ürün kodu koşmaz).
"""

from __future__ import annotations

import sys
import threading
import types
from pathlib import Path

_KOK = Path(__file__).resolve().parents[1]
AD = "ai-pro-dongu"


def _kayitli_conftest():
    """pytest'in YÜKLEDİĞİ conftest (`import conftest` başka kipte ikinci kopya yaratabilir → kör kayıt)."""
    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (_KOK / "tests" / "conftest.py").resolve(), (
        "kayıtlı tests/conftest.py bulunamadı"
    )
    return c


def _dongu(durum, bitti: threading.Event, kapanis_gecikmesi: float = 0.05):
    """Ürün döngüsünün biçimi: bayrak inene dek döner, sonra KAPANIŞ yan etkisi (gecikmeli) yazar."""
    while durum._ai_loop_active:
        threading.Event().wait(0.01)
    threading.Event().wait(kapanis_gecikmesi)
    bitti.set()


def test_KRITIK_gozcu_YASAYAN_donguyu_bulur_DURDURUR_ve_BEKLER():
    durum = types.SimpleNamespace(_ai_loop_active=True)
    bitti = threading.Event()
    t = threading.Thread(target=_dongu, args=(durum, bitti), daemon=True, name=AD)
    t.start()
    try:
        sorun = _kayitli_conftest().ai_pro_dongu_sizinti_sorunu(durum, threading.enumerate(), bekle=5.0)
        assert "YAŞIYORDU (1; beklemeden sonra 0)" in sorun, sorun
        assert durum._ai_loop_active is False and not t.is_alive() and bitti.is_set(), (
            "gözcü döngüyü durdurup KAPANIŞINI beklemedi — yan etki sonraki teste taşınır"
        )
    finally:
        durum._ai_loop_active = False
        t.join(5)


def test_KRITIK_aparat_geri_DONGUNUN_kapanisini_BEKLER(monkeypatch, tmp_path):
    """`ns.geri()` döndüğünde döngü BİTMİŞ ve kapanış yan etkisi YAZILMIŞ olmalı (bayrak beklemek yetmez)."""
    import ai_pro_aparati as ap

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    bitti = threading.Event()
    t = threading.Thread(target=_dongu, args=(ns.air, bitti, 0.3), daemon=True, name=AD)
    try:
        ns.air._ai_loop_active = True
        t.start()
    finally:
        ns.air._ai_loop_active = False  # sızan testlerin yıkım deseni: bayrak iner…
        ns.geri()  # …ve aparat döngünün BİTMESİNİ bekler
    assert not t.is_alive() and bitti.is_set(), "aparat geri() döngünün kapanışını BEKLEMEDİ (sonraki teste sızar)"


def test_KARSIT_gozcu_dongu_YOKKEN_ve_BASKA_adli_is_parcaciginda_SUSAR():
    durum = types.SimpleNamespace(_ai_loop_active=True)
    dur = threading.Event()
    t = threading.Thread(target=dur.wait, args=(5,), daemon=True, name="ai-pro-hazirlik")
    t.start()
    try:
        assert _kayitli_conftest().ai_pro_dongu_sizinti_sorunu(durum, threading.enumerate(), bekle=0.1) == ""
        assert durum._ai_loop_active is True and t.is_alive(), "gözcü BAŞKA iş parçacığına dokundu"
    finally:
        dur.set()
        t.join(5)


def test_KRITIK_gozcu_BAYRAK_inmis_ama_is_parcacigi_YASIYORKEN_de_bulur():
    """Sızan testlerin GERÇEK deseni: `_ai_loop_active=False` yapılmış, döngü kapanışını henüz yazmamış. Ölçüt bayrak olsaydı
    gözcü bunu kaçırırdı (bayrak zaten inik)."""
    durum = types.SimpleNamespace(_ai_loop_active=False)
    bitti = threading.Event()
    t = threading.Thread(target=_dongu, args=(durum, bitti, 0.5), daemon=True, name=AD)
    t.start()
    try:
        sorun = _kayitli_conftest().ai_pro_dongu_sizinti_sorunu(durum, threading.enumerate(), bekle=5.0)
        assert "YAŞIYORDU (1; beklemeden sonra 0)" in sorun, sorun
        assert bitti.is_set(), "gözcü kapanışı BEKLEMEDİ"
    finally:
        t.join(5)
