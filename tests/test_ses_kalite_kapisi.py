# Author: mertaygn, cglrgrkn
"""Denetim 2026-08-15: kedi sesi analizi SESSİZ kayıtta sonuç üretmemeli.

SAHA BİLDİRİMİ (sahip, ev sahibi modu): "ses kaydında kedi sesi olmamasına rağmen analiz
yapıp sonuç veriyor" + laptopta boş kayıt analiz edilmeye çalışılıyordu.

KÖK NEDEN MİMARİ: `inference_cat_sound` modelinin 10 sınıfının HEPSİ kedi duygusudur;
"kedi değil" sınıfı YOKTUR. Softmax 1'e toplandığı için model sessizliğe bile mutlaka bir
duygu atar (ölçüldü: tam sessizlik → "Resting" %16,7; şans %10 — yani model hiçbir şey
söylemiyor ama arayüz kesin bulgu gibi gösteriyordu).

Bu dosya iki şeyi kilitler:
  1) SESSİZLİK KAPISI — analiz edilemeyecek kadar zayıf kayıt reddedilir,
  2) ⚠️ EŞİĞİN GERÇEK KAYITLARA PAYI — kapı, depodaki GERÇEK kedi kayıtlarının hiçbirini
     reddetmemeli. Eşiği yukarı çekmek "gürültüyü daha iyi eliyorum" gibi görünür ama
     gerçek bir AĞRI kaydını sessiz sayarsa ev sahibi ağrıyı KAÇIRIR — düzeltmeye
     çalıştığımız hatadan daha kötüsü.

⚠️ Düşük güven REDDEDİLMEZ, yalnız işaretlenir: kedi/kedi-değil olasılık aralıkları
ÖRTÜŞÜYOR (gerçek ağrı kaydı 0,563 · oda gürültüsü 0,595). Sert eşik gerçek ağrıyı elerdi.
Sahip kararı (2026-08-15): sessizliği reddet, zayıfı uyar.
"""

import math
import struct
import wave

import pytest

from utils.ses_kalitesi import (
    BELIRSIZLIK_ESIGI,
    SESSIZLIK_ESIGI_DBFS,
    guvenilir_mi,
    normalize_entropi,
    rms_dbfs,
    sessiz_mi,
    wav_rms_dbfs,
)

SR = 22050


def _wav_yaz(yol, ornekler, sr=SR, genislik=2):
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(genislik)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", max(-32768, min(32767, int(x * 32767)))) for x in ornekler))


