# -*- coding: utf-8 -*-
"""Y306 (sahip 19-11, OTB [SAHİBE] 1 — "son 5 ölçümün ortancası"): kamera OYNAMADAN hareketsiz plakada Hough kuyu aralığı kareden kareye
%0,2–7,4 salınıyor (tolerans %3) → hazırlıkta ve seansın ilk karelerinde ara sıra "Kamera oynamış olabilir ya da taban yüksekliği ayarı
yanlış" çıkıyor ve o kare sayılmıyordu (19-11 tezgâh denemesi madde 5).
SÖZLEŞME:
  · karar sağlayıcının penceresindeki son `KUYU_ARALIGI_PENCERESI` (5) ölçümün ORTANCASIYLA verilir; tolerans AYNI (%3 / eski kayıtta %10);
  · tek gürültülü ölçüm `kamera_oynamis` ENGELİ vermez; kalıcı sapma (kamera / taban yüksekliği gerçekten değişti) pencerenin yarısını
    geçince yine ENGEL (yakalama gücü korunur);
  · pencere seans başında / durdurmada (`odak_ayarla`) ve sabit numune referansı kurulurken BOŞALIR;
  · pencere verilmezse (hat tek başına) karar bu karenin ölçümüyle — bugünkü davranış AYNEN;
  · T-8 kayma STOP'u (referans örtüşmesi) pencereden BAĞIMSIZ: plaka kayınca kare yine reddedilir.
GERÇEK: petri hattı (sentetik kabin, gerçek kalibrasyon çözümü), sağlayıcının `localize` / `odak_ayarla` / `_pipeline_kur`'u."""

from __future__ import annotations

import numpy as np
import pytest
import sabit_duzlem_sahne as sh
from test_KD_sabit_duzlem_kalibrasyonu import _petri, _sentetik_kayit, sentetik  # noqa: F401  sentetik kabin

KARE = np.zeros((8, 8, 3), dtype=np.uint8)


def _sd():
    from ai_hub.cv_ortak import sabit_duzlem as sd

    return sd


def _kareler(s):
    """İyi kare (kalibrasyon pozu) + kuyu aralığını %3'ün üstünde saptıran kare (2 cm yükseklik değişimi — gürültü yerine)."""
    iyi = sh.ciz(s["R"], s["t"], s["K"], s["D"], plaka=(60.0, 20.0))
    R2, t2 = sh.poz((27.5, 175.0, -122.5))
    sapan = sh.ciz(R2, t2, s["K"], s["D"], plaka=(60.0, 20.0))
    return iyi, sapan


def _isle(duz, tmp_path, kare, pencere):
    pl = _petri(duz, tmp_path)
    pl.kuyu_araligi_penceresi = pencere  # sağlayıcı her karede hattı yeniden kurar, pencere AYNI liste
    res, _ = pl.process_image(kare)
    return res


def test_KRITIK_tek_gurultulu_olcum_ENGEL_vermez_son_olcumlerin_ORTANCASI(sentetik, tmp_path):  # noqa: F811
    duz = _sentetik_kayit(tmp_path, sentetik, referans=False)
    iyi, sapan = _kareler(sentetik)
    pencere: list = []
    for _ in range(2):
        r = _isle(duz, tmp_path, iyi, pencere)
        assert "kamera_oynamis" not in r.kalibrasyon["engeller"], r.kalibrasyon
    r = _isle(duz, tmp_path, sapan, pencere)
    ka = r.kalibrasyon["olcum"]["kuyu_araligi"]
    assert ka["kare_sapma"] > 0.03 and ka["sapma"] <= 0.03 and ka["pencere"] == 3, ka
    assert ka["gecti"] is True and "kamera_oynamis" not in r.kalibrasyon["engeller"], r.kalibrasyon
    assert len(pencere) == 3


def test_KARSIT_pencere_YOKSA_ayni_kare_bugunku_gibi_ENGEL(sentetik, tmp_path):  # noqa: F811
    duz = _sentetik_kayit(tmp_path, sentetik, referans=False)
    _, sapan = _kareler(sentetik)
    r = _isle(duz, tmp_path, sapan, None)
    ka = r.kalibrasyon["olcum"]["kuyu_araligi"]
    assert "pencere" not in ka and "kare_sapma" not in ka and ka["gecti"] is False, ka
    assert "kamera_oynamis" in r.kalibrasyon["engeller"] and r.pemf_valid is False


def test_KRITIK_KALICI_sapma_pencerenin_YARISINI_gecince_ENGEL(sentetik, tmp_path):  # noqa: F811
    """Kamera / taban yüksekliği gerçekten değişti: 2 iyi ölçümün ardından 3. sapan ölçümde (5'in çoğunluğu) ENGEL ve neden ortanca der."""
    duz = _sentetik_kayit(tmp_path, sentetik, referans=False)
    iyi, sapan = _kareler(sentetik)
    pencere: list = []
    for _ in range(2):
        _isle(duz, tmp_path, iyi, pencere)
    sonuc = [_isle(duz, tmp_path, sapan, pencere) for _ in range(3)]
    assert ["kamera_oynamis" in r.kalibrasyon["engeller"] for r in sonuc] == [False, False, True]
    son = sonuc[-1]
    assert son.pemf_valid is False and son.kalibrasyon["olcum"]["kuyu_araligi"]["sapma"] > 0.03
    assert any("son 5 olcumun ortancasi" in str(w) for w in son.warnings), son.warnings


