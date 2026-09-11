# -*- coding: utf-8 -*-
# Author: mertaygn
"""ÖLÇÜLEN YOĞUNLUK — aktif seans kartındaki mT değeri sensörden gelmeli.

SAHİP KARARI 2026-09-11: "aktif seans kısmı var en üstte manuel modu başlatınca frekans var
süre var yoğunluk var ordaki yoğunluk değeri stm e bağlı olan SENSÖRDEN GELSİN".

===============================================================================
İKİ FARKLI "YOĞUNLUK" — KAPININ ASIL İŞİ BUNLARI AYRI TUTMAK
===============================================================================
· `intensityMt`          = REÇETE. Operatörün yazdığı sayı; cihaza GÖNDERİLMEZ (STM/ESP
                           paketi mT taşımaz), yalnız DB'ye girer. Denetim 2026-09-03'te
                           operatörlerin bunu UYGULANAN doz sandığı ölçüldü → "(kayıt)".
· `measuredIntensityMt`  = ÖLÇÜM. MLX90393'ün seans boyunca gördüğü TEPE |B|.

Ölçümü reçetenin üzerine yazmak, "yazılan sayı ölçülmüş gibi kaydedildi" arızasının
aynısı olurdu. Bu dosya ikisinin ayrı kaldığını ve ölçümün seansa KAPILANDIĞINI ölçer.

Tasarım: `_event_loop` None → `_ws_broadcast_sync` no-op; saf state geçişleri sınanır.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest


@pytest.fixture()
def ls():
    from servers import live_state

    with live_state._live_state_lock:
        live_state._live_state["activeTreatment"].update(
            {
                "isActive": False,
                "intensityMt": 0.0,
                "measuredIntensityMt": None,
                "measuredIntensityCoil": None,
            }
        )
    yield live_state
    with live_state._live_state_lock:
        live_state._live_state["activeTreatment"].update(
            {"isActive": False, "measuredIntensityMt": None, "measuredIntensityCoil": None}
        )


def _at(live_state):
    with live_state._live_state_lock:
        return dict(live_state._live_state["activeTreatment"])


def test_KRITIK_seans_YOKKEN_olcum_YAZILMAZ(ls):
    """Boştaki cihazın okuduğu alan "uygulanan doz" değildir.

    MUTASYON: `update_measured_intensity`teki `if not at.get("isActive"): return False`
    kapısını kaldır → KIRMIZI. Sahadaki etki: seans yokken bile kartta bir mT belirir ve
    operatör tedavi sürüyor sanır.
    """
    assert ls.update_measured_intensity(3.2, 6) is False, "seans YOKKEN olcum yaziliyor"
    assert _at(ls)["measuredIntensityMt"] is None


def test_KRITIK_aktif_seansta_olcum_yazilir_ve_RECETE_KORUNUR(ls):
    ls.update_live_session_state(is_active=True, mode="Manuel", freq=10, intensity=3.5, duration_sec=600)
    assert ls.update_measured_intensity(7.25, 6) is True
    at = _at(ls)
    assert at["measuredIntensityMt"] == pytest.approx(7.25)
    assert at["measuredIntensityCoil"] == 6
    # ⚠️ REÇETE DOKUNULMAZ: ikisi farkli buyukluktur, biri otekinin uzerine yazilamaz.
    assert at["intensityMt"] == pytest.approx(3.5), "olcum RECETE alaninin uzerine yazildi"


def test_KRITIK_seans_BASLARKEN_onceki_olcum_TEMIZLENIR(ls):
    """Yeni seansın ilk telemetrisi gelene kadar ESKİ seansın tepesi görünmemeli.

    MUTASYON: `update_live_session_state`teki temizlemeyi yalnız `if not is_active`
    dalına taşı → KIRMIZI.
    """
    ls.update_live_session_state(is_active=True, mode="Manuel", freq=10, intensity=1.0, duration_sec=600)
    ls.update_measured_intensity(9.9, 6)
    assert _at(ls)["measuredIntensityMt"] == pytest.approx(9.9)

    # (a) Bitiste temizlenir.
    ls.update_live_session_state(is_active=False, mode="Sistem Hazır")
    assert _at(ls)["measuredIntensityMt"] is None, "seans bitince olcum kaldi"

    # (b) ⚠️ BASLANGICTA DA TEMIZLENIR — bitis yolundan BAGIMSIZ olarak.
    # Kapiyi bilerek "durdur-sonra-basla" dizisiyle sinamiyoruz: o dizide (a) zaten
    # temizledigi icin baslangic temizligi HIC OLCULMEZ ve mutasyon YESIL kalirdi
    # (2026-09-11'de tam olarak bu olmustu). Onun yerine kirli state DOGRUDAN kuruluyor:
    # backend'in gormedigi bir yoldan (surec ici cagri sirasi, ileride eklenecek 5. stop
    # yolu) deger kalmis olabilir; seans BASLANGICI onu tasimamali.
    with ls._live_state_lock:
        ls._live_state["activeTreatment"]["measuredIntensityMt"] = 7.7
        ls._live_state["activeTreatment"]["measuredIntensityCoil"] = 6
    ls.update_live_session_state(is_active=True, mode="Manuel", freq=10, intensity=1.0, duration_sec=600)
    assert _at(ls)["measuredIntensityMt"] is None, "seans BASLANGICI onceki olcumu tasidi"
    assert _at(ls)["measuredIntensityCoil"] is None


def test_KRITIK_degismeyen_olcum_YENIDEN_YAYINLANMAZ(ls):
    """Telemetri saniyede bir gelir; hiçbir şey değişmediyse WS'e yük bindirmemeli."""
    ls.update_live_session_state(is_active=True, mode="Manuel", freq=10, intensity=1.0, duration_sec=600)
    assert ls.update_measured_intensity(4.0, 6) is True
    assert ls.update_measured_intensity(4.0, 6) is False, "ayni deger tekrar yayinlaniyor"
    assert ls.update_measured_intensity(4.5, 6) is True


