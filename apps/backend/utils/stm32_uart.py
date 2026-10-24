# -*- coding: utf-8 -*-
"""STM32 UART OKUMA — port seçimi + açılış banner'ını dinleme. TEK KAYNAK.

⚠️ **NEDEN `utils/` ALTINDA, `scripts/` ALTINDA DEĞİL** (ölçüldü 2026-09-22):
sevk edilen pakete `scripts/` altından YALNIZ altı `.ps1` giriyor
(`build_tools/make_base_zip.py::ADD_SCRIPTS`) — `scripts/*.py` **HİÇ gitmiyor**.
Donmuş EXE `utils`'i bundle'lar. Firmware güncellemesi kurulu cihazda banner okumak
zorunda; mantık `scripts/` altında kalsaydı sahada **hiç bulunmazdı**.
Aynı gerekçe `build_tools/source_crypto.py` başlığında da yazılı — bu, deponun yerleşik
deseni: *ilkeler `utils`'de durur, `scripts/` yalnız CLI yüzüdür.*

⚠️ BU MODÜL **YAZDIRMAZ**. Kütüphanedir; `print` çağıran bir kütüphane, arayüzü olmayan
bir serviste (NSSM/pipe) stdout'u doldurup kilitlenmeye yol açabilir — bu depoda
`_configure_logging` notunda ölçülmüş bir sınıf. Port listesi VERİ olarak döner,
yazdırma çağırana aittir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from utils.stm32_kimlik import PAKET_RED_CRC_ESIGI, banner_ayristir

BAUD = 115200

#: T-a (Tezgâh-2 #1, 2026-10-23) — SERVİS ARAÇLARININ (kimlik betiği, `stm_yak` yakma sonrası doğrulaması) yoklama sayısı red eşiğinin
#: ÜÇ KATI. Saha imajlı kart telemetri basarken NACK'i DÜŞÜRÜR (eski firmware TX meşgulken yanıtı atar): 3 yoklamaya 2 `STM_NACK: CRC`
#: geldi, eşik (3) dolmadı → eski kart "doğrulanamadı" sayıldı, uyumsuz ikili kartta KALDI. Kabul / red görülünce yoklama erken biter.
#: Backend el sıkışması BUNU KULLANMAZ (bkz. `stm32_transport.DOGRULAMA_*` notu: ACİL DURDUR gecikmesi + geç NACK sızıntısı).
ARAC_DOGRULAMA_YOKLAMA_SAYISI = 3 * PAKET_RED_CRC_ESIGI
#: Seri okuma zaman aşımı (`serial.Serial(..., timeout=0.3)`): yanıtsız kartta her tur bu kadar bekler → pencere bütün yoklamalara yeter.
ARAC_OKUMA_ZAMAN_ASIMI_SN = 0.3

#: Banner'ın yanı sıra toplanan ilgi çekici satırlar (tanılama için). TD1: `STM_ID` (Y68 kimlik yanıtı) ve `STM_OK` (paket
#: kabulü) de toplanır — uyum kararı bunlardan verilir (`utils.stm32_kimlik.satirlardan_karar`).
ILGI_ANAHTARLARI = ("STM_READY", "STM_ID", "STM_OK", "STM_NACK", "STM_SENS", "STM_ERR", "STM_TELE")


@dataclass(frozen=True)
class PortBilgisi:
    aygit: str
    aciklama: str


def portlari_listele() -> list[PortBilgisi]:
    """Sistemdeki seri portlar. `pyserial` yoksa boş liste (çağıran karar verir)."""
    try:
        from serial.tools import list_ports
    except Exception:
        return []
    return [PortBilgisi(p.device, p.description or "") for p in list_ports.comports()]


def port_adaylari(istenen: str | None = None) -> list[str]:
    """Denenecek portlar — ST-Link VCP ÖNCE.

    ⚠️ Öncelik ölçütü `utils/stm32_transport` ile aynı olmalı: backend orayı kullanıyor,
    bu modül de tanılama/yakma sonrası doğrulamada kullanıyor. İkisi ayrı port seçerse
    "backend bağlı ama betik başka kartı okuyor" durumu doğar.
    """
    if istenen:
        return [istenen]
    hepsi = portlari_listele()
    oncelikli = [p.aygit for p in hepsi if any(k in p.aciklama.upper() for k in ("ST-LINK", "STLINK", "STM"))]
    return oncelikli + [p.aygit for p in hepsi if p.aygit not in oncelikli]


def banner_dinle(port: str, sure: float = 12.0) -> tuple[int | None, list[str]]:
    """(kanal_sayısı | None, toplanan satırlar).

    Kart açılış banner'ını YALNIZ RESET'te basar; `sure` boyunca dinlenir. Banner
    ayrıştırılır ayrıştırılmaz döner (beklemeye gerek yok).

    ⚠️ Seri port TEK KULLANICILIDIR: backend çalışıyorsa portu tutar ve burada
    `SerialException` yükselir. Çağıran bunu YUTMAMALI, açıkça söylemeli — "hiçbir şey
    duyulmadı" ile "port meşgul" farklı arızalardır.
    """
    import serial  # yerel import: modül, pyserial olmayan ortamda da import edilebilsin

    satirlar: list[str] = []
    with serial.Serial(port, BAUD, timeout=0.3) as s:
        bitis = time.monotonic() + sure
        tampon = b""
        while time.monotonic() < bitis:
            tampon += s.read(4096)
            while b"\n" in tampon:
                ham, tampon = tampon.split(b"\n", 1)
                satir = ham.decode("utf-8", "replace").strip()
                if not satir:
                    continue
                if any(k in satir for k in ILGI_ANAHTARLARI):
                    satirlar.append(satir)
                kimlik = banner_ayristir(satir)
                if kimlik:
                    return kimlik.kanal, satirlar
    return None, satirlar


def kart_dogrula(port: str, sure: float = 12.0) -> tuple[list[str], dict]:
    """TD1-d / TD1-e (tezgâh 2026-10-14): kartın uyumunu BANNER'LA DEĞİL KANITLA ölç — (toplanan satırlar, yoklama özeti).

    ⚠️ NEDEN: 120 ve 121 baytlık firmware AYNI banner'ı basar; servis betiği uyumsuz kartta "UYUMLU" dedi, yakma akışı yakmayı
    banner'dan "doğruladı". (1) `sure` boyunca banner beklenir (kart RESET'te basar; resetsiz kart basmaz — yine de doğrulanır),
    (2) backend'in el sıkışmasıyla AYNI doğrulama yoklaması (`Stm32SerialTransport._dogrulama_yoklamasi`): Y68 kimlik sorgusu +
    en çok `ARAC_DOGRULAMA_YOKLAMA_SAYISI` sıfır-duty paketi (STOP — çıkışlara güvenli; T-a: red eşiğinin üç katı — eski kart telemetri
    basarken NACK düşürür). Karar çağıranda: `stm32_kimlik.satirlardan_karar(satirlar)`.
    ⚠️ Seri port TEK KULLANICILIDIR: backend çalışıyorsa `SerialException` yükselir (çağıran "port meşgul" der)."""
    import serial  # yerel import: modül, pyserial olmayan ortamda da import edilebilsin

    from utils.stm32_transport import Stm32PortCandidate, Stm32SerialTransport

    satirlar: list[str] = []

    def _topla(satir: str) -> None:
        if any(k in satir for k in ILGI_ANAHTARLARI):
            satirlar.append(satir)

    from utils.stm32_transport import DOGRULAMA_ARALIK_SN, DOGRULAMA_KIMLIK_BEKLEME_SN

    pencere = (
        ARAC_DOGRULAMA_YOKLAMA_SAYISI * (DOGRULAMA_ARALIK_SN + ARAC_OKUMA_ZAMAN_ASIMI_SN) + DOGRULAMA_KIMLIK_BEKLEME_SN
    )
    with serial.Serial(port, BAUD, timeout=ARAC_OKUMA_ZAMAN_ASIMI_SN) as s:
        hazir = ""
        bitis = time.monotonic() + max(0.0, float(sure))
        while time.monotonic() < bitis:
            ham = s.readline()
            if not ham:
                continue
            satir = ham.decode("utf-8", "replace").strip()
            if not satir:
                continue
            _topla(satir)
            if banner_ayristir(satir):
                hazir = satir
                break
        ozet = Stm32SerialTransport(None)._dogrulama_yoklamasi(
            s,
            Stm32PortCandidate(device=port),
            None,
            _topla,
            hazir,
            yoklama_sayisi=ARAC_DOGRULAMA_YOKLAMA_SAYISI,
            sure_sn=pencere,
        )
    return satirlar, ozet