def _sinus(genlik, sure=1.0, frek=700.0, sr=SR):
    n = int(sr * sure)
    return [genlik * math.sin(2 * math.pi * frek * i / sr) for i in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
# SESSİZLİK KAPISI
# ─────────────────────────────────────────────────────────────────────────────


def test_tam_sessizlik_sessiz_sayilir():
    """Sahibin bildirdiği durum: boş kayıt analiz edilmemeli."""
    assert rms_dbfs([0.0] * 1000) == float("-inf")
    assert sessiz_mi(rms_dbfs([0.0] * 1000)) is True


def test_KRITIK_gercek_kedi_kayitlari_sessiz_SAYILMAZ():
    """🔴 Kapı gerçek kayıtları elerse ev sahibi AĞRIYI KAÇIRIR.

    Ölçülen en sessiz gerçek kayıt -26,3 dBFS ('10c_KediSesi_agri'). Eşik ondan belirgin
    aşağıda olmalı; bu test eşiği yukarı çekmeyi (ör. -20) engeller.
    """
    en_sessiz_gercek_kayit = -26.3
    assert SESSIZLIK_ESIGI_DBFS < en_sessiz_gercek_kayit, (
        f"Sessizlik eşiği ({SESSIZLIK_ESIGI_DBFS} dBFS) ölçülen en sessiz GERÇEK kedi "
        f"kaydından ({en_sessiz_gercek_kayit} dBFS) yüksek → o kayıt 'sessiz' sanılıp "
        "reddedilir ve ev sahibi kedisinin ağrısını göremez."
    )
    assert sessiz_mi(en_sessiz_gercek_kayit) is False
    # Makul bir pay da kalmalı (gürültü tabanı kayıttan kayda değişir).
    assert en_sessiz_gercek_kayit - SESSIZLIK_ESIGI_DBFS >= 10.0, "eşiğin payı 10 dB'den az"


@pytest.mark.parametrize(
    "dbfs,beklenen",
    [
        (-70.0, True),  # mikrofon kapalı/çok uzak
        (-60.0, True),  # ölçülen "sessiz oda"
        (-50.0, True),  # hâlâ analiz edilemez
        (-35.0, False),  # ölçülen "oda gürültüsü" — SESSİZ DEĞİL (düşük güvenle işaretlenir)
        (-26.3, False),  # gerçek ağrı kaydı
        (-12.7, False),  # gerçek mutlu kaydı
    ],
)
def test_sessizlik_esigi_olculen_degerlerde_dogru_karar_verir(dbfs, beklenen):
    assert sessiz_mi(dbfs) is beklenen


def test_wav_rms_gercek_dosyadan_okunur(tmp_path):
    """Kapı ffmpeg'in ürettiği WAV üzerinden çalışır — dosya yolunu gerçekten okumalı."""
    sessiz = tmp_path / "sessiz.wav"
    _wav_yaz(sessiz, [0.0] * SR)
    assert sessiz_mi(wav_rms_dbfs(str(sessiz))) is True

    yuksek = tmp_path / "yuksek.wav"
    _wav_yaz(yuksek, _sinus(0.3))
    olculen = wav_rms_dbfs(str(yuksek))
    # 0.3 genlikli sinüsün RMS'i 0.3/√2 ≈ 0.212 → ~-13,5 dBFS
    assert -15.0 < olculen < -12.0, f"beklenmeyen RMS: {olculen}"
    assert sessiz_mi(olculen) is False


def test_bos_wav_sessiz_sayilir(tmp_path):
    bos = tmp_path / "bos.wav"
    _wav_yaz(bos, [])
    assert wav_rms_dbfs(str(bos)) == float("-inf")


def test_beklenmeyen_bit_derinligi_hata_verir(tmp_path):
    """Kapı sessizce yanlış ölçüm yapmaktansa 'ölçemedim' demeli (çağıran kapıyı atlar)."""
    sekiz_bit = tmp_path / "8bit.wav"
    with wave.open(str(sekiz_bit), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(SR)
        w.writeframes(b"\x80" * 100)
    with pytest.raises(ValueError, match="16-bit"):
        wav_rms_dbfs(str(sekiz_bit))


# ─────────────────────────────────────────────────────────────────────────────
# BELİRSİZLİK İŞARETİ (reddetme DEĞİL)
# ─────────────────────────────────────────────────────────────────────────────


def test_duz_dagilim_tam_belirsiz():
    """10 sınıfa eşit olasılık = model hiçbir şey söylemiyor."""
    assert normalize_entropi([0.1] * 10) == pytest.approx(1.0, abs=1e-9)
    assert guvenilir_mi([0.1] * 10) is False


def test_keskin_dagilim_guvenilir():
    p = [0.91] + [0.01] * 9
    assert normalize_entropi(p) < 0.30
    assert guvenilir_mi(p) is True


def test_KRITIK_olculen_gercek_kedi_kayitlari_guvenilir_isaretlenir():
    """Net kedi kayıtları uyarı ALMAMALI — her sonuca uyarı basmak uyarıyı anlamsızlaştırır."""
    mutlu = [0.910, 0.030, 0.020, 0.015, 0.010, 0.005, 0.004, 0.003, 0.002, 0.001]
    kizgin = [0.898, 0.040, 0.020, 0.015, 0.010, 0.007, 0.004, 0.003, 0.002, 0.001]
    for ad, p in (("mutlu", mutlu), ("kizgin", kizgin)):
        assert guvenilir_mi(p) is True, f"gerçek '{ad}' kaydı gereksiz yere uyarı alıyor"


def test_KRITIK_olculen_gurultu_guvenilir_SAYILMAZ():
    """Sahibin şikayeti: kedi sesi yokken sonuç veriyor. Sonuç veriyor AMA artık işaretli."""
    # Ölçülen "oda gürültüsü": top-1 0,595, entropi 0,637 → belirsiz.
    gurultu = [0.595, 0.120, 0.080, 0.060, 0.045, 0.035, 0.025, 0.020, 0.012, 0.008]
    assert normalize_entropi(gurultu) > BELIRSIZLIK_ESIGI
    assert guvenilir_mi(gurultu) is False


def test_KRITIK_dusuk_guven_REDDEDILMEZ_yalnizca_isaretlenir():
    """🔴 SAHİP KARARI: sert eşik gerçek ağrıyı elerdi.

    Ölçülen gerçek ağrı kaydı top-1 = 0,563 iken oda gürültüsü 0,595 — yani düz bir
    olasılık eşiği gerçek ağrıyı ELER, gürültüyü GEÇİRİR. `guvenilir_mi` bir REDDETME
    fonksiyonu değildir; yalnız "kesin bulgu gibi gösterme" der. Kapı yalnız SESSİZLİK.
    """
    gercek_agri_top1 = 0.563
    oda_gurultusu_top1 = 0.595
    assert gercek_agri_top1 < oda_gurultusu_top1, (
        "ölçüm değişmiş — düz olasılık eşiğinin neden kullanılamayacağı yeniden ölçülmeli"
    )
    # Sessizlik kapısı bir OLASILIK eşiği DEĞİLDİR; sinyal seviyesine bakar.
    assert sessiz_mi(-26.3) is False, "gerçek ağrı kaydı sessizlik kapısına takılıyor"


def test_tek_sinif_entropisi_sifir():
    """Dejenere girdi kapıyı çökertmemeli."""
    assert normalize_entropi([1.0]) == 0.0
    assert normalize_entropi([]) == 0.0


def test_normalize_edilmemis_olasiliklar_da_calisir():
    """Toplamı 1 olmayan dağılım gelirse (yuvarlama/ONNX çıktısı) yine doğru ölçülmeli."""
    assert normalize_entropi([2.0] * 10) == pytest.approx(1.0, abs=1e-9)