def test_KRITIK_olcum_None_ise_alan_None_KALIR_sifir_DEGIL(ls):
    """⚠️ 0.0 "ölçtük, alan yok" demektir; ölçmediysek None demeliyiz."""
    ls.update_live_session_state(is_active=True, mode="Manuel", freq=10, intensity=1.0, duration_sec=600)
    ls.update_measured_intensity(None, 6)
    at = _at(ls)
    assert at["measuredIntensityMt"] is None, "olcum yokken 0.0 yazildi"
    assert at["measuredIntensityCoil"] is None, "olcum yokken bobin kimligi kaldi"


def test_KRITIK_telemetri_TEPE_ve_ORNEK_SAYISINI_tasir():
    """`headless_core` ayrıştırıcısı `N=`/`S=1` alanlarını taşımalı.

    ⚠️ ALAN YOKKEN ANAHTAR KOYULMAZ: aşağı akış "ölçülmedi" ile "0 ölçüldü"yü ancak
    anahtarın YOKLUĞUNDAN ayırt edebiliyor.

    MUTASYON: `if _n is not None and "magnetic_field" in govde` → `if _n is not None`
    yap ve `B=` içermeyen bir satır gönder → KIRMIZI.
    """
    from headless_core import HeadlessCore

    ayristir = HeadlessCore._parse_stm_tele
    sahte = HeadlessCore.__new__(HeadlessCore)

    g = ayristir(sahte, "-> STM_TELE: C=6,T=34.20,A=27.10,B=1.842,N=412")
    assert g == {
        "coil_id": 6,
        "object_temp": 34.2,
        "ambient_temp": 27.1,
        "magnetic_field": 1.842,
        "magnetic_samples": 412,
    }

    g = ayristir(sahte, "-> STM_TELE: C=6,B=8.750,N=1,S=1")
    assert g["magnetic_saturated"] is True, "doygunluk bayragi TASINMIYOR -> guvenilmez deger sessizce doza girer"
    assert g["magnetic_samples"] == 1

    # Alan YOKKEN ornek/doygunluk anahtari HIC olmamali.
    g = ayristir(sahte, "-> STM_TELE: C=3,I=2.140")
    assert "magnetic_samples" not in g and "magnetic_saturated" not in g
    assert "magnetic_field" not in g, "olculmeyen alan icin anahtar uretildi"

    # ⚠️ KARSIT-KANIT: `N=`/`S=` ALAN OLMADAN gelirse (bozuk/yabanci satir, yarim yazilmis
    # UART tamponu) hayalet anahtar URETILMEMELI. Ilk sinama bunu OLCMUYORDU — o satirda
    # `N=` zaten yoktu, yani kapi mutasyona YESIL kaliyordu (2026-09-11).
    g = ayristir(sahte, "-> STM_TELE: C=6,N=400,S=1,I=1.500")
    assert "magnetic_samples" not in g, "alan YOKKEN ornek sayisi uretildi -> asagi akis 'olculdu' saymaya baslar"
    assert "magnetic_saturated" not in g, "alan YOKKEN doygunluk bayragi uretildi"
    assert g["current"] == pytest.approx(1.5), "ayni satirdaki gecerli akim alani kayboldu"

    # Eski (N/S'siz) firmware satiri HALA ayristirilmali — atomik olmayan sevk penceresi.
    g = ayristir(sahte, "-> STM_TELE: C=6,T=34.20,A=27.10,B=1.842")
    assert g["magnetic_field"] == pytest.approx(1.842)
    assert "magnetic_samples" not in g
