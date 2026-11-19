# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""OTB T-0 [SAHİP KARARI 19-11] — "Doğrula" GEÇİNCE "Kalibrasyon ESKİ" uyarısı kalkar.

ÖLÇÜLEN (ODM tezgâhı 19-11): 12:38'de 11. kez "kalibre etmeden devam" (sahne yenileme), 12:45'te "Doğrula" GEÇTİ (plaka merkezi 1,23 cm) —
ekranda "Kalibrasyon ESKİ" kaldı: `KareDurumu.eski` yalnız `sahne_yenileme` VARLIĞINA bakıyordu (yalnız yeniden kalibrasyon siliyordu).
SÖZLEŞME: son sahne yenilemesinden SONRA geçen bir doğrulama (`dogrulamalar[].gecti` + `tarih`) varsa ESKİ DEĞİL → uyarı yok, kuyu aralığı
toleransı %3'e döner (kart durumu + kare durumu + AI Pro şeridi aynı kaynaktan). Kalan / önceki / tarihi okunamayan doğrulama ESKİ'yi
kaldırmaz (uyarı yutulmaz). VERİ ODAKLI: kurulu dosyadaki 12:45 geçen doğrulama kendiliğinden sayılır (sahip yeniden basmaz).
"""

import pytest
import sabit_duzlem_sahne as sh
from test_KD_sabit_duzlem_kalibrasyonu import _sd, _sentetik_kayit, _undistort, sentetik  # noqa: F401  aynı düzenek

YENILEME = "2026-11-19T12:38:10+0300"


def _yenile(tmp_path, s, tarih=YENILEME):
    sd = _sd()
    und = _undistort(s["kare1"], s["K"], s["D"])
    maske = sd.cokgen_maskesi((sh.W, sh.H), [], genislet_px=0)
    return sd.sahne_yenile(tmp_path, und, maske, {"tarih": tarih, "kayma_px": 30.0, "kuyu_sapma": 0.04})


def _dogrulama(tarih, gecti=True):
    return {"tarih": tarih, "kose_fark_cm": [0.9, 1.8, 1.2, 1.0], "merkez_fark_cm": 1.23, "gecti": gecti}


def _kare(tmp_path):
    sd = _sd()
    return sd.kare_hazirla(sd.yukle(tmp_path), kare_boyutu=(sh.W, sh.H), kamera_indeksi=1)


def test_KRITIK_T0_yenilemeden_SONRA_GECEN_dogrulama_ESKI_uyarisini_KALDIRIR_tolerans_yuzde_3(sentetik, tmp_path):
    sd = _sd()
    _sentetik_kayit(tmp_path, sentetik)
    assert _yenile(tmp_path, sentetik) is not None
    kd = _kare(tmp_path)
    assert kd.eski is True and kd.kuyu_araligi_toleransi == 0.10  # önce: kalibre etmeden devam → ESKİ
    assert sd.dogrulama_ekle(tmp_path, _dogrulama("2026-11-19T12:45:02+0300")) is not None
    kd = _kare(tmp_path)
    assert kd.eski is False, "Doğrula GEÇTİ ama kalibrasyon hâlâ ESKİ"
    assert kd.kuyu_araligi_toleransi == 0.03 and kd.ozet()["eski"] is False
    assert not any(u.startswith("kalibrasyon_eski") for u in kd.uyarilar), kd.uyarilar
    assert kd.gecerli


@pytest.mark.parametrize(
    "kayit",
    [
        _dogrulama("2026-11-19T12:45:02+0300", gecti=False),  # KALDI
        _dogrulama("2026-11-19T12:30:00+0300"),  # yenilemeden ÖNCE
        _dogrulama("?"),  # tarihi okunamıyor
        {"tarih": "2026-11-19T12:45:02+0300", "gecti": "true"},  # bozuk tür
    ],
    ids=["kaldi", "once", "tarihsiz", "bozuk_tur"],
)
def test_KRITIK_T0_KALAN_ONCEKI_ya_da_okunamayan_dogrulama_ESKIyi_KALDIRMAZ(sentetik, tmp_path, kayit):
    sd = _sd()
    _sentetik_kayit(tmp_path, sentetik)
    _yenile(tmp_path, sentetik)
    sd.dogrulama_ekle(tmp_path, kayit)
    kd = _kare(tmp_path)
    assert kd.eski is True and kd.kuyu_araligi_toleransi == 0.10
    assert any(u.startswith("kalibrasyon_eski") for u in kd.uyarilar), kd.uyarilar


def test_KRITIK_T0_dogrulamadan_SONRA_yeniden_kalibre_etmeden_devam_YINE_ESKI(sentetik, tmp_path):
    sd = _sd()
    _sentetik_kayit(tmp_path, sentetik)
    _yenile(tmp_path, sentetik)
    sd.dogrulama_ekle(tmp_path, _dogrulama("2026-11-19T12:45:02+0300"))
    assert _kare(tmp_path).eski is False
    _yenile(tmp_path, sentetik, tarih="2026-11-19T13:10:00+0300")  # kamera yine oynadı, yine "devam"
    assert _kare(tmp_path).eski is True


def test_T0_yenileme_tarihi_OKUNAMAZSA_ESKI_kalir_ve_yenileme_YOKSA_hic_eski_degil():
    sd = _sd()
    assert sd.eski_mi(None) is False and sd.eski_mi({}) is False
    assert sd.eski_mi({"dogrulamalar": [_dogrulama("2026-11-19T12:45:02+0300")]}) is False
    bozuk = {"sahne_yenileme": {"tarih": None}, "dogrulamalar": [_dogrulama("2026-11-19T12:45:02+0300")]}
    assert sd.eski_mi(bozuk) is True
    # saat dilimi yazılmamış eski kayıt da karşılaştırılır (aynı makinenin yerel saati)
    assert (
        sd.eski_mi(
            {"sahne_yenileme": {"tarih": "2026-11-19T12:38:10"}, "dogrulamalar": [_dogrulama("2026-11-19T12:45:02")]}
        )
        is False
    )


def test_KRITIK_T0_kalibrasyon_KARTI_durumu_ESKI_degil_VERI_ODAKLI(sentetik, tmp_path, monkeypatch):
    """Kart (`/api/ai/pro/kalibrasyon` → `durum_ozeti`) AYNI kuraldan: kurulu dosyadaki geçen doğrulama kendiliğinden sayılır."""
    from servers import kabin_kalibrasyonu as kk

    sd = _sd()
    _sentetik_kayit(tmp_path, sentetik)
    _yenile(tmp_path, sentetik)
    monkeypatch.setattr(kk, "_veri_koku", lambda: tmp_path)
    assert kk.durum_ozeti()["eski"] is True
    sd.dogrulama_ekle(tmp_path, _dogrulama("2026-11-19T12:45:02+0300"))
    d = kk.durum_ozeti()
    assert d["eski"] is False and d["sonDogrulama"]["gecti"] is True, d