def test_KRITIK_BOS_pencerede_ilk_sapan_olcum_ENGEL_seans_basinda_korunmaz(sentetik, tmp_path):  # noqa: F811
    """Pencere boşken (seans başı / referans kuruluşu) tek ölçüm kendi başına karar verir — yakalama gücü düşmez."""
    duz = _sentetik_kayit(tmp_path, sentetik, referans=False)
    _, sapan = _kareler(sentetik)
    r = _isle(duz, tmp_path, sapan, [])
    assert "kamera_oynamis" in r.kalibrasyon["engeller"], r.kalibrasyon


def test_ortanca_PENCERE_5_alt_ortanca_ve_TOLERANS_olcumun():
    sd = _sd()
    assert sd.KUYU_ARALIGI_PENCERESI == 5 and sd.KUYU_ARALIGI_TOLERANSI == 0.03

    def ka(sapma, tol=0.03):
        return {
            "sutun_mm": 19.3,
            "satir_mm": 19.3,
            "beklenen_mm": 19.3,
            "sapma": sapma,
            "tolerans": tol,
            "gecti": sapma <= tol,
        }

    p: list = []
    k = sd.kuyu_araligi_ortancasi(ka(0.01), p)
    assert (k["sapma"], k["kare_sapma"], k["pencere"], k["gecti"]) == (0.01, 0.01, 1, True)
    k = sd.kuyu_araligi_ortancasi(ka(0.074), p)  # 2 ölçümden biri gürültülü → ALT ortanca
    assert (k["sapma"], k["pencere"], k["gecti"]) == (0.01, 2, True), k
    for s in (0.05, 0.06, 0.07, 0.08):
        k = sd.kuyu_araligi_ortancasi(ka(s), p)
    assert p == [0.074, 0.05, 0.06, 0.07, 0.08] and k["pencere"] == 5 and k["sapma"] == 0.07 and k["gecti"] is False
    k = sd.kuyu_araligi_ortancasi(ka(0.08, tol=0.10), [])  # "kalibre etmeden devam" kaydı: tolerans ölçümün (%10)
    assert k["gecti"] is True and k["tolerans"] == 0.10
    girdi = ka(0.02)
    sd.kuyu_araligi_ortancasi(girdi, [])
    assert girdi == ka(0.02), "girdi sözlüğü değiştirildi"


def test_KRITIK_saglayici_penceresi_HATTA_verilir_ve_AYNI_liste():
    from servers import ai_pro_hedef as hedef

    class _Hat:
        def __init__(self, cfg, **k):
            self.kuyu_araligi_uyari = False
            self.kuyu_araligi_penceresi = None

    s = hedef.PetriSaglayici()
    onbellek = {"cls": _Hat, "cfg": None, "yolo_path": "y.onnx", "yolo": None, "predictor": None}
    p1, p2 = s._pipeline_kur(onbellek), s._pipeline_kur(onbellek)
    assert p1.kuyu_araligi_penceresi is s._aralik_penceresi and p2.kuyu_araligi_penceresi is s._aralik_penceresi
    assert hedef.PetriSaglayici()._aralik_penceresi is not s._aralik_penceresi, "sağlayıcılar pencere paylaşıyor"


def test_KRITIK_pencere_SEANS_basinda_durdurmada_ve_REFERANS_kurulurken_BOSALIR():
    from petri_plaka_aparati import plaka_adaylari
    from servers import ai_pro_hedef as hedef
    from test_OTB_T8_SABIT_NUMUNE_izgara_referansi import _saglayici

    ref = plaka_adaylari()
    s = _saglayici([ref])
    s._aralik_penceresi.extend([0.05, 0.06])
    hedef.odak_ayarla(s, {"doz_mT": 1.4, "kip": "TUM_PETRI"}, "Tüm petri")  # seans başı
    assert s._aralik_penceresi == []
    s._aralik_penceresi.extend([0.01, 0.07])  # hazırlıktan kalan / referans öncesi kareler
    assert s.localize(KARE, 0)[0] is True and s._sabit_izgara is not None
    assert s._aralik_penceresi == [], "referans kurulurken pencere boşalmadı"
    s._aralik_penceresi.append(0.02)
    hedef.odak_ayarla(s, None)  # durdurma
    assert s._aralik_penceresi == []


@pytest.mark.parametrize("dx", [19.3, 12.0])
def test_KRITIK_T8_kayma_REDDI_penceredeki_olcumlerden_BAGIMSIZ(dx):
    """Pencere "her şey yolunda" ölçümleriyle doluyken plaka kayarsa kare yine `plakaKaydi` ile reddedilir (Y300 30 sn + STOP AYNEN)."""
    from petri_plaka_aparati import plaka_adaylari
    from servers import ai_pro_hedef as hedef
    from test_OTB_T8_SABIT_NUMUNE_izgara_referansi import _kayik, _saglayici

    ref = plaka_adaylari()
    s = _saglayici([ref, _kayik(ref, dx=dx)])
    hedef.odak_ayarla(s, {"doz_mT": 1.4, "kip": "TUM_PETRI"}, "Tüm petri")
    assert s.localize(KARE, 0)[0] is True
    s._aralik_penceresi.extend([0.001] * 5)
    assert s.localize(KARE, 0)[0] is False
    assert s.son_lokalizasyon_meta()["plaka_dogrulanmadi"] == "plakaKaydi"
